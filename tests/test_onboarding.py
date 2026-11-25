import pytest

from mosign.gestures import NEXT_TAB, SCROLL_DOWN, SCROLL_UP, TOGGLE_MENU, TOGGLE_TRACKING
from mosign.onboarding import CELEBRATE_SECONDS, HOLD_SECONDS, STEP_PAUSE, STEPS, Onboarding, Step

DT = 1 / 30


class Clock:
    def __init__(self):
        self.t = 0.0

    def tick(self, tour, n=1, **kw):
        result = None
        for _ in range(n):
            self.t += DT
            r = tour.update(self.t, DT, **kw)
            result = r or result
        return result

    def wait_pause(self, tour):
        self.tick(tour, int(STEP_PAUSE / DT) + 2)


def test_every_control_is_covered():
    assert [s.icon for s in STEPS] == ["scroll_up", "scroll_down", "prev_tab", "next_tab",
                                       "toggle_tracking", "toggle_menu"]


def test_every_step_is_the_same_timed_hold():
    assert all(s.kind == "hold" and s.seconds == HOLD_SECONDS for s in STEPS)
    assert HOLD_SECONDS == 0.8      # the original scroll speed, now used by every step


def test_full_tutorial():
    tour, clock = Onboarding(), Clock()
    for step in tour.steps:
        assert tour.step == step
        clock.tick(tour, 3, gesture=step.icon)
        assert tour.step == step and 0 < tour.progress < 1    # not instant
        result = clock.tick(tour, int(HOLD_SECONDS / DT) + 2, gesture=step.icon)
        assert result in ("step", "done")
        if not tour.done:
            clock.wait_pause(tour)
    assert tour.done and tour.step is None
    assert tour.celebrating(clock.t)
    assert not tour.celebrating(clock.t + CELEBRATE_SECONDS + 0.1)


def test_a_quick_tap_does_not_pass_a_step():
    tour, clock = Onboarding(), Clock()
    clock.tick(tour, 6, gesture=SCROLL_UP)
    clock.tick(tour, 30, gesture=None)
    assert tour.step.key == "scroll_up" and tour.progress == 0


def test_the_wrong_gesture_never_counts():
    tour, clock = Onboarding(), Clock()
    clock.tick(tour, 200, gesture=SCROLL_DOWN)
    clock.tick(tour, 200, gesture=NEXT_TAB)
    clock.tick(tour, 200, gesture=TOGGLE_TRACKING)
    assert tour.step.key == "scroll_up" and tour.progress == 0


def test_bar_drains_when_you_let_go():
    tour, clock = Onboarding(), Clock()
    clock.tick(tour, 12, gesture=SCROLL_UP)
    p = tour.progress
    clock.tick(tour, 3, gesture=None)
    assert 0 < tour.progress < p


def test_input_ignored_during_nice_pause():
    tour, clock = Onboarding(), Clock()
    while clock.tick(tour, 1, gesture=SCROLL_UP) != "step":
        pass
    assert tour.between_steps(clock.t)
    clock.tick(tour, 5, gesture=SCROLL_DOWN)
    assert tour.progress == 0


def test_hand_step_still_works_for_custom_tours():
    tour, clock = Onboarding([Step("hand", "Show your hand", "x", kind="hand", seconds=0.6)]), Clock()
    assert clock.tick(tour, 40, hand_present=True) == "done"


def test_there_are_six_steps_with_names_for_the_screens():
    assert [s.key for s in STEPS] == ["scroll_up", "scroll_down", "prev_tab", "next_tab",
                                      "pause", "menu"]
    for s in STEPS:
        assert s.title and s.name and s.caption and s.tray and s.icon
