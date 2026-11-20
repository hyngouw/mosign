"""Colors and fonts. Colors are BGR tuples because OpenCV uses BGR."""

from functools import lru_cache

from PIL import ImageFont


def bgr(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


# Light green base, dark green text, yellow accents
BG = bgr("#EAF6E4")           # window background
PANEL = bgr("#FAFDF7")        # cards
PANEL_ALT = bgr("#F1F9EC")    # rows inside cards
BORDER = bgr("#CDE6C3")
GREEN_SOFT = bgr("#D5EFCC")
GREEN = bgr("#5DB36A")
GREEN_DARK = bgr("#2F7D45")
TEXT = bgr("#1F3A2B")         # main text: ~11:1 contrast on BG
MUTED = bgr("#4F6E5A")        # secondary text: ~5:1 contrast on BG
YELLOW = bgr("#F6C945")
YELLOW_SOFT = bgr("#FFF3C4")
YELLOW_DARK = bgr("#8A6A00")  # readable text on yellow-soft
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
