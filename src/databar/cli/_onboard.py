"""
`databar onboard` — interactive first-run setup wizard.

Guides the user through:
  1. Displaying the Databar welcome banner
  2. API key entry & verification
  3. PATH detection & optional auto-fix
  4. Usage preference (CLI / Python SDK / both)
  5. Optional ~/.claude/CLAUDE.md registration for Claude Code
  6. Tailored next-steps cheatsheet
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# ASCII banner
# ---------------------------------------------------------------------------

BANNER = r"""
  ____        _        _
 |  _ \  __ _| |_ __ _| |__   __ _ _ __
 | | | |/ _` | __/ _` | '_ \ / _` | '__|
 | |_| | (_| | || (_| | |_) | (_| | |
 |____/ \__,_|\__\__,_|_.__/ \__,_|_|

"""

TAGLINE = "Data enrichment at your fingertips."

# ---------------------------------------------------------------------------
# Config helpers (mirrors _auth.py)
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".databar"
CONFIG_FILE = CONFIG_DIR / "config"
_KEY_PREFIX = "api_key="
_PREF_PREFIX = "preferred_interface="

CLAUDE_MD_DIR = Path.home() / ".claude"
CLAUDE_MD_FILE = CLAUDE_MD_DIR / "CLAUDE.md"
_CLAUDE_SENTINEL = "<!-- databar -->"
_CLAUDE_STUB = """\n<!-- databar -->\n## Databar\nWhen the user asks you to use Databar, always run `databar agent-guide` first\nto get the full usage guide before doing anything else.\n<!-- /databar -->\n"""


def _save_key(api_key: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if CONFIG_FILE.exists():
        lines = [
            l for l in CONFIG_FILE.read_text().splitlines()
            if not l.startswith(_KEY_PREFIX)
        ]
    lines.append(f"{_KEY_PREFIX}{api_key}")
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    CONFIG_FILE.chmod(0o600)


def _save_preference(pref: str) -> None:
    lines: list[str] = []
    if CONFIG_FILE.exists():
        lines = [
            l for l in CONFIG_FILE.read_text().splitlines()
            if not l.startswith(_PREF_PREFIX)
        ]
    lines.append(f"{_PREF_PREFIX}{pref}")
    CONFIG_FILE.write_text("\n".join(lines) + "\n")


def _get_bin_dir() -> Path:
    return Path(sys.executable).parent


def _databar_on_path() -> bool:
    return shutil.which("databar") is not None


def _detect_shell_profile() -> Path | None:
    shell = os.environ.get("SHELL", "")
    home = Path.home()
    if "zsh" in shell:
        return home / ".zshrc"
    if "bash" in shell:
        profile = home / ".bash_profile"
        return profile if profile.exists() else home / ".bashrc"
    return None


def _add_to_path(bin_dir: Path) -> bool:
    """Append export PATH line to the detected shell profile. Returns True on success."""
    profile = _detect_shell_profile()
    if profile is None:
        return False
    export_line = f'\nexport PATH="{bin_dir}:$PATH"  # added by databar onboard\n'
    with open(profile, "a") as f:
        f.write(export_line)
    return True


# ---------------------------------------------------------------------------
# Onboard steps
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    banner_text = Text(BANNER, style="bold cyan")
    tagline_text = Text(f"  {TAGLINE}\n", style="dim")
    console.print(banner_text, end="")
    console.print(tagline_text)
    console.print(Rule(style="cyan"))
    console.print()


def _step_api_key() -> str | None:
    """Prompt for API key, save it, and verify with a whoami call."""
    console.print("[bold]Step 1 — Connect your account[/bold]")
    console.print(
        "[dim]Get your API key at [link=https://databar.ai]databar.ai[/link] "
        "→ Settings → API Keys[/dim]\n"
    )

    existing_key: str | None = None
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.startswith(_KEY_PREFIX):
                existing_key = line[len(_KEY_PREFIX):].strip()
                break
    if not existing_key:
        existing_key = os.environ.get("DATABAR_API_KEY", "").strip() or None

    if existing_key:
        masked = existing_key[:6] + "•" * (len(existing_key) - 10) + existing_key[-4:]
        use_existing = Confirm.ask(
            f"  Found existing key [bold]{masked}[/bold] — use it?",
            default=True,
        )
        if use_existing:
            api_key = existing_key
        else:
            api_key = Prompt.ask("  Enter your Databar API key", password=True).strip()
    else:
        api_key = Prompt.ask("  Enter your Databar API key", password=True).strip()

    if not api_key:
        console.print("[yellow]  Skipped — you can run `databar login` later.[/yellow]\n")
        return None

    console.print("  [dim]Verifying…[/dim]", end="")
    try:
        from databar.client import DatabarClient
        client = DatabarClient(api_key=api_key)
        user = client.get_user()
        client.close()
        _save_key(api_key)
        console.print(
            f"\r  [bold green]✓[/bold green] Authenticated as "
            f"[bold]{user.first_name or user.email}[/bold] "
            f"([dim]{user.balance:.0f} credits[/dim])\n"
        )
        return api_key
    except Exception as e:
        console.print(f"\r  [bold red]✗[/bold red] Could not verify key: {e}\n")
        console.print("  [dim]Key not saved. Run `databar login` to try again.[/dim]\n")
        return None


def _step_path() -> None:
    """Check PATH and offer to fix it."""
    console.print("[bold]Step 2 — Fix PATH (so `databar` works anywhere)[/bold]")

    if _databar_on_path():
        console.print("  [bold green]✓[/bold green] `databar` is already on your PATH.\n")
        return

    bin_dir = _get_bin_dir()
    console.print(
        f"  [yellow]![/yellow] `databar` is not on PATH.\n"
        f"  It's installed at: [bold]{bin_dir}/databar[/bold]\n"
    )

    profile = _detect_shell_profile()
    profile_label = str(profile) if profile else "your shell profile"
    fix = Confirm.ask(
        f"  Add `{bin_dir}` to PATH in {profile_label} automatically?",
        default=True,
    )
    if fix:
        ok = _add_to_path(bin_dir)
        if ok:
            console.print(
                f"  [bold green]✓[/bold green] Added to {profile_label}.\n"
                f"  Run [bold]source {profile_label}[/bold] or open a new terminal to apply.\n"
            )
        else:
            console.print(
                f"  [yellow]Could not detect your shell profile.[/yellow]\n"
                f"  Add this manually:\n\n"
                f"    [bold]export PATH=\"{bin_dir}:$PATH\"[/bold]\n"
            )
    else:
        console.print(
            f"  [dim]Skipped. Use the full path for now: [bold]{bin_dir}/databar[/bold][/dim]\n"
        )


def _step_preference() -> str:
    """Ask how the user plans to use Databar and return their choice."""
    console.print("[bold]Step 3 — How do you plan to use Databar?[/bold]\n")
    console.print("  [bold cyan]1[/bold cyan]  CLI       — terminal commands, scripts, AI agents (Claude Code etc.)")
    console.print("  [bold cyan]2[/bold cyan]  Python    — import DatabarClient in your Python code")
    console.print("  [bold cyan]3[/bold cyan]  Both      — I'll use whichever fits the task\n")

    choice = Prompt.ask("  Your choice", choices=["1", "2", "3"], default="3")
    pref_map = {"1": "cli", "2": "python", "3": "both"}
    pref = pref_map[choice]
    _save_preference(pref)
    console.print()
    return pref


def _step_claude_md() -> None:
    """Optionally register Databar in the user's global ~/.claude/CLAUDE.md."""
    console.print("[bold]Step 4 — Claude Code integration (optional)[/bold]\n")

    already = (
        CLAUDE_MD_FILE.exists()
        and _CLAUDE_SENTINEL in CLAUDE_MD_FILE.read_text()
    )
    if already:
        console.print(
            "  [bold green]✓[/bold green] Databar is already registered in "
            f"[dim]{CLAUDE_MD_FILE}[/dim].\n"
        )
        return

    console.print(
        f"  Adding a small entry to [bold]{CLAUDE_MD_FILE}[/bold] tells Claude Code\n"
        "  to always run [bold]databar agent-guide[/bold] first, so it knows exactly\n"
        "  how to use Databar without guessing.\n"
    )
    add = Confirm.ask(
        "  Add Databar to your global Claude Code config (~/.claude/CLAUDE.md)?",
        default=True,
    )
    if add:
        CLAUDE_MD_DIR.mkdir(parents=True, exist_ok=True)
        with open(CLAUDE_MD_FILE, "a") as f:
            f.write(_CLAUDE_STUB)
        console.print(
            f"  [bold green]✓[/bold green] Added to {CLAUDE_MD_FILE}.\n"
            "  Claude Code will now pick up Databar instructions automatically "
            "in every project.\n"
        )
    else:
        console.print("  [dim]Skipped.[/dim]\n")


def _step_next_steps(pref: str) -> None:
    """Print tailored next steps based on preference."""
    console.print(Rule(style="cyan"))
    console.print()
    console.print("[bold green]You're all set![/bold green] Here's where to start:\n")

    if pref in ("cli", "both"):
        console.print(Panel(
            "[bold]CLI Quick Start[/bold]\n\n"
            "  databar enrich list                          [dim]# browse enrichments[/dim]\n"
            "  databar enrich get <id>                      [dim]# inspect params[/dim]\n"
            "  databar enrich run <id> --params '{...}'     [dim]# run one row[/dim]\n"
            "  databar enrich bulk <id> --input data.csv    [dim]# bulk from CSV[/dim]\n\n"
            "  databar waterfall list\n"
            "  databar waterfall run <identifier> --params '{...}'\n\n"
            "  databar table create --name 'Leads' --columns 'email,name'\n"
            "  databar table rows <uuid> --format json\n\n"
            "  [dim]Tip: always use --format json when piping output.[/dim]",
            border_style="cyan",
            title="[cyan]CLI[/cyan]",
        ))

    if pref in ("python", "both"):
        console.print(Panel(
            "[bold]Python SDK Quick Start[/bold]\n\n"
            "  from databar import DatabarClient\n\n"
            "  client = DatabarClient()  [dim]# reads DATABAR_API_KEY from env or ~/.databar/config[/dim]\n\n"
            "  enrichments = client.list_enrichments(q='email')\n"
            "  result = client.run_enrichment_sync(123, {'email': 'alice@example.com'})\n\n"
            "  tables = client.list_tables()\n"
            "  rows = client.get_rows(table.identifier)   [dim]# returns RowsResponse[/dim]\n"
            "  rows.data                                  [dim]# list of row dicts[/dim]",
            border_style="cyan",
            title="[cyan]Python[/cyan]",
        ))

    console.print(
        "\n  [dim]Full reference: [bold]databar agent-guide[/bold] | "
        "Docs: [link=https://build.databar.ai]build.databar.ai[/link][/dim]\n"
    )


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

def onboard() -> None:
    """Interactive setup wizard — configure auth, PATH, and get started."""
    _print_banner()
    console.print(
        "  Welcome to [bold cyan]Databar[/bold cyan]! This wizard takes ~1 minute "
        "and sets up everything you need.\n"
        "  [dim]Press Ctrl+C at any time to exit.[/dim]\n"
    )

    try:
        _step_api_key()
        _step_path()
        pref = _step_preference()
        _step_claude_md()
        _step_next_steps(pref)
    except (KeyboardInterrupt, typer.Abort):
        console.print("\n\n[dim]Onboarding cancelled. Run `databar onboard` any time to restart.[/dim]")
        raise typer.Exit(0)
