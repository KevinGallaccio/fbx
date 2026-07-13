"""`fbx fs` — browse the box's filesystem."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import fs as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Browse files on the box's storage.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="fs")


@app.command()
def ls(
    ctx: typer.Context,
    path: str = typer.Argument("/", help="Absolute path on the box (e.g. /Freebox)."),
) -> None:
    """List a directory on the box's storage."""
    data = fetch(ctx, api.ls, path)
    ui.emit(data, ctx.obj, table=lambda d: _ls_table(d, path))


def _ls_table(data: object, path: str) -> Table:
    # `.` and `..` are display noise in a listing (JSON keeps them).
    entries = [e for e in api.entries(data) if e.get("name") not in (".", "..")]
    t = Table(box=None, title=f"{fmt.safe(path)} — {len(entries)} entries")
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Size", justify="right")
    t.add_column("Modified")

    def sort_key(e: dict):
        return (e.get("type") != "dir", str(e.get("name") or "").lower())

    for e in sorted(entries, key=sort_key):
        is_dir = e.get("type") == "dir"
        name = fmt.safe(e.get("name") or "?")
        if e.get("hidden"):
            name = f"[dim]{name}[/]"
        contents = ""
        if is_dir:
            folders, files = e.get("foldercount"), e.get("filecount")
            if fmt.is_num(folders) and fmt.is_num(files):
                contents = f"{int(folders) + int(files)} items"
        t.add_row(
            f"[bold blue]{name}/[/]" if is_dir else name,
            fmt.safe(e.get("type")),
            contents if is_dir else fmt.human_bytes(e.get("size")),
            fmt.epoch(e.get("modification")),
        )
    return t
