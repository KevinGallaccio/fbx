#!/usr/bin/env python3
"""Scrub Freebox recon captures so they are safe to commit to a public repo.

Raw captures (from the in-page fetch/XHR/WebSocket tap) contain the box
serial, its uid, every MAC on the LAN, the WAN IP, session tokens, Wi-Fi
passphrases, possibly phone numbers and contacts. This script replaces all
of it with stable fake values:

    MAC addresses              -> 02:00:00:00:xx:xx   (locally administered)
    public IPv4                -> 203.0.113.N         (TEST-NET-3, then TEST-NET-2)
    IPv6 (global)              -> 2001:db8::N         (documentation prefix)
    IPv6 (link-local)          -> fe80::N             (EUI-64 embeds the MAC)
    *.fbxos.fr remote domains  -> fake-N.fbxos.fr
    French phone numbers       -> +33100000NN
    emails                     -> userN@example.com
    long hex blobs (>=32)      -> SCRUBBED_HEX_N      (challenges, hashes)
    secret-named fields        -> SCRUBBED_<KEY>
    serial/uid/ssid/hostnames  -> stable fakes from a named pool

"Stable" means a given real value always maps to the same fake value, within
and across runs, so cross-references between capture files stay coherent.
The real<->fake mapping is persisted in recon/raw/scrub_map.json — inside
the gitignored raw/ directory, never committed.

Usage:
    python recon/scrub.py --selftest
    python recon/scrub.py --all                # recon/raw/*.json -> recon/capture/
    python recon/scrub.py raw.json out.json    # single file
    python recon/scrub.py --check FILE...      # verify no identifying data remains
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path

RECON_DIR = Path(__file__).resolve().parent
RAW_DIR = RECON_DIR / "raw"
CAPTURE_DIR = RECON_DIR / "capture"
MAP_PATH = RAW_DIR / "scrub_map.json"

# ---------------------------------------------------------------------------
# Field-name rules
# ---------------------------------------------------------------------------

# Replaced with "SCRUBBED_<KEY>" whenever the value is a non-empty string.
SECRET_KEYS = {
    "app_token", "session_token", "challenge", "password", "password_salt",
    "pwd", "passphrase", "key", "wpa_key", "psk", "pre_shared_key",
    "private_key", "public_key", "secret", "token", "api_key", "wps_pin",
    "pin", "cert", "certificate", "ca_cert", "client_cert", "crt",
}

# Replaced with a stable fake from the named pool.
POOL_KEYS = {
    "serial": "serial",
    "uid": "uid",
    "box_uid": "uid",
    "ssid": "ssid",
    "bss_name": "ssid",
    "primary_name": "host",
    "host_name": "host",
    "hostname": "host",
    "display_name": "person",
    "first_name": "person",
    "last_name": "person",
    "company": "person",
    "owner": "person",
}

# Leaf values under keys matching this are exempt from the pattern pass:
# firmware versions like "4.8.9.1" would otherwise be mistaken for public
# IPv4 addresses.
VERSION_KEY_RE = re.compile(r"version|firmware", re.I)

# ---------------------------------------------------------------------------
# Pattern rules (applied to every string value, and inside nested JSON)
# ---------------------------------------------------------------------------

MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# Greedy candidates; ipaddress.ip_address() is the real gate.
IPV6_CAND_RE = re.compile(r"(?<![\w:.])[0-9A-Fa-f:]*::?[0-9A-Fa-f:]+(?![\w:])")
FBXOS_RE = re.compile(r"\b[A-Za-z0-9-]+\.fbxos\.fr\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+33|0033)\s?[1-9](?:[\s.\-]?\d{2}){4}(?!\d)"
    r"|(?<![\d.+])0[1-9](?:[\s.\-]?\d{2}){4}(?![\d.])"
)
HEXBLOB_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def _ipv4_is_safe(ip: ipaddress.IPv4Address) -> bool:
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def _ipv6_is_safe(ip: ipaddress.IPv6Address) -> bool:
    # Link-local is NOT safe: EUI-64 addresses embed the interface MAC.
    return ip.is_loopback or ip.is_unspecified or ip.is_multicast


class ScrubMap:
    """Stable real->fake mapping, persisted inside the gitignored raw/ dir."""

    def __init__(self, path: Path | None = MAP_PATH):
        self.path = path
        self.map: dict[str, dict[str, str]] = {}
        if path is not None and path.exists():
            self.map = json.loads(path.read_text())

    def get(self, pool: str, real: str, factory=None) -> str:
        bucket = self.map.setdefault(pool, {})
        if real not in bucket:
            n = len(bucket) + 1
            bucket[real] = factory(n) if factory else self._fake(pool, n)
        return bucket[real]

    @staticmethod
    def _fake(pool: str, n: int) -> str:
        if pool == "mac":
            return f"02:00:00:00:{(n >> 8) & 0xFF:02x}:{n & 0xFF:02x}"
        if pool == "ipv4":
            return f"203.0.113.{n}" if n <= 254 else f"198.51.100.{n - 254}"
        if pool == "ipv6":
            return f"2001:db8::{n:x}"
        if pool == "fbxos":
            return f"fake-{n}.fbxos.fr"
        if pool == "phone":
            return f"+33100000{n:02d}"
        if pool == "email":
            return f"user{n}@example.com"
        if pool == "serial":
            return f"SCRUBBEDSERIAL{n:04d}"
        if pool == "uid":
            return f"scrubbed-uid-{n}"
        if pool == "ssid":
            return f"scrubbed-ssid-{n}"
        if pool == "host":
            return f"host-{n}"
        if pool == "person":
            return f"person-{n}"
        if pool == "hex":
            return f"SCRUBBED_HEX_{n}"
        return f"scrubbed-{pool}-{n}"

    def save(self) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.map, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Scrubbing
# ---------------------------------------------------------------------------

def scrub_value(obj, m: ScrubMap, key: str | None = None):
    if isinstance(obj, dict):
        return {k: scrub_field(k, v, m) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_value(v, m, key) for v in obj]
    if isinstance(obj, str):
        return scrub_string(obj, m, key)
    return obj


def scrub_field(key: str, value, m: ScrubMap):
    lk = key.lower()
    if lk in SECRET_KEYS and isinstance(value, str) and value:
        return f"SCRUBBED_{lk.upper()}"
    if lk in POOL_KEYS and isinstance(value, str) and value:
        return m.get(POOL_KEYS[lk], value)
    return scrub_value(value, m, key)


def scrub_string(s: str, m: ScrubMap, key: str | None = None) -> str:
    # Nested JSON (reqBody / resBody / WebSocket frames): parse, scrub the
    # structure so field-name rules apply inside, re-serialize compactly.
    stripped = s.lstrip()
    if stripped[:1] in ("{", "["):
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, RecursionError):
            pass
        else:
            if isinstance(parsed, (dict, list)):
                return json.dumps(
                    scrub_value(parsed, m), separators=(",", ":"),
                    ensure_ascii=False,
                )

    if key is not None and VERSION_KEY_RE.search(key):
        return s

    s = FBXOS_RE.sub(lambda mt: m.get("fbxos", mt.group(0)), s)
    s = EMAIL_RE.sub(lambda mt: m.get("email", mt.group(0)), s)
    s = PHONE_RE.sub(lambda mt: m.get("phone", mt.group(0)), s)

    def _ipv6_repl(mt: re.Match) -> str:
        try:
            ip = ipaddress.IPv6Address(mt.group(0))
        except ValueError:
            return mt.group(0)
        if _ipv6_is_safe(ip):
            return mt.group(0)
        if ip.is_link_local:
            return m.get("ipv6_ll", mt.group(0), lambda n: f"fe80::{n:x}")
        return m.get("ipv6", mt.group(0))

    s = IPV6_CAND_RE.sub(_ipv6_repl, s)

    def _ipv4_repl(mt: re.Match) -> str:
        try:
            ip = ipaddress.IPv4Address(mt.group(0))
        except ValueError:
            return mt.group(0)
        return mt.group(0) if _ipv4_is_safe(ip) else m.get("ipv4", mt.group(0))

    s = IPV4_RE.sub(_ipv4_repl, s)
    s = MAC_RE.sub(lambda mt: m.get("mac", mt.group(0).lower()), s)
    s = HEXBLOB_RE.sub(lambda mt: m.get("hex", mt.group(0).lower()), s)
    return s


def scrub_file(src: Path, dst: Path, m: ScrubMap) -> None:
    data = json.loads(src.read_text())
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(scrub_value(data, m), indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# --check: verify a scrubbed file has nothing identifying left
# ---------------------------------------------------------------------------

def check_value(obj, key: str | None = None) -> list[str]:
    """Structure-aware check mirroring scrub_value's key exemptions."""
    problems: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            problems += check_value(v, k)
    elif isinstance(obj, list):
        for v in obj:
            problems += check_value(v, key)
    elif isinstance(obj, str):
        if obj.lstrip()[:1] in ("{", "["):
            try:
                parsed = json.loads(obj)
            except (json.JSONDecodeError, RecursionError):
                parsed = None
            if isinstance(parsed, (dict, list)):
                return check_value(parsed, key)
        if key is not None and VERSION_KEY_RE.search(key):
            return problems
        problems += check_text(obj)
    return problems


