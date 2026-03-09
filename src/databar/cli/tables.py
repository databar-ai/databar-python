"""
CLI commands for tables and rows.

  databar table list
  databar table create        [--name] [--columns col1,col2,...]
  databar table columns       <uuid>
  databar table rows          <uuid> [--page] [--per-page] [--format] [--out]
  databar table insert        <uuid> (--data JSON | --input FILE.csv) [--allow-new-columns] [--dedupe-keys]
  databar table patch         <uuid> (--data JSON | --input FILE.csv) [--no-overwrite]
  databar table upsert        <uuid> --key-col <col> (--data JSON | --input FILE.csv)
  databar table enrichments   <uuid>
  databar table add-enrichment <uuid> --enrichment-id <n> --mapping '{...}'
  databar table run-enrichment <uuid> --enrichment-id <n> [--run-strategy]
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

import typer

from databar.exceptions import DatabarError
from databar.models import BatchUpdateRow, InsertOptions, InsertRow, DedupeOptions, UpsertRow

from ._auth import get_client
from ._output import OutputFormat, console, error, info, output, success

app = typer.Typer(help="Manage tables and rows.")


@app.command("list")
def list_tables(
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """List all tables in your workspace."""
    client = get_client()
    try:
        tables = client.list_tables()
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    if not tables:
        info("No tables found.")
        return

    rows = [
        {"uuid": t.identifier, "name": t.name, "created": t.created_at, "updated": t.updated_at}
        for t in tables
    ]
    output(rows, fmt, table_columns=["uuid", "name", "created", "updated"])


@app.command("create")
def create_table(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Table name."),
    columns: Optional[str] = typer.Option(None, "--columns", "-c", help="Comma-separated column names."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Create a new empty table."""
    col_list = [c.strip() for c in columns.split(",")] if columns else None

    client = get_client()
    try:
        table = client.create_table(name=name, columns=col_list)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    success(f"Table created: {table.identifier}")
    output({"uuid": table.identifier, "name": table.name, "created": table.created_at}, fmt)


