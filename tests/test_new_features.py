"""
Tests for features added in v2.1: pagination, new table operations,
exporters, connectors, folders and updated polling behavior.
"""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from databar.client import DatabarClient
from databar.exceptions import (
    DatabarError,
    DatabarGoneError,
    DatabarTaskCancelledError,
    DatabarTaskFailedError,
)
from databar.models import (
    AddEnrichmentResponse,
    AddExporterResponse,
    AddWaterfallResponse,
    Connector,
    CreateColumnResponse,
    Enrichment,
    EnrichmentListResponse,
    ExporterDetail,
    ExporterListResponse,
    Folder,
    InstalledExporter,
    InstalledWaterfall,
    RunEnrichmentResponse,
    Table,
)

from .conftest import (
    BASE_URL,
    column_payload,
    connector_payload,
    enrichment_list_response_payload,
    enrichment_payload,
    enrichment_summary_payload,
    exporter_detail_payload,
    exporter_list_response_payload,
    exporter_payload,
    folder_payload,
    table_payload,
    task_payload,
    waterfall_payload,
)


# ===========================================================================
# Task polling — new statuses
# ===========================================================================


def test_poll_task_partially_completed(client: DatabarClient, httpx_mock: HTTPXMock):
    """partially_completed should be treated as success and return data."""
    httpx_mock.add_response(
        url=f"{BASE_URL}/tasks/t1",
        json=task_payload("partially_completed", task_id="t1", data=[{"row": 1}]),
    )
    result = client.poll_task("t1")
    assert result == [{"row": 1}]


def test_poll_task_no_data_continues(client: DatabarClient, httpx_mock: HTTPXMock):
    """no_data status should keep polling until completed."""
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/t1", json=task_payload("no_data", task_id="t1"))
    httpx_mock.add_response(url=f"{BASE_URL}/tasks/t1", json=task_payload("completed", task_id="t1", data={"k": "v"}))
    result = client.poll_task("t1")
    assert result == {"k": "v"}


def test_poll_task_gone_raises(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/tasks/t1",
        json={"task_id": "t1", "status": "gone", "data": None, "error": None},
    )
    with pytest.raises(DatabarGoneError):
        client.poll_task("t1")


def test_poll_task_cancelled_raises_with_partial_data(client: DatabarClient, httpx_mock: HTTPXMock):
    """A cancelled bulk run returns only the rows that finished, so it can't be joined
    back by position — hand it over as partial_data rather than as a normal result."""
    httpx_mock.add_response(
        url=f"{BASE_URL}/tasks/t1",
        json=task_payload("cancelled", task_id="t1", data=[{"row": 1}]),
    )
    with pytest.raises(DatabarTaskCancelledError) as exc_info:
        client.poll_task("t1")
    assert exc_info.value.partial_data == [{"row": 1}]
    assert exc_info.value.task_id == "t1"


def test_get_task_exposes_bulk_progress(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/tasks/t1",
        json=task_payload(
            "processing",
            task_id="t1",
            progress={"total": 10, "completed": 4, "failed": 1, "processing": 5},
        ),
    )
    task = client.get_task("t1")
    assert task.progress == {"total": 10, "completed": 4, "failed": 1, "processing": 5}


def test_get_task_partial_is_opt_in(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/tasks/t1?include_partial=true",
        json=task_payload("processing", task_id="t1", data=[{"row": 1}]),
    )
    assert client.get_task("t1", include_partial=True).data == [{"row": 1}]


def test_cancel_task(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/tasks/t1/cancel",
        json=task_payload("cancelled", task_id="t1"),
    )
    assert client.cancel_task("t1").status == "cancelled"


def test_cancel_task_of_a_finished_task_raises(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/tasks/t1/cancel",
        status_code=409,
        json={"detail": "Task has already finished"},
    )
    with pytest.raises(DatabarError):
        client.cancel_task("t1")


# ===========================================================================
# Enrichments — pagination
# ===========================================================================


