"""`fbx contacts` — the address book (empty on the reference box)."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login

runner = CliRunner()

CONTACTS = [
    {
        "id": 1,
        "display_name": "person-1",
        "first_name": "person",
        "last_name": "1",
        "company": "ACME",
        "numbers": [{"id": 1, "number": "+3310000001", "type": "mobile"}],
    }
]


@respx.mock
def test_empty_book_normalizes_to_empty_list():
    authorize()
    mock_login()
    # Captured reality: empty address book → bare {"success": true}, no result.
    mock_get("contact/", envelope={"success": True})
    result = runner.invoke(app, ["--json", "contacts", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


@respx.mock
def test_empty_book_table_renders():
    authorize()
    mock_login()
    mock_get("contact/", envelope={"success": True})
    result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0
    assert "Contacts — 0" in result.stdout


@respx.mock
def test_list_table_shows_contact():
    authorize()
    mock_login()
    mock_get("contact/", CONTACTS)
    result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0
    assert "person-1" in result.stdout
    assert "ACME" in result.stdout
    assert "+3310000001" in result.stdout
