"""
CLI commands for workbooks and trash.

  databar workbook list
  databar workbook get <id>
  databar workbook rename <id> --name
  databar workbook delete <id>
  databar workbook duplicate <id>
  databar workbook merge --target <id> --sources id1,id2
  databar workbook add-table <id> [--name]
  databar trash list
  databar trash restore --workbooks id1 [--tables uuid]
  databar trash purge --workbooks id1 [--tables uuid]
"""

from __future__ import annotations

from typing import Optional

import typer

from databar.exceptions import DatabarError

from ._auth import get_client
from ._output import OutputFormat, error, info, output, success

workbook_app = typer.Typer(help="Manage workbooks (multi-sheet documents).")
trash_app = typer.Typer(help="List, restore, or permanently delete trash.")


@workbook_app.command("list")
def list_workbooks(
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """List workbooks in your workspace."""
    client = get_client()
    try:
        workbooks = client.list_workbooks()
    except DatabarError as e:
        error(e)
    finally:
        client.close()

    if not workbooks:
        info("No workbooks found.")
        output([], fmt)
        return

    rows = [
        {
            "id": w.identifier,
            "name": w.name,
            "tables": w.tables_count,
            "updated": w.updated_at,
        }
        for w in workbooks
    ]
    output(rows, fmt, table_columns=["id", "name", "tables", "updated"])


@workbook_app.command("get")
def get_workbook(
    workbook_id: str = typer.Argument(..., help="Workbook identifier (wb_…)."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Show one workbook and its sheets."""
    client = get_client()
    try:
        wb = client.get_workbook(workbook_id)
    except DatabarError as e:
        error(e)
    finally:
        client.close()

    output(
        {
            "id": wb.identifier,
            "name": wb.name,
            "tables": [{"uuid": t.identifier, "name": t.name, "position": t.position} for t in wb.tables],
        },
        fmt,
    )


@workbook_app.command("rename")
def rename_workbook(
    workbook_id: str = typer.Argument(..., help="Workbook identifier (wb_…)."),
    name: str = typer.Option(..., "--name", "-n", help="New name."),
) -> None:
    """Rename a workbook."""
    client = get_client()
    try:
        wb = client.rename_workbook(workbook_id, name)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success(f"Renamed workbook to {wb.name!r}")


@workbook_app.command("delete")
def delete_workbook(
    workbook_id: str = typer.Argument(..., help="Workbook identifier (wb_…)."),
) -> None:
    """Move a workbook to Trash."""
    client = get_client()
    try:
        client.delete_workbook(workbook_id)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success(f"Workbook {workbook_id} moved to trash.")


@workbook_app.command("duplicate")
def duplicate_workbook(
    workbook_id: str = typer.Argument(..., help="Workbook identifier (wb_…)."),
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """Duplicate a workbook."""
    client = get_client()
    try:
        wb = client.duplicate_workbook(workbook_id)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success(f"Duplicated as {wb.identifier}")
    output({"id": wb.identifier, "name": wb.name, "tables": wb.tables_count}, fmt)


@workbook_app.command("merge")
def merge_workbooks(
    target: str = typer.Option(..., "--target", help="Workbook that keeps the sheets."),
    sources: str = typer.Option(..., "--sources", help="Comma-separated workbook ids to fold in."),
) -> None:
    """Merge source workbooks into target."""
    source_ids = [s.strip() for s in sources.split(",") if s.strip()]
    client = get_client()
    try:
        wb = client.merge_workbooks(target, source_ids)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success(f"Merged into {wb.identifier} ({wb.tables_count} sheets)")


@workbook_app.command("add-table")
def add_workbook_table(
    workbook_id: str = typer.Argument(..., help="Workbook identifier (wb_…)."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Sheet name."),
) -> None:
    """Add an empty sheet to a workbook."""
    client = get_client()
    try:
        table = client.add_workbook_table(workbook_id, name=name)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success(f"Added table {table.get('identifier')}")


@trash_app.command("list")
def list_trash(
    fmt: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "--output", "-f"),
) -> None:
    """List items in Trash."""
    client = get_client()
    try:
        items = client.list_trash()
    except DatabarError as e:
        error(e)
    finally:
        client.close()

    if not items:
        info("Trash is empty.")
        output([], fmt)
        return

    rows = [
        {
            "kind": i.kind,
            "id": i.identifier,
            "name": i.name,
            "trashed_at": i.trashed_at,
        }
        for i in items
    ]
    output(rows, fmt, table_columns=["kind", "id", "name", "trashed_at"])


@trash_app.command("restore")
def restore_trash(
    workbooks: Optional[str] = typer.Option(None, "--workbooks", help="Comma-separated workbook ids."),
    tables: Optional[str] = typer.Option(None, "--tables", help="Comma-separated table UUIDs."),
) -> None:
    """Restore workbooks and/or tables from Trash."""
    wb_ids = [s.strip() for s in (workbooks or "").split(",") if s.strip()]
    table_ids = [s.strip() for s in (tables or "").split(",") if s.strip()]
    if not wb_ids and not table_ids:
        error("Pass --workbooks and/or --tables.")
    client = get_client()
    try:
        client.restore_trash(workbooks=wb_ids, tables=table_ids)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success("Restored.")


@trash_app.command("purge")
def purge_trash(
    workbooks: Optional[str] = typer.Option(None, "--workbooks", help="Comma-separated workbook ids."),
    tables: Optional[str] = typer.Option(None, "--tables", help="Comma-separated table UUIDs."),
) -> None:
    """Permanently delete workbooks and/or tables from Trash."""
    wb_ids = [s.strip() for s in (workbooks or "").split(",") if s.strip()]
    table_ids = [s.strip() for s in (tables or "").split(",") if s.strip()]
    if not wb_ids and not table_ids:
        error("Pass --workbooks and/or --tables.")
    client = get_client()
    try:
        client.purge_trash(workbooks=wb_ids, tables=table_ids)
    except DatabarError as e:
        error(e)
    finally:
        client.close()
    success("Purged.")
