"""Shared plumbing for domain-command tests: an authorized, respx-mocked box.

Fixture payloads in the per-domain test modules are converted from the Phase 0
captures — shapes are real (firmware 4.12.2 / API 16.0), values are the scrub
placeholders (02:00:… MACs, 192.168.1.x, host-N, scrubbed-ssid-N).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import respx

from fbx.core import credentials

BASE = "http://mafreebox.freebox.fr/api/v16/"


def authorize() -> None:
    """Store a fake credential so `connect()` finds a profile.

    Hard guard: refuses to touch the real credential store. This must only
    ever run with `config_dir` monkeypatched to a tmp dir (the autouse
    `_isolate_credentials` fixture in conftest.py). Running it un-isolated —
    e.g. from a REPL snippet that imports test helpers — would overwrite the
    user's real app token, which is unrecoverable without re-pairing.
    """
    real = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "fbx"
    if credentials.config_dir().resolve() == real.resolve():
        raise RuntimeError(
            "tests/helpers.authorize() called without credential isolation; "
            "it would clobber the real app token"
        )
    credentials.save(
        credentials.Credential(app_id="app", app_token="tok", box_model="fbxgw9-r1")
    )


def mock_login() -> None:
    """Mock discovery + session so any data command can authenticate."""
    respx.get("http://mafreebox.freebox.fr/api_version").mock(
        return_value=httpx.Response(
            200,
            json={"api_version": "16.0", "api_base_url": "/api/", "box_model": "fbxgw9-r1"},
        )
    )
    respx.get(f"{BASE}login/").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"challenge": "c"}})
    )
    respx.post(f"{BASE}login/session/").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"session_token": "S1", "permissions": {}}},
        )
    )


def mock_get(
    path: str,
    result: Any = None,
    *,
    envelope: dict | None = None,
    startswith: bool = False,
) -> respx.Route:
    """Mock `GET {BASE}{path}` with a success envelope around `result`.

    `envelope` overrides the whole body — used for the box's empty-collection
    answer, a bare `{"success": true}` with no `result` key at all.
    `startswith` matches by URL prefix (for paths with encoded segments/params).
    """
    body = envelope if envelope is not None else {"success": True, "result": result}
    url = f"{BASE}{path}"
    route = respx.get(url__startswith=url) if startswith else respx.get(url)
    return route.mock(return_value=httpx.Response(200, json=body))
