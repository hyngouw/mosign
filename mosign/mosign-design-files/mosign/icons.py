"""Little hand drawings that show each gesture (used by the menu and the tour)."""

import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from mosign import theme
from mosign.draw import AA, blend_rgba, ipt

HAND_DIR = Path(__file__).resolve().parent / "assets" / "hands"

# gesture label -> (sprite file, flip left-right, rotate 180). The illustrations
# are drawn once (pointing up / pointing right) and turned for the other gestures.
SPRITES = {
    "scroll_up": ("up", False, False),
    "scroll_down": ("up", False, True),
    "prev_tab": ("right", True, False),
    "next_tab": ("right", False, False),
    "toggle_tracking": ("horns", False, False),
    "toggle_menu": ("pinky", False, False),
    "palm": ("palm", False, False),
}

# Local hand shape: palm length = 1, y grows down, fingers point up (-y).
_PALM = [(-0.42, 0.05), (0.42, 0.05), (0.46, -0.82), (-0.46, -0.82)]
_FINGER_X = {"index": -0.33, "middle": -0.11, "ring": 0.11, "pinky": 0.33}
_FINGER_LEN = {"index": 0.78, "middle": 0.86, "ring": 0.78, "pinky": 0.62}
_THUMB_BASE = (-0.42, -0.22)
_THUMB_OUT = (-0.88, -0.72)
_THUMB_IN = (-0.12, -0.52)
_CENTER = (0.0, -0.72)  # middle of the whole hand shape

# What each gesture looks like: (fingers that are out, rotation in degrees
# counterclockwise on screen, motion arrow direction or None, held?)
POSES = {
    "scroll_up": ({"index"}, 0, (0, -1), False),
    "scroll_down": ({"index"}, 180, (0, 1), False),
    "prev_tab": ({"index"}, 90, (-1, 0), False),
    "next_tab": ({"index"}, -90, (1, 0), False),
    "toggle_tracking": ({"index", "pinky"}, 0, None, True),
    "toggle_menu": ({"pinky"}, 0, None, True),
}


def _rot(p, deg):
    t = math.radians(deg)
    x, y = p[0] - _CENTER[0], p[1] - _CENTER[1]
    return (x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t))


def draw_hand_icon(img, center, size, fingers, rotation=0.0,
                   fill=theme.GREEN, active=theme.YELLOW, outline=theme.GREEN_DARK):
    """Draw a simple hand. Raised fingers are yellow, the rest green.

    `size` is roughly the icon's height in pixels.
    """
    scale = size / 1.85
    cx, cy = center

    def tx(p):
        rx, ry = _rot(p, rotation)
        return (cx + rx * scale, cy + ry * scale)

    width = max(3, int(0.25 * scale))
    segments = []  # (start, end, color)
    for name, x in _FINGER_X.items():
        base = (x, -0.78)
        if name in fingers:
            tip = (x, -0.78 - _FINGER_LEN[name])
            segments.append((base, tip, active))
        else:
            segments.append((base, (x, -0.95), fill))  # knuckle bump
    thumb_tip = _THUMB_OUT if "thumb" in fingers else _THUMB_IN
    segments.append((_THUMB_BASE, thumb_tip, active if "thumb" in fingers else fill))

    palm = np.array([ipt(tx(p)) for p in _PALM], np.int32)
    # outline pass, then color pass, so overlapping parts merge cleanly
    for a, b, _ in segments:
        cv2.line(img, ipt(tx(a)), ipt(tx(b)), outline, width + 4, AA)
    cv2.polylines(img, [palm], True, outline, 4, AA)
    cv2.fillPoly(img, [palm], fill, AA)
    for a, b, color in segments:
        if color == fill:
            cv2.line(img, ipt(tx(a)), ipt(tx(b)), color, width, AA)
    for a, b, color in segments:
        if color != fill:
            cv2.line(img, ipt(tx(a)), ipt(tx(b)), color, width, AA)


@lru_cache(maxsize=64)
def hand_sprite(label, longest):
    """The illustrated hand for a gesture as straight-alpha BGRA, `longest` px on
    its longer side. Every hand is scaled the same way, so they all look the same size."""
    name, flip, rot = SPRITES[label]
    img = cv2.imread(str(HAND_DIR / f"{name}.png"), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if flip:
        img = cv2.flip(img, 1)
    if rot:
        img = cv2.rotate(img, cv2.ROTATE_180)
    h, w = img.shape[:2]
    k = longest / max(h, w)
    size = (max(1, round(w * k)), max(1, round(h * k)))
    # premultiplied resize avoids dark fringes around the outline
    a = img[..., 3:4].astype(np.float32) / 255.0
    pre = np.dstack([img[..., :3].astype(np.float32) * a, a * 255.0])
    pre = cv2.resize(pre, size, interpolation=cv2.INTER_AREA)
    alpha = pre[..., 3:4]
    rgb = np.where(alpha > 0, pre[..., :3] / np.maximum(alpha, 1e-6) * 255.0, 0)
    return np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8)


def draw_hand_sprite(img, center, longest, label):
    sprite = hand_sprite(label, max(8, int(longest)))
    if sprite is None:
        return False
    h, w = sprite.shape[:2]
    blend_rgba(img, sprite, int(round(center[0] - w / 2)), int(round(center[1] - h / 2)))
    return True


def draw_arrow(img, start, end, color=theme.GREEN_DARK, thickness=3):
    cv2.arrowedLine(img, ipt(start), ipt(end), color, thickness, AA, tipLength=0.35)


def draw_gesture_icon(img, center, size, label, t=0.0, animate=True):
    """Hand + motion hint for a gesture label. `t` (seconds) drives the demo."""
    fingers, rotation, arrow, held = POSES[label]
    cx, cy = center
    if arrow and animate:
        nudge = math.sin(t * 5.0) * 0.06 * size
        cx += arrow[0] * nudge
        cy += arrow[1] * nudge
    if not draw_hand_sprite(img, (cx, cy), size * 0.8, label):
        draw_hand_icon(img, (cx, cy), size * 0.82, fingers, rotation)
    if held:
        r = max(5, int(size * 0.14))
        c = (int(center[0] + size * 0.36), int(center[1] + size * 0.34))
        cv2.circle(img, c, r, theme.WHITE, -1, AA)
        cv2.circle(img, c, r, theme.BORDER, 2, AA)
        sweep = (t % 1.6) / 1.2 if animate else 1.0
        cv2.ellipse(img, c, (r, r), -90, 0, 360 * min(1.0, sweep), theme.YELLOW, max(2, r // 3), AA)


def draw_palm_icon(img, center, size):
    """An open hand (the tour's "show your hand" step)."""
    if not draw_hand_sprite(img, center, size * 0.8, "palm"):
        draw_hand_icon(img, center, size, {"thumb", "index", "middle", "ring", "pinky"})
