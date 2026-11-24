"""Render the Mosign window and the screen overlay to PNG files (no camera needed).

The *_screen.png files show the overlay composited over a fake browser page,
the way it floats in the top-right corner of your screen.

    python scripts/preview_ui.py [output_folder]

Handy for checking the look after changing colors or layout.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from handgen import make_hand  # noqa: E402
from mosign.onboarding import Onboarding  # noqa: E402
from mosign.overlay import Overlay  # noqa: E402
from mosign.ui import UI, View  # noqa: E402


def fake_frame(w=1280, h=720):
    """A soft gradient 'room' so the preview isn't a flat block."""
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    b = (90 + 60 * y + 20 * x).astype(np.uint8)
    g = (110 + 50 * y).astype(np.uint8) * np.ones_like(x, np.uint8)
    r = (130 + 40 * x + 30 * y).astype(np.uint8)
    return np.dstack([np.broadcast_to(c, (h, w)) for c in (b, g, r)]).copy()


def norm_hand(fingers, rotation=0, w=1280, h=720):
    aspect = w / h
    pts = make_hand(fingers, rotation, center=(0.62 * aspect, 0.72), scale=0.22)
    return [(x / aspect, y) for x, y in pts]


def tour_at(index, progress=0.0, between=False, done=False, now=0.0):
    tour = Onboarding()
    tour.index = index
    tour.progress = progress
    if between:
        tour._paused_until = now + 10
    if done:
        tour.index, tour.done, tour.finished_at = tour.total, True, now
    return tour


def scenes():
    frame = fake_frame()
    yield "00_tour_start", View(frame=frame, tour=tour_at(0, 0.3), tour_required=True,
                                hand=norm_hand({"thumb", "index", "middle", "ring", "pinky"}))
    yield "00b_tour_scroll_down", View(frame=frame, hand=norm_hand({"index"}, 180),
                                       confirmed="scroll_down", scroll_mode="down",
                                       tour=tour_at(2, 0.55), tour_required=True)
    yield "00c_tour_between", View(frame=frame, tour=tour_at(5, between=True, now=130),
                                   tour_required=True)
    yield "00d_tour_done", View(frame=frame, tour=tour_at(0, done=True, now=130),
                                events=["celebrate"])
    yield "01_idle", View(frame=frame, fps=30)
    yield "02_scrolling_up", View(frame=frame, hand=norm_hand({"index"}), confirmed="scroll_up",
                                  scroll_mode="up", fps=30)
    yield "03_next_tab", View(frame=frame, hand=norm_hand({"index"}, -90), confirmed="next_tab",
                              events=["next_tab"], fps=30)
    yield "03b_scroll_down", View(frame=frame, hand=norm_hand({"index"}, 180),
                                  confirmed="scroll_down", scroll_mode="down", fps=30)
    yield "04_holding_sleep", View(frame=frame, hand=norm_hand({"index", "pinky"}),
                                   confirmed="toggle_tracking",
                                   holding=("toggle_tracking", 0.6), fps=30)
    yield "05_paused", View(frame=frame, hand=norm_hand(set()), awake=False, fps=30)
    yield "06_no_camera", View(frame=None, camera_label="No camera")
    yield "07_menu_hidden", View(frame=frame, hand=norm_hand({"pinky"}), confirmed="toggle_menu",
                                 holding=("toggle_menu", 0.3), menu_visible=False, fps=30)


def fake_browser(w=1440, h=900):
    """A plain made-up web page to show the overlay on top of."""
    img = np.full((h, w, 3), 252, np.uint8)
    cv2.rectangle(img, (0, 0), (w, 64), (236, 236, 236), -1)
    cv2.rectangle(img, (160, 16), (w - 160, 48), (255, 255, 255), -1)
    for i in range(12):
        y = 130 + i * 58
        cv2.rectangle(img, (120, y), (120 + 520 + (i % 3) * 90, y + 16), (205, 205, 205), -1)
    cv2.rectangle(img, (w - 560, 120), (w - 140, 420), (196, 160, 122), -1)
    return img


def composite(bg, over, x, y):
    h, w = over.shape[:2]
    a = over[..., 3:4].astype(np.float32) / 255
    roi = bg[y:y + h, x:x + w].astype(np.float32)
    bg[y:y + h, x:x + w] = (over[..., :3] + roi * (1 - a)).clip(0, 255).astype(np.uint8)
    return bg


def main(out=None, scale=2.0):
    out = Path(out or ROOT / "build" / "preview")
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (name, view) in enumerate(scenes()):
        ui, overlay = UI(), Overlay(scale)
        t = 100.0 + i * 10
        # play a few frames so Pip is caught mid-move
        for k in range(12):
            overlay.update(view, t + k / 30)
            ui.render(view, now=t + k / 30)
            view.events = []
        now = t + 12 / 30
        img = ui.render(view, now=now)
        path = out / f"{name}.png"
        cv2.imwrite(str(path), img)
        paths.append(path)

        over = overlay.render(view, now)
        margin = int(12 * scale)
        screen = fake_browser(1440, max(900, over.shape[0] + 3 * margin))
        composite(screen, over, screen.shape[1] - over.shape[1] - margin, margin)
        path = out / f"{name}_screen.png"
        cv2.imwrite(str(path), screen)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in main(sys.argv[1] if len(sys.argv) > 1 else None):
        print(p)
