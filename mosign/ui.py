"""The Mosign window: camera view, status / tour card and buttons.

Everything is drawn into one numpy image per frame; qt_app.py shows it.
Pip and the gesture menu live in the on-screen overlay (overlay.py).
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from mosign import theme
from mosign.draw import (
    Rect,
    S,
    TextLayer,
    blend_bgra_premultiplied,
    blend_rect,
    blend_rgba,
    card,
    circle,
    corner_size,
    drawing_scale,
    line as draw_line,
    region,
    round_corners,
    save_corners,
    paste,
    progress_bar,
    ring,
    rounded_mask,
    rounded_rect,
    soft_shadow,
    wrap_text,
)
from mosign.gestures import (
    NEXT_TAB,
    PREV_TAB,
    SCROLL_DOWN,
    SCROLL_UP,
    TOGGLE_MENU,
    TOGGLE_TRACKING,
)
from mosign.cat import CatFace, CatSprite
from mosign.screens import FlowScreens
from mosign.tracker import HAND_CONNECTIONS
from mosign.ui_types import Button

WIDTH, HEIGHT = 768, 780
WINDOW_TITLE = "Mosign"

HEADER = Rect(0, 0, WIDTH, 76)
CAMERA = Rect(24, 88, 720, 405)     # 16:9 camera view
STATUS = Rect(24, 509, 720, 182)    # "right now" / tour card
BAR = Rect(24, 707, 720, 56)

CAMERA_LETTERBOX = theme.PANEL_ALT   # mint behind the camera picture
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"
BUTTON_GAP = 12
HEADER_DROP = 6      # centres the header contents between the window top and the camera (y=88)
STATUS_RISE = 18     # status card contents sit this much higher (top gap ≈ side padding)
CAT_HEIGHT_EMPTY = 168


@lru_cache(maxsize=4)
def _logo(height):
    """The cat-face app icon, straight-alpha BGRA, `height` px tall (or None)."""
    img = cv2.imread(str(LOGO_PATH), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    k = height / img.shape[0]
    return cv2.resize(img, (max(1, round(img.shape[1] * k)), height), interpolation=cv2.INTER_AREA)

GESTURE_NAMES = {
    SCROLL_UP: "Pointing up",
    SCROLL_DOWN: "Pointing down",
    PREV_TAB: "Pointing left",
    NEXT_TAB: "Pointing right",
    TOGGLE_TRACKING: "Rock horns",
    TOGGLE_MENU: "Pinky up",
}

EVENT_TEXT = {
    "scroll_up": "Scrolling up",
    "scroll_down": "Scrolling down",
    "prev_tab": "Previous tab",
    "next_tab": "Next tab",
    "sleep": "Tracking paused",
    "wake": "Tracking on",
    "menu_on": "Menu shown",
    "menu_off": "Menu hidden",
}


@dataclass
class View:
    """Everything the window needs to draw one frame."""

    frame: object = None            # mirrored BGR camera frame, or None
    hand: object = None             # 21 normalized (x, y) points, or None
    confirmed: str = None           # steady gesture label
    awake: bool = True
    holding: object = None          # (label, progress) while holding a special gesture
    scroll_mode: str = None
    events: list = field(default_factory=list)
    camera_label: str = "Camera 0"
    fps: float = 0.0
    menu_visible: bool = True
    tour: object = None             # Onboarding while the tour runs / celebrates
    tour_required: bool = False     # first run: the tour can't be skipped
    flow: object = None             # onboarding screens (flow.Flow) instead of the main window


class UI:
    def __init__(self, scale=1.0):
        """`scale`: real pixels per logical pixel (2 on Retina). The picture is drawn
        at that size so text and edges stay sharp; layout and clicks stay logical."""
        self.scale = float(scale)
        self.mouse = (-1, -1)
        self._commands = []
        self._toast = None   # (text, until)
        self._flash = None   # (text, until)
        self.buttons = []
        with drawing_scale(self.scale):
            self._camera_mask = rounded_mask(CAMERA.w, CAMERA.h, 18)
        self._statics = {}
        self._cat = None     # (CatSprite, CatFace): the cat shown when there is no camera picture
        self._screens = None  # FlowScreens, built the first time an onboarding screen shows

    def set_scale(self, scale):
        """Draw at a different size (the window was resized or moved to another screen)."""
        scale = float(scale)
        if abs(scale - self.scale) < 1e-6:
            return
        self.scale = scale
        with drawing_scale(scale):
            self._camera_mask = rounded_mask(CAMERA.w, CAMERA.h, 18)
        self._statics.clear()
        self._cat = None
        self._screens = None

    # ---------- input ----------
    def hover(self, x, y):
        self.mouse = (x, y)

    def click(self, x, y):
        for b in self.buttons:
            if b.rect and b.rect.contains(x, y):
                self._commands.append(b.command)
                return b.command
        return None

    def key(self, text, name=""):
        """A key press. No screen takes typed text any more, so this is always False."""
        return False

    def pop_commands(self):
        cmds, self._commands = self._commands, []
        return cmds

    def toast(self, text, now, seconds=2.5):
        self._toast = (text, now + seconds)

    # ---------- drawing ----------
    def _static(self, view):
        """Background with card shadows. Built once per layout, then copied."""
        key = self._static_key(view)
        if key not in self._statics:
            img = np.full((S(HEIGHT), S(WIDTH), 3), theme.BG, np.uint8)
            cards = self._static_cards(view)
            for rect in cards:
                soft_shadow(img, rect)
            for rect in cards:
                card(img, rect)
            self._statics[key] = img
        return self._statics[key]

    def _static_key(self, view):
        return ()

    def _static_cards(self, view):
        return [CAMERA, STATUS]

    def _layout_buttons(self, view):
        buttons = [
            Button("swap_camera", "Camera", "C"),
            Button("toggle_tracking", "Pause" if view.awake else "Resume", "S"),
            Button("toggle_menu", "Hide menu" if view.menu_visible else "Show menu", "M"),
        ]
        if view.tour is not None and view.tour.step is not None:
            if not view.tour_required:
                buttons.append(Button("tour", "End tour", "O"))
        else:
            buttons.append(Button("tour", "Tour", "O"))
        buttons.append(Button("quit", "Quit", "Q"))
        # equal widths and equal gaps, spread across the whole bar
        n = len(buttons)
        w = (BAR.w - BUTTON_GAP * (n - 1)) / n
        for i, b in enumerate(buttons):
            left = BAR.x + i * (w + BUTTON_GAP)
            b.rect = Rect(int(round(left)), BAR.y + 6, int(round(left + w)) - int(round(left)), 44)
        return buttons

    def render(self, view, now):
        with drawing_scale(self.scale):
            return self._render(view, now)

    def _render(self, view, now):
        if view.flow is not None and not view.flow.finished:
            if self._screens is None:
                self._screens = FlowScreens(self)
            img = self._screens.render(view, now)
            self.buttons = self._screens.buttons
            return img
        img = self._static(view).copy()
        text = TextLayer()

        for event in view.events:
            if event in EVENT_TEXT:
                self._flash = (EVENT_TEXT[event], now + 0.9)
        if self._flash and now > self._flash[1]:
            self._flash = None
        if self._toast and now > self._toast[1]:
            self._toast = None

        self._draw_header(img, text, view)
        self._draw_camera(img, text, view, now)
        self._draw_status(img, text, view)
        self.buttons = self._layout_buttons(view)
        self._draw_buttons(img, text)
        self._draw_extras(img, text, view, now)
        if self._toast:
            self._draw_toast(img, text, self._toast[0])
        text.flush(img)
        return img

    def _draw_extras(self, img, text, view, now):
        """Hook for panels added on top of the base window."""

    def _pill(self, img, text, x, cy, label, fill, border, color, size=15, dot=None, align="l"):
        tw, _ = TextLayer.measure(label, size, True)
        pad = 14
        dot_w = 16 if dot is not None else 0
        w = tw + pad * 2 + dot_w
        h = size + 16
        if align == "r":
            x -= w
        elif align == "m":
            x -= w // 2
        rect = Rect(int(x), int(cy - h // 2), int(w), int(h))
        rounded_rect(img, rect, h // 2, fill)
        if border is not None:
            rounded_rect(img, rect, h // 2, border, 1)
        if dot is not None:
            circle(img, (rect.x + pad + 4, rect.cy), 5, dot, -1)
        text.add(label, (rect.x + pad + dot_w, rect.cy), size, color, True, "lm")
        return rect

    def _draw_header(self, img, text, view):
        logo = Rect(28, 16 + HEADER_DROP, 44, 44)
        rounded_rect(img, logo, 14, theme.YELLOW)
        mark = _logo(S(32))
        if mark is not None:
            blend_rgba(img, mark, S(logo.cx) - mark.shape[1] // 2, S(logo.cy) - mark.shape[0] // 2)
        text.add("Mosign", (84, 38 + HEADER_DROP), 28, theme.GREEN, "brand", "lm")
        tw = TextLayer.measure("Mosign", 28, "brand")[0]
        text.add("hand gesture control", (84 + tw + 12, 40 + HEADER_DROP), 15, theme.MUTED, False, "lm")

        if view.awake:
            r = self._pill(img, text, WIDTH - 24, 38 + HEADER_DROP, "Tracking on", theme.YELLOW, None,
                           theme.TEXT, dot=theme.GREEN, align="r")
        else:
            r = self._pill(img, text, WIDTH - 24, 38 + HEADER_DROP, "Paused", theme.PANEL, theme.BORDER,
                           theme.MUTED, dot=theme.MUTED, align="r")
        self._pill(img, text, r.x - 10, 38 + HEADER_DROP, view.camera_label, theme.PANEL, theme.BORDER,
                   theme.TEXT, dot=theme.GREEN if view.frame is not None else theme.MUTED,
                   align="r")

    def camera_fit(self, frame):
        fh, fw = frame.shape[:2]
        scale = min(CAMERA.w / fw, CAMERA.h / fh)
        nw, nh = max(1, int(fw * scale)), max(1, int(fh * scale))
        if CAMERA.w - nw <= 2:   # avoid 1px slivers from rounding
            nw = CAMERA.w
        if CAMERA.h - nh <= 2:
            nh = CAMERA.h
        return (CAMERA.w - nw) // 2, (CAMERA.h - nh) // 2, nw, nh

    def _draw_empty_cat(self, img, now):
        """The cat sitting in the camera area while there is no picture."""
        if self._cat is None:
            self._cat = (CatSprite(S(CAT_HEIGHT_EMPTY)), CatFace())
        sprite, face = self._cat
        face.update(now, [], None, True)
        ax, ay = sprite.anchor
        blend_bgra_premultiplied(img, sprite.render_bgra(face),
                                 int(S(CAMERA.cx) - ax), int(S(CAMERA.cy + 56) - ay))

    def _draw_camera(self, img, text, view, now):
        cam = region(img, CAMERA)
        r = corner_size(self._camera_mask)
        behind = save_corners(cam, r)       # what the rounded corners must show
        cam[:] = CAMERA_LETTERBOX
        if view.frame is None:
            round_corners(cam, self._camera_mask, r, behind)
            self._draw_empty_cat(img, now)
            text.add("No camera picture", (CAMERA.cx, CAMERA.cy + 96), 24, theme.TEXT, True, "mm")
            text.add("Press C or click Camera to try again",
                     (CAMERA.cx, CAMERA.cy + 128), 16, theme.MUTED, False, "mm")
            return

        ox, oy, nw, nh = self.camera_fit(view.frame)
        sx, sy, sw, sh = S(ox), S(oy), S(nw), S(nh)
        interp = cv2.INTER_AREA if sw < view.frame.shape[1] else cv2.INTER_LINEAR
        pic = cv2.resize(view.frame, (sw, sh), interpolation=interp)
        fit = cam[sy:sy + sh, sx:sx + sw]
        fit[:] = pic[:fit.shape[0], :fit.shape[1]]

        if not view.awake:
            blend_rect(img, CAMERA, theme.BG, 0.55)

        if view.hand is not None:
            # points outside the frame (MediaPipe allows that) are clipped by the slice
            pts = [(ox + x * nw, oy + y * nh) for x, y in view.hand]
            self._draw_hand(cam, pts, dim=not view.awake)
            if view.holding:
                palm = [pts[i] for i in (0, 5, 9, 13, 17)]
                cx = sum(p[0] for p in palm) / 5
                cy = sum(p[1] for p in palm) / 5
                size = np.hypot(pts[0][0] - pts[9][0], pts[0][1] - pts[9][1])
                ring(cam, (cx, cy), max(40, min(110, size * 1.1)), view.holding[1])
        round_corners(cam, self._camera_mask, r, behind)   # round the corners last

        if not view.awake:
            banner = Rect(CAMERA.cx - 210, CAMERA.y + 18, 420, 68)
            card(img, banner, 16, theme.PANEL, theme.YELLOW)
            text.add("Tracking paused", (banner.cx, banner.y + 24), 20, theme.TEXT, True, "mm")
            text.add("Hold rock horns for 1 second to wake up",
                     (banner.cx, banner.y + 48), 15, theme.MUTED, False, "mm")

    def _draw_hand(self, img, pts, dim=False):
        color = theme.GREEN_SOFT if dim else theme.YELLOW
        for a, b in HAND_CONNECTIONS:
            draw_line(img, pts[a], pts[b], theme.GREEN_DARK, 6)
            draw_line(img, pts[a], pts[b], color, 3)
        for p in pts:
            circle(img, p, 6, theme.GREEN_DARK, -1)
            circle(img, p, 4, theme.WHITE, -1)

    def _draw_status(self, img, text, view):
        x, y = STATUS.x + 28, STATUS.y - STATUS_RISE
        if view.confirmed in GESTURE_NAMES:
            title = GESTURE_NAMES[view.confirmed]
        elif view.hand is not None:
            title = "Hand found"
        else:
            title = "No hand in view"
        text.add(title, (x, y + 54), 30, theme.TEXT, True, "lm")

        if self._flash:
            self._pill(img, text, x, y + 98, self._flash[0], theme.YELLOW, None, theme.TEXT, 16)
        elif not view.awake:
            self._pill(img, text, x, y + 98, "Paused", theme.YELLOW_SOFT, theme.YELLOW,
                       theme.YELLOW_DARK, 16)
        elif view.scroll_mode:
            self._pill(img, text, x, y + 98, f"Scrolling {view.scroll_mode}", theme.GREEN,
                       None, theme.WHITE, 16)
        else:
            self._pill(img, text, x, y + 98, "Ready", theme.GREEN_SOFT, None,
                       theme.GREEN_DARK, 16)

        if view.holding:
            if view.holding[0] == TOGGLE_MENU:
                msg = "Keep holding to " + ("hide" if view.menu_visible else "show") + " the menu"
            else:
                msg = "Keep holding to pause tracking" if view.awake else "Keep holding to wake up"
            text.add(msg, (x, y + 136), 15, theme.MUTED, False, "lm")
            progress_bar(img, Rect(x, y + 150, STATUS.w - 56, 10), view.holding[1])
        else:
            tip = ("Click your browser window, then point up/down to scroll, left/right for tabs."
                   if view.awake else "Gestures are ignored until you wake tracking.")
            text.add(tip, (x, y + 142), 15, theme.MUTED, False, "lm")

    def _draw_buttons(self, img, text):
        mx, my = self.mouse
        for b in self.buttons:
            hover = b.rect.contains(mx, my)
            fill = theme.YELLOW if hover else theme.PANEL
            border = theme.YELLOW if hover else theme.BORDER
            rounded_rect(img, b.rect, 22, fill)
            rounded_rect(img, b.rect, 22, border, 1)
            # label and key badge centred together, so equal-width buttons stay balanced
            lw = TextLayer.measure(b.label, 15, True)[0]
            left = b.rect.cx - (lw + 10 + 24) / 2
            text.add(b.label, (left, b.rect.cy), 15, theme.TEXT, True, "lm")
            badge = Rect(int(left + lw + 10), b.rect.cy - 12, 24, 24)
            rounded_rect(img, badge, 7, theme.WHITE if hover else theme.PANEL_ALT)
            text.add(b.key, (badge.cx, badge.cy), 13, theme.GREEN, True, "mm")

    def _draw_toast(self, img, text, label):
        self._pill(img, text, CAMERA.cx, CAMERA.y + 30, label, theme.GREEN_DARK, None,
                   theme.WHITE, 15, align="m")


def render_message(title, body):
    """A plain full-window message, e.g. when the hand model can't be loaded."""
    img = np.full((HEIGHT, WIDTH, 3), theme.BG, np.uint8)
    box = Rect(WIDTH // 2 - 340, HEIGHT // 2 - 130, 680, 260)
    soft_shadow(img, box)
    card(img, box)
    text = TextLayer()
    text.add(title, (box.cx, box.y + 60), 26, theme.TEXT, True, "mm")
    for i, ln in enumerate(wrap_text(body, 16, box.w - 80)[:6]):
        text.add(ln, (box.cx, box.y + 110 + i * 24), 16, theme.MUTED, False, "mm")
    text.add("Press Q to quit", (box.cx, box.bottom - 30), 14, theme.GREEN_DARK, True, "mm")
    text.flush(img)
    return img
