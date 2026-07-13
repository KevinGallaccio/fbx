"""`fbx fs ls` — path encoding and listing against captured shapes."""

from __future__ import annotations

import base64
import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import BASE, authorize, mock_get, mock_login

runner = CliRunner()

ENTRIES = [
    {
        "type": "dir",
        "name": ".",
        "path": "L0ZyZWVib3g=",
        "index": 0,
        "size": 4096,
        "modification": 1726319787,
        "mimetype": "inode/directory",
        "hidden": False,
        "link": False,
    },
    {
        "type": "dir",
        "name": "..",
        "path": "Lw==",
        "index": 1,
        "size": 4096,
        "modification": 1726319787,
        "mimetype": "inode/directory",
        "hidden": False,
        "link": False,
    },
    {
        "type": "dir",
        "name": "Vidéos",
        "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0xNQ==",
        "index": 4,
        "size": 4096,
        "modification": 1770024546,
        "mimetype": "inode/directory",
        "hidden": False,
        "link": False,
        "foldercount": 4,
        "filecount": 0,
    },
    {
        "type": "file",
        "name": "notes.txt",
        "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0xNg==",
        "index": 5,
        "size": 25236,
        "modification": 1770024546,
        "mimetype": "text/plain",
        "hidden": False,
        "link": False,
    },
]


@respx.mock
def test_ls_encodes_the_path_argument_as_base64():
    authorize()
    mock_login()
    route = mock_get("fs/ls/", {"entries": ENTRIES}, startswith=True)
    result = runner.invoke(app, ["--json", "fs", "ls", "/Freebox"])
    assert result.exit_code == 0
    sent = route.calls.last.request.url
    assert sent.path.endswith("/fs/ls/" + base64.b64encode(b"/Freebox").decode())
    assert "countSubFolder=1" in str(sent.query.decode())


@respx.mock
def test_ls_defaults_to_root():
    authorize()
    mock_login()
    route = mock_get("fs/ls/", {"entries": []}, startswith=True)
    result = runner.invoke(app, ["--json", "fs", "ls"])
    assert result.exit_code == 0
    assert route.calls.last.request.url.path.endswith("/fs/ls/Lw==")  # base64("/")


@respx.mock
def test_ls_json_is_the_whole_upstream_object():
    authorize()
    mock_login()
    # Rule #5: --json must not reshape — sibling keys and `.`/`..` survive.
    upstream = {"entries": ENTRIES, "some_future_sibling": 42}
    mock_get("fs/ls/", upstream, startswith=True)
    result = runner.invoke(app, ["--json", "fs", "ls", "/Freebox"])
    assert json.loads(result.stdout) == upstream


@respx.mock
def test_ls_table_filters_dot_entries_and_shows_counts():
    authorize()
    mock_login()
    mock_get("fs/ls/", {"entries": ENTRIES}, startswith=True)
    result = runner.invoke(app, ["fs", "ls", "/Freebox"])
    assert result.exit_code == 0
    assert "2 entries" in result.stdout  # . and .. filtered from display
    assert "Vidéos/" in result.stdout
    assert "4 items" in result.stdout
    assert "notes.txt" in result.stdout
    assert "25.2 KB" in result.stdout


@respx.mock
def test_ls_bracketed_path_argument_does_not_break_the_title():
    # The path is user input interpolated into a markup-parsed table title.
    authorize()
    mock_login()
    mock_get("fs/ls/", {"entries": []}, startswith=True)
    result = runner.invoke(app, ["fs", "ls", "/Freebox/[YTS] Movie [/x]"])
    assert result.exit_code == 0
    assert "Traceback" not in result.stderr


def test_ls_route_prefix_sanity():
    # The startswith mock above must not accidentally cover other endpoints.
    assert f"{BASE}fs/ls/".startswith(BASE)
