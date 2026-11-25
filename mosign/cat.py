"""The cat: drawn from the layers of the "feed cat" Rive file (assets/cat).

The .riv file only animates eating / gagging, so everything Mosign needs is
done here on the separate layers: breathing, blinking, a swaying tail,
looking up / down while you scroll, sleeping (closed eyes + Z's) while
tracking is paused, and squash-and-stretch for jumps.

CatFace decides how the cat looks (pure logic, easy to test);
CatSprite turns that into a transparent image; CatMotion moves the cat
around the screen (jumping from tab to tab).
"""

import math
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from mosign import theme

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "cat"
CANVAS = (420, 425)                      # size of every layer image
EYES = [(119.5, 157.4), (238.3, 159.9)]  # eye centres on the canvas
EYE_RADIUS = 9.5
TAIL_PIVOT = (340.0, 375.0)              # where the tail meets the body
FEET_Y = 419.0                           # bottom of the feet on the canvas
INK = (51, 35, 13)                       # the drawing's outline colour (RGB)
BACK_LAYERS = ["body", "foot", "head", "ear", "whiskers", "nose"]  # drawn after the tail

HEADROOM = 0.45   # extra space above the cat (for Z's and stretch), x cat height
SIDE_ROOM = 0.15  # extra space either side (for leaning)


@lru_cache(maxsize=1)
def load_layers():
    layers = {}
    for path in ASSET_DIR.glob("*.png"):
        layers[path.stem] = Image.open(path).convert("RGBA")
    return layers


def to_premultiplied_bgra(img):
    """PIL RGBA -> numpy BGRA with premultiplied alpha (what the Qt overlay wants)."""
    a = np.asarray(img, dtype=np.uint16)
    alpha = a[..., 3:4]
    rgb = (a[..., :3] * alpha + 127) // 255
    return np.dstack([rgb[..., ::-1], alpha]).astype(np.uint8)


class CatFace:
    """How the cat looks right now: eyes, mouth, breathing, tail, Z's."""

    def __init__(self, seed=7):
        self._rng = random.Random(seed)
        self.t = 0.0
        self.asleep = False
        self.look = 0.0             # -1 looking up .. +1 looking down
        self._look_target = 0.0
        self._next_blink = 2.5
        self._blink_until = -1.0
        self._mouth_until = -1.0
        self._wide_until = -1.0
        self._swish_until = -1.0
        self._last = None

    def update(self, now, events=(), scroll_mode=None, awake=True):
        dt = 0.0 if self._last is None else max(0.0, min(0.1, now - self._last))
        self._last = now
        self.t += dt

        for event in events:
            if event in ("next_tab", "prev_tab"):
                self._mouth_until = now + 0.55       # a little "mrrp!" on the jump
            elif event == "wake":
                self._wide_until = now + 0.8          # big surprised eyes
            elif event in ("menu_on", "menu_off"):
                self._swish_until = now + 1.2
            elif event == "celebrate":
                self._mouth_until = now + 1.5
                self._swish_until = now + 2.0

        self.asleep = not awake
        self._look_target = {"up": -1.0, "down": 1.0}.get(scroll_mode, 0.0)
        if self.asleep:
            self._look_target = 0.0
        self.look += (self._look_target - self.look) * min(1.0, dt * 10)

        if not self.asleep and now >= self._next_blink:
            self._blink_until = now + 0.13
            self._next_blink = now + self._rng.uniform(2.5, 6.0)

    @property
    def eyes(self):
        """'closed', 'wide' or 'open'."""
        if self.asleep or self._last is not None and self._last < self._blink_until:
            return "closed"
        if self._last is not None and self._last < self._wide_until:
            return "wide"
        return "open"

    @property
    def mouth_open(self):
        return not self.asleep and self._last is not None and self._last < self._mouth_until

    @property
    def breath(self):
        """Vertical scale offset: slow and deep asleep, quick and small awake."""
        if self.asleep:
            return 0.03 * math.sin(self.t * 1.6)
        return 0.012 * math.sin(self.t * 3.2)

    @property
    def tail_angle(self):
        swishing = self._last is not None and self._last < self._swish_until
        if self.asleep:
            return 2.0 * math.sin(self.t * 0.8)
        if swishing:
            return 16.0 * math.sin(self.t * 14)
        return 7.0 * math.sin(self.t * 2.1)

    def zzz(self):
        """[(x, y, size)] for floating Z's, in units of the cat's height."""
        if not self.asleep:
            return []
        out = []
        for i in range(3):
            phase = (self.t * 0.45 + i / 3) % 1.0
            out.append((0.58 + 0.14 * phase + 0.04 * i, 0.05 - 0.38 * phase, 0.12 + 0.04 * i))
        return out


