"""Filesystem domain — browse the box's storage.

Paths cross this API base64-encoded (see `core.fspath`); callers hand this
module plain absolute paths and get plain entries back — the `path` token
inside each entry is left as returned, since it is what the API expects on
the next call.
"""

from __future__ import annotations

from typing import Any

from .. import fspath
from . import as_list


def ls(client: Any, path: str = "/") -> Any:
    """GET /fs/ls/{b64path} — list a directory. `path` is a plain absolute path.

    Returns the upstream result object as-is (observed: `{"entries": [...]}`)
    so `--json` stays lossless; use `entries()` to get the entry list.
    `countSubFolder` makes the box include `foldercount`/`filecount` on each
    directory entry (the web UI passes it too; omitted, they're absent).
    """
    return client.get(f"fs/ls/{fspath.encode(path)}", params={"countSubFolder": 1})


def entries(result: Any) -> list:
    """The entry list out of an `ls()` result, whatever the box sent."""
    if isinstance(result, dict):
        return as_list(result.get("entries"))
    # Observed shape is {"entries": [...]}; tolerate a bare list just in case.
    return as_list(result)
