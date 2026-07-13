"""Address-book domain — contacts (requires the `contacts` permission)."""

from __future__ import annotations

from typing import Any

from . import as_list


def list_all(client: Any) -> list:
    """GET /contact/ — every contact (empty book → missing result → [])."""
    return as_list(client.get("contact/"))
