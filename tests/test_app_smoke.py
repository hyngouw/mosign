"""Run the real main loop with a fake camera, fake tracker and fake OS actions."""

import os

import numpy as np
import pytest

from handgen import make_hand
from mosign import app
from mosign.actions import RecordingActions
from mosign.config import Config


class FakeCapture:
    working = {0, 1}   # camera indexes that "exist"
    opened = []

    def __init__(self, index, *args):
        self.index = index
        FakeCapture.opened.append(index)

    def isOpened(self):
        return self.index in FakeCapture.working

    def read(self):
        if self.index not in FakeCapture.working:
            return False, None
        return True, np.full((360, 640, 3), 120 + self.index * 40, np.uint8)

    def release(self):
        pass


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
    FakeCapture.opened = []
    FakeTracker.hand = None
    monkeypatch.setattr("mosign.camera.cv2.VideoCapture", FakeCapture)
    monkeypatch.setattr(app, "HandTracker", FakeTracker)
    monkeypatch.setattr(app, "PyAutoGuiActions", lambda: recorder)
    keys = []
    # no real window in CI; run with xvfb-run to exercise the real one
    if not os.environ.get("DISPLAY"):
        for name, fn in {
            "imshow": lambda *a: None,
            "namedWindow": lambda *a: None,
            "resizeWindow": lambda *a: None,
            "setMouseCallback": lambda *a: None,
            "getWindowProperty": lambda *a: 1.0,
            "destroyAllWindows": lambda *a: None,
        }.items():
            monkeypatch.setattr(app.cv2, name, fn)
    real_wait = app.cv2.waitKey

    def wait_key(delay):
        if os.environ.get("DISPLAY"):
            real_wait(delay)
        return keys.pop(0) if keys else -1

    monkeypatch.setattr(app.cv2, "waitKey", wait_key)
    recorder.keys = keys
    return recorder


def test_main_loop_runs_and_scrolls(fakes):
    FakeTracker.hand = make_hand({"index"})  # index pointing up = scroll up
    assert app.main(["--max-frames", "30"]) == 0
    assert any(c[0] == "scroll" and c[1] > 0 for c in fakes.calls)


def test_point_right_switches_tab(fakes):
    FakeTracker.hand = make_hand({"index"}, rotation=-90)
    app.main(["--max-frames", "30"])
    assert fakes.calls.count(("next_tab",)) == 1


def test_s_key_pauses_tracking(fakes):
    FakeTracker.hand = make_hand({"index"})
    fakes.keys.extend([ord("s")])
    app.main(["--max-frames", "30"])
    assert len(fakes.calls) <= 1  # paused on the first frame


def test_c_key_swaps_camera_and_remembers_it(fakes):
    fakes.keys.extend([-1, ord("c")])
    app.main(["--max-frames", "10", "--camera", "0"])
    assert 1 in FakeCapture.opened
    assert Config.load().camera_index == 1


def test_q_key_quits(fakes):
    fakes.keys.extend([ord("q")])
    assert app.main(["--max-frames", "1000"]) == 0


def test_missing_camera_does_not_crash(fakes):
    FakeCapture.working = set()
    try:
        assert app.main(["--max-frames", "5"]) == 0
    finally:
        FakeCapture.working = {0, 1}


def test_tracker_failure_shows_message_instead_of_crashing(fakes, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no model")

    monkeypatch.setattr(app, "HandTracker", broken)
    assert app.main(["--max-frames", "3"]) == 1
