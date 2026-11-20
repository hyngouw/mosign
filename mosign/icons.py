"""Little hand drawings that show each gesture (used by the menu and the tour)."""

import math

import cv2
import numpy as np

from mosign import theme
from mosign.draw import AA, ipt

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
    draw_hand_icon(img, (cx, cy), size * 0.82, fingers, rotation)
    if held:
        r = max(5, int(size * 0.14))
        c = (int(center[0] + size * 0.36), int(center[1] + size * 0.34))
        cv2.circle(img, c, r, theme.WHITE, -1, AA)
        cv2.circle(img, c, r, theme.BORDER, 2, AA)
        sweep = (t % 1.6) / 1.2 if animate else 1.0
        cv2.ellipse(img, c, (r, r), -90, 0, 360 * min(1.0, sweep), theme.YELLOW, max(2, r // 3), AA)
