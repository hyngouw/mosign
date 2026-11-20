"""Pip the penguin: a small buddy that copies your gestures.

Point up and Pip hops up, point down and Pip slides down, switch tabs and
Pip waddles left or right, pause tracking and Pip naps. It's quick visual
feedback that a gesture was understood, even out of the corner of your eye.

Movement uses a simple spring so Pip overshoots a little and settles back.
"""

import math

import cv2
import numpy as np

from mosign import theme
from mosign.draw import AA, ipt

BODY = theme.bgr("#263238")
BELLY = theme.WHITE
BEAK = theme.bgr("#F5B335")
CHEEK = theme.bgr("#F8C8C4")
PUPIL = theme.bgr("#1B2428")

MAX_X = 36      # how far Pip may move from the middle, in pixels
MAX_Y = 95
STIFFNESS = 110.0
DAMPING = 13.0

CAPTIONS = {
    "idle": "Waiting for a gesture",
    "up": "Hopping up!",
    "down": "Sliding down",
    "left": "Waddling back a tab",
    "right": "Waddling to the next tab",
    "sleep": "Napping… zzz",
    "wake": "Awake!",
    "wave": "Waving at you",
}


class Penguin:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.lean = 0.0          # degrees, + leans right
        self.facing = 0.0        # -1 left, 0 front, 1 right (eyes look that way)
        self.look_y = 0.0
        self.asleep = False
        self.mood = "idle"
        self._mood_until = 0.0
        self._wave_until = 0.0
        self._push_x = 0.0       # where a tab switch sends Pip for a moment
        self._push_until = 0.0
        self._last = None
        self._t = 0.0

    # ---------- behaviour ----------
    def _set_mood(self, mood, now, seconds=1.0):
        self.mood = mood
        self._mood_until = now + seconds

    def update(self, now, events=(), scroll_mode=None, awake=True):
        dt = 0.0 if self._last is None else max(0.0, min(0.1, now - self._last))
        self._last = now
        self._t += dt

        for event in events:
            if event in ("prev_tab", "next_tab"):
                d = -1 if event == "prev_tab" else 1
                self.vx += 260 * d
                self._push_x = MAX_X * d
                self._push_until = now + 0.55
                self.facing = d
                self._set_mood("left" if d < 0 else "right", now)
            elif event == "sleep":
                self._set_mood("sleep", now, 0)
            elif event == "wake":
                self.vy -= 650
                self._set_mood("wake", now, 1.2)
            elif event in ("menu_on", "menu_off"):
                self._wave_until = now + 1.0
                self._set_mood("wave", now)

        self.asleep = not awake
        target_x = self._push_x if now < self._push_until else 0.0
        target_y = 0.0
        if self.asleep:
            target_y = 14
            self.mood = "sleep"
        elif scroll_mode == "up":
            target_y = -60 - abs(math.sin(self._t * 9)) * 22   # little hops
            self.look_y = -1
            self.mood = "up"
        elif scroll_mode == "down":
            target_y = 60
            self.look_y = 1
            self.mood = "down"
        else:
            self.look_y *= 0.9
            if now > self._mood_until and self.mood not in ("idle",):
                self.mood = "idle"

        if now > self._mood_until:
            self.facing *= 0.92

        # spring toward the target
        ax = -STIFFNESS * (self.x - target_x) - DAMPING * self.vx
        ay = -STIFFNESS * (self.y - target_y) - DAMPING * self.vy
        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        # keep Pip inside the panel
        if abs(self.x) > MAX_X:
            self.x = math.copysign(MAX_X, self.x)
            self.vx *= -0.3
        if abs(self.y) > MAX_Y:
            self.y = math.copysign(MAX_Y, self.y)
            self.vy *= -0.3
        self.lean = max(-18.0, min(18.0, self.vx * 0.04))

    @property
    def caption(self):
        return CAPTIONS.get(self.mood, CAPTIONS["idle"])

    @property
    def waving(self):
        return self._last is not None and self._last < self._wave_until

    # ---------- drawing ----------
    def draw(self, img, center, scale=1.0):
        """Draw Pip with its feet-center resting at `center` (+ movement)."""
        base_x = center[0] + self.x
        base_y = center[1] + self.y
        lean = math.radians(self.lean)
        s = scale

        def P(lx, ly):
            """Local point (origin between the feet, y up negative) -> image."""
            x = lx * math.cos(lean) - ly * math.sin(lean)
            y = lx * math.sin(lean) + ly * math.cos(lean)
            return ipt((base_x + x * s, base_y + y * s))

        def ell(lx, ly, ax, ay, color, angle=0.0, thickness=-1):
            cv2.ellipse(img, P(lx, ly), (max(1, int(ax * s)), max(1, int(ay * s))),
                        angle + self.lean, 0, 360, color, thickness, AA)

        # ground shadow shrinks as Pip rises
        lift = max(0.0, -self.y) / MAX_Y
        sw = int((46 - 18 * lift) * s)
        cv2.ellipse(img, ipt((center[0] + self.x, center[1] + 6 * s)), (sw, int(8 * s)),
                    0, 0, 360, theme.GREEN_SOFT, -1, AA)

        # feet
        ell(-18, -2, 16, 7, BEAK)
        ell(18, -2, 16, 7, BEAK)

        # flippers (flap while hopping, wave on menu toggle)
        flap = 0.0
        if self.mood == "up":
            flap = math.sin(self._t * 18) * 25
        left_angle, right_angle = 20 + flap, -20 - flap
        if self.waving:
            right_angle = -70 + math.sin(self._t * 14) * 30
        ell(-48, -60, 12, 36, BODY, left_angle)
        ell(48, -60, 12, 36, BODY, right_angle)

        # body + belly
        ell(0, -66, 50, 66, BODY)
        ell(0, -56, 36, 50, BELLY)

        # face
        eye_dx = 6 * self.facing
        eye_dy = 4 * self.look_y
        for side in (-1, 1):
            ex, ey = side * 17, -100
            if self.asleep:
                cv2.ellipse(img, P(ex, ey + 2), (int(8 * s), int(5 * s)), self.lean, 0, 180,
                            PUPIL, max(2, int(2.5 * s)), AA)
            else:
                ell(ex, ey, 10, 12, theme.WHITE)
                ell(ex + eye_dx, ey + eye_dy + 1, 5, 6, PUPIL)
                ell(ex + eye_dx - 2, ey + eye_dy - 2, 1.6, 1.6, theme.WHITE)
            ell(side * 28, -84, 7, 4, CHEEK)
        beak = np.array([P(-10, -86), P(10, -86), P(0, -72)], np.int32)
        cv2.fillPoly(img, [beak], BEAK, AA)

        # little hair tuft, because why not
        cv2.line(img, P(0, -131), P(4, -142), BODY, max(2, int(3 * s)), AA)

    def draw_motion_hints(self, img, center, scale=1.0):
        """Faint chevrons showing which way Pip is going."""
        cx, cy = center[0] + self.x, center[1] + self.y - 66 * scale
        color = theme.YELLOW
        phase = (self._t * 2.0) % 1.0
        if self.mood == "up":
            for i in range(2):
                y = cy - (95 + 18 * i + 14 * phase) * scale
                self._chevron(img, (cx, y), 0, color, scale)
        elif self.mood == "down":
            for i in range(2):
                y = cy + (95 + 18 * i + 14 * phase) * scale
                self._chevron(img, (cx, y), 180, color, scale)
        elif self.mood in ("left", "right"):
            d = -1 if self.mood == "left" else 1
            for i in range(2):  # ">>" or "<<" above Pip's head
                x = cx + d * (16 * i - 8 + 10 * phase) * scale
                self._chevron(img, (x, cy - 100 * scale), 90 * d, color, scale)

    @staticmethod
    def _chevron(img, c, angle_deg, color, scale):
        t = math.radians(angle_deg)
        pts = [(-10, 6), (0, -4), (10, 6)]
        out = []
        for x, y in pts:
            rx = x * math.cos(t) - y * math.sin(t)
            ry = x * math.sin(t) + y * math.cos(t)
            out.append(ipt((c[0] + rx * scale, c[1] + ry * scale)))
        cv2.polylines(img, [np.array(out, np.int32)], False, color, max(2, int(4 * scale)), AA)

    def zzz(self, center, scale=1.0):
        """(text, xy, size) for floating Z's while asleep (drawn by the caller)."""
        items = []
        if not self.asleep:
            return items
        for i in range(3):
            phase = (self._t * 0.6 + i / 3) % 1.0
            x = center[0] + self.x + (40 + 18 * phase + 8 * i) * scale
            y = center[1] + self.y - (140 + 70 * phase) * scale
            items.append(("z", (x, y), int((14 + 8 * i) * scale)))
        return items
