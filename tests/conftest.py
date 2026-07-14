"""
Shared test fixtures for the Databar SDK test suite.
Uses pytest-httpx to mock at the HTTP transport level.
"""

from __future__ import annotations

import pytest
import httpx
from pytest_httpx import HTTPXMock

from databar.client import DatabarClient


TEST_API_KEY = "test-key-abc123"
BASE_URL = "https://api.databar.ai/v1"


@pytest.fixture
def http_mock(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Re-export pytest-httpx mock with no changes — kept for clarity."""
    return httpx_mock


@pytest.fixture
def client(httpx_mock: HTTPXMock) -> DatabarClient:
    """Return a DatabarClient wired to the test API key."""
    return DatabarClient(api_key=TEST_API_KEY, poll_interval_s=0.01)


# ---------------------------------------------------------------------------
# Response factory helpers
# ---------------------------------------------------------------------------

def user_payload(**overrides) -> dict:
    return {
        "first_name": "Alice",
        "email": "alice@example.com",
        "balance": 100.0,
        "plan": "pro",
        **overrides,
    }


def enrichment_summary_payload(id: int = 1, **overrides) -> dict:
    return {
        "id": id,
        "name": "Test Enrichment",
        "description": "A test enrichment",
        "data_source": "test-source",
        "price": 0.5,
        "auth_method": "apikey",
        **overrides,
    }


def enrichment_payload(id: int = 1, **overrides) -> dict:
    return {
        **enrichment_summary_payload(id=id),
        "params": [
            {
                "name": "email",
                "is_required": True,
                "type_field": "text",
                "description": "Email address",
                "choices": None,
            }
        ],
        "response_fields": [
            {"name": "name", "type_field": "text"},
        ],
        **overrides,
    }


def enrichment_list_response_payload(page: int = 1, items: list | None = None, **overrides) -> dict:
    return {
        "items": items if items is not None else [enrichment_summary_payload(1), enrichment_summary_payload(2)],
        "page": page,
        "limit": 50,
        "has_next_page": False,
        "total_count": 2,
        **overrides,
    }


def task_payload(status: str = "processing", task_id: str = "task-123", data=None) -> dict:
    return {
        "task_id": task_id,
        "status": status,
        "data": data,
        "error": None,
    }


def table_payload(identifier: str = "tbl-uuid-1", **overrides) -> dict:
    return {
        "identifier": identifier,
        "name": "My Table",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        **overrides,
    }


def column_payload(identifier: str = "col-uuid-1", **overrides) -> dict:
    return {
        "identifier": identifier,
        "internal_name": "abc123",
        "name": "Email",
        "type_of_value": "text",
        "data_processor_id": None,
        **overrides,
    }


def waterfall_payload(identifier: str = "email_getter", **overrides) -> dict:
    return {
        "identifier": identifier,
        "name": "Email Getter",
        "description": "Find email addresses",
        "input_params": [{"name": "linkedin_url", "type": "text", "required": True}],
        "output_fields": [{"name": "email", "label": "Email", "type": "text"}],
        "available_enrichments": [
            {"id": 10, "name": "Provider A", "description": "", "price": "0.1", "params": ["linkedin_url"]},
            {"id": 11, "name": "Provider B", "description": "", "price": "0.2", "params": ["linkedin_url"]},
        ],
        "is_email_verifying": False,
        "email_verifiers": [],
        **overrides,
    }


def flow_payload(flow_id: str = "flow-uuid-1", **overrides) -> dict:
    return {
        "id": flow_id,
        "name": "Find buyer",
        "description": "Enrich a lead through several steps",
        "inputs": [
            {"id": "email", "description": "Email address", "type": "text", "required": True}
        ],
        "outputs": [{"id": "full_name", "response_field_id": 7}],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        **overrides,
    }


def exporter_payload(id: int = 1, **overrides) -> dict:
    return {
        "id": id,
        "name": "Google Sheets",
        "description": "Push data to Google Sheets",
        "dataset": 42,
        **overrides,
    }


def exporter_detail_payload(id: int = 1, **overrides) -> dict:
    return {
        **exporter_payload(id=id),
        "params": [
            {
                "name": "spreadsheet_url",
                "is_required": True,
                "type_field": "text",
                "description": "Google Sheets URL",
                "choices": None,
            }
        ],
        "response_fields": [
            {"name": "status", "display_name": "Status", "type_field": "text"},
        ],
        "authorization": {"required": False, "connections": []},
        **overrides,
    }


def exporter_list_response_payload(page: int = 1, **overrides) -> dict:
    return {
        "items": [exporter_payload(1), exporter_payload(2)],
        "page": page,
        "limit": 50,
        "has_next_page": False,
        "total_count": 2,
        **overrides,
    }


def connector_payload(id: int = 1, **overrides) -> dict:
    return {
        "id": id,
        "name": "My Scoring API",
        "type": "enrichment",
        "method": "post",
        "url": "https://api.example.com/v1/score",
        "headers": [{"name": "Authorization", "value": "Bearer sk-xxx"}],
        "parameters": [],
        "body": [{"name": "domain", "value": ""}],
        "body_template": None,
        "rate_limit": 60,
        "max_concurrency": 5,
        "created_at": "2025-01-15T10:30:00Z",
        **overrides,
    }


def folder_payload(id: int = 1, **overrides) -> dict:
    return {
        "id": id,
        "name": "My Folder",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "table_count": 3,
        **overrides,
    }
