"""
CLI commands for enrichments.

  databar enrich list    [--query] [--format]
  databar enrich get     <id> [--format]
  databar enrich run     <id> --params '{"k":"v"}' [--format]
  databar enrich bulk    <id> --input FILE.csv [--format] [--out FILE]
  databar enrich choices <id> <param> [--query] [--page] [--limit]
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

import typer

from databar.exceptions import DatabarError

from ._auth import get_client
from ._output import OutputFormat, console, error, info, output

app = typer.Typer(help="Search and run data enrichments.")


@app.command("list")
def list_enrichments(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f"),
) -> None:
    """List available enrichments."""
    client = get_client()
    try:
        enrichments = client.list_enrichments(q=query)
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    if not enrichments:
        info("No enrichments found.")
        return

    rows = [
        {
            "id": e.id,
            "name": e.name,
            "data_source": e.data_source,
            "price": f"{e.price} credits",
            "description": e.description[:60] + ("…" if len(e.description) > 60 else ""),
        }
        for e in enrichments
    ]
    output(rows, fmt, table_columns=["id", "name", "data_source", "price", "description"])


@app.command("get")
def get_enrichment(
    enrichment_id: int = typer.Argument(..., help="Enrichment ID."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f"),
) -> None:
    """Get full details for an enrichment including parameters."""
    client = get_client()
    try:
        e = client.get_enrichment(enrichment_id)
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    if fmt == OutputFormat.JSON:
        output(e.model_dump(), fmt)
        return

    console.print(f"\n[bold cyan]Enrichment #{e.id}[/bold cyan]: {e.name}")
    console.print(f"[dim]Data source:[/dim] {e.data_source}")
    console.print(f"[dim]Price:[/dim] {e.price} credits per call")
    console.print(f"[dim]Auth:[/dim] {e.auth_method}")
    console.print(f"\n{e.description}\n")

    if e.params:
        console.print("[bold]Parameters:[/bold]")
        rows = [
            {
                "name": p.name,
                "required": "yes" if p.is_required else "no",
                "type": p.type_field,
                "description": p.description,
            }
            for p in e.params
        ]
        output(rows, OutputFormat.TABLE, table_columns=["name", "required", "type", "description"])

    if e.response_fields:
        console.print("\n[bold]Response fields:[/bold]")
        rows = [{"name": f.name, "type": f.type_field} for f in e.response_fields]
        output(rows, OutputFormat.TABLE, table_columns=["name", "type"])


@app.command("run")
def run_enrichment(
    enrichment_id: int = typer.Argument(..., help="Enrichment ID."),
    params_json: str = typer.Option(..., "--params", "-p", help='JSON params, e.g. \'{"email":"alice@example.com"}\''),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f"),
    raw: bool = typer.Option(False, "--raw", help="Print raw result without formatting."),
) -> None:
    """Run a single enrichment and wait for results."""
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON for --params: {e}")

    client = get_client()
    try:
        info(f"Running enrichment #{enrichment_id}…")
        result = client.run_enrichment_sync(enrichment_id, params)
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    if raw:
        console.print(result)
        return

    output(result, fmt)


@app.command("bulk")
def bulk_enrichment(
    enrichment_id: int = typer.Argument(..., help="Enrichment ID."),
    input_file: Path = typer.Option(..., "--input", "-i", help="CSV file with one row per input.", exists=True),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output file (for CSV format)."),
) -> None:
    """Run a bulk enrichment from a CSV input file."""
    params_list = _read_csv_as_dicts(input_file)
    if not params_list:
        error(f"Input file {input_file} is empty.")

    client = get_client()
    try:
        info(f"Running bulk enrichment #{enrichment_id} for {len(params_list)} rows…")
        result = client.run_enrichment_bulk_sync(enrichment_id, params_list)
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    output(result, fmt, out=out)


@app.command("choices")
def param_choices(
    enrichment_id: int = typer.Argument(..., help="Enrichment ID."),
    param_slug: str = typer.Argument(..., help="Parameter slug/name."),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Filter choices."),
    page: int = typer.Option(1, "--page", help="Page number."),
    limit: int = typer.Option(50, "--limit", help="Results per page."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f"),
) -> None:
    """List available choices for a select/mselect enrichment parameter."""
    client = get_client()
    try:
        response = client.get_param_choices(enrichment_id, param_slug, q=query, page=page, limit=limit)
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    rows = [{"id": c.id, "name": c.name} for c in response.items]
    output(rows, fmt, table_columns=["id", "name"])

    if response.has_next_page:
        info(f"Page {response.page} of many. Use --page {response.page + 1} for the next page.")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _read_csv_as_dicts(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
