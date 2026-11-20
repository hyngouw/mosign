import pytest

from mosign.onboarding import CELEBRATE_SECONDS, STEP_PAUSE, STEPS, Onboarding

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
    icons = {s.icon for s in STEPS if s.icon}
    assert icons == {"scroll_up", "scroll_down", "prev_tab", "next_tab",
                     "toggle_menu", "toggle_tracking"}
    completing = {e for s in STEPS for e in s.target}
    assert {"sleep", "wake", "menu_on", "menu_off", "prev_tab", "next_tab"} <= completing


def walk_through(tour, clock):
    """Do every step the way a user would."""
    for step in tour.steps:
        assert tour.step == step
        if step.kind == "hand":
            assert clock.tick(tour, 40, hand_present=True) == "step"
        elif step.kind == "scroll":
            assert clock.tick(tour, 40, hand_present=True, scroll_mode=step.target[0]) in (
                "step", "done")
        else:
            clock.tick(tour, 5, hand_present=True)
            assert tour.step == step  # nothing happens without the gesture
            assert clock.tick(tour, 1, events=[step.target[0]]) in ("step", "done")
        if not tour.done:
            clock.wait_pause(tour)


def test_full_tour():
    tour, clock = Onboarding(), Clock()
    walk_through(tour, clock)
    assert tour.done and tour.step is None
    assert tour.celebrating(clock.t)
    assert not tour.celebrating(clock.t + CELEBRATE_SECONDS + 0.1)


def test_steps_cannot_be_skipped_with_the_wrong_gesture():
    tour, clock = Onboarding(), Clock()
    clock.tick(tour, 40, hand_present=True)
    clock.wait_pause(tour)
    assert tour.step.key == "scroll_up"
    clock.tick(tour, 60, scroll_mode="down", events=["next_tab", "sleep", "menu_off"])
    assert tour.step.key == "scroll_up" and tour.progress == 0


def test_scroll_step_needs_a_steady_hold():
    tour, clock = Onboarding(), Clock()
    clock.tick(tour, 40, hand_present=True)
    clock.wait_pause(tour)
    clock.tick(tour, 10, scroll_mode="up")
    assert 0 < tour.progress < 1 and tour.step.key == "scroll_up"


def test_hand_progress_drains_when_hand_leaves():
    tour, clock = Onboarding(), Clock()
    clock.tick(tour, 9, hand_present=True)
    p = tour.progress
    clock.tick(tour, 5, hand_present=False)
    assert tour.progress < p


def test_input_ignored_during_nice_pause():
    tour, clock = Onboarding(), Clock()
    while clock.tick(tour, 1, hand_present=True) != "step":
        pass
    assert tour.between_steps(clock.t)
    clock.tick(tour, 5, scroll_mode="up")
    assert tour.progress == 0


@pytest.mark.parametrize("menu,awake,expect", [
    (True, True, "hide"), (False, True, "show"),
])
def test_text_adapts_to_state(menu, awake, expect):
    tour = Onboarding()
    menu_step = next(s for s in STEPS if s.key == "menu")
    assert expect in tour.text_for(menu_step.instruction, menu, awake)
    pause_step = next(s for s in STEPS if s.key == "pause")
    assert "pause" in tour.text_for(pause_step.title, True, True)
    assert "wake up" in tour.text_for(pause_step.title, True, False)
