import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real ~/.mosign during tests."""
    monkeypatch.setenv("MOSIGN_HOME", str(tmp_path / "mosign_home"))
    monkeypatch.setenv("MOSIGN_MUTE", "1")     # no chimes while testing
    yield tmp_path / "mosign_home"



# Qt windows open off-screen in tests (works on macOS, Windows and Linux CI)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
