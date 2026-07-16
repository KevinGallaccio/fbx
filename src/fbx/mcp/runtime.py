"""The MCP server's connection to the box: one client, serialized, typed errors.

The client lifecycle (lazy connect, lock, drop-on-transport-error) lives in
`core.runtime.ClientRuntime`, shared with the interactive app; this module
adds the agent-facing error translation. Regular tools never trigger the
pairing flow: with no stored credential they fail with instructions instead.
Pairing happens only through the two explicit enroll tools (`mcp.enroll`),
which still hinge on the physical ▶ press on the box.
"""

from __future__ import annotations

import threading
from typing import Any

from ..core.errors import (
    FbxAPIError,
    FbxDiscoveryError,
    FbxError,
    FbxHTTPError,
    FbxNotAuthenticated,
    FbxPermissionError,
)
from ..core.runtime import ClientRuntime
from .registry import ToolSpec


class FbxMcpToolError(Exception):
    """A tool failure with an agent-facing message (becomes an MCP tool error)."""


def error_message(exc: FbxError, *, profile: str) -> str:
    """One clean, actionable line per failure class — no stack traces."""
    if isinstance(exc, FbxNotAuthenticated):
        return (
            f"fbx is not paired with a Freebox (profile {profile!r}). Pairing is a "
            "one-time human step gated by a physical ▶ press on the box's front "
            "panel: the user can run `fbx auth login` in a terminal on this "
            "machine, or — with their explicit go-ahead — use the fbx_auth_enroll "
            "tool and go press the button when told."
        )
    if isinstance(exc, FbxPermissionError):
        return (
            f"the fbx app token lacks the `{exc.scope}` permission. Grant it in "
            "Freebox OS (http://mafreebox.freebox.fr) → Paramètres → Gestion des "
            "accès → Applications → fbx, then retry."
        )
    if isinstance(exc, FbxAPIError):
        where = f" ({exc.method} {exc.path})" if exc.path else ""
        return f"the box refused the call{where}: {exc.error_code}: {exc.msg or 'API error'}"
    if isinstance(exc, (FbxDiscoveryError, FbxHTTPError)):
        return f"can't reach the box: {exc}"
    return str(exc)


class FbxRuntime:
    """Shared state for one server process: the client and its settings."""

    def __init__(self, *, profile: str = "default", host: str | None = None) -> None:
        self.profile = profile
        self.host = host
        self._runtime = ClientRuntime(profile=profile, host=host)
        # Pairing in flight (mcp.enroll): track_id -> PendingEnrollment. Held
        # here so both enroll tools see the same state across worker threads.
        self.pending_enrollments: dict[int, Any] = {}
        self.enroll_lock = threading.Lock()

    def call(self, spec: ToolSpec, args: dict) -> Any:
        """Run one tool call synchronously (the server offloads to a thread)."""
        try:
            if not spec.requires_client:
                # Pre-pairing tools get the runtime itself, not a box client.
                return spec.fn(self, **args)
            return self._runtime.call(spec.fn, **args)
        except FbxError as exc:
            raise FbxMcpToolError(error_message(exc, profile=self.profile)) from exc

    def reset_client(self) -> None:
        """Drop the cached box client (e.g. after pairing replaced the credential)."""
        self._runtime.close()

    def close(self) -> None:
        self._runtime.close()
