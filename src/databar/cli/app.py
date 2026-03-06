"""
Databar CLI root application.

Registers all subcommand groups and exposes top-level login/whoami commands.
"""

from __future__ import annotations

import typer

from databar import __version__

from . import enrichments, tables, tasks, waterfalls
from ._auth import app as auth_app

app = typer.Typer(
    name="databar",
    help="Official Databar.ai CLI — run enrichments, manage tables, and more.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Top-level auth commands (login + whoami) live directly on the root app
app.add_typer(auth_app, name=None)  # merged at root level

# Subcommand groups
app.add_typer(enrichments.app, name="enrich")
app.add_typer(waterfalls.app, name="waterfall")
app.add_typer(tables.app, name="table")
app.add_typer(tasks.app, name="task")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"databar {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Databar CLI."""
