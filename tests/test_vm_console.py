"""The VM console pre-flight: explain, offer a choice, never type secrets.

All cloud-init samples are fictional. The suspend/pump path is monkeypatched —
a headless pilot has no terminal to hand over.
"""

from __future__ import annotations

import contextlib

import pytest
import respx
from textual.widgets import Static

from fbx.core.cloudinit import find_credentials
from fbx.tui.app import FbxApp
from fbx.tui.screens.vm import ConsolePreflightModal
from tests.helpers import authorize, mock_get
from tests.test_tui import _mock_dashboard_box, _settle
from tests.test_tui_screens import _open


@pytest.fixture
def anyio_backend():
    return "asyncio"


# -- cloud-init scanning -------------------------------------------------------


def test_find_credentials_chpasswd_block_scalar():
    doc = "#cloud-config\nchpasswd:\n  expire: false\n  list: |\n    demo:s3cretpw\n"
    assert find_credentials(doc) == [("demo", "s3cretpw")]


def test_find_credentials_users_with_plain_text_passwd():
    doc = (
        "#cloud-config\nusers:\n  - name: alice\n    plain_text_passwd: 'hunter2'\n"
        "    groups: sudo\n"
    )
    assert find_credentials(doc) == [("alice", "hunter2")]


def test_find_credentials_chpasswd_users_style():
    doc = (
        "#cloud-config\nchpasswd:\n  users:\n    - name: bob\n      password: pw123\n"
    )
    assert find_credentials(doc) == [("bob", "pw123")]


def test_find_credentials_finds_nothing_in_key_only_configs():
    doc = (
        "#cloud-config\nlocale: en_US\nssh_authorized_keys:\n"
        "  - ssh-ed25519 AAAAfictional\nruncmd:\n  - echo ok\n"
    )
    assert find_credentials(doc) == []


# -- the modal flows -----------------------------------------------------------

_USERDATA = "#cloud-config\nchpasswd:\n  list: |\n    demo:s3cretpw\n"


def _mock_vm_screen() -> None:
    mock_get("vm/info/", {"total_memory": 2048, "used_memory": 512,
                          "total_cpus": 2, "used_cpus": 1})
    mock_get(
        "vm/",
        [{"id": 1, "name": "vm-one", "status": "running", "os": "debian",
          "vcpus": 1, "memory": 512, "disk_type": "qcow2",
          "mac": "02:00:00:00:00:01", "enable_screen": False,
          "enable_cloudinit": True, "cloudinit_hostname": "vm-one",
          "cloudinit_userdata": _USERDATA}],
    )


def _modal_text(app: FbxApp) -> str:
    return "\n".join(
        str(widget.content) for widget in app.screen.query(Static)
    )


@pytest.mark.anyio
@respx.mock
async def test_console_preflight_masks_credentials_until_reveal(monkeypatch):
    monkeypatch.setattr("fbx.tui.screens.vm.oslaunch.can_spawn_terminal", lambda: True)
    authorize()
    _mock_dashboard_box()
    _mock_vm_screen()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        await pilot.press("c")
        await _settle(pilot, lambda: isinstance(app.screen, ConsolePreflightModal))
        text = _modal_text(app)
        assert "Ctrl-]" in text
        assert "demo" in text
        assert "s3cretpw" not in text  # masked by default
        await pilot.press("r")
        await _settle(pilot, lambda: "s3cretpw" in _modal_text(app))
        await pilot.press("escape")
        await _settle(pilot, lambda: not isinstance(app.screen, ConsolePreflightModal))


@pytest.mark.anyio
@respx.mock
async def test_console_attach_choice_runs_the_pump(monkeypatch):
    monkeypatch.setattr("fbx.tui.screens.vm.oslaunch.can_spawn_terminal", lambda: True)
    authorize()
    _mock_dashboard_box()
    _mock_vm_screen()
    app = FbxApp(splash=False)

    suspended = []
    pumped = []

    @contextlib.contextmanager
    def fake_suspend():
        suspended.append(True)
        yield

    async with app.run_test(size=(120, 40)) as pilot:
        monkeypatch.setattr(app, "suspend", fake_suspend)
        real_call = app.runtime.call

        def spy_call(fn, *args, **kwargs):
            from fbx.core import vmconsole

            if fn is vmconsole.console_runner:
                pumped.append(args)
                return None
            return real_call(fn, *args, **kwargs)

        monkeypatch.setattr(app.runtime, "call", spy_call)
        await _open(pilot, app, "vm", "vms")
        await pilot.press("c")
        await _settle(pilot, lambda: isinstance(app.screen, ConsolePreflightModal))
        await pilot.press("a")
        await _settle(pilot, lambda: bool(pumped))
        assert suspended and pumped == [(1,)]


@pytest.mark.anyio
@respx.mock
async def test_console_terminal_choice_spawns_a_window(monkeypatch):
    monkeypatch.setattr("fbx.tui.screens.vm.oslaunch.can_spawn_terminal", lambda: True)
    spawned = []
    monkeypatch.setattr(
        "fbx.tui.screens.vm.oslaunch.spawn_terminal",
        lambda argv: spawned.append(argv) or True,
    )
    authorize()
    _mock_dashboard_box()
    _mock_vm_screen()
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        await pilot.press("c")
        await _settle(pilot, lambda: isinstance(app.screen, ConsolePreflightModal))
        await pilot.press("t")
        await _settle(pilot, lambda: bool(spawned))
        assert spawned == [["fbx", "vm", "console", "1"]]
        # No suspend happened: the app is still live under the toast.
        assert not isinstance(app.screen, ConsolePreflightModal)


@pytest.mark.anyio
@respx.mock
async def test_console_still_requires_a_running_vm():
    authorize()
    _mock_dashboard_box()
    mock_get("vm/info/", {"total_memory": 2048, "used_memory": 0,
                          "total_cpus": 2, "used_cpus": 0})
    mock_get("vm/", [{"id": 1, "name": "vm-one", "status": "stopped"}])
    app = FbxApp(splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "vm", "vms")
        await pilot.press("c")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, ConsolePreflightModal)


def test_applescript_quoting_survives_quotes_and_backslashes():
    from fbx.tui.oslaunch import _applescript_quote

    assert _applescript_quote('echo "a\\b"') == '"echo \\"a\\\\b\\""'
