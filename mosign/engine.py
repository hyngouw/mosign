"""Everything Mosign does each frame, without any window code.

camera -> hand tracker -> gesture -> controller (-> browser), plus the tour,
then draw the main window image and the overlay image. qt_app.py shows those
images; the tests drive Engine directly with a fake camera and fake hands.
"""

from dataclasses import dataclass

import cv2

from mosign.actions import PyAutoGuiActions, RecordingActions
from mosign.camera import Camera
from mosign.controller import Controller
from mosign.gestures import classify_landmarks
from mosign.onboarding import Onboarding
from mosign.overlay import Overlay
from mosign.tracker import HandTracker, to_gesture_space
from mosign.ui import UI, View

# keyboard shortcuts in the main window
KEY_COMMANDS = {
    "c": "swap_camera",
    "s": "toggle_tracking",
    "m": "toggle_menu",
    "o": "tour",
    "q": "quit",
}


@dataclass
class Output:
    main: object          # BGR image for the main window
    overlay: object       # BGRA premultiplied image for the overlay
    menu_visible: bool
    quit: bool = False


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


class Engine:
    def __init__(self, cfg, overlay_scale=1.0, start_tour=False, tracker=None, actions=None):
        """Raises if hand tracking can't start (the caller shows a message)."""
        self.cfg = cfg
        self.tracker = tracker or HandTracker()
        self.camera = Camera(cfg.camera_index)
        self.real_actions = actions or PyAutoGuiActions()
        self.controller = Controller(
            self.real_actions,
            scroll_amount=cfg.scroll_amount,
            stable_frames=cfg.stable_frames,
            tab_cooldown=cfg.tab_cooldown,
            hold_seconds=cfg.hold_seconds,
            menu_visible=cfg.menu_visible,
        )
        self.ui = UI()
        self.overlay = Overlay(overlay_scale)
        self.fps = FpsCounter()
        self.tour = None
        self.tour_required = False
        self._last_now = None
        if start_tour or not cfg.onboarding_complete:
            self.start_tour(required=not cfg.onboarding_complete)

    # ---------- tour ----------
    def start_tour(self, required=False):
        """Practice mode: recognise everything, send nothing to the browser."""
        self.tour = Onboarding()
        self.tour_required = required
        self.controller.actions = RecordingActions()
        self.controller.set_awake(True)
        if not self.controller.menu_visible:
            self.controller.toggle_menu()

    def end_tour(self):
        self.controller.actions = self.real_actions
        self.tour_required = False

    # ---------- one frame ----------
    def step(self, now, commands=()):
        cfg, controller, camera = self.cfg, self.controller, self.camera
        frame = camera.read()
        norm = raw = None
        if frame is not None:
            frame = cv2.flip(frame, 1)  # mirror so it feels natural
            norm = self.tracker.process(frame)
            if norm is not None:
                h, w = frame.shape[:2]
                raw = classify_landmarks(to_gesture_space(norm, w, h))
        controller.update(raw, now)
        events = list(controller.events)

        tour = self.tour
        if tour is not None and not tour.done:
            dt = 0.0 if self._last_now is None else min(0.1, now - self._last_now)
            result = tour.update(now, dt, hand_present=norm is not None,
                                 scroll_mode=controller.scroll_mode, events=events)
            if result == "step":
                controller.last_tab_time = float("-inf")  # no cooldown between steps
            elif result == "done":
                self.end_tour()
                cfg.onboarding_complete = True
                cfg.save()
                events.append("celebrate")
        if tour is not None and tour.done and not tour.celebrating(now):
            self.tour = None
        self._last_now = now

        commands = list(commands) + self.ui.pop_commands()
        quit_now = "quit" in commands
        for cmd in commands:
            before = len(controller.events)
            self._run_command(cmd, now)
            events += controller.events[before:]   # e.g. menu_on from the M key

        if controller.menu_visible != cfg.menu_visible:
            cfg.menu_visible = controller.menu_visible
            cfg.save()

        view = View(
            frame=frame,
            hand=norm,
            confirmed=controller.confirmed,
            awake=controller.awake,
            holding=controller.holding,
            scroll_mode=controller.scroll_mode,
            events=events,
            camera_label=camera.label,
            fps=self.fps.tick(now),
            menu_visible=controller.menu_visible,
            tour=self.tour,
            tour_required=self.tour_required,
        )
        self.overlay.update(view, now)
        return Output(
            main=self.ui.render(view, now),
            overlay=self.overlay.render(view, now),
            menu_visible=view.menu_visible,
            quit=quit_now,
        )

    def _run_command(self, cmd, now):
        controller = self.controller
        if cmd == "swap_camera":
            if self.camera.next_camera():
                controller.reset()
                self.cfg.camera_index = self.camera.index
                self.cfg.save()
                self.ui.toast(f"Switched to {self.camera.label}", now)
            else:
                self.ui.toast("No other camera found", now)
        elif cmd == "toggle_tracking":
            controller.toggle_awake()
        elif cmd == "toggle_menu":
            controller.toggle_menu()
        elif cmd == "tour":
            if self.tour is not None and self.tour.step is not None:
                if not self.tour_required:
                    self.end_tour()
                    self.tour = None
                    self.ui.toast("Tour ended", now)
            else:
                self.start_tour()

    def close(self):
        self.tracker.close()
        self.camera.release()
