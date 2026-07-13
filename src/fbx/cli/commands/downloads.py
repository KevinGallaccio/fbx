"""`fbx downloads` — the download manager (read side)."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import downloads as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Download manager: tasks and stats.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="downloads")


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """List download tasks."""
    data = fetch(ctx, api.tasks)
    ui.emit(data, ctx.obj, table=_tasks_table)


@app.command()
def stats(ctx: typer.Context) -> None:
    """Show download-manager counters and throughput."""
    data = fetch(ctx, api.stats)
    ui.emit(data, ctx.obj, table=_stats_table)


_STATUS_STYLE = {"done": "green", "downloading": "cyan", "seeding": "cyan", "error": "red"}


def _tasks_table(items: list) -> Table:
    t = Table(box=None, title=f"Downloads — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Status")
    t.add_column("Progress", justify="right")
    t.add_column("Size", justify="right")
    t.add_column("Rate ↓")
    t.add_column("ETA")
    for task in items:
        status = str(task.get("status") or "")
        style = _STATUS_STYLE.get(status)
        rx_pct = task.get("rx_pct")
        # rx_pct is per-10000; floor, so 9999 shows 99% (not a premature 100%).
        progress = f"{int(rx_pct // 100)}%" if fmt.is_num(rx_pct) else ""
        t.add_row(
            str(task.get("id", "")),
            fmt.safe(task.get("name")),
            fmt.safe(task.get("type")),
            f"[{style}]{fmt.safe(status)}[/]" if style else fmt.safe(status),
            progress,
            fmt.human_bytes(task.get("size")),
            fmt.human_rate(task.get("rx_rate")),
            fmt.duration(task.get("eta")) if task.get("eta") else "",
        )
    return t


def _stats_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Download stats")
    t.add_column(style="bold")
    t.add_column()
    throttling = d.get("throttling_rate") or {}
    throttle = ""
    if throttling.get("rx_rate") or throttling.get("tx_rate"):
        throttle = (
            f"{fmt.human_rate(throttling.get('rx_rate'))} / "
            f"{fmt.human_rate(throttling.get('tx_rate'))}"
        )
    rows = [
        ("Tasks", d.get("nb_tasks")),
        ("Active", d.get("nb_tasks_active")),
        ("Downloading", d.get("nb_tasks_downloading")),
        ("Seeding", d.get("nb_tasks_seeding")),
        ("Queued", d.get("nb_tasks_queued")),
        ("Stopped", d.get("nb_tasks_stopped")),
        ("Done", d.get("nb_tasks_done")),
        ("Error", d.get("nb_tasks_error")),
        (
            "Rate ↓ / ↑",
            f"{fmt.human_rate(d.get('rx_rate'))} / {fmt.human_rate(d.get('tx_rate'))}"
            if d.get("rx_rate") is not None or d.get("tx_rate") is not None
            else None,
        ),
        ("Throttling", d.get("throttling_mode")),
        ("Throttle ↓ / ↑", throttle or None),
        ("Peers", d.get("nb_peer")),
        ("Connection ready", fmt.yesno(d.get("conn_ready"))),
    ]
    for label, value in rows:
        if value is not None and value != "":
            t.add_row(label, fmt.safe(value))
    return t
