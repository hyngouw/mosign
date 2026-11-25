"""The onboarding screens, drawn into the same numpy window as the main UI.

welcome -> camera -> tutorial -> ready, plus "welcome back" for
returning users. The tutorial shows the real camera and reacts to the real
gestures: nothing here needs a click once you reach the tutorial.
"""

import math

import cv2
import numpy as np

from mosign import flow as F
from mosign import theme
from mosign.cat import CatFace, CatSprite
from mosign.draw import (
    Rect,
    S,
    TextLayer,
    U,
    blend_bgra_premultiplied,
    check_mark,
    circle,
    ellipse,
    line as draw_line,
    blend_rgba,
    paste,
    polylines,
    progress_bar,
    region,
    rounded_mask,
    rounded_rect,
    soft_shadow,
    wrap_text,
)
from mosign.icons import draw_hand_sprite, hand_sprite
from mosign.onboarding import FLASH_SECONDS, FLY_DELAY, FLY_SECONDS, STEP_PAUSE
from mosign.ui_types import Button

WIDTH, HEIGHT = 768, 780

SKY_TOP = theme.BG            # the pale header band of the camera screen
WINDOW = Rect(0, 0, WIDTH, HEIGHT)   # every screen is one card that fills the whole window
TUTORIAL_BG = theme.bgr("#FFF8D6")   # the light yellow around the X button
HALO = theme.bgr("#FBE98A")        # the pale disc behind the cat
CAT_HEIGHT = 190


def background():
    """What the onboarding screens fade out to: the main window's own colour."""
    return np.full((S(HEIGHT), S(WIDTH), 3), theme.BG, np.uint8)


def dome_card(img, rect, head_h, head=theme.YELLOW, bulge=44, radius=0, shadow=False,
              base=theme.WHITE):
    """A white card with a coloured top whose lower edge arches up in the middle.
    By default it fills `rect` edge to edge (no rounded corners, no shadow)."""
    if shadow:
        soft_shadow(img, rect, radius, offset=8, blur=18, strength=0.16)
    body = np.full((S(rect.h), S(rect.w), 3), base, np.uint8)
    if head_h > 0:
        body[:S(head_h)] = head
        if bulge > 0:
            ry = bulge * 3
            cv2.ellipse(body, (S(rect.w / 2), S(head_h + ry - bulge)),
                        (S(rect.w * 0.62), S(ry)), 0, 0, 360, base, -1, cv2.LINE_AA)
            body[S(head_h + 2 * bulge):] = base
    if radius:
        mask = rounded_mask(rect.w, rect.h, radius)
        roi = region(img, rect)
        roi[:] = (body * mask + roi * (1 - mask)).astype(np.uint8)
    else:
        region(img, rect)[:] = body


def cover(frame, w, h):
    """Crop-to-fill resize to w x h real pixels. Returns the picture and (scaled width,
    height, crop x, crop y), all in real pixels."""
    fh, fw = frame.shape[:2]
    k = max(w / fw, h / fh)
    nw, nh = max(w, round(fw * k)), max(h, round(fh * k))
    pic = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    ox, oy = (nw - w) // 2, (nh - h) // 2
    return pic[oy:oy + h, ox:ox + w].copy(), (nw, nh, ox, oy)


def ease_fly(x, x1=0.5, y1=0.0, x2=0.2, y2=1.0):
    """CSS cubic-bezier(.5, 0, .2, 1): the prototype's easing for the hand flying to its slot."""
    x = min(1.0, max(0.0, x))

    def bez(t, a, b):
        return 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t ** 2 * b + t ** 3

    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bez(mid, x1, x2) < x else (lo, mid)
    return bez((lo + hi) / 2, y1, y2)


LAND_SCALE = 0.5      # how big the hand is when it lands in its slot (1 = size in the panel)


