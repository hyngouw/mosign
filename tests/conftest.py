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
    yield tmp_path / "mosign_home"

