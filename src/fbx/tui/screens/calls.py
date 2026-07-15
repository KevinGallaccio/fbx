"""Phone: the landline call log."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header

from ...cli import fmt
from ...core.api import calls
from ..support import BoxCallError
from ..widgets import cursor_key, refill
from ._base import BoxScreen

_TYPE_STYLE = {"missed": "red", "accepted": "green", "outgoing": "cyan"}


class CallsScreen(BoxScreen):
    POLL_INTERVAL = 10.0

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
        Binding("m", "mark_read", "Mark read"),
        Binding("M", "mark_all_read", "Mark all read"),
        Binding("d", "delete_entry", "Delete"),
        Binding("C", "clear_log", "Clear log"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="calls", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#calls", DataTable).add_columns(
            "When", "Type", "Number", "Name", "Duration", "New"
        )
        super().on_mount()

    async def refresh_data(self) -> None:
        log = await self.box(calls.log)
        rows, keys = [], []
        for c in log:
            call_type = str(c.get("type") or "")
            rows.append(
                (
                    fmt.epoch(c.get("datetime")),
                    Text(call_type, style=_TYPE_STYLE.get(call_type, "")),
                    str(c.get("number") or ""),
                    str(c.get("name") or ""),
                    fmt.duration(c.get("duration")),
                    "●" if c.get("new") else "",
                )
            )
            keys.append(str(c.get("id")))
        refill(self.query_one("#calls", DataTable), rows, keys)

    @work
    async def action_mark_read(self) -> None:
        call_id = cursor_key(self.query_one("#calls", DataTable))
        if call_id is None:
            return
        try:
            await self.box(calls.mark_read, int(call_id))
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_mark_all_read(self) -> None:
        try:
            await self.box(calls.mark_all_read)
        except BoxCallError:
            return
        self.notify("All calls marked read.")
        self.run_refresh()

    @work
    async def action_delete_entry(self) -> None:
        call_id = cursor_key(self.query_one("#calls", DataTable))
        if call_id is None:
            return
        if not await self.confirm("Delete this call log entry?", confirm_label="Delete"):
            return
        try:
            await self.box(calls.delete_entry, int(call_id))
        except BoxCallError:
            return
        self.run_refresh()

    @work
    async def action_clear_log(self) -> None:
        if not await self.confirm(
            "Clear the WHOLE call log? This cannot be undone.", confirm_label="Clear log"
        ):
            return
        try:
            await self.box(calls.delete_all)
        except BoxCallError:
            return
        self.notify("Call log cleared.", severity="warning")
        self.run_refresh()
