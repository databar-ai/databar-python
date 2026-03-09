"""Embedded agent guide — printed by `databar agent-guide`."""

AGENT_GUIDE = r"""# Databar SDK & CLI — Agent Guide

Official Databar Python SDK and CLI (`pip install databar`).
Run data enrichments, waterfall lookups, and manage tables via api.databar.ai/v1.

## Setup

```bash
pip install databar
export DATABAR_API_KEY=YOUR_API_KEY   # or: databar login --api-key YOUR_API_KEY
databar whoami                        # verify auth
```

If `databar` command not found after install:
```bash
export PATH="$(python3 -m site --user-base)/bin:$PATH"
```

## CLI Quick Reference

All commands support `--format table|json|csv` (default: table) and `--help`.
**For machine-parseable output, always use `--format json`.**

### Enrichments
```
databar enrich list                          # list all enrichments
databar enrich list --query "linkedin"       # search enrichments
databar enrich get <id>                      # get enrichment details (params, response fields)
databar enrich choices <id> <param>          # list choices for a select param
databar enrich run <id> --params '{"key": "value"}'   # run single
databar enrich bulk <id> --input data.csv --out results.csv
```

### Waterfalls
```
databar waterfall list
databar waterfall get <identifier>           # e.g. email_getter
databar waterfall run <identifier> --params '{"key": "value"}'
databar waterfall bulk <identifier> --input data.csv --out results.csv
```

### Tables
```
databar table list
databar table create --name "My Table" --columns "email,name,company"
databar table columns <table-uuid>
databar table rows <table-uuid>
databar table rows <table-uuid> --format json

databar table insert <table-uuid> --data '[{"email":"a@b.com","name":"Alice"}]'
databar table insert <table-uuid> --input data.csv --allow-new-columns

databar table enrichments <table-uuid>
databar table add-enrichment <table-uuid> --enrichment-id <id> --mapping '{"param": "column_name"}'
databar table run-enrichment <table-uuid> --enrichment-id <TABLE-ENRICHMENT-ID>
```

Note: `run-enrichment` uses the TABLE-ENRICHMENT ID (from `add-enrichment` or `table enrichments`), NOT the catalog enrichment ID.

### Tasks
```
databar task get <task-id>                   # check status once
databar task get <task-id> --poll            # poll until complete
```

### Account
```
databar whoami
databar whoami --format json
```

## Python SDK Quick Reference

```python
from databar import DatabarClient

client = DatabarClient()  # reads DATABAR_API_KEY from env

# Enrichments
enrichments = client.list_enrichments(q="linkedin")
enrichment = client.get_enrichment(123)
# enrichment.params → list of EnrichmentParam (fields: .name, .is_required, .description)
# enrichment.response_fields → list of EnrichmentResponseField (fields: .name, .type_field)

result = client.run_enrichment_sync(123, {"email": "alice@example.com"})

# Waterfalls
waterfalls = client.list_waterfalls()
# waterfall.identifier → slug like "email_getter" (also available as .slug)
result = client.run_waterfall_sync("email_getter", {"linkedin_url": "..."})

# Tables
tables = client.list_tables()
# table.identifier → UUID (also available as .id and .uuid)
table = client.create_table(name="Leads", columns=["email", "name"])
resp = client.get_rows(table.identifier)
# resp.data → list of row dicts, resp.has_next_page, resp.total_count, resp.page

from databar import InsertRow
client.create_rows(table.identifier, [
    InsertRow(fields={"email": "alice@example.com", "name": "Alice"}),
])
```

## Key Concepts

- All enrichment/waterfall runs are async: submit → get task_id → poll until completed.
  The `*_sync` methods handle this automatically.
- task_id is the universal identifier for polling. Use it with poll_task() or `databar task get`.
- Results expire after 1 hour (status becomes "gone").
- Table enrichments are a two-step process: add_enrichment() then run_table_enrichment().
  The ID from add_enrichment is a TABLE-ENRICHMENT ID, different from the catalog enrichment ID.
- The SDK auto-resolves column names to UUIDs in add_enrichment().

## Model Field Aliases

Common aliases that work on all models:
- Table: .id, .uuid → .identifier
- Waterfall: .slug → .identifier
- EnrichmentParam: .slug → .name, .label → .description, .required → .is_required
- EnrichmentResponseField: .slug → .name, .label → .name

## Error Handling

```python
from databar import (
    DatabarAuthError,                  # 401/403
    DatabarInsufficientCreditsError,   # 406
    DatabarNotFoundError,              # 404
    DatabarTaskFailedError,            # task completed with error
    DatabarTimeoutError,               # polling timed out
    DatabarGoneError,                  # task data expired (>1 hour)
)
```
"""
