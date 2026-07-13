"""`fbx storage` — disks and partitions against captured shapes."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login

runner = CliRunner()

PARTITION = {
    "id": 1001,
    "disk_id": 1000,
    "label": "Freebox",
    "fstype": "ext4",
    "state": "mounted",
    "internal": False,
    "total_bytes": 984260000000,
    "used_bytes": 626210000000,
    "free_bytes": 358030000000,
    "fsck_result": "no_run_yet",
    "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS00",  # → /Freebox/scrubbed/file-4
}

DISKS = [
    {
        "id": 1000,
        "type": "usb",
        "connector": 0,
        "state": "enabled",
        "table_type": "gpt",
        "total_bytes": 1000000000000,
        "temp": 0,
        "spinning": False,
        "idle": True,
        "read_requests": 847962,
        "write_requests": 553288,
        "read_error_requests": 0,
        "write_error_requests": 0,
        "model": "",
        "firmware": "",
        "serial": "",
        "partitions": [PARTITION],
    }
]


@respx.mock
def test_disks_json_is_whole_result():
    authorize()
    mock_login()
    mock_get("storage/disk/", DISKS)
    result = runner.invoke(app, ["--json", "storage", "disks"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == DISKS


@respx.mock
def test_disks_table_shows_capacity():
    authorize()
    mock_login()
    mock_get("storage/disk/", DISKS)
    result = runner.invoke(app, ["storage", "disks"])
    assert result.exit_code == 0
    assert "usb" in result.stdout
    assert "1 TB" in result.stdout
    assert "idle" in result.stdout


@respx.mock
def test_partitions_table_decodes_path_and_computes_usage():
    authorize()
    mock_login()
    mock_get("storage/partition/", [PARTITION])
    result = runner.invoke(app, ["storage", "partitions"])
    assert result.exit_code == 0
    # Base64 decoded for humans ("/Freebox…" only appears decoded; the cell may
    # be ellipsized by the 80-col test terminal, so match the head of the path).
    assert "/Freebox" in result.stdout
    assert "64%" in result.stdout
    assert "ext4" in result.stdout


@respx.mock
def test_partitions_json_keeps_encoded_path():
    authorize()
    mock_login()
    mock_get("storage/partition/", [PARTITION])
    result = runner.invoke(app, ["--json", "storage", "partitions"])
    payload = json.loads(result.stdout)
    # JSON is the upstream object — the path stays base64 (feedable to fs/ls).
    assert payload[0]["path"] == "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS00"
