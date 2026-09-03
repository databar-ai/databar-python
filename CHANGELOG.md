# Changelog

All notable changes to the Databar Python SDK are documented here.

---

## [Unreleased]

---

## [2.5.1] — 2026-09-03

### Fixed

- **CLI crash on Typer 0.26+** — Typer now vendors Click and no longer
  installs the `click` package. `databar` imported `click` at startup, so a
  fresh `pip install databar` on current Typer raised
  `ModuleNotFoundError: No module named 'click'`. Read the live context from
  Typer's vendored Click (and fall back to the `click` package on older Typer).

---

## [2.5.0] — 2026-09-03

Ships everything that never made it to PyPI after 2.2.0 (local 2.3/2.4
were never published).

### Added

- **Flow editing (DEV-5144)** — the client can now create and change flows, not
  just list and run them: `create_flow`, `replace_flow`, `update_flow`,
  `delete_flow`, and `patch_flow_config` for targeted edits that change one node
  without resending the whole graph.
- **Flow version history** — `list_flow_versions`, `get_flow_version` and
  `restore_flow_version`, plus `databar flow versions` / `databar flow restore`
  in the CLI. A rollback is written as a new version, so it is itself revertible.
- `FlowDetail` (a flow plus `config`, `ui` and the `internal_version` token
  needed to edit it), `FlowVersion`, `FlowVersionDetail`, `FlowConfigOpsResult`,
  `RestoreFlowVersionResult`.
- `DatabarConflictError` for `409` — a stale `internal_version`, or a delete
  blocked by a table column still running the flow. Previously untyped.
- **CLI UUID validation (DEV-5135)** — `table` and `task` identifier args are
  checked client-side before any request. Bad values (e.g. `foo%2Fbar`) fail with
  `code: validation` / exit 5 and a UUID hint, instead of a bare API 404.
- **CLI `--out` normalization (DEV-5135)** — output paths are resolved; null bytes
  are rejected; a note is printed when the resolved path leaves the current
  directory.
- **Exporter dynamic fields** — `get_exporter` returns `additional_params`
  (HubSpot/Pipedrive property names) when a connection is available. Pass them
  via `add_exporter(..., additional_mapping={...})` — not via `mapping`.
- **Task progress** — `get_task` now returns a `progress` object for bulk runs
  (`total` / `completed` / `failed` / `processing` counts of inputs), so a task
  that is advancing can be told apart from one that is stuck. `databar task get`
  prints it.
- **Cancel a task** — `client.cancel_task(task_id)` and
  `databar task cancel <task-id>` stop a running task and refund what its
  unfinished requests reserved. Rows that already finished keep their results.
- **Partial results** — `get_task(task_id, include_partial=True)` and
  `databar task get --partial` return the rows a running bulk task has already
  finished. Opt-in, because it makes the API read the whole result set per poll.
- **`DatabarTaskCancelledError`** — raised by `poll_task` when a task was
  cancelled. Carries `.partial_data`, which is *not* aligned to the inputs (the
  rows that never ran leave no gap), so it can't be joined back by position.

### Changed

- `get_flow()` returns `FlowDetail` instead of `Flow`. Without `config` and
  `internal_version` a caller could not do a read-modify-write at all.
- `406` now surfaces the server's own message. It is not always about credits —
  being at the plan's flow limit uses the same status.
- `create_flow()` and `restore_flow_version()` are not retried on a `5xx`: the
  response can arrive after the server already did the work, and a retry would
  do it twice.
- **CLI `--format json` envelope (breaking)** — success and failure both emit a
  single JSON object on stdout:
  `{"ok": true, "data": ...}` / `{"ok": false, "error": {"code", "message", "hint"?}}`.
  Agents must read `.data` (e.g. `jq '.data[].name'`). Errors no longer leave
  stdout empty with prose on stderr.
- **CLI exit codes** — usage → 2, auth → 3, not found → 4, validation → 5;
  other failures stay 1.

### Fixed

- **`--format json` on errors** — failures honor the format flag (DEV-5133).
- **Rich mid-word wrap on errors** — prose errors use soft wrap so stderr
  matching is not broken by terminal width.
