"""
CLI commands for waterfalls.

  databar waterfall list  [--query] [--format]
  databar waterfall get   <identifier> [--format]
  databar waterfall run   <identifier> --params '{"k":"v"}' [--format]
  databar waterfall bulk  <identifier> --input FILE.csv [--format] [--out FILE]
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

app = typer.Typer(help="Search and run waterfall enrichments.")


@app.command("list")
def list_waterfalls(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Filter by name/description."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """List available waterfall enrichments."""
    client = get_client()
    try:
        waterfalls = client.list_waterfalls()
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    if query:
        q = query.lower()
        waterfalls = [
            w for w in waterfalls
            if q in w.name.lower() or q in w.description.lower() or q in w.identifier.lower()
        ]

    if not waterfalls:
        info("No waterfalls found.")
        return

    rows = [
        {
            "identifier": w.identifier,
            "name": w.name,
            "providers": len(w.available_enrichments),
            "description": w.description[:60] + ("…" if len(w.description) > 60 else ""),
        }
        for w in waterfalls
    ]
    output(rows, fmt, table_columns=["identifier", "name", "providers", "description"])


@app.command("get")
def get_waterfall(
    identifier: str = typer.Argument(..., help="Waterfall identifier."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Get details for a specific waterfall."""
    client = get_client()
    try:
        w = client.get_waterfall(identifier)
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    if fmt == OutputFormat.JSON:
        output(w.model_dump(), fmt)
        return

    console.print(f"\n[bold cyan]Waterfall:[/bold cyan] {w.name} ({w.identifier})")
    console.print(f"\n{w.description}\n")

    if w.input_params:
        console.print("[bold]Input parameters:[/bold]")
        rows = [
            {
                "name": p.get("name", ""),
                "required": "yes" if p.get("required") else "no",
                "type": p.get("type", ""),
            }
            for p in w.input_params
        ]
        output(rows, OutputFormat.TABLE, table_columns=["name", "required", "type"])

    if w.available_enrichments:
        console.print("\n[bold]Available providers:[/bold]")
        rows = [
            {"id": e.id, "name": e.name, "price": e.price}
            for e in w.available_enrichments
        ]
        output(rows, OutputFormat.TABLE, table_columns=["id", "name", "price"])


@app.command("info", hidden=True)
def info_waterfall(
    identifier: str = typer.Argument(..., help="Waterfall identifier."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Alias for 'get'. Get details for a specific waterfall."""
    get_waterfall(identifier, fmt)


@app.command("run")
def run_waterfall(
    identifier: str = typer.Argument(..., help="Waterfall identifier."),
    params_json: str = typer.Option(..., "--params", "-p", help='JSON params, e.g. \'{"linkedin_url":"https://..."}\''),
    providers: Optional[str] = typer.Option(None, "--providers", help="Comma-separated provider IDs (default: all)."),
    email_verifier: Optional[int] = typer.Option(None, "--email-verifier", help="Email verifier enrichment ID."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    raw: bool = typer.Option(False, "--raw", help="Print raw result without formatting."),
) -> None:
    """Run a waterfall enrichment and wait for results."""
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON for --params: {e}")

    enrichment_ids: list[int] | None = None
    if providers:
        try:
            enrichment_ids = [int(x.strip()) for x in providers.split(",")]
        except ValueError:
            error("--providers must be a comma-separated list of integers.")

    client = get_client()
    try:
        info(f"Running waterfall '{identifier}'…")
        result = client.run_waterfall_sync(
            identifier, params,
            enrichments=enrichment_ids,
            email_verifier=email_verifier,
        )
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    if raw:
        console.print(result)
        return

    output(result, fmt)


@app.command("bulk")
def bulk_waterfall(
    identifier: str = typer.Argument(..., help="Waterfall identifier."),
    input_file: Path = typer.Option(..., "--input", "-i", help="CSV file with one row per input.", exists=True),
    providers: Optional[str] = typer.Option(None, "--providers", help="Comma-separated provider IDs (default: all)."),
    email_verifier: Optional[int] = typer.Option(None, "--email-verifier", help="Email verifier enrichment ID."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output file (for CSV format)."),
) -> None:
    """Run a waterfall enrichment in bulk from a CSV input file."""
    params_list = _read_csv_as_dicts(input_file)
    if not params_list:
        error(f"Input file {input_file} is empty.")

    enrichment_ids: list[int] | None = None
    if providers:
        try:
            enrichment_ids = [int(x.strip()) for x in providers.split(",")]
        except ValueError:
            error("--providers must be a comma-separated list of integers.")

    client = get_client()
    try:
        info(f"Running bulk waterfall '{identifier}' for {len(params_list)} rows…")
        result = client.run_waterfall_bulk_sync(
            identifier, params_list,
            enrichments=enrichment_ids,
            email_verifier=email_verifier,
        )
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()

    output(result, fmt, out=out)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _read_csv_as_dicts(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
