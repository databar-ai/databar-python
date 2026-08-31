"""
Shared output formatting helpers for the Databar CLI.

All CLI commands use these helpers to ensure consistent output.
Supports three output formats:
  - table  (default) — rich-rendered terminal table
  - json   — envelope JSON to stdout, pipe-friendly
  - csv    — CSV to stdout or --out file
"""

from __future__ import annotations

import csv
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any, NoReturn, Optional, Union

import click
import typer
from rich import print_json as rich_print_json
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from databar.exceptions import (
    DatabarAuthError,
    DatabarError,
    DatabarGoneError,
    DatabarInsufficientCreditsError,
    DatabarNotFoundError,
    DatabarRateLimitError,
    DatabarTaskCancelledError,
    DatabarTaskFailedError,
    DatabarTimeoutError,
    DatabarValidationError,
)

# Force UTF-8 on stdout/stderr before any Console is created. On Windows, a
# redirected pipe uses the locale encoding (e.g. cp1251) and crashes on
# characters outside that codepage (DEV-5080).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass

console = Console()
# soft_wrap=True: don't hard-wrap mid-word (breaks naive stderr matching).
err_console = Console(stderr=True, soft_wrap=True)


class OutputFormat(str, Enum):
    TABLE = "table"
    JSON = "json"
    CSV = "csv"


# Exit codes by error class (ticket DEV-5133).
_EXIT_USAGE = 2
_EXIT_AUTH = 3
_EXIT_NOT_FOUND = 4
_EXIT_VALIDATION = 5
_EXIT_GENERIC = 1

_HINTS = {
    "auth_missing": "Run `databar login` or set the DATABAR_API_KEY environment variable.",
    "auth_invalid": "Check your API key at databar.ai → Settings → API Keys.",
}


def _current_format() -> OutputFormat:
    """Read --format from the active Click/Typer context, defaulting to table."""
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return OutputFormat.TABLE
    fmt = ctx.params.get("fmt")
    if isinstance(fmt, OutputFormat):
        return fmt
    if isinstance(fmt, str):
        try:
            return OutputFormat(fmt)
        except ValueError:
            return OutputFormat.TABLE
    return OutputFormat.TABLE


def _plain(message: str) -> str:
    """Strip Rich markup so JSON/stderr consumers get clean text."""
    try:
        return Text.from_markup(message).plain
    except Exception:
        return message


def _classify(
    err: Union[str, DatabarError, BaseException],
    code: Optional[str],
) -> tuple[str, int, str, Optional[str]]:
    """Return (code, exit_code, message, hint)."""
    if isinstance(err, DatabarError):
        message = _plain(err.message if hasattr(err, "message") else str(err))
        if code is None:
            if isinstance(err, DatabarAuthError):
                code = "auth_invalid"
            elif isinstance(err, DatabarNotFoundError):
                code = "not_found"
            elif isinstance(err, DatabarValidationError):
                code = "validation"
            elif isinstance(err, DatabarRateLimitError):
                code = "rate_limit"
            elif isinstance(err, DatabarInsufficientCreditsError):
                code = "insufficient_credits"
            elif isinstance(err, DatabarGoneError):
                code = "gone"
            elif isinstance(err, DatabarTaskFailedError):
                code = "task_failed"
            elif isinstance(err, DatabarTaskCancelledError):
                code = "task_cancelled"
            elif isinstance(err, DatabarTimeoutError):
                code = "timeout"
            else:
                code = "server_error"
    else:
        message = _plain(str(err))
        if code is None:
            code = "usage"

    exit_map = {
        "auth_missing": _EXIT_AUTH,
        "auth_invalid": _EXIT_AUTH,
        "not_found": _EXIT_NOT_FOUND,
        "usage": _EXIT_USAGE,
        "validation": _EXIT_VALIDATION,
    }
    exit_code = exit_map.get(code, _EXIT_GENERIC)
    hint = _HINTS.get(code)
    return code, exit_code, message, hint


# ---------------------------------------------------------------------------
# Core output functions
# ---------------------------------------------------------------------------


def _print_json(payload: Any) -> None:
    """Print a JSON payload to stdout (Rich-highlighted when on a TTY)."""
    rich_print_json(json.dumps(payload, default=str))


def output_json(data: Any) -> None:
    """Print data as a success envelope: {"ok": true, "data": ...}."""
    _print_json({"ok": True, "data": data})


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
    dest = open(out, "w", newline="", encoding="utf-8") if out else sys.stdout
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


def error(
    message: Union[str, DatabarError, BaseException],
    *,
    code: Optional[str] = None,
    hint: Optional[str] = None,
    exit_code: Optional[int] = None,
) -> NoReturn:
    """
    Emit an error and exit.

    When --format json: write {"ok": false, "error": {...}} to stdout.
    Otherwise: styled prose to stderr (no mid-word hard wrap).
    """
    err_code, default_exit, plain_msg, default_hint = _classify(message, code)
    final_hint = hint if hint is not None else default_hint
    final_exit = exit_code if exit_code is not None else default_exit

    if _current_format() == OutputFormat.JSON:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {"code": err_code, "message": plain_msg},
        }
        if final_hint:
            payload["error"]["hint"] = final_hint
        _print_json(payload)
    else:
        # Escape user text so accidental [bold] in messages isn't re-parsed;
        # auth_missing still embeds intentional Rich markup in the source string.
        if isinstance(message, str) and "[" in message and not isinstance(message, DatabarError):
            # Keep intentional Rich markup from our own string literals.
            err_console.print(f"[bold red]Error:[/bold red] {message}")
        else:
            err_console.print(f"[bold red]Error:[/bold red] {escape(plain_msg)}")

    raise typer.Exit(code=final_exit)


def success(message: str) -> None:
    """Print a styled success message (no-op in JSON mode — keep stdout clean)."""
    if _current_format() == OutputFormat.JSON:
        return
    console.print(f"[bold green]{message}[/bold green]")


def info(message: str) -> None:
    """Print a dim informational message (no-op in JSON mode)."""
    if _current_format() == OutputFormat.JSON:
        return
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
