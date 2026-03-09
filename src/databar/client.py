"""
DatabarClient — the core SDK client for api.databar.ai/v1.

Covers all 19 endpoints with:
  - Exponential backoff retry (3 attempts, skip 4xx except 429)
  - Async task polling with configurable timeout
  - Auto-batching for row operations (50 per request, API limit)
  - Sync convenience wrappers that submit + poll in one call
  - Typed exceptions for every error condition
  - API key auto-read from DATABAR_API_KEY env var

Behavior is modeled on the TypeScript MCP reference implementation
in databar_mcp/src/databar-client.ts.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

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
    BatchInsertResponse,
    BatchUpdateResponse,
    BatchUpdateRow,
    ChoicesResponse,
    Column,
    Enrichment,
    EnrichmentSummary,
    InsertOptions,
    InsertRow,
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
            raise DatabarAuthError(
                "No API key provided. Pass api_key= or set the DATABAR_API_KEY "
                "environment variable. Run `databar login` to save your key."
            )
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
                "Task data has expired. Results are only stored for 1 hour after "
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
                # Retry on 429 and 5xx; don't retry other 4xx
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

        Returns the task's data payload on success.
        Raises DatabarTaskFailedError or DatabarTimeoutError otherwise.
        """
        for _ in range(self._max_poll_attempts):
            time.sleep(self._poll_interval_s)
            task = self.get_task(task_id)
            status = task.status.lower()

            if status in ("completed", "success"):
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

    def list_enrichments(self, q: Optional[str] = None) -> List[EnrichmentSummary]:
        """List all available enrichments, optionally filtered by search query."""
        params = {"q": q} if q else None
        data = self._request("GET", "/enrichments/", params=params)
        return [EnrichmentSummary.model_validate(e) for e in data]

    def get_enrichment(self, enrichment_id: int) -> Enrichment:
        """Get full details for a specific enrichment including params and response fields."""
        data = self._request("GET", f"/enrichments/{enrichment_id}")
        return Enrichment.model_validate(data)

    def run_enrichment(self, enrichment_id: int, params: Dict[str, Any]) -> RunResponse:
        """Submit an enrichment run. Returns a task — use poll_task() or run_enrichment_sync()."""
        data = self._request("POST", f"/enrichments/{enrichment_id}/run", json={"params": params})
        return RunResponse.model_validate(data)

    def run_enrichment_bulk(
        self, enrichment_id: int, params: List[Dict[str, Any]]
    ) -> RunResponse:
        """Submit a bulk enrichment run for multiple inputs."""
        data = self._request("POST", f"/enrichments/{enrichment_id}/bulk-run", json={"params": params})
        return RunResponse.model_validate(data)

    def run_enrichment_sync(
        self, enrichment_id: int, params: Dict[str, Any]
    ) -> Any:
        """Submit and poll an enrichment, returning final data when complete."""
        task = self.run_enrichment(enrichment_id, params)
        return self.poll_task(task.task_id)

    def run_enrichment_bulk_sync(
        self, enrichment_id: int, params: List[Dict[str, Any]]
    ) -> Any:
        """Submit and poll a bulk enrichment, returning final data when complete."""
        task = self.run_enrichment_bulk(enrichment_id, params)
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
        """Submit a bulk waterfall run for multiple inputs."""
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
        """Submit and poll a bulk waterfall, returning final data when complete."""
        task = self.run_waterfall_bulk(identifier, params, enrichments, email_verifier)
        return self.poll_task(task.task_id)

    # -----------------------------------------------------------------------
    # Tables
    # -----------------------------------------------------------------------

    def create_table(
        self,
        name: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> Table:
        """
        Create a new empty table.

        name defaults to 'New empty table'.
        columns pre-defines column names; defaults to column1/column2/column3.
        """
        payload: Dict[str, Any] = {}
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

    def get_columns(self, table_uuid: str) -> List[Column]:
        """Get all columns defined on a table."""
        data = self._request("GET", f"/table/{table_uuid}/columns")
        return [Column.model_validate(c) for c in data]

    def get_table_enrichments(self, table_uuid: str) -> List[TableEnrichment]:
        """List enrichments configured on a table."""
        data = self._request("GET", f"/table/{table_uuid}/enrichments")
        return [TableEnrichment.model_validate(e) for e in data]

    def add_enrichment(
        self,
        table_uuid: str,
        enrichment_id: int,
        mapping: Dict[str, Any],
    ) -> TableEnrichment:
        """
        Add an enrichment to a table with a parameter-to-column mapping.

        ``mapping`` keys are enrichment parameter names. Values are dicts with:
          - ``{"type": "mapping", "value": "<column-name-or-uuid>"}``
            — reads the value from a table column per row.
            You may pass a human-readable column name; the SDK will automatically
            resolve it to the required column UUID via GET /table/{uuid}/columns.
          - ``{"type": "simple", "value": "<static-value>"}``
            — uses the same hardcoded value for every row.

        Returns the newly added :class:`TableEnrichment` (with ``id`` and ``name``),
        resolved by diffing enrichments before and after the add.
        """
        # Auto-resolve column names → UUIDs for mapping-type entries
        resolved_mapping: Dict[str, Any] = {}
        column_map: Optional[Dict[str, str]] = None  # name → uuid, built lazily

        for param, entry in mapping.items():
            if not isinstance(entry, dict) or entry.get("type") != "mapping":
                resolved_mapping[param] = entry
                continue

            value = entry.get("value", "")
            # Looks like a UUID already — 8-4-4-4-12 hex pattern
            if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", str(value), re.IGNORECASE):
                resolved_mapping[param] = entry
                continue

            # Build the column name→uuid map once
            if column_map is None:
                columns = self.get_columns(table_uuid)
                column_map = {c.name: c.identifier for c in columns}

            uuid = column_map.get(value)
            if uuid is None:
                # Not a known column name — pass through and let the API surface the error
                resolved_mapping[param] = entry
            else:
                resolved_mapping[param] = {**entry, "value": uuid}

        # Snapshot existing enrichment IDs so we can detect the new one
        before_ids = {e.id for e in self.get_table_enrichments(table_uuid)}

        payload = {"enrichment": enrichment_id, "mapping": resolved_mapping}
        self._request("POST", f"/table/{table_uuid}/add-enrichment", json=payload)

        # Fetch updated list and return the newly created TableEnrichment
        after = self.get_table_enrichments(table_uuid)
        new_enrichments = [e for e in after if e.id not in before_ids]
        if new_enrichments:
            return new_enrichments[-1]

        # Fallback: return the last enrichment in the list if we can't detect which is new
        if after:
            return after[-1]

        raise DatabarError("Enrichment was added but could not be retrieved. Use get_table_enrichments() to fetch it manually.")

    def run_table_enrichment(
        self,
        table_uuid: str,
        enrichment_id: str,
        run_strategy: Optional[str] = None,
    ) -> Any:
        """Trigger an enrichment to run on all rows in a table."""
        params = {"run_strategy": run_strategy} if run_strategy else None
        return self._request(
            "POST",
            f"/table/{table_uuid}/run-enrichment/{enrichment_id}",
            params=params,
        )

    # -----------------------------------------------------------------------
    # Rows
    # -----------------------------------------------------------------------

    def get_rows(
        self,
        table_uuid: str,
        page: int = 1,
        per_page: int = 100,
    ) -> Dict[str, Any]:
        """
        Get rows from a table with pagination.

        Returns a dict with keys: ``data`` (list of row dicts), ``has_next_page``,
        ``total_count``, ``page``.  Each row dict is keyed by column name.

        ``per_page`` max is 500 (API limit). Default is 100.
        """
        return self._request(
            "GET",
            f"/table/{table_uuid}/rows",
            params={"page": page, "per_page": per_page},
        )

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
