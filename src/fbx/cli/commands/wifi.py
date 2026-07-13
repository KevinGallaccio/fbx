"""`fbx wifi` — radios, SSIDs, and associated clients."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import wifi as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Wi-Fi radios, networks, and clients.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="wifi")


@app.command()
def status(ctx: typer.Context) -> None:
    """Show the global Wi-Fi state and detected radios."""
    data = fetch(ctx, api.state)
    ui.emit(data, ctx.obj, table=_status_table)


@app.command()
def config(ctx: typer.Context) -> None:
    """Show the global Wi-Fi configuration."""
    data = fetch(ctx, api.config)
    ui.emit(data, ctx.obj, table=_config_table)


@app.command()
def ap(ctx: typer.Context) -> None:
    """List access points (one per radio) with channel and state."""
    data = fetch(ctx, api.aps)
    ui.emit(data, ctx.obj, table=_ap_table)


@app.command()
def bss(ctx: typer.Context) -> None:
    """List broadcast SSIDs with security settings (keys not shown; use --json)."""
    data = fetch(ctx, api.bss)
    ui.emit(data, ctx.obj, table=_bss_table)


@app.command()
def stations(
    ctx: typer.Context,
    ap_id: int | None = typer.Option(None, "--ap", help="Only clients of this AP id."),
) -> None:
    """List associated Wi-Fi clients across all access points."""
    if ap_id is not None:
        data = fetch(ctx, api.ap_stations, ap_id)
    else:
        data = fetch(ctx, api.stations)
    ui.emit(data, ctx.obj, table=_stations_table)


def _status_table(d: dict) -> Table:
    t = Table(box=None, title=f"Wi-Fi — {fmt.safe(d.get('state', '?'))}")
    t.add_column("PHY", justify="right")
    t.add_column("Band")
    t.add_column("Detected")
    for phy in d.get("expected_phys") or []:
        t.add_row(
            str(phy.get("phy_id", "")),
            fmt.safe(phy.get("band")),
            fmt.yesno(phy.get("detected")),
        )
    return t


def _config_table(d: dict) -> Table:
    t = Table(show_header=False, box=None, title="Wi-Fi config")
    t.add_column(style="bold")
    t.add_column()
    rows = [
        ("Enabled", fmt.yesno(d.get("enabled"))),
        ("Power saving", fmt.onoff(d.get("power_saving"))),
        ("MAC filter", d.get("mac_filter_state")),
    ]
    for label, value in rows:
        if value not in (None, ""):
            t.add_row(label, fmt.safe(value))
    return t


def _ap_table(items: list) -> Table:
    t = Table(box=None, title="Access points")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Band")
    t.add_column("Channel")
    t.add_column("Width")
    t.add_column("State")
    t.add_column("DFS")
    for a in items:
        cfg = a.get("config") or {}
        st = a.get("status") or {}
        channel = st.get("primary_channel", cfg.get("primary_channel"))
        state = str(st.get("state") or "")
        t.add_row(
            str(a.get("id", "")),
            fmt.safe(a.get("name")),
            fmt.safe(cfg.get("band")),
            str(channel if channel is not None else ""),
            fmt.safe(st.get("channel_width") or cfg.get("channel_width")),
            f"[green]{state}[/]" if state == "active" else fmt.safe(state),
            fmt.yesno(cfg.get("dfs_enabled")),
        )
    return t


def _bss_table(items: list) -> Table:
    t = Table(box=None, title="Wi-Fi networks (BSS)")
    t.add_column("SSID")
    t.add_column("Band")
    t.add_column("Encryption")
    t.add_column("Hidden")
    t.add_column("State")
    t.add_column("Clients", justify="right")
    for b in items:
        cfg = b.get("config") or {}
        st = b.get("status") or {}
        state = str(st.get("state") or "")
        t.add_row(
            fmt.safe(cfg.get("ssid")),
            fmt.safe(str(st.get("band") or "").lower()),  # bss reports '6G'; normalize
            fmt.safe(cfg.get("encryption")),
            fmt.yesno(cfg.get("hide_ssid")),
            f"[green]{state}[/]" if state == "active" else fmt.safe(state),
            str(st.get("sta_count", "")),
        )
    return t


def _stations_table(items: list) -> Table:
    t = Table(box=None, title=f"Wi-Fi clients — {len(items)}")
    t.add_column("Name")
    t.add_column("MAC")
    t.add_column("AP")
    t.add_column("Band")
    t.add_column("Auth")
    t.add_column("Signal")
    t.add_column("Rate ↓ / ↑")
    t.add_column("Connected")
    for s in items:
        host = s.get("host") or {}
        name = s.get("hostname") or host.get("primary_name") or ""
        ap_info = s.get("_fbx_ap") or {}
        signal = s.get("signal")
        rx = s.get("rx_rate")
        tx = s.get("tx_rate")
        rate = ""
        if rx is not None or tx is not None:
            rate = f"{fmt.human_rate(rx)} / {fmt.human_rate(tx)}"
        t.add_row(
            fmt.safe(name),
            fmt.safe(s.get("mac")),
            fmt.safe(ap_info.get("name") or ap_info.get("id", "")),
            fmt.safe(ap_info.get("band") or s.get("band")),
            fmt.safe(s.get("wpa_alg")),
            f"{signal} dBm" if fmt.is_num(signal) else "",
            rate,
            fmt.duration(s.get("conn_duration")),
        )
    return t
