"""Colors and fonts. Colors are BGR tuples because OpenCV uses BGR."""

from functools import lru_cache

from PIL import ImageFont


def bgr(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


# Mosign design system: butter-yellow window, white cards, mint tiles,
# brand yellow (#F6DE5E) and green (#2C9E36), dark green text.
BG = bgr("#FFF4B8")           # window background (butter)
PANEL = bgr("#FFFFFF")        # cards
PANEL_ALT = bgr("#EAF4E7")    # mint: tiles and rows inside cards
BORDER = bgr("#D3E3CF")
GREEN_SOFT = bgr("#DDEFD8")
GREEN = bgr("#2C9E36")
GREEN_DARK = bgr("#1F6F2B")
TEXT = bgr("#1F3D23")         # main text: ~10:1 contrast on BG
MUTED = bgr("#5D7260")        # secondary text: ~4.6:1 contrast on BG
YELLOW = bgr("#F6DE5E")       # the app icon's yellow
YELLOW_HOVER = bgr("#EBCB3A")  # primary button under the mouse
YELLOW_SOFT = bgr("#FFF4B8")
YELLOW_DARK = bgr("#6B5600")  # readable text on yellow-soft
WHITE = (255, 255, 255)
SHADOW = bgr("#2F5A3A")

_BOLD_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",   # macOS
    "/Library/Fonts/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/seguisb.ttf",                                # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",        # Linux
]
_REGULAR_FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


@lru_cache(maxsize=64)
def font(size, bold=False):
    for path in _BOLD_FONTS if bold else _REGULAR_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()
