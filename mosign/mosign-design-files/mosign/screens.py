"""The onboarding screens, drawn into the same numpy window as the main UI.

welcome -> sign in -> camera -> tutorial -> ready, plus "welcome back" for
returning users. The tutorial shows the real camera and reacts to the real
gestures: nothing here needs a click once you reach the tutorial.
"""

import cv2
import numpy as np

from mosign import flow as F
from mosign import theme
from mosign.cat import CatFace, CatSprite
from mosign.draw import (
    Rect,
    TextLayer,
    blend_bgra_premultiplied,
    blend_rgba,
    check_mark,
    progress_bar,
    rounded_mask,
    rounded_rect,
    soft_shadow,
    wrap_text,
)
from mosign.icons import draw_hand_sprite
from mosign.ui_types import Button

WIDTH, HEIGHT = 768, 780

SKY_TOP = theme.bgr("#FFF4B8")
SKY_BOTTOM = theme.bgr("#EAF4E7")
HALO = theme.bgr("#FBE98A")        # the pale disc behind the cat
ERROR = theme.bgr("#B3261E")
CAT_HEIGHT = 190


def background():
    t = np.linspace(0, 1, HEIGHT, dtype=np.float32)[:, None, None]
    top = np.array(SKY_TOP, np.float32)
    bottom = np.array(SKY_BOTTOM, np.float32)
    row = top * (1 - t) + bottom * t
    return np.broadcast_to(row, (HEIGHT, WIDTH, 3)).astype(np.uint8).copy()


