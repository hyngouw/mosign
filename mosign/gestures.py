"""Pure gesture logic: no camera, no MediaPipe, no OS calls.

Everything here works on a list of 21 hand landmarks given as (x, y) tuples.
x and y must use the same unit (multiply normalized x by the frame's
width/height ratio first), and y grows downward like image coordinates.
That keeps this module easy to unit test with synthetic hands.
"""

import math
from collections import deque

WRIST = 0

# (tip landmark, middle-joint landmark) for each non-thumb finger
FINGERS = {
    "index": (8, 6),
    "middle": (12, 10),
    "ring": (16, 14),
    "pinky": (20, 18),
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def fingers_extended(lm):
    """Return the set of finger names that are held out straight.

    A finger counts as 'up' when its tip is farther from the wrist than its
    middle joint. This works no matter how the hand is rotated.
    """
    wrist = lm[WRIST]
    up = set()
    for name, (tip, joint) in FINGERS.items():
        if dist(wrist, lm[tip]) > dist(wrist, lm[joint]) * 1.05:
            up.add(name)
    # Thumb: when stuck out, its tip is farther from the base of the pinky
    # than the thumb's upper joint is.
    if dist(lm[4], lm[17]) > dist(lm[3], lm[17]) * 1.05:
        up.add("thumb")
    return up


def classify(up):
    if up == {"index"}:
        return "scroll_up"
    if up == {"index", "middle"}:
        return "scroll_down"
    if up == {"thumb", "index", "middle", "ring", "pinky"}:
        return "stop"
    if up == {"index", "middle", "ring"}:
        return "next_tab"
    if up == {"thumb", "pinky"}:
        return "prev_tab"
    return None


def classify_landmarks(lm):
    """Landmarks -> gesture label (or None)."""
    if lm is None:
        return None
    return classify(fingers_extended(lm))


class Stabilizer:
    """Only accept a gesture once it has been seen N frames in a row.

    Until a new label is steady, the previously confirmed label is kept, so a
    single noisy frame never triggers anything.
    """

    def __init__(self, frames):
        self.frames = max(1, int(frames))
        self._history = deque(maxlen=self.frames)
        self.confirmed = None

    def update(self, label):
        self._history.append(label)
        if len(self._history) == self.frames and len(set(self._history)) == 1:
            self.confirmed = label
        return self.confirmed

    def reset(self):
        self._history.clear()
        self.confirmed = None
