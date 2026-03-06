"""
Shared output formatting helpers for the Databar CLI.

All CLI commands use these helpers to ensure consistent output.
Supports three output formats:
  - table  (default) — rich-rendered terminal table
  - json   — raw JSON to stdout, pipe-friendly
  - csv    — CSV to stdout or --out file
"""

from __future__ import annotations

import csv
import io
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from rich import print_json as rich_print_json
from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


class OutputFormat(str, Enum):
    TABLE = "table"
    JSON = "json"
    CSV = "csv"


# ---------------------------------------------------------------------------
# Core output functions
# ---------------------------------------------------------------------------


def output_json(data: Any) -> None:
    """Print data as syntax-highlighted JSON."""
    rich_print_json(json.dumps(data, default=str))


def output_table(rows: list[dict], columns: list[str] | None = None) -> None:
    """
    Render a list of dicts as a rich table.

    columns controls the column order/subset. If None, all keys from the
    first row are used.
    """
    if not rows:
        console.print("[dim]No results.[/dim]")
        return

    cols = columns or list(rows[0].keys())
    table = Table(show_header=True, header_style="bold cyan")
    for col in cols:
        table.add_column(col)

    for row in rows:
        table.add_row(*[_cell(row.get(col)) for col in cols])

    console.print(table)


def output_csv(rows: list[dict], columns: list[str] | None = None, out: Path | None = None) -> None:
    """
    Write rows as CSV.

    If out is given, writes to that file. Otherwise writes to stdout.
    """
    if not rows:
        return

    cols = columns or list(rows[0].keys())
    dest = open(out, "w", newline="") if out else sys.stdout
    writer = csv.DictWriter(dest, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    if out and not dest.closed:
        dest.close()
        console.print(f"[green]Saved to {out}[/green]")


def output(
    data: Any,
    fmt: OutputFormat,
    table_columns: list[str] | None = None,
    out: Path | None = None,
) -> None:
    """
    Unified output dispatcher — routes to the right format handler.

    data may be:
      - a list of dicts  → table/csv renders rows
      - a dict           → wrapped in a list for table, raw for json
      - any other value  → rendered as json
    """
    if fmt == OutputFormat.JSON:
        output_json(data)
        return

    rows = _to_rows(data)

    if fmt == OutputFormat.CSV:
        output_csv(rows, columns=table_columns, out=out)
    else:
        output_table(rows, columns=table_columns)


def error(message: str, exit_code: int = 1) -> None:
    """Print a styled error message to stderr and exit."""
    err_console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(code=exit_code)


def success(message: str) -> None:
    """Print a styled success message."""
    console.print(f"[bold green]{message}[/bold green]")


def info(message: str) -> None:
    """Print a dim informational message."""
    console.print(f"[dim]{message}[/dim]")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def _to_rows(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [r if isinstance(r, dict) else {"value": r} for r in data]
    if isinstance(data, dict):
        return [data]
    return [{"value": str(data)}]