def check_document(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return check_text(text)
    return check_value(data)


def check_text(text: str) -> list[str]:
    """Return problems found; whitelists our own fake namespaces."""
    problems: list[str] = []
    for mt in MAC_RE.finditer(text):
        if not mt.group(0).lower().startswith("02:00:00:00:"):
            problems.append(f"MAC survives: {mt.group(0)}")
    for mt in IPV4_RE.finditer(text):
        try:
            ip = ipaddress.IPv4Address(mt.group(0))
        except ValueError:
            continue
        if not _ipv4_is_safe(ip) and not (
            mt.group(0).startswith("203.0.113.") or mt.group(0).startswith("198.51.100.")
        ):
            problems.append(f"public IPv4 survives: {mt.group(0)}")
    for mt in IPV6_CAND_RE.finditer(text):
        try:
            ip = ipaddress.IPv6Address(mt.group(0))
        except ValueError:
            continue
        if _ipv6_is_safe(ip):
            continue
        if ip in ipaddress.IPv6Network("2001:db8::/32"):
            continue
        if ip.is_link_local and mt.group(0).lower().startswith("fe80::") and len(mt.group(0)) <= 12:
            continue  # our short fe80::N fakes, not EUI-64
        problems.append(f"IPv6 survives: {mt.group(0)}")
    for mt in FBXOS_RE.finditer(text):
        if not mt.group(0).startswith("fake-"):
            problems.append(f"fbxos domain survives: {mt.group(0)}")
    for mt in PHONE_RE.finditer(text):
        if not re.sub(r"[\s.\-]", "", mt.group(0)).startswith("+33100000"):
            problems.append(f"phone number survives: {mt.group(0)}")
    for mt in EMAIL_RE.finditer(text):
        if not mt.group(0).endswith("@example.com"):
            problems.append(f"email survives: {mt.group(0)}")
    for mt in HEXBLOB_RE.finditer(text):
        problems.append(f"long hex blob survives: {mt.group(0)[:16]}…")
    return problems


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

SELFTEST_SAMPLE = {
    "http": [
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/system/",
            "reqBody": None,
            "status": 200,
            "resBody": json.dumps({
                "success": True,
                "result": {
                    "serial": "FBX1234567890",
                    "uid": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                    "mac": "68:A3:78:12:34:56",
                    "firmware_version": "4.8.9.1",
                    "api_domain": "abcd1234.fbxos.fr",
                },
            }),
        },
        {
            "method": "POST",
            "url": "http://mafreebox.freebox.fr/api/v14/login/session/",
            "reqBody": json.dumps({
                "app_id": "fr.freebox.osnav",
                "password": "0123456789abcdef0123456789abcdef01234567",
            }),
            "status": 200,
            "resBody": json.dumps({
                "success": True,
                "result": {
                    "session_token": "35JYdQSvkcBYK54IFMU7R86QfNSEkFKGHyR1y7vHk",
                    "challenge": "fedcba9876543210fedcba9876543210fedcba98",
                },
            }),
        },
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/connection/",
            "resBody": json.dumps({
                "result": {
                    "ipv4": "88.123.45.67",
                    "ipv6": "2a01:e0a:1234:5678::1",
                    "ipv4_local": "192.168.1.254",
                },
            }),
        },
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/lan/browser/pub/",
            "resBody": json.dumps({
                "result": [{
                    "primary_name": "MacBook-de-Kevin",
                    "l2ident": {"id": "AA:BB:CC:DD:EE:FF", "type": "mac_address"},
                    "ipv6": "fe80::a8bb:ccff:fedd:eeff",
                }],
            }),
        },
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/wifi/bss/",
            "resBody": json.dumps({
                "result": [{"ssid": "MaisonKevin", "key": "SuperSecret123!",
                            "bssid": "68:A3:78:AA:BB:CC"}],
            }),
        },
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/call/log/",
            "resBody": json.dumps({
                "result": [{"number": "+33 6 12 34 56 78", "name": "Maman",
                            "email": "maman@gmail.com"},
                           {"number": "0612345678"}],
            }),
        },
    ],
    "ws": [
        {"dir": "tx", "data": json.dumps({"action": "register",
                                          "events": ["lan_host_l3addr_reachable"]})},
        {"dir": "rx", "data": json.dumps({"event": "lan_host_l3addr_reachable",
                                          "result": {"mac": "AA:BB:CC:DD:EE:FF"}})},
    ],
}


