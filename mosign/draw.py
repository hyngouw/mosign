"""Small drawing helpers on top of OpenCV, plus Pillow text rendering."""

from collections import namedtuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

from mosign import theme

AA = cv2.LINE_AA


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
    r = Rect(rect.x, rect.y + offset, rect.w, rect.h)
    rounded_rect(mask, r, radius, 255)
    mask = cv2.GaussianBlur(mask, (0, 0), blur).astype(np.float32)[..., None] / 255.0
    a = mask * strength
    img[:] = (img * (1 - a) + np.array(theme.SHADOW, np.float32) * a).astype(np.uint8)


def rounded_mask(w, h, radius):
    """Anti-aliased 0..1 float mask of a rounded rectangle."""
    m = np.zeros((h, w), np.uint8)
    rounded_rect(m, Rect(0, 0, w, h), radius, 255)
    return (m.astype(np.float32) / 255.0)[..., None]


def blend_rect(img, rect, color, alpha):
    x, y, w, h = (int(v) for v in rect)
    roi = img[y:y + h, x:x + w]
    roi[:] = (roi * (1 - alpha) + np.array(color, np.float32) * alpha).astype(np.uint8)


def paste(img, src, x, y, mask=None):
    """Copy `src` into `img` at (x, y), optionally through a 0..1 mask."""
    h, w = src.shape[:2]
    roi = img[y:y + h, x:x + w]
    if mask is None:
        roi[:] = src
    else:
        roi[:] = (src * mask + roi * (1 - mask)).astype(np.uint8)


def progress_bar(img, rect, progress, fill=theme.YELLOW, track=theme.GREEN_SOFT):
    rounded_rect(img, rect, rect.h // 2, track)
    w = int(rect.w * max(0.0, min(1.0, progress)))
    if w >= rect.h:
        rounded_rect(img, Rect(rect.x, rect.y, w, rect.h), rect.h // 2, fill)
    elif w > 0:
        r = (rect.h - 1) // 2
        cv2.circle(img, (rect.x + r, rect.y + r), r, fill, -1, AA)


def ring(img, center, radius, progress, color=theme.YELLOW, track=theme.WHITE, thickness=6):
    c = ipt(center)
    cv2.circle(img, c, int(radius), track, thickness, AA)
    if progress > 0:
        cv2.ellipse(img, c, (int(radius), int(radius)), -90, 0, 360 * min(1.0, progress),
                    color, thickness, AA)


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
        f = theme.font(size, bold)
        left, top, right, bottom = f.getbbox(text)
        return right - left, bottom - top

    def add(self, text, xy, size=16, color=theme.TEXT, bold=False, anchor="la"):
        if text:
            self.items.append((str(text), xy, size, color, bold, anchor))

    def flush(self, img):
        if not self.items:
            return
        pil = Image.fromarray(img)
        d = ImageDraw.Draw(pil)
        for text, (x, y), size, color, bold, anchor in self.items:
            f = theme.font(size, bold)
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
