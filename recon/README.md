# recon/ — Phase 0 API reconnaissance

Tooling and captures from reverse-engineering the Freebox OS API by watching
the official web UI drive it. Everything here feeds `docs/api-notes.md` (the
spec) and, later, `tests/cassettes/` (the test fixtures).

Captured on a **Freebox Ultra** (hardware `fbxgw9-r1`, firmware **4.12.2**,
API **16.0**) on 2026-07-13.

## Layout

| Path | Committed? | What |
|---|---|---|
| `raw/` | **No** (`.gitignore`) | Unscrubbed captures — serials, MACs, WAN IP, tokens, the on-box doc mirror, and `scrub_map.json` (the real→fake mapping). Never leaves this machine. |
| `capture/` | Yes | Scrubbed request/response pairs, one file per Freebox OS section. Safe for a public repo; become `tests/cassettes/` in Phase 2. |
| `scrub.py` | Yes | The scrubber. Replaces every identifier with a stable fake and refuses to emit a file that still contains one. |
| `mirror_doc.py` | Yes | Mirrors the box's own docs (`/doc/index.html`, unauthenticated) into `raw/onbox-doc/`. |
| `extract_doc.py` | Yes | → `doc_inventory.json`: the 343-endpoint list parsed from those docs. |
| `receiver.py` | Yes | Tiny LAN HTTP server the instrumented page POSTs capture batches to, so multi-MB captures never touch the agent transcript. |
| `summarize.py` | Yes | Prints the unique endpoints in a capture file. |
| `doc_inventory.json` | Yes | Method + path for every endpoint the on-box docs describe. |

## How the capture worked

1. `receiver.py` runs on the LAN (`python3 recon/receiver.py`).
2. A `fetch`/`XHR`/`WebSocket` tap is injected into the Freebox OS page; it
   records every request/response and WS frame.
3. Clicking through each section (and a bulk-GET harvest of every documented
   read-only endpoint) drains batches to the receiver → `raw/<section>.json`.
4. `scrub.py --all` turns `raw/*.json` into `capture/*.json`, rejecting any
   file that still contains identifying data.

## Scrubbing discipline

**Nothing from `raw/` is ever committed.** The scrubber is the gate:

```sh
python3 recon/scrub.py --selftest        # regression suite
python3 recon/scrub.py --all             # raw/*.json -> capture/*.json
python3 recon/scrub.py --check FILE...   # verify a file has no identifiers left
```

`--all` and `--check` load `raw/scrub_map.json` and reject any output that
still contains a known real value — by any code path, not just the ones the
rules anticipated. If you capture anything new, it goes through `scrub.py`
before `git add`. No exceptions.
