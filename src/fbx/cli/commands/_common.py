"""Shared plumbing for data commands: connect, call one core function, return.

Keeps each command to "fetch, then emit" so the connect/error boilerplate
lives in exactly one place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import typer

from ...core import client as core_client
from .. import ui


def fetch(ctx: typer.Context, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Open an authenticated client, run `fn(client, …)`, close, return data.

    Errors are mapped to exit codes by `handle_errors`, so a command body is
    just: `data = fetch(ctx, domain.thing)` then `ui.emit(...)`.
    """
    from ..main import handle_errors

    state: ui.CliState = ctx.obj
    with handle_errors():
        fbx = core_client.connect(state.profile, host=state.host)
        with fbx:
            return fn(fbx, *args, **kwargs)
