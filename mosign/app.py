"""Main loop: camera -> hand tracker -> gesture -> controller -> window."""

import argparse
import time

import cv2

from mosign.actions import PyAutoGuiActions
from mosign.camera import Camera
from mosign.config import Config
from mosign.controller import Controller
from mosign.gestures import classify_landmarks
from mosign.tracker import HandTracker, to_gesture_space
from mosign.ui import HEIGHT, UI, WIDTH, WINDOW_TITLE, View, render_message

KEY_COMMANDS = {
    ord("c"): "swap_camera",
    ord("s"): "toggle_tracking",
    ord("q"): "quit",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Control your browser with hand gestures.")
    parser.add_argument("--camera", type=int, default=None,
                        help="camera index to start with (default: last used)")
    parser.add_argument("--max-frames", type=int, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def open_window():
    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_TITLE, WIDTH, HEIGHT)


def window_closed():
    try:
        return cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def show_fatal(title, message, max_frames=None):
    """Show an error inside the window (packaged apps have no terminal)."""
    img = render_message(title, message)
    open_window()
    frames = 0
    while True:
        cv2.imshow(WINDOW_TITLE, img)
        key = cv2.waitKey(50) & 0xFF
        frames += 1
        if key == ord("q") or window_closed() or (max_frames and frames >= max_frames):
            break
    cv2.destroyAllWindows()


class FpsCounter:
    def __init__(self):
        self.fps = 0.0
        self._last = None

    def tick(self, now):
        if self._last is not None and now > self._last:
            inst = 1.0 / (now - self._last)
            self.fps = inst if not self.fps else self.fps * 0.9 + inst * 0.1
        self._last = now
        return self.fps


def main(argv=None):
    args = parse_args(argv)
    cfg = Config.load()
    if args.camera is not None:
        cfg.camera_index = args.camera

    try:
        tracker = HandTracker()
    except Exception as exc:  # missing model, broken install, ...
        show_fatal("Hand tracking could not start", str(exc), args.max_frames)
        return 1

    camera = Camera(cfg.camera_index)
    controller = Controller(
        PyAutoGuiActions(),
        scroll_amount=cfg.scroll_amount,
        stable_frames=cfg.stable_frames,
        tab_cooldown=cfg.tab_cooldown,
        hold_seconds=cfg.hold_seconds,
    )
    ui = UI()
    fps = FpsCounter()

    open_window()
    cv2.setMouseCallback(WINDOW_TITLE, ui.on_mouse)
    frames = 0
    try:
        while True:
            now = time.time()
            frame = camera.read()
            norm = raw = None
            if frame is not None:
                frame = cv2.flip(frame, 1)  # mirror so it feels natural
                norm = tracker.process(frame)
                if norm is not None:
                    h, w = frame.shape[:2]
                    raw = classify_landmarks(to_gesture_space(norm, w, h))
            controller.update(raw, now)

            view = View(
                frame=frame,
                hand=norm,
                confirmed=controller.confirmed,
                awake=controller.awake,
                holding=controller.holding,
                scroll_mode=controller.scroll_mode,
                events=list(controller.events),
                camera_label=camera.label,
                fps=fps.tick(now),
            )
            cv2.imshow(WINDOW_TITLE, ui.render(view, now))

            key = cv2.waitKey(1) & 0xFF
            commands = ui.pop_commands()
            if key in KEY_COMMANDS:
                commands.append(KEY_COMMANDS[key])

            if "quit" in commands:
                break
            for cmd in commands:
                if cmd == "swap_camera":
                    if camera.next_camera():
                        controller.reset()
                        cfg.camera_index = camera.index
                        cfg.save()
                        ui.toast(f"Switched to {camera.label}", now)
                    else:
                        ui.toast("No other camera found", now)
                elif cmd == "toggle_tracking":
                    controller.toggle_awake()

            frames += 1
            if args.max_frames and frames >= args.max_frames:
                break
            if window_closed():
                break
    finally:
        tracker.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0
