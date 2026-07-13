"""`fbx contacts` — the box's address book."""

from __future__ import annotations

import typer
from rich.table import Table

from ...core.api import contacts as api
from .. import fmt, ui
from ._common import fetch

app = typer.Typer(help="Address book.", no_args_is_help=True)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="contacts")


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """List contacts."""
    data = fetch(ctx, api.list_all)
    ui.emit(data, ctx.obj, table=_contacts_table)


def _contacts_table(items: list) -> Table:
    t = Table(box=None, title=f"Contacts — {len(items)}")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Company")
    t.add_column("Numbers")
    for c in sorted(items, key=lambda c: str(c.get("display_name") or "").lower()):
        numbers = c.get("numbers") or []
        shown = ", ".join(str(n.get("number")) for n in numbers if n.get("number"))
        name = c.get("display_name") or " ".join(
            str(x) for x in [c.get("first_name"), c.get("last_name")] if x
        )
        t.add_row(
            str(c.get("id", "")),
            fmt.safe(name),
            fmt.safe(c.get("company")),
            fmt.safe(shown),
        )
    return t
