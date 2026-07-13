"""Storage domain — physical disks and partitions."""

from __future__ import annotations

from typing import Any

from . import as_list


def disks(client: Any) -> list:
    """GET /storage/disk/ — physical disks (partitions embedded)."""
    return as_list(client.get("storage/disk/"))


def partitions(client: Any) -> list:
    """GET /storage/partition/ — all partitions across disks."""
    return as_list(client.get("storage/partition/"))
