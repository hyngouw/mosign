"""Main loop: camera -> hand tracker -> gesture -> controller -> screen."""

import argparse
import time

import cv2

from mosign.actions import PyAutoGuiActions
from mosign.controller import Controller
from mosign.gestures import classify_landmarks
from mosign.tracker import HAND_CONNECTIONS, HandTracker, to_gesture_space

# ---------------- Settings you can tweak ----------------
SCROLL_AMOUNT = 1        # per frame; raise on macOS if scrolling feels slow
STABLE_FRAMES = 3        # gesture must be held this many frames to count
TAB_COOLDOWN = 1.0       # seconds between tab switches
CAMERA_INDEX = 0
# --------------------------------------------------------


def draw_hand(frame, norm_points):
    h, w = frame.shape[:2]
    pts = [(int(x * w), int(y * h)) for x, y in norm_points]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (255, 255, 255), 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(frame, p, 4, (0, 0, 255), -1, cv2.LINE_AA)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Control your browser with hand gestures.")
    parser.add_argument("--camera", type=int, default=CAMERA_INDEX, help="camera index")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam.")

    tracker = HandTracker()
    controller = Controller(PyAutoGuiActions(), SCROLL_AMOUNT, STABLE_FRAMES, TAB_COOLDOWN)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)  # mirror so it feels natural
            norm = tracker.process(frame)
            raw = None
            if norm is not None:
                draw_hand(frame, norm)
                h, w = frame.shape[:2]
                raw = classify_landmarks(to_gesture_space(norm, w, h))
            controller.update(raw, time.time())

            cv2.putText(frame, f"Gesture: {raw}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"Scrolling: {controller.scroll_mode}", (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 200, 0), 2)
            status = "ON" if controller.awake else "SLEEPING (hold rock horns to wake)"
            cv2.putText(frame, f"Tracking: {status}", (10, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
            if controller.holding:
                pct = int(controller.holding[1] * 100)
                cv2.putText(frame, f"Hold... {pct}%", (10, 135),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.imshow("Gesture Control (q to quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):
                controller.toggle_awake()
    finally:
        tracker.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0
