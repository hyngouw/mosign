"""Webcam access with the ability to switch between cameras."""

import cv2

MAX_CAMERAS = 6          # camera indexes 0..5 are tried when swapping
LOST_AFTER_FAILURES = 30  # consecutive failed reads before a camera counts as lost


class Camera:
    def __init__(self, index=0, opener=None, max_cameras=MAX_CAMERAS):
        self._opener = opener or cv2.VideoCapture
        self.max_cameras = max_cameras
        self.index = index
        self._cap = None
        self._failures = 0
        self.open(index)

    @property
    def label(self):
        return f"Camera {self.index}" if self.is_open else "No camera"

    @property
    def is_open(self):
        return self._cap is not None

    def _try_open(self, index):
        cap = self._opener(index)
        if cap is not None and cap.isOpened():
            ok, _ = cap.read()
            if ok:
                return cap
        if cap is not None:
            cap.release()
        return None

    def open(self, index):
        cap = self._try_open(index)
        if cap is None:
            return False
        self.release()
        self._cap = cap
        self.index = index
        self._failures = 0
        return True

    def next_camera(self):
        """Switch to the next camera that works. Returns True if it changed."""
        for step in range(1, self.max_cameras):
            candidate = (self.index + step) % self.max_cameras
            if self.open(candidate):
                return True
        if not self.is_open:  # current one was lost; try to get it back
            return self.open(self.index)
        return False

    def read(self):
        """Return a BGR frame, or None if there is no picture right now."""
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._failures += 1
            if self._failures >= LOST_AFTER_FAILURES:
                self.release()
            return None
        self._failures = 0
        return frame

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
