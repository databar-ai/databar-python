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


def task_payload(status: str = "processing", task_id: str = "task-123", data=None) -> dict:
    return {
        "request_id": task_id,
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
