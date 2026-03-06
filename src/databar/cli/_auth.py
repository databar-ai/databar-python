"""
API key management and auth-related CLI commands.

Key resolution order (same as MCP server):
  1. DATABAR_API_KEY environment variable
  2. ~/.databar/config file
  3. Error with helpful message pointing to `databar login`
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from databar.client import DatabarClient
from databar.exceptions import DatabarError

from ._output import console, error, output, success, OutputFormat

CONFIG_DIR = Path.home() / ".databar"
CONFIG_FILE = CONFIG_DIR / "config"

_KEY_PREFIX = "api_key="


def get_api_key() -> str:
    """
    Resolve the API key using the standard priority order.
    Exits with a helpful error if no key is found.
    """
    key = os.environ.get("DATABAR_API_KEY")
    if key:
        return key.strip()

    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.startswith(_KEY_PREFIX):
                key = line[len(_KEY_PREFIX):].strip()
                if key:
                    return key

    error(
        "No API key found.\n"
        "  Run [bold]databar login[/bold] to save your key, or set the "
        "[bold]DATABAR_API_KEY[/bold] environment variable.\n"
        "  Get your key at [link=https://databar.ai]databar.ai[/link] → Integrations."
    )
    raise typer.Exit(1)  # unreachable but satisfies type checkers


def get_client() -> DatabarClient:
    """Return a configured DatabarClient using the resolved API key."""
    return DatabarClient(api_key=get_api_key())


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

app = typer.Typer(help="Authentication commands.")


@app.command("login")
def login(
    api_key: str = typer.Option(
        None,
        "--api-key",
        "-k",
        help="Your Databar API key. Prompted interactively if not provided.",
        hide_input=True,
    )
) -> None:
    """Save your Databar API key to ~/.databar/config."""
    if not api_key:
        api_key = typer.prompt("Enter your Databar API key", hide_input=True)

    api_key = api_key.strip()
    if not api_key:
        error("API key cannot be empty.")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(f"{_KEY_PREFIX}{api_key}\n")
    CONFIG_FILE.chmod(0o600)

    success(f"API key saved to {CONFIG_FILE}")
    console.print("[dim]Tip: You can also set DATABAR_API_KEY as an environment variable.[/dim]")


@app.command("whoami")
def whoami(
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f", help="Output format.")
) -> None:
    """Show current user info and credit balance."""
    client = get_client()
    try:
        user = client.get_user()
    except DatabarError as e:
        error(str(e))
    finally:
        client.close()

    data = {
        "name": user.first_name or "(no name)",
        "email": user.email,
        "balance": f"{user.balance:.2f} credits",
        "plan": user.plan,
    }
    output(data, fmt)
