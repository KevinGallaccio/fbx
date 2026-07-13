"""`fbx storage` — disks and partitions."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core import fspath
from ...core.api import storage as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Attached storage: disks and partitions.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="storage")


@app.command()
def disks(ctx: typer.Context) -> None:
    """List physical disks."""
    data = fetch(ctx, api.disks)
    ui.emit(data, ctx.obj, table=_disks_table)


@app.command()
def partitions(ctx: typer.Context) -> None:
    """List partitions with space usage."""
    data = fetch(ctx, api.partitions)
    ui.emit(data, ctx.obj, table=_partitions_table)


def _disks_table(items: list) -> Table:
    t = Table(box=None, title=f"Disks — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Type")
    t.add_column("Model")
    t.add_column("Capacity", justify="right")
    t.add_column("State")
    t.add_column("Temp")
    t.add_column("Activity")
    t.add_column("Partitions", justify="right")
    for d in items:
        temp = d.get("temp")
        activity = "idle" if d.get("idle") else ("spinning" if d.get("spinning") else "active")
        t.add_row(
            str(d.get("id", "")),
            fmt.safe(d.get("type")),
            fmt.safe(d.get("model")),
            fmt.human_bytes(d.get("total_bytes")),
            fmt.safe(d.get("state")),
            f"{temp}°C" if fmt.is_num(temp) and temp > 0 else "",
            activity,
            str(len(d.get("partitions") or [])),
        )
    return t


def _partitions_table(items: list) -> Table:
    t = Table(box=None, title=f"Partitions — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Label")
    t.add_column("FS")
    t.add_column("State")
    t.add_column("Used", justify="right")
    t.add_column("Free", justify="right")
    t.add_column("Total", justify="right")
    t.add_column("Use%", justify="right")
    t.add_column("Path")
    for p in items:
        used, total = p.get("used_bytes"), p.get("total_bytes")
        pct = ""
        if fmt.is_num(used) and fmt.is_num(total) and total:
            pct = f"{used / total * 100:.0f}%"
        path = p.get("path")
        t.add_row(
            str(p.get("id", "")),
            fmt.safe(p.get("label")),
            fmt.safe(p.get("fstype")),
            fmt.safe(p.get("state")),
            fmt.human_bytes(used),
            fmt.human_bytes(p.get("free_bytes")),
            fmt.human_bytes(total),
            pct,
            fmt.safe(fspath.decode(path)) if isinstance(path, str) else "",
        )
    return t
