#!/usr/bin/env python3
"""Print the unique endpoints (and WS frame kinds) in raw capture files.

Usage: python3 recon/summarize.py recon/raw/<file>.json...
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DC_RE = re.compile(r"[?&]_dc=\d+")
HOST_RE = re.compile(r"^https?://[^/]+")
NUM_RE = re.compile(r"/\d+(?=/|$)")


def norm(url: str) -> str:
    url = HOST_RE.sub("", url)
    url = DC_RE.sub("", url)
    return NUM_RE.sub("/{id}", url)


def main() -> int:
    for f in sys.argv[1:]:
        data = json.loads(Path(f).read_text())
        seen: dict[str, int] = {}
        for h in data.get("http", []):
            k = f"{h.get('method', '?').upper()} {norm(h.get('url', '?'))}"
            seen[k] = seen.get(k, 0) + 1
        print(f"== {f} ({len(data.get('http', []))} http, {len(data.get('ws', []))} ws)")
        for k in sorted(seen):
            print(f"  {seen[k]:4d}  {k}")
        for w in data.get("ws", []):
            if w.get("dir") in ("open", "tx"):
                print(f"  WS {w['dir']}: {str(w.get('data', w.get('url', '')))[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
