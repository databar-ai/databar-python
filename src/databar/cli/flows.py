"""
CLI commands for flows.

  databar flow list [--query] [--format]
  databar flow get  <flow-id> [--format]
  databar flow run  <flow-id> --inputs '{"email":"a@b.com"}' [--format] [--raw]
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
) -> None:
    """List saved flows in the workspace."""
    client = get_client()
    try:
        flows = client.list_flows()
    except DatabarError as e:
        error(str(e))
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
    output(rows, fmt, table_columns=["id", "name", "inputs", "description"])


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
        error(str(exc))
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
        error(str(exc))
    finally:
        client.close()

    if raw:
        console.print(result)
        return

    output(result, fmt)
