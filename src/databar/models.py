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
    name: str
    is_required: bool
    type_field: str = Field(
        description="Input type. Common values: text, select, mselect, datetime."
    )
    description: str
    choices: Optional[Choices] = None


class EnrichmentResponseField(BaseModel):
    name: str
    type_field: str


class EnrichmentSummary(BaseModel):
    """Enrichment as returned by the list endpoint (no params/response_fields)."""

    id: int
    name: str
    description: str
    data_source: str
    price: float
    auth_method: str


class Enrichment(EnrichmentSummary):
    """Full enrichment detail including params and response fields."""

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
    identifier: str
    name: str
    description: str
    input_params: List[Dict[str, Any]]
    output_fields: List[Dict[str, Any]]
    available_enrichments: List[WaterfallEnrichment]
    is_email_verifying: bool
    email_verifiers: List[Any]


# ===========================================================================
# Tables
# ===========================================================================


class Table(BaseModel):
    identifier: str
    name: str
    created_at: str
    updated_at: str


class Column(BaseModel):
    identifier: str
    internal_name: str
    name: str
    type_of_value: str
    data_processor_id: Optional[int] = None


class TableEnrichment(BaseModel):
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
