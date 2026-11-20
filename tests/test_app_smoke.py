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

    script = None  # optional list of hands, one per frame

    def process(self, frame):
        if FakeTracker.script is not None:
            FakeTracker.hand = FakeTracker.script.pop(0) if FakeTracker.script else None
        if FakeTracker.hand is None:
            return None
        h, w = frame.shape[:2]
        aspect = w / h
        return [(x / aspect, y) for x, y in FakeTracker.hand]

    def close(self):
        pass


@pytest.fixture
def fakes(monkeypatch):
    Config(onboarding_complete=True).save()  # most tests skip the tour
    recorder = RecordingActions()
    FakeCapture.opened = []
    FakeTracker.hand = None
    FakeTracker.script = None
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


def test_m_key_toggles_menu_and_remembers_it(fakes):
    fakes.keys.extend([ord("m")])
    app.main(["--max-frames", "5"])
    assert Config.load().menu_visible is False
    fakes.keys.extend([ord("m")])
    app.main(["--max-frames", "5"])
    assert Config.load().menu_visible is True


def first_run():
    Config(onboarding_complete=False).save()


def test_first_run_is_practice_mode(fakes):
    first_run()
    FakeTracker.hand = make_hand({"index"})
    app.main(["--max-frames", "60"])
    assert fakes.calls == []           # nothing reached the browser
    assert not Config.load().onboarding_complete


def test_skip_tour_flag(fakes):
    first_run()
    FakeTracker.hand = make_hand({"index"})
    app.main(["--max-frames", "30", "--skip-tour"])
    assert any(c[0] == "scroll" for c in fakes.calls)
    assert Config.load().onboarding_complete


def test_completing_the_tour_turns_gestures_on(fakes, monkeypatch):
    first_run()
    clock = iter(i / 30 for i in range(100_000))
    monkeypatch.setattr(app.time, "time", lambda: next(clock))

    def pose(fingers, rot, n):
        return [make_hand(fingers, rot)] * n

    rest = [None] * 40          # lower the hand between steps
    script = (
        pose({"thumb", "index", "middle", "ring", "pinky"}, 0, 40) + rest
        + pose({"index"}, 0, 50) + rest              # point up
        + pose({"index"}, 180, 50) + rest            # point down
        + pose({"index"}, 90, 15) + rest             # point left
        + pose({"index"}, -90, 15) + rest            # point right
        + pose({"pinky"}, 0, 45) + rest              # hide menu
        + pose({"pinky"}, 0, 45) + rest              # show menu
        + pose({"index", "pinky"}, 0, 45) + rest     # pause
        + pose({"index", "pinky"}, 0, 45) + rest     # resume
    )
    tour_frames = len(script)
    script += pose({"index"}, -90, 15)               # a real gesture afterwards
    FakeTracker.script = script
    app.main(["--max-frames", str(len(script) + 5)])

    assert Config.load().onboarding_complete
    assert Config.load().menu_visible  # ended up shown again
    assert fakes.calls == [("next_tab",)], f"tour took {tour_frames} frames"


def test_tour_can_be_replayed_and_ended(fakes):
    FakeTracker.hand = make_hand({"index"})
    fakes.keys.extend([ord("o")] + [-1] * 10 + [ord("o")])
    app.main(["--max-frames", "40"])
    scrolls = [c for c in fakes.calls if c[0] == "scroll"]
    # live at frame 1, practice for ~11 frames, then live again
    assert 0 < len(scrolls) < 38


def test_first_run_tour_cannot_be_ended_with_o(fakes):
    first_run()
    FakeTracker.hand = make_hand({"index"})
    fakes.keys.extend([ord("o")])
    app.main(["--max-frames", "30"])
    assert fakes.calls == []
