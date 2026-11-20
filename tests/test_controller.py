import pytest

from mosign.actions import RecordingActions
from mosign.controller import Controller


def feed(ctrl, label, n, t0=0.0, dt=0.033):
    t = t0
    for _ in range(n):
        ctrl.update(label, t)
        t += dt
    return t


def scrolls(acts):
    return [c[1] for c in acts.calls if c[0] == "scroll"]


def test_scrolls_only_while_pointing():
    acts = RecordingActions()
    c = Controller(acts, scroll_amount=2, stable_frames=3)
    t = feed(c, "scroll_up", 10)
    assert c.scroll_mode == "up"
    assert scrolls(acts) == [2] * 8  # starts once the pose is steady (frame 3)
    t = feed(c, None, 3, t)          # finger lowered -> stops
    assert c.scroll_mode is None
    n = len(scrolls(acts))
    feed(c, None, 10, t)
    assert len(scrolls(acts)) == n


def test_point_down_scrolls_down():
    acts = RecordingActions()
    c = Controller(acts, scroll_amount=3, stable_frames=2)
    feed(c, "scroll_down", 5)
    assert set(scrolls(acts)) == {-3}
    assert c.scroll_mode == "down"


def test_scroll_start_event_fires_once():
    c = Controller(RecordingActions(), stable_frames=2)
    seen = []
    for i in range(6):
        c.update("scroll_up", i * 0.03)
        seen += c.events
    assert seen == ["scroll_up"]


def test_tab_fires_once_and_respects_cooldown():
    acts = RecordingActions()
    c = Controller(acts, stable_frames=3, tab_cooldown=1.0)
    t = feed(c, "next_tab", 10)
    assert acts.calls.count(("next_tab",)) == 1
    t = feed(c, None, 3, t)
    feed(c, "next_tab", 3, t)  # still within the 1s cooldown
    assert acts.calls.count(("next_tab",)) == 1
    feed(c, None, 3, 5.0)
    feed(c, "prev_tab", 3, 6.0)
    assert ("prev_tab",) in acts.calls
    assert not scrolls(acts)


def test_reset_stops_scrolling():
    c = Controller(RecordingActions(), stable_frames=1)
    c.update("scroll_up", 0)
    c.reset()
    assert c.scroll_mode is None and c.last_gesture is None


def hold(ctrl, label, seconds, t0, dt=0.033):
    return feed(ctrl, label, int(seconds / dt) + 1, t0, dt)


def test_wake_gesture_toggles_tracking():
    acts = RecordingActions()
    c = Controller(acts, stable_frames=3, hold_seconds=1.0)
    assert c.awake
    t = hold(c, "toggle_tracking", 0.5, 0)  # too short
    assert c.awake
    t = feed(c, None, 5, t)
    events = []
    for _ in range(60):  # ~2s hold: toggles exactly once
        c.update("toggle_tracking", t)
        events += c.events
        t += 0.033
    assert not c.awake and events == ["sleep"]

    # asleep: pointing does nothing
    t = feed(c, None, 5, t)
    t = feed(c, "scroll_up", 20, t)
    t = feed(c, "next_tab", 20, t)
    assert acts.calls == [] and c.scroll_mode is None

    # hold again: wakes up, and gestures work again
    t = feed(c, None, 5, t)
    t = hold(c, "toggle_tracking", 1.2, t)
    assert c.awake
    t = feed(c, None, 5, t)
    feed(c, "scroll_up", 5, t)
    assert ("scroll", 1) in acts.calls


def test_sleep_stops_scrolling_immediately():
    acts = RecordingActions()
    c = Controller(acts, stable_frames=1)
    c.update("scroll_up", 0)
    c.toggle_awake()
    n = len(acts.calls)
    c.update("scroll_up", 0.1)
    assert len(acts.calls) == n and c.scroll_mode is None


def test_holding_reports_progress():
    c = Controller(RecordingActions(), stable_frames=1, hold_seconds=1.0)
    c.update("toggle_tracking", 0.0)
    c.update("toggle_tracking", 0.25)
    label, progress = c.holding
    assert label == "toggle_tracking" and progress == pytest.approx(0.25)
    c.update(None, 0.3)
    assert c.holding is None
