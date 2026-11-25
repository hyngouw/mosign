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
    assert engine.cat_face.asleep


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
    assert engine.overlay._flash[0] == "Menu hidden"   # status pill says so
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


ONBOARDING_KEYS = {1: ["flow_next"], 2: ["flow_next"]}


def tutorial_script():
    def pose(fingers, rot, n):
        return [make_hand(fingers, rot)] * n

    rest = [None] * 40          # lower the hand between steps
    hold = 40                   # a bit over the 0.8 second hold every step needs
    return (
        [None] * 6
        + pose({"index"}, 0, hold) + rest              # point up
        + pose({"index"}, 180, hold) + rest            # point down
        + pose({"index"}, 90, hold) + rest             # point left
        + pose({"index"}, -90, hold) + rest            # point right
        + pose({"index", "pinky"}, 0, hold) + rest     # rock horns
        + pose({"pinky"}, 0, hold) + rest              # pinky
    )


def test_completing_the_tutorial_turns_gestures_on(make):
    script = tutorial_script()
    tour_frames = len(script)
    script += [make_hand({"index"}, -90)] * 15       # a real gesture afterwards
    engine, rec = make(script=script, first_run=True)
    engine.sound.enabled = True
    played = []
    engine.sound.play = lambda: played.append(1)
    run(engine, len(script) + 60, ONBOARDING_KEYS)

    assert Config.load().onboarding_complete
    assert Config.load().menu_visible and engine.controller.awake   # put back after the tutorial
    assert rec.calls == [("next_tab",)], f"tutorial took {tour_frames} frames"
    assert len(played) == 6                          # one chime per gesture, from the real hand
    assert engine.flow.stage == "ready"              # the "You're ready!" screen
    run(engine, 2, {0: ["flow_next"]}, t0=100)
    assert engine.flow is not None                     # fading out first...
    run(engine, 30, t0=101)
    assert engine.flow is None                         # ...then straight to the window


def test_onboarding_screens_hide_the_overlay_and_ignore_gestures(make):
    engine, rec = make(make_hand({"index"}), first_run=True)
    out = run(engine, 30)
    assert engine.flow.stage == "welcome" and not out.show_overlay
    assert rec.calls == []
    run(engine, 4, {0: ["flow_next"], 1: ["flow_next"]}, t0=1)
    assert engine.flow.stage == "tutorial"


def test_welcome_back_shows_then_hands_over_to_the_window(make):
    Config(onboarding_complete=True, user_name="Alex").save()
    engine = Engine(Config.load(), tracker=FakeTracker(), actions=RecordingActions(),
                    welcome_back=True)
    out = run(engine, 5)
    assert engine.flow.stage == "back" and out.show_overlay
    out = run(engine, 5, t0=10)
    assert engine.flow is None and out.show_overlay


def test_close_on_first_screens_quits(make):
    engine, _ = make(first_run=True)
    out = run(engine, 3, {0: ["flow_close"]})
    assert out.quit


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


class FakeTabs:
    """Pretends to be the browser: 4 tabs in a row; switches when told."""

    def __init__(self, active=1, lag=0):
        from mosign.tabs import TabInfo
        self.info = TabInfo([(100 + i * 200, 30, 190, 34) for i in range(4)], active, stamp=0)
        self.available = True
        self.pokes = 0

    def clock(self):
        return 0

    def latest(self):
        return self.info

    def poke(self):
        self.pokes += 1

    def start(self):
        return self

    def stop(self):
        pass


def settle(engine, frames, t0, hand=None):
    if hand is not None:
        engine.tracker.hand = hand
    return run(engine, frames, t0=t0)


def test_cat_sits_on_the_active_tab(make):
    engine, _ = make()
    engine.tabs = FakeTabs(active=2)
    engine.set_home(1300, 100)
    out = settle(engine, 60, 0)
    assert out.cat_feet == pytest.approx(Engine.perch((500, 30, 190, 34)))
    assert out.cat.shape[2] == 4 and out.cat[..., 3].max() == 255


