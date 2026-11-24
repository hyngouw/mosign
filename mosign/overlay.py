"""The on-screen overlay: Pip and the gesture menu, top-right of your screen.

This is drawn into a BGRA image with real transparency, so it can float over
the browser in a frameless, click-through window (see qt_app.py).

How the transparency works: everything is drawn twice, once on black and once
on white. Where a pixel is fully see-through the two differ by 255, where it
is solid they are equal, and anti-aliased edges, text and shadows land
in between. That gives exact alpha for anything the normal drawing code can
draw, without needing alpha-aware versions of every helper.
"""

import numpy as np

from mosign import theme
from mosign.draw import Rect, TextLayer, card, progress_bar, rounded_rect, soft_shadow
from mosign.gestures import (
    NEXT_TAB,
    PREV_TAB,
    SCROLL_DOWN,
    SCROLL_UP,
    TOGGLE_MENU,
    TOGGLE_TRACKING,
)
from mosign.icons import draw_gesture_icon
from mosign.penguin import Penguin

# Sizes in logical pixels (multiplied by `scale`, e.g. 2 on Retina screens)
WIDTH = 248
PIP_HEIGHT = 204
MENU_GAP = 4
MENU_HEADER = 44
ROW_HEIGHT = 50
MENU_PAD = 8
SIDE = 8            # room for the card shadow
BOTTOM = 16
MARGIN = 12         # distance from the screen corner (used by the window)

# (gesture label, title, what it does)
MENU_ROWS = [
    (SCROLL_UP, "Point up", "Scroll up"),
    (SCROLL_DOWN, "Point down", "Scroll down"),
    (PREV_TAB, "Point left", "Previous tab"),
    (NEXT_TAB, "Point right", "Next tab"),
    (TOGGLE_TRACKING, "Hold rock horns", "Pause / resume tracking"),
    (TOGGLE_MENU, "Hold pinky up", "Hide / show this menu"),
]

MENU_HEIGHT = MENU_HEADER + len(MENU_ROWS) * ROW_HEIGHT + MENU_PAD


def logical_size(menu_visible):
    """(width, height) of the overlay in logical pixels."""
    h = PIP_HEIGHT
    if menu_visible:
        h += MENU_GAP + MENU_HEIGHT + BOTTOM
    return WIDTH, h