def selftest() -> int:
    m = ScrubMap(path=None)  # in-memory only
    out = scrub_value(SELFTEST_SAMPLE, m)
    text = json.dumps(out, ensure_ascii=False)

    problems = check_value(out)
    for needle in (
        "FBX1234567890", "a1b2c3d4e5f6", "68:A3:78", "68:a3:78", "abcd1234.fbxos",
        "88.123.45.67", "2a01:", "MacBook-de-Kevin", "AA:BB:CC", "aa:bb:cc",
        "MaisonKevin", "SuperSecret", "35JYdQSvkcBYK54", "6 12 34 56 78",
        "0612345678", "maman@gmail.com", "fedcba98",
    ):
        if needle in text:
            problems.append(f"needle survives: {needle!r}")

    # Stability: same MAC in two places -> same fake.
    ws_rx = json.loads(out["ws"][1]["data"])
    lan = json.loads(out["http"][3]["resBody"])
    if ws_rx["result"]["mac"] != lan["result"][0]["l2ident"]["id"]:
        problems.append("mapping not stable across occurrences")

    # Fidelity: things that must NOT be touched.
    sysinfo = json.loads(out["http"][0]["resBody"])
    if sysinfo["result"]["firmware_version"] != "4.8.9.1":
        problems.append("firmware version was mangled")
    conn = json.loads(out["http"][2]["resBody"])
    if conn["result"]["ipv4_local"] != "192.168.1.254":
        problems.append("private LAN IP was mangled")

    if problems:
        print("SELFTEST FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("selftest OK", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="src [dst] for single-file mode, or files for --check")
    ap.add_argument("--all", action="store_true", help="scrub recon/raw/*.json into recon/capture/")
    ap.add_argument("--check", action="store_true", help="verify files contain nothing identifying")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.check:
        bad = 0
        for f in args.files:
            problems = check_document(Path(f).read_text())
            for p in problems:
                print(f"{f}: {p}", file=sys.stderr)
            bad += len(problems)
        print(f"--check: {len(args.files)} file(s), {bad} problem(s)", file=sys.stderr)
        return 1 if bad else 0

    m = ScrubMap()
    if args.all:
        srcs = sorted(RAW_DIR.glob("*.json"))
        srcs = [s for s in srcs if s.name != "scrub_map.json"]
        if not srcs:
            print(f"nothing to scrub in {RAW_DIR}", file=sys.stderr)
            return 1
        for src in srcs:
            dst = CAPTURE_DIR / src.name
            scrub_file(src, dst, m)
            residue = check_document(dst.read_text())
            for p in residue:
                print(f"{dst}: {p}", file=sys.stderr)
            if residue:
                dst.unlink()
                print(f"{src.name}: REJECTED ({len(residue)} problems), output deleted", file=sys.stderr)
            else:
                print(f"{src.name} -> {dst}", file=sys.stderr)
        m.save()
        return 0

    if len(args.files) == 2:
        src, dst = Path(args.files[0]), Path(args.files[1])
        scrub_file(src, dst, m)
        residue = check_document(dst.read_text())
        for p in residue:
            print(f"{dst}: {p}", file=sys.stderr)
        if residue:
            dst.unlink()
            print("REJECTED: output deleted", file=sys.stderr)
            return 1
        m.save()
        return 0

    ap.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
