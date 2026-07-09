"""
DatabarClient — the core SDK client for api.databar.ai/v1.

Covers all endpoints with:
  - Exponential backoff retry (3 attempts, skip 4xx except 429)
  - Async task polling with configurable timeout; handles partially_completed
  - Auto-batching for row operations (50 per request, API limit)
  - Sync convenience wrappers that submit + poll in one call
  - Typed exceptions for every error condition
  - API key auto-read from DATABAR_API_KEY env var

Endpoint groups:
  - User:        get_user
  - Tasks:       get_task, poll_task
  - Enrichments: list_enrichments, get_enrichment, run_enrichment[_bulk][_sync],
                 get_param_choices
  - Waterfalls:  list_waterfalls, get_waterfall, run_waterfall[_bulk][_sync]
  - Tables:      create_table, list_tables, delete_table, rename_table,
                 get_columns, create_column, rename_column, delete_column,
                 get_table_enrichments, add_enrichment, run_table_enrichment,
                 add_waterfall, get_table_waterfalls,
                 add_exporter, get_table_exporters,
                 get_rows, create_rows, patch_rows, upsert_rows, delete_rows
  - Exporters:   list_exporters, get_exporter
  - Connectors:  list_connectors, get_connector, create_connector,
                 update_connector, delete_connector
  - Folders:     create_folder, list_folders, rename_folder, delete_folder,
                 move_table_to_folder
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Literal, Optional, Union

import httpx

from .exceptions import (
    DatabarAuthError,
    DatabarError,
    DatabarGoneError,
    DatabarInsufficientCreditsError,
    DatabarNotFoundError,
    DatabarRateLimitError,
    DatabarTaskFailedError,
    DatabarTimeoutError,
    DatabarValidationError,
)
from .models import (
    AddEnrichmentResponse,
    AddExporterResponse,
    AddWaterfallResponse,
    AuthorizationInfo,
    BatchInsertResponse,
    BatchUpdateResponse,
    BatchUpdateRow,
    ChoicesResponse,
    Column,
    Connection,
    Connector,
    CreateColumnResponse,
    DedupeOptions,
    Enrichment,
    EnrichmentListResponse,
    EnrichmentSummary,
    Exporter,
    ExporterDetail,
    ExporterListResponse,
    ExporterParam,
    ExporterResponseField,
    Folder,
    InsertOptions,
    InsertRow,
    InstalledExporter,
    InstalledWaterfall,
    NameValue,
    RunEnrichmentResponse,
    RowsResponse,
    RunResponse,
    Table,
    TableEnrichment,
    TaskResponse,
    UpsertResponse,
    UpsertRow,
    User,
    Waterfall,
)

DEFAULT_BASE_URL = "https://api.databar.ai/v1"
_ROW_BATCH_SIZE = 50
_MAX_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 1.0


def _chunk(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


class DatabarClient:
    """
    Synchronous client for the Databar API.

    Usage::

        from databar import DatabarClient

        client = DatabarClient(api_key="your-key")
        enrichments = client.list_enrichments()
        result = client.run_enrichment_sync(123, {"email": "alice@example.com"})
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_poll_attempts: int = 150,
        poll_interval_s: float = 2.0,
    ) -> None:
        resolved_key = api_key or os.environ.get("DATABAR_API_KEY")
        if not resolved_key:
            import shutil
            msg = (
                "No API key provided. Pass api_key= or set the DATABAR_API_KEY "
                "environment variable. Run `databar login` to save your key."
            )
            if shutil.which("databar") is not None:
                msg += (
                    "\n\nUsing Databar with an AI agent (Claude Code, Cursor, etc.)? "
                    "Run `databar agent-guide` for agent-optimized setup instructions."
                )
            raise DatabarAuthError(msg)
        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_poll_attempts = max_poll_attempts
        self._poll_interval_s = poll_interval_s
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"x-apikey": self._api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> DatabarClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        status = response.status_code
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        if status in (401, 403):
            raise DatabarAuthError(
                "Invalid API key or insufficient permissions. Check your API key.",
                status_code=status,
                response_body=body,
            )
        if status == 404:
            raise DatabarNotFoundError(
                "Resource not found.",
                status_code=status,
                response_body=body,
            )
        if status == 406:
            raise DatabarInsufficientCreditsError(
                "Insufficient credits. Top up your account at databar.ai.",
                status_code=status,
                response_body=body,
            )
        if status == 410:
            raise DatabarGoneError(
                "Task data has expired. Results are only stored for 24 hours after "
                "completion. Re-run the enrichment to fetch fresh data.",
                status_code=status,
                response_body=body,
            )
        if status == 422:
            detail = body.get("detail", [])
            if isinstance(detail, list):
                errors = [f"{'.'.join(str(l) for l in d.get('loc', []))}: {d.get('msg', '')}" for d in detail]
                msg = "Validation error: " + "; ".join(errors)
            else:
                msg = f"Validation error: {detail}"
            raise DatabarValidationError(
                msg,
                errors=detail if isinstance(detail, list) else [],
                status_code=422,
                response_body=body,
            )
        if status == 429:
            raise DatabarRateLimitError(
                "Rate limit exceeded. Please try again later.",
                status_code=status,
                response_body=body,
            )

        error_msg = body.get("error") or body.get("detail") or response.text
        raise DatabarError(
            f"API error ({status}): {error_msg}",
            status_code=status,
            response_body=body,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict] = None,
        json: Any = None,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRY_ATTEMPTS):
            try:
                response = self._http.request(
                    method, path, params=params, json=json
                )
                self._raise_for_response(response)
                return response.json() if response.content else None
            except (DatabarRateLimitError, DatabarError) as exc:
                if isinstance(exc, DatabarError) and exc.status_code is not None:
                    if 400 <= exc.status_code < 500 and exc.status_code != 429:
                        raise
                last_exc = exc
                if attempt < _MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(_RETRY_BASE_DELAY_S * (2 ** attempt))
            except httpx.TransportError as exc:
                last_exc = DatabarError(f"Network error: {exc}")
                if attempt < _MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(_RETRY_BASE_DELAY_S * (2 ** attempt))

        raise last_exc  # type: ignore[misc]

    # -----------------------------------------------------------------------
    # Task polling
    # -----------------------------------------------------------------------

    def get_task(self, task_id: str) -> TaskResponse:
        """Get the current status of a task."""
        data = self._request("GET", f"/tasks/{task_id}")
        return TaskResponse.model_validate(data)

    def poll_task(self, task_id: str) -> Any:
        """
        Poll until a task completes or times out.

        Returns the task's data payload on success (status completed or partially_completed).
        Raises DatabarTaskFailedError, DatabarGoneError or DatabarTimeoutError otherwise.

        For bulk runs the payload is a list aligned to the inputs: one element
        per input in input order, with ``None`` for inputs that returned no data
        (so ``len(data) == number of inputs`` and ``data[i]`` ↔ ``input[i]``). A
        single run returns the bare result object.

        Task data is stored for 24 hours. After that the status becomes 'gone'.
        """
        for _ in range(self._max_poll_attempts):
            time.sleep(self._poll_interval_s)
            task = self.get_task(task_id)
            status = task.status.lower()

            if status in ("completed", "success", "partially_completed"):
                return task.data

            if status in ("failed", "error"):
                error = task.error
                if isinstance(error, list):
                    msg = "; ".join(error)
                else:
                    msg = error or "Task failed with no error message."
                raise DatabarTaskFailedError(msg, task_id=task_id, response_body=task.model_dump())

            if status == "gone":
                raise DatabarGoneError(
                    "Task data has expired. Re-run the enrichment to get fresh results.",
                    response_body=task.model_dump(),
                )
            # "processing", "no_data" → continue polling

        raise DatabarTimeoutError(task_id, self._max_poll_attempts, self._poll_interval_s)

    # -----------------------------------------------------------------------
    # User
    # -----------------------------------------------------------------------

    def get_user(self) -> User:
        """Get the current authenticated user's info and credit balance."""
        data = self._request("GET", "/user/me")
        return User.model_validate(data)

    # -----------------------------------------------------------------------
    # Enrichments
    # -----------------------------------------------------------------------

    def list_enrichments(
        self,
        q: Optional[str] = None,
        page: Optional[int] = None,
        limit: int = 50,
        authorized_only: bool = True,
        category: Optional[str] = None,
    ) -> Union[List[EnrichmentSummary], EnrichmentListResponse]:
        """
        List available enrichments.

        Without ``page`` (default): returns a plain list of :class:`EnrichmentSummary`.
        With ``page``: returns a paginated :class:`EnrichmentListResponse` envelope.

        Args:
            q: Search query to filter results.
            page: Page number for paginated results. When set, returns EnrichmentListResponse.
            limit: Items per page (only used with page). Max 500.
            authorized_only: Only show enrichments the user has access to (default True).
            category: Filter by category name (e.g. 'Company Data').
        """
        params: Dict[str, Any] = {}
        if not authorized_only:
            params["authorized_only"] = "false"
        if q:
            params["q"] = q
        if page is not None:
            params["page"] = page
            params["limit"] = limit
        if category:
            params["category"] = category

        data = self._request("GET", "/enrichments/", params=params if params else None)

        if page is not None:
            return EnrichmentListResponse(
                items=[EnrichmentSummary.model_validate(e) for e in data.get("items", data)],
                page=data["page"],
                limit=data["limit"],
                has_next_page=data["has_next_page"],
                total_count=data["total_count"],
            )
        return [EnrichmentSummary.model_validate(e) for e in data]

    def get_enrichment(self, enrichment_id: int) -> Enrichment:
        """Get full details for a specific enrichment including params and response fields."""
        data = self._request("GET", f"/enrichments/{enrichment_id}")
        return Enrichment.model_validate(data)

    def run_enrichment(
        self,
        enrichment_id: int,
        params: Dict[str, Any],
        pages: Optional[int] = None,
    ) -> RunResponse:
        """
        Submit an enrichment run. Returns a task — use poll_task() or run_enrichment_sync().

        Args:
            enrichment_id: The enrichment to run.
            params: Enrichment input parameters.
            pages: For list-style enrichments, number of result pages to fetch.
        """
        body: Dict[str, Any] = {"params": params}
        if pages is not None and pages > 1:
            body["pagination"] = {"pages": pages}
        data = self._request("POST", f"/enrichments/{enrichment_id}/run", json=body)
        return RunResponse.model_validate(data)

    def run_enrichment_bulk(
        self,
        enrichment_id: int,
        params: List[Dict[str, Any]],
        pages: Optional[int] = None,
    ) -> RunResponse:
        """
        Submit a bulk enrichment run for multiple inputs.

        The polled result is aligned to the inputs: one element per input, in the
        same order as ``params``, with ``None`` for inputs that returned no data.
        So ``len(result) == len(params)`` and ``result[i]`` is the result for
        ``params[i]`` — join results back to inputs by position.

        Args:
            enrichment_id: The enrichment to run.
            params: List of per-row input parameter dicts.
            pages: For list-style enrichments, pages to fetch per row.
        """
        body: Dict[str, Any] = {"params": params}
        if pages is not None and pages > 1:
            body["pagination"] = {"pages": pages}
        data = self._request("POST", f"/enrichments/{enrichment_id}/bulk-run", json=body)
        return RunResponse.model_validate(data)

    def run_enrichment_sync(
        self,
        enrichment_id: int,
        params: Dict[str, Any],
        pages: Optional[int] = None,
    ) -> Any:
        """Submit and poll an enrichment, returning final data when complete."""
        task = self.run_enrichment(enrichment_id, params, pages=pages)
        return self.poll_task(task.task_id)

    def run_enrichment_bulk_sync(
        self,
        enrichment_id: int,
        params: List[Dict[str, Any]],
        pages: Optional[int] = None,
    ) -> Any:
        """Submit and poll a bulk enrichment, returning final data when complete.

        Returns a list aligned to ``params``: one element per input in input
        order, ``None`` for misses (``len(result) == len(params)``).
        """
        task = self.run_enrichment_bulk(enrichment_id, params, pages=pages)
        return self.poll_task(task.task_id)

    def get_param_choices(
        self,
        enrichment_id: int,
        param_slug: str,
        q: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> ChoicesResponse:
        """Get paginated choices for a select/mselect enrichment parameter."""
        params: Dict[str, Any] = {"page": page, "limit": limit}
        if q:
            params["q"] = q
        data = self._request(
            "GET",
            f"/enrichments/{enrichment_id}/params/{param_slug}/choices",
            params=params,
        )
        return ChoicesResponse.model_validate(data)

    # -----------------------------------------------------------------------
    # Waterfalls
    # -----------------------------------------------------------------------

    def list_waterfalls(self) -> List[Waterfall]:
        """List all available waterfall enrichments."""
        data = self._request("GET", "/waterfalls/")
        return [Waterfall.model_validate(w) for w in data]

    def get_waterfall(self, identifier: str) -> Waterfall:
        """Get details for a specific waterfall."""
        data = self._request("GET", f"/waterfalls/{identifier}")
        return Waterfall.model_validate(data)

    def run_waterfall(
        self,
        identifier: str,
        params: Dict[str, Any],
        enrichments: Optional[List[int]] = None,
        email_verifier: Optional[int] = None,
    ) -> RunResponse:
        """
        Submit a waterfall run.

        If enrichments is None or empty, all available providers are used
        (auto-resolved from get_waterfall, same behavior as MCP).
        """
        if not enrichments:
            waterfall = self.get_waterfall(identifier)
            enrichments = [e.id for e in waterfall.available_enrichments]

        payload: Dict[str, Any] = {"params": params, "enrichments": enrichments}
        if email_verifier is not None:
            payload["email_verifier"] = email_verifier

        data = self._request("POST", f"/waterfalls/{identifier}/run", json=payload)
        return RunResponse.model_validate(data)

    def run_waterfall_bulk(
        self,
        identifier: str,
        params: List[Dict[str, Any]],
        enrichments: Optional[List[int]] = None,
        email_verifier: Optional[int] = None,
    ) -> RunResponse:
        """Submit a bulk waterfall run for multiple inputs.

        The polled result is aligned to the inputs: one element per input, in the
        same order as ``params``, with ``None`` for inputs that returned no data
        (``len(result) == len(params)``, ``result[i]`` ↔ ``params[i]``).
        """
        if not enrichments:
            waterfall = self.get_waterfall(identifier)
            enrichments = [e.id for e in waterfall.available_enrichments]

        payload: Dict[str, Any] = {"params": params, "enrichments": enrichments}
        if email_verifier is not None:
            payload["email_verifier"] = email_verifier

        data = self._request("POST", f"/waterfalls/{identifier}/bulk-run", json=payload)
        return RunResponse.model_validate(data)

    def run_waterfall_sync(
        self,
        identifier: str,
        params: Dict[str, Any],
        enrichments: Optional[List[int]] = None,
        email_verifier: Optional[int] = None,
    ) -> Any:
        """Submit and poll a waterfall, returning final data when complete."""
        task = self.run_waterfall(identifier, params, enrichments, email_verifier)
        return self.poll_task(task.task_id)

    def run_waterfall_bulk_sync(
        self,
        identifier: str,
        params: List[Dict[str, Any]],
        enrichments: Optional[List[int]] = None,
        email_verifier: Optional[int] = None,
    ) -> Any:
        """Submit and poll a bulk waterfall, returning final data when complete.

        Returns a list aligned to ``params``: one element per input in input
        order, ``None`` for misses (``len(result) == len(params)``).
        """
        task = self.run_waterfall_bulk(identifier, params, enrichments, email_verifier)
        return self.poll_task(task.task_id)

    # -----------------------------------------------------------------------
    # Tables — CRUD
    # -----------------------------------------------------------------------

    def create_table(
        self,
        name: Optional[str] = None,
        columns: Optional[List[str]] = None,
        rows: int = 0,
    ) -> Table:
        """
        Create a new empty table.

        Args:
            name: Table name. Defaults to 'New empty table'.
            columns: Pre-defined column names. Defaults to column1/column2/column3.
            rows: Number of empty placeholder rows to create (default 0).
        """
        payload: Dict[str, Any] = {"rows": rows}
        if name is not None:
            payload["name"] = name
        if columns is not None:
            payload["columns"] = columns
        data = self._request("POST", "/table/create", json=payload)
        return Table.model_validate(data)

    def list_tables(self) -> List[Table]:
        """List all tables in the workspace."""
        data = self._request("GET", "/table/")
        return [Table.model_validate(t) for t in data]

    def delete_table(self, table_uuid: str) -> None:
        """Permanently delete a table and all its rows."""
        self._request("DELETE", f"/table/{table_uuid}")

    def rename_table(self, table_uuid: str, name: str) -> Table:
        """Rename a table."""
        data = self._request("PATCH", f"/table/{table_uuid}", json={"name": name})
        return Table.model_validate(data)

    # -----------------------------------------------------------------------
    # Tables — Columns
    # -----------------------------------------------------------------------

    def get_columns(self, table_uuid: str) -> List[Column]:
        """Get all columns defined on a table."""
        data = self._request("GET", f"/table/{table_uuid}/columns")
        return [Column.model_validate(c) for c in data]

    def create_column(
        self,
        table_uuid: str,
        name: str,
        type: str = "text",
        config: Optional[Dict[str, Any]] = None,
    ) -> CreateColumnResponse:
        """
        Add a new column to a table.

        Args:
            table_uuid: UUID of the table.
            name: Column display name.
            type: Column type (default 'text').
            config: Column configuration dict (default empty).
        """
        data = self._request(
            "POST",
            f"/table/{table_uuid}/columns",
            json={"name": name, "type": type, "config": config or {}},
        )
        return CreateColumnResponse.model_validate(data)

    def rename_column(
        self,
        table_uuid: str,
        column_id: str,
        name: str,
    ) -> CreateColumnResponse:
        """Rename an existing column."""
        data = self._request(
            "PATCH",
            f"/table/{table_uuid}/columns/{column_id}",
            json={"name": name},
        )
        return CreateColumnResponse.model_validate(data)

    def delete_column(self, table_uuid: str, column_id: str) -> None:
        """Delete a column from a table."""
        self._request("DELETE", f"/table/{table_uuid}/columns/{column_id}")

    # -----------------------------------------------------------------------
    # Tables — Enrichments
    # -----------------------------------------------------------------------

    def get_table_enrichments(self, table_uuid: str) -> List[TableEnrichment]:
        """List enrichments configured on a table."""
        data = self._request("GET", f"/table/{table_uuid}/enrichments")
        return [TableEnrichment.model_validate(e) for e in data]

    def add_enrichment(
        self,
        table_uuid: str,
        enrichment_id: int,
        mapping: Dict[str, Any],
        launch_strategy: Literal["run_on_click", "run_on_update"] = "run_on_click",
    ) -> AddEnrichmentResponse:
        """
        Add an enrichment to a table with a parameter-to-column mapping.

        ``mapping`` keys are enrichment parameter names. Values are dicts with:
          - ``{"type": "mapping", "value": "<column-name-or-uuid>"}``
            — reads the value from a table column per row.
            You may pass a human-readable column name; the SDK will automatically
            resolve it to the required column UUID via GET /table/{uuid}/columns.
          - ``{"type": "simple", "value": "<static-value>"}``
            — uses the same hardcoded value for every row.

        Args:
            launch_strategy: 'run_on_click' (manual) or 'run_on_update' (auto-trigger
                when mapped input columns change).

        Returns:
            :class:`AddEnrichmentResponse` with ``id`` (table-enrichment id) and
            ``enrichment_name``. Use ``id`` with run_table_enrichment().
        """
        resolved_mapping: Dict[str, Any] = {}
        column_map: Optional[Dict[str, str]] = None

        for param, entry in mapping.items():
            if not isinstance(entry, dict) or entry.get("type") != "mapping":
                resolved_mapping[param] = entry
                continue

            value = entry.get("value", "")
            if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", str(value), re.IGNORECASE):
                resolved_mapping[param] = entry
                continue

            if column_map is None:
                columns = self.get_columns(table_uuid)
                column_map = {c.name: c.identifier for c in columns}

            uuid = column_map.get(value)
            if uuid is None:
                resolved_mapping[param] = entry
            else:
                resolved_mapping[param] = {**entry, "value": uuid}

        payload: Dict[str, Any] = {
            "enrichment": enrichment_id,
            "mapping": resolved_mapping,
            "launch_strategy": launch_strategy,
        }
        data = self._request("POST", f"/table/{table_uuid}/add-enrichment", json=payload)
        return AddEnrichmentResponse.model_validate(data)

    def run_table_enrichment(
        self,
        table_uuid: str,
        enrichment_id: str,
        run_strategy: Literal["run_all", "run_empty", "run_errors"] = "run_all",
        row_ids: Optional[List[str]] = None,
    ) -> RunEnrichmentResponse:
        """
        Trigger an enrichment or waterfall to run on table rows.

        Args:
            table_uuid: UUID of the table.
            enrichment_id: ID of the table enrichment (from add_enrichment or add_waterfall).
            run_strategy: 'run_all' (default), 'run_empty' (skip rows with results),
                or 'run_errors' (only re-run rows that errored).
            row_ids: Optional list of specific row UUIDs to process.
        """
        body: Dict[str, Any] = {"run_strategy": run_strategy}
        if row_ids is not None:
            body["row_ids"] = row_ids
        data = self._request(
            "POST",
            f"/table/{table_uuid}/run-enrichment/{enrichment_id}",
            json=body,
        )
        return RunEnrichmentResponse.model_validate(data)

    # -----------------------------------------------------------------------
    # Tables — Waterfalls
    # -----------------------------------------------------------------------

    def add_waterfall(
        self,
        table_uuid: str,
        waterfall_identifier: str,
        enrichments: List[int],
        mapping: Dict[str, str],
        email_verifier: Optional[int] = None,
    ) -> AddWaterfallResponse:
        """
        Add a waterfall to a table.

        Args:
            table_uuid: UUID of the table.
            waterfall_identifier: Waterfall slug (e.g. 'email_getter').
            enrichments: List of enrichment (provider) IDs to use in the cascade.
            mapping: Maps waterfall parameter names to column UUIDs or column names.
                The API resolves names to UUIDs automatically.
            email_verifier: Optional enrichment ID for email verification.

        Returns:
            :class:`AddWaterfallResponse` with ``id`` and ``waterfall_name``.
            Use ``id`` with run_table_enrichment().
        """
        payload: Dict[str, Any] = {
            "waterfall": waterfall_identifier,
            "enrichments": enrichments,
            "mapping": mapping,
        }
        if email_verifier is not None:
            payload["email_verifier"] = email_verifier
        data = self._request("POST", f"/table/{table_uuid}/add-waterfall", json=payload)
        return AddWaterfallResponse.model_validate(data)

    def get_table_waterfalls(self, table_uuid: str) -> List[InstalledWaterfall]:
        """List waterfalls installed on a table."""
        data = self._request("GET", f"/table/{table_uuid}/waterfalls")
        return [InstalledWaterfall.model_validate(w) for w in data]

    # -----------------------------------------------------------------------
    # Tables — Exporters
    # -----------------------------------------------------------------------

    def add_exporter(
        self,
        table_uuid: str,
        exporter_id: int,
        mapping: Dict[str, Any],
        launch_strategy: Literal["run_on_click", "run_on_update"] = "run_on_click",
        authorization: Optional[int] = None,
        custom_body_template: Optional[str] = None,
    ) -> AddExporterResponse:
        """
        Add an exporter to a table.

        Args:
            table_uuid: UUID of the table.
            exporter_id: The exporter ID (from list_exporters).
            mapping: Parameter mapping. Keys are exporter parameter slugs. Values are
                ``{"type": "mapping"|"simple", "value": "<column-name-or-uuid|static-value>"}``.
            launch_strategy: 'run_on_click' (manual) or 'run_on_update' (auto-trigger).
            authorization: ID of the API key / OAuth connection to use. Auto-selected if omitted.
            custom_body_template: Custom JSON body template. Column values referenced via
                {column_internal_name} placeholders. When set, mapping is ignored.

        Returns:
            :class:`AddExporterResponse` with ``id`` and ``exporter_name``.
            Use ``id`` with run_table_enrichment().
        """
        payload: Dict[str, Any] = {
            "exporter": exporter_id,
            "mapping": mapping,
            "launch_strategy": launch_strategy,
        }
        if authorization is not None:
            payload["authorization"] = authorization
        if custom_body_template is not None:
            payload["custom_body_template"] = custom_body_template
        data = self._request("POST", f"/table/{table_uuid}/add-exporter", json=payload)
        return AddExporterResponse.model_validate(data)

    def get_table_exporters(self, table_uuid: str) -> List[InstalledExporter]:
        """List exporters installed on a table."""
        data = self._request("GET", f"/table/{table_uuid}/exporters")
        return [InstalledExporter.model_validate(e) for e in data]

    # -----------------------------------------------------------------------
    # Rows
    # -----------------------------------------------------------------------

    def get_rows(
        self,
        table_uuid: str,
        page: int = 1,
        per_page: int = 100,
        filter: Optional[str] = None,
    ) -> RowsResponse:
        """
        Get rows from a table with pagination and optional filtering.

        Args:
            table_uuid: UUID of the table.
            page: Page number (default 1).
            per_page: Rows per page (max 500, default 100).
            filter: JSON-encoded filter object. Keys are column names, values are
                operator objects. Supported operators: equals, contains, not_equals,
                is_empty, is_not_empty.
                Example: '{"company":{"contains":"tech"},"status":{"equals":"active"}}'

        Returns a :class:`RowsResponse` with ``.data``, ``.has_next_page``,
        ``.total_count``, ``.page``. Each row dict is keyed by column name and
        includes an ``id`` key.
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if filter is not None:
            params["filter"] = filter
        data = self._request(
            "GET",
            f"/table/{table_uuid}/rows",
            params=params,
        )
        return RowsResponse.model_validate(data)

    def create_rows(
        self,
        table_uuid: str,
        rows: List[InsertRow],
        options: Optional[InsertOptions] = None,
    ) -> BatchInsertResponse:
        """
        Insert rows into a table. Auto-batches into chunks of 50.

        Merges results from all batches into a single BatchInsertResponse.
        """
        all_results = []
        offset = 0

        for chunk in _chunk(rows, _ROW_BATCH_SIZE):
            payload: Dict[str, Any] = {
                "rows": [r.model_dump() for r in chunk]
            }
            if options is not None:
                payload["options"] = options.model_dump(exclude_none=True)

            data = self._request("POST", f"/table/{table_uuid}/rows", json=payload)
            response = BatchInsertResponse.model_validate(data)

            for item in response.results:
                adjusted = item.model_copy(update={"index": item.index + offset})
                all_results.append(adjusted)

            offset += len(chunk)

        return BatchInsertResponse(results=all_results)

    def patch_rows(
        self,
        table_uuid: str,
        rows: List[BatchUpdateRow],
        overwrite: bool = True,
        return_rows: bool = False,
    ) -> BatchUpdateResponse:
        """
        Update existing rows by row UUID. Auto-batches into chunks of 50.
        """
        all_results = []

        for chunk in _chunk(rows, _ROW_BATCH_SIZE):
            payload: Dict[str, Any] = {
                "rows": [r.model_dump() for r in chunk],
                "overwrite": overwrite,
                "return_rows": return_rows,
            }
            data = self._request("PATCH", f"/table/{table_uuid}/rows", json=payload)
            response = BatchUpdateResponse.model_validate(data)
            all_results.extend(response.results)

        return BatchUpdateResponse(results=all_results)

    def upsert_rows(
        self,
        table_uuid: str,
        rows: List[UpsertRow],
        return_rows: bool = False,
    ) -> UpsertResponse:
        """
        Insert or update rows by matching key column. Auto-batches into chunks of 50.
        """
        all_results = []

        for chunk in _chunk(rows, _ROW_BATCH_SIZE):
            payload: Dict[str, Any] = {
                "rows": [r.model_dump() for r in chunk],
                "return_rows": return_rows,
            }
            data = self._request("POST", f"/table/{table_uuid}/rows/upsert", json=payload)
            response = UpsertResponse.model_validate(data)
            all_results.extend(response.results)

        return UpsertResponse(results=all_results)

    def delete_rows(self, table_uuid: str, row_ids: List[str]) -> None:
        """Delete specific rows from a table by their UUIDs."""
        self._request(
            "POST",
            f"/table/{table_uuid}/rows/delete",
            json={"row_ids": row_ids},
        )

    # -----------------------------------------------------------------------
    # Exporters
    # -----------------------------------------------------------------------

    def list_exporters(
        self,
        q: Optional[str] = None,
        page: Optional[int] = None,
        limit: int = 50,
    ) -> Union[List[Exporter], ExporterListResponse]:
        """
        List available exporters (CRM/destination integrations).

        Without ``page`` (default): returns a plain list of :class:`Exporter`.
        With ``page``: returns a paginated :class:`ExporterListResponse` envelope.

        Args:
            q: Search query to filter results.
            page: Page number for paginated results.
            limit: Items per page (only used with page). Max 500.
        """
        params: Dict[str, Any] = {}
        if q:
            params["q"] = q
        if page is not None:
            params["page"] = page
            params["limit"] = limit

        data = self._request("GET", "/exporters/", params=params if params else None)

        if page is not None:
            return ExporterListResponse(
                items=[Exporter.model_validate(e) for e in data.get("items", data)],
                page=data["page"],
                limit=data["limit"],
                has_next_page=data["has_next_page"],
                total_count=data["total_count"],
            )
        return [Exporter.model_validate(e) for e in data]

    def get_exporter(self, exporter_id: int) -> ExporterDetail:
        """
        Get full details for a specific exporter, including params and authorization info.
        """
        data = self._request("GET", f"/exporters/{exporter_id}")
        return ExporterDetail.model_validate(data)

    # -----------------------------------------------------------------------
    # Connectors
    # -----------------------------------------------------------------------

    def list_connectors(self) -> List[Connector]:
        """List all custom API connectors in the workspace."""
        data = self._request("GET", "/connectors/")
        return [Connector.model_validate(c) for c in data]

    def get_connector(self, connector_id: int) -> Connector:
        """Get details of a specific custom API connector."""
        data = self._request("GET", f"/connectors/{connector_id}")
        return Connector.model_validate(data)

    def create_connector(
        self,
        name: str,
        method: str,
        url: str,
        type: str = "enrichment",
        headers: Optional[List[Dict[str, str]]] = None,
        parameters: Optional[List[Dict[str, str]]] = None,
        body: Optional[List[Dict[str, str]]] = None,
        body_template: Optional[str] = None,
        rate_limit: Optional[int] = None,
        max_concurrency: Optional[int] = None,
    ) -> Connector:
        """
        Register a new custom HTTP API endpoint as a connector.

        Once created the connector appears as an enrichment/exporter usable in tables.

        Args:
            name: Display name for the connector.
            method: HTTP method: get, post, put, or patch.
            url: Full API endpoint URL.
            type: Connector type: simple, enrichment, or exporter (default enrichment).
            headers: HTTP headers as list of {"name": ..., "value": ...} dicts.
            parameters: Query parameters as list of {"name": ..., "value": ...} dicts.
            body: Request body fields as list of {"name": ..., "value": ...} dicts.
            body_template: Jinja body template. When set, body params become template vars.
            rate_limit: Max requests per minute (capped by plan).
            max_concurrency: Max concurrent requests (capped by plan).
        """
        payload: Dict[str, Any] = {
            "name": name,
            "method": method,
            "url": url,
            "type": type,
            "headers": headers or [],
            "parameters": parameters or [],
            "body": body or [],
        }
        if body_template is not None:
            payload["body_template"] = body_template
        if rate_limit is not None:
            payload["rate_limit"] = rate_limit
        if max_concurrency is not None:
            payload["max_concurrency"] = max_concurrency
        data = self._request("POST", "/connectors/", json=payload)
        return Connector.model_validate(data)

    def update_connector(
        self,
        connector_id: int,
        name: str,
        method: str,
        url: str,
        type: str = "enrichment",
        headers: Optional[List[Dict[str, str]]] = None,
        parameters: Optional[List[Dict[str, str]]] = None,
        body: Optional[List[Dict[str, str]]] = None,
        body_template: Optional[str] = None,
        rate_limit: Optional[int] = None,
        max_concurrency: Optional[int] = None,
    ) -> Connector:
        """Replace the configuration of an existing custom API connector."""
        payload: Dict[str, Any] = {
            "name": name,
            "method": method,
            "url": url,
            "type": type,
            "headers": headers or [],
            "parameters": parameters or [],
            "body": body or [],
        }
        if body_template is not None:
            payload["body_template"] = body_template
        if rate_limit is not None:
            payload["rate_limit"] = rate_limit
        if max_concurrency is not None:
            payload["max_concurrency"] = max_concurrency
        data = self._request("PUT", f"/connectors/{connector_id}", json=payload)
        return Connector.model_validate(data)

    def delete_connector(self, connector_id: int) -> None:
        """Permanently remove a custom API connector."""
        self._request("DELETE", f"/connectors/{connector_id}")

    # -----------------------------------------------------------------------
    # Folders
    # -----------------------------------------------------------------------

    def create_folder(self, name: str) -> Folder:
        """Create a new folder to organize tables."""
        data = self._request("POST", "/folders", json={"name": name})
        return Folder.model_validate(data)

    def list_folders(self) -> List[Folder]:
        """List all folders in the workspace."""
        data = self._request("GET", "/folders")
        return [Folder.model_validate(f) for f in data]

    def rename_folder(self, folder_id: int, name: str) -> Folder:
        """Rename an existing folder."""
        data = self._request("PATCH", f"/folders/{folder_id}", json={"name": name})
        return Folder.model_validate(data)

    def delete_folder(self, folder_id: int) -> None:
        """Delete a folder. Tables in the folder are moved to the root level."""
        self._request("DELETE", f"/folders/{folder_id}")

    def move_table_to_folder(
        self,
        table_uuid: str,
        folder_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Move a table into a folder, or remove it from its current folder.

        Pass folder_id=None (default) to remove the table from any folder.
        """
        payload: Dict[str, Any] = {"table_uuid": table_uuid}
        if folder_id is not None:
            payload["folder_id"] = folder_id
        data = self._request("POST", "/folders/move-table", json=payload)
        return data or {}
