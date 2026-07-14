"""
Pydantic v2 models for the Databar API.

All shapes are sourced from the user_api OpenAPI definition (user_api/app/api/v1/).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ===========================================================================
# Pricing / Category (shared by Enrichment and Exporter)
# ===========================================================================


class PricingInfo(BaseModel):
    """Describes how an enrichment is priced per request."""

    type: str = Field(
        description='"fixed" (flat per-request) or "per_parameter" (price × param value).'
    )
    parameter: Optional[str] = Field(
        default=None,
        description="Parameter name that multiplies the base price. Only present when type is per_parameter.",
    )


class CategoryInfo(BaseModel):
    """A category tag attached to an enrichment."""

    id: int
    name: str


# ===========================================================================
# User
# ===========================================================================


class User(BaseModel):
    """Authenticated user profile.

    Fields: first_name, email, balance, plan, workspace.
    """

    first_name: Optional[str] = None
    email: str
    balance: float
    plan: str
    workspace: Optional[str] = None


# ===========================================================================
# Enrichments
# ===========================================================================


class ChoiceItem(BaseModel):
    """A single selectable option for a select/mselect enrichment parameter."""

    id: str = Field(description="Value to pass in the API param.")
    name: str = Field(description="Human-readable label for display.")


class Choices(BaseModel):
    """Describes how choices for a param are delivered."""

    mode: Literal["inline", "remote"] = Field(
        description="inline — options embedded here; remote — fetch from choices endpoint."
    )
    items: Optional[List[ChoiceItem]] = Field(
        default=None,
        description="Available choices (only present when mode is inline).",
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="URL path to fetch choices from (only present when mode is remote).",
    )


class EnrichmentParam(BaseModel):
    """A parameter required or accepted by an enrichment.

    Fields: name, is_required, type_field, description, choices.

    Property aliases: .slug → .name, .label → .description, .required → .is_required.
    """

    name: str = Field(description="Parameter slug used as the key in the params dict.")
    is_required: bool = Field(description="Whether this parameter is required.")
    type_field: str = Field(
        description="Input type. Common values: text, select, mselect, datetime."
    )
    description: str = Field(description="Human-readable label / description.")
    choices: Optional[Choices] = None

    @property
    def slug(self) -> str:
        """Alias for name."""
        return self.name

    @property
    def label(self) -> str:
        """Alias for description."""
        return self.description

    @property
    def required(self) -> bool:
        """Alias for is_required."""
        return self.is_required


class EnrichmentResponseField(BaseModel):
    """A field returned in the enrichment result data.

    Fields: name, display_name, type_field.

    Property aliases: .slug → .name, .label → .name.
    """

    name: str = Field(description="Field name as it appears in the result data.")
    display_name: Optional[str] = Field(
        default=None,
        description="Human-readable display name for this field.",
    )
    type_field: str = Field(description="Data type of this field.")

    @property
    def slug(self) -> str:
        """Alias for name."""
        return self.name

    @property
    def label(self) -> str:
        """Alias for name."""
        return self.name


class PaginationInfo(BaseModel):
    """Pagination metadata for a list-style enrichment."""

    supported: bool = Field(description="Whether this enrichment supports pagination.")
    per_page: Optional[int] = Field(
        default=None,
        description="Default rows per page (only present when supported is True).",
    )


class EnrichmentSummary(BaseModel):
    """Enrichment as returned by the list endpoint (no params/response_fields).

    Fields: id, name, description, data_source, price, auth_method, pricing, category.
    """

    id: int
    name: str
    description: str
    data_source: str
    price: float
    auth_method: str
    pricing: Optional[PricingInfo] = None
    category: List[CategoryInfo] = Field(default_factory=list)


class Enrichment(EnrichmentSummary):
    """Full enrichment detail including params, response fields and pagination info.

    Fields: id, name, description, data_source, price, auth_method, pricing, category,
    params, response_fields, pagination.

    Usage::

        enrichment = client.get_enrichment(123)
        for p in enrichment.params:
            print(p.name, p.is_required, p.description)
    """

    params: Optional[List[EnrichmentParam]] = None
    response_fields: Optional[List[EnrichmentResponseField]] = None
    pagination: Optional[PaginationInfo] = None


class EnrichmentListResponse(BaseModel):
    """Paginated response returned by list_enrichments(page=N).

    Fields: items, page, limit, has_next_page, total_count.

    Usage::

        resp = client.list_enrichments(page=1, limit=50)
        for e in resp.items:
            print(e.id, e.name)
        if resp.has_next_page:
            resp2 = client.list_enrichments(page=2, limit=50)
    """

    items: List[EnrichmentSummary]
    page: int
    limit: int
    has_next_page: bool
    total_count: int


class ChoicesResponse(BaseModel):
    """Paginated response for enrichment parameter choices."""

    items: List[ChoiceItem]
    page: int
    limit: int
    has_next_page: bool
    total_count: int = 0


class PaginationOptions(BaseModel):
    """Pagination options for run / bulk-run requests on list-style enrichments."""

    pages: int = Field(default=1, ge=1, le=100, description="Number of pages to fetch.")


# ===========================================================================
# Tasks
# ===========================================================================


class TaskStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    GONE = "gone"
    NO_DATA = "no_data"


class RunResponse(BaseModel):
    """Returned by all /run and /bulk-run endpoints. Contains the task_id to poll."""

    task_id: str = Field(description="Unique identifier of the submitted task.")
    status: str = Field(default="processing")


class TaskResponse(BaseModel):
    """Returned by GET /v1/tasks/{task_id}.

    The backend also populates `request_id` (deprecated alias) so both names are accepted.
    Statuses: processing, no_data, completed, partially_completed, failed, gone.

    Task data is stored for **24 hours**. After that status becomes 'gone'.
    """

    task_id: str = Field(description="Unique identifier of the task.")
    request_id: Optional[str] = Field(
        default=None,
        description="Deprecated alias for task_id. Same value.",
    )
    status: str = Field(
        description="Current status: processing, completed, partially_completed, failed, or gone."
    )
    data: Optional[Union[List[Any], Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Resulting data once completed. For bulk runs this is a list aligned to "
            "the inputs: one element per input in input order, with null for inputs "
            "that returned no data (len(data) == number of inputs). A single run "
            "returns the bare result object."
        ),
    )
    error: Optional[Union[str, List[str]]] = None
    credits_spent: float = 0

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "TaskResponse":
        if isinstance(obj, dict) and "task_id" not in obj and "request_id" in obj:
            obj = {**obj, "task_id": obj["request_id"]}
        return super().model_validate(obj, **kwargs)


# ===========================================================================
# Waterfalls
# ===========================================================================


class WaterfallEnrichment(BaseModel):
    id: int
    name: str
    description: str
    price: Union[str, float]
    params: List[str]


class Waterfall(BaseModel):
    """A waterfall enrichment that tries multiple providers in sequence.

    Fields: identifier, name, description, input_params, output_fields,
    available_enrichments, is_email_verifying, email_verifiers.

    Property aliases: .slug → .identifier.

    Usage::

        wf = client.get_waterfall("email_getter")
        result = client.run_waterfall_sync(wf.identifier, {...})
    """

    identifier: str = Field(description="Slug-style identifier, e.g. 'email_getter'. Use this when calling run_waterfall().")
    name: str
    description: str
    input_params: List[Dict[str, Any]]
    output_fields: List[Dict[str, Any]]
    available_enrichments: List[WaterfallEnrichment]
    is_email_verifying: bool
    email_verifiers: List[Any]

    @property
    def slug(self) -> str:
        """Alias for identifier."""
        return self.identifier


# ===========================================================================
# Flows
# ===========================================================================


class FlowInput(BaseModel):
    """A declared input of a flow.

    Fields: id, description, type, required.

    The ``id`` is the key to use in the inputs dict passed to run_flow().
    """

    id: str = Field(description="Input id — the key to use in the run_flow() inputs dict.")
    description: str
    type: str
    required: bool


class FlowOutput(BaseModel):
    """A field produced by a flow node.

    Fields: id, response_field_id.
    """

    id: str
    response_field_id: Optional[int] = None


class Flow(BaseModel):
    """A saved workspace flow (multi-step enrichment pipeline).

    Fields: id, name, description, inputs, outputs, created_at, updated_at.

    Property aliases: .identifier → .id.

    Usage::

        flow = client.get_flow("flow-uuid")
        result = client.run_flow_sync(flow.id, {"email": "alice@example.com"})
    """

    id: str = Field(description="Flow UUID. Use this when calling get_flow()/run_flow().")
    name: str
    description: str
    inputs: List[FlowInput] = Field(default_factory=list)
    outputs: List[FlowOutput] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def identifier(self) -> str:
        """Alias for id."""
        return self.id


# ===========================================================================
# Tables
# ===========================================================================


class Table(BaseModel):
    """A Databar table.

    Fields: identifier, name, created_at, updated_at, workspace_identifier, table_url.

    Property aliases: .id → .identifier, .uuid → .identifier.

    Usage::

        table = client.create_table(name="Leads", columns=["email", "name"])
        rows = client.get_rows(table.identifier)
    """

    identifier: str = Field(description="Table UUID. Use this in all table operations.")
    name: str
    created_at: str
    updated_at: str
    workspace_identifier: Optional[str] = None
    table_url: Optional[str] = None

    @property
    def id(self) -> str:
        """Alias for identifier."""
        return self.identifier

    @property
    def uuid(self) -> str:
        """Alias for identifier."""
        return self.identifier


class Column(BaseModel):
    """A column defined on a table.

    Fields: identifier, internal_name, additional_intenal_name, name, type_of_value, data_processor_id.

    Note: 'additional_intenal_name' preserves the upstream typo for wire compatibility.
    """

    identifier: str = Field(description="Column UUID.")
    internal_name: str
    additional_intenal_name: Optional[str] = None
    name: str = Field(description="Human-readable column name.")
    type_of_value: str
    data_processor_id: Optional[int] = None


class CreateColumnResponse(BaseModel):
    """Response from creating or renaming a column."""

    identifier: str
    name: str
    type_of_value: str


class TableEnrichment(BaseModel):
    """An enrichment configured on a table (from get_table_enrichments).

    Fields: id, name.

    The id is the TABLE-ENRICHMENT id — use it with run_table_enrichment(),
    not the enrichment catalog id.
    """

    id: int
    name: str


class AddEnrichmentResponse(BaseModel):
    """Response from adding an enrichment to a table (add_enrichment).

    Fields: id, enrichment_name.

    Note: id here is the table-enrichment id, not the enrichment catalog id.
    Use it with run_table_enrichment().
    """

    id: int
    enrichment_name: str


class AddWaterfallResponse(BaseModel):
    """Response from adding a waterfall to a table (add_waterfall).

    Fields: id, waterfall_name.
    """

    id: int
    waterfall_name: str


class InstalledWaterfall(BaseModel):
    """A waterfall installed on a table.

    Fields: id, waterfall_name.
    """

    id: int
    waterfall_name: str


class AddExporterResponse(BaseModel):
    """Response from adding an exporter to a table (add_exporter).

    Fields: id, exporter_name.
    """

    id: int
    exporter_name: str


class InstalledExporter(BaseModel):
    """An exporter installed on a table.

    Fields: id, name.
    """

    id: int
    name: str


class RunEnrichmentResponse(BaseModel):
    """Response from triggering a table enrichment or waterfall run.

    Fields: status, processing_rows.
    """

    status: str
    processing_rows: Optional[int] = None


# ===========================================================================
# Rows — Query
# ===========================================================================


class RowsResponse(BaseModel):
    """Paginated rows returned by get_rows().

    Fields: data, has_next_page, total_count, page.

    Property alias: .rows → .data.

    Usage::

        resp = client.get_rows(table.identifier)
        for row in resp.data:
            print(row["email"])
        if resp.has_next_page:
            resp2 = client.get_rows(table.identifier, page=2)
    """

    data: List[Dict[str, Any]] = Field(description="List of row dicts keyed by column name. Each row also has an 'id' key with the row UUID.")
    has_next_page: bool = Field(default=False)
    total_count: int = Field(default=0)
    page: int = Field(default=1)

    @property
    def rows(self) -> List[Dict[str, Any]]:
        """Alias for data."""
        return self.data


# ===========================================================================
# Rows — Insert
# ===========================================================================


class InsertRow(BaseModel):
    fields: Dict[str, Any] = Field(
        description="Column values keyed by human-readable column name."
    )


class DedupeOptions(BaseModel):
    enabled: bool = False
    keys: List[str] = Field(default_factory=list)


class InsertOptions(BaseModel):
    allow_new_columns: bool = Field(
        default=False,
        description="Auto-create unknown column names as text columns.",
    )
    dedupe: Optional[DedupeOptions] = None


class BatchInsertResultItem(BaseModel):
    index: int = Field(description="Original index in the request array.")
    id: Optional[str] = Field(default=None, description="UUID of the created row.")
    action: Literal["created", "skipped_duplicate"]
    row_data: Optional[Dict[str, Any]] = None


class BatchInsertResponse(BaseModel):
    results: List[BatchInsertResultItem]


# ===========================================================================
# Rows — Patch (update)
# ===========================================================================


class BatchUpdateRow(BaseModel):
    id: str = Field(description="UUID of the row to update.")
    fields: Dict[str, Any] = Field(
        description="Column values to set, keyed by human-readable column name."
    )


class BatchUpdateResultItem(BaseModel):
    id: str
    ok: bool
    error: Optional[Dict[str, Any]] = None
    row_data: Optional[Dict[str, Any]] = None


class BatchUpdateResponse(BaseModel):
    results: List[BatchUpdateResultItem]


# ===========================================================================
# Rows — Upsert
# ===========================================================================


class UpsertRow(BaseModel):
    key: Dict[str, Any] = Field(
        description="Exactly one column to match on: {column_name: value}.",
    )
    fields: Dict[str, Any] = Field(
        description="Column values to set/update, keyed by human-readable column name."
    )


class UpsertResultItem(BaseModel):
    index: Optional[int] = None
    id: Optional[str] = None
    action: Optional[Literal["created", "updated"]] = None
    ok: bool = True
    error: Optional[Dict[str, Any]] = None
    row_data: Optional[Dict[str, Any]] = None


class UpsertResponse(BaseModel):
    results: List[UpsertResultItem]


# ===========================================================================
# Exporters
# ===========================================================================


class Exporter(BaseModel):
    """An exporter (CRM/destination integration) as returned by the list endpoint.

    Fields: id, name, description, dataset.

    Usage::

        exporters = client.list_exporters()
        detail = client.get_exporter(exporters[0].id)
    """

    id: int
    name: str
    description: str
    dataset: int


class ExporterListResponse(BaseModel):
    """Paginated response returned by list_exporters(page=N).

    Fields: items, page, limit, has_next_page, total_count.
    """

    items: List[Exporter]
    page: int
    limit: int
    has_next_page: bool
    total_count: int


class ExporterParam(BaseModel):
    """A parameter for an exporter.

    Fields: name, is_required, type_field, description, choices.
    """

    name: str
    is_required: bool
    type_field: str
    description: str
    choices: Optional[Choices] = None


class ExporterResponseField(BaseModel):
    """A field in the exporter result."""

    name: str
    display_name: Optional[str] = None
    type_field: str


class Connection(BaseModel):
    """A stored API key or OAuth connection for an exporter."""

    id: int
    name: str
    type: str


class AuthorizationInfo(BaseModel):
    """Authorization requirements and available connections for an exporter."""

    required: bool
    connections: List[Connection] = Field(default_factory=list)


class ExporterDetail(Exporter):
    """Full exporter detail including params, response fields and authorization info.

    Fields: id, name, description, dataset, params, response_fields, authorization.
    """

    params: List[ExporterParam] = Field(default_factory=list)
    response_fields: List[ExporterResponseField] = Field(default_factory=list)
    authorization: AuthorizationInfo


# ===========================================================================
# Connectors
# ===========================================================================


class NameValue(BaseModel):
    """A name/value pair used in connector headers, parameters, and body fields."""

    name: str
    value: str = ""


class Connector(BaseModel):
    """A custom HTTP API connector registered in the workspace.

    Fields: id, name, type, method, url, headers, parameters, body,
    body_template, rate_limit, max_concurrency, created_at.

    Usage::

        connector = client.create_connector(
            name="My Scoring API",
            method="post",
            url="https://api.example.com/v1/score",
            headers=[{"name": "Authorization", "value": "Bearer sk-xxx"}],
            body=[{"name": "domain", "value": ""}],
        )
    """

    id: int
    name: str
    type: str = "enrichment"
    method: str
    url: str
    headers: List[NameValue] = Field(default_factory=list)
    parameters: List[NameValue] = Field(default_factory=list)
    body: List[NameValue] = Field(default_factory=list)
    body_template: Optional[str] = None
    rate_limit: Optional[int] = None
    max_concurrency: Optional[int] = None
    created_at: Optional[str] = None


# ===========================================================================
# Folders
# ===========================================================================


class Folder(BaseModel):
    """A folder for organizing tables in the workspace.

    Fields: id, name, created_at, updated_at, table_count.

    Usage::

        folder = client.create_folder("Leads")
        client.move_table_to_folder(table.identifier, folder.id)
    """

    id: int
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    table_count: Optional[int] = None
