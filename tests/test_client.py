"""
Unit tests for DatabarClient.

Tests mock at the HTTP transport level using pytest-httpx so no real
network calls are made.
"""

from __future__ import annotations

import json

import pytest
import httpx
from pytest_httpx import HTTPXMock

from databar.client import DatabarClient, _ROW_BATCH_SIZE, _MAX_RETRY_ATTEMPTS as _MAX_RETRIES
from databar.exceptions import (
    DatabarAuthError,
    DatabarGoneError,
    DatabarInsufficientCreditsError,
    DatabarNotFoundError,
    DatabarRateLimitError,
    DatabarTaskFailedError,
    DatabarTimeoutError,
    DatabarValidationError,
)
from databar.models import (
    BatchInsertResponse,
    BatchUpdateResponse,
    BatchUpdateRow,
    InsertRow,
    RunResponse,
    UpsertResponse,
    UpsertRow,
)

from .conftest import (
    BASE_URL,
    enrichment_payload,
    enrichment_summary_payload,
    table_payload,
    task_payload,
    user_payload,
    waterfall_payload,
)


# ===========================================================================
# Construction / auth
# ===========================================================================


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("DATABAR_API_KEY", raising=False)
    with pytest.raises(DatabarAuthError):
        DatabarClient(api_key=None)


def test_client_reads_env_var(monkeypatch):
    monkeypatch.setenv("DATABAR_API_KEY", "env-key")
    c = DatabarClient()
    assert c._api_key == "env-key"
    c.close()


