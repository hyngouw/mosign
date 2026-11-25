"""The corner overlay, top-right of your screen: the gesture menu, a status
pill, and the spot where the cat sits when it isn't on a browser tab (the
cat itself has its own little window, see cat.py and qt_app.py).

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
from mosign.draw import Rect, TextLayer, card, progress_bar, rounded_rect, soft_shadow, wrap_text
from mosign.gestures import (
    NEXT_TAB,
    PREV_TAB,
    SCROLL_DOWN,
    SCROLL_UP,
    TOGGLE_MENU,
    TOGGLE_TRACKING,
)
from mosign.icons import draw_gesture_icon

# Sizes in logical pixels (multiplied by `scale`, e.g. 2 on Retina screens)
WIDTH = 248
HOME_HEIGHT = 140   # top part: the cat's home spot + the status pill
STATUS_Y = 122      # centre of the status pill
HOME_FEET_Y = 100   # where the cat's feet go when it's home
MENU_GAP = 4
MENU_HEADER = 36
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
    (TOGGLE_TRACKING, "Hold rock horns", "Turn tracking off or on"),
    (TOGGLE_MENU, "Hold pinky up", "Hide or show the gesture guide"),
]

MENU_HEIGHT = MENU_HEADER + len(MENU_ROWS) * ROW_HEIGHT + MENU_PAD


def logical_size(menu_visible):
    """(width, height) of the overlay in logical pixels."""
    h = HOME_HEIGHT
    if menu_visible:
        h += MENU_GAP + MENU_HEIGHT + BOTTOM
    return WIDTH, h


# short status shown after a gesture
EVENT_TEXT = {
    "scroll_up": "Scrolling up",
    "scroll_down": "Scrolling down",
    "prev_tab": "Previous tab",
    "next_tab": "Next tab",
    "sleep": "Tracking paused",
    "wake": "Tracking on",
    "menu_on": "Menu shown",
    "menu_off": "Menu hidden",
    "celebrate": "You're all set!",
}
FLASH_SECONDS = 1.2


def home_feet(corner_x, corner_y):
    """Screen point for the cat's feet at home, given the overlay's top-left."""
    return corner_x + WIDTH / 2, corner_y + HOME_FEET_Y


class Overlay:
    def __init__(self, scale=1.0):
        self.scale = float(scale)
        self._shadow_cache = {}
        self._flash = None   # (text, until)

    def size(self, menu_visible):
        """(width, height) in real pixels."""
        w, h = logical_size(menu_visible)
        return int(round(w * self.scale)), int(round(h * self.scale))

    def update(self, view, now):
        """Call once per frame, before render()."""
        for event in view.events:
            if event in EVENT_TEXT:
                self._flash = (EVENT_TEXT[event], now + FLASH_SECONDS)
        if self._flash and now > self._flash[1]:
            self._flash = None

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
        return self._r(SIDE, HOME_HEIGHT + MENU_GAP, WIDTH - 2 * SIDE, MENU_HEIGHT)

    def _draw(self, view, now, background):
        img = self._base(view.menu_visible, background)
        text = TextLayer()
        self._draw_status(img, text, view)
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

    def _draw_status(self, img, text, view):
        """Hold progress, "paused", or what just happened. Nothing when idle."""
        s = self.scale
        cx, cy = WIDTH * s / 2, STATUS_Y * s
        if view.holding:
            label, progress = view.holding
            if label == TOGGLE_MENU:
                msg = "Keep holding: " + ("hide menu" if view.menu_visible else "show menu")
            else:
                msg = "Keep holding: " + ("pause" if view.awake else "wake up")
            pill = self._pill(img, text, cx, cy - 3 * s, msg, theme.YELLOW_SOFT,
                              theme.TEXT, 12, theme.YELLOW)
            bar = Rect(pill.x + self._px(12), pill.bottom + self._px(3),
                       pill.w - self._px(24), self._px(5))
            progress_bar(img, bar, progress)
        elif not view.awake:
            self._pill(img, text, cx, cy, "Paused · hold rock horns", theme.YELLOW_SOFT,
                       theme.TEXT, 12, theme.YELLOW)
        elif self._flash:
            self._pill(img, text, cx, cy, self._flash[0], theme.YELLOW, theme.TEXT, 12)

    def _draw_menu(self, img, text, view, now):
        s = self.scale
        box = self._menu_card()
        # the gesture guide is one butter container with a white row per gesture
        card(img, box, self._px(16), theme.YELLOW_SOFT, theme.BORDER)
        text.add("Gesture guide", (box.x + 14 * s, box.y + 20 * s), self._px(12), theme.TEXT,
                 True, "lm")

        step = view.tour.step if view.tour is not None else None
        for i, (label, title, action) in enumerate(MENU_ROWS):
            row = self._r(SIDE + 8, HOME_HEIGHT + MENU_GAP + MENU_HEADER + i * ROW_HEIGHT,
                          WIDTH - 2 * SIDE - 16, ROW_HEIGHT - 6)
            active = view.confirmed == label and (
                view.awake or label in (TOGGLE_TRACKING, TOGGLE_MENU))
            target = step is not None and step.icon == label
            rounded_rect(img, row, self._px(12), theme.YELLOW if active else theme.PANEL)
            if target and not active:
                rounded_rect(img, row, self._px(12), theme.YELLOW, max(2, self._px(1.5)))
            # every hand sits in its own mint tile, all the same size
            icon = Rect(row.x + self._px(4), row.y + self._px(4),
                        row.h - self._px(8), row.h - self._px(8))
            rounded_rect(img, icon, self._px(10), theme.PANEL_ALT)
            roi = img[icon.y:icon.bottom, icon.x:icon.right]   # clip the demo motion
            draw_gesture_icon(roi, (icon.w / 2, icon.h / 2), icon.h * 1.05, label,
                              now + i * 0.3)
            tx = icon.right + self._px(10)
            size = self._px(12)
            lines = wrap_text(action, size, row.right - tx - self._px(8), True)[:2]
            top = row.cy - (len(lines) - 1) * size * 0.65
            for k, line in enumerate(lines):
                text.add(line, (tx, top + k * size * 1.3), size, theme.TEXT, True, "lm")
