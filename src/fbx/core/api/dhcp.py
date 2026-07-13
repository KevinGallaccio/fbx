"""DHCP domain — server config, dynamic leases, static reservations."""

from __future__ import annotations

from typing import Any

from . import as_list


def config(client: Any) -> dict:
    """GET /dhcp/config/ — DHCPv4 server configuration."""
    return client.get("dhcp/config/")


def dynamic_leases(client: Any) -> list:
    """GET /dhcp/dynamic_lease/ — currently active leases."""
    return as_list(client.get("dhcp/dynamic_lease/"))


def static_leases(client: Any) -> list:
    """GET /dhcp/static_lease/ — configured static reservations."""
    return as_list(client.get("dhcp/static_lease/"))
