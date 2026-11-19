"""
API key management and auth-related CLI commands.

Key resolution order (same as MCP server):
  1. DATABAR_API_KEY environment variable
  2. ~/.databar/config file
  3. Error with helpful message pointing to `databar login`
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

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
                key = line[len(_KEY_PREFIX) :].strip()
                if key:
                    return key

    error(
        "No API key found.\n"
        "  Run [bold]databar login[/bold] to sign in via browser, or set the "
        "[bold]DATABAR_API_KEY[/bold] environment variable.\n"
        "  Or paste a key with [bold]databar login --api-key[/bold].",
        code="auth_missing",
    )
    raise typer.Exit(1)  # unreachable but satisfies type checkers


def get_client() -> DatabarClient:
    """Return a configured DatabarClient using the resolved API key."""
    from ._update_notice import notify_if_outdated

    client = DatabarClient(api_key=get_api_key(), client_source="cli")
    client.on_latest_version = notify_if_outdated
    return client


def _save_api_key(api_key: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Preserve non-key lines (preferred_interface, etc.) when rewriting.
    other_lines: list[str] = []
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if not line.startswith(_KEY_PREFIX):
                other_lines.append(line)
    body = "\n".join([f"{_KEY_PREFIX}{api_key}", *other_lines]).rstrip() + "\n"
    CONFIG_FILE.write_text(body)
    CONFIG_FILE.chmod(0o600)


def _path_hint() -> None:
    if shutil.which("databar") is not None:
        return
    import sys

    bin_dir = Path(sys.executable).parent
    console.print(
        f"\n[yellow]Note:[/yellow] The [bold]databar[/bold] command is not on your PATH.\n"
        f"Add this to your shell profile ([dim]~/.zshrc[/dim] or [dim]~/.bashrc[/dim]):\n\n"
        f'  [bold]export PATH="{bin_dir}:$PATH"[/bold]\n\n'
        f"Then restart your terminal, or run:\n\n"
        f"  [bold]source ~/.zshrc[/bold]\n\n"
        f"Until then, use the full path: [bold]{bin_dir}/databar[/bold]"
    )


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

app = typer.Typer(help="Authentication commands.")


@app.command("login")
def login(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        "-k",
        help="Paste an API key instead of opening the browser.",
        hide_input=True,
    ),
) -> None:
    """Sign in to Databar (opens the browser) and save your API key."""
    if api_key is not None:
        # Explicit --api-key (possibly empty → interactive paste).
        if not api_key:
            api_key = typer.prompt("Enter your Databar API key", hide_input=True)
        api_key = api_key.strip()
        if not api_key:
            error("API key cannot be empty.")
        _save_api_key(api_key)
        success(f"API key saved to {CONFIG_FILE}")
        console.print("[dim]Tip: You can also set DATABAR_API_KEY as an environment variable.[/dim]")
        _path_hint()
        return

    from ._oauth import run_browser_login

    def _print_url(url: str, *, opened: bool) -> None:
        if opened:
            console.print("[dim]Opening browser for Databar login…[/dim]")
        else:
            console.print("Open this URL in your browser to continue:")
        console.print(f"  {url}")

    try:
        creds = run_browser_login(print_url=_print_url)
    except RuntimeError as exc:
        error(str(exc))

    _save_api_key(creds["api_key"])
    email = creds.get("email") or ""
    if email:
        success(f"Logged in as {email}")
    else:
        success(f"API key saved to {CONFIG_FILE}")
    console.print(f"[dim]Credentials saved to {CONFIG_FILE}[/dim]")
    _path_hint()


@app.command("logout")
def logout() -> None:
    """Sign out: revoke this CLI's key on the server and remove it from ~/.databar/config."""
    if not CONFIG_FILE.exists():
        console.print("[dim]Already logged out — no config file found.[/dim]")
        return

    lines = CONFIG_FILE.read_text().splitlines()
    saved_key = next(
        (line[len(_KEY_PREFIX) :].strip() for line in lines if line.startswith(_KEY_PREFIX)),
        "",
    )
    revoked = None
    if saved_key:
        from ._oauth import revoke_sign_in

        revoked = revoke_sign_in(saved_key)

    other_lines = [line for line in lines if not line.startswith(_KEY_PREFIX)]
    if other_lines:
        CONFIG_FILE.write_text("\n".join(other_lines).rstrip() + "\n")
        CONFIG_FILE.chmod(0o600)
    else:
        CONFIG_FILE.unlink(missing_ok=True)

    if revoked:
        success("Logged out — this CLI's API key is revoked and removed from local config.")
        return
    success("Logged out — API key removed from local config.")
    if revoked is None and saved_key:
        console.print(
            "[dim]Could not reach Databar to revoke the key; it still works until you "
            "revoke \"Databar CLI\" in Settings → MCP & API → Connected apps.[/dim]"
        )


@app.command("whoami")
def whoami(
    fmt: OutputFormat = typer.Option(
        OutputFormat.TABLE, "--format", "--output", "-f", help="Output format."
    ),
) -> None:
    """Show current user info and credit balance."""
    client = get_client()
    try:
        user = client.get_user()
    except DatabarError as e:
        error(e)
    finally:
        client.close()

    from databar import __version__

    from ._update_notice import is_outdated

    data = {
        "name": user.first_name or "(no name)",
        "email": user.email,
        "balance": f"{user.balance:.2f} credits",
        "plan": user.plan,
        "version": __version__,
        "latest_version": client.latest_version,
    }
    if fmt != OutputFormat.JSON:
        latest = data.pop("latest_version")
        if latest and is_outdated(__version__, latest):
            data["version"] = f"{__version__} (latest {latest})"
    output(data, fmt)
