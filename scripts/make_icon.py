"""Draw the app icon (the cat face on a yellow tile) as a 1024x1024 PNG, plus a Windows .ico.

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

SIZE = 1024


def render_icon(size=SIZE):
    """The cat face on a yellow rounded tile: the same icon as the window header."""
    big = size * 2   # draw at 2x and shrink for smooth edges
    rgb = np.zeros((big, big, 3), np.uint8)
    alpha = np.zeros((big, big), np.uint8)
    tile = Rect(int(big * 0.09), int(big * 0.09), int(big * 0.82), int(big * 0.82))
    rounded_rect(alpha, tile, int(big * 0.22), 255)
    rounded_rect(rgb, tile, int(big * 0.22), theme.YELLOW)
    face = cv2.imread(str(ROOT / "mosign" / "assets" / "logo.png"), cv2.IMREAD_UNCHANGED)
    k = tile.h * 0.73 / face.shape[0]
    face = cv2.resize(face, (round(face.shape[1] * k), round(face.shape[0] * k)),
                      interpolation=cv2.INTER_AREA)
    x0, y0 = tile.x + (tile.w - face.shape[1]) // 2, tile.y + (tile.h - face.shape[0]) // 2
    a = face[..., 3:4].astype(np.float32) / 255
    roi = rgb[y0:y0 + face.shape[0], x0:x0 + face.shape[1]].astype(np.float32)
    rgb[y0:y0 + face.shape[0], x0:x0 + face.shape[1]] = (face[..., :3] * a + roi * (1 - a)).astype(np.uint8)
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
    img.resize((512, 512), Image.LANCZOS).save(ROOT / "mosign" / "assets" / "app_icon.png")
    ico = out / "icon.ico"
    img.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png, ico


if __name__ == "__main__":
    for p in main(sys.argv[1] if len(sys.argv) > 1 else None):
        print(p)
