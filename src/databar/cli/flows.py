"""
CLI commands for flows.

  databar flow list [--query] [--format]
  databar flow get  <flow-id> [--format]
  databar flow run  <flow-id> --inputs '{"email":"a@b.com"}' [--format] [--raw]
  databar flow versions <flow-id> [--format]
  databar flow restore  <flow-id> <version> [--yes]

Editing a graph is deliberately not a CLI command — that is an editor or SDK
job. Reading the history and rolling back are, because that is what you reach
for from a terminal when a flow started returning nothing.
"""

from __future__ import annotations

import json
from typing import Optional

import typer

from databar.exceptions import DatabarError

from ._auth import get_client
from ._output import OutputFormat, console, error, info, output

app = typer.Typer(help="List and run saved flows.")


@app.command("list")
def list_flows(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Filter by name/description."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output file (for CSV format)."),
) -> None:
    """List saved flows in the workspace."""
    client = get_client()
    try:
        flows = client.list_flows()
    except DatabarError as e:
        error(e)
    finally:
        client.close()

    if query:
        q = query.lower()
        flows = [
            f for f in flows
            if q in f.name.lower() or q in f.description.lower() or q in f.id.lower()
        ]

    if not flows:
        info("No flows found.")
        output([], fmt, out=out)
        return

    rows = [
        {
            "id": f.id,
            "name": f.name,
            "inputs": len(f.inputs),
            "description": f.description[:60] + ("…" if len(f.description) > 60 else ""),
        }
        for f in flows
    ]
    output(rows, fmt, table_columns=["id", "name", "inputs", "description"], out=out)


@app.command("get")
def get_flow(
    flow_id: str = typer.Argument(..., help="Flow id."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Get details for a specific flow."""
    client = get_client()
    try:
        f = client.get_flow(flow_id)
    except DatabarError as exc:
        error(exc)
    finally:
        client.close()

    if fmt == OutputFormat.JSON:
        output(f.model_dump(), fmt)
        return

    console.print(f"\n[bold cyan]Flow:[/bold cyan] {f.name} ({f.id})")
    console.print(f"\n{f.description}\n")

    if f.inputs:
        console.print("[bold]Inputs:[/bold]")
        rows = [
            {
                "id": inp.id,
                "required": "yes" if inp.required else "no",
                "type": inp.type,
                "description": inp.description,
            }
            for inp in f.inputs
        ]
        output(rows, OutputFormat.TABLE, table_columns=["id", "required", "type", "description"])


@app.command("run")
def run_flow(
    flow_id: str = typer.Argument(..., help="Flow id."),
    inputs_json: str = typer.Option(..., "--inputs", "-i", help='JSON inputs, e.g. \'{"email":"a@b.com"}\''),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    raw: bool = typer.Option(False, "--raw", help="Print raw result without formatting."),
) -> None:
    """Run a flow and wait for results."""
    try:
        inputs = json.loads(inputs_json)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON for --inputs: {e}")

    client = get_client()
    try:
        info(f"Running flow '{flow_id}'…")
        result = client.run_flow_sync(flow_id, inputs)
    except DatabarError as exc:
        error(exc)
    finally:
        client.close()

    if raw:
        console.print(result)
        return

    output(result, fmt)


@app.command("versions")
def list_versions(
    flow_id: str = typer.Argument(..., help="Flow id."),
    limit: int = typer.Option(50, "--limit", "-n", help="How many versions to show (newest first)."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Show the flow's edit history: what changed, who changed it and from where."""
    client = get_client()
    try:
        versions = client.list_flow_versions(flow_id, limit=limit)
    except DatabarError as exc:
        error(exc)
    finally:
        client.close()

    if fmt == OutputFormat.JSON:
        output([v.model_dump() for v in versions], fmt)
        return

    rows = [
        {
            "version": v.number,
            "changed": ", ".join(v.changed_fields) or "-",
            "source": v.source,
            "by": v.created_by or "-",
            "at": v.created_at,
            "restored_from": v.restored_from if v.restored_from is not None else "-",
        }
        for v in versions
    ]
    output(rows, fmt, table_columns=["version", "changed", "source", "by", "at", "restored_from"])


@app.command("restore")
def restore_version(
    flow_id: str = typer.Argument(..., help="Flow id."),
    version: int = typer.Argument(..., help="Version number from `databar flow versions`."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Roll the flow back to an earlier version.

    Nothing is overwritten: the old config is stored as a new version, so the
    rollback is itself revertible.
    """
    if not yes and not typer.confirm(f"Restore v{version} of {flow_id}? This adds a new version."):
        raise typer.Abort()

    client = get_client()
    try:
        result = client.restore_flow_version(flow_id, version)
    except DatabarError as exc:
        error(exc)
    finally:
        client.close()

    if fmt == OutputFormat.JSON:
        output(result.model_dump(), fmt)
        return

    info(f"Restored v{version} of {result.flow.name} — saved as v{result.version.number}.")
