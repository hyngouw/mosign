"""Hand tracking with MediaPipe.

MediaPipe has two Python APIs:

* the old ``mp.solutions.hands`` API (MediaPipe 0.10.14 and earlier-ish), and
* the newer Tasks API (``HandLandmarker``), which is the only one left in
  current releases such as 0.10.3x and 1.x.

HandTracker uses whichever one is installed. The Tasks API needs a model
file (hand_landmarker.task). It is looked for next to the app first, and
downloaded once to ~/.mosign/models if it is missing.
"""

import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

MODEL_NAME = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# The 21-point hand skeleton, for drawing.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]


class ModelNotFoundError(RuntimeError):
    pass


def app_home():
    """Folder for settings and downloaded models (override with MOSIGN_HOME)."""
    return Path(os.environ.get("MOSIGN_HOME", Path.home() / ".mosign"))


def model_candidates():
    """Places a hand_landmarker.task file may live, in priority order."""
    paths = []
    bundle_dir = getattr(sys, "_MEIPASS", None)  # inside a PyInstaller app
    if bundle_dir:
        paths.append(Path(bundle_dir) / "models" / MODEL_NAME)
    paths.append(Path(__file__).resolve().parent.parent / "models" / MODEL_NAME)
    paths.append(app_home() / "models" / MODEL_NAME)
    return paths


def find_model():
    for path in model_candidates():
        if path.is_file():
            return path
    return None


def download_model(dest=None, url=MODEL_URL):
    dest = Path(dest) if dest else app_home() / "models" / MODEL_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    print(f"Downloading hand model to {dest} ...")
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    except Exception as exc:  # network down, blocked, etc.
        if tmp.exists():
            tmp.unlink()
        raise ModelNotFoundError(
            "Could not download the MediaPipe hand model. Connect to the "
            f"internet once, or put {MODEL_NAME} in a 'models' folder next "
            f"to the app. ({exc})"
        ) from exc
    return dest


def ensure_model():
    return find_model() or download_model()


def to_gesture_space(norm_points, width, height):
    """Normalized (x, y) -> same-unit (x * aspect, y) for gesture math."""
    aspect = width / float(height) if height else 1.0
    return [(x * aspect, y) for x, y in norm_points]


class HandTracker:
    """Finds one hand per frame. process() returns 21 normalized (x, y) or None."""

    def __init__(self, backend="auto", model_path=None,
                 min_detection_confidence=0.7, min_tracking_confidence=0.6):
        import mediapipe as mp

        self._mp = mp
        has_legacy = hasattr(mp, "solutions") and hasattr(mp.solutions, "hands")
        if backend == "auto":
            backend = "legacy" if has_legacy else "tasks"
        self.backend = backend

        if backend == "legacy":
            self._hands = mp.solutions.hands.Hands(
                max_num_hands=1,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
        elif backend == "tasks":
            from mediapipe.tasks.python import BaseOptions, vision

            path = Path(model_path) if model_path else ensure_model()
            if not path.is_file():
                raise ModelNotFoundError(f"Model file not found: {path}")
            options = vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=min_detection_confidence,
                min_hand_presence_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
            self._t0 = time.monotonic()
            self._last_ts = -1
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def process(self, frame_bgr):
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        if self.backend == "legacy":
            result = self._hands.process(rgb)
            if not result.multi_hand_landmarks:
                return None
            return [(p.x, p.y) for p in result.multi_hand_landmarks[0].landmark]

        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # VIDEO mode needs strictly increasing timestamps in milliseconds.
        ts = max(int((time.monotonic() - self._t0) * 1000), self._last_ts + 1)
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)
        if not result.hand_landmarks:
            return None
        return [(p.x, p.y) for p in result.hand_landmarks[0]]

    def close(self):
        if self.backend == "legacy":
            self._hands.close()
        else:
            self._landmarker.close()
