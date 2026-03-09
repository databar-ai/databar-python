"""
Pydantic v2 models for the Databar API.

All shapes are sourced directly from api-docs/api-reference/openapi.json.
Where the TypeScript MCP client uses custom normalizations, these models
match the actual API response, not the MCP adaptation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ===========================================================================
# User
# ===========================================================================


class User(BaseModel):
    """Authenticated user profile.

    Fields: first_name, email, balance, plan.
    """

    first_name: Optional[str] = None
    email: str
    balance: float
    plan: str


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

    Fields: name, type_field.

    Property aliases: .slug → .name, .label → .name.
    """

    name: str = Field(description="Field name as it appears in the result data.")
    type_field: str = Field(description="Data type of this field.")

    @property
    def slug(self) -> str:
        """Alias for name."""
        return self.name

    @property
    def label(self) -> str:
        """Alias for name."""
        return self.name


class EnrichmentSummary(BaseModel):
    """Enrichment as returned by the list endpoint (no params/response_fields).

    Fields: id, name, description, data_source, price, auth_method.
    """

    id: int
    name: str
    description: str
    data_source: str
    price: float
    auth_method: str


class Enrichment(EnrichmentSummary):
    """Full enrichment detail including params and response fields.

    Fields: id, name, description, data_source, price, auth_method, params, response_fields.

    Usage::

        enrichment = client.get_enrichment(123)
        for p in enrichment.params:
            print(p.name, p.is_required, p.description)
    """

    params: Optional[List[EnrichmentParam]] = None
    response_fields: Optional[List[EnrichmentResponseField]] = None


class ChoicesResponse(BaseModel):
    """Paginated response for enrichment parameter choices."""

    items: List[ChoiceItem]
    page: int
    limit: int
    has_next_page: bool


# ===========================================================================
# Tasks
# ===========================================================================


class TaskStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    GONE = "gone"


class RunResponse(BaseModel):
    """Returned by all /run and /bulk-run endpoints. Contains the task_id to poll."""

    task_id: str = Field(description="Unique identifier of the submitted task.")
    status: str = Field(default="processing")


class TaskResponse(BaseModel):
    """Returned by GET /v1/tasks/{task_id}.

    The backend currently uses 'request_id' as the field name; this model
    accepts both 'task_id' and 'request_id' so it works before and after
    the backend renames the field.
    """

    task_id: str = Field(
        description="Unique identifier of the task.",
    )
    status: str = Field(
        description="Current status: processing, completed, failed, or gone."
    )
    data: Optional[Union[List[Any], Dict[str, Any]]] = Field(
        default=None,
        description="Resulting data once completed.",
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
# Tables
# ===========================================================================


class Table(BaseModel):
    """A Databar table.

    Fields: identifier, name, created_at, updated_at.

    Property aliases: .id → .identifier, .uuid → .identifier.

    Usage::

        table = client.create_table(name="Leads", columns=["email", "name"])
        rows = client.get_rows(table.identifier)
    """

    identifier: str = Field(description="Table UUID. Use this in all table operations.")
    name: str
    created_at: str
    updated_at: str

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

    Fields: identifier, internal_name, name, type_of_value, data_processor_id.
    """

    identifier: str = Field(description="Column UUID.")
    internal_name: str
    name: str = Field(description="Human-readable column name.")
    type_of_value: str
    data_processor_id: Optional[int] = None


class TableEnrichment(BaseModel):
    """An enrichment configured on a table.

    Fields: id, name.

    The id here is the TABLE-ENRICHMENT id — use it with run_table_enrichment(),
    not the enrichment catalog id.
    """

    id: int
    name: str


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
