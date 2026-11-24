"""Drive the real Engine with a fake camera, fake hands and fake OS actions."""

import numpy as np
import pytest

from handgen import make_hand
from mosign.actions import RecordingActions
from mosign.config import Config
from mosign.engine import Engine


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
    """Pretends the user holds the same hand pose every frame (or follows a script)."""

    def __init__(self, hand=None, script=None):
        self.hand = hand
        self.script = script
        self.backend = "fake"
        self.closed = False

    def process(self, frame):
        if self.script is not None:
            self.hand = self.script.pop(0) if self.script else None
        if self.hand is None:
            return None
        h, w = frame.shape[:2]
        aspect = w / h
        return [(x / aspect, y) for x, y in self.hand]

    def close(self):
        self.closed = True


@pytest.fixture
def make(monkeypatch):
    """make(hand=..., script=..., tour=..., first_run=...) -> (engine, recorder)."""
    FakeCapture.opened = []
    FakeCapture.working = {0, 1}
    monkeypatch.setattr("mosign.camera.cv2.VideoCapture", FakeCapture)

    def _make(hand=None, script=None, tour=False, first_run=False):
        Config(onboarding_complete=not first_run).save()
        recorder = RecordingActions()
        engine = Engine(Config.load(), start_tour=tour,
                        tracker=FakeTracker(hand, script), actions=recorder)
        return engine, recorder

    return _make


def run(engine, frames, keys=None, t0=0.0, dt=1 / 30):
    """Step the engine; keys maps frame number -> list of commands."""
    out = None
    for i in range(frames):
        out = engine.step(t0 + i * dt, (keys or {}).get(i, []))
        if out.quit:
            break
    return out


def test_scrolls_when_pointing_up(make):
    engine, rec = make(make_hand({"index"}))
    run(engine, 30)
    assert any(c[0] == "scroll" and c[1] > 0 for c in rec.calls)


def test_point_right_switches_tab(make):
    engine, rec = make(make_hand({"index"}, rotation=-90))
    run(engine, 30)
    assert rec.calls.count(("next_tab",)) == 1


def test_outputs_main_image_and_transparent_overlay(make):
    engine, _ = make(make_hand({"index"}))
    out = run(engine, 3)
    assert out.main.ndim == 3 and out.main.shape[2] == 3
    assert out.overlay.shape[2] == 4
    alpha = out.overlay[..., 3]
    assert alpha.min() == 0 and alpha.max() == 255   # see-through and solid parts
    assert np.all(out.overlay[..., :3] <= alpha[..., None])   # valid premultiplied


def test_s_pauses_tracking(make):
    engine, rec = make(make_hand({"index"}))
    run(engine, 30, {0: ["toggle_tracking"]})
    assert rec.calls == []
    assert engine.overlay.penguin.asleep


def test_c_swaps_camera_and_remembers_it(make):
    engine, _ = make()
    run(engine, 5, {1: ["swap_camera"]})
    assert 1 in FakeCapture.opened
    assert Config.load().camera_index == 1


def test_quit_command(make):
    engine, _ = make()
    out = run(engine, 100, {3: ["quit"]})
    assert out.quit


def test_missing_camera_does_not_crash(make):
    FakeCapture.working = set()
    engine, _ = make()
    out = run(engine, 5)
    assert out.main is not None


def test_m_hides_overlay_menu_and_remembers_it(make):
    engine, _ = make()
    shown = run(engine, 2).overlay
    hidden = run(engine, 2, {0: ["toggle_menu"]}, t0=1).overlay
    assert hidden.shape[0] < shown.shape[0]     # overlay shrinks to just Pip
    assert Config.load().menu_visible is False
    assert engine.overlay.penguin.waving        # Pip reacts to the key too
    run(engine, 2, {0: ["toggle_menu"]}, t0=2)
    assert Config.load().menu_visible is True


def test_pinky_hold_hides_overlay_menu(make):
    engine, _ = make(make_hand({"pinky"}))
    out = run(engine, 50)
    assert not out.menu_visible


def test_close_releases_tracker(make):
    engine, _ = make()
    engine.close()
    assert engine.tracker.closed


def test_first_run_is_practice_mode(make):
    engine, rec = make(make_hand({"index"}), first_run=True)
    run(engine, 60)
    assert rec.calls == []           # nothing reached the browser
    assert not Config.load().onboarding_complete


def test_completing_the_tour_turns_gestures_on(make):
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
    engine, rec = make(script=script, first_run=True)
    run(engine, len(script) + 5)

    assert Config.load().onboarding_complete
    assert Config.load().menu_visible  # ended up shown again
    assert rec.calls == [("next_tab",)], f"tour took {tour_frames} frames"


def test_tour_can_be_replayed_and_ended(make):
    engine, rec = make(make_hand({"index"}))
    run(engine, 40, {0: ["tour"], 11: ["tour"]})
    scrolls = [c for c in rec.calls if c[0] == "scroll"]
    # practice for ~11 frames, then live again
    assert 0 < len(scrolls) < 38


def test_first_run_tour_cannot_be_ended(make):
    engine, rec = make(make_hand({"index"}), first_run=True)
    run(engine, 30, {0: ["tour"]})
    assert rec.calls == []


def test_tour_forces_overlay_menu_on(make):
    engine, _ = make()
    engine.controller.toggle_menu()
    out = run(engine, 2, {0: ["tour"]})
    assert out.menu_visible
