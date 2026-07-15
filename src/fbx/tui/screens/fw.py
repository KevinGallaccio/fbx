"""Port forwarding: static rules, DMZ, incoming services, UPnP."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from ...cli import fmt
from ...core.api import fw
from ..support import BoxCallError
from ..widgets import Field, FormModal, cursor_key, refill
from ._base import BoxScreen


def _wan_ports(rule: dict) -> str:
    start, end = rule.get("wan_port_start"), rule.get("wan_port_end")
    return str(start) if start == end or not end else f"{start}-{end}"


class FwScreen(BoxScreen):
    POLL_INTERVAL = 10.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("a", "add_redir", "Add rule"),
        Binding("t", "toggle_redir", "Enable/disable"),
        Binding("d", "delete_redir", "Delete"),
        Binding("z", "set_dmz", "DMZ…"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._redir_by_id: dict[str, dict] = {}
        self._dmz: dict = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Port forwards", id="tab-redirs"):
                yield DataTable(id="redirs", cursor_type="row")
            with TabPane("DMZ", id="tab-dmz"):
                yield Static("…", id="dmz", classes="panel")
            with TabPane("Incoming services", id="tab-incoming"):
                yield DataTable(id="incoming", cursor_type="row")
            with TabPane("UPnP", id="tab-upnp"):
                yield Static("…", id="upnp-config", classes="panel")
                yield DataTable(id="upnp-redirs", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#redirs", DataTable).add_columns(
            "On", "Proto", "WAN port", "→ LAN", "Source", "Comment"
        )
        self.query_one("#incoming", DataTable).add_columns("Service", "On", "Port(s)")
        self.query_one("#upnp-redirs", DataTable).add_columns(
            "Proto", "WAN port", "→ LAN", "Description"
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        redirs = await self.box(fw.redirs)
        self._redir_by_id = {str(r.get("id")): r for r in redirs}
        refill(
            self.query_one("#redirs", DataTable),
            [
                (
                    "●" if r.get("enabled") else "○",
                    str(r.get("ip_proto") or ""),
                    _wan_ports(r),
                    f"{r.get('lan_ip', '')}:{r.get('lan_port', '')}",
                    str(r.get("src_ip") or ""),
                    str(r.get("comment") or ""),
                )
                for r in redirs
            ],
            list(self._redir_by_id),
        )

        active = self.query_one(TabbedContent).active
        if active == "tab-dmz":
            self._dmz = await self.box(fw.dmz)
            self.query_one("#dmz", Static).update(
                f"DMZ {fmt.onoff(self._dmz.get('enabled'))}"
                + (f" → {fmt.safe(self._dmz.get('ip'))}" if self._dmz.get("ip") else "")
            )
        elif active == "tab-incoming":
            incoming = await self.box(fw.incoming)
            rows = []
            for e in incoming:
                lo, hi = e.get("min_port"), e.get("max_port")
                ports = str(lo) if lo == hi or not hi else f"{lo}-{hi}"
                rows.append(
                    (str(e.get("id") or ""), "●" if e.get("enabled") else "○", ports)
                )
            refill(self.query_one("#incoming", DataTable), rows)
        elif active == "tab-upnp":
            config = await self.box(fw.upnpigd_config)
            self.query_one("#upnp-config", Static).update(
                f"UPnP IGD {fmt.onoff(config.get('enabled'))}"
            )
            upnp_redirs = await self.box(fw.upnpigd_redirs)
            refill(
                self.query_one("#upnp-redirs", DataTable),
                [
                    (
                        str(r.get("ip_proto") or ""),
                        str(r.get("ext_port") or ""),
                        f"{r.get('int_ip', '')}:{r.get('int_port', '')}",
                        str(r.get("description") or ""),
                    )
                    for r in upnp_redirs
                ],
            )

    @work
    async def action_add_redir(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(
                "New port forward",
                [
                    Field("lan_ip", "LAN IP", placeholder="192.168.1.x"),
                    Field("lan_port", "LAN port"),
                    Field("wan_port", "WAN port (this box allows 16384-32767)"),
                    Field("proto", "Protocol", default="tcp", placeholder="tcp | udp"),
                    Field("comment", "Comment (optional)"),
                ],
                submit_label="Forward",
            )
        )
        if not values or not (values["lan_ip"] and values["lan_port"] and values["wan_port"]):
            return
        try:
            wan, lan_port = int(values["wan_port"]), int(values["lan_port"])
        except ValueError:
            self.notify("Ports must be numbers.", severity="error")
            return
        fields = {
            "enabled": True,
            "comment": values["comment"],
            "lan_ip": values["lan_ip"],
            "lan_port": lan_port,
            "wan_port_start": wan,
            "wan_port_end": wan,
            "ip_proto": values["proto"] or "tcp",
            "src_ip": "0.0.0.0",
        }
        try:
            await self.box(fw.create_redir, fields)
        except BoxCallError:
            return
        self.notify(f"Forwarded WAN {wan} → {values['lan_ip']}:{lan_port}.")
        self.run_refresh()

    @work
    async def action_toggle_redir(self) -> None:
        redir_id = cursor_key(self.query_one("#redirs", DataTable))
        if redir_id is None:
            return
        rule = self._redir_by_id.get(redir_id, {})
        enabled = bool(rule.get("enabled"))
        try:
            await self.box(fw.update_redir, redir_id, {"enabled": not enabled})
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_delete_redir(self) -> None:
        redir_id = cursor_key(self.query_one("#redirs", DataTable))
        if redir_id is None:
            return
        rule = self._redir_by_id.get(redir_id, {})
        if not await self.confirm(
            f"Delete the forward WAN {_wan_ports(rule)} → "
            f"{rule.get('lan_ip')}:{rule.get('lan_port')}?",
            confirm_label="Delete",
        ):
            return
        try:
            await self.box(fw.delete_redir, redir_id)
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_set_dmz(self) -> None:
        values = await self.app.push_screen_wait(
            FormModal(
                "DMZ host (leave empty to disable)",
                [Field("ip", "LAN IP", default=str(self._dmz.get("ip") or ""))],
                submit_label="Apply",
            )
        )
        if values is None:
            return
        ip = values["ip"]
        if ip:
            if not await self.confirm(
                f"Expose {ip} to the whole internet as the DMZ host?",
                confirm_label="Expose",
            ):
                return
            fields = {"enabled": True, "ip": ip}
        else:
            fields = {"enabled": False}
        try:
            await self.box(fw.set_dmz, fields)
        except BoxCallError:
            return
        self.notify("DMZ updated.")
        self.run_refresh()