def test_list_enrichments_paginated(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(json=enrichment_list_response_payload(page=1))
    result = client.list_enrichments(page=1, limit=50)
    assert isinstance(result, EnrichmentListResponse)
    assert result.page == 1
    assert result.total_count == 2
    assert len(result.items) == 2


def test_list_enrichments_paginated_query_params(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(json=enrichment_list_response_payload())
    client.list_enrichments(page=2, limit=100, q="email", authorized_only=False, category="Company Data")
    req = httpx_mock.get_requests()[0]
    url_str = str(req.url)
    assert "page=2" in url_str
    assert "limit=100" in url_str
    assert "q=email" in url_str
    assert "authorized_only=false" in url_str
    assert "category=Company+Data" in url_str or "category=Company%20Data" in url_str or "category=Company Data" in url_str


def test_list_enrichments_plain_without_page(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/", json=[enrichment_summary_payload(1)])
    result = client.list_enrichments()
    assert isinstance(result, list)
    assert len(result) == 1
def test_enrichment_summary_with_pricing_and_category(client: DatabarClient, httpx_mock: HTTPXMock):
    payload = enrichment_summary_payload(
        1,
        pricing={"type": "per_parameter", "parameter": "limit"},
        category=[{"id": 1, "name": "Company Data"}],
    )
    httpx_mock.add_response(json=[payload])
    result = client.list_enrichments()
    e = result[0]
    assert e.pricing is not None
    assert e.pricing.type == "per_parameter"
    assert e.pricing.parameter == "limit"
    assert len(e.category) == 1
    assert e.category[0].name == "Company Data"


def test_run_enrichment_with_pagination(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/1/run", json=task_payload("processing"))
    client.run_enrichment(1, {"query": "test"}, pages=3)
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert body["pagination"] == {"pages": 3}


def test_run_enrichment_no_pagination_field_when_one_page(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/enrichments/1/run", json=task_payload("processing"))
    client.run_enrichment(1, {"query": "test"})
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert "pagination" not in body


# ===========================================================================
# Tables — new CRUD operations
# ===========================================================================


def test_delete_table(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1", status_code=200, json={"status": "deleted"})
    client.delete_table("tbl-1")
    assert len(httpx_mock.get_requests()) == 1


def test_rename_table(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1", json=table_payload("tbl-1", name="New Name"))
    result = client.rename_table("tbl-1", "New Name")
    assert isinstance(result, Table)
    assert result.name == "New Name"
    req = httpx_mock.get_requests()[0]
    assert json.loads(req.content)["name"] == "New Name"


def test_create_table_sends_rows_field(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/create", json=table_payload())
    client.create_table(name="T", rows=5)
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["rows"] == 5
    assert body["name"] == "T"


# ===========================================================================
# Tables — Columns
# ===========================================================================


def test_create_column(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/columns",
        json={"identifier": "col-1", "name": "Phone", "type_of_value": "text"},
    )
    result = client.create_column("tbl-1", "Phone", type="text")
    assert isinstance(result, CreateColumnResponse)
    assert result.identifier == "col-1"
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert body["name"] == "Phone"
    assert body["type"] == "text"


def test_rename_column(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/columns/col-1",
        json={"identifier": "col-1", "name": "Mobile", "type_of_value": "text"},
    )
    result = client.rename_column("tbl-1", "col-1", "Mobile")
    assert isinstance(result, CreateColumnResponse)
    assert result.name == "Mobile"


def test_delete_column(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/columns/col-1", json={"status": "deleted"})
    client.delete_column("tbl-1", "col-1")
    assert len(httpx_mock.get_requests()) == 1


# ===========================================================================
# Tables — Enrichments (updated behavior)
# ===========================================================================


def test_add_enrichment_returns_response(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/add-enrichment",
        json={"id": 42, "enrichment_name": "Email Enrichment"},
    )
    result = client.add_enrichment("tbl-1", 1, {"email": {"type": "simple", "value": "test@x.com"}})
    assert isinstance(result, AddEnrichmentResponse)
    assert result.id == 42
    assert result.enrichment_name == "Email Enrichment"


def test_add_enrichment_sends_launch_strategy(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/add-enrichment",
        json={"id": 1, "enrichment_name": "Test"},
    )
    client.add_enrichment(
        "tbl-1", 1,
        {"email": {"type": "simple", "value": "a@b.com"}},
        launch_strategy="run_on_update",
    )
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["launch_strategy"] == "run_on_update"


def test_run_table_enrichment_sends_body(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/run-enrichment/42",
        json={"status": "queued", "processing_rows": 10},
    )
    result = client.run_table_enrichment("tbl-1", "42", run_strategy="run_empty", row_ids=["r1", "r2"])
    assert isinstance(result, RunEnrichmentResponse)
    assert result.status == "queued"
    assert result.processing_rows == 10
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["run_strategy"] == "run_empty"
    assert body["row_ids"] == ["r1", "r2"]


# ===========================================================================
# Tables — Waterfalls
# ===========================================================================


def test_add_waterfall(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/add-waterfall",
        json={"id": 55, "waterfall_name": "Email Finder"},
    )
    result = client.add_waterfall(
        "tbl-1",
        waterfall_identifier="email_getter",
        enrichments=[833, 966],
        mapping={"first_name": "first_name", "company": "company"},
        email_verifier=10,
    )
    assert isinstance(result, AddWaterfallResponse)
    assert result.id == 55
    assert result.waterfall_name == "Email Finder"
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["waterfall"] == "email_getter"
    assert body["enrichments"] == [833, 966]
    assert body["email_verifier"] == 10


def test_get_table_waterfalls(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/waterfalls",
        json=[{"id": 55, "waterfall_name": "Email Finder"}],
    )
    result = client.get_table_waterfalls("tbl-1")
    assert len(result) == 1
    assert isinstance(result[0], InstalledWaterfall)
    assert result[0].id == 55


# ===========================================================================
# Tables — Exporters
# ===========================================================================


def test_add_exporter(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/add-exporter",
        json={"id": 7, "exporter_name": "HubSpot CRM"},
    )
    result = client.add_exporter(
        "tbl-1",
        exporter_id=1,
        mapping={"email": {"type": "mapping", "value": "email_col"}},
        launch_strategy="run_on_click",
    )
    assert isinstance(result, AddExporterResponse)
    assert result.id == 7
    assert result.exporter_name == "HubSpot CRM"


def test_get_table_exporters(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-1/exporters",
        json=[{"id": 7, "name": "HubSpot CRM"}],
    )
    result = client.get_table_exporters("tbl-1")
    assert len(result) == 1
    assert isinstance(result[0], InstalledExporter)
    assert result[0].name == "HubSpot CRM"


# ===========================================================================
# Rows — new operations
# ===========================================================================


def test_delete_rows(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/table/tbl-1/rows/delete", json={"status": "deleted"})
    client.delete_rows("tbl-1", ["row-1", "row-2"])
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert body["row_ids"] == ["row-1", "row-2"]


def test_get_rows_with_filter(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={"data": [{"id": "r1", "email": "alice@example.com"}], "has_next_page": False, "total_count": 1, "page": 1},
    )
    resp = client.get_rows("tbl-1", filter='{"email":{"contains":"alice"}}')
    assert len(resp.data) == 1
    req = httpx_mock.get_requests()[0]
    assert "filter=" in str(req.url)


# ===========================================================================
# Exporters
# ===========================================================================


def test_list_exporters_plain(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/exporters/", json=[exporter_payload(1), exporter_payload(2)])
    result = client.list_exporters()
    assert isinstance(result, list)
    assert len(result) == 2


def test_list_exporters_paginated(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(json=exporter_list_response_payload(page=1))
    result = client.list_exporters(page=1, limit=50)
    assert isinstance(result, ExporterListResponse)
    assert result.total_count == 2
    assert len(result.items) == 2


def test_get_exporter(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/exporters/1", json=exporter_detail_payload(1))
    result = client.get_exporter(1)
    assert isinstance(result, ExporterDetail)
    assert result.id == 1
    assert len(result.params) == 1
    assert result.authorization.required is False


# ===========================================================================
# Connectors
# ===========================================================================


def test_list_connectors(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/connectors/", json=[connector_payload(1)])
    result = client.list_connectors()
    assert len(result) == 1
    assert isinstance(result[0], Connector)
    assert result[0].method == "post"


def test_get_connector(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/connectors/1", json=connector_payload(1))
    result = client.get_connector(1)
    assert isinstance(result, Connector)
    assert result.name == "My Scoring API"


def test_create_connector(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/connectors/", status_code=201, json=connector_payload(42))
    result = client.create_connector(
        name="My Scoring API",
        method="post",
        url="https://api.example.com/v1/score",
        headers=[{"name": "Authorization", "value": "Bearer sk-xxx"}],
        rate_limit=60,
    )
    assert isinstance(result, Connector)
    assert result.id == 42
    req = httpx_mock.get_requests()[0]
    body = json.loads(req.content)
    assert body["name"] == "My Scoring API"
    assert body["method"] == "post"
    assert body["rate_limit"] == 60


def test_update_connector(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/connectors/1", json=connector_payload(1, name="Updated API"))
    result = client.update_connector(1, name="Updated API", method="get", url="https://api.example.com")
    assert result.name == "Updated API"
    req = httpx_mock.get_requests()[0]
    assert req.method == "PUT"


def test_delete_connector(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/connectors/1", status_code=204)
    client.delete_connector(1)
    req = httpx_mock.get_requests()[0]
    assert req.method == "DELETE"


# ===========================================================================
# Folders
# ===========================================================================


def test_create_folder(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/folders", json=folder_payload(1, name="My Leads"))
    result = client.create_folder("My Leads")
    assert isinstance(result, Folder)
    assert result.name == "My Leads"
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["name"] == "My Leads"


def test_list_folders(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/folders", json=[folder_payload(1), folder_payload(2)])
    result = client.list_folders()
    assert len(result) == 2
    assert all(isinstance(f, Folder) for f in result)


def test_rename_folder(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/folders/1", json=folder_payload(1, name="Renamed"))
    result = client.rename_folder(1, "Renamed")
    assert result.name == "Renamed"
    req = httpx_mock.get_requests()[0]
    assert req.method == "PATCH"
    assert json.loads(req.content)["name"] == "Renamed"


def test_delete_folder(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/folders/1", json={"status": "deleted"})
    client.delete_folder(1)
    req = httpx_mock.get_requests()[0]
    assert req.method == "DELETE"


def test_move_table_to_folder(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/folders/move-table", json={"status": "moved"})
    result = client.move_table_to_folder("tbl-uuid-1", folder_id=1)
    assert result["status"] == "moved"
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["table_uuid"] == "tbl-uuid-1"
    assert body["folder_id"] == 1


def test_move_table_out_of_folder(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/folders/move-table", json={"status": "moved"})
    client.move_table_to_folder("tbl-uuid-1")
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert "folder_id" not in body


# ===========================================================================
# User — workspace field
# ===========================================================================


def test_get_user_with_workspace(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/user/me",
        json={"first_name": "Alice", "email": "a@x.com", "balance": 50.0, "plan": "pro", "workspace": "ws-uuid"},
    )
    user = client.get_user()
    assert user.workspace == "ws-uuid"
