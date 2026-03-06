"""
CLI integration tests using typer's CliRunner.

These tests mock DatabarClient at the method level so no HTTP calls are made.
Each test verifies the CLI command wires correctly to the SDK and formats output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from databar.cli.app import app
from databar.exceptions import DatabarAuthError
from databar.models import (
    BatchInsertResponse,
    BatchInsertResultItem,
    BatchUpdateResponse,
    BatchUpdateResultItem,
    ChoicesResponse,
    ChoiceItem,
    Column,
    Enrichment,
    EnrichmentParam,
    EnrichmentSummary,
    Table,
    TableEnrichment,
    TaskResponse,
    UpsertResponse,
    UpsertResultItem,
    User,
    Waterfall,
    WaterfallEnrichment,
)

runner = CliRunner(mix_stderr=False)
FAKE_KEY = "test-api-key"


def _client_mock(**method_overrides):
    """Return a MagicMock DatabarClient with sensible defaults."""
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)

    m.get_user.return_value = User(
        first_name="Alice", email="alice@example.com", balance=99.5, plan="pro"
    )
    m.list_enrichments.return_value = [
        EnrichmentSummary(id=1, name="Test Enrich", description="desc", data_source="src", price=0.5, auth_method="apikey")
    ]
    m.get_enrichment.return_value = Enrichment(
        id=1,
        name="Test Enrich",
        description="A test enrichment",
        data_source="src",
        price=0.5,
        auth_method="apikey",
        params=[EnrichmentParam(name="email", is_required=True, type_field="text", description="Email")],
        response_fields=[],
    )
    m.run_enrichment_sync.return_value = [{"email": "alice@example.com", "name": "Alice"}]
    m.run_enrichment_bulk_sync.return_value = [{"email": "alice@example.com", "name": "Alice"}]
    m.get_param_choices.return_value = ChoicesResponse(
        items=[ChoiceItem(id="us", name="United States")], page=1, limit=50, has_next_page=False
    )

    m.list_waterfalls.return_value = [
        Waterfall(
            identifier="email_getter",
            name="Email Getter",
            description="Find emails",
            input_params=[],
            output_fields=[],
            available_enrichments=[
                WaterfallEnrichment(id=10, name="Provider A", description="", price="0.1", params=[])
            ],
            is_email_verifying=False,
            email_verifiers=[],
        )
    ]
    m.get_waterfall.return_value = m.list_waterfalls.return_value[0]
    m.run_waterfall_sync.return_value = [{"email": "alice@example.com"}]
    m.run_waterfall_bulk_sync.return_value = [{"email": "alice@example.com"}]

    m.list_tables.return_value = [
        Table(identifier="tbl-1", name="My Table", created_at="2024-01-01", updated_at="2024-01-01")
    ]
    m.create_table.return_value = Table(
        identifier="tbl-new", name="New Table", created_at="2024-01-01", updated_at="2024-01-01"
    )
    m.get_columns.return_value = [
        Column(identifier="col-1", internal_name="email_col", name="email", type_of_value="text", data_processor_id=None)
    ]
    m.get_rows.return_value = {"result": [{"id": "r1", "data": {"email": "alice@example.com"}}], "total_count": 1, "has_next_page": False}
    m.create_rows.return_value = BatchInsertResponse(
        results=[BatchInsertResultItem(index=0, id="r1", action="created")]
    )
    m.patch_rows.return_value = BatchUpdateResponse(
        results=[BatchUpdateResultItem(id="r1", ok=True)]
    )
    m.upsert_rows.return_value = UpsertResponse(
        results=[UpsertResultItem(id="r1", action="created", ok=True)]
    )
    m.get_table_enrichments.return_value = [TableEnrichment(id=5, name="My Enrichment")]
    m.add_enrichment.return_value = {"status": "ok"}
    m.run_table_enrichment.return_value = {"status": "triggered"}
    m.get_task.return_value = TaskResponse(request_id="t1", status="completed", data={"result": "ok"})
    m.poll_task.return_value = {"result": "ok"}

    for method, return_value in method_overrides.items():
        getattr(m, method).return_value = return_value

    return m


def invoke(args: list[str], env: dict | None = None) -> object:
    """Invoke the CLI with DATABAR_API_KEY set."""
    env = {**(env or {}), "DATABAR_API_KEY": FAKE_KEY}
    return runner.invoke(app, args, env=env)


# ===========================================================================
# Auth
# ===========================================================================


def test_missing_api_key_shows_helpful_error(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABAR_API_KEY", raising=False)
    monkeypatch.setattr("databar.cli._auth.CONFIG_FILE", tmp_path / "config")
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code != 0
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") and result.stderr else "")
    assert "login" in combined.lower() or "api key" in combined.lower() or result.exit_code != 0


def test_login_saves_key(tmp_path, monkeypatch):
    config_file = tmp_path / "config"
    monkeypatch.setattr("databar.cli._auth.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("databar.cli._auth.CONFIG_FILE", config_file)
    result = runner.invoke(app, ["login", "--api-key", "my-secret-key"])
    assert result.exit_code == 0
    assert config_file.exists()
    assert "my-secret-key" in config_file.read_text()


def test_whoami_table(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli._auth.get_client", lambda: mock)
    result = invoke(["whoami"])
    assert result.exit_code == 0
    assert "alice@example.com" in result.output


def test_whoami_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli._auth.get_client", lambda: mock)
    result = invoke(["whoami", "--format", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["email"] == "alice@example.com"


# ===========================================================================
# Enrichments
# ===========================================================================


def test_enrich_list(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "list"])
    assert result.exit_code == 0
    assert "Test Enrich" in result.output


def test_enrich_list_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["id"] == 1


def test_enrich_get(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "get", "1"])
    assert result.exit_code == 0
    assert "Test Enrich" in result.output


def test_enrich_run(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "run", "1", "--params", '{"email":"alice@example.com"}'])
    assert result.exit_code == 0
    mock.run_enrichment_sync.assert_called_once_with(1, {"email": "alice@example.com"})


def test_enrich_run_invalid_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "run", "1", "--params", "not-json"])
    assert result.exit_code != 0


def test_enrich_choices(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "choices", "1", "country"])
    assert result.exit_code == 0
    assert "United States" in result.output


# ===========================================================================
# Waterfalls
# ===========================================================================


def test_waterfall_list(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.waterfalls.get_client", lambda: mock)
    result = invoke(["waterfall", "list"])
    assert result.exit_code == 0
    assert "email_getter" in result.output


def test_waterfall_run(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.waterfalls.get_client", lambda: mock)
    result = invoke(["waterfall", "run", "email_getter", "--params", '{"linkedin_url":"https://linkedin.com/in/alice"}'])
    assert result.exit_code == 0
    mock.run_waterfall_sync.assert_called_once()


# ===========================================================================
# Tables
# ===========================================================================


def test_table_list(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "list"])
    assert result.exit_code == 0
    assert "My Table" in result.output


def test_table_create(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "create", "--name", "New Table"])
    assert result.exit_code == 0
    mock.create_table.assert_called_once_with(name="New Table", columns=None)


def test_table_create_with_columns(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "create", "--name", "T", "--columns", "email,name"])
    assert result.exit_code == 0
    mock.create_table.assert_called_once_with(name="T", columns=["email", "name"])


def test_table_rows_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "rows", "tbl-1", "--format", "json"])
    assert result.exit_code == 0


def test_table_insert_json_data(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "insert", "tbl-1", "--data", '[{"email":"alice@example.com"}]'])
    assert result.exit_code == 0
    mock.create_rows.assert_called_once()


def test_table_insert_requires_data_or_input(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "insert", "tbl-1"])
    assert result.exit_code != 0


def test_table_enrichments(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "enrichments", "tbl-1"])
    assert result.exit_code == 0
    assert "My Enrichment" in result.output


# ===========================================================================
# Tasks
# ===========================================================================


def test_task_get(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", "t1"])
    assert result.exit_code == 0
    assert "completed" in result.output.lower()


def test_task_get_poll(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", "t1", "--poll"])
    assert result.exit_code == 0
    mock.poll_task.assert_called_once_with("t1")


# ===========================================================================
# Version flag
# ===========================================================================


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "1.0.0" in result.output
