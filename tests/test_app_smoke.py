"""Run the real main loop with a fake camera, fake tracker and fake OS actions."""

import os

import numpy as np
import pytest

from handgen import make_hand
from mosign import app
from mosign.actions import RecordingActions


class FakeCapture:
    def __init__(self, index, *args, frames=40):
        self.index = index
        self.left = frames

    def isOpened(self):
        return True

    def read(self):
        if self.left <= 0:
            return False, None
        self.left -= 1
        return True, np.full((360, 640, 3), 120, np.uint8)

    def release(self):
        pass

    def set(self, *a):
        return True


class FakeTracker:
    """Pretends the user holds the same hand pose every frame."""

    hand = None

    def __init__(self, *a, **k):
        self.backend = "fake"

    def process(self, frame):
        if FakeTracker.hand is None:
            return None
        h, w = frame.shape[:2]
        aspect = w / h
        return [(x / aspect, y) for x, y in FakeTracker.hand]

    def close(self):
        pass


@pytest.fixture
def fakes(monkeypatch):
    recorder = RecordingActions()
    monkeypatch.setattr(app.cv2, "VideoCapture", FakeCapture)
    # no real window in CI; run with xvfb-run to exercise the real one
    if not os.environ.get("DISPLAY"):
        for name, fn in {
            "imshow": lambda *a: None,
            "waitKey": lambda *a: -1,
            "namedWindow": lambda *a: None,
            "resizeWindow": lambda *a: None,
            "setMouseCallback": lambda *a: None,
            "getWindowProperty": lambda *a: 1.0,
            "destroyAllWindows": lambda *a: None,
        }.items():
            monkeypatch.setattr(app.cv2, name, fn)
    monkeypatch.setattr(app, "HandTracker", FakeTracker)
    monkeypatch.setattr(app, "PyAutoGuiActions", lambda: recorder)
    return recorder


def test_main_loop_runs_and_scrolls(fakes):
    FakeTracker.hand = make_hand({"index"})  # index pointing up = scroll up
    assert app.main(["--camera", "0"]) == 0
    assert any(c[0] == "scroll" and c[1] > 0 for c in fakes.calls)


def test_point_right_switches_tab(fakes):
    FakeTracker.hand = make_hand({"index"}, rotation=-90)
    app.main([])
    assert fakes.calls.count(("next_tab",)) == 1
