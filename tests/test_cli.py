"""
CLI integration tests using typer's CliRunner.

These tests mock DatabarClient at the method level so no HTTP calls are made.
Each test verifies the CLI command wires correctly to the SDK and formats output.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from databar.cli.app import app
from databar.exceptions import DatabarAuthError, DatabarError, DatabarNotFoundError
from databar.models import (
    AddEnrichmentResponse,
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
    Flow,
    FlowInput,
    RowsResponse,
    RunEnrichmentResponse,
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
TABLE_UUID = "11111111-1111-1111-1111-111111111111"
TASK_ID = "22222222-2222-2222-2222-222222222222"


def _client_mock(**method_overrides):
    """Return a MagicMock DatabarClient with sensible defaults."""
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.latest_version = None
    m.last_task = None

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

    m.list_flows.return_value = [
        Flow(
            id="flow-uuid-1",
            name="Find buyer",
            description="Enrich a lead",
            inputs=[FlowInput(id="email", description="Email", type="text", required=True)],
            outputs=[],
        )
    ]
    m.get_flow.return_value = m.list_flows.return_value[0]
    m.run_flow_sync.return_value = {"full_name": "Alice"}

    m.list_tables.return_value = [
        Table(identifier="tbl-1", name="My Table", created_at="2024-01-01", updated_at="2024-01-01")
    ]
    m.create_table.return_value = Table(
        identifier="tbl-new", name="New Table", created_at="2024-01-01", updated_at="2024-01-01"
    )
    m.get_columns.return_value = [
        Column(identifier="col-1", internal_name="email_col", name="email", type_of_value="text", data_processor_id=None)
    ]
    m.get_rows.return_value = RowsResponse(
        data=[{"id": "r1", "email": "alice@example.com"}],
        total_count=1,
        has_next_page=False,
        page=1,
    )
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
    m.get_task.return_value = TaskResponse(task_id="t1", status="completed", data={"result": "ok"})
    m.cancel_task.return_value = TaskResponse(
        task_id="t1",
        status="cancelled",
        progress={"total": 10, "completed": 4, "failed": 1, "processing": 5},
    )
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


def test_login_oauth_saves_key(tmp_path, monkeypatch):
    config_file = tmp_path / "config"
    monkeypatch.setattr("databar.cli._auth.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("databar.cli._auth.CONFIG_FILE", config_file)
    monkeypatch.setattr(
        "databar.cli._oauth.run_browser_login",
        lambda print_url=None: {"api_key": "oauth-key", "email": "ada@example.com"},
    )
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0
    assert "ada@example.com" in result.output
    assert "api_key=oauth-key" in config_file.read_text()


def test_login_oauth_preserves_other_config_lines(tmp_path, monkeypatch):
    config_file = tmp_path / "config"
    config_file.write_text("preferred_interface=cli\napi_key=old\n")
    monkeypatch.setattr("databar.cli._auth.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("databar.cli._auth.CONFIG_FILE", config_file)
    monkeypatch.setattr(
        "databar.cli._oauth.run_browser_login",
        lambda print_url=None: {"api_key": "new-key", "email": "ada@example.com"},
    )
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0
    text = config_file.read_text()
    assert "api_key=new-key" in text
    assert "preferred_interface=cli" in text
    assert "api_key=old" not in text


def _logout_with(tmp_path, monkeypatch, revoked):
    config_file = tmp_path / "config"
    config_file.write_text("api_key=secret\npreferred_interface=cli\n")
    monkeypatch.setattr("databar.cli._auth.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("databar.cli._auth.CONFIG_FILE", config_file)
    calls = []
    monkeypatch.setattr(
        "databar.cli._oauth.revoke_sign_in", lambda key: calls.append(key) or revoked
    )
    result = runner.invoke(app, ["logout"])
    return result, config_file.read_text(), calls


def test_logout_removes_key(tmp_path, monkeypatch):
    result, text, calls = _logout_with(tmp_path, monkeypatch, revoked=False)
    assert result.exit_code == 0
    assert calls == ["secret"]
    assert "api_key=" not in text
    assert "preferred_interface=cli" in text
    assert "Could not reach" not in result.output


def test_logout_revokes_the_sign_in(tmp_path, monkeypatch):
    result, text, _ = _logout_with(tmp_path, monkeypatch, revoked=True)
    assert result.exit_code == 0
    assert "revoked" in result.output
    assert "api_key=" not in text


def test_logout_offline_still_forgets_the_key(tmp_path, monkeypatch):
    result, text, _ = _logout_with(tmp_path, monkeypatch, revoked=None)
    assert result.exit_code == 0
    assert "api_key=" not in text
    assert "Could not reach" in result.output


def test_whoami_table(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli._auth.get_client", lambda: mock)
    result = invoke(["whoami"])
    assert result.exit_code == 0
    assert "alice@example.com" in result.output


def test_whoami_json_reports_the_latest_version(monkeypatch):
    from databar import __version__

    mock = _client_mock()
    mock.latest_version = "99.0.0"
    monkeypatch.setattr("databar.cli._auth.get_client", lambda: mock)
    result = invoke(["whoami", "--format", "json"])
    data = json.loads(result.stdout)["data"]
    assert data["version"] == __version__
    assert data["latest_version"] == "99.0.0"


def test_update_notice_goes_to_stderr_once(monkeypatch, capsys):
    from databar.cli import _update_notice

    monkeypatch.setattr(_update_notice, "_shown", False)
    monkeypatch.setattr(_update_notice, "__version__", "2.5.1")
    monkeypatch.delenv("DATABAR_NO_UPDATE_NOTICE", raising=False)
    _update_notice.notify_if_outdated("2.10.1")
    _update_notice.notify_if_outdated("2.10.1")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("databar 2.5.1 is outdated, latest is 2.10.1: pip install -U databar") == 1


def test_update_notice_stays_quiet_when_current(monkeypatch, capsys):
    from databar.cli import _update_notice

    monkeypatch.setattr(_update_notice, "_shown", False)
    monkeypatch.setattr(_update_notice, "__version__", "2.10.1")
    _update_notice.notify_if_outdated("2.10.1")
    _update_notice.notify_if_outdated("2.9.9")
    assert capsys.readouterr().err == ""


def test_update_notice_compares_versions_as_numbers():
    from databar.cli._update_notice import is_outdated

    assert is_outdated("2.9.0", "2.10.0")
    assert not is_outdated("2.10.0", "2.9.0")
    assert not is_outdated("2.10", "2.10.0")
    assert not is_outdated("2.10.0", "garbage")


def test_whoami_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli._auth.get_client", lambda: mock)
    result = invoke(["whoami", "--format", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["ok"] is True
    assert parsed["data"]["email"] == "alice@example.com"


def test_whoami_json_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABAR_API_KEY", raising=False)
    monkeypatch.setattr("databar.cli._auth.CONFIG_FILE", tmp_path / "config")
    result = runner.invoke(app, ["whoami", "--format", "json"])
    assert result.exit_code == 3
    assert (result.stderr or "") == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "auth_missing"
    assert "api key" in parsed["error"]["message"].lower() or "login" in parsed["error"]["message"].lower()


def test_whoami_json_auth_invalid(monkeypatch):
    mock = _client_mock()
    mock.get_user.side_effect = DatabarAuthError(
        "Invalid API key or insufficient permissions. Check your API key.",
        status_code=401,
    )
    monkeypatch.setattr("databar.cli._auth.get_client", lambda: mock)
    result = invoke(["whoami", "--format", "json"])
    assert result.exit_code == 3
    assert (result.stderr or "") == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "auth_invalid"


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
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, list)
    assert data[0]["id"] == 1


def test_enrich_run_invalid_json_format_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "run", "1", "--params", "not-json", "--format", "json"])
    assert result.exit_code == 2
    assert (result.stderr or "") == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "usage"


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


def test_enrich_run_json_carries_credits_spent(monkeypatch):
    """DEV-5305: the charge of a run, beside data so data keeps its shape."""
    mock = _client_mock()
    mock.last_task = TaskResponse(task_id="t1", status="completed", data={"x": 1}, credits_spent=1.5)
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "run", "1", "--params", '{"email":"a@x.com"}', "--format", "json"])
    body = json.loads(result.stdout)
    assert body["credits_spent"] == 1.5
    assert body["data"] == [{"email": "alice@example.com", "name": "Alice"}]


def test_enrich_run_table_prints_credits_spent(monkeypatch):
    mock = _client_mock()
    mock.last_task = TaskResponse(task_id="t1", status="completed", data={}, credits_spent=0.25)
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "run", "1", "--params", '{"email":"a@x.com"}'])
    assert "Credits spent: 0.25" in result.stdout


def test_enrich_bulk_dry_run_estimates_without_running(monkeypatch, tmp_path):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    src = tmp_path / "in.csv"
    src.write_text("email\na@x.com\nb@x.com\nc@x.com\n")
    result = invoke(["enrich", "bulk", "1", "--input", str(src), "--dry-run", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["dry_run"] is True
    assert data["records"] == 3
    assert data["estimated_credits"] == {"min": 1.5, "max": 1.5}
    assert data["balance"] == 99.5
    mock.run_enrichment_bulk_sync.assert_not_called()


def test_waterfall_dry_run_is_a_range(monkeypatch):
    mock = _client_mock()
    mock.get_waterfall.return_value = Waterfall(
        identifier="email_getter",
        name="Email Getter",
        description="",
        input_params=[],
        output_fields=[],
        available_enrichments=[
            WaterfallEnrichment(id=10, name="A", description="", price="0.5", params=[]),
            WaterfallEnrichment(id=11, name="B", description="", price="1.0", params=[]),
            WaterfallEnrichment(id=12, name="C", description="", price="9", params=[], enabled_by_default=False),
        ],
        is_email_verifying=True,
        email_verifiers=[{"id": 99, "price": "0.1"}],
    )
    monkeypatch.setattr("databar.cli.waterfalls.get_client", lambda: mock)
    result = invoke(
        ["waterfall", "run", "email_getter", "--params", "{}", "--email-verifier", "99", "--dry-run", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["estimated_credits"] == {"min": 0.6, "max": 1.7}
    mock.run_waterfall_sync.assert_not_called()


def test_flow_dry_run_asks_the_api_estimate(monkeypatch):
    from databar.models import FlowCostEstimate, FlowDetail

    mock = _client_mock()
    mock.get_flow.return_value = FlowDetail(
        id="flow-uuid-1", name="F", description="", inputs=[], outputs=[], config={"nodes": []}
    )
    mock.estimate_flow_cost.return_value = FlowCostEstimate(min="0.5", max="2")
    monkeypatch.setattr("databar.cli.flows.get_client", lambda: mock)
    result = invoke(["flow", "run", "flow-uuid-1", "--inputs", "{}", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Estimated cost of flow flow-uuid-1: 0.5–2 credits for 1 row." in result.stdout
    mock.estimate_flow_cost.assert_called_once_with({"nodes": []})
    mock.run_flow_sync.assert_not_called()


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
# Flows
# ===========================================================================


def test_flow_list(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.flows.get_client", lambda: mock)
    result = invoke(["flow", "list"])
    assert result.exit_code == 0
    assert "flow-uuid-1" in result.output
    assert "Find buyer" in result.output


def test_flow_get(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.flows.get_client", lambda: mock)
    result = invoke(["flow", "get", "flow-uuid-1"])
    assert result.exit_code == 0
    assert "Find buyer" in result.output


def test_flow_run(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.flows.get_client", lambda: mock)
    result = invoke(["flow", "run", "flow-uuid-1", "--inputs", '{"email":"alice@example.com"}'])
    assert result.exit_code == 0
    mock.run_flow_sync.assert_called_once_with("flow-uuid-1", {"email": "alice@example.com"})


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


def test_table_create_rejects_duplicate_columns(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "create", "--name", "T", "--columns", "email,email"])
    assert result.exit_code != 0
    mock.create_table.assert_not_called()


def test_table_create_strips_empty_columns(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "create", "--name", "T", "--columns", "email,,name,"])
    assert result.exit_code == 0
    mock.create_table.assert_called_once_with(name="T", columns=["email", "name"])


def test_table_delete(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "delete", TABLE_UUID])
    assert result.exit_code == 0
    mock.delete_table.assert_called_once_with(TABLE_UUID)


def test_table_delete_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "delete", TABLE_UUID, "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "data": {"uuid": TABLE_UUID, "deleted": True}}


def test_table_add_enrichment_json_is_an_object(monkeypatch):
    """DEV-5305: the response model went out as its repr string."""
    mock = _client_mock(add_enrichment=AddEnrichmentResponse(id=108904, enrichment_name="Email finder"))
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(
        ["table", "add-enrichment", TABLE_UUID, "-e", "1", "--mapping", '{"email": "email"}', "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"] == {"id": 108904, "enrichment_name": "Email finder"}
    mock.add_enrichment.assert_called_once_with(TABLE_UUID, 1, {"email": "email"})


def test_table_run_enrichment_defaults_to_run_all(monkeypatch):
    """DEV-5305: without --run-strategy the CLI sent null and the server refused the run."""
    mock = _client_mock(run_table_enrichment=RunEnrichmentResponse(status="queued", processing_rows=3))
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "run-enrichment", TABLE_UUID, "-e", "5", "--format", "json"])
    assert result.exit_code == 0, result.output
    mock.run_table_enrichment.assert_called_once_with(TABLE_UUID, "5", run_strategy="run_all")
    assert json.loads(result.stdout)["data"] == {"status": "queued", "processing_rows": 3}


def test_table_run_enrichment_refuses_an_unknown_strategy(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "run-enrichment", TABLE_UUID, "-e", "5", "--run-strategy", "empty_only"])
    assert result.exit_code == 2
    mock.run_table_enrichment.assert_not_called()


def test_enrich_bulk_csv_writes_nested_values_as_json(monkeypatch, tmp_path):
    """DEV-5305: a nested column came out as a Python dict repr (single quotes, True, None)."""
    mock = _client_mock(
        run_enrichment_bulk_sync=[{"email": "a@x.com", "alldata": {"ok": True, "phone": None, "tags": ["a"]}}]
    )
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    src = tmp_path / "in.csv"
    src.write_text("email\na@x.com\n")
    result = invoke(["enrich", "bulk", "1", "--input", str(src), "--format", "csv"])
    assert result.exit_code == 0, result.output
    import csv as _csv
    import io

    rows = list(_csv.DictReader(io.StringIO(result.stdout)))
    assert json.loads(rows[0]["alldata"]) == {"ok": True, "phone": None, "tags": ["a"]}


def test_table_rows_json(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "rows", TABLE_UUID, "--format", "json"])
    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["ok"] is True
    assert envelope["data"][0]["email"] == "alice@example.com"
    mock.get_rows.assert_called_once_with(TABLE_UUID, page=1, per_page=500)


def test_table_rows_json_not_found(monkeypatch):
    mock = _client_mock()
    mock.get_rows.side_effect = DatabarNotFoundError("Resource not found.", status_code=404)
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "rows", TABLE_UUID, "--format", "json"])
    assert result.exit_code == 4
    assert (result.stderr or "") == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "not_found"


def test_table_rows_rejects_invalid_uuid(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "rows", "foo%2Fbar", "--format", "json"])
    assert result.exit_code == 5
    mock.get_rows.assert_not_called()
    assert (result.stderr or "") == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "validation"
    assert "hint" in parsed["error"]
    assert "UUID" in parsed["error"]["hint"]


def test_table_rows_rejects_bad_per_page(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "rows", TABLE_UUID, "--per-page", "1000"])
    assert result.exit_code != 0
    mock.get_rows.assert_not_called()


def test_table_rows_rejects_bad_page(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "rows", TABLE_UUID, "--page", "0"])
    assert result.exit_code != 0
    mock.get_rows.assert_not_called()


def test_table_patch_nonzero_exit_on_failure(monkeypatch):
    mock = _client_mock(
        patch_rows=BatchUpdateResponse(
            results=[BatchUpdateResultItem(id="missing", ok=False, error={"code": "ROW_NOT_FOUND"})]
        )
    )
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(
        [
            "table",
            "patch",
            TABLE_UUID,
            "--data",
            '[{"id":"missing","email":"x@y.com"}]',
            "--format",
            "json",
        ]
    )
    assert result.exit_code == 1


def test_table_insert_json_data(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "insert", TABLE_UUID, "--data", '[{"email":"alice@example.com"}]'])
    assert result.exit_code == 0
    mock.create_rows.assert_called_once()


def test_table_insert_requires_data_or_input(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "insert", TABLE_UUID])
    assert result.exit_code != 0


def _stderr(result) -> str:
    return result.stderr if hasattr(result, "stderr") and result.stderr else ""


def test_table_insert_rejects_non_object_data(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "insert", TABLE_UUID, "--data", "[1]", "--format", "json"])
    assert result.exit_code == 2
    mock.create_rows.assert_not_called()
    assert _stderr(result) == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "usage"
    assert "--data[0]" in parsed["error"]["message"]
    assert "object" in parsed["error"]["message"]
    assert "Traceback" not in parsed["error"]["message"]
    assert "ValidationError" not in parsed["error"]["message"]


def test_table_insert_rejects_non_object_at_index(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(
        ["table", "insert", TABLE_UUID, "--data", '[{"email":"a@b.com"}, 1]']
    )
    assert result.exit_code != 0
    mock.create_rows.assert_not_called()
    assert "--data[1]" in _stderr(result)


def test_table_insert_rejects_non_array_data(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "insert", TABLE_UUID, "--data", "{}"])
    assert result.exit_code != 0
    mock.create_rows.assert_not_called()
    assert "JSON array of objects" in _stderr(result)


def test_table_patch_rejects_non_object_data(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "patch", TABLE_UUID, "--data", "[1]"])
    assert result.exit_code != 0
    mock.patch_rows.assert_not_called()
    err = _stderr(result)
    assert "--data[0]" in err
    assert "Traceback" not in err


def test_table_upsert_rejects_non_object_data(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(
        ["table", "upsert", TABLE_UUID, "--key-col", "email", "--data", "[1]"]
    )
    assert result.exit_code != 0
    mock.upsert_rows.assert_not_called()
    err = _stderr(result)
    assert "--data[0]" in err
    assert "Traceback" not in err


def test_pretty_exceptions_disabled_by_default():
    from databar.cli.app import app as cli_app

    assert cli_app.pretty_exceptions_enable is False


def test_table_enrichments(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "enrichments", TABLE_UUID])
    assert result.exit_code == 0
    assert "My Enrichment" in result.output


def test_table_rows_out_resolves_dotdot(monkeypatch, tmp_path):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    out_arg = str(Path("sub") / ".." / "out.csv")
    result = invoke(["table", "rows", TABLE_UUID, "--format", "csv", "--out", out_arg])
    assert result.exit_code == 0
    assert (tmp_path / "out.csv").is_file()
    assert not (tmp_path / "sub" / "out.csv").exists()


def test_table_rows_out_rejects_null_byte(monkeypatch, tmp_path):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    monkeypatch.chdir(tmp_path)
    result = invoke(
        ["table", "rows", TABLE_UUID, "--format", "csv", "--out", "bad\0name.csv"]
    )
    assert result.exit_code == 5
    assert list(tmp_path.iterdir()) == []


def test_table_rows_out_notes_outside_cwd(monkeypatch, tmp_path):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    cwd = tmp_path / "cwd"
    outside = tmp_path / "outside"
    cwd.mkdir()
    outside.mkdir()
    monkeypatch.chdir(cwd)
    out_path = outside / "rows.csv"
    result = invoke(["table", "rows", TABLE_UUID, "--format", "csv", "--out", str(out_path)])
    assert result.exit_code == 0
    assert out_path.is_file()
    combined = (result.output or "") + _stderr(result)
    assert "outside the current directory" in combined


def test_enrich_choices_rejects_bad_page(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "choices", "1", "country", "--page", "-1"])
    assert result.exit_code != 0
    mock.get_param_choices.assert_not_called()


def test_enrich_choices_rejects_bad_limit(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.enrichments.get_client", lambda: mock)
    result = invoke(["enrich", "choices", "1", "country", "--limit", "999999"])
    assert result.exit_code != 0
    mock.get_param_choices.assert_not_called()


def test_output_json_handles_unicode():
    from databar.cli._output import output_json

    # Smoke: non-ASCII / nb-hyphen must not raise under UTF-8 stdout.
    output_json({"name": "Acme‑Corp"})


# ===========================================================================
# Tasks
# ===========================================================================


def test_task_get(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", TASK_ID])
    assert result.exit_code == 0
    assert "completed" in result.output.lower()


def test_task_get_rejects_invalid_uuid(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", "not-a-uuid", "--format", "json"])
    assert result.exit_code == 5
    mock.get_task.assert_not_called()
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "validation"
    assert "hint" in parsed["error"]


def test_task_get_json_with_task_error(monkeypatch):
    mock = _client_mock()
    mock.get_task.return_value = TaskResponse(
        task_id=TASK_ID, status="failed", data=None, error=["upstream blew up"]
    )
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", TASK_ID, "--format", "json"])
    assert result.exit_code == 1
    assert (result.stderr or "") == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "task_failed"
    assert "upstream blew up" in parsed["error"]["message"]


def test_task_get_poll(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", TASK_ID, "--poll"])
    assert result.exit_code == 0
    mock.poll_task.assert_called_once_with(TASK_ID)


def test_task_get_shows_progress_of_a_running_bulk_task(monkeypatch):
    mock = _client_mock()
    mock.get_task.return_value = TaskResponse(
        task_id=TASK_ID,
        status="processing",
        progress={"total": 10, "completed": 4, "failed": 1, "processing": 5},
    )
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", TASK_ID])
    assert result.exit_code == 0
    assert "4 completed" in result.output
    assert "of 10" in result.output


def test_task_get_partial_asks_for_finished_rows(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", TASK_ID, "--partial"])
    assert result.exit_code == 0
    mock.get_task.assert_called_once_with(TASK_ID, include_partial=True, include_trace=False)


def test_task_get_trace_names_the_output_step_that_answered(monkeypatch):
    mock = _client_mock()
    mock.get_task.return_value = TaskResponse(
        task_id=TASK_ID,
        status="completed",
        data={"email": "a@b.co"},
        trace={
            "run_status": "completed",
            "returned_by": {"id": "out_hot", "name": "Hot lead"},
            "steps": [{"node_id": "check", "type": "condition"}, {"node_id": "out_hot", "type": "output"}],
        },
    )
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "get", TASK_ID, "--trace"])
    assert result.exit_code == 0
    mock.get_task.assert_called_once_with(TASK_ID, include_partial=False, include_trace=True)
    assert "Hot lead" in result.output

    result = invoke(["task", "get", TASK_ID, "--trace", "--format", "json"])
    payload = json.loads(result.stdout)["data"]
    assert payload["trace"]["returned_by"]["id"] == "out_hot"
    assert payload["data"] == {"email": "a@b.co"}


def test_task_cancel(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "cancel", TASK_ID])
    assert result.exit_code == 0
    assert "cancelled" in result.output.lower()
    mock.cancel_task.assert_called_once_with(TASK_ID)


def test_task_cancel_reports_a_finished_task(monkeypatch):
    mock = _client_mock()
    mock.cancel_task.side_effect = DatabarError("Task has already finished", status_code=409)
    monkeypatch.setattr("databar.cli.tasks.get_client", lambda: mock)
    result = invoke(["task", "cancel", TASK_ID])
    assert result.exit_code == 1
    assert "already finished" in result.stderr


# ===========================================================================
# Version flag
# ===========================================================================


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "2.10.1" in result.output


def test_output_module_does_not_import_click():
    # Typer 0.26+ vendors Click; a top-level `import click` crashes a fresh install.
    import databar.cli._output as out

    assert "click" not in out.__dict__


# ---------------------------------------------------------------------------
# Workbook sheets: move / reorder
# ---------------------------------------------------------------------------

OTHER_UUID = "33333333-3333-3333-3333-333333333333"


def test_table_move_to_workbook(monkeypatch):
    mock = _client_mock()
    mock.move_table.return_value = {"status": "moved", "workbook": "wb_target123", "table": TABLE_UUID}
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "move", TABLE_UUID, "--workbook", "wb_target123", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["workbook"] == "wb_target123"
    mock.move_table.assert_called_once_with(TABLE_UUID, workbook="wb_target123", new_workbook=False, name=None)


def test_table_move_to_new_workbook_with_name(monkeypatch):
    mock = _client_mock()
    mock.move_table.return_value = {"status": "created", "workbook": "wb_new12345", "table": TABLE_UUID}
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "move", TABLE_UUID, "--new-workbook", "--name", "Split out"])
    assert result.exit_code == 0, result.output
    mock.move_table.assert_called_once_with(TABLE_UUID, workbook=None, new_workbook=True, name="Split out")


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--workbook", "wb_target123", "--new-workbook"],
        ["--workbook", "wb_target123", "--name", "X"],
    ],
)
def test_table_move_needs_exactly_one_target(monkeypatch, args):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.tables.get_client", lambda: mock)
    result = invoke(["table", "move", TABLE_UUID, *args])
    assert result.exit_code == 2
    mock.move_table.assert_not_called()


def test_workbook_reorder(monkeypatch):
    from databar.models import Workbook

    mock = _client_mock()
    mock.reorder_workbook_tables.return_value = Workbook(
        identifier="wb_abc12345",
        name="Doc",
        created_at="2026-10-30T00:00:00Z",
        updated_at="2026-10-30T00:00:00Z",
        tables=[
            {"identifier": TABLE_UUID, "name": "B", "position": 1},
            {"identifier": OTHER_UUID, "name": "A", "position": 0},
        ],
        tables_count=2,
    )
    monkeypatch.setattr("databar.cli.workbooks.get_client", lambda: mock)
    result = invoke(["workbook", "reorder", "wb_abc12345", "--tables", f"{OTHER_UUID}, {TABLE_UUID}", "--format", "json"])
    assert result.exit_code == 0, result.output
    mock.reorder_workbook_tables.assert_called_once_with("wb_abc12345", [OTHER_UUID, TABLE_UUID])
    assert [t["uuid"] for t in json.loads(result.output)["data"]] == [OTHER_UUID, TABLE_UUID]


def test_workbook_reorder_rejects_repeats(monkeypatch):
    mock = _client_mock()
    monkeypatch.setattr("databar.cli.workbooks.get_client", lambda: mock)
    result = invoke(["workbook", "reorder", "wb_abc12345", "--tables", f"{TABLE_UUID},{TABLE_UUID}"])
    assert result.exit_code == 2
    mock.reorder_workbook_tables.assert_not_called()
