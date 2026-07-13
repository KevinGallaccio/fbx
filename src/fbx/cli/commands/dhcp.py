"""`fbx dhcp` — DHCP server config, leases, static reservations."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import dhcp as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="DHCP server: leases and configuration.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="dhcp")


@app.command()
def leases(ctx: typer.Context) -> None:
    """List currently active DHCP leases."""
    data = fetch(ctx, api.dynamic_leases)
    ui.emit(data, ctx.obj, table=_leases_table)


@app.command()
def static(ctx: typer.Context) -> None:
    """List configured static (reserved) leases."""
    data = fetch(ctx, api.static_leases)
    ui.emit(data, ctx.obj, table=_static_table)


@app.command()
def config(ctx: typer.Context) -> None:
    """Show the DHCP server configuration."""
    data = fetch(ctx, api.config)
    ui.emit(data, ctx.obj, table=_config_table)


def _leases_table(items: list) -> Table:
    t = Table(box=None, title=f"DHCP leases — {len(items)}")
    t.add_column("Hostname")
    t.add_column("IP")
    t.add_column("MAC")
    t.add_column("Assigned")
    t.add_column("Remaining")
    t.add_column("Static")
    for lease in sorted(items, key=_ip_sort_key):
        t.add_row(
            fmt.safe(lease.get("hostname")),
            fmt.safe(lease.get("ip")),
            fmt.safe(lease.get("mac")),
            fmt.epoch(lease.get("assign_time")),
            fmt.duration(lease.get("lease_remaining")),
            fmt.yesno(lease.get("is_static")),
        )
    return t


def _ip_sort_key(lease: dict):
    ip = str(lease.get("ip") or "")
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return (0, tuple(int(p) for p in parts))
    return (1, ip)


def _static_table(items: list) -> Table:
    t = Table(box=None, title=f"DHCP static leases — {len(items)}")
    t.add_column("Hostname")
    t.add_column("IP")
    t.add_column("MAC")
    t.add_column("Comment")
    t.add_column("Active")
    for lease in sorted(items, key=_ip_sort_key):
        host = lease.get("host") or {}
        t.add_row(
            fmt.safe(lease.get("hostname")),
            fmt.safe(lease.get("ip")),
            fmt.safe(lease.get("mac")),
            fmt.safe(lease.get("comment")),
            fmt.yesno(host.get("active")) if host else "",
        )
    return t


def _config_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="DHCP config")
    t.add_column(style="bold")
    t.add_column()
    ip_start, ip_end = d.get("ip_range_start"), d.get("ip_range_end")
    dns = [str(s) for s in (d.get("dns") or []) if s]
    rows = [
        ("Enabled", fmt.yesno(d.get("enabled"))),
        ("Range", f"{ip_start} – {ip_end}" if ip_start and ip_end else None),
        ("Netmask", d.get("netmask")),
        ("Gateway", d.get("gateway")),
        ("DNS", ", ".join(dns) if dns else None),
        ("Sticky assign", fmt.yesno(d.get("sticky_assign"))),
        ("Always broadcast", fmt.yesno(d.get("always_broadcast"))),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, fmt.safe(value))
    return t