def test_cat_jumps_to_the_next_tab_right_away(make):
    engine, _ = make()
    tabs = FakeTabs(active=1)
    engine.tabs = tabs
    settle(engine, 60, 0)
    start = engine.cat_motion.x
    # point right: the browser hasn't reported the new tab yet (lag)
    out = settle(engine, 25, 2.0, hand=make_hand({"index"}, rotation=-90))
    assert tabs.pokes >= 1
    assert out.cat_feet[0] == pytest.approx(Engine.perch((500, 30, 190, 34))[0])
    assert out.cat_feet[0] > start
    tabs.info.active = 2            # browser catches up: cat stays put
    out = settle(engine, 60, 3.0, hand=None)
    assert out.cat_feet[0] == pytest.approx(Engine.perch((500, 30, 190, 34))[0])


def test_cat_returns_if_the_browser_never_switches(make):
    """If the switch didn't happen (e.g. the browser ignored the key), the cat
    goes back to the tab the browser says is active."""
    engine, _ = make()
    engine.tabs = FakeTabs(active=1)
    settle(engine, 30, 0)
    out = settle(engine, 90, 2.0, hand=make_hand({"index"}, rotation=-90))
    assert out.cat_feet[0] == pytest.approx(Engine.perch((300, 30, 190, 34))[0])


def test_cat_wraps_from_last_tab_to_first(make):
    engine, _ = make()
    engine.tabs = FakeTabs(active=3)
    settle(engine, 30, 0)
    out = settle(engine, 25, 2.0, hand=make_hand({"index"}, rotation=-90))
    assert out.cat_feet[0] == pytest.approx(Engine.perch((100, 30, 190, 34))[0])


def test_without_tabs_cat_stays_home_and_hops(make):
    engine, _ = make()
    engine.set_home(1300, 100)
    settle(engine, 5, 0)
    assert engine.cat_motion.target == (1300, 100)
    engine.tracker.hand = make_hand({"index"}, rotation=90)    # point left
    xs = []
    for i in range(40):
        out = engine.step(1 + i / 30)
        xs.append(out.cat_feet[0])
    assert min(xs) < 1300 - 5                 # hopped left...
    assert xs[-1] == pytest.approx(1300)      # ...and came back


def test_cat_sleeps_when_paused(make):
    engine, _ = make()
    run(engine, 10, {0: ["toggle_tracking"]})
    assert engine.cat_face.asleep and engine.cat_face.eyes == "closed"
    run(engine, 10, {0: ["toggle_tracking"]}, t0=2)
    assert not engine.cat_face.asleep


def test_cat_goes_home_when_tabs_disappear(make):
    engine, _ = make()
    tabs = FakeTabs(active=0)
    engine.tabs = tabs
    engine.set_home(1300, 100)
    settle(engine, 60, 0)
    tabs.info = None                # e.g. switched to a non-browser app
    out = settle(engine, 90, 3)
    assert out.cat_feet == pytest.approx((1300, 100))


def test_last_hand_lands_in_its_slot_before_the_ready_screen(make):
    from mosign.onboarding import LAND_PAUSE, STEP_PAUSE
    script = tutorial_script()
    engine, _ = make(script=script, first_run=True)
    run(engine, 4, ONBOARDING_KEYS)
    t = 1.0
    while engine.tour is not None and not engine.tour.done:
        t += 1 / 30
        engine.step(t)
    done_at = engine.tour.finished_at
    t = done_at + STEP_PAUSE + LAND_PAUSE / 2          # landed, slot full, still on the tutorial
    engine.step(t)
    assert engine.flow.stage == "tutorial" and engine.tour.filled(t) == 6
    engine.step(done_at + STEP_PAUSE + LAND_PAUSE + 0.1)
    assert engine.flow.stage == "ready"