@app.command("columns")
def get_columns(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """List columns defined on a table."""
    client = get_client()
    try:
        columns = client.get_columns(table_uuid)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    if not columns:
        info("No columns found.")
        return

    rows = [
        {"name": c.name, "type": c.type_of_value, "internal_name": c.internal_name, "id": c.identifier}
        for c in columns
    ]
    output(rows, fmt, table_columns=["name", "type", "internal_name", "id"])


@app.command("rows")
def get_rows(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    page: int = typer.Option(1, "--page", help="Page number."),
    per_page: int = typer.Option(1000, "--per-page", help="Rows per page (max 1000)."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output file (for CSV format)."),
) -> None:
    """Get rows from a table."""
    client = get_client()
    try:
        data = client.get_rows(table_uuid, page=page, per_page=per_page)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    results = data.get("result", data) if isinstance(data, dict) else data
    total = data.get("total_count", "?") if isinstance(data, dict) else "?"
    has_next = data.get("has_next_page", False) if isinstance(data, dict) else False

    # Flatten nested row data format {id, data: {...}} → flat dict
    flat = []
    for row in (results if isinstance(results, list) else []):
        if isinstance(row, dict) and "data" in row and isinstance(row["data"], dict):
            flat.append({"_id": row.get("id", ""), **row["data"]})
        else:
            flat.append(row)

    output(flat, fmt, out=out)

    if has_next:
        info(f"Showing page {page} of results (total: {total}). Use --page {page + 1} for next page.")


@app.command("insert")
def insert_rows(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    data_json: Optional[str] = typer.Option(None, "--data", "-d", help="JSON array of row objects."),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="CSV file.", exists=True),
    allow_new_columns: bool = typer.Option(False, "--allow-new-columns", help="Auto-create unknown columns."),
    dedupe_keys: Optional[str] = typer.Option(None, "--dedupe-keys", help="Comma-separated column names for deduplication."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Insert rows into a table."""
    raw_rows = _load_rows(data_json, input_file)
    rows = [InsertRow(fields=r) for r in raw_rows]

    options = InsertOptions(allow_new_columns=allow_new_columns)
    if dedupe_keys:
        options.dedupe = DedupeOptions(
            enabled=True,
            keys=[k.strip() for k in dedupe_keys.split(",")],
        )

    client = get_client()
    try:
        info(f"Inserting {len(rows)} row(s) into {table_uuid}…")
        response = client.create_rows(table_uuid, rows, options=options)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    created = [r for r in response.results if r.action == "created"]
    skipped = [r for r in response.results if r.action == "skipped_duplicate"]

    success(f"Inserted {len(created)} row(s). Skipped {len(skipped)} duplicate(s).")

    if fmt == OutputFormat.JSON:
        output(response.model_dump(), fmt)
    else:
        rows_out = [{"index": r.index, "id": r.id or "", "action": r.action} for r in response.results]
        output(rows_out, fmt, table_columns=["index", "id", "action"])


@app.command("patch")
def patch_rows(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    data_json: Optional[str] = typer.Option(None, "--data", "-d", help='JSON array: [{"id":"<uuid>","fields":{...}}]'),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="CSV file (must have an 'id' column).", exists=True),
    no_overwrite: bool = typer.Option(False, "--no-overwrite", help="Only fill empty cells; keep existing values."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Update existing rows by row UUID."""
    raw_rows = _load_rows(data_json, input_file)
    rows = []
    for r in raw_rows:
        if "id" not in r:
            error("Each row must have an 'id' field for patch operations.")
        rows.append(BatchUpdateRow(id=r.pop("id"), fields=r))

    client = get_client()
    try:
        info(f"Patching {len(rows)} row(s) in {table_uuid}…")
        response = client.patch_rows(table_uuid, rows, overwrite=not no_overwrite)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    ok = [r for r in response.results if r.ok]
    failed = [r for r in response.results if not r.ok]
    success(f"Updated {len(ok)} row(s). Failed: {len(failed)}.")

    if fmt == OutputFormat.JSON:
        output(response.model_dump(), fmt)
    else:
        rows_out = [{"id": r.id, "ok": r.ok, "error": r.error or ""} for r in response.results]
        output(rows_out, fmt, table_columns=["id", "ok", "error"])


@app.command("upsert")
def upsert_rows(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    key_col: str = typer.Option(..., "--key-col", "-k", help="Column name to match on (e.g. 'email')."),
    data_json: Optional[str] = typer.Option(None, "--data", "-d", help="JSON array of row objects."),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="CSV file.", exists=True),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Insert or update rows matched by a key column."""
    raw_rows = _load_rows(data_json, input_file)
    rows = []
    for r in raw_rows:
        if key_col not in r:
            error(f"Each row must contain the key column '{key_col}'.")
        key_val = r.pop(key_col)
        rows.append(UpsertRow(key={key_col: key_val}, fields=r))

    client = get_client()
    try:
        info(f"Upserting {len(rows)} row(s) in {table_uuid} on key '{key_col}'…")
        response = client.upsert_rows(table_uuid, rows)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    created = [r for r in response.results if r.action == "created"]
    updated = [r for r in response.results if r.action == "updated"]
    success(f"Created {len(created)}, updated {len(updated)} row(s).")

    if fmt == OutputFormat.JSON:
        output(response.model_dump(), fmt)
    else:
        rows_out = [{"id": r.id or "", "action": r.action or "", "ok": r.ok} for r in response.results]
        output(rows_out, fmt, table_columns=["id", "action", "ok"])


@app.command("enrichments")
def table_enrichments(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """List enrichments configured on a table."""
    client = get_client()
    try:
        enrichments = client.get_table_enrichments(table_uuid)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    if not enrichments:
        info("No enrichments configured on this table.")
        return

    rows = [{"id": e.id, "name": e.name} for e in enrichments]
    output(rows, fmt, table_columns=["id", "name"])


@app.command("add-enrichment")
def add_enrichment(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    enrichment_id: int = typer.Option(..., "--enrichment-id", "-e", help="Enrichment ID to add."),
    mapping_json: str = typer.Option(..., "--mapping", "-m", help='JSON mapping of param → column, e.g. \'{"email": "email_col"}\''),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Add an enrichment to a table with a column mapping."""
    try:
        mapping = json.loads(mapping_json)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON for --mapping: {e}")

    client = get_client()
    try:
        result = client.add_enrichment(table_uuid, enrichment_id, mapping)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    success("Enrichment added to table.")
    output(result, fmt)


@app.command("run-enrichment")
def run_table_enrichment(
    table_uuid: str = typer.Argument(..., help="Table UUID."),
    enrichment_id: str = typer.Option(..., "--enrichment-id", "-e", help="Table enrichment ID (from `table enrichments`)."),
    run_strategy: Optional[str] = typer.Option(None, "--run-strategy", help="Run strategy (e.g. 'empty_only')."),
) -> None:
    """Trigger an enrichment to run on all rows in a table."""
    client = get_client()
    try:
        result = client.run_table_enrichment(table_uuid, enrichment_id, run_strategy=run_strategy)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    success("Table enrichment triggered.")
    if result:
        output(result, OutputFormat.JSON)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_rows(data_json: Optional[str], input_file: Optional[Path]) -> list[dict]:
    if data_json and input_file:
        error("Provide either --data or --input, not both.")

    if data_json:
        try:
            parsed = json.loads(data_json)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON for --data: {e}")
        if not isinstance(parsed, list):
            error("--data must be a JSON array of objects.")
        return parsed

    if input_file:
        with open(input_file, newline="") as f:
            return list(csv.DictReader(f))

    error("Provide either --data or --input.")
    return []  # unreachable
