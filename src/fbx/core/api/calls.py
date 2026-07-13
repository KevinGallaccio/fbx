"""Telephony domain — call log (requires the `calls` permission)."""

from __future__ import annotations

from typing import Any

from . import as_list


def log(client: Any) -> list:
    """GET /call/log/ — call history, newest first."""
    return as_list(client.get("call/log/"))
