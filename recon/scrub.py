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
import base64
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
    "cloudinit_userdata",  # cloud-init YAML: ssh keys, sometimes passwords
    "comment",             # free-text user comments (DHCP leases, etc.)
    # contact-record free text / postal data
    "street", "address", "note", "notes", "zip_code", "zipcode", "city",
    "birthday",
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
    "default_name": "host",
    "domain_name": "host",
    "device_name": "host",   # /player, and app-authorization records
    "friendlyname": "host",  # UPnP-advertised device name
    "cloudinit_hostname": "host",
    "name_dns": "host",      # lan/config box names
    "name_mdns": "host",
    "name_netbios": "host",
    "custom_key_ssid": "ssid",
    "profile_name": "person",
    "display_name": "person",
    "first_name": "person",
    "last_name": "person",
    "company": "person",
    "owner": "person",
    # VPN client / DDNS / SIP / FTP credentials & endpoints
    "remote_host": "host",
    "user": "person",
    "username": "person",
    "login": "person",
    "label": "host",        # storage volume labels ("Extreme SSD")
    "number": "phone",      # call-log numbers, any national format
    "disk_path": "b64path",
    "cd_path": "b64path",
    "download_dir": "b64path",
}

# fs-entry "path"/"filepath" values are base64url of a real (often personal)
# path — but the same key names also carry plain API endpoint paths in our
# own harvest records. Only the base64 form is scrubbed: a value starting
# with "/" is a plain path and passes through (see scrub_field).
B64PATH_KEYS = {"path", "filepath"}

# Values that must never be pool-scrubbed even when a shape rule matches —
# API placeholders ("call" is the call log's stand-in when no caller ID
# resolves), Free's own product names, and factory-default device names that
# identify a device *type*, not a person. Checked case-insensitively.
NEVER_SCRUB_VALUES = {
    "call", "unknown", "inconnu", "n/a", "none", "-", "",
    "freebox server", "freebox-server", "freebox player", "freebox player pop",
    "freebox", "freebox-delta", "freebox-ultra",
    "linux", "android", "iphone", "ipad", "mac", "pc", "windows",
    "xboxone", "xbox one", "playstation",
    # factory-default Freebox disk folder names — present on every box
    "vms", "téléchargements", "musiques", "photos", "vidéos",
    "enregistrements", "disque dur", "disque dur interne",
}

# The bare key "name" is too polymorphic to scrub unconditionally — it's also
# a sensor label ("Température CPU 1"), a fan label, a box model name, a
# torrent/file name, none of which are identifying. Instead, disambiguate by
# the OTHER keys present alongside "name" in the same dict (its "shape"):
# every one of these shapes is a real, observed Freebox API record type that
# names a person or a device. required: ALL must be present as siblings;
# forbidden: NONE may be present (excludes lookalike shapes, e.g. a Home/PVR
# category tile is {category,icon,name,type} — icon+type alone would
# wrongly match the player-device shape without the "category" exclusion).
NAME_SHAPE_RULES: list[tuple[frozenset[str], frozenset[str], str]] = [
    # LAN host's name-with-provenance record: {name, source}
    (frozenset({"source"}), frozenset(), "host"),
    # call log entry (caller display name): {name, number, contact_id, ...}
    (frozenset({"number"}), frozenset(), "person"),
    (frozenset({"contact_id"}), frozenset(), "person"),
    # parental-control profile record: exactly {id, name, icon}
    (frozenset({"id", "icon"}), frozenset({"type", "category"}), "person"),
    # LAN host's network_control association: {current_mode, profile_id, name}
    (frozenset({"profile_id"}), frozenset(), "person"),
    # VM record: {..., mac, vcpus, cloudinit_hostname, ...}
    (frozenset({"vcpus"}), frozenset(), "host"),
    # push-notification target device: {..., api_url, subscriptions, ...}
    (frozenset({"api_url"}), frozenset(), "host"),
    # AirMedia receiver: {name, capabilities, password_protected}
    (frozenset({"capabilities"}), frozenset(), "host"),
    (frozenset({"password_protected"}), frozenset(), "host"),
    # cast/player-type target device: {icon, name, type} but NOT a category tile
    (frozenset({"icon", "type"}), frozenset({"category", "id"}), "host"),
    # download task (torrent/file names are personal): {..., tx_pct, rx_pct}
    (frozenset({"tx_pct"}), frozenset(), "file"),
    # download file entry / fs listing entry: both carry a base64 "path"
    (frozenset({"path"}), frozenset(), "file"),
]

