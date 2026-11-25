"""Small drawing helpers on top of OpenCV, plus Pillow text rendering."""

from collections import namedtuple
from contextlib import contextmanager
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw

from mosign import theme

AA = cv2.LINE_AA

# Everything is laid out in "logical" pixels. While `drawing_scale(k)` is active the
# helpers below multiply positions, sizes and line widths by k, so the main window can
# be drawn at the screen's real pixel density (k = 2 on Retina) and stay sharp.
_K = [1.0]


@contextmanager
def drawing_scale(k):
    old = _K[0]
    _K[0] = float(k)
    try:
        yield
    finally:
        _K[0] = old


def S(v):
    """A logical length in real pixels."""
    return int(round(v * _K[0]))


def U(v):
    """Real pixels back to logical length."""
    return v / _K[0]


def _sp(p):
    return (S(p[0]), S(p[1]))


def _srect(rect):
    x, y, w, h = rect
    return Rect(S(x), S(y), max(1, S(w)), max(1, S(h)))


def _sthick(t):
    return t if t < 0 else max(1, S(t))


def circle(img, center, radius, color, thickness=-1):
    cv2.circle(img, _sp(center), max(1, S(radius)), color, _sthick(thickness), AA)


def line(img, p1, p2, color, thickness=1):
    cv2.line(img, _sp(p1), _sp(p2), color, _sthick(thickness), AA)


def ellipse(img, center, axes, angle, start, end, color, thickness=-1):
    cv2.ellipse(img, _sp(center), (max(1, S(axes[0])), max(1, S(axes[1]))), angle, start, end,
                color, _sthick(thickness), AA)


def polylines(img, pts, closed, color, thickness=1):
    cv2.polylines(img, [np.array([_sp(p) for p in pts], np.int32)], closed, color,
                  _sthick(thickness), AA)


def region(img, rect):
    """A view of `img` covering a logical rectangle."""
    r = _srect(rect)
    return img[r.y:r.y + r.h, r.x:r.x + r.w]


class Rect(namedtuple("Rect", "x y w h")):
    def contains(self, px, py):
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    def inset(self, dx, dy=None):
        dy = dx if dy is None else dy
        return Rect(self.x + dx, self.y + dy, self.w - 2 * dx, self.h - 2 * dy)


def ipt(p):
    return (int(round(p[0])), int(round(p[1])))


def rounded_rect(img, rect, radius, color, thickness=-1):
    if _K[0] != 1.0:
        rect, radius, thickness = _srect(rect), S(radius), _sthick(thickness)
    _rounded_rect_px(img, rect, radius, color, thickness)


