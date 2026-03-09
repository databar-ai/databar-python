"""
CLI commands for tasks.

  databar task get <task-id> [--format] [--poll]
"""

from __future__ import annotations

import typer

from databar.exceptions import DatabarError, DatabarTaskFailedError, DatabarTimeoutError

from ._auth import get_client
from ._output import OutputFormat, console, error, info, output

app = typer.Typer(help="Check the status of async tasks.")


@app.command("get")
def get_task(
    task_id: str = typer.Argument(..., help="Task ID returned by a run or bulk-run call."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
    poll: bool = typer.Option(
        False,
        "--poll",
        help="Keep polling until the task completes (or times out).",
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
            task = client.get_task(task_id)
            status = task.status
            style = {
                "completed": "bold green",
                "processing": "yellow",
                "failed": "bold red",
                "gone": "dim",
            }.get(status.lower(), "white")

            console.print(f"[{style}]Status: {status}[/{style}]")
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