- **Malformed `--data` traceback** — `table insert` / `patch` / `upsert` with a
  JSON array of non-objects (e.g. `--data '[1]'`) now emit a clear validation
  error instead of a Rich/Pydantic traceback that leaked local filesystem paths.
  Typer pretty exceptions are off by default; set `DATABAR_DEBUG=1` to re-enable.

---

## [2.3.0] — 2026-08-10

### Fixed

- **Windows redirect crash** — `--format json/csv` no longer raises
  `UnicodeEncodeError` when stdout is redirected on non-UTF-8 locales
  (e.g. cp1251). CLI forces UTF-8 on stdout/stderr and writes CSV files as UTF-8.
- **`table rows` default `--per-page`** — was 1000 (API max is 500), so the
  command failed out of the box with `PER_PAGE_TOO_LARGE`. Default and help
  text are now 500; values outside 1–500 are rejected client-side.
- **`table rows` empty output** — CLI now reads `RowsResponse` correctly
  instead of looking for a legacy `result` dict key.
- **`enrich choices` / pagination** — `--page` must be >= 1 and `--limit`
  must be 1–500; invalid values fail with a clear CLI error instead of a
  backend 500 HTML page.
- **`table create --columns`** — duplicate and empty names are rejected
  instead of creating ambiguous/blank columns.
- **`table patch` / `table upsert` exit code** — returns 1 when any row
  fails (`ok: false`), matching the documented Unix exit-code convention.

### Added

- **`databar table delete <uuid>`** — delete a table via CLI (SDK method
  already existed).
- **`--out`** on list commands that support CSV: `enrich list`,
  `enrich choices`, `table list`, `table columns`, `table enrichments`,
  `waterfall list`, `flow list`.

---

## [2.2.0] — 2026-07-14

### Added

- **Flows** — list, get, and run saved workspace flows (multi-step enrichment
  pipelines), matching the public API (`GET /flows`, `GET /flows/{id}`,
  `POST /flows/{id}/run` + task polling).
  - SDK: `list_flows`, `get_flow`, `run_flow`, `run_flow_sync`.
  - CLI: `databar flow list`, `databar flow get <id>`,
    `databar flow run <id> --inputs '{"key":"value"}'`.
  - New models: `Flow`, `FlowInput`, `FlowOutput`. `Flow.identifier` is an alias
    for `Flow.id`.

### Changed

- **Bulk results are now aligned to inputs.** `run_enrichment_bulk_sync`,
  `run_waterfall_bulk_sync`, and `poll_task` now return a list with one element
  per input, in the original input order, with `None` for inputs that returned
  no data (`len(results) == len(inputs)`, `results[i]` ↔ `inputs[i]`). Previously
  only hits were returned, in no guaranteed order, making it impossible to map a
  result back to its input. This is a **breaking change** to the bulk output
  shape; single (non-bulk) runs are unchanged.

---

## [2.1.0] — 2026-04-09

### Full parity with user_api (api.databar.ai/v1)

This release syncs the SDK with every endpoint currently exposed by the public
`user_api` service, adds new Pydantic models to match its response shapes, and
fixes several behavioral gaps.

#### New endpoint groups

- **Exporters** — `list_exporters`, `get_exporter`
- **Connectors** — `list_connectors`, `get_connector`, `create_connector`,
  `update_connector`, `delete_connector`
- **Folders** — `create_folder`, `list_folders`, `rename_folder`,
  `delete_folder`, `move_table_to_folder`

#### New table operations

- `delete_table`, `rename_table`
- `create_column`, `rename_column`, `delete_column`
- `add_waterfall`, `get_table_waterfalls`
- `add_exporter`, `get_table_exporters`
- `delete_rows`

#### Updated behavior

- **`poll_task`** now also treats `partially_completed` as a successful
  completion (returns data) and ignores `no_data` (continues polling).
- **`list_enrichments`** — new parameters `page`, `limit`, `authorized_only`,
  `category`. Passing `page` returns a paginated `EnrichmentListResponse`
  envelope; omitting it keeps the old plain-list behavior.
