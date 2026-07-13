#!/usr/bin/env python3
"""LAN receiver for browser-side recon captures.

The instrumented Freebox OS page ships drained capture batches here via
POST /save?name=<label>; each batch lands in recon/raw/<label>.json
(gitignored). This keeps multi-hundred-KB captures out of the agent
transcript entirely.

Usage: python3 recon/receiver.py [port]     (default 8737)
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent / "raw"
NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/save?name="):
            return self._reply(404, "unknown path")
        name = self.path.split("=", 1)[1]
        if not NAME_RE.match(name):
            return self._reply(400, f"bad name: {name!r}")
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > 100 * 1024 * 1024:
            return self._reply(400, f"bad length {length}")
        body = self.rfile.read(length)
        try:
            json.loads(body)
        except json.JSONDecodeError as e:
            return self._reply(400, f"not JSON: {e}")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        dst = RAW_DIR / f"{name}.json"
        dst.write_bytes(body)
        print(f"saved {dst} ({length} bytes)", flush=True)
        self._reply(200, f"saved {name}.json ({length} bytes)")

    def log_message(self, *args) -> None:  # quiet
        pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8737
    srv = HTTPServer(("0.0.0.0", port), Handler)
    print(f"receiver on 0.0.0.0:{port} -> {RAW_DIR}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