class FlowScreens:
    def __init__(self, ui):
        self.ui = ui
        self._static = {}
        self._sprite = CatSprite(S(CAT_HEIGHT))
        self._face = CatFace()
        self.buttons = []

    # ---------- shared pieces ----------
    def _base(self, key, build):
        if key not in self._static:
            img = background()
            build(img)
            self._static[key] = img
        return self._static[key].copy()

    def _button(self, img, text, rect, command, label, primary=True, key=""):
        mx, my = self.ui.mouse
        hover = rect.contains(mx, my)
        if primary:
            fill = theme.YELLOW_HOVER if hover else theme.YELLOW
            rounded_rect(img, rect, rect.h // 2, fill)
        else:
            rounded_rect(img, rect, rect.h // 2, theme.GREEN_SOFT if hover else theme.PANEL_ALT)
        text.add(label, (rect.cx, rect.cy), 17 if primary else 16, theme.TEXT, True, "mm")
        self.buttons.append(Button(command, label, key, rect))

    def _cat(self, img, cx, feet_y, now):
        self._face.update(now, [], None, True)
        ax, ay = self._sprite.anchor
        blend_bgra_premultiplied(img, self._sprite.render_bgra(self._face),
                                 int(S(cx) - ax), int(S(feet_y) - ay))

    def _title(self, cx, y, parts, size=32):
        """Centred title from (string, color[, font]) parts, e.g. 'Welcome to ' + green 'Mosign'.
        A part's font is True (bold Outfit, the default) or "brand" (Madimi One)."""
        text = self.text
        parts = [(p + (True,))[:3] for p in parts]
        dot = {f: TextLayer.measure(".", size, f)[0] for f in {p[2] for p in parts}}
        widths = [TextLayer.measure(s + ".", size, f)[0] - dot[f] for s, _, f in parts]
        x = cx - sum(widths) / 2
        for (s, color, f), w in zip(parts, widths):
            text.add(s, (x, y), size, color, f, "lm")
            x += w

    # ---------- entry point ----------
    def render(self, view, now):
        flow = view.flow
        self.buttons = []
        draw = {F.WELCOME: self._welcome, F.CAMERA: self._camera,
                F.TUTORIAL: self._tutorial, F.READY: self._ready, F.BACK: self._back}[flow.stage]
        self.text = text = TextLayer()
        img = draw(view, now)
        text.flush(img)
        alpha = flow.alpha(now)
        if alpha < 1.0:
            bg = background()
            img = (bg * (1 - alpha) + img * alpha).astype(np.uint8)
        return img

    # ---------- welcome / welcome back / ready ----------
    def _cat_card(self, rect, key):
        def build(img):
            dome_card(img, WINDOW, rect.y + 250, bulge=50)
            circle(img, (rect.cx, rect.y + 150), 98, HALO, -1)
        return self._base(key, build)

    def _welcome(self, view, now):
        text = self.text
        rect = Rect(164, 120, 440, 540)
        img = self._cat_card(rect, "welcome")
        self._cat(img, rect.cx, rect.y + 262, now)
        self._title(rect.cx, rect.y + 318, [("Welcome to ", theme.TEXT),
                                                  ("Mosign", theme.GREEN, "brand"),
                                                  ("!", theme.TEXT)])
        for i, line in enumerate(wrap_text("Scroll and switch tabs with simple hand gestures, "
                                           "so your hands stay free to cook, type or relax.",
                                           16, rect.w - 90)):
            text.add(line, (rect.cx, rect.y + 364 + i * 24), 16, theme.MUTED, False, "mm")
        self._button(img, text, Rect(rect.cx - 110, rect.y + 450, 220, 54), "flow_next",
                     "Get started", key="Enter")
        return img

    def _ready(self, view, now):
        text = self.text
        rect = Rect(164, 120, 440, 540)
        img = self._cat_card(rect, "ready")
        self._cat(img, rect.cx, rect.y + 262, now)
        self._title(rect.cx, rect.y + 318, [("You're ", theme.TEXT),
                                                  ("ready!", theme.GREEN)])
        for i, line in enumerate(wrap_text("Gestures now control your browser. Click your "
                                           "browser window, then point up or down to scroll.",
                                           16, rect.w - 90)):
            text.add(line, (rect.cx, rect.y + 364 + i * 24), 16, theme.MUTED, False, "mm")
        self._button(img, text, Rect(rect.cx - 110, rect.y + 450, 220, 54), "flow_next",
                     "Start browsing", key="Enter")
        return img

    def _back(self, view, now):
        text = self.text
        rect = Rect(164, 150, 440, 480)
        img = self._cat_card(rect, "back")
        self._cat(img, rect.cx, rect.y + 262, now)
        name = view.flow.name
        parts = [("Welcome back, ", theme.TEXT), (name, theme.GREEN), ("!", theme.TEXT)] \
            if name else [("Welcome back!", theme.TEXT)]
        self._title(rect.cx, rect.y + 330, parts)
        text.add("Your hands are free to go.", (rect.cx, rect.y + 380), 16, theme.MUTED,
                 False, "mm")
        return img

    # ---------- camera ----------
    def _camera(self, view, now):
        text = self.text
        rect = Rect(124, 110, 520, 560)
        img = self._base("camera", lambda im: dome_card(im, WINDOW, rect.y + 70, head=theme.YELLOW, bulge=34))
        text.add("Let Mosign see your hand", (rect.cx, rect.y + 116), 30, theme.TEXT, True, "mm")
        for i, line in enumerate(wrap_text("Video is processed on your device and never recorded "
                                           "or shared. It turns off when you close Mosign.",
                                           14, rect.w - 70)):
            text.add(line, (rect.x + 36, rect.y + 152 + i * 20), 14, theme.MUTED, False, "lm")
        tile = Rect(rect.x + 36, rect.y + 206, rect.w - 72, 240)
        self._camera_tile(img, text, tile, view, now)
        live = view.frame is not None
        label = "Continue" if live else "Allow camera"
        cmd = "flow_next" if live else "swap_camera"
        self._button(img, text, Rect(rect.cx - 110, rect.y + 474, 220, 54), cmd, label)
        return img

    def _camera_tile(self, img, text, tile, view, now, dim_hand=False):
        mask = rounded_mask(tile.w, tile.h, 18)
        block = np.full((S(tile.h), S(tile.w), 3), theme.PANEL_ALT, np.uint8)
        if view.frame is None:
            from mosign.icons import draw_palm_icon
            draw_palm_icon(block, (tile.w / 2, tile.h / 2 - 14), 92)
            text.add("Waiting for your camera", (tile.cx, tile.bottom - 34), 15, theme.MUTED,
                     True, "mm")
        else:
            block, (nw, nh, ox, oy) = cover(view.frame, S(tile.w), S(tile.h))
            if view.hand is not None:
                pts = [(U(x * nw - ox), U(y * nh - oy)) for x, y in view.hand]
                self.ui._draw_hand(block, pts, dim=dim_hand)
        paste(img, block, tile.x, tile.y, mask)
        rounded_rect(img, tile, 18, theme.BORDER, 1)

    # ---------- tutorial ----------
    def _tutorial(self, view, now):
        text = self.text
        tour = view.tour
        rect = Rect(24, 60, 720, 660)
        img = self._base("tutorial", lambda im: dome_card(im, WINDOW, 0, bulge=0, base=TUTORIAL_BG))
        steps = tour.steps
        total = tour.total
        celebrate = tour.done or tour.between_steps(now)
        cur = steps[(tour.index - 1) if celebrate and tour.index > 0 else min(tour.index, total - 1)]

        text.add("Great job!" if celebrate else cur.title, (rect.x + 34, rect.y + 50), 32,
                 theme.TEXT, True, "lm")
        count = tour.index if celebrate else tour.index + 1
        text.add(f"{count}/{total}", (rect.right - 76, rect.y + 52), 20, theme.MUTED, True, "rm")
        self._checkpoints(img, tour, rect.x + 34, rect.y + 100, rect.w - 68)

        right_w, gap = 232, 16
        cam = Rect(rect.x + 28, rect.y + 132, rect.w - 56 - right_w - gap, 360)
        self._camera_tile(img, text, cam, view, now, dim_hand=celebrate)
        if celebrate:
            check_mark(img, (cam.cx, cam.cy), 34)

        panel = Rect(cam.right + gap, cam.y, right_w, cam.h)
        rounded_rect(img, panel, 18, theme.YELLOW_SOFT)
        tray = Rect(rect.x + 28, rect.y + 132 + 360 + 20, rect.w - 56, 110)
        slots = self._slot_rects(tray, total)
        t_pass = tour.since_pass(now) if celebrate else None
        self._gesture(img, text, panel, cur, t_pass, slots[steps.index(cur)])
        text.add(cur.caption, (panel.cx, panel.y + 196 + min(2, len(wrap_text(
            cur.name, 16, panel.w - 28, True))) * 21 + 6), 12, theme.MUTED, False, "mm")
        chip = Rect(panel.x + 18, panel.bottom - 70, panel.w - 36, 54)
        if celebrate:
            rounded_rect(img, chip, 27, theme.GREEN)
            text.add("Correct!", (chip.cx, chip.cy), 16, theme.WHITE, True, "mm")
        else:
            rounded_rect(img, chip, 27, theme.YELLOW)
            label = "Keep holding..." if tour.progress > 0 else "Checking gesture"
            text.add(label, (chip.cx, chip.cy - 9), 15, theme.TEXT, True, "mm")
            progress_bar(img, Rect(chip.x + 24, chip.bottom - 20, chip.w - 48, 9),
                         self._progress(view, tour, cur), fill=theme.GREEN, track=theme.WHITE)

        self._tray(img, text, tour, tray, slots, now)
        return img

    @staticmethod
    def _progress(view, tour, step):
        return tour.progress

    def _checkpoints(self, img, tour, x, cy, width):
        n, r = tour.total, 11
        gap = (width - 2 * r) / max(1, n - 1)
        centers = [(x + r + i * gap, cy) for i in range(n)]
        for i in range(n - 1):
            done = i < tour.index
            draw_line(img, (centers[i][0] + r, cy), (centers[i + 1][0] - r, cy),
                 theme.YELLOW if done else theme.BORDER, 3)
        for i, c in enumerate(centers):
            if i < tour.index or tour.done:
                circle(img, c, r, theme.YELLOW, -1)
                polylines(img, [(c[0] - 5, c[1]), (c[0] - 1, c[1] + 4), (c[0] + 5, c[1] - 4)],
                          False, theme.TEXT, 2)
            else:
                circle(img, c, r, theme.PANEL, -1)
                circle(img, c, r, theme.YELLOW if i == tour.index else theme.BORDER, 2)

    def _gesture(self, img, text, panel, step, t_pass, slot):
        """The hand and its name. When a gesture is passed it flashes (a pulse with a yellow
        glow), then after a short wait flies into its tray slot: the prototype's animation."""
        if t_pass is not None and t_pass >= STEP_PAUSE:
            return          # it has landed: the slot in the tray shows it now
        hand_size = 128
        hand_c = (panel.cx, panel.y + 104)
        lines = wrap_text(step.name, 16, panel.w - 28, True)[:2]
        ys = [panel.y + 196 + i * 21 for i in range(len(lines))]
        c0 = (panel.cx, (hand_c[1] - hand_size / 2 + ys[-1] + 10) / 2)   # middle of hand + name
        scale, center, glow = 1.0, c0, 0.0
        if t_pass is not None:
            if t_pass < FLASH_SECONDS:
                glow = math.sin(math.pi * t_pass / FLASH_SECONDS)
                scale = 1 + 0.1 * glow
            if t_pass >= FLY_DELAY:
                p = ease_fly((t_pass - FLY_DELAY) / FLY_SECONDS)
                center = (c0[0] + (slot.cx - c0[0]) * p, c0[1] + (slot.cy - c0[1]) * p)
                scale = 1 + (LAND_SCALE - 1) * p

        def at(x, y):
            return (center[0] + (x - c0[0]) * scale, center[1] + (y - c0[1]) * scale)

        hc = at(*hand_c)
        if glow > 0:
            self._glow(img, hc, hand_size * scale, step.icon, glow)
        draw_hand_sprite(img, hc, hand_size * scale, step.icon)
        for y, line in zip(ys, lines):
            text.add(line, at(panel.cx, y), 16 * scale, theme.TEXT, True, "mm")

    @staticmethod
    def _glow(img, center, size, label, strength):
        """A soft yellow glow around the hand (the prototype's drop-shadow)."""
        sprite = hand_sprite(label, max(8, S(size)))
        if sprite is None:
            return
        pad = S(24)
        alpha = np.pad(sprite[..., 3], pad).astype(np.float32)
        alpha = cv2.GaussianBlur(cv2.dilate(alpha, np.ones((3, 3), np.uint8), iterations=S(2)),
                                 (0, 0), max(1.0, S(7)))
        layer = np.zeros(alpha.shape + (4,), np.uint8)
        layer[..., :3] = theme.YELLOW
        layer[..., 3] = np.clip(alpha * 1.6 * strength, 0, 255).astype(np.uint8)
        h, w = layer.shape[:2]
        blend_rgba(img, layer, int(round(S(center[0]) - w / 2)), int(round(S(center[1]) - h / 2)))

    @staticmethod
    def _slot_rects(area, n, gap=10):
        w = (area.w - gap * (n - 1)) / n
        return [Rect(int(area.x + i * (w + gap)), area.y, int(w), area.h) for i in range(n)]

    def _tray(self, img, text, tour, area, slots, now):
        """One slot per gesture; each fills in when its hand lands."""
        full = tour.filled(now)
        for i, (step, slot) in enumerate(zip(tour.steps, slots)):
            if i < full:
                rounded_rect(img, slot, 16, theme.PANEL_ALT)
                rounded_rect(img, slot, 16, theme.BORDER, 1)
                draw_hand_sprite(img, (slot.cx, slot.y + 42), 58, step.icon)
                for j, line in enumerate(wrap_text(step.tray, 12, slot.w - 10, True)[:2]):
                    text.add(line, (slot.cx, slot.y + 82 + j * 15), 12, theme.TEXT, True, "mm")
            else:
                rounded_rect(img, slot, 16, theme.bgr("#F3F8F1"))
