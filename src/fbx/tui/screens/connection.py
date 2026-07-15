"""Connection: WAN status, fiber health, IPv6, logs, and config toggles."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from ...cli import fmt
from ...core.api import connection
from ..support import BoxCallError
from ..widgets import refill
from ._base import BoxScreen


class ConnectionScreen(BoxScreen):
    POLL_INTERVAL = 2.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("p", "toggle_ping", "Toggle WAN ping"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Status", id="tab-status"):
                with VerticalScroll():
                    yield Static("…", id="conn-status", classes="panel")
                    yield Static("…", id="conn-config", classes="panel")
            with TabPane("Fiber", id="tab-ftth"):
                yield Static("…", id="conn-ftth", classes="panel")
            with TabPane("IPv6", id="tab-ipv6"):
                yield Static("…", id="conn-ipv6", classes="panel")
            with TabPane("Logs", id="tab-logs"):
                yield DataTable(id="conn-logs", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#conn-logs", DataTable).add_columns("When", "State", "Type", "Link")
        super().on_mount()

    async def refresh_data(self) -> None:
        status = await self.box(connection.status)
        state = str(status.get("state") or "?")
        dot = "[green]●[/]" if state == "up" else "[red]●[/]"
        self.query_one("#conn-status", Static).update(
            f"{dot} [b]{fmt.safe(state)}[/b] · {fmt.safe(status.get('media'))} "
            f"({fmt.safe(status.get('type'))})\n"
            f"IPv4 {fmt.safe(status.get('ipv4'))} · IPv6 {fmt.safe(status.get('ipv6'))}\n"
            f"rate     ↓ {fmt.human_rate(status.get('rate_down'))}"
            f"   ↑ {fmt.human_rate(status.get('rate_up'))}\n"
            f"link     ↓ {fmt.human_bits(status.get('bandwidth_down'))}"
            f"   ↑ {fmt.human_bits(status.get('bandwidth_up'))}\n"
            f"total    ↓ {fmt.human_bytes(status.get('bytes_down'))}"
            f"   ↑ {fmt.human_bytes(status.get('bytes_up'))}"
        )

        # The active tab drives which extra fetch is worth making; config is
        # tiny and feeds the toggle bindings, so it always refreshes.
        config = await self.box(connection.config)
        self._config = config
        self.query_one("#conn-config", Static).update(
            f"WAN ping {fmt.onoff(config.get('ping'))} · "
            f"remote access {fmt.onoff(config.get('remote_access'))} · "
            f"WOL proxy {fmt.onoff(config.get('wol'))}\n"
            f"API domain {fmt.safe(config.get('api_domain'))}"
        )

        active = self.query_one(TabbedContent).active
        if active == "tab-ftth":
            ftth = await self.box(connection.ftth)
            self.query_one("#conn-ftth", Static).update(
                f"link {fmt.onoff(ftth.get('link'))} · SFP {fmt.safe(ftth.get('sfp_model'))} "
                f"({fmt.safe(ftth.get('sfp_vendor'))})\n"
                f"power   rx {fmt.centi_dbm(ftth.get('sfp_pwr_rx'))}"
                f"   tx {fmt.centi_dbm(ftth.get('sfp_pwr_tx'))}\n"
                f"signal  {fmt.onoff(ftth.get('sfp_has_signal'))}"
            )
        elif active == "tab-ipv6":
            ipv6 = await self.box(connection.ipv6_config)
            lines = [f"IPv6 {fmt.onoff(ipv6.get('ipv6_enabled'))}"]
            for d in ipv6.get("delegations") or []:
                lines.append(
                    f"prefix {fmt.safe(d.get('prefix'))} → next hop {fmt.safe(d.get('next_hop'))}"
                )
            self.query_one("#conn-ipv6", Static).update("\n".join(lines))
        elif active == "tab-logs":
            logs = await self.box(connection.logs)
            refill(
                self.query_one("#conn-logs", DataTable),
                [
                    (
                        fmt.epoch(entry.get("date")),
                        str(entry.get("state") or ""),
                        str(entry.get("type") or ""),
                        str(entry.get("conn") or entry.get("link") or ""),
                    )
                    for entry in logs
                ],
            )

    @work
    async def action_toggle_ping(self) -> None:
        current = bool(getattr(self, "_config", {}).get("ping"))
        try:
            await self.box(connection.set_config, {"ping": not current})
        except BoxCallError:
            return
        self.notify(f"WAN ping responses {'disabled' if current else 'enabled'}.")
        self.run_refresh()
