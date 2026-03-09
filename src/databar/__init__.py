"""
Databar Python SDK — official client for api.databar.ai

Quick start::

    from databar import DatabarClient

    client = DatabarClient(api_key="your-key")  # or set DATABAR_API_KEY env var

    # List enrichments
    enrichments = client.list_enrichments(q="linkedin")

    # Run a single enrichment (submit + poll)
    result = client.run_enrichment_sync(123, {"email": "alice@example.com"})

    # Work with tables
    tables = client.list_tables()
    rows = client.get_rows(tables[0].identifier)
"""

from .client import DatabarClient
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
    ChoiceItem,
    Choices,
    ChoicesResponse,
    Column,
    DedupeOptions,
    Enrichment,
    EnrichmentParam,
    EnrichmentResponseField,
    EnrichmentSummary,
    InsertOptions,
    InsertRow,
    RowsResponse,
    RunResponse,
    Table,
    TableEnrichment,
    TaskResponse,
    TaskStatus,
    UpsertResponse,
    UpsertRow,
    User,
    Waterfall,
    WaterfallEnrichment,
)

__version__ = "2.0.7"
__all__ = [
    "DatabarClient",
    # exceptions
    "DatabarError",
    "DatabarAuthError",
    "DatabarNotFoundError",
    "DatabarInsufficientCreditsError",
    "DatabarGoneError",
    "DatabarValidationError",
    "DatabarRateLimitError",
    "DatabarTaskFailedError",
    "DatabarTimeoutError",
    # models
    "User",
    "Enrichment",
    "EnrichmentSummary",
    "EnrichmentParam",
    "EnrichmentResponseField",
    "ChoiceItem",
    "Choices",
    "ChoicesResponse",
    "RunResponse",
    "TaskResponse",
    "TaskStatus",
    "Waterfall",
    "WaterfallEnrichment",
    "Table",
    "Column",
    "TableEnrichment",
    "RowsResponse",
    "InsertRow",
    "InsertOptions",
    "DedupeOptions",
    "BatchInsertResponse",
    "BatchUpdateRow",
    "BatchUpdateResponse",
    "UpsertRow",
    "UpsertResponse",
]
