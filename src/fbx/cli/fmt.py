"""Human formatting for table cells.

Every helper tolerates None/missing/garbage and returns a string — tables are
built from API fields that may be absent (rule: build tables defensively).
JSON output never passes through here; these are display-only.
"""

from __future__ import annotations

from datetime import datetime

from rich.markup import escape

_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def is_num(v: object) -> bool:
    """True for real numbers only (bool excluded — it's an int in Python)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def safe(v: object) -> str:
    """A box- or user-sourced value → markup-escaped cell text.

    Hostnames, SSIDs, and file names come from the network; without escaping,
    a device named `evil[/]` crashes Rich rendering and `[red]…` spoofs table
    styling. None → "" so `if value:` row-skipping keeps working.
    """
    if v is None:
        return ""
    return escape(str(v))


def human_bytes(n: object) -> str:
    """1234567 → '1.2 MB' (decimal units, matching the Freebox UI)."""
    if not is_num(n):
        return ""
    value = float(n)
    for unit in _UNITS:
        if abs(value) < 1000 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f}".rstrip("0").rstrip(".") + f" {unit}"
        value /= 1000
    return ""  # pragma: no cover — loop always returns


def human_rate(n: object) -> str:
    """Bytes/sec → '1.2 MB/s'."""
    s = human_bytes(n)
    return f"{s}/s" if s else ""


def human_bits(n: object) -> str:
    """Bits/sec → '8 Gbit/s' (link capacities are advertised in bits)."""
    if not is_num(n):
        return ""
    value = float(n)
    for unit in ["bit/s", "kbit/s", "Mbit/s", "Gbit/s", "Tbit/s"]:
        if abs(value) < 1000 or unit == "Tbit/s":
            return f"{value:.1f}".rstrip("0").rstrip(".") + f" {unit}"
        value /= 1000
    return ""  # pragma: no cover — loop always returns


def epoch(ts: object) -> str:
    """Unix seconds → local 'YYYY-MM-DD HH:MM'."""
    if not is_num(ts) or ts <= 0:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


def duration(secs: object) -> str:
    """Seconds → compact '11h 13m' / '42s' / '3d 2h'."""
    if not is_num(secs) or secs < 0:
        return ""
    s = int(secs)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    if s < 86400:
        return f"{s // 3600}h {s % 3600 // 60:02d}m"
    return f"{s // 86400}d {s % 86400 // 3600}h"


def centi_dbm(v: object) -> str:
    """Optical power in hundredths of a dBm → '-18.38 dBm' (SFP telemetry)."""
    if not is_num(v):
        return ""
    return f"{v / 100:.2f} dBm"


def yesno(v: object) -> str:
    if v is None:
        return ""
    return "yes" if v else "no"


def onoff(v: object) -> str:
    if v is None:
        return ""
    return "on" if v else "off"
