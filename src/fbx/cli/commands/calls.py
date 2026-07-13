"""`fbx calls` — the landline call log."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import calls as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Landline call history.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="calls")


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """List the call log (newest first)."""
    data = fetch(ctx, api.log)
    ui.emit(data, ctx.obj, table=_log_table)


_TYPE_STYLE = {"missed": "red", "accepted": "green", "outgoing": "cyan"}


def _log_table(items: list) -> Table:
    t = Table(box=None, title=f"Calls — {len(items)}")
    t.add_column("Date")
    t.add_column("Type")
    t.add_column("Number")
    t.add_column("Name")
    t.add_column("Duration", justify="right")
    t.add_column("New")
    def sort_key(c: dict):
        # Mixed-type datetimes must not crash sorted(); non-numbers sink last.
        dt = c.get("datetime")
        return dt if fmt.is_num(dt) else 0

    for c in sorted(items, key=sort_key, reverse=True):
        call_type = str(c.get("type") or "")
        style = _TYPE_STYLE.get(call_type)
        t.add_row(
            fmt.epoch(c.get("datetime")),
            f"[{style}]{fmt.safe(call_type)}[/]" if style else fmt.safe(call_type),
            fmt.safe(c.get("number")),
            fmt.safe(c.get("name")),
            fmt.duration(c.get("duration")),
            "●" if c.get("new") else "",
        )
    return t
