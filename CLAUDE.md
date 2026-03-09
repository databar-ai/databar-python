# Databar SDK & CLI — Claude Code Guide

This repo contains the official Databar Python SDK and CLI (`pip install databar`).
Use it to run data enrichments, waterfall lookups, and manage tables via `api.databar.ai/v1`.

---

## Setup

### Install

```bash
pip install databar
```

### Fix PATH (if `databar` command not found)

```bash
export PATH="$(python3 -m site --user-base)/bin:$PATH"
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent.

### Authenticate

**Non-interactive (preferred for agents):**

```bash
databar login --api-key YOUR_API_KEY
```

**Or set the environment variable:**

```bash
export DATABAR_API_KEY=YOUR_API_KEY
```

**Verify it works:**

```bash
databar whoami
```

---

## CLI Quick Reference

All commands support `--format table|json|csv` (default: `table`) and `--help`.

### Enrichments

```bash
databar enrich list                          # list all enrichments
databar enrich list --query "linkedin"       # search enrichments
databar enrich get 123                       # get enrichment details (params, response fields)
databar enrich choices 123 country           # list choices for a select param
databar enrich run 123 --params '{"email": "alice@example.com"}'        # run single
databar enrich run 123 --params '{"email": "alice@example.com"}' --format json
databar enrich bulk 123 --input leads.csv --format csv --out results.csv  # bulk from CSV
```

### Waterfalls

```bash
databar waterfall list                       # list all waterfalls
databar waterfall get email_getter           # get waterfall details
databar waterfall run email_getter --params '{"linkedin_url": "https://linkedin.com/in/alice"}'
databar waterfall bulk email_getter --input leads.csv --out results.csv
```

### Tables

```bash
databar table list                           # list tables
databar table create --name "My Leads" --columns "email,name,company"
databar table columns <table-uuid>           # list columns
databar table rows <table-uuid>              # get rows
databar table rows <table-uuid> --format csv --out rows.csv

# Insert rows (from JSON or CSV)
databar table insert <table-uuid> --data '[{"email":"alice@example.com","name":"Alice"}]'
databar table insert <table-uuid> --input data.csv --allow-new-columns
databar table insert <table-uuid> --input data.csv --dedupe-keys email

# Upsert by key column
databar table upsert <table-uuid> --key-col email --input data.csv

# Update rows by UUID
databar table patch <table-uuid> --data '[{"id":"<row-uuid>","fields":{"name":"New"}}]'

# Table enrichments
databar table enrichments <table-uuid>
databar table add-enrichment <table-uuid> --enrichment-id 123 --mapping '{"email": "email_col"}'
databar table run-enrichment <table-uuid> --enrichment-id <table-enrichment-id>
```

> **Note:** `--enrichment-id` in `run-enrichment` is the **table-enrichment ID** returned by `add-enrichment` (or `table enrichments`), NOT the original enrichment catalog ID.

### Tasks

Enrichment and waterfall runs are async — they return a `task_id`. Use these to check results:

```bash
databar task get <task-id>                   # check status once
databar task get <task-id> --poll            # poll until complete
```

### Account

```bash
databar whoami                               # show email, balance, plan
databar whoami --format json
```

---

## Python SDK Quick Reference

```python
from databar import DatabarClient

client = DatabarClient()  # reads DATABAR_API_KEY from env

# --- Enrichments ---
enrichments = client.list_enrichments(q="linkedin")
enrichment = client.get_enrichment(123)

# Sync (submit + poll in one call — recommended)
result = client.run_enrichment_sync(123, {"email": "alice@example.com"})

# Async (manual polling)
task = client.run_enrichment(123, {"email": "alice@example.com"})
# task.task_id  ← use this to poll
result = client.poll_task(task.task_id)

# Bulk
results = client.run_enrichment_bulk_sync(123, [
    {"email": "alice@example.com"},
    {"email": "bob@example.com"},
])

# --- Waterfalls ---
result = client.run_waterfall_sync("email_getter", {"linkedin_url": "https://linkedin.com/in/alice"})

# --- Tables ---
tables = client.list_tables()
table = client.create_table(name="Leads", columns=["email", "name"])
rows = client.get_rows(table.identifier)

from databar import InsertRow, InsertOptions, DedupeOptions
client.create_rows(table.identifier, [
    InsertRow(fields={"email": "alice@example.com", "name": "Alice"}),
])
```

---

## Key Concepts

### Async task flow

All enrichment and waterfall runs are async:

1. Call a run endpoint → get back `{ "task_id": "...", "status": "processing" }`
2. Poll `GET /v1/tasks/{task_id}` until `status` is `completed`, `failed`, or `gone`
3. Read results from the `data` field

The SDK's `*_sync` methods do this automatically. The CLI's `task get --poll` does too.

### task_id is the only identifier

Every run response returns a single `task_id`. Use it everywhere:
- `client.poll_task(task.task_id)`
- `databar task get <task_id>`
- `GET /v1/tasks/{task_id}`

### Data retention

Results are stored for **1 hour only**. After that, `GET /v1/tasks/{task_id}` returns `status: "gone"`.

### Output formats

```bash
--format table   # rich table (default, human-readable)
--format json    # JSON array, pipeable to jq
--format csv     # CSV, use with --out results.csv
```

> **Important for agents:** Always pass `--format json` (or `--output json`) when you need to parse or pipe CLI output. The default `table` format contains Rich terminal formatting that is not machine-parseable.

---

## Table Enrichments Workflow

Adding an enrichment to a table is a two-step process:

1. **Add the enrichment** — links the enrichment to the table and configures the column mapping.
2. **Run the enrichment** — triggers execution on all rows using the **table-enrichment ID** (not the catalog enrichment ID).

```bash
# 1. Find the right enrichment
databar enrich list --query "email verifier"
databar enrich get <enrichment-id>     # see param names

# 2. See your table columns
databar table columns <table-uuid>

# 3. Add enrichment — mapping keys = enrichment param names, values = column names
databar table add-enrichment <table-uuid> \
  --enrichment-id <enrichment-id> \
  --mapping '{"email": {"type": "mapping", "value": "email_column_name"}}'
# → Returns a table-enrichment-id (different from the catalog enrichment-id)

# 4. Run it using the table-enrichment-id
databar table run-enrichment <table-uuid> --enrichment-id <table-enrichment-id>
```

SDK equivalent:

```python
# Add enrichment — pass column names; SDK auto-resolves to UUIDs
te = client.add_enrichment(
    table_uuid,
    enrichment_id=123,
    mapping={"email": {"type": "mapping", "value": "email"}}  # "email" is the column name
)
# te.id is the TABLE-ENRICHMENT id — use this for run_table_enrichment
client.run_table_enrichment(table_uuid, str(te.id))
```

---

## Discovery Workflow (for agents)

To find the right enrichment:

```bash
databar enrich list --query "email"          # search by keyword
databar enrich get <id>                      # inspect params and response fields
databar enrich run <id> --params '{"param": "value"}'
```

To find a waterfall:

```bash
databar waterfall list
databar waterfall get <identifier>           # see input_params and available_enrichments
databar waterfall run <identifier> --params '{"param": "value"}'
```

---

## Error Handling (SDK)

```python
from databar import (
    DatabarAuthError,           # 401/403 — bad API key
    DatabarInsufficientCreditsError,  # 406 — not enough credits
    DatabarNotFoundError,       # 404 — enrichment/table not found
    DatabarTaskFailedError,     # task completed with error
    DatabarTimeoutError,        # polling timed out
    DatabarGoneError,           # task data expired (>1 hour)
)
```
