"""Build fake 21-point hands for tests.

The hand is built upright (fingers toward the top of the image, thumb on the
left), then rotated on screen. Angles are counterclockwise as seen on screen,
so rotation=90 points the fingers to the LEFT, 180 down, -90 right.
"""

import math

ALL = {"thumb", "index", "middle", "ring", "pinky"}

# x offset of each finger's knuckle (MCP) across the palm
_MCP_X = {"index": -0.3, "middle": -0.1, "ring": 0.1, "pinky": 0.3}
_BASE = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}


def _rot(v, deg):
    t = math.radians(deg)
    x, y = v
    return (x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t))


def make_hand(extended, rotation=0.0, center=(0.8, 0.6), scale=0.15):
    """Return 21 (x, y) points in gesture space (y grows down)."""
    extended = set(extended)
    pts = [None] * 21
    pts[0] = (0.0, 0.0)  # wrist
    # local coords: up is -y, right is +x
    for name, mx in _MCP_X.items():
        b = _BASE[name]
        mcp = (mx, -0.9)
        if name in extended:
            pip = (mcp[0], mcp[1] - 0.45)
            dip = (mcp[0], pip[1] - 0.3)
            tip = (mcp[0], dip[1] - 0.25)
        else:  # curled back toward the palm
            pip = (mcp[0], mcp[1] - 0.35)
            dip = (mcp[0], pip[1] + 0.2)
            tip = (mcp[0], dip[1] + 0.2)
        pts[b], pts[b + 1], pts[b + 2], pts[b + 3] = mcp, pip, dip, tip
    pts[1] = (-0.3, -0.25)
    pts[2] = (-0.55, -0.45)
    pts[3] = (-0.75, -0.6)
    pts[4] = (-0.95, -0.75) if "thumb" in extended else (-0.1, -0.55)

    out = []
    for p in pts:
        rx, ry = _rot(p, rotation)
        out.append((center[0] + rx * scale, center[1] + ry * scale))
    return out