def test_client_context_manager(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/user/me", json=user_payload())
    with DatabarClient(api_key="key") as c:
        user = c.get_user()
    assert user.email == "alice@example.com"


# ===========================================================================
# Error handling
# ===========================================================================


@pytest.mark.parametrize("status,exc_cls", [
    (401, DatabarAuthError),
    (403, DatabarAuthError),
    (404, DatabarNotFoundError),
    (406, DatabarInsufficientCreditsError),
    (410, DatabarGoneError),
    (422, DatabarValidationError),
    (429, DatabarRateLimitError),
])
def test_http_error_mapping(client: DatabarClient, httpx_mock: HTTPXMock, status, exc_cls):
    body = {"detail": "error"} if status != 422 else {"detail": [{"loc": ["body", "params"], "msg": "required", "type": "missing"}]}
    # 429 is retried — register enough responses for all retry attempts
    for _ in range(_MAX_RETRIES if status == 429 else 1):
        httpx_mock.add_response(url=f"{BASE_URL}/user/me", status_code=status, json=body)
    with pytest.raises(exc_cls):
        client.get_user()


def test_retry_on_500(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/user/me", status_code=500, json={"detail": "oops"})
    httpx_mock.add_response(url=f"{BASE_URL}/user/me", status_code=500, json={"detail": "oops"})
    httpx_mock.add_response(url=f"{BASE_URL}/user/me", json=user_payload())
    user = client.get_user()
    assert user.email == "alice@example.com"


def test_no_retry_on_404(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/999", status_code=404, json={"detail": "not found"})
    with pytest.raises(DatabarNotFoundError):
        client.get_enrichment(999)
    assert len(httpx_mock.get_requests()) == 1


# ===========================================================================
# User
# ===========================================================================


def test_get_user(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/user/me", json=user_payload())
    user = client.get_user()
    assert user.email == "alice@example.com"
    assert user.balance == 100.0
    assert user.plan == "pro"


# ===========================================================================
# Enrichments
# ===========================================================================


def test_list_enrichments(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/", json=[enrichment_summary_payload(1), enrichment_summary_payload(2)])
    result = client.list_enrichments()
    assert len(result) == 2
    assert result[0].id == 1


def test_list_enrichments_with_query(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(json=[enrichment_summary_payload()])
    client.list_enrichments(q="linkedin")
    req = httpx_mock.get_requests()[0]
    assert "q=linkedin" in str(req.url)


def test_get_enrichment(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/1", json=enrichment_payload(1))
    e = client.get_enrichment(1)
    assert e.id == 1
    assert e.params is not None
    assert e.params[0].name == "email"


def test_run_enrichment_returns_task(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/1/run", json=task_payload("processing"))
    task = client.run_enrichment(1, {"email": "test@example.com"})
    assert task.task_id == "task-123"
    assert task.status == "processing"


def test_run_enrichment_sync(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/1/run", json=task_payload("processing"))
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/task-123", json=task_payload("completed", data={"name": "Alice"}))
    result = client.run_enrichment_sync(1, {"email": "test@example.com"})
    assert result == {"name": "Alice"}


def test_run_enrichment_sync_failed(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/1/run", json=task_payload("processing"))
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/task-123", json={"task_id": "task-123", "status": "failed", "data": None, "error": "upstream error"})
    with pytest.raises(DatabarTaskFailedError, match="upstream error"):
        client.run_enrichment_sync(1, {"email": "test@example.com"})


def test_poll_task_timeout(httpx_mock: HTTPXMock):
    c = DatabarClient(api_key="key", max_poll_attempts=2, poll_interval_s=0.001)
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/t1", json=task_payload("processing", task_id="t1"))
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/t1", json=task_payload("processing", task_id="t1"))
    with pytest.raises(DatabarTimeoutError):
        c.poll_task("t1")
    c.close()


# ===========================================================================
# Waterfalls
# ===========================================================================


def test_list_waterfalls(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/waterfalls/", json=[waterfall_payload()])
    result = client.list_waterfalls()
    assert len(result) == 1
    assert result[0].identifier == "email_getter"


def test_run_waterfall_auto_resolves_providers(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/waterfalls/email_getter", json=waterfall_payload())
    httpx_mock.add_response(url=f"{BASE_URL}/waterfalls/email_getter/run", json=task_payload("processing"))
    task = client.run_waterfall("email_getter", {"linkedin_url": "https://linkedin.com/in/alice"})
    assert task.task_id == "task-123"
    req = httpx_mock.get_requests()[-1]
    body = json.loads(req.content)
    assert body["enrichments"] == [10, 11]


# ===========================================================================
# Tables
# ===========================================================================


def test_create_table(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/create", json=table_payload())
    table = client.create_table(name="My Table")
    assert table.identifier == "tbl-uuid-1"
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert body["name"] == "My Table"


def test_create_table_with_columns(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/create", json=table_payload())
    client.create_table(name="T", columns=["email", "name"])
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert body["columns"] == ["email", "name"]


def test_list_tables(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/", json=[table_payload("t1"), table_payload("t2")])
    tables = client.list_tables()
    assert len(tables) == 2


# ===========================================================================
# Rows — auto-batching
# ===========================================================================


def _insert_response(n: int, offset: int = 0) -> dict:
    return {
        "results": [
            {"index": i, "id": f"row-{i + offset}", "action": "created", "row_data": None}
            for i in range(n)
        ]
    }


def test_create_rows_auto_batches(client: DatabarClient, httpx_mock: HTTPXMock):
    total = _ROW_BATCH_SIZE + 10  # 60 rows → 2 batches
    rows = [InsertRow(fields={"email": f"u{i}@x.com"}) for i in range(total)]

    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows", json=_insert_response(_ROW_BATCH_SIZE))
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows", json=_insert_response(10, offset=_ROW_BATCH_SIZE))

    result = client.create_rows("tbl-1", rows)
    assert isinstance(result, BatchInsertResponse)
    assert len(result.results) == total
    assert len(httpx_mock.get_requests()) == 2


def test_patch_rows_auto_batches(client: DatabarClient, httpx_mock: HTTPXMock):
    total = _ROW_BATCH_SIZE + 5
    rows = [BatchUpdateRow(id=f"row-{i}", fields={"name": f"User {i}"}) for i in range(total)]
    batch_resp = {"results": [{"id": f"row-{i}", "ok": True} for i in range(_ROW_BATCH_SIZE)]}
    small_resp = {"results": [{"id": f"row-{i}", "ok": True} for i in range(5)]}

    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows", json=batch_resp)
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows", json=small_resp)

    result = client.patch_rows("tbl-1", rows)
    assert isinstance(result, BatchUpdateResponse)
    assert len(result.results) == total


def test_upsert_rows_auto_batches(client: DatabarClient, httpx_mock: HTTPXMock):
    total = _ROW_BATCH_SIZE + 3
    rows = [UpsertRow(key={"email": f"u{i}@x.com"}, fields={"name": f"User {i}"}) for i in range(total)]
    batch_resp = {"results": [{"id": f"r{i}", "action": "created", "ok": True} for i in range(_ROW_BATCH_SIZE)]}
    small_resp = {"results": [{"id": f"r{i}", "action": "updated", "ok": True} for i in range(3)]}

    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows/upsert", json=batch_resp)
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows/upsert", json=small_resp)

    result = client.upsert_rows("tbl-1", rows)
    assert isinstance(result, UpsertResponse)
    assert len(result.results) == total
