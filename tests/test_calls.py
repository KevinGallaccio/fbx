"""`fbx calls` — the call log against captured shapes."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login

runner = CliRunner()

LOG = [
    {
        "id": 10,
        "datetime": 1777904840,
        "type": "missed",
        "number": "+3310000001",
        "name": "person-1",
        "contact_id": 0,
        "duration": 29,
        "new": True,
    },
    {
        "id": 9,
        "datetime": 1764688798,
        "type": "outgoing",
        "number": "+3310000002",
        "name": "person-2",
        "contact_id": 0,
        "duration": 95,
        "new": False,
    },
]


@respx.mock
def test_list_json_is_whole_result():
    authorize()
    mock_login()
    mock_get("call/log/", LOG)
    result = runner.invoke(app, ["--json", "calls", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == LOG


@respx.mock
def test_list_table_shows_calls():
    authorize()
    mock_login()
    mock_get("call/log/", LOG)
    result = runner.invoke(app, ["calls", "list"])
    assert result.exit_code == 0
    assert "missed" in result.stdout
    assert "+3310000001" in result.stdout
    assert "person-1" in result.stdout
    assert "29s" in result.stdout
    assert "1m 35s" in result.stdout


@respx.mock
def test_mixed_type_datetimes_do_not_crash_the_sort():
    authorize()
    mock_login()
    mixed = [dict(LOG[0]), dict(LOG[1], datetime="not-an-epoch")]
    mock_get("call/log/", mixed)
    result = runner.invoke(app, ["calls", "list"])
    assert result.exit_code == 0
    assert "person-2" in result.stdout  # bad-datetime row still rendered


@respx.mock
def test_empty_log_normalizes():
    authorize()
    mock_login()
    mock_get("call/log/", envelope={"success": True})
    result = runner.invoke(app, ["--json", "calls", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []
