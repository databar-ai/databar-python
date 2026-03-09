# Databar SDK & CLI — Claude Code Guide

Databar is a data enrichment platform. Given an input (email, LinkedIn URL, company
domain, etc.) it returns enriched data from dozens of providers. The `databar` package
ships three interfaces: a **CLI**, a **Python SDK**, and an **MCP server**.

Databar supports two enrichment workflows:

- **Direct** — submit inputs, get results back immediately. Best for one-off lookups or bulk CSV jobs.
- **Table-based** — create a table, upload rows, attach enrichments, run them. Results appear as new columns. Best for observability, re-running enrichments, or pairing with the Databar web UI.

---

## STEP 1 — Check authentication

Before doing anything else, check whether the user is already authenticated:

```bash
echo $DATABAR_API_KEY        # check env var
cat ~/.databar/config        # check saved config
```

If neither exists, ask the user in chat:

> "Please provide your Databar API key. You can find it at databar.ai → Settings → API Keys."

Once they give it to you, save it non-interactively:

```bash
databar login --api-key <key>
databar whoami --format json    # verify
```

**Never run `databar onboard`** — that is an interactive wizard for humans, not agents.  
**Never run `databar login` without `--api-key`** — it will hang waiting for terminal input.

---

## STEP 2 — Ask the user their preferred interface AND workflow

Unless `~/.databar/config` already contains `preferred_interface=`, ask the user:

> "Databar has three interfaces — which do you prefer?
>
> - **CLI** (default) — terminal commands, pipeable JSON output, no code to write.
>   Best for single operations: run an enrichment, insert rows, list tables.
> - **Python SDK** — required when you need conditional logic (e.g. only enrich
>   verified emails), loops over results, or multi-step pipelines with branching.
> - **MCP** — if Databar MCP tools are available in this session, use them — most
>   agent-native option, zero setup required."

Also ask about workflow preference:

> "Databar supports two enrichment workflows — which fits your use case?
>
> - **Direct** (default) — submit inputs, get results back immediately. Good for
>   one-off lookups or bulk CSV jobs where you just need the output.
> - **Table-based** — create a table, upload rows, attach enrichments, then run them.
>   Results appear as new columns in the Databar UI. Best when you want observability,
>   plan to re-run enrichments, or want to pair with the Databar web interface."

Default to **CLI + Direct** if the user doesn't specify. Save their answers:

```bash
echo "preferred_interface=cli" >> ~/.databar/config     # or: python, mcp, both
echo "preferred_workflow=direct" >> ~/.databar/config   # or: table
```

---

## STEP 3 — Fix PATH before using the CLI

After `pip install databar`, the binary lands in the Python user bin directory which is
**not on PATH by default**. Always verify before running any CLI command:

```bash
which databar        # empty output = not on PATH
databar --version    # "command not found" = fix PATH first
```

**If not on PATH:**

```bash
export PATH="$(python3 -m site --user-base)/bin:$PATH"
databar --version    # should now work
```

Offer to make it permanent:

```bash
echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.zshrc
```

---

## CLI Quick Reference

All commands support `--format table|json|csv` (default: `table`).  
**Always use `--format json` when parsing or piping output** — the default `table`
format uses Rich terminal formatting that is not machine-parseable.

### Enrichments

```bash
databar enrich list --format json
databar enrich list --query "email verifier" --format json
databar enrich get <id> --format json                      # params + response fields
databar enrich choices <id> <param> --format json
databar enrich run <id> --params '{"email": "a@b.com"}' --format json
databar enrich bulk <id> --input data.csv --out results.csv
```

### Waterfalls

```bash
databar waterfall list --format json
databar waterfall get <identifier> --format json
databar waterfall run <identifier> --params '{"key": "value"}' --format json
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
databar table add-enrichment <table-uuid> --enrichment-id <id> \
  --mapping '{"param": "column_name"}'
databar table run-enrichment <table-uuid> --enrichment-id <TABLE-ENRICHMENT-ID>
```

> `run-enrichment` uses the **TABLE-ENRICHMENT ID** (from `add-enrichment` output or
> `table enrichments`), NOT the catalog enrichment ID. These are different numbers.

### Tasks

```bash
databar task get <task-id> --format json    # check once
databar task get <task-id> --poll           # poll until complete
```

### Account

```bash
databar whoami --format json
```

---

## Python SDK Quick Reference

```python
from databar import DatabarClient

client = DatabarClient()  # reads DATABAR_API_KEY or ~/.databar/config automatically

# Enrichments
enrichments = client.list_enrichments(q="email verifier")
enrichment  = client.get_enrichment(123)
# enrichment.params[i].name        → param slug (key in params dict)
# enrichment.params[i].is_required → bool
# enrichment.params[i].description → human label
result = client.run_enrichment_sync(123, {"email": "alice@example.com"})

# Waterfalls
waterfalls = client.list_waterfalls()
# waterfall.identifier (also .slug) → e.g. "email_getter"
result = client.run_waterfall_sync("email_getter", {"linkedin_url": "..."})

# Tables
tables = client.list_tables()
# table.identifier (also .id, .uuid) → UUID string
table = client.create_table(name="Leads", columns=["email", "name"])
resp  = client.get_rows(table.identifier)
# resp.data          → list of row dicts keyed by column name
# resp.has_next_page → bool
# resp.total_count   → int

from databar import InsertRow
client.create_rows(table.identifier, [InsertRow(fields={"email": "alice@example.com"})])
```

---

## Key Concepts

- All enrichment/waterfall runs are **async** — submit → get `task_id` → poll until done.
  The `*_sync` methods and `--poll` flag handle this automatically.
- `task_id` is the only task identifier. Results **expire after 1 hour** (status = `"gone"`).
- Table enrichments are two steps: `add-enrichment` (configure mapping) → `run-enrichment`
  (trigger execution). The ID from `add-enrichment` is the TABLE-ENRICHMENT ID.
- The SDK auto-resolves column names to UUIDs in `add_enrichment()`.

## Model Field Aliases (Python SDK)

| Model | Alias | Real field |
|---|---|---|
| `Table` | `.id`, `.uuid` | `.identifier` |
| `Waterfall` | `.slug` | `.identifier` |
| `EnrichmentParam` | `.slug` | `.name` |
| `EnrichmentParam` | `.label` | `.description` |
| `EnrichmentParam` | `.required` | `.is_required` |
| `EnrichmentResponseField` | `.slug` | `.name` |

## Error Handling (Python SDK)

```python
from databar import (
    DatabarAuthError,                  # 401/403
    DatabarInsufficientCreditsError,   # 406
    DatabarNotFoundError,              # 404
    DatabarTaskFailedError,            # task failed
    DatabarTimeoutError,               # polling timed out
    DatabarGoneError,                  # results expired
)
```
