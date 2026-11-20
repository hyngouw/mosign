"""Draw the app icon (Pip on a green tile) as a 1024x1024 PNG, plus a Windows .ico.

    python scripts/make_icon.py [output_folder]
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mosign import theme  # noqa: E402
from mosign.draw import Rect, rounded_rect  # noqa: E402
from mosign.penguin import Penguin  # noqa: E402

SIZE = 1024


def render_icon(size=SIZE):
    # draw at 2x and shrink for smooth edges
    big = size * 2
    rgb = np.zeros((big, big, 3), np.uint8)
    alpha = np.zeros((big, big), np.uint8)
    tile = Rect(int(big * 0.09), int(big * 0.09), int(big * 0.82), int(big * 0.82))
    rounded_rect(alpha, tile, int(big * 0.18), 255)
    rounded_rect(rgb, tile, int(big * 0.18), theme.GREEN_SOFT)
    cv2.circle(rgb, (tile.right - int(big * 0.17), tile.y + int(big * 0.17)), int(big * 0.07),
               theme.YELLOW, -1, cv2.LINE_AA)
    pip = Penguin()
    pip.update(0.0)
    pip.draw(rgb, (big / 2, tile.bottom - big * 0.17), scale=big / 300)
    bgra = np.dstack([rgb, alpha])
    small = cv2.resize(bgra, (size, size), interpolation=cv2.INTER_AREA)
    rgba = cv2.cvtColor(small, cv2.COLOR_BGRA2RGBA)
    return Image.fromarray(rgba, "RGBA")


def main(out=None):
    out = Path(out or ROOT / "packaging")
    out.mkdir(parents=True, exist_ok=True)
    img = render_icon()
    png = out / "icon.png"
    img.save(png)
    ico = out / "icon.ico"
    img.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png, ico


if __name__ == "__main__":
    for p in main(sys.argv[1] if len(sys.argv) > 1 else None):
        print(p)