# Leaf values under keys matching this are exempt from the pattern pass:
# firmware versions like "4.8.9.1" would otherwise be mistaken for public
# IPv4 addresses. Anchored so that 'conversion'/'diversion' don't match.
VERSION_KEY_RE = re.compile(r"(?:^|_)version$|^firmware", re.I)

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
# a MAC with separators stripped: exactly 12 hex chars, standalone, and with
# at least one letter so we don't nuke 12-digit decimal counters/timestamps.
MAC_NOSEP_RE = re.compile(
    r"(?<![0-9A-Za-z])(?=[0-9A-Fa-f]{12}(?![0-9A-Fa-f]))(?=[0-9]*[A-Fa-f])[0-9A-Fa-f]{12}"
)
# International phone numbers beyond the French formats PHONE_RE handles:
# a leading + and 8–14 digits (optionally spaced), e.g. +49..., +1...
INTL_PHONE_RE = re.compile(r"(?<![\w+])\+\d[\d\s.\-]{7,17}\d(?!\w)")
# base64url fs paths embedded in request URLs: /fs/ls/<b64>, /dl/<b64>,
# and as query params (?node=<b64>, &path=<b64>, …)
FS_URL_RE = re.compile(r"(?<=/)(?:ls|dl|rm|mv|cp|mkdir|share)/([A-Za-z0-9%_=-]{4,})")
FS_PARAM_RE = re.compile(r"(?<=[?&])(?:node|path|dir|folder)=([A-Za-z0-9%_=-]{4,})")


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
        if pool == "file":
            return f"file-{n}"
        if pool == "b64path":
            # keep the base64url encoding the fs API uses, but of a fake path
            return base64.urlsafe_b64encode(f"/Freebox/scrubbed/file-{n}".encode()).decode()
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

def _normkey(key: str) -> str:
    return re.sub(r"[\s-]+", "_", key.strip().lower())


_B64_RE = re.compile(r"^[A-Za-z0-9_-]{8,}={0,2}$")


def _decodes_to_path(value: str) -> bool:
    """True if value is base64url of an absolute filesystem path.

    The Freebox fs API encodes every path this way (/fs/ls/<b64>, download
    dirs, share targets, watch dirs, …). Catching them by *value shape*
    rather than key name closes the whole class in one rule — no field can
    be forgotten. Guarded tightly (clean UTF-8, printable, leading '/') so it
    won't fire on icon blobs, tokens, or hashes.
    """
    if not _B64_RE.match(value) or len(value) % 4 == 1:
        return False
    try:
        dec = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        t = dec.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    return t.startswith("/") and t.isprintable() and "/scrubbed/" not in t


def scrub_value(obj, m: ScrubMap, key: str | None = None):
    if isinstance(obj, dict):
        siblings = {_normkey(k) for k in obj}
        return {k: scrub_field(k, v, m, siblings) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_value(v, m, key) for v in obj]
    if isinstance(obj, str):
        return scrub_string(obj, m, key)
    return obj


