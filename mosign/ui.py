"""The Mosign window: camera view, status / tour card and buttons.

Everything is drawn into one numpy image per frame; qt_app.py shows it.
Pip and the gesture menu live in the on-screen overlay (overlay.py).
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from mosign import theme
from mosign.draw import (
    Rect,
    TextLayer,
    blend_rect,
    card,
    check_mark,
    ipt,
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
from mosign.icons import draw_gesture_icon, draw_hand_icon
from mosign.tracker import HAND_CONNECTIONS

WIDTH, HEIGHT = 768, 780
WINDOW_TITLE = "Mosign"

HEADER = Rect(0, 0, WIDTH, 76)
CAMERA = Rect(24, 88, 720, 405)     # 16:9 camera view
STATUS = Rect(24, 509, 720, 182)    # "right now" / tour card
BAR = Rect(24, 707, 720, 56)

CAMERA_LETTERBOX = theme.bgr("#2C4A36")

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


@dataclass
class Button:
    command: str
    label: str
    key: str
    rect: Rect = None


class UI:
    def __init__(self):
        self.mouse = (-1, -1)
        self._commands = []
        self._toast = None   # (text, until)
        self._flash = None   # (text, until)
        self.buttons = []
        self._camera_mask = rounded_mask(CAMERA.w, CAMERA.h, 18)
        self._statics = {}

    # ---------- input ----------
    def hover(self, x, y):
        self.mouse = (x, y)

    def click(self, x, y):
        for b in self.buttons:
            if b.rect and b.rect.contains(x, y):
                self._commands.append(b.command)
                return b.command
        return None

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
            img = np.full((HEIGHT, WIDTH, 3), theme.BG, np.uint8)
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
        x = BAR.x
        for b in buttons:
            w = TextLayer.measure(b.label, 15, True)[0] + 64
            b.rect = Rect(x, BAR.y + 6, w, 44)
            x += w + 10
        return buttons

    def render(self, view, now):
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
        self._draw_camera(img, text, view)
        if not self._draw_tour(img, text, view, now):
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
            cv2.circle(img, (rect.x + pad + 4, rect.cy), 5, dot, -1, cv2.LINE_AA)
        text.add(label, (rect.x + pad + dot_w, rect.cy), size, color, True, "lm")
        return rect

    def _draw_header(self, img, text, view):
        logo = Rect(28, 18, 40, 40)
        rounded_rect(img, logo, 12, theme.GREEN)
        cv2.circle(img, (logo.right - 9, logo.y + 9), 6, theme.YELLOW, -1, cv2.LINE_AA)
        text.add("m", (logo.cx - 1, logo.cy + 1), 26, theme.WHITE, True, "mm")
        text.add("Mosign", (80, 38), 28, theme.TEXT, True, "lm")
        tw = TextLayer.measure("Mosign", 28, True)[0]
        text.add("hand gesture control", (80 + tw + 12, 40), 15, theme.MUTED, False, "lm")

        if view.awake:
            r = self._pill(img, text, WIDTH - 24, 38, "Tracking on", theme.GREEN_SOFT,
                           theme.GREEN, theme.GREEN_DARK, dot=theme.GREEN, align="r")
        else:
            r = self._pill(img, text, WIDTH - 24, 38, "Paused", theme.YELLOW_SOFT,
                           theme.YELLOW, theme.YELLOW_DARK, dot=theme.YELLOW, align="r")
        self._pill(img, text, r.x - 10, 38, view.camera_label, theme.PANEL,
                   theme.BORDER, theme.MUTED, align="r")

    def camera_fit(self, frame):
        fh, fw = frame.shape[:2]
        scale = min(CAMERA.w / fw, CAMERA.h / fh)
        nw, nh = max(1, int(fw * scale)), max(1, int(fh * scale))
        if CAMERA.w - nw <= 2:   # avoid 1px slivers from rounding
            nw = CAMERA.w
        if CAMERA.h - nh <= 2:
            nh = CAMERA.h
        return (CAMERA.w - nw) // 2, (CAMERA.h - nh) // 2, nw, nh

    def _draw_camera(self, img, text, view):
        if view.frame is None:
            block = np.full((CAMERA.h, CAMERA.w, 3), CAMERA_LETTERBOX, np.uint8)
            paste(img, block, CAMERA.x, CAMERA.y, self._camera_mask)
            text.add("No camera picture", (CAMERA.cx, CAMERA.cy - 16), 24, theme.WHITE, True, "mm")
            text.add("Press C or click Swap camera to try another one",
                     (CAMERA.cx, CAMERA.cy + 18), 16, theme.GREEN_SOFT, False, "mm")
            return

        ox, oy, nw, nh = self.camera_fit(view.frame)
        block = np.full((CAMERA.h, CAMERA.w, 3), CAMERA_LETTERBOX, np.uint8)
        interp = cv2.INTER_AREA if nw < view.frame.shape[1] else cv2.INTER_LINEAR
        block[oy:oy + nh, ox:ox + nw] = cv2.resize(view.frame, (nw, nh), interpolation=interp)
        paste(img, block, CAMERA.x, CAMERA.y, self._camera_mask)

        if not view.awake:
            blend_rect(img, CAMERA, theme.BG, 0.55)

        if view.hand is not None:
            # draw in camera-local coordinates on a view of the camera area, so
            # points outside the frame (MediaPipe allows that) are clipped
            cam = img[CAMERA.y:CAMERA.bottom, CAMERA.x:CAMERA.right]
            pts = [(ox + x * nw, oy + y * nh) for x, y in view.hand]
            self._draw_hand(cam, pts, dim=not view.awake)
            if view.holding:
                palm = [pts[i] for i in (0, 5, 9, 13, 17)]
                cx = sum(p[0] for p in palm) / 5
                cy = sum(p[1] for p in palm) / 5
                size = np.hypot(pts[0][0] - pts[9][0], pts[0][1] - pts[9][1])
                ring(cam, (cx, cy), max(40, min(110, size * 1.1)), view.holding[1])
            # restore the rounded corners the skeleton may have painted over
            corner = (self._camera_mask < 0.999)[..., 0]
            cam[corner] = (cam[corner] * self._camera_mask[corner] +
                           np.array(theme.BG, np.float32) * (1 - self._camera_mask[corner])
                           ).astype(np.uint8)

        if not view.awake:
            banner = Rect(CAMERA.cx - 210, CAMERA.y + 18, 420, 68)
            card(img, banner, 16, theme.PANEL, theme.YELLOW)
            text.add("Tracking paused", (banner.cx, banner.y + 24), 20, theme.TEXT, True, "mm")
            text.add("Hold rock horns for 1 second to wake up",
                     (banner.cx, banner.y + 48), 15, theme.MUTED, False, "mm")

    def _draw_hand(self, img, pts, dim=False):
        line = theme.GREEN_SOFT if dim else theme.YELLOW
        for a, b in HAND_CONNECTIONS:
            cv2.line(img, ipt(pts[a]), ipt(pts[b]), theme.GREEN_DARK, 6, cv2.LINE_AA)
            cv2.line(img, ipt(pts[a]), ipt(pts[b]), line, 3, cv2.LINE_AA)
        for p in pts:
            cv2.circle(img, ipt(p), 6, theme.GREEN_DARK, -1, cv2.LINE_AA)
            cv2.circle(img, ipt(p), 4, theme.WHITE, -1, cv2.LINE_AA)

    def _draw_status(self, img, text, view):
        x, y = STATUS.x + 28, STATUS.y
        text.add("RIGHT NOW", (x, y + 26), 13, theme.MUTED, True, "lm")
        if view.confirmed in GESTURE_NAMES:
            title = GESTURE_NAMES[view.confirmed]
        elif view.hand is not None:
            title = "Hand found"
        else:
            title = "No hand in view"
        text.add(title, (x, y + 64), 30, theme.TEXT, True, "lm")

        if self._flash:
            self._pill(img, text, x, y + 108, self._flash[0], theme.YELLOW, None, theme.TEXT, 16)
        elif not view.awake:
            self._pill(img, text, x, y + 108, "Paused", theme.YELLOW_SOFT, theme.YELLOW,
                       theme.YELLOW_DARK, 16)
        elif view.scroll_mode:
            self._pill(img, text, x, y + 108, f"Scrolling {view.scroll_mode}", theme.GREEN,
                       None, theme.WHITE, 16)
        else:
            self._pill(img, text, x, y + 108, "Ready", theme.GREEN_SOFT, None,
                       theme.GREEN_DARK, 16)

        if view.holding:
            if view.holding[0] == TOGGLE_MENU:
                msg = "Keep holding to " + ("hide" if view.menu_visible else "show") + " the menu"
            else:
                msg = "Keep holding to pause tracking" if view.awake else "Keep holding to wake up"
            text.add(msg, (x, y + 146), 15, theme.MUTED, False, "lm")
            progress_bar(img, Rect(x, y + 160, STATUS.w - 56, 10), view.holding[1])
        else:
            tip = ("Click your browser window, then point up/down to scroll, left/right for tabs."
                   if view.awake else "Gestures are ignored until you wake tracking.")
            text.add(tip, (x, y + 152), 15, theme.MUTED, False, "lm")
        if view.fps:
            text.add(f"{view.fps:.0f} fps", (STATUS.right - 24, y + 26), 13, theme.MUTED,
                     False, "rm")

    def _draw_tour(self, img, text, view, now):
        """Tour card in place of the status card. Returns False if no tour."""
        tour = view.tour
        if tour is None or not (tour.step is not None or tour.celebrating(now)):
            return False
        x, y = STATUS.x, STATUS.y
        icon = Rect(x + 20, y + 20, 142, 142)
        rounded_rect(img, icon, 18, theme.PANEL_ALT)
        tx = icon.right + 22
        wrap_w = STATUS.right - tx - 24

        if tour.done:
            check_mark(img, (icon.cx, icon.cy), 44)
            text.add("QUICK TOUR · COMPLETE", (tx, y + 30), 13, theme.MUTED, True, "lm")
            self._pill(img, text, STATUS.right - 20, y + 30, "Live", theme.GREEN, None,
                       theme.WHITE, 13, align="r")
            title = "You're all set!"
            body = "Gestures now control your browser. Click your browser window and try it."
        elif tour.between_steps(now):
            check_mark(img, (icon.cx, icon.cy), 44)
            text.add(f"QUICK TOUR · STEP {tour.index} OF {tour.total}", (tx, y + 30), 13,
                     theme.MUTED, True, "lm")
            title = "Nice!"
            nxt = tour.text_for(tour.step.title, view.menu_visible, view.awake)
            body = f"Next: {nxt}"
        else:
            step = tour.step
            box = img[icon.y:icon.bottom, icon.x:icon.right]  # clip the demo motion
            if step.icon:
                draw_gesture_icon(box, (icon.w / 2, icon.h / 2), 118, step.icon, now)
            else:
                draw_hand_icon(box, (icon.w / 2, icon.h / 2 + 8), 100,
                               {"thumb", "index", "middle", "ring", "pinky"})
            text.add(f"QUICK TOUR · STEP {tour.index + 1} OF {tour.total}", (tx, y + 30), 13,
                     theme.MUTED, True, "lm")
            self._pill(img, text, STATUS.right - 20, y + 30, "Practice mode", theme.YELLOW_SOFT,
                       theme.YELLOW, theme.YELLOW_DARK, 13, align="r")
            title = tour.text_for(step.title, view.menu_visible, view.awake)
            body = tour.text_for(step.instruction, view.menu_visible, view.awake)
            if step.kind in ("hand", "scroll"):
                progress_bar(img, Rect(tx, y + 132, min(320, wrap_w), 10), tour.progress)

        text.add(title, (tx, y + 64), 24, theme.TEXT, True, "lm")
        for i, line in enumerate(wrap_text(body, 15, wrap_w)[:2]):
            text.add(line, (tx, y + 96 + i * 20), 15, theme.MUTED, False, "lm")

        # progress dots
        for i in range(tour.total):
            c = (tx + 6 + i * 20, y + 158)
            if i < tour.index:
                color = theme.GREEN
            elif i == tour.index and not tour.done:
                color = theme.YELLOW
            else:
                color = theme.BORDER
            cv2.circle(img, c, 6, color, -1, cv2.LINE_AA)
        return True

    def _draw_buttons(self, img, text):
        mx, my = self.mouse
        for b in self.buttons:
            hover = b.rect.contains(mx, my)
            fill = theme.YELLOW_SOFT if hover else theme.PANEL
            border = theme.YELLOW if hover else theme.BORDER
            rounded_rect(img, b.rect, 22, fill)
            rounded_rect(img, b.rect, 22, border, 1)
            text.add(b.label, (b.rect.x + 18, b.rect.cy), 15, theme.TEXT, True, "lm")
            badge = Rect(b.rect.right - 38, b.rect.cy - 12, 24, 24)
            rounded_rect(img, badge, 7, theme.GREEN_SOFT)
            text.add(b.key, (badge.cx, badge.cy), 13, theme.GREEN_DARK, True, "mm")

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
