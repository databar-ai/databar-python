"""Embedded agent guide — printed by `databar agent-guide`."""

AGENT_GUIDE = r"""# Databar — Agent Guide

Databar is a data enrichment platform. Given an input (email, LinkedIn URL, company
domain, etc.) it returns enriched data from dozens of providers. The `databar` package
ships three interfaces: a **CLI**, a **Python SDK**, and an **MCP server**.

Databar supports two enrichment workflows:

- **Direct** — submit inputs and get results back immediately. Best for one-off lookups
  or bulk CSV processing where you just need the output.
- **Table-based** — create a table, upload rows, attach enrichments, run them. Results
  appear as new columns on each row. Best when you want observability (see results in
  the Databar UI), re-run enrichments on the same data, or build a persistent dataset.

---

## DECISION MATRIX — read this first

+----------------------------------+--------------------+
| Situation                        | Use                |
+----------------------------------+--------------------+
| MCP tools available this session | MCP (best option)  |
| Single operation, no branching   | CLI                |
| Conditional logic / loops /      | Python SDK         |
| multi-step pipeline with         |                    |
| decisions per row                |                    |
+----------------------------------+--------------------+

**Default: CLI.** Use Python SDK only when you need to branch on results or loop
with per-row decisions. Use MCP when it is configured — it requires zero setup.

---

## STEP 1 — Check authentication

```bash
echo $DATABAR_API_KEY      # check env var
cat ~/.databar/config      # check saved config (file has no extension)
```

If neither exists, ask the user in chat:
  "Please provide your Databar API key (databar.ai → Settings → API Keys)."

Then save it non-interactively:

```bash
databar login --api-key <key>
databar whoami --format json    # verify
```

Never run `databar onboard` — interactive wizard, not for agents.
Never run `databar login` without `--api-key` — will hang on terminal input.

---

## STEP 2 — Ask the user their preferred interface AND workflow

Unless ~/.databar/config already contains `preferred_interface=`, ask:

  "Databar has three interfaces — which do you prefer?
   - CLI (default) — terminal commands, no code, pipeable JSON. Best for single operations.
   - Python SDK — required for conditional logic, loops, multi-step pipelines with branching.
   - MCP — if configured in your Claude session, it's the most agent-native option.
   Which do you prefer?"

Also ask about workflow preference:

  "Databar supports two enrichment workflows — which fits your use case?
   - Direct (default) — submit inputs, get results back immediately. Good for one-off
     lookups or bulk CSV jobs where you just need the output fast.
   - Table-based — create a table, upload rows, attach enrichments, then run them.
     Results appear as new columns in the Databar UI. Best when you want observability,
     plan to re-run enrichments, or want to pair with the Databar web interface.
   Which do you prefer?"

Save their answers:
```bash
echo "preferred_interface=cli" >> ~/.databar/config      # or: python, mcp, both
echo "preferred_workflow=direct" >> ~/.databar/config    # or: table
```

---

## STEP 3 — Fix PATH before using the CLI

After `pip install databar`, the binary is NOT on PATH by default. Always check:

```bash
which databar        # empty = not on PATH
databar --version    # "command not found" = fix PATH first
```

Fix for this session:
```bash
export PATH="$(python3 -m site --user-base)/bin:$PATH"
databar --version    # should work now
```

Make permanent:
```bash
echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.zshrc
```

---

## CLI Quick Reference

**Always use `--format json` when parsing or piping output.**
The default `table` format uses Rich terminal markup — not machine-parseable.

### Enrichments
```bash
databar enrich list --format json
databar enrich list --query "email verifier" --format json
databar enrich get <id> --format json                       # params + response fields
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

NOTE: `run-enrichment` takes the TABLE-ENRICHMENT ID (from `add-enrichment` or
`table enrichments`), NOT the catalog enrichment ID. These are different numbers.

### Tasks
```bash
databar task get <task-id> --format json    # check once
databar task get <task-id> --poll           # poll until complete
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
result = client.run_waterfall_sync("email_getter", {"linkedin_url": "..."})
# waterfall.identifier (also .slug) → slug like "email_getter"

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

- All runs are async. `*_sync` methods and `--poll` flag handle submit + poll automatically.
- `task_id` is the only task identifier. Results expire after 1 hour (status = "gone").
- Table enrichments: add-enrichment (configure) → run-enrichment (execute).
  The ID from add is the TABLE-ENRICHMENT ID — different from the catalog ID.
- SDK auto-resolves column names to UUIDs in `add_enrichment()`.

## Model Field Aliases (Python SDK)

- `Table`: `.id`, `.uuid` → `.identifier`
- `Waterfall`: `.slug` → `.identifier`
- `EnrichmentParam`: `.slug` → `.name`, `.label` → `.description`, `.required` → `.is_required`
- `EnrichmentResponseField`: `.slug` → `.name`

## Error Handling (Python SDK)

```python
from databar import (
    DatabarAuthError,                  # 401/403
    DatabarInsufficientCreditsError,   # 406
    DatabarNotFoundError,              # 404
    DatabarTaskFailedError,            # task failed
    DatabarTimeoutError,               # polling timed out
    DatabarGoneError,                  # results expired (>1 hour)
)
```
"""