def scrub_field(key: str, value, m: ScrubMap, siblings: frozenset[str] = frozenset()):
    lk = _normkey(key)
    if lk in SECRET_KEYS and isinstance(value, str) and value:
        return f"SCRUBBED_{lk.upper()}"
    never = isinstance(value, str) and value.lower() in NEVER_SCRUB_VALUES
    # The recon capture envelope is {label, http, ws} / {label, harvest}; its
    # "label" is our own section name (metadata we chose), not box data.
    if lk == "label" and siblings & {"http", "ws", "harvest"}:
        return scrub_value(value, m, key)
    # Any *_serial (sfp_serial, disk_serial, …) is a hardware identifier.
    if (lk == "serial" or lk.endswith("_serial")) and isinstance(value, str) and value:
        return m.get("serial", value)
    if lk in POOL_KEYS and isinstance(value, str) and value and not never:
        return m.get(POOL_KEYS[lk], value)
    if (
        lk in B64PATH_KEYS and isinstance(value, str) and value
        and not never and not value.startswith("/")
    ):
        return m.get("b64path", value)
    if lk == "name" and isinstance(value, str) and value and not never:
        for required, forbidden, pool in NAME_SHAPE_RULES:
            if required <= siblings and not (forbidden & siblings):
                return m.get(pool, value)
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

    # Value-shape catch-all for base64url'd fs paths, whatever the key.
    if _decodes_to_path(s):
        return m.get("b64path", s)

    if key is not None and VERSION_KEY_RE.search(key):
        return s

    s = FS_URL_RE.sub(
        lambda mt: mt.group(0)[: -len(mt.group(1))] + m.get("b64path", mt.group(1)), s
    )
    s = FS_PARAM_RE.sub(
        lambda mt: mt.group(0)[: -len(mt.group(1))] + m.get("b64path", mt.group(1)), s
    )
    s = FBXOS_RE.sub(lambda mt: m.get("fbxos", mt.group(0)), s)
    s = EMAIL_RE.sub(lambda mt: m.get("email", mt.group(0)), s)
    s = PHONE_RE.sub(lambda mt: m.get("phone", mt.group(0)), s)

    def _intl_phone_repl(mt: re.Match) -> str:
        # Don't re-scrub our own fake phones (+33100000NN) into phone-of-phone.
        if re.sub(r"[\s.\-]", "", mt.group(0)).startswith("+33100000"):
            return mt.group(0)
        return m.get("phone", mt.group(0))

    s = INTL_PHONE_RE.sub(_intl_phone_repl, s)

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

    def _mac_nosep_repl(mt: re.Match) -> str:
        # Key the map by the colon'd form so the same device maps identically
        # whether written "aabbcc.." or "aa:bb:cc.."; emit sep-less to match.
        colon = ":".join(mt.group(0).lower()[i:i + 2] for i in range(0, 12, 2))
        return m.get("mac", colon).replace(":", "")

    s = MAC_NOSEP_RE.sub(_mac_nosep_repl, s)
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
    for mt in INTL_PHONE_RE.finditer(text):
        if not re.sub(r"[\s.\-]", "", mt.group(0)).startswith("+33100000"):
            problems.append(f"intl phone survives: {mt.group(0)}")
    for mt in EMAIL_RE.finditer(text):
        if not mt.group(0).endswith("@example.com"):
            problems.append(f"email survives: {mt.group(0)}")
    for mt in MAC_NOSEP_RE.finditer(text):
        if not mt.group(0).lower().startswith("020000000"):
            problems.append(f"sep-less MAC survives: {mt.group(0)}")
    for mt in HEXBLOB_RE.finditer(text):
        problems.append(f"long hex blob survives: {mt.group(0)[:16]}…")
    for tok in re.findall(r"[A-Za-z0-9_-]{12,}={0,2}", text):
        if _decodes_to_path(tok):
            dec = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8")
            problems.append(f"base64 fs path survives: {tok[:20]}… -> {dec[:40]}")
    return problems


