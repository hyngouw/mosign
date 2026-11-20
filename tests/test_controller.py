from mosign.actions import RecordingActions
from mosign.controller import Controller


def feed(ctrl, label, n, t0=0.0, dt=0.033):
    t = t0
    for _ in range(n):
        ctrl.update(label, t)
        t += dt
    return t


def test_scroll_keeps_going_until_stop():
    acts = RecordingActions()
    c = Controller(acts, scroll_amount=2, stable_frames=3)
    t = feed(c, "scroll_up", 3)
    assert c.scroll_mode == "up"
    t = feed(c, None, 5, t)  # hand gone: still scrolling (old behaviour)
    assert c.scroll_mode == "up"
    feed(c, "stop", 3, t)
    assert c.scroll_mode is None
    assert ("scroll", 2) in acts.calls


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