- **`list_exporters`** — same pagination pattern as `list_enrichments`.
- **`run_enrichment` / `run_enrichment_bulk`** — new optional `pages` argument
  for list-style enrichments that support pagination.
- **`get_rows`** — new `filter` parameter (JSON-encoded filter object).
- **`create_table`** — new `rows` parameter (number of empty placeholder rows).
- **`add_enrichment`** — new `launch_strategy` parameter
  (`run_on_click` | `run_on_update`). Returns `AddEnrichmentResponse` instead
  of `TableEnrichment` — see breaking changes below.
- **`run_table_enrichment`** — now accepts `run_strategy` (`run_all`,
  `run_empty`, `run_errors`) and optional `row_ids` via JSON body. Returns
  `RunEnrichmentResponse` instead of `Any`.
- TTL text in docstrings and exceptions updated from 1 hour to **24 hours**
  to match the current API documentation.

#### New / updated models

| Model | Notes |
|-------|-------|
| `PricingInfo` | New — describes fixed vs. per-parameter pricing |
| `CategoryInfo` | New — enrichment category tag |
| `PaginationInfo` | New — pagination metadata on enrichment detail |
| `PaginationOptions` | New — `pages` field for run requests |
| `EnrichmentListResponse` | New — paginated envelope for `list_enrichments(page=N)` |
| `EnrichmentSummary` | Added optional `pricing` and `category` fields |
| `Enrichment` | Added optional `pagination` field |
| `EnrichmentResponseField` | Added optional `display_name` field |
| `Choices` | Added optional `endpoint` field (for remote choices mode) |
| `ChoicesResponse` | Added `total_count` field |
| `User` | Added optional `workspace` field |
| `Table` | Added optional `workspace_identifier` and `table_url` fields |
| `Column` | Added optional `additional_intenal_name` field (typo preserved for wire compat) |
| `TaskResponse` | Added deprecated `request_id` alias; handles `partially_completed` / `no_data` statuses |
| `CreateColumnResponse` | New |
| `AddEnrichmentResponse` | New — returned by `add_enrichment` |
| `AddWaterfallResponse` | New — returned by `add_waterfall` |
| `InstalledWaterfall` | New — item in `get_table_waterfalls` list |
| `AddExporterResponse` | New — returned by `add_exporter` |
| `InstalledExporter` | New — item in `get_table_exporters` list |
| `RunEnrichmentResponse` | New — returned by `run_table_enrichment` |
| `Exporter` / `ExporterDetail` / `ExporterListResponse` | New |
| `ExporterParam` / `ExporterResponseField` | New |
| `Connection` / `AuthorizationInfo` | New |
| `Connector` / `NameValue` | New |
| `Folder` | New |

#### Breaking changes

- `add_enrichment` return type changed from `TableEnrichment` (fields: `id`,
  `name`) to `AddEnrichmentResponse` (fields: `id`, `enrichment_name`). Update
  any code that reads `.name` from the result to use `.enrichment_name`.
- `run_table_enrichment` return type changed from `Any` to `RunEnrichmentResponse`.
  The new type is a superset, but typed code accessing raw dict keys will break.

---

## [2.0.0] — 2026-03-06

### Complete rewrite — targets `api.databar.ai/v1`

This is a full rewrite of the package. The previous `0.x` versions targeted
the legacy `api.databar.ai/v2` and `v3` endpoints which are no longer the
primary API. Version 1.0.0 is not backwards compatible.

#### What's new

- **New API target:** All calls now go to `https://api.databar.ai/v1`
- **Full endpoint coverage:** All 19 API endpoints are implemented
  - User: `get_user`
  - Enrichments: list, get, run, bulk-run, param choices
  - Waterfalls: list, get, run, bulk-run
  - Tasks: get, poll
  - Tables: create, list, get columns, get enrichments, add enrichment, run enrichment
  - Rows: get, insert, patch, upsert