def check_against_map(text: str, m: ScrubMap) -> list[str]:
    """Defense in depth: every real value the map has ever scrubbed
    successfully, anywhere, must never appear literally in scrubbed output —
    independent of which key-name or shape rule caught it originally. This
    catches leaks through structural shapes the rules don't yet know about,
    as long as the same real value was scrubbed at least once elsewhere.
    """
    # Strip our own fake-value markers first — e.g. the real value "BED" is a
    # substring of the literal marker "SCRUBBED", which would otherwise
    # false-positive on every redacted secret in the document.
    haystack = re.sub(r"SCRUBBED[A-Z0-9_]*", "", text)
    problems: list[str] = []
    for pool, bucket in m.map.items():
        for real in bucket:
            if len(real) < 3:
                continue
            # Word-boundary match: a real hostname "linux" must not flag the
            # public URL "alpinelinux.org"; "Plexi" inside "Plexi.qcow2" must.
            if re.search(
                r"(?<![A-Za-z0-9])" + re.escape(real) + r"(?![A-Za-z0-9])", haystack
            ):
                problems.append(f"real {pool} value survives verbatim: {real!r}")
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
                    "default_name": "MacBook-Pro",
                    "domain_name": "macbook-pro-2.home",
                    "l2ident": {"id": "AA:BB:CC:DD:EE:FF", "type": "mac_address"},
                    "ipv6": "fe80::a8bb:ccff:fedd:eeff",
                    "names": [
                        {"name": "MacBook-Pro", "source": "dhcp"},
                        {"name": "MacBook-Pro-2", "source": "mdns"},
                    ],
                    "info": {"dhcp": {"Host Name": "MacBook-Pro"}},
                    "network_control": {
                        "current_mode": "allowed", "profile_id": 1, "name": "Kevin",
                    },
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
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/profile",
            "resBody": json.dumps({
                "result": [{"id": 1, "name": "Kevin", "icon": "/resources/profile_03.png"}],
            }),
        },
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/downloads/config/",
            "resBody": json.dumps({
                "result": {
                    # base64url of "/Disque dur/Perso de Kevin" under a key the
                    # POOL_KEYS list does NOT contain — must still be caught by
                    # the value-shape heuristic.
                    "watch_dir": base64.urlsafe_b64encode(
                        "/Disque dur/Perso de Kevin".encode()).decode(),
                },
            }),
        },
        {
            "method": "GET",
            "url": "http://mafreebox.freebox.fr/api/v14/system/",
            "resBody": json.dumps({
                "result": {
                    "sensors": [{"id": "temp_cpu1", "name": "Température CPU 1", "value": 59}],
                    "fans": [{"id": "fan0_speed", "name": "Ventilateur 1", "value": 660}],
                    "model_info": {"name": "fbxgw9-r1"},
                },
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
    problems += check_against_map(text, m)
    for needle in (
        "FBX1234567890", "a1b2c3d4e5f6", "68:A3:78", "68:a3:78", "abcd1234.fbxos",
        "88.123.45.67", "2a01:", "MacBook-de-Kevin", "AA:BB:CC", "aa:bb:cc",
        "MaisonKevin", "SuperSecret", "35JYdQSvkcBYK54", "6 12 34 56 78",
        "0612345678", "maman@gmail.com", "fedcba98",
        # shapes disambiguated by sibling keys (names[], call log, profile, network_control)
        "MacBook-Pro", "macbook-pro-2.home",
    ):
        if needle in text:
            problems.append(f"needle survives: {needle!r}")

    # Stability: same MAC in two places -> same fake.
    ws_rx = json.loads(out["ws"][1]["data"])
    lan = json.loads(out["http"][3]["resBody"])
    if ws_rx["result"]["mac"] != lan["result"][0]["l2ident"]["id"]:
        problems.append("mapping not stable across occurrences")

    # Names disambiguated by sibling-key shape (not substring-safe to needle-check
    # since "Kevin"/"Maman" could coincidentally appear inside a generated fake).
    lan0 = lan["result"][0]
    if lan0["network_control"]["name"] == "Kevin":
        problems.append("network_control.name (person, via profile_id sibling) not scrubbed")
    if lan0["names"][0]["name"] == "MacBook-Pro":
        problems.append("names[].name (host, via source sibling) not scrubbed")
    if lan0["info"]["dhcp"]["Host Name"] == "MacBook-Pro":
        problems.append("info.dhcp.'Host Name' (space in key) not scrubbed")
    calllog = json.loads(out["http"][5]["resBody"])["result"]
    if calllog[0]["name"] == "Maman":
        problems.append("call log name (person, via number sibling) not scrubbed")
    if json.loads(out["http"][6]["resBody"])["result"][0]["name"] == "Kevin":
        problems.append("profile name (person, via icon sibling) not scrubbed")
    watch = json.loads(out["http"][7]["resBody"])["result"]["watch_dir"]
    if _decodes_to_path(watch) and "Kevin" in base64.urlsafe_b64decode(
        watch + "=" * (-len(watch) % 4)
    ).decode("utf-8"):
        problems.append("base64 fs path (unmapped key 'watch_dir') not scrubbed")

    # Stability: the same real name ("Kevin", via network_control) scrubbed in
    # two different shapes must produce the SAME fake — both are person pool.
    nc_name = lan["result"][0]["network_control"]["name"]
    profile_name = json.loads(out["http"][6]["resBody"])["result"][0]["name"]
    if nc_name != profile_name:
        problems.append("same real name scrubbed to two different fakes")

    # Fidelity: things that must NOT be touched.
    sysinfo = json.loads(out["http"][0]["resBody"])
    if sysinfo["result"]["firmware_version"] != "4.8.9.1":
        problems.append("firmware version was mangled")
    conn = json.loads(out["http"][2]["resBody"])
    if conn["result"]["ipv4_local"] != "192.168.1.254":
        problems.append("private LAN IP was mangled")
    sys2 = json.loads(out["http"][8]["resBody"])["result"]
    if sys2["sensors"][0]["name"] != "Température CPU 1":
        problems.append("sensor label was wrongly scrubbed")
    if sys2["fans"][0]["name"] != "Ventilateur 1":
        problems.append("fan label was wrongly scrubbed")
    if sys2["model_info"]["name"] != "fbxgw9-r1":
        problems.append("box model name was wrongly scrubbed")

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
        m = ScrubMap()
        bad = 0
        for f in args.files:
            text = Path(f).read_text()
            problems = check_document(text) + check_against_map(text, m)
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
            text = dst.read_text()
            residue = check_document(text) + check_against_map(text, m)
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
        text = dst.read_text()
        residue = check_document(text) + check_against_map(text, m)
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
