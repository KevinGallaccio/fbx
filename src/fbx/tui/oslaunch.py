"""Open an OS terminal window running a command (macOS only for now).

The app's only process-spawning code: the VM console pre-flight offers a
window of its own instead of suspending the TUI. Warp has no scripting
interface, so its documented launch-configuration file + `warp://launch/`
URI does the job; everything else goes through Terminal.app AppleScript.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

_WARP_CONFIG = """\
---
name: fbx-console
windows:
  - tabs:
      - title: fbx-console
        layout:
          commands:
            - exec: {command}
"""


def can_spawn_terminal() -> bool:
    return sys.platform == "darwin"


def spawn_terminal(argv: list[str]) -> bool:
    """Run `argv` in a new terminal window; True if one was opened.

    In Warp ($TERM_PROGRAM), a new Warp window; otherwise Terminal.app.
    """
    if not can_spawn_terminal():
        return False
    command = shlex.join(argv)
    if os.environ.get("TERM_PROGRAM") == "WarpTerminal" and _spawn_warp(command):
        return True
    return _spawn_terminal_app(command)


def _spawn_warp(command: str) -> bool:
    """One stable launch-config file, overwritten per launch, then the URI."""
    try:
        config_dir = Path.home() / ".warp" / "launch_configurations"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = config_dir / "fbx-console.yaml"
        config.write_text(_WARP_CONFIG.format(command=command))
        done = subprocess.run(
            ["open", f"warp://launch/{config.name}"], capture_output=True, check=False
        )
    except OSError:
        return False
    return done.returncode == 0


def _applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _spawn_terminal_app(command: str) -> bool:
    script = f"tell application \"Terminal\" to do script {_applescript_quote(command)}"
    try:
        done = subprocess.run(
            ["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return done.returncode == 0
