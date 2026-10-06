"""Workbook, trash and table-operation client methods hit the routes the server serves."""

from __future__ import annotations

import json

from pytest_httpx import HTTPXMock

from databar.client import DatabarClient
from databar.models import DedupeResult, ExportStatus, TrashItem, Workbook

from .conftest import BASE_URL, table_payload


def workbook_payload(identifier: str = "wb_abc12345", **overrides) -> dict:
    return {
        "identifier": identifier,
        "name": "Doc",
        "created_at": "2026-10-06T00:00:00Z",
        "updated_at": "2026-10-06T00:00:00Z",
        "folder_id": None,
        "tables": [{"identifier": "tbl-uuid-1", "name": "Sheet", "position": 0}],
        "tables_count": 1,
        **overrides,
    }


def test_list_and_merge_workbooks(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE_URL}/workbooks", json=[workbook_payload()])
    httpx_mock.add_response(url=f"{BASE_URL}/workbooks/merge", method="POST", json=workbook_payload(tables_count=2))

    workbooks = client.list_workbooks()
    merged = client.merge_workbooks("wb_abc12345", ["wb_other123"])

    assert isinstance(workbooks[0], Workbook)
    assert workbooks[0].tables[0].identifier == "tbl-uuid-1"
    assert merged.tables_count == 2
    assert json.loads(httpx_mock.get_requests()[1].content) == {"target": "wb_abc12345", "sources": ["wb_other123"]}


def test_table_operations(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/duplicate", method="POST", json=table_payload("tbl-copy", workbook="wb_new12345")
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-uuid-1/export", method="POST", json={"status": "waiting", "file_id": 7}
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-uuid-1/rows/dedupe",
        method="POST",
        json={"count_all_rows": 3, "count_rows_delete": 2},
    )

    copy = client.duplicate_table("tbl-uuid-1")
    export = client.export_table("tbl-uuid-1", format="xlsx")
    dedupe = client.dedupe_table_rows("tbl-uuid-1", columns=["col-uuid-1"])

    assert copy.workbook == "wb_new12345"
    assert isinstance(export, ExportStatus) and export.file_id == 7
    assert isinstance(dedupe, DedupeResult) and dedupe.count_rows_delete == 2
    requests = httpx_mock.get_requests()
    assert json.loads(requests[0].content) == {"table": "tbl-uuid-1"}
    assert json.loads(requests[1].content) == {"format": "xlsx"}
    assert json.loads(requests[2].content) == {"columns": ["col-uuid-1"]}


def test_update_enrichment_sends_only_what_changed(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/table/tbl-uuid-1/enrichments/5",
        method="PATCH",
        json={"id": 5, "enrichment_name": "Email finder"},
    )

    client.update_enrichment("tbl-uuid-1", 5, launch_strategy="run_on_update")

    assert json.loads(httpx_mock.get_requests()[0].content) == {"launch_strategy": "run_on_update"}


def test_trash_list_and_restore(client: DatabarClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/trash",
        json=[{"kind": "workbook", "identifier": "wb_abc12345", "name": "Doc", "tables_count": 1}],
    )
    httpx_mock.add_response(url=f"{BASE_URL}/trash/restore", method="POST", json={"status": "ok"})

    items = client.list_trash()
    client.restore_trash(workbooks=["wb_abc12345"])

    assert isinstance(items[0], TrashItem) and items[0].kind == "workbook"
    assert json.loads(httpx_mock.get_requests()[1].content) == {"workbooks": ["wb_abc12345"], "tables": []}
