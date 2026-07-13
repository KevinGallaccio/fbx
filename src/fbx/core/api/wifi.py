"""Wi-Fi domain — global state, per-radio APs, BSS/SSIDs, associated stations."""

from __future__ import annotations

from typing import Any

from . import as_list


def config(client: Any) -> dict:
    """GET /wifi/config/ — global Wi-Fi service state."""
    return client.get("wifi/config/")


def state(client: Any) -> dict:
    """GET /wifi/state/ — radio detection map (one entry per PHY)."""
    return client.get("wifi/state/")


def aps(client: Any) -> list:
    """GET /wifi/ap/ — access points, one per radio/PHY."""
    return as_list(client.get("wifi/ap/"))


def bss(client: Any) -> list:
    """GET /wifi/bss/ — broadcast SSIDs with security config and status."""
    return as_list(client.get("wifi/bss/"))


def ap_stations(client: Any, ap_id: int) -> list:
    """GET /wifi/ap/{id}/stations/ — clients associated to one AP."""
    return as_list(client.get(f"wifi/ap/{ap_id}/stations/"))


def stations(client: Any) -> list:
    """All associated Wi-Fi clients, aggregated across every AP.

    There is no box-wide stations endpoint — only the per-AP one — so this
    walks /wifi/ap/ and concatenates. Each station is annotated with the AP
    it came from under `_fbx_ap` (an fbx-side key, absent upstream).
    """
    result: list = []
    for ap in aps(client):
        ap_id = ap.get("id")
        if ap_id is None:
            continue
        ap_band = (ap.get("config") or {}).get("band")
        for station in ap_stations(client, ap_id):
            station["_fbx_ap"] = {"id": ap_id, "name": ap.get("name"), "band": ap_band}
            result.append(station)
    return result
