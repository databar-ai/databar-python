"""
CLI commands for tasks.

  databar task get <task-id> [--format] [--poll] [--partial]
  databar task cancel <task-id>
"""

from __future__ import annotations

import typer

from databar.exceptions import DatabarError, DatabarTaskFailedError, DatabarTimeoutError

from ._auth import get_client
from ._output import OutputFormat, console, error, info, output

app = typer.Typer(help="Check the status of async tasks.")

_STATUS_STYLES = {
    "completed": "bold green",
    "partially_completed": "green",
    "processing": "yellow",
    "failed": "bold red",
    "cancelled": "bold yellow",
    "gone": "dim",
}


def _print_status(task) -> None:
    style = _STATUS_STYLES.get(task.status.lower(), "white")
    console.print(f"[{style}]Status: {task.status}[/{style}]")
    if task.progress:
        p = task.progress
        console.print(
            f"[dim]Progress: {p.get('completed', 0)} completed, "
            f"{p.get('failed', 0)} no data, {p.get('processing', 0)} still running "
            f"of {p.get('total', 0)}[/dim]"
        )


@app.command("get")
def get_task(
    task_id: str = typer.Argument(..., help="Task ID returned by a run or bulk-run call."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    poll: bool = typer.Option(
        False,
        "--poll",
        help="Keep polling until the task completes (or times out).",
    ),
    partial: bool = typer.Option(
        False,
        "--partial",
        help="For a running bulk task, also show the rows that have already finished.",
    ),
) -> None:
    """Get the status and result of a task."""
    client = get_client()
    try:
        if poll:
            info(f"Polling task {task_id}…")
            data = client.poll_task(task_id)
            output(data, fmt)
        else:
            task = client.get_task(task_id, include_partial=partial)
            _print_status(task)
            if task.data is not None:
                output(task.data, fmt)
            elif task.error:
                error_val = task.error
                msg = "; ".join(error_val) if isinstance(error_val, list) else error_val
                console.print(f"[red]Error: {msg}[/red]")
    except DatabarTaskFailedError as exc:
        error(str(exc))
    except DatabarTimeoutError as exc:
        error(str(exc))
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()


@app.command("cancel")
def cancel_task(
    task_id: str = typer.Argument(..., help="Task ID of a running task."),
) -> None:
    """Stop a running task. Rows that already finished keep their results."""
    client = get_client()
    try:
        task = client.cancel_task(task_id)
        _print_status(task)
        info(f"Cancelled. Collect what finished with: databar task get {task_id}")
    except DatabarError as exc:
        error(str(exc))
    finally:
        client.close()
