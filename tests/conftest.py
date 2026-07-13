from __future__ import annotations

import pytest

from fbx.core import credentials


@pytest.fixture(autouse=True)
def _isolate_credentials(tmp_path, monkeypatch):
    """Never let a test read or write the user's real credential store."""
    monkeypatch.setattr(credentials, "config_dir", lambda: tmp_path)