class Overlay:
    def __init__(self, scale=1.0):
        self.scale = float(scale)
        self.penguin = Penguin(max_x=34, max_y=38)
        self._shadow_cache = {}

    def size(self, menu_visible):
        """(width, height) in real pixels."""
        w, h = logical_size(menu_visible)
        return int(round(w * self.scale)), int(round(h * self.scale))

    def update(self, view, now):
        """Advance Pip. Call once per frame, before render()."""
        self.penguin.update(now, view.events, view.scroll_mode, view.awake)

    def render(self, view, now):
        """BGRA image, premultiplied alpha (what Qt's ARGB32_Premultiplied wants)."""
        on_black = self._draw(view, now, 0)
        on_white = self._draw(view, now, 255)
        diff = on_white.astype(np.int16) - on_black.astype(np.int16)
        alpha = np.clip(255 - diff.mean(axis=2), 0, 255).astype(np.uint8)
        color = np.minimum(on_black, alpha[..., None])  # premultiplied: color <= alpha
        return np.dstack([color, alpha])

    # ---------- drawing ----------
    def _r(self, x, y, w, h):
        s = self.scale
        return Rect(int(round(x * s)), int(round(y * s)), int(round(w * s)), int(round(h * s)))

    def _px(self, v):
        return int(round(v * self.scale))

    def _menu_card(self):
        return self._r(SIDE, PIP_HEIGHT + MENU_GAP, WIDTH - 2 * SIDE, MENU_HEIGHT)

    def _draw(self, view, now, background):
        img = self._base(view.menu_visible, background)
        text = TextLayer()
        self._draw_pip(img, text, view)
        if view.menu_visible:
            self._draw_menu(img, text, view, now)
        text.flush(img)
        return img

    def _base(self, menu_visible, background):
        """Empty overlay, with the menu card's shadow already in place."""
        w, h = self.size(menu_visible)
        key = (menu_visible, background, w, h)
        if key not in self._shadow_cache:  # blurring is slow-ish, so cache it
            img = np.full((h, w, 3), background, np.uint8)
            if menu_visible:
                soft_shadow(img, self._menu_card(), self._px(16), offset=self._px(3),
                            blur=self._px(7), strength=0.18)
            self._shadow_cache[key] = img
        return self._shadow_cache[key].copy()

    def _pill(self, img, text, cx, cy, label, fill, color, size, border=None):
        s = self.scale
        fs = self._px(size)
        tw, _ = TextLayer.measure(label, fs, True)
        pw, ph = tw + 24 * s, fs + 14 * s
        rect = Rect(int(cx - pw / 2), int(cy - ph / 2), int(pw), int(ph))
        rounded_rect(img, rect, rect.h // 2, fill)
        if border is not None:
            rounded_rect(img, rect, rect.h // 2, border, max(1, int(s)))
        text.add(label, (rect.cx, rect.cy), fs, color, True, "mm")
        return rect

    def _draw_pip(self, img, text, view):
        s = self.scale
        stage = self._r(0, 0, WIDTH, PIP_HEIGHT - 34)
        roi = img[stage.y:stage.bottom, stage.x:stage.right]   # keep Pip inside its area
        feet = (stage.w / 2, stage.h - 16 * s)
        pip_scale = 0.6 * s
        self.penguin.draw_motion_hints(roi, feet, pip_scale)
        self.penguin.draw(roi, feet, pip_scale)
        for z, (zx, zy), size in self.penguin.zzz(feet, pip_scale):
            text.add(z, (stage.x + zx, stage.y + zy), max(8, size), theme.MUTED, True, "mm")

        cy = (PIP_HEIGHT - 24) * s
        if view.holding:
            label, progress = view.holding
            if label == TOGGLE_MENU:
                msg = "Keep holding: " + ("hide menu" if view.menu_visible else "show menu")
            else:
                msg = "Keep holding: " + ("pause" if view.awake else "wake up")
            pill = self._pill(img, text, WIDTH * s / 2, cy, msg, theme.YELLOW_SOFT,
                              theme.TEXT, 12, theme.YELLOW)
            bar = Rect(pill.x + self._px(12), pill.bottom + self._px(4),
                       pill.w - self._px(24), self._px(5))
            progress_bar(img, bar, progress)
        else:
            mood = self.penguin.mood
            if not view.awake:
                fill, border = theme.YELLOW_SOFT, theme.YELLOW
            elif mood != "idle":
                fill, border = theme.YELLOW, None
            else:
                fill, border = theme.PANEL, theme.BORDER
            caption = self.penguin.caption
            if not view.awake:
                caption = "Paused · hold rock horns"
            self._pill(img, text, WIDTH * s / 2, cy, caption, fill, theme.TEXT, 12, border)

    def _draw_menu(self, img, text, view, now):
        s = self.scale
        box = self._menu_card()
        card(img, box, self._px(16), theme.PANEL, theme.BORDER)

        text.add("Gestures", (box.x + 14 * s, box.y + 23 * s), self._px(16), theme.TEXT, True,
                 "lm")
        text.add("hold pinky to hide", (box.right - 14 * s, box.y + 24 * s), self._px(11),
                 theme.MUTED, False, "rm")

        step = view.tour.step if view.tour is not None else None
        for i, (label, title, action) in enumerate(MENU_ROWS):
            row = self._r(SIDE + 8, PIP_HEIGHT + MENU_GAP + MENU_HEADER + i * ROW_HEIGHT,
                          WIDTH - 2 * SIDE - 16, ROW_HEIGHT - 6)
            active = view.confirmed == label and (
                view.awake or label in (TOGGLE_TRACKING, TOGGLE_MENU))
            target = step is not None and step.icon == label
            rounded_rect(img, row, self._px(12), theme.YELLOW_SOFT if active else theme.PANEL_ALT)
            if active or target:
                rounded_rect(img, row, self._px(12), theme.YELLOW, max(2, self._px(1.5)))
            icon = Rect(row.x + self._px(4), row.y + self._px(4),
                        row.h - self._px(8), row.h - self._px(8))
            rounded_rect(img, icon, self._px(9), theme.PANEL)
            roi = img[icon.y:icon.bottom, icon.x:icon.right]   # clip the demo motion
            draw_gesture_icon(roi, (icon.w / 2, icon.h / 2), icon.h * 0.84, label,
                              now + i * 0.3)
            tx = icon.right + self._px(10)
            text.add(title, (tx, row.cy - 8 * s), self._px(13), theme.TEXT, True, "lm")
            text.add(action, (tx, row.cy + 9 * s), self._px(11.5), theme.MUTED, False, "lm")