def dome_card(img, rect, head_h, head=theme.YELLOW, bulge=44, radius=30):
    """White card with a coloured top whose lower edge arches up in the middle."""
    soft_shadow(img, rect, radius, offset=8, blur=18, strength=0.16)
    region = np.full((rect.h, rect.w, 3), 255, np.uint8)
    region[:head_h] = head
    ry = bulge * 3
    cv2.ellipse(region, (rect.w // 2, head_h + ry - bulge), (int(rect.w * 0.62), ry),
                0, 0, 360, theme.WHITE, -1, cv2.LINE_AA)
    region[head_h + 2 * bulge:] = 255
    mask = rounded_mask(rect.w, rect.h, radius)
    roi = img[rect.y:rect.bottom, rect.x:rect.right]
    roi[:] = (region * mask + roi * (1 - mask)).astype(np.uint8)


def cover(frame, w, h):
    """Crop-to-fill resize. Returns the picture and (scaled width, height, crop x, crop y)."""
    fh, fw = frame.shape[:2]
    k = max(w / fw, h / fh)
    nw, nh = max(w, round(fw * k)), max(h, round(fh * k))
    pic = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    ox, oy = (nw - w) // 2, (nh - h) // 2
    return pic[oy:oy + h, ox:ox + w].copy(), (nw, nh, ox, oy)


class FlowScreens:
    def __init__(self, ui):
        self.ui = ui
        self._static = {}
        self._sprite = CatSprite(CAT_HEIGHT)
        self._face = CatFace()
        self.buttons = []
        self._show_password = False

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

    def _close(self, img, rect, command="flow_close"):
        c = (rect.right - 32, rect.y + 32)
        cv2.circle(img, c, 15, theme.bgr("#FFF8D6"), -1, cv2.LINE_AA)
        for dx, dy in ((-1, -1), (-1, 1)):
            cv2.line(img, (c[0] + 5 * dx, c[1] + 5 * dy), (c[0] - 5 * dx, c[1] - 5 * dy),
                     theme.TEXT, 2, cv2.LINE_AA)
        self.buttons.append(Button(command, "Close", "", Rect(c[0] - 18, c[1] - 18, 36, 36)))

    def _cat(self, img, cx, feet_y, now):
        self._face.update(now, [], None, True)
        ax, ay = self._sprite.anchor
        blend_bgra_premultiplied(img, self._sprite.render_bgra(self._face),
                                 int(cx - ax), int(feet_y - ay))

    def _title(self, cx, y, parts, size=32):
        text = self.text
        """Centred title from (string, color) parts, e.g. 'Welcome to ' + green 'Mosign'."""
        widths = [TextLayer.measure(s + ".", size, True)[0] - TextLayer.measure(".", size, True)[0]
                  for s, _ in parts]
        x = cx - sum(widths) / 2
        for (s, color), w in zip(parts, widths):
            text.add(s, (x, y), size, color, True, "lm")
            x += w

    # ---------- entry point ----------
    def render(self, view, now):
        flow = view.flow
        self.buttons = []
        draw = {F.WELCOME: self._welcome, F.LOGIN: self._login, F.CAMERA: self._camera,
                F.TUTORIAL: self._tutorial, F.READY: self._ready, F.BACK: self._back}[flow.stage]
        self.text = text = TextLayer()
        img = draw(view, now)
        text.flush(img)
        if flow.stage == F.BACK:
            alpha = flow.back_alpha(now)
            if alpha < 1.0:
                bg = background()
                img = (bg * (1 - alpha) + img * alpha).astype(np.uint8)
        return img

    # ---------- welcome / welcome back / ready ----------
    def _cat_card(self, rect, key):
        def build(img):
            dome_card(img, rect, 250, bulge=50)
            cv2.circle(img, (rect.cx, rect.y + 150), 98, HALO, -1, cv2.LINE_AA)
        return self._base(key, build)

    def _welcome(self, view, now):
        text = self.text
        rect = Rect(164, 120, 440, 540)
        img = self._cat_card(rect, "welcome")
        self._cat(img, rect.cx, rect.y + 262, now)
        self._close(img, rect)
        self._title(rect.cx, rect.y + 318, [("Welcome to ", theme.TEXT),
                                                  ("Mosign", theme.GREEN)])
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
        self._close(img, rect)
        name = view.flow.name
        parts = [("Welcome back, ", theme.TEXT), (name, theme.GREEN), ("!", theme.TEXT)] \
            if name else [("Welcome back!", theme.TEXT)]
        self._title(rect.cx, rect.y + 330, parts)
        text.add("Your hands are free to go.", (rect.cx, rect.y + 380), 16, theme.MUTED,
                 False, "mm")
        return img

    # ---------- sign in ----------
    def _field(self, img, text, rect, label, value, focused, now, secret=False, command=""):
        rounded_rect(img, rect, 14, theme.PANEL_ALT)
        if focused:
            rounded_rect(img, rect, 14, theme.YELLOW, 2)
        shown = ("•" * len(value)) if secret and not self._show_password else value
        if shown:
            text.add(shown, (rect.x + 18, rect.cy), 16, theme.TEXT, False, "lm")
        else:
            text.add(label, (rect.x + 18, rect.cy), 16, theme.MUTED, False, "lm")
        if focused and int(now * 2) % 2 == 0:
            x = rect.x + 18 + (TextLayer.measure(shown, 16)[0] + 2 if shown else 0)
            cv2.line(img, (x, rect.cy - 10), (x, rect.cy + 10), theme.TEXT, 2)
        self.buttons.append(Button(command, label, "", rect))

    def _login(self, view, now):
        text = self.text
        flow = view.flow
        rect = Rect(164, 70, 440, 640)
        img = self._base("login", lambda im: dome_card(im, rect, 70, bulge=34))
        self._close(img, rect)
        text.add("Log in or Sign up", (rect.cx, rect.y + 116), 30, theme.TEXT, True, "mm")
        x, w = rect.x + 24, rect.w - 48
        self._show_password = flow.show_password
        email = Rect(x, rect.y + 156, w, 52)
        self._field(img, text, email, "Email address", flow.email, flow.focus == "email", now,
                    command="focus_email")
        pw = Rect(x, rect.y + 220, w, 52)
        self._field(img, text, pw, "Password (8+ characters)", flow.password,
                    flow.focus == "password", now, secret=True, command="focus_password")
        text.add("Hide" if flow.show_password else "Show", (pw.right - 20, pw.cy), 13,
                 theme.TEXT, True, "rm")
        self.buttons.append(Button("toggle_password", "Show", "", Rect(pw.right - 70, pw.y, 70, pw.h)))
        if flow.error:
            text.add(flow.error, (x + 4, rect.y + 292), 14, ERROR, True, "lm")
        self._button(img, text, Rect(x, rect.y + 308, w, 52), "login_submit", "Continue")
        text.add("or", (rect.cx, rect.y + 392), 14, theme.MUTED, False, "mm")
        g = Rect(x, rect.y + 416, w, 50)
        self._button(img, text, g, "login_google", "Continue with Google", primary=False)
        gw = TextLayer.measure("Continue with Google", 16, True)[0]
        text.add("G", (g.cx - gw / 2 - 20, g.cy), 19, theme.bgr("#4285F4"), True, "mm")
        a = Rect(x, rect.y + 478, w, 50)
        self._button(img, text, a, "login_apple", "Continue with Apple", primary=False)
        aw = TextLayer.measure("Continue with Apple", 16, True)[0]
        cx, cy = int(a.cx - aw / 2 - 20), a.cy + 1
        cv2.circle(img, (cx - 3, cy + 2), 7, theme.TEXT, -1, cv2.LINE_AA)
        cv2.circle(img, (cx + 4, cy + 2), 7, theme.TEXT, -1, cv2.LINE_AA)
        cv2.ellipse(img, (cx + 3, cy - 8), (5, 2), -35, 0, 360, theme.TEXT, -1, cv2.LINE_AA)
        text.add("Your details stay on this computer.", (rect.cx, rect.y + 580), 13,
                 theme.MUTED, False, "mm")
        return img

    # ---------- camera ----------
    def _camera(self, view, now):
        text = self.text
        rect = Rect(124, 110, 520, 560)
        img = self._base("camera", lambda im: dome_card(im, rect, 70, head=SKY_TOP, bulge=34))
        self._close(img, rect)
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
        block = np.full((tile.h, tile.w, 3), theme.PANEL_ALT, np.uint8)
        if view.frame is None:
            ph = np.array(theme.PANEL_ALT, np.uint8)
            block[:] = ph
            from mosign.icons import draw_palm_icon
            draw_palm_icon(block, (tile.w / 2, tile.h / 2 - 14), 92)
            text.add("Waiting for your camera", (tile.cx, tile.bottom - 34), 15, theme.MUTED,
                     True, "mm")
        else:
            block, (nw, nh, ox, oy) = cover(view.frame, tile.w, tile.h)
            if view.hand is not None:
                pts = [(x * nw - ox, y * nh - oy) for x, y in view.hand]
                self.ui._draw_hand(block, pts, dim=dim_hand)
        roi = img[tile.y:tile.bottom, tile.x:tile.right]
        roi[:] = (block * mask + roi * (1 - mask)).astype(np.uint8)
        rounded_rect(img, tile, 18, theme.BORDER, 1)

    # ---------- tutorial ----------
    def _tutorial(self, view, now):
        text = self.text
        tour = view.tour
        rect = Rect(24, 128, 720, 524)
        img = self._base("tutorial", lambda im: dome_card(im, rect, 0, bulge=0, radius=30))
        steps = tour.steps
        total = tour.total
        celebrate = tour.done or tour.between_steps(now)
        cur = steps[(tour.index - 1) if celebrate and tour.index > 0 else min(tour.index, total - 1)]
        self._close(img, rect)

        text.add("Great job!" if celebrate else cur.title, (rect.x + 34, rect.y + 50), 32,
                 theme.TEXT, True, "lm")
        count = tour.index if celebrate else tour.index + 1
        text.add(f"{count}/{total}", (rect.right - 76, rect.y + 52), 20, theme.MUTED, True, "rm")
        self._checkpoints(img, tour, rect.x + 34, rect.y + 100, rect.w - 68)

        right_w, gap = 232, 16
        cam = Rect(rect.x + 28, rect.y + 132, rect.w - 56 - right_w - gap, 252)
        self._camera_tile(img, text, cam, view, now, dim_hand=celebrate)
        if celebrate:
            check_mark(img, (cam.cx, cam.cy), 34)

        panel = Rect(cam.right + gap, cam.y, right_w, cam.h)
        rounded_rect(img, panel, 18, theme.YELLOW_SOFT)
        box = img[panel.y:panel.bottom, panel.x:panel.right]
        draw_hand_sprite(box, (panel.w / 2, 66), 100, cur.icon)
        lines = wrap_text(cur.name, 16, panel.w - 28, True)[:2]
        for i, line in enumerate(lines):
            text.add(line, (panel.cx, panel.y + 130 + i * 20), 16, theme.TEXT, True, "mm")
        text.add(cur.caption, (panel.cx, panel.y + 130 + len(lines) * 20 + 4), 12, theme.MUTED,
                 False, "mm")
        chip = Rect(panel.x + 22, panel.bottom - 62, panel.w - 44, 44)
        if celebrate:
            rounded_rect(img, chip, 22, theme.GREEN)
            text.add("Correct!", (chip.cx, chip.cy), 16, theme.WHITE, True, "mm")
        else:
            rounded_rect(img, chip, 22, theme.YELLOW)
            text.add("Try it now", (chip.cx, chip.cy - 6), 15, theme.TEXT, True, "mm")
            progress_bar(img, Rect(chip.x + 28, chip.bottom - 12, chip.w - 56, 5),
                         self._progress(view, tour, cur), fill=theme.GREEN, track=theme.WHITE)

        self._tray(img, text, tour, Rect(rect.x + 28, rect.y + 404, rect.w - 56, 96))
        return img

    @staticmethod
    def _progress(view, tour, step):
        if step.kind in ("hand", "scroll"):
            return tour.progress
        if view.holding and view.holding[0] == step.icon:
            return view.holding[1]
        return 1.0 if view.confirmed == step.icon else 0.0

    def _checkpoints(self, img, tour, x, cy, width):
        n, r = tour.total, 11
        gap = (width - 2 * r) / max(1, n - 1)
        centers = [(int(x + r + i * gap), cy) for i in range(n)]
        for i in range(n - 1):
            done = i < tour.index
            cv2.line(img, (centers[i][0] + r, cy), (centers[i + 1][0] - r, cy),
                     theme.YELLOW if done else theme.BORDER, 3, cv2.LINE_AA)
        for i, c in enumerate(centers):
            if i < tour.index or tour.done:
                cv2.circle(img, c, r, theme.YELLOW, -1, cv2.LINE_AA)
                pts = np.array([(c[0] - 5, c[1]), (c[0] - 1, c[1] + 4), (c[0] + 5, c[1] - 4)],
                               np.int32)
                cv2.polylines(img, [pts], False, theme.TEXT, 2, cv2.LINE_AA)
            else:
                cv2.circle(img, c, r, theme.PANEL, -1, cv2.LINE_AA)
                cv2.circle(img, c, r, theme.YELLOW if i == tour.index else theme.BORDER, 2,
                           cv2.LINE_AA)

    def _tray(self, img, text, tour, area):
        """One slot per gesture; each fills in as you learn it."""
        n, gap = tour.total, 10
        w = (area.w - gap * (n - 1)) / n
        for i, step in enumerate(tour.steps):
            slot = Rect(int(area.x + i * (w + gap)), area.y, int(w), area.h)
            if i < tour.index or tour.done:
                rounded_rect(img, slot, 16, theme.PANEL_ALT)
                rounded_rect(img, slot, 16, theme.BORDER, 1)
                draw_hand_sprite(img, (slot.cx, slot.y + 38), 54, step.icon)
                for j, line in enumerate(wrap_text(step.tray, 12, slot.w - 10, True)[:2]):
                    text.add(line, (slot.cx, slot.y + 72 + j * 14), 12, theme.TEXT, True, "mm")
            else:
                rounded_rect(img, slot, 16, theme.bgr("#F3F8F1"))
