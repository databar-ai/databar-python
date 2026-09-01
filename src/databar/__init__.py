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

    # Manage exporters, connectors and folders
    exporters = client.list_exporters()
    folder = client.create_folder("My Leads")
    client.move_table_to_folder(tables[0].identifier, folder.id)
"""

from .client import DatabarClient
from .exceptions import (
    DatabarAuthError,
    DatabarError,
    DatabarConflictError,
    DatabarGoneError,
    DatabarInsufficientCreditsError,
    DatabarNotFoundError,
    DatabarRateLimitError,
    DatabarTaskCancelledError,
    DatabarTaskFailedError,
    DatabarTimeoutError,
    DatabarValidationError,
)
from .models import (
    # Pricing / Category
    PricingInfo,
    CategoryInfo,
    # User
    User,
    # Enrichments
    ChoiceItem,
    Choices,
    EnrichmentParam,
    EnrichmentResponseField,
    PaginationInfo,
    PaginationOptions,
    EnrichmentSummary,
    Enrichment,
    EnrichmentListResponse,
    ChoicesResponse,
    # Tasks
    RunResponse,
    TaskResponse,
    TaskStatus,
    # Waterfalls
    Waterfall,
    WaterfallEnrichment,
    # Flows
    Flow,
    FlowConfigOpsResult,
    FlowDetail,
    FlowInput,
    FlowOutput,
    FlowVersion,
    FlowVersionDetail,
    RestoreFlowVersionResult,
    # Tables
    Table,
    Column,
    CreateColumnResponse,
    TableEnrichment,
    AddEnrichmentResponse,
    AddWaterfallResponse,
    InstalledWaterfall,
    AddExporterResponse,
    InstalledExporter,
    RunEnrichmentResponse,
    # Rows
    RowsResponse,
    InsertRow,
    InsertOptions,
    DedupeOptions,
    BatchInsertResponse,
    BatchUpdateRow,
    BatchUpdateResponse,
    UpsertRow,
    UpsertResponse,
    # Exporters
    Exporter,
    ExporterListResponse,
    ExporterParam,
    ExporterAdditionalParam,
    ExporterResponseField,
    Connection,
    AuthorizationInfo,
    ExporterDetail,
    # Connectors
    NameValue,
    Connector,
    # Folders
    Folder,
)

__version__ = "2.4.0"
__all__ = [
    "DatabarClient",
    # exceptions
    "DatabarError",
    "DatabarAuthError",
    "DatabarNotFoundError",
    "DatabarInsufficientCreditsError",
    "DatabarConflictError",
    "DatabarGoneError",
    "DatabarValidationError",
    "DatabarRateLimitError",
    "DatabarTaskCancelledError",
    "DatabarTaskFailedError",
    "DatabarTimeoutError",
    # pricing / category
    "PricingInfo",
    "CategoryInfo",
    # user
    "User",
    # enrichments
    "EnrichmentSummary",
    "Enrichment",
    "EnrichmentListResponse",
    "EnrichmentParam",
    "EnrichmentResponseField",
    "PaginationInfo",
    "PaginationOptions",
    "ChoiceItem",
    "Choices",
    "ChoicesResponse",
    # tasks
    "RunResponse",
    "TaskResponse",
    "TaskStatus",
    # waterfalls
    "Waterfall",
    "WaterfallEnrichment",
    # flows
    "Flow",
    "FlowConfigOpsResult",
    "FlowDetail",
    "FlowInput",
    "FlowOutput",
    "FlowVersion",
    "FlowVersionDetail",
    "RestoreFlowVersionResult",
    # tables
    "Table",
    "Column",
    "CreateColumnResponse",
    "TableEnrichment",
    "AddEnrichmentResponse",
    "AddWaterfallResponse",
    "InstalledWaterfall",
    "AddExporterResponse",
    "InstalledExporter",
    "RunEnrichmentResponse",
    # rows
    "RowsResponse",
    "InsertRow",
    "InsertOptions",
    "DedupeOptions",
    "BatchInsertResponse",
    "BatchUpdateRow",
    "BatchUpdateResponse",
    "UpsertRow",
    "UpsertResponse",
    # exporters
    "Exporter",
    "ExporterListResponse",
    "ExporterParam",
    "ExporterAdditionalParam",
    "ExporterResponseField",
    "Connection",
    "AuthorizationInfo",
    "ExporterDetail",
    # connectors
    "NameValue",
    "Connector",
    # folders
    "Folder",
]
