"""Typed accessors for each Freebox API domain.

One module per domain; each is the single place its endpoint paths are
written. Functions take an `FbxClient` and return the unwrapped `result`.
List endpoints normalize the box's "empty" answer — a bare
`{"success": true}` with no `result` at all — to `[]` so callers never
special-case it.
"""

from __future__ import annotations

from typing import Any


def as_list(result: Any) -> list:
    """Normalize a list endpoint's result: the box omits `result` entirely
    when a collection is empty (observed on /lan/routes, /contact/,
    /fw/redir/, …)."""
    return result if isinstance(result, list) else []
