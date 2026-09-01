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
    DatabarError,
    DatabarConflictError,
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
    flow_version_payload,
    flow_detail_payload,
    BASE_URL,
    enrichment_payload,
    enrichment_summary_payload,
    flow_payload,
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
# Flows
# ===========================================================================


def test_list_flows(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows", json=[flow_payload()])
    result = client.list_flows()
    assert len(result) == 1
    assert result[0].id == "flow-uuid-1"
    assert result[0].identifier == "flow-uuid-1"
    assert result[0].inputs[0].id == "email"


def test_get_flow(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows/flow-uuid-1", json=flow_payload())
    f = client.get_flow("flow-uuid-1")
    assert f.name == "Find buyer"
    assert f.inputs[0].required is True


def test_run_flow_returns_task(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows/flow-uuid-1/run", json=task_payload("processing"))
    task = client.run_flow("flow-uuid-1", {"email": "alice@example.com"})
    assert task.task_id == "task-123"
    req = httpx_mock.get_requests()[-1]
    body = json.loads(req.content)
    assert body == {"inputs": {"email": "alice@example.com"}}


def test_run_flow_sync(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows/flow-uuid-1/run", json=task_payload("processing"))
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/task-123", json=task_payload("completed", data={"full_name": "Alice"}))
    result = client.run_flow_sync("flow-uuid-1", {"email": "alice@example.com"})
    assert result == {"full_name": "Alice"}


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


# ---------------------------------------------------------------------------
# Flow editing
# ---------------------------------------------------------------------------


def test_get_flow_exposes_the_graph_and_edit_token(client: DatabarClient, httpx_mock: HTTPXMock):
    """Without config + internal_version a caller cannot read-modify-write at all."""
    httpx_mock.add_response(url=f"{BASE_URL}/flows/flow-uuid-1", json=flow_detail_payload())
    f = client.get_flow("flow-uuid-1")
    assert f.internal_version == "uuid-token-1"
    assert f.config["nodes"][0]["id"] == "m1"


def test_create_flow_posts_the_config(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows", json=flow_detail_payload(), method="POST")
    f = client.create_flow(name="Made by SDK", config={"inputs": [], "nodes": []})
    assert f.id == "flow-uuid-1"
    body = json.loads(httpx_mock.get_requests()[-1].content)
    assert body == {"name": "Made by SDK", "config": {"inputs": [], "nodes": []}, "description": ""}


def test_create_flow_is_not_retried_on_a_server_error(client: DatabarClient, httpx_mock: HTTPXMock):
    """A 5xx can land after the flow was created; retrying would make a second one."""
    httpx_mock.add_response(url=f"{BASE_URL}/flows", method="POST", status_code=500, json={"detail": "boom"})
    with pytest.raises(DatabarError):
        client.create_flow(name="x", config={"nodes": []})
    assert len([r for r in httpx_mock.get_requests() if r.method == "POST"]) == 1


def test_replace_flow_sends_the_concurrency_token(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows/flow-uuid-1", json=flow_detail_payload(), method="PUT")
    client.replace_flow("flow-uuid-1", name="N", config={"nodes": []}, internal_version="uuid-token-1")
    body = json.loads(httpx_mock.get_requests()[-1].content)
    assert body["internal_version"] == "uuid-token-1"


def test_update_flow_sends_only_what_was_passed(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/flows/flow-uuid-1", json=flow_detail_payload(), method="PATCH")
    client.update_flow("flow-uuid-1", name="Renamed")
    body = json.loads(httpx_mock.get_requests()[-1].content)
    assert body == {"name": "Renamed"}


def test_patch_flow_config_sends_the_op_batch(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1/config",
        method="PATCH",
        json={"valid": True, "errors": [], "config": {"nodes": []}, "flow": flow_detail_payload()},
    )
    result = client.patch_flow_config("flow-uuid-1", [{"op": "remove_node", "node_id": "m1"}])
    assert result.valid is True
    assert result.flow is not None and result.flow.id == "flow-uuid-1"
    body = json.loads(httpx_mock.get_requests()[-1].content)
    assert body == {"ops": [{"op": "remove_node", "node_id": "m1"}], "validate_only": False}


def test_patch_flow_config_validate_only_returns_no_flow(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1/config",
        method="PATCH",
        json={"valid": False, "errors": ["Node m1: unknown output"], "config": {"nodes": []}, "flow": None},
    )
    result = client.patch_flow_config("flow-uuid-1", [{"op": "remove_node", "node_id": "m1"}], validate_only=True)
    assert result.valid is False
    assert result.flow is None
    assert result.errors == ["Node m1: unknown output"]


def test_delete_flow_blocked_by_a_column_raises_conflict(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1",
        method="DELETE",
        status_code=409,
        json={"detail": "Flow is attached to table columns."},
    )
    with pytest.raises(DatabarConflictError) as exc:
        client.delete_flow("flow-uuid-1")
    assert "attached to table columns" in exc.value.message


def test_list_flow_versions_newest_first(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1/versions?page=1&limit=50",
        json=[flow_version_payload(2, changed_fields=["ui"]), flow_version_payload(1)],
    )
    versions = client.list_flow_versions("flow-uuid-1")
    assert [v.number for v in versions] == [2, 1]
    # A canvas-only move must be distinguishable from a graph edit.
    assert versions[0].changed_fields == ["ui"]
    assert versions[0].source == "api"


def test_get_flow_version_carries_the_stored_graph(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1/versions/1",
        json={**flow_version_payload(1), "config": {"nodes": [{"id": "old"}]}, "ui": {}},
    )
    version = client.get_flow_version("flow-uuid-1", 1)
    assert version.config["nodes"][0]["id"] == "old"


def test_restore_returns_the_version_the_rollback_created(client: DatabarClient, httpx_mock: HTTPXMock):
    """A rollback adds a version rather than rewriting history, so the number differs."""
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1/versions/1/restore",
        method="POST",
        json={"flow": flow_detail_payload(), "version": flow_version_payload(3, restored_from=1)},
    )
    result = client.restore_flow_version("flow-uuid-1", 1)
    assert result.version.number == 3
    assert result.version.restored_from == 1
    assert result.flow.internal_version == "uuid-token-1"


def test_stale_token_on_restore_raises_conflict(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/flows/flow-uuid-1/versions/1/restore",
        method="POST",
        status_code=409,
        json={"detail": "This flow was modified by someone else."},
    )
    with pytest.raises(DatabarConflictError):
        client.restore_flow_version("flow-uuid-1", 1, internal_version="stale")
