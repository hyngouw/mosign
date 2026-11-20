import importlib.util
from pathlib import Path

import cv2
import numpy as np

from mosign import theme
from mosign.ui import HEIGHT, WIDTH, UI, View, render_message

ROOT = Path(__file__).resolve().parent.parent


def load_preview():
    spec = importlib.util.spec_from_file_location("preview_ui", ROOT / "scripts" / "preview_ui.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_preview_scene_renders(tmp_path):
    paths = load_preview().main(tmp_path)
    assert len(paths) >= 6
    for p in paths:
        img = cv2.imread(str(p))
        assert img.shape == (HEIGHT, WIDTH, 3)


def test_background_is_light_green():
    img = UI().render(View(), now=0)
    assert tuple(int(c) for c in img[HEIGHT - 4, WIDTH // 2]) == theme.BG


def test_buttons_are_clickable():
    ui = UI()
    ui.render(View(), now=0)
    names = {b.command for b in ui.buttons}
    assert {"swap_camera", "toggle_tracking", "quit"} <= names
    swap = next(b for b in ui.buttons if b.command == "swap_camera")
    ui.on_mouse(cv2.EVENT_LBUTTONUP, swap.rect.cx, swap.rect.cy)
    assert ui.pop_commands() == ["swap_camera"]
    assert ui.pop_commands() == []
    ui.on_mouse(cv2.EVENT_LBUTTONUP, 5, 5)  # empty space
    assert ui.pop_commands() == []


def test_pause_button_label_follows_state():
    ui = UI()
    ui.render(View(awake=False), now=0)
    labels = [b.label for b in ui.buttons]
    assert "Resume tracking" in labels


def test_odd_camera_sizes_fit():
    ui = UI()
    for shape in [(480, 640, 3), (1080, 1920, 3), (100, 900, 3), (900, 100, 3)]:
        img = ui.render(View(frame=np.zeros(shape, np.uint8)), now=0)
        assert img.shape == (HEIGHT, WIDTH, 3)


def test_hand_drawn_in_yellow():
    from handgen import make_hand
    ui = UI()
    hand = [(x / (16 / 9), y) for x, y in make_hand({"index"}, center=(0.9, 0.6), scale=0.2)]
    plain = ui.render(View(frame=np.zeros((360, 640, 3), np.uint8)), now=0)
    drawn = ui.render(View(frame=np.zeros((360, 640, 3), np.uint8), hand=hand), now=0)
    changed = np.any(plain != drawn, axis=2)
    assert changed.sum() > 500
    yellow = np.all(np.abs(drawn.astype(int) - theme.YELLOW) < 10, axis=2)
    assert yellow.sum() > 100


def test_message_screen_wraps_long_text():
    img = render_message("Oops", "word " * 200)
    assert img.shape == (HEIGHT, WIDTH, 3)


def test_menu_panel_shows_and_hides():
    from mosign.ui import RIGHT
    ui = UI()
    shown = ui.render(View(menu_visible=True), now=0)
    hidden = ui.render(View(menu_visible=False), now=0)
    region = (slice(RIGHT.y + 80, RIGHT.bottom), slice(RIGHT.x, RIGHT.right))
    assert np.any(shown[region] != hidden[region], axis=2).mean() > 0.3
    # hidden: the lower part of the panel area is plain background
    assert np.all(hidden[RIGHT.bottom - 20, RIGHT.x + 20] == theme.BG)


def test_menu_highlights_current_gesture():
    from mosign.ui import RIGHT
    ui = UI()
    plain = ui.render(View(), now=0)
    lit = ui.render(View(confirmed="next_tab"), now=0)
    region = (slice(RIGHT.y, RIGHT.bottom), slice(RIGHT.x, RIGHT.right))
    yellow = np.all(np.abs(lit[region].astype(int) - theme.YELLOW_SOFT) < 6, axis=2)
    assert yellow.sum() > 2000
    assert not np.array_equal(plain[region], lit[region])


def test_menu_button_present():
    ui = UI()
    ui.render(View(menu_visible=False), now=0)
    assert any(b.command == "toggle_menu" and b.label == "Show menu" for b in ui.buttons)


def test_all_gesture_icons_draw():
    from mosign.icons import POSES, draw_gesture_icon
    for label in POSES:
        for t in (0.0, 0.4, 1.3):
            img = np.full((80, 80, 3), 250, np.uint8)
            draw_gesture_icon(img, (40, 40), 66, label, t)
            assert (img != 250).any(axis=2).sum() > 300


def test_penguin_panel_reacts_to_events():
    from mosign.ui import LEFT
    ui = UI()
    still = ui.render(View(), now=0.0)
    ui.render(View(events=["next_tab"]), now=0.03)
    moved = ui.render(View(), now=0.15)
    region = (slice(LEFT.y, LEFT.bottom), slice(LEFT.x, LEFT.right))
    assert not np.array_equal(still[region], moved[region])
    assert ui.penguin.caption.startswith("Waddling")
