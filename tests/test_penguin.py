import numpy as np
import pytest

from mosign import theme
from mosign.penguin import MAX_X, MAX_Y, Penguin


def run(p, seconds, t0=0.0, **kw):
    t = t0
    for _ in range(int(seconds * 30)):
        t += 1 / 30
        p.update(t, **kw)
    return t


def test_tab_switch_moves_pip_that_way_then_back():
    p = Penguin()
    p.update(0.0)
    p.update(1 / 30, events=["next_tab"])
    run(p, 0.15, 1 / 30)
    assert p.x > 15 and p.mood == "right"
    run(p, 3, 1)
    assert abs(p.x) < 2 and p.mood == "idle"

    p.update(10.0, events=["prev_tab"])
    run(p, 0.15, 10.0)
    assert p.x < -15 and p.mood == "left"


def test_scrolling_moves_pip_up_or_down():
    p = Penguin()
    run(p, 1.0, scroll_mode="up")
    assert p.y < -30 and p.mood == "up"
    run(p, 1.0, 2.0, scroll_mode="down")
    assert p.y > 30 and p.mood == "down"


def test_sleep_and_wake():
    p = Penguin()
    run(p, 0.5, events=(), awake=False)
    assert p.asleep and p.mood == "sleep" and p.zzz((100, 100))
    p.update(1.0, events=["wake"], awake=True)
    assert not p.asleep and p.mood == "wake" and not p.zzz((100, 100))


def test_menu_toggle_waves():
    p = Penguin()
    p.update(0.0, events=["menu_off"])
    assert p.waving and p.mood == "wave"


@pytest.mark.parametrize("event", ["next_tab", "prev_tab"])
def test_pip_never_leaves_its_panel(event):
    p = Penguin()
    t = 0.0
    for _ in range(100):  # spam the same gesture
        t += 1 / 30
        p.update(t, events=[event], scroll_mode="up")
        assert abs(p.x) <= MAX_X and abs(p.y) <= MAX_Y


def test_draw_in_every_mood():
    for kw in [dict(), dict(scroll_mode="up"), dict(scroll_mode="down"),
               dict(awake=False), dict(events=["next_tab"]), dict(events=["menu_on"])]:
        p = Penguin()
        run(p, 0.2, **kw)
        img = np.full((400, 220, 3), 240, np.uint8)
        p.draw_motion_hints(img, (110, 280))
        p.draw(img, (110, 280))
        assert (img != 240).any(axis=2).sum() > 5000


@pytest.mark.parametrize("event,sign", [("next_tab", 1), ("prev_tab", -1)])
def test_tab_chevrons_point_the_way_pip_moves(event, sign):
    p = Penguin()
    p.update(0.0)
    p.update(0.02, events=[event])
    img = np.full((400, 400, 3), 240, np.uint8)
    p.draw_motion_hints(img, (200, 280))
    ys, xs = np.where(np.all(img == theme.YELLOW, axis=2))
    assert len(xs)
    # A ">" chevron's tip (middle row) is its rightmost point; "<" the leftmost.
    row = int(round(ys.mean()))
    middle, others = xs[ys == row] * sign, xs[np.abs(ys - row) > 3] * sign
    assert middle.max() > others.max()
