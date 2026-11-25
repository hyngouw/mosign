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
        if p.stem.endswith("_screen"):     # overlay drawn over a fake web page
            assert img.shape[1] == 1440 and img.shape[0] >= 900
        else:
            assert img.shape == (HEIGHT * 2, WIDTH * 2, 3)   # previews are drawn at 2x, like Retina


def test_background_is_light_green():
    img = UI().render(View(), now=0)
    assert tuple(int(c) for c in img[HEIGHT - 4, WIDTH // 2]) == theme.BG


def test_buttons_are_clickable():
    ui = UI()
    ui.render(View(), now=0)
    names = {b.command for b in ui.buttons}
    assert {"swap_camera", "toggle_tracking", "quit"} <= names
    swap = next(b for b in ui.buttons if b.command == "swap_camera")
    ui.click(swap.rect.cx, swap.rect.cy)
    assert ui.pop_commands() == ["swap_camera"]
    assert ui.pop_commands() == []
    ui.click(5, 5)  # empty space
    assert ui.pop_commands() == []


def test_pause_button_label_follows_state():
    ui = UI()
    ui.render(View(awake=False), now=0)
    labels = [b.label for b in ui.buttons]
    assert "Resume" in labels


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


def test_tour_button_follows_the_tutorial_state():
    from mosign.onboarding import Onboarding
    ui = UI()
    tour = Onboarding()
    tour.index = 3  # "point left"
    ui.render(View(tour=tour, tour_required=True), now=0)
    labels = [b.command for b in ui.buttons]
    assert "tour" not in labels  # can't skip on first run
    ui.render(View(tour=tour, tour_required=False), now=0)
    assert any(b.label == "End tour" for b in ui.buttons)
    ui.render(View(), now=0)
    assert any(b.label == "Tour" for b in ui.buttons)


def test_hand_outside_frame_is_clipped_to_camera():
    from mosign.ui import CAMERA, STATUS
    ui = UI()
    frame = np.zeros((360, 640, 3), np.uint8)
    far = [(0.5, 1.6)] * 21   # way below the frame
    a = ui.render(View(frame=frame), now=0)
    b = ui.render(View(frame=frame, hand=far), now=0)
    # the gap between the camera and the status card must stay untouched
    below = (slice(CAMERA.bottom, STATUS.y), slice(CAMERA.x, CAMERA.right))
    assert np.array_equal(a[below], b[below])


def test_main_window_buttons_fit_in_the_bar():
    from mosign.ui import BAR
    ui = UI()
    for view in (View(), View(awake=False, menu_visible=False)):
        ui.render(view, now=0)
        assert ui.buttons[-1].rect.right <= BAR.right



def test_buttons_are_equal_width_and_evenly_spaced():
    from mosign.ui import BAR, View

    ui = UI()
    for view in (View(), View(awake=False, menu_visible=False)):
        buttons = ui._layout_buttons(view)
        widths = {b.rect.w for b in buttons}
        assert max(widths) - min(widths) <= 1
        gaps = {b2.rect.x - b1.rect.right for b1, b2 in zip(buttons, buttons[1:])}
        assert max(gaps) - min(gaps) <= 1
        assert buttons[0].rect.x == BAR.x and abs(buttons[-1].rect.right - BAR.right) <= 1


def test_every_gesture_hand_is_the_same_size():
    from mosign.icons import SPRITES, hand_sprite

    for label in SPRITES:
        sprite = hand_sprite(label, 100)
        assert sprite is not None and max(sprite.shape[:2]) == 100


def test_window_can_be_drawn_at_retina_size():
    one, two = UI(1).render(View(), now=0), UI(2).render(View(), now=0)
    assert one.shape == (HEIGHT, WIDTH, 3) and two.shape == (HEIGHT * 2, WIDTH * 2, 3)
    # same picture, but the 2x one has real detail: it is not just the 1x one stretched
    stretched = cv2.resize(one, (WIDTH * 2, HEIGHT * 2), interpolation=cv2.INTER_LINEAR)
    sharp = lambda im: cv2.Laplacian(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    assert sharp(two) > sharp(stretched) * 1.3


def test_clicks_stay_in_logical_pixels_at_any_scale():
    for scale in (1, 2):
        ui = UI(scale)
        ui.render(View(), now=0)
        quit_button = next(b for b in ui.buttons if b.command == "quit")
        assert ui.click(quit_button.rect.cx, quit_button.rect.cy) == "quit"


def test_scale_can_change_while_running():
    ui = UI(2)
    ui.render(View(), now=0)
    ui.set_scale(2.5)
    img = ui.render(View(), now=1)
    assert img.shape == (int(HEIGHT * 2.5), int(WIDTH * 2.5), 3)
    ui.set_scale(2)
    assert ui.render(View(), now=2).shape == (HEIGHT * 2, WIDTH * 2, 3)


def test_camera_picture_has_rounded_corners_at_every_scale():
    import numpy as np
    frame = np.full((360, 640, 3), 30, np.uint8)
    for scale in (1, 2):
        img = UI(scale).render(View(frame=frame), now=0)
        from mosign.ui import CAMERA
        corner = img[int(CAMERA.y * scale), int(CAMERA.x * scale)]
        middle = img[int((CAMERA.y + 200) * scale), int((CAMERA.x + 360) * scale)]
        assert tuple(int(c) for c in corner) != (30, 30, 30)      # corner shows the window, not the picture
        assert tuple(int(c) for c in middle) == (30, 30, 30)
