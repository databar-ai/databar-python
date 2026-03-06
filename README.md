# Databar Python SDK

Official Python SDK and CLI for [Databar.ai](https://databar.ai) — run data enrichments, waterfall lookups, and manage tables via `api.databar.ai/v1`.

[![PyPI](https://img.shields.io/pypi/v/databar-ai)](https://pypi.org/project/databar-ai/)
[![Python](https://img.shields.io/pypi/pyversions/databar-ai)](https://pypi.org/project/databar-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Installation

```bash
pip install databar-ai
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

# Get full details (params, response fields)
enrichment = client.get_enrichment(123)
for param in enrichment.params:
    print(f"  {param.name} (required={param.is_required}): {param.description}")

# Run single enrichment (async — returns task)
task = client.run_enrichment(123, {"email": "alice@example.com"})
data = client.poll_task(task.request_id)

# Run single enrichment (sync convenience wrapper)
data = client.run_enrichment_sync(123, {"email": "alice@example.com"})

# Bulk run
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
# List tables
tables = client.list_tables()

# Create a table
table = client.create_table(name="My Leads", columns=["email", "name", "company"])

# Get columns
columns = client.get_columns(table.identifier)

# Get rows (paginated)
data = client.get_rows(table.identifier, page=1, per_page=500)

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
response = client.patch_rows(table.identifier, rows)

# Upsert rows by key column
from databar import UpsertRow

rows = [UpsertRow(key={"email": "alice@example.com"}, fields={"name": "Alice"})]
response = client.upsert_rows(table.identifier, rows)
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
