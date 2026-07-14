# Changelog

All notable changes to the Databar Python SDK are documented here.

---

## [Unreleased]

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
