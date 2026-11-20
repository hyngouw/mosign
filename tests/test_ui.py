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
