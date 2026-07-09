# Databar Python SDK

Official Python SDK and CLI for [Databar.ai](https://databar.ai) — run data enrichments, waterfall lookups, and manage tables via `api.databar.ai/v1`.

[![PyPI](https://img.shields.io/pypi/v/databar-ai)](https://pypi.org/project/databar-ai/)
[![Python](https://img.shields.io/pypi/pyversions/databar-ai)](https://pypi.org/project/databar-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Installation

```bash
pip install databar
```

Requires Python 3.9+.

---

## Authentication

Get your API key from [databar.ai](https://databar.ai) → **Integrations**.

**Option 1 — CLI (recommended):**
```bash
databar login
```
Saves your key to `~/.databar/config`.

**Option 2 — Environment variable:**
```bash
export DATABAR_API_KEY=your-key-here
```

**Option 3 — In code:**
```python
from databar import DatabarClient
client = DatabarClient(api_key="your-key-here")
```

---

## Python SDK

### Quick start

```python
from databar import DatabarClient

client = DatabarClient()  # reads DATABAR_API_KEY from env

# Check your balance
user = client.get_user()
print(f"Balance: {user.balance} credits")

# Find enrichments
enrichments = client.list_enrichments(q="linkedin")
for e in enrichments:
    print(f"  [{e.id}] {e.name} — {e.price} credits")

# Run a single enrichment (submit + poll in one call)
result = client.run_enrichment_sync(123, {"email": "alice@example.com"})
print(result)

# Run a waterfall
result = client.run_waterfall_sync("email_getter", {"linkedin_url": "https://linkedin.com/in/alice"})
print(result)
```

### Enrichments

```python
# List all enrichments
enrichments = client.list_enrichments()

# Search enrichments
enrichments = client.list_enrichments(q="phone")

# Paginated list (returns EnrichmentListResponse)
page = client.list_enrichments(page=1, limit=50, category="Company Data")
for e in page.items:
    print(f"  [{e.id}] {e.name} — {e.price} credits")
if page.has_next_page:
    page2 = client.list_enrichments(page=2, limit=50)

# Get full details (params, response fields)
enrichment = client.get_enrichment(123)
for param in enrichment.params:
    print(f"  {param.name} (required={param.is_required}): {param.description}")

# Run single enrichment (async — returns task)
task = client.run_enrichment(123, {"email": "alice@example.com"})
data = client.poll_task(task.task_id)

# Run single enrichment (sync convenience wrapper)
data = client.run_enrichment_sync(123, {"email": "alice@example.com"})

# Run with pagination (for list-style enrichments)
data = client.run_enrichment_sync(123, {"query": "CEO"}, pages=3)

# Bulk run — results are aligned to inputs: one element per input, in input
# order, with None for inputs that returned no data (len(data) == len(inputs)).
data = client.run_enrichment_bulk_sync(123, [
    {"email": "alice@example.com"},
    {"email": "bob@example.com"},
])

# Get choices for a select parameter
choices = client.get_param_choices(123, "country", q="united")
for choice in choices.items:
    print(f"  {choice.id}: {choice.name}")
```

### Waterfalls

```python
# List waterfalls
waterfalls = client.list_waterfalls()

# Run a waterfall (tries all providers in sequence)
result = client.run_waterfall_sync(
    "email_getter",
    {"linkedin_url": "https://linkedin.com/in/alice"},
)

# Run with specific providers only
result = client.run_waterfall_sync(
    "email_getter",
    {"linkedin_url": "https://linkedin.com/in/alice"},
    enrichments=[10, 11],  # provider IDs
)

# Bulk waterfall
results = client.run_waterfall_bulk_sync(
    "email_getter",
    [{"linkedin_url": url} for url in urls],
)
```

### Tables

```python
# List and manage tables
tables = client.list_tables()
table = client.create_table(name="My Leads", columns=["email", "name", "company"])
client.rename_table(table.identifier, "Leads 2026")
client.delete_table(table.identifier)

# Columns
columns = client.get_columns(table.identifier)
col = client.create_column(table.identifier, "Phone", type="text")
client.rename_column(table.identifier, col.identifier, "Mobile")
client.delete_column(table.identifier, col.identifier)

# Get rows with optional server-side filter
import json
data = client.get_rows(table.identifier, page=1, per_page=500)
filtered = client.get_rows(
    table.identifier,
    filter=json.dumps({"company": {"contains": "OpenAI"}}),
)

# Insert rows (auto-batched at 50)
from databar import InsertRow, InsertOptions, DedupeOptions

rows = [InsertRow(fields={"email": e, "name": n}) for e, n in leads]
response = client.create_rows(
    table.identifier,
    rows,
    options=InsertOptions(
        allow_new_columns=True,
        dedupe=DedupeOptions(enabled=True, keys=["email"]),
    ),
)
print(f"Created: {len([r for r in response.results if r.action == 'created'])}")

# Update rows by UUID
from databar import BatchUpdateRow
rows = [BatchUpdateRow(id=row_id, fields={"name": "Updated Name"})]
client.patch_rows(table.identifier, rows)

# Upsert rows by key column
from databar import UpsertRow
rows = [UpsertRow(key={"email": "alice@example.com"}, fields={"name": "Alice"})]
client.upsert_rows(table.identifier, rows)

# Delete specific rows
client.delete_rows(table.identifier, ["row-uuid-1", "row-uuid-2"])
```

### Enrichments on tables

```python
# Add an enrichment (with column mapping)
result = client.add_enrichment(
    table.identifier,
    enrichment_id=123,
    mapping={
        "email": {"type": "mapping", "value": "email_col"},   # from column
        "country": {"type": "simple", "value": "US"},          # static value
    },
    launch_strategy="run_on_click",  # or "run_on_update"
)
print(f"Added enrichment #{result.id}: {result.enrichment_name}")

# Run it (run_strategy: run_all | run_empty | run_errors)
status = client.run_table_enrichment(
    table.identifier,
    enrichment_id=str(result.id),
    run_strategy="run_empty",
)
print(f"Processing {status.processing_rows} rows")
```

### Waterfalls on tables

```python
# Add a waterfall
wf = client.add_waterfall(
    table.identifier,
    waterfall_identifier="email_getter",
    enrichments=[833, 966],
    mapping={"first_name": "first_name", "company": "company"},
    email_verifier=10,
)
print(f"Added waterfall #{wf.id}: {wf.waterfall_name}")

# List installed waterfalls
installed = client.get_table_waterfalls(table.identifier)

# Run the waterfall
client.run_table_enrichment(table.identifier, enrichment_id=str(wf.id))
```

### Exporters

```python
# List available exporters
exporters = client.list_exporters()              # plain list
page = client.list_exporters(page=1, limit=50)  # paginated envelope

# Get exporter details (params, authorization info)
detail = client.get_exporter(exporters[0].id)
print(detail.params, detail.authorization.required)

# Add an exporter to a table
result = client.add_exporter(
    table.identifier,
    exporter_id=detail.id,
    mapping={"email": {"type": "mapping", "value": "email_col"}},
)
client.run_table_enrichment(table.identifier, enrichment_id=str(result.id))
```

### Connectors

```python
# Create a custom HTTP API connector
connector = client.create_connector(
    name="My Scoring API",
    method="post",
    url="https://api.example.com/v1/score",
    headers=[{"name": "Authorization", "value": "Bearer sk-xxx"}],
    body=[{"name": "domain", "value": ""}],
    rate_limit=60,
)

# CRUD
connectors = client.list_connectors()
c = client.get_connector(connector.id)
client.update_connector(connector.id, name="Updated API", method="post", url="https://...")
client.delete_connector(connector.id)
```

### Folders

```python
# Organize tables in folders
folder = client.create_folder("My Leads")
folders = client.list_folders()
client.rename_folder(folder.id, "Leads 2026")
client.move_table_to_folder(table.identifier, folder_id=folder.id)
client.move_table_to_folder(table.identifier)          # remove from folder
client.delete_folder(folder.id)                        # tables move to root
```

### Error handling

```python
from databar import (
    DatabarClient,
    DatabarAuthError,
    DatabarInsufficientCreditsError,
    DatabarNotFoundError,
    DatabarTaskFailedError,
    DatabarTimeoutError,
)

try:
    result = client.run_enrichment_sync(123, {"email": "alice@example.com"})
except DatabarAuthError:
    print("Invalid API key")
except DatabarInsufficientCreditsError:
    print("Not enough credits")
except DatabarNotFoundError:
    print("Enrichment not found")
except DatabarTaskFailedError as e:
    print(f"Task failed: {e.message}")
except DatabarTimeoutError as e:
    print(f"Timed out after polling {e.max_attempts} times")
```

### Context manager

```python
with DatabarClient() as client:
    result = client.run_enrichment_sync(123, {"email": "alice@example.com"})
# connection pool closed automatically
```

---

## CLI

After installing, the `databar` command is available in your terminal.

### Authentication

```bash
databar login              # save API key interactively
databar whoami             # show name, email, balance, plan
databar whoami --format json
```

### Enrichments

```bash
# List enrichments
databar enrich list
databar enrich list --query "linkedin"
databar enrich list --format json

# Get enrichment details
databar enrich get 123

# Run a single enrichment
databar enrich run 123 --params '{"email": "alice@example.com"}'
databar enrich run 123 --params '{"email": "alice@example.com"}' --format json

# Bulk run from CSV
databar enrich bulk 123 --input emails.csv --format csv --out results.csv

# Get choices for a select parameter
databar enrich choices 123 country
databar enrich choices 123 country --query "united"
```

### Waterfalls

```bash
# List waterfalls
databar waterfall list
databar waterfall list --query "email"

# Get waterfall details
databar waterfall get email_getter

# Run a waterfall
databar waterfall run email_getter --params '{"linkedin_url": "https://linkedin.com/in/alice"}'

# Bulk run from CSV
databar waterfall bulk email_getter --input leads.csv --out results.csv
```

### Tables

```bash
# List tables
databar table list

# Create a table
databar table create --name "My Leads"
databar table create --name "My Leads" --columns "email,name,company"

# Inspect a table
databar table columns <uuid>
databar table rows <uuid>
databar table rows <uuid> --page 2 --per-page 500
databar table rows <uuid> --format csv --out rows.csv

# Insert rows
databar table insert <uuid> --data '[{"email":"alice@example.com","name":"Alice"}]'
databar table insert <uuid> --input data.csv --allow-new-columns
databar table insert <uuid> --input data.csv --dedupe-keys email

# Update rows by UUID
databar table patch <uuid> --data '[{"id":"<row-uuid>","email":"new@example.com"}]'

# Upsert rows by key column
databar table upsert <uuid> --key-col email --input data.csv

# Enrichments on a table
databar table enrichments <uuid>
databar table add-enrichment <uuid> --enrichment-id 123 --mapping '{"email": "email_col"}'
databar table run-enrichment <uuid> --enrichment-id <table-enrichment-id>
```

### Tasks

```bash
# Check a task status
databar task get <task-id>

# Poll until complete
databar task get <task-id> --poll
```

### Output formats

All commands support `--format table|json|csv` (default: `table`):

```bash
# Pipe JSON output
databar table rows <uuid> --format json | jq '.[].email'

# Save to CSV
databar enrich bulk 123 --input input.csv --format csv --out output.csv
```

---

## Configuration

| Variable | Description |
|---|---|
| `DATABAR_API_KEY` | Your Databar API key (overrides `~/.databar/config`) |

---

## Development

```bash
git clone https://github.com/databar-ai/databar-python
cd databar-python
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).
