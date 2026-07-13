"""Downloads domain — the torrent/NZB/HTTP download manager (read side)."""

from __future__ import annotations

from typing import Any

from . import as_list


def tasks(client: Any) -> list:
    """GET /downloads/ — every download task."""
    return as_list(client.get("downloads/"))


def stats(client: Any) -> dict:
    """GET /downloads/stats — aggregate manager counters and throughput."""
    return client.get("downloads/stats")