def _rounded_rect_px(img, rect, radius, color, thickness=-1):
    x, y, w, h = (int(v) for v in rect)
    if w <= 0 or h <= 0:
        return
    r = int(max(0, min(radius, (w - 1) // 2, (h - 1) // 2)))
    x2, y2 = x + w - 1, y + h - 1
    if thickness < 0:
        cv2.rectangle(img, (x + r, y), (x2 - r, y2), color, -1)
        cv2.rectangle(img, (x, y + r), (x2, y2 - r), color, -1)
        if r:
            for c in ((x + r, y + r), (x2 - r, y + r), (x + r, y2 - r), (x2 - r, y2 - r)):
                cv2.circle(img, c, r, color, -1, AA)
        return
    t = thickness
    cv2.line(img, (x + r, y), (x2 - r, y), color, t, AA)
    cv2.line(img, (x + r, y2), (x2 - r, y2), color, t, AA)
    cv2.line(img, (x, y + r), (x, y2 - r), color, t, AA)
    cv2.line(img, (x2, y + r), (x2, y2 - r), color, t, AA)
    if r:
        cv2.ellipse(img, (x + r, y + r), (r, r), 180, 0, 90, color, t, AA)
        cv2.ellipse(img, (x2 - r, y + r), (r, r), 270, 0, 90, color, t, AA)
        cv2.ellipse(img, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, t, AA)
        cv2.ellipse(img, (x + r, y2 - r), (r, r), 90, 0, 90, color, t, AA)


def card(img, rect, radius=18, fill=theme.PANEL, border=theme.BORDER):
    rounded_rect(img, rect, radius, fill)
    if border is not None:
        rounded_rect(img, rect, radius, border, 1)


def soft_shadow(img, rect, radius=18, offset=4, blur=10, strength=0.12):
    """Blurred shadow under a card. Slow-ish: use for static layers only."""
    mask = np.zeros(img.shape[:2], np.uint8)
    r = _srect(Rect(rect.x, rect.y + offset, rect.w, rect.h))
    _rounded_rect_px(mask, r, S(radius), 255)
    mask = cv2.GaussianBlur(mask, (0, 0), max(0.5, blur * _K[0])).astype(np.float32)[..., None] / 255.0
    a = mask * strength
    img[:] = (img * (1 - a) + np.array(theme.SHADOW, np.float32) * a).astype(np.uint8)


def rounded_mask(w, h, radius):
    """Anti-aliased 0..1 float mask of a rounded rectangle."""
    w, h = max(1, S(w)), max(1, S(h))
    m = np.zeros((h, w), np.uint8)
    _rounded_rect_px(m, Rect(0, 0, w, h), S(radius), 255)
    return (m.astype(np.float32) / 255.0)[..., None]


def blend_rect(img, rect, color, alpha):
    x, y, w, h = _srect(rect)
    roi = img[y:y + h, x:x + w]
    roi[:] = (roi * (1 - alpha) + np.array(color, np.float32) * alpha).astype(np.uint8)


def corner_size(mask):
    """How big the rounded corners of a 0..1 mask are (a square this many pixels wide)."""
    r = int(np.argmax(mask[:, 0, 0] > 0.999)) + 1
    return max(1, min(r, mask.shape[0] // 2, mask.shape[1] // 2))


def _corner_slices(r):
    return [(slice(0, r), slice(0, r)), (slice(0, r), slice(-r, None)),
            (slice(-r, None), slice(0, r)), (slice(-r, None), slice(-r, None))]


def save_corners(roi, r):
    return [roi[ys, xs].copy() for ys, xs in _corner_slices(r)]


def round_corners(roi, mask, r, saved):
    """Blend the four corners of `roi` back towards what was there before (`saved`),
    following the rounded-rectangle `mask`. Only the corners need blending: it is
    much cheaper than blending a whole camera picture."""
    for (ys, xs), before in zip(_corner_slices(r), saved):
        m = mask[ys, xs]
        roi[ys, xs] = (roi[ys, xs] * m + before * (1 - m)).astype(np.uint8)


def paste(img, src, x, y, mask=None):
    """Copy `src` into `img` at (x, y), optionally through a 0..1 rounded-rectangle mask."""
    h, w = src.shape[:2]
    x, y = S(x), S(y)
    roi = img[y:y + h, x:x + w]
    if mask is None:
        roi[:] = src
        return
    r = corner_size(mask)
    saved = save_corners(roi, r)
    roi[:] = src
    round_corners(roi, mask, r, saved)


def progress_bar(img, rect, progress, fill=theme.YELLOW, track=theme.GREEN_SOFT):
    rounded_rect(img, rect, rect.h // 2, track)
    w = int(rect.w * max(0.0, min(1.0, progress)))
    if w >= rect.h:
        rounded_rect(img, Rect(rect.x, rect.y, w, rect.h), rect.h // 2, fill)
    elif w > 0:
        r = (rect.h - 1) / 2
        circle(img, (rect.x + r, rect.y + r), r, fill, -1)


def ring(img, center, radius, progress, color=theme.YELLOW, track=theme.WHITE, thickness=6):
    circle(img, center, radius, track, thickness)
    if progress > 0:
        ellipse(img, center, (radius, radius), -90, 0, 360 * min(1.0, progress), color, thickness)


def wrap_text(text, size, width, bold=False):
    """Split text into lines that fit `width` pixels."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and TextLayer.measure(trial, size, bold)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def check_mark(img, center, radius, color=theme.GREEN, mark=theme.WHITE):
    cx, cy = center
    circle(img, center, radius, color, -1)
    r = radius
    polylines(img, [(cx - 0.45 * r, cy + 0.02 * r), (cx - 0.12 * r, cy + 0.35 * r),
                    (cx + 0.5 * r, cy - 0.3 * r)], False, mark, max(3, r * 0.18))


@lru_cache(maxsize=2048)
def _text_box(text, px_size, bold):
    left, top, right, bottom = theme.font(px_size, bold).getbbox(text)
    return right - left, bottom - top


class TextLayer:
    """Collects text for one frame, then draws it all in one Pillow pass.

    Anchors: first letter l/m/r (left/middle/right), second a/m/s
    (top/middle/baseline). Colors are BGR like everything else: the image is
    handed to Pillow as-is, so channel order stays consistent.
    """

    def __init__(self):
        self.items = []

    @staticmethod
    def measure(text, size=16, bold=False):
        """Text size in logical pixels (measured at the real size, so it matches what is drawn)."""
        k = _K[0]
        width, height = _text_box(text, max(1, S(size)), bold)
        return width / k, height / k

    def add(self, text, xy, size=16, color=theme.TEXT, bold=False, anchor="la"):
        if text:
            self.items.append((str(text), xy, size, color, bold, anchor))

    def flush(self, img):
        if not self.items:
            return
        pil = Image.fromarray(img)
        d = ImageDraw.Draw(pil)
        for text, (x, y), size, color, bold, anchor in self.items:
            f = theme.font(max(1, S(size)), bold)
            x, y = x * _K[0], y * _K[0]
            left, top, right, bottom = f.getbbox(text)
            h_anchor, v_anchor = anchor[0], anchor[1]
            if h_anchor == "m":
                x -= (left + right) / 2
            elif h_anchor == "r":
                x -= right
            else:
                x -= left
            if v_anchor == "m":
                y -= (top + bottom) / 2
            elif v_anchor == "s":
                try:
                    y -= f.getmetrics()[0]
                except AttributeError:
                    y -= bottom
            else:
                y -= top
            d.text((x, y), text, font=f, fill=tuple(int(c) for c in color))
        img[:] = np.asarray(pil)
        self.items = []


def blend_rgba(img, rgba, x, y):
    """Alpha-blend a straight-alpha BGRA image onto `img` at (x, y), clipped to `img`."""
    h, w = rgba.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.shape[1], x + w), min(img.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    src = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = src[..., 3:4] / 255.0
    roi = img[y0:y1, x0:x1].astype(np.float32)
    img[y0:y1, x0:x1] = (src[..., :3] * a + roi * (1 - a)).astype(np.uint8)


def blend_bgra_premultiplied(img, bgra, x, y):
    """Same, for the premultiplied BGRA the cat sprite produces."""
    h, w = bgra.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.shape[1], x + w), min(img.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    src = bgra[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = src[..., 3:4] / 255.0
    roi = img[y0:y1, x0:x1].astype(np.float32)
    img[y0:y1, x0:x1] = (src[..., :3] + roi * (1 - a)).clip(0, 255).astype(np.uint8)