class CatSprite:
    """Draws the cat `height` pixels tall (plus room for Z's and leaning)."""

    def __init__(self, height):
        self.height = int(height)
        self.scale = self.height / CANVAS[1]
        w = max(1, round(CANVAS[0] * self.scale))
        layers = load_layers()
        self._layers = {n: im.resize((w, self.height), Image.LANCZOS) for n, im in layers.items()}
        self.cat_w = w
        self.width = int(round(w * (1 + 2 * SIDE_ROOM)))
        self.full_height = int(round(self.height * (1 + HEADROOM)))

    @property
    def anchor(self):
        """Pixel in the output image where the cat's feet touch the ground."""
        return self.width / 2, self.full_height - (CANVAS[1] - FEET_Y) * self.scale

    def _closed_eyes(self, img, squint=False):
        d = ImageDraw.Draw(img)
        s = self.scale
        width = max(2, round(5.5 * s))
        for cx, cy in EYES:
            r = EYE_RADIUS * 1.25 * s
            box = [cx * s - r, cy * s - r * 0.7, cx * s + r, cy * s + r * 1.1]
            d.arc(box, 25 if not squint else 200, 155 if not squint else 340,
                  fill=INK + (255,), width=width)

    def render_cat(self, face):
        """The cat alone, canvas-sized (no squash), as PIL RGBA."""
        img = Image.new("RGBA", (self.cat_w, self.height), (0, 0, 0, 0))
        s = self.scale
        tail = self._layers["tail"].rotate(face.tail_angle, resample=Image.BICUBIC,
                                           center=(TAIL_PIVOT[0] * s, TAIL_PIVOT[1] * s))
        img.alpha_composite(tail)
        for name in BACK_LAYERS:
            img.alpha_composite(self._layers[name])

        eyes = face.eyes
        if eyes == "closed":
            self._closed_eyes(img)
        else:
            layer = self._layers["eyes_2" if eyes == "wide" else "eyes"]
            dy = int(round(face.look * 5 * s)) if eyes == "open" else 0
            img.alpha_composite(layer, (0, dy))
        img.alpha_composite(self._layers["mouth_2" if face.mouth_open else "mouth_1"])
        return img

    def render(self, face, squash=0.0, lean=0.0):
        """Transparent image with the cat standing on `anchor`.

        squash > 0 flattens (landing), < 0 stretches (in the air).
        lean is in degrees, + leans right.
        """
        cat = self.render_cat(face)
        sy = max(0.6, 1.0 - squash + face.breath)
        sx = max(0.6, 1.0 + squash * 0.6 - face.breath * 0.4)
        w = max(1, round(self.cat_w * sx))
        h = max(1, round(self.height * sy))
        cat = cat.resize((w, h), Image.BICUBIC)
        out = Image.new("RGBA", (self.width, self.full_height), (0, 0, 0, 0))
        ax, ay = self.anchor
        feet_in_cat = FEET_Y * self.scale * sy
        out.alpha_composite(cat, (int(round(ax - w / 2)), int(round(ay - feet_in_cat))))
        if lean:
            out = out.rotate(-lean, resample=Image.BICUBIC, center=(ax, ay))

        zs = face.zzz()
        if zs:
            d = ImageDraw.Draw(out)
            top = ay - self.height
            for zx, zy, size in zs:
                fs = max(8, int(size * self.height))
                alpha = int(255 * min(1.0, 1.2 - zy * -1.5)) if zy < 0 else 255
                d.text((self.width * 0.5 + (zx - 0.5) * self.cat_w, top + zy * self.height),
                       "z", font=theme.font(fs, True), fill=INK + (max(60, min(255, alpha)),))
        return out

    def render_bgra(self, face, squash=0.0, lean=0.0):
        return to_premultiplied_bgra(self.render(face, squash, lean))


