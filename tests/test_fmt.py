"""Unit tests for the display formatters and the fs-path codec."""

from __future__ import annotations

import re

from fbx.cli import fmt
from fbx.core import fspath

# -- fmt --------------------------------------------------------------------


def test_human_bytes():
    assert fmt.human_bytes(0) == "0 B"
    assert fmt.human_bytes(512) == "512 B"
    assert fmt.human_bytes(1000) == "1 KB"
    assert fmt.human_bytes(1234567) == "1.2 MB"
    assert fmt.human_bytes(984260000000) == "984.3 GB"
    assert fmt.human_bytes(1000000000000) == "1 TB"


def test_human_bytes_rejects_non_numbers():
    assert fmt.human_bytes(None) == ""
    assert fmt.human_bytes("nope") == ""
    assert fmt.human_bytes(True) == ""  # bool is not a size


def test_human_rate_and_bits():
    assert fmt.human_rate(2500000) == "2.5 MB/s"
    assert fmt.human_rate(None) == ""
    assert fmt.human_bits(8000000000) == "8 Gbit/s"


def test_duration():
    assert fmt.duration(42) == "42s"
    assert fmt.duration(95) == "1m 35s"
    assert fmt.duration(40408) == "11h 13m"
    assert fmt.duration(90000) == "1d 1h"
    assert fmt.duration(-5) == ""
    assert fmt.duration(None) == ""


def test_epoch():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", fmt.epoch(1783941970))
    assert fmt.epoch(0) == ""
    assert fmt.epoch(None) == ""


def test_centi_dbm():
    assert fmt.centi_dbm(-1838) == "-18.38 dBm"
    assert fmt.centi_dbm(642) == "6.42 dBm"
    assert fmt.centi_dbm(None) == ""


def test_is_num():
    assert fmt.is_num(5)
    assert fmt.is_num(-55.5)
    assert not fmt.is_num(True)  # bool is an int in Python, but not a number here
    assert not fmt.is_num("5")
    assert not fmt.is_num(None)


def test_safe_escapes_markup():
    assert fmt.safe("evil[/]name") == r"evil\[/]name"
    assert fmt.safe("[red]x") == r"\[red]x"
    assert fmt.safe("plain") == "plain"
    assert fmt.safe(None) == ""  # keeps `if value:` row-skipping working
    assert fmt.safe(42) == "42"


def test_yesno_onoff():
    assert fmt.yesno(True) == "yes"
    assert fmt.yesno(False) == "no"
    assert fmt.yesno(None) == ""
    assert fmt.onoff(True) == "on"
    assert fmt.onoff(False) == "off"


# -- fspath -----------------------------------------------------------------


def test_fspath_roundtrip():
    assert fspath.encode("/") == "Lw=="
    assert fspath.decode("Lw==") == "/"
    assert fspath.decode(fspath.encode("/Freebox/Vidéos")) == "/Freebox/Vidéos"


def test_fspath_decode_passes_through_non_paths():
    assert fspath.decode("not base64!") == "not base64!"
    # Valid base64 that doesn't decode to an absolute path stays as-is.
    assert fspath.decode("aGVsbG8=") == "aGVsbG8="  # "hello"
