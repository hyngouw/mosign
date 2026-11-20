import ast
import importlib.util
from pathlib import Path

from PIL import Image

from mosign import app

ROOT = Path(__file__).resolve().parent.parent


def test_spec_and_launcher_are_valid_python():
    ast.parse((ROOT / "mosign.spec").read_text())
    ast.parse((ROOT / "run_mosign.py").read_text())


def test_spec_asks_for_camera_permission_and_bundles_model():
    spec = (ROOT / "mosign.spec").read_text()
    assert "NSCameraUsageDescription" in spec
    assert '"models"' in spec and "hand_landmarker.task" in spec
    assert "console=False" in spec


def test_build_scripts_run_tests_and_self_test():
    for name in ("build_mac.sh", "build_windows.ps1"):
        script = (ROOT / "scripts" / name).read_text()
        assert "pytest" in script and "--self-test" in script and "hand_landmarker.task" in script


def test_icon_is_generated(tmp_path):
    spec = importlib.util.spec_from_file_location("make_icon", ROOT / "scripts" / "make_icon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    png, ico = mod.main(tmp_path)
    img = Image.open(png)
    assert img.size == (1024, 1024) and img.mode == "RGBA"
    assert img.getpixel((5, 5))[3] == 0          # transparent corner
    assert img.getpixel((512, 512))[3] == 255    # solid middle
    assert ico.stat().st_size > 1000


class OkTracker:
    backend = "fake"

    def __init__(self, *a, **k):
        pass

    def close(self):
        pass


def test_self_test_passes_when_everything_loads(monkeypatch, capsys):
    monkeypatch.setattr(app, "HandTracker", OkTracker)
    assert app.main(["--self-test"]) == 0
    assert "PASSED" in capsys.readouterr().out


def test_self_test_fails_loudly(monkeypatch, capsys):
    def broken(*a, **k):
        raise RuntimeError("model missing")

    monkeypatch.setattr(app, "HandTracker", broken)
    assert app.main(["--self-test"]) == 1
    out = capsys.readouterr().out
    assert "FAIL hand tracker: model missing" in out and "FAILED" in out
