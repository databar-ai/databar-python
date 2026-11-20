"""One-line upgrade notice when the API reports a newer release (DEV-5305).

The API sends ``X-Databar-Latest-Version`` on every response, so the check costs no extra
request and needs no background job. The notice goes to stderr, so ``--format json`` on
stdout stays clean; ``DATABAR_NO_UPDATE_NOTICE=1`` turns it off.
"""

from __future__ import annotations

import os
import re

from databar import __version__

from ._output import err_console

_shown = False


def _parts(version: str) -> tuple[int, ...] | None:
    match = re.match(r"^(\d+(?:\.\d+)*)", version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_outdated(current: str, latest: str) -> bool:
    current_parts, latest_parts = _parts(current), _parts(latest)
    if current_parts is None or latest_parts is None:
        return False
    width = max(len(current_parts), len(latest_parts))
    pad = lambda parts: parts + (0,) * (width - len(parts))  # noqa: E731
    return pad(latest_parts) > pad(current_parts)


def notify_if_outdated(latest: str) -> None:
    global _shown
    if _shown or os.environ.get("DATABAR_NO_UPDATE_NOTICE"):
        return
    if not is_outdated(__version__, latest):
        return
    _shown = True
    err_console.print(
        f"[yellow]databar {__version__} is outdated, latest is {latest}: pip install -U databar[/yellow]",
        highlight=False,
    )
