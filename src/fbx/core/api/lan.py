"""LAN domain — the box's LAN identity and the network device browser."""

from __future__ import annotations

from typing import Any

from . import as_list

DEFAULT_INTERFACE = "pub"


def config(client: Any) -> dict:
    """GET /lan/config/ — the box's own LAN identity and router/bridge mode."""
    return client.get("lan/config/")


def interfaces(client: Any) -> list:
    """GET /lan/browser/interfaces/ — browsable L2 interfaces + host counts."""
    return as_list(client.get("lan/browser/interfaces/"))


def devices(client: Any, interface: str = DEFAULT_INTERFACE) -> list:
    """GET /lan/browser/{interface}/ — the LAN host list (the device browser)."""
    return as_list(client.get(f"lan/browser/{interface}/"))
