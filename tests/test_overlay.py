import numpy as np
import pytest

from mosign import overlay as ov
from mosign.onboarding import Onboarding
from mosign.overlay import Overlay
from mosign.ui import View


def rendered(view, scale=1.0, frames=1, o=None):
    o = o or Overlay(scale)
    for k in range(frames):
        o.update(view, k / 30)
        view.events = []
    return o, o.render(view, frames / 30)


def composite(img, bg):
    a = img[..., 3:4].astype(np.float32) / 255
    return (img[..., :3] + bg * (1 - a)).astype(np.uint8)


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_size_matches_layout_and_scale(scale):
    o = Overlay(scale)
    for menu in (True, False):
        img = o.render(View(menu_visible=menu), 0)
        assert img.shape[:2][::-1] == o.size(menu)
        w, h = ov.logical_size(menu)
        assert img.shape[1] == round(w * scale)


def test_corners_are_see_through_and_card_is_solid():
    _, img = rendered(View())
    alpha = img[..., 3]
    assert alpha[0, 0] == 0 and alpha[0, -1] == 0       # top corners: empty
    card = Overlay()._menu_card()
    assert alpha[card.cy, card.cx] == 255                # menu card: solid
    assert alpha[card.bottom + 3, card.cx] not in (0, 255)  # soft shadow edge


def test_same_picture_on_any_background():
    """Correct alpha means the overlay looks identical over black and white."""
    _, img = rendered(View(scroll_mode="up"), frames=10)
    over_black = composite(img, 0.0)
    over_white = composite(img, 255.0)
    solid = img[..., 3] == 255
    assert np.abs(over_black[solid].astype(int) - over_white[solid]).max() <= 1
    clear = img[..., 3] == 0
    assert over_black[clear].max() == 0 and over_white[clear].min() == 255


def test_hidden_menu_and_idle_leaves_nothing_on_screen():
    _, shown = rendered(View(menu_visible=True))
    _, hidden = rendered(View(menu_visible=False))
    assert hidden.shape[0] < shown.shape[0] / 2
    assert hidden[..., 3].max() == 0       # nothing drawn: the cat has its own window


def test_menu_highlights_current_gesture_and_tour_target():
    _, plain = rendered(View())
    _, lit = rendered(View(confirmed="next_tab"))
    assert not np.array_equal(plain, lit)
    tour = Onboarding()
    tour.index = 3
    _, target = rendered(View(tour=tour))
    assert not np.array_equal(plain, target)


def test_status_pill_flashes_after_a_gesture_then_goes():
    o = Overlay()
    o.update(View(events=["next_tab"], menu_visible=False), 1.0)
    assert o.render(View(menu_visible=False), 1.0)[..., 3].max() == 255
    o.update(View(menu_visible=False), 3.0)
    assert o.render(View(menu_visible=False), 3.0)[..., 3].max() == 0


def test_home_spot_is_centred_above_the_menu():
    x, y = ov.home_feet(100, 20)
    assert x == 100 + ov.WIDTH / 2 and 20 < y < 20 + ov.HOME_HEIGHT


def test_hold_and_pause_captions_render():
    for view in (View(holding=("toggle_menu", 0.5), confirmed="toggle_menu"),
                 View(holding=("toggle_tracking", 0.9), awake=False),
                 View(awake=False)):
        _, img = rendered(view)
        assert img[..., 3].max() == 255


def test_all_gesture_icons_draw():
    from mosign.icons import POSES, draw_gesture_icon
    for label in POSES:
        for t in (0.0, 0.4, 1.3):
            img = np.full((80, 80, 3), 250, np.uint8)
            draw_gesture_icon(img, (40, 40), 66, label, t)
            assert (img != 250).any(axis=2).sum() > 300