- **Pydantic v2 models** sourced directly from the OpenAPI spec
- **Typed exceptions** for every error condition (auth, credits, not found, gone, timeout, etc.)
- **Exponential backoff retry** (3 attempts, skips 4xx except 429)
- **Async task polling** with configurable timeout (150 attempts × 2s default)
- **Auto-batching** for row operations — transparently splits large inserts/patches/upserts into chunks of 50
- **Sync convenience wrappers** — `run_enrichment_sync`, `run_waterfall_sync`, etc. submit and poll in one call
- **New CLI** — `databar` command available after `pip install`
  - `databar login` / `databar whoami`
  - `databar enrich list/get/run/bulk/choices`
  - `databar waterfall list/get/run/bulk`
  - `databar table list/create/columns/rows/insert/patch/upsert/enrichments/add-enrichment/run-enrichment`
  - `databar task get --poll`
  - Output formats: `table` (rich), `json`, `csv`
- **API key resolution:** env var `DATABAR_API_KEY` → `~/.databar/config` → helpful error

#### Breaking changes from 0.x

- `Connection` class removed — use `DatabarClient` instead
- `make_request(endpoint_id, params)` removed — use specific methods like `run_enrichment_sync(id, params)`
- API key is now `x-apikey` header (was different in legacy API)
- All response shapes updated to match v1 API

#### Migration from 0.x

```python
# Before (0.x)
import databar
conn = databar.Connection(api_key="...")
result = conn.make_request("some-endpoint-id", params, fmt="json")

# After (1.0)
from databar import DatabarClient
client = DatabarClient(api_key="...")
result = client.run_enrichment_sync(123, params)
```

---

## [0.7.0] and earlier

Legacy versions targeting the old `v2`/`v3` API. See git history for details.


### Complete rewrite — targets `api.databar.ai/v1`

This is a full rewrite of the package. The previous `0.x` versions targeted
the legacy `api.databar.ai/v2` and `v3` endpoints which are no longer the
primary API. Version 1.0.0 is not backwards compatible.

#### What's new

- **New API target:** All calls now go to `https://api.databar.ai/v1`
- **Full endpoint coverage:** All 19 API endpoints are implemented
  - User: `get_user`
  - Enrichments: list, get, run, bulk-run, param choices
  - Waterfalls: list, get, run, bulk-run
  - Tasks: get, poll
  - Tables: create, list, get columns, get enrichments, add enrichment, run enrichment
  - Rows: get, insert, patch, upsert
- **Pydantic v2 models** sourced directly from the OpenAPI spec
- **Typed exceptions** for every error condition (auth, credits, not found, gone, timeout, etc.)
- **Exponential backoff retry** (3 attempts, skips 4xx except 429)
- **Async task polling** with configurable timeout (150 attempts × 2s default)
- **Auto-batching** for row operations — transparently splits large inserts/patches/upserts into chunks of 50
- **Sync convenience wrappers** — `run_enrichment_sync`, `run_waterfall_sync`, etc. submit and poll in one call
- **New CLI** — `databar` command available after `pip install`
  - `databar login` / `databar whoami`
  - `databar enrich list/get/run/bulk/choices`
  - `databar waterfall list/get/run/bulk`
  - `databar table list/create/columns/rows/insert/patch/upsert/enrichments/add-enrichment/run-enrichment`
  - `databar task get --poll`
  - Output formats: `table` (rich), `json`, `csv`
- **API key resolution:** env var `DATABAR_API_KEY` → `~/.databar/config` → helpful error

#### Breaking changes from 0.x

- `Connection` class removed — use `DatabarClient` instead
- `make_request(endpoint_id, params)` removed — use specific methods like `run_enrichment_sync(id, params)`
- API key is now `x-apikey` header (was different in legacy API)
- All response shapes updated to match v1 API

#### Migration from 0.x

```python
# Before (0.x)
import databar
conn = databar.Connection(api_key="...")
result = conn.make_request("some-endpoint-id", params, fmt="json")

# After (1.0)
from databar import DatabarClient
client = DatabarClient(api_key="...")
result = client.run_enrichment_sync(123, params)
```

---

## [0.7.0] and earlier

Legacy versions targeting the old `v2`/`v3` API. See git history for details.
