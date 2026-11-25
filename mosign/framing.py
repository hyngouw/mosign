"""Make a picture fill a window of any size and shape (no Qt, so it can be tested)."""

import cv2


def fit_picture(img, pw, ph, aspect):
    """Return an image exactly `pw` x `ph` pixels.

    `img` (width / height = `aspect`) keeps its proportions and sits in the middle,
    as large as fits. The rest of the window is filled by continuing the picture's own
    edge colours outwards, so there are never white bars. Returns (image, (x, y, w, h))
    where the rectangle is where the original picture ended up.
    """
    pw, ph = max(1, int(pw)), max(1, int(ph))
    if pw / ph > aspect:
        th, tw = ph, max(1, round(ph * aspect))
    else:
        tw, th = pw, max(1, round(pw / aspect))
    if (img.shape[1], img.shape[0]) != (tw, th):
        shrink = tw < img.shape[1]
        img = cv2.resize(img, (tw, th),
                         interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LINEAR)
    ox, oy = (pw - tw) // 2, (ph - th) // 2
    out = cv2.copyMakeBorder(img, oy, ph - th - oy, ox, pw - tw - ox, cv2.BORDER_REPLICATE)
    return out, (ox, oy, tw, th)
