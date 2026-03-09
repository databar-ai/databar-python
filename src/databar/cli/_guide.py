"""Embedded agent guide — printed by `databar agent-guide`."""

AGENT_GUIDE = r"""# Databar — Agent Guide

Databar is a data enrichment platform. The `databar` package ships both a
**CLI** and a **Python SDK**. This guide tells you exactly how to set up and
use each, including common pitfalls.

---

## STEP 1 — Check authentication

Before doing anything else, check whether the user is already authenticated:

```bash
# Check 1: env var
echo $DATABAR_API_KEY

# Check 2: saved config
cat ~/.databar/config
```

If neither exists, the user is not authenticated. Ask them in chat:

  "Please provide your Databar API key. You can find it at databar.ai → Settings → API Keys."

Once they give it to you, save it non-interactively:

```bash
databar login --api-key <key they provided>
databar whoami --format json    # verify it works
```

Never run `databar onboard` — that is an interactive wizard for humans, not agents.
Never run `databar login` without `--api-key` — it will hang waiting for terminal input.

---

## STEP 2 — Ask the user which interface they prefer

**Always ask this before starting work** (unless ~/.databar/config already contains
`preferred_interface=`):

  "Databar has two interfaces:
   - **CLI** — terminal commands, great for single operations, pipeable JSON output,
     no code to write. Best for straightforward tasks.
   - **Python SDK** — import DatabarClient, full control, required for conditional
     logic (e.g. 'only enrich rows where email is verified') and multi-step pipelines
     with branching.
   - **Both** — use CLI for simple lookups, Python for complex workflows.

   Which do you prefer? (default: CLI)"

Save their preference:

```bash
# After they answer, append to config:
echo "preferred_interface=cli" >> ~/.databar/config     # or: python, both
```

Default to CLI if they don't answer or say they don't mind.

---

## STEP 3 — Set up the CLI (IMPORTANT — read carefully)

### The PATH problem

After `pip install databar`, the `databar` binary is installed to the Python
user bin directory — but this directory is NOT on PATH by default on most systems.

**Always check this first:**

```bash
which databar        # if this prints nothing, databar is not on PATH
databar --version    # if this says "command not found", fix PATH before continuing
```

**If databar is not on PATH, fix it:**

```bash
# Find where it's installed
python3 -m site --user-base    # e.g. /Users/alice/Library/Python/3.9

# The binary is at <user-base>/bin/databar
# Add to PATH for this session:
export PATH="$(python3 -m site --user-base)/bin:$PATH"

# Verify it works now:
databar --version
```

Tell the user to add that export line to their `~/.zshrc` or `~/.bashrc` to make
it permanent. You can offer to do it:

```bash
echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.zshrc
```

### CLI vs Python — when to use each

Use CLI when:
- Running a single enrichment or waterfall on known inputs
- Listing/searching enrichments, waterfalls, or tables
- Creating tables, inserting rows from CSV or JSON
- Running table enrichments
- The task is straightforward with no branching logic

Use Python SDK when:
- You need to branch on results (e.g. only process rows where a field matches)
- You're building a multi-step pipeline where step N depends on step N-1's output
- You need to loop over results and make decisions per row
- The task requires data transformation between steps

---

## CLI Quick Reference

All commands support `--format table|json|csv` (default: table).
**Always use `--format json` when you need to parse or pipe the output.**
The default `table` format uses Rich terminal formatting that is not machine-parseable.

### Enrichments
```bash
databar enrich list --format json                          # list all enrichments
databar enrich list --query "email verifier" --format json # search
databar enrich get <id> --format json                      # params + response fields
databar enrich choices <id> <param> --format json          # choices for a select param
databar enrich run <id> --params '{"email": "a@b.com"}' --format json
databar enrich bulk <id> --input data.csv --out results.csv
```

### Waterfalls
```bash
databar waterfall list --format json
databar waterfall get <identifier> --format json
databar waterfall run <identifier> --params '{"linkedin_url": "..."}' --format json
databar waterfall bulk <identifier> --input data.csv --out results.csv
```

### Tables
```bash
databar table list --format json
databar table create --name "My Table" --columns "email,name,company"
databar table columns <table-uuid> --format json
databar table rows <table-uuid> --format json

databar table insert <table-uuid> --data '[{"email":"a@b.com"}]'
databar table insert <table-uuid> --input data.csv --allow-new-columns

databar table enrichments <table-uuid> --format json
databar table add-enrichment <table-uuid> --enrichment-id <id> --mapping '{"param": "col_name"}'
databar table run-enrichment <table-uuid> --enrichment-id <TABLE-ENRICHMENT-ID>
```

IMPORTANT: `run-enrichment` takes the TABLE-ENRICHMENT ID (from `add-enrichment` output or
`table enrichments`), NOT the catalog enrichment ID. These are different numbers.

### Tasks
```bash
databar task get <task-id> --format json     # check status once
databar task get <task-id> --poll            # poll until complete
```

---

## Python SDK Quick Reference

```python
from databar import DatabarClient

client = DatabarClient()  # reads DATABAR_API_KEY or ~/.databar/config automatically

# Enrichments
enrichments = client.list_enrichments(q="email verifier")
enrichment = client.get_enrichment(123)
# enrichment.params[i].name          → parameter slug (use as key in params dict)
# enrichment.params[i].is_required   → bool
# enrichment.params[i].description   → human label
# enrichment.response_fields[i].name → output field name

result = client.run_enrichment_sync(123, {"email": "alice@example.com"})
# result["data"] contains the enrichment output

# Waterfalls
waterfalls = client.list_waterfalls()
# waterfall.identifier (also .slug) → slug like "email_getter"
result = client.run_waterfall_sync("email_getter", {"linkedin_url": "..."})

# Tables
tables = client.list_tables()
# table.identifier (also .id, .uuid) → UUID string

table = client.create_table(name="Leads", columns=["email", "name"])
resp = client.get_rows(table.identifier)
# resp.data           → list of row dicts keyed by column name
# resp.has_next_page  → bool
# resp.total_count    → int
# resp.page           → int

from databar import InsertRow
client.create_rows(table.identifier, [
    InsertRow(fields={"email": "alice@example.com", "name": "Alice"}),
])
```

---

## Key Concepts

- All enrichment/waterfall runs are async. The `*_sync` CLI and SDK methods handle
  submit + poll automatically. For manual polling use `task get --poll` or `poll_task()`.
- `task_id` is the only task identifier. Results expire after 1 hour (status = "gone").
- Table enrichments are two steps: add (links enrichment to table) → run (triggers execution).
  The ID returned by add is the TABLE-ENRICHMENT ID — different from the catalog ID.
- The SDK auto-resolves column names to UUIDs in `add_enrichment()`.

## Model Field Aliases (Python SDK)

- `Table`: `.id`, `.uuid` → `.identifier`
- `Waterfall`: `.slug` → `.identifier`
- `EnrichmentParam`: `.slug` → `.name`, `.label` → `.description`, `.required` → `.is_required`
- `EnrichmentResponseField`: `.slug` → `.name`

## Error Handling (Python SDK)

```python
from databar import (
    DatabarAuthError,                  # 401/403 — bad or missing API key
    DatabarInsufficientCreditsError,   # 406 — not enough credits
    DatabarNotFoundError,              # 404 — enrichment/table not found
    DatabarTaskFailedError,            # task completed with error
    DatabarTimeoutError,               # polling timed out
    DatabarGoneError,                  # task data expired (>1 hour)
)
```
"""