class CatMotion:
    """Where the cat's feet are on screen, and how it jumps between places.

    All positions are screen coordinates (logical pixels). `go(x, y)` makes
    the cat jump there in an arc; `hop(direction)` is a little jump in place
    when there's no tab to jump to.
    """

    LAND_SECONDS = 0.18
    HOP_SECONDS = 0.38

    def __init__(self, x=0.0, y=0.0):
        self.x, self.y = float(x), float(y)
        self.target = (self.x, self.y)
        self._jump = None    # (start_time, duration, (x0, y0), (x1, y1), height)
        self._hop = None     # (start_time, direction)
        self._landed_at = -10.0
        self.squash = 0.0
        self.lean = 0.0

    @property
    def jumping(self):
        return self._jump is not None

    def place(self, x, y):
        """Teleport (e.g. the very first frame)."""
        self.x, self.y = float(x), float(y)
        self.target = (self.x, self.y)
        self._jump = None

    def go(self, x, y, now):
        x, y = float(x), float(y)
        if math.hypot(x - self.target[0], y - self.target[1]) < 3:
            return False
        self.target = (x, y)
        dist = math.hypot(x - self.x, y - self.y)
        if dist < 6 and not self._jump:      # window nudged: just follow it
            self.x, self.y = x, y
            return False
        duration = min(0.8, max(0.34, 0.3 + dist / 2400))
        height = min(160.0, 34 + dist * 0.12)
        self._jump = (now, duration, (self.x, self.y), (x, y), height)
        self._hop = None
        return True

    def hop(self, direction, now):
        if self._jump is None:
            self._hop = (now, 1 if direction >= 0 else -1)

    def update(self, now):
        self.squash, self.lean = 0.0, 0.0
        if self._jump is not None:
            t0, dur, (x0, y0), (x1, y1), h = self._jump
            p = min(1.0, (now - t0) / dur)
            e = p * p * (3 - 2 * p)               # ease in-out for x
            self.x = x0 + (x1 - x0) * e
            self.y = y0 + (y1 - y0) * p - 4 * h * p * (1 - p)
            direction = 1 if x1 >= x0 else -1
            if p < 0.12:
                self.squash = 0.18 * (1 - p / 0.12)       # crouch before take-off
            else:
                self.squash = -0.1 * math.sin(math.pi * p)  # stretch in the air
            self.lean = direction * 10 * math.sin(math.pi * p)
            if p >= 1.0:
                self._jump = None
                self.x, self.y = x1, y1
                self._landed_at = now
        elif self._hop is not None:
            t0, direction = self._hop
            p = min(1.0, (now - t0) / self.HOP_SECONDS)
            self.x = self.target[0] + direction * 26 * math.sin(math.pi * p)
            self.y = self.target[1] - 30 * math.sin(math.pi * p)
            self.lean = direction * 9 * math.sin(math.pi * p)
            self.squash = -0.06 * math.sin(math.pi * p)
            if p >= 1.0:
                self._hop = None
                self.x, self.y = self.target
                self._landed_at = now
        since = now - self._landed_at
        if self._jump is None and self._hop is None and 0 <= since < self.LAND_SECONDS:
            self.squash = 0.16 * (1 - since / self.LAND_SECONDS)   # squish on landing
