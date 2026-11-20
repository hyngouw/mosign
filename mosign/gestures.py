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


# Labels the rest of the app understands
SCROLL_UP = "scroll_up"
SCROLL_DOWN = "scroll_down"
PREV_TAB = "prev_tab"
NEXT_TAB = "next_tab"
TOGGLE_TRACKING = "toggle_tracking"   # the wake / sleep gesture
TOGGLE_MENU = "toggle_menu"           # show / hide the reference menu

# Hold a special gesture this long before it counts.
HOLD_SECONDS = 1.0

# A pointing finger must be at least this long (relative to the palm) to
# count. Shorter means it's aimed at the camera, so the direction is unclear.
MIN_POINT_LENGTH = 0.45


def is_pointing_pose(up):
    """Only the index finger is out. The thumb may be either way."""
    return up - {"thumb"} == {"index"}


def pointing_direction(lm):
    """Which way the index finger points on screen: up/down/left/right/None.

    Uses the line from the index knuckle (5) to the index tip (8). Angles
    near a diagonal return None so the gesture never flickers between two
    directions.
    """
    vx = lm[8][0] - lm[5][0]
    vy = lm[8][1] - lm[5][1]
    palm = dist(lm[WRIST], lm[9]) or 1e-6
    if math.hypot(vx, vy) / palm < MIN_POINT_LENGTH:
        return None
    angle = math.degrees(math.atan2(-vy, vx))  # 0 = right, 90 = up
    if -35 <= angle <= 35:
        return "right"
    if 55 <= angle <= 125:
        return "up"
    if angle >= 145 or angle <= -145:
        return "left"
    if -125 <= angle <= -55:
        return "down"
    return None


_DIRECTION_TO_LABEL = {
    "up": SCROLL_UP,
    "down": SCROLL_DOWN,
    "left": PREV_TAB,    # the camera image is mirrored, so this is YOUR left
    "right": NEXT_TAB,
}


def is_horns_pose(up):
    """"Rock horns": index + pinky out, middle + ring curled, thumb either way.

    Used to wake / sleep tracking because nobody does it by accident.
    """
    return up - {"thumb"} == {"index", "pinky"}


def is_pinky_pose(up):
    """Only the pinky out (thumb either way). Shows / hides the gesture menu."""
    return up - {"thumb"} == {"pinky"}


def classify_landmarks(lm):
    """Landmarks -> gesture label (or None).

    Point your index finger the way you want to go:
    up = scroll up, down = scroll down, left = previous tab, right = next tab.
    Hold "rock horns" to turn tracking on or off.
    Hold up just your pinky to show or hide the gesture menu.
    """
    if lm is None:
        return None
    up = fingers_extended(lm)
    if is_horns_pose(up):
        return TOGGLE_TRACKING
    if is_pinky_pose(up):
        return TOGGLE_MENU
    if is_pointing_pose(up):
        return _DIRECTION_TO_LABEL.get(pointing_direction(lm))
    return None


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


class HoldTrigger:
    """Fires once after a gesture has been held for `seconds`.

    You have to let go before it can fire again, so holding the gesture
    longer never toggles something twice. `progress` (0..1) is for the
    on-screen hold ring.
    """

    def __init__(self, seconds=HOLD_SECONDS):
        self.seconds = seconds
        self.progress = 0.0
        self._start = None
        self._armed = True

    def update(self, active, now):
        if not active:
            self._start = None
            self._armed = True
            self.progress = 0.0
            return False
        if self._start is None:
            self._start = now
        self.progress = min(1.0, (now - self._start) / self.seconds) if self.seconds > 0 else 1.0
        if self.progress >= 1.0 and self._armed:
            self._armed = False
            return True
        return False
