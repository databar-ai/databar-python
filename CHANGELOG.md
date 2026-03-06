# Changelog

All notable changes to the Databar Python SDK are documented here.

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
