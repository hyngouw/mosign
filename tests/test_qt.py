"""The real Qt windows, run on Qt's 'offscreen' platform (no display needed)."""

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QKeyEvent  # noqa: E402

from handgen import make_hand  # noqa: E402
from mosign import app, engine as engine_mod, qt_app  # noqa: E402
from mosign.actions import RecordingActions  # noqa: E402
from mosign.config import Config  # noqa: E402
from test_app_smoke import FakeCapture, FakeTracker  # noqa: E402


@pytest.fixture
def qt_fakes(monkeypatch):
    Config(onboarding_complete=True).save()
    FakeCapture.working = {0, 1}
    monkeypatch.setattr("mosign.camera.cv2.VideoCapture", FakeCapture)
    recorder = RecordingActions()
    monkeypatch.setattr(engine_mod, "PyAutoGuiActions", lambda: recorder)
    tracker = FakeTracker(make_hand({"index"}))
    monkeypatch.setattr(app, "HandTracker", lambda *a, **k: tracker)

    seen = []
    real_set_image = qt_app.OverlayWindow.set_image

    def spy(self, qimage, dpr):
        real_set_image(self, qimage, dpr)
        seen.append((self.geometry(), self.windowFlags(), self.isVisible()))

    monkeypatch.setattr(qt_app.OverlayWindow, "set_image", spy)
    recorder.overlay_seen = seen
    return recorder


def test_app_runs_with_windows_and_corner_overlay(qt_fakes):
    assert app.main(["--max-frames", "12"]) == 0
    assert any(c[0] == "scroll" for c in qt_fakes.calls)

    geo, flags, visible = qt_fakes.overlay_seen[-1]
    assert visible
    for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint,
                 Qt.WindowType.WindowTransparentForInput,
                 Qt.WindowType.WindowDoesNotAcceptFocus):
        assert flags & flag, flag
    screen = QGuiApplication.primaryScreen().availableGeometry()
    assert screen.contains(geo)
    assert screen.right() - geo.right() < 40      # hugging the right edge
    assert geo.top() - screen.top() < 40          # and the top


def test_overlay_moves_to_stay_in_corner_when_menu_hides(qt_fakes, monkeypatch):
    tracker = FakeTracker(make_hand({"pinky"}))   # hold pinky -> menu hides
    monkeypatch.setattr(app, "HandTracker", lambda *a, **k: tracker)
    app.main(["--max-frames", "60"])
    heights = [g.height() for g, _, _ in qt_fakes.overlay_seen]
    assert heights[-1] < heights[0]
    last = qt_fakes.overlay_seen[-1][0]
    screen = QGuiApplication.primaryScreen().availableGeometry()
    assert screen.right() - last.right() < 40 and last.top() - screen.top() < 40
    assert Config.load().menu_visible is False


def test_tracker_failure_shows_message_window(qt_fakes, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no model")

    monkeypatch.setattr(app, "HandTracker", broken)
    assert app.main(["--max-frames", "3"]) == 1


def test_keys_and_clicks_become_commands():
    qt_app.get_app()
    win = qt_app.CanvasWindow()
    win.resize(win.canvas_size[0] // 2, win.canvas_size[1] // 2)  # shrunk to half
    for key, text, cmd in [(Qt.Key.Key_C, "c", "swap_camera"), (Qt.Key.Key_M, "M", "toggle_menu"),
                           (Qt.Key.Key_Q, "q", "quit")]:
        win.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier,
                                    text))
        assert win.commands[-1] == cmd
    x, y = win.to_canvas(QPointF(win.width() / 2, win.height() / 2))
    assert abs(x - win.canvas_size[0] / 2) < 3 and abs(y - win.canvas_size[1] / 2) < 3
    win.close()
    assert win.closed and win.commands[-1] == "quit"


def test_premultiplied_overlay_pixels_survive_conversion():
    qt_app.get_app()
    img = np.zeros((2, 2, 4), np.uint8)
    img[0, 0] = (0, 0, 128, 128)      # half-transparent pure red (premultiplied)
    img[1, 1] = (255, 0, 0, 255)      # solid blue
    q = qt_app.bgra_to_qimage(img)
    red = q.pixelColor(0, 0)
    assert (red.red(), red.green(), red.blue()) == (255, 0, 0) and abs(red.alpha() - 128) <= 1
    assert q.pixelColor(1, 1).blue() == 255 and q.pixelColor(1, 1).alpha() == 255
    assert q.pixelColor(1, 0).alpha() == 0


def test_hide_dock_icon_flag_is_remembered_and_passed_on(qt_fakes, monkeypatch):
    seen = {}
    real_run = qt_app.run

    def spy(make_engine, **kw):
        seen.update(kw)
        return real_run(make_engine, **kw)

    monkeypatch.setattr(qt_app, "run", spy)
    app.main(["--max-frames", "2", "--hide-dock-icon"])
    assert seen["hide_dock_icon"] is True and Config.load().hide_dock_icon
    app.main(["--max-frames", "2"])
    assert seen["hide_dock_icon"] is True            # remembered
    app.main(["--max-frames", "2", "--show-dock-icon"])
    assert seen["hide_dock_icon"] is False and not Config.load().hide_dock_icon


def test_mac_window_tweaks_skipped_without_a_real_mac_window(qt_fakes, monkeypatch):
    calls = []
    monkeypatch.setattr(qt_app.macos, "configure_overlay", lambda *a, **k: calls.append(1))
    app.main(["--max-frames", "3"])
    assert QGuiApplication.platformName() == "offscreen" and calls == []


def test_window_asks_for_a_sharp_picture_size():
    qt_app.get_app()
    win = qt_app.CanvasWindow()
    assert 2.0 <= win.pixel_scale() <= 2.5
    win.resize(win.canvas_size[0] * 2, win.canvas_size[1] * 2)    # a big window: capped
    assert win.pixel_scale() == 2.5
    win.close()
