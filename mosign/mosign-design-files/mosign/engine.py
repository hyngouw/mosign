"""Everything Mosign does each frame, without any window code.

camera -> hand tracker -> gesture -> controller (-> browser), plus the tour,
then draw the main window image and the overlay image. qt_app.py shows those
images; the tests drive Engine directly with a fake camera and fake hands.
"""

import os
from dataclasses import dataclass

import cv2

from mosign.actions import PyAutoGuiActions, RecordingActions
from mosign.camera import Camera
from mosign.cat import CatFace, CatMotion, CatSprite
from mosign import flow as flows
from mosign.controller import Controller
from mosign.gestures import classify_landmarks
from mosign.onboarding import STEP_PAUSE, Onboarding
from mosign.overlay import Overlay
from mosign.sound import Chime
from mosign.tabs import TabLocator
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


CAT_HEIGHT = 54          # logical pixels; a bit taller than a browser tab
CLOSE_BUTTON_ROOM = 28   # keep clear of the tab's close button
FEET_INSET = 3           # feet this far above the tab's bottom edge
PREDICT_SECONDS = 1.0    # after a switch, trust our guess over a lagging browser
STALE_SECONDS = 3.0      # tab positions older than this are ignored


@dataclass
class Output:
    main: object          # BGR image for the main window
    overlay: object       # BGRA premultiplied image for the corner overlay
    menu_visible: bool
    cat: object = None    # BGRA premultiplied image of the cat
    cat_feet: tuple = (0.0, 0.0)    # where the cat's feet are, in screen points
    cat_anchor: tuple = (0.0, 0.0)  # where the feet are inside `cat`, in screen points
    quit: bool = False
    show_overlay: bool = True   # False while the welcome / tutorial screens are up


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
    def __init__(self, cfg, overlay_scale=1.0, start_tour=False, tracker=None, actions=None,
                 tabs=None, home=(0.0, 0.0), welcome_back=False, sound=None):
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
        self.cat_face = CatFace()
        self.cat_sprite = CatSprite(CAT_HEIGHT * overlay_scale)
        self.cat_motion = CatMotion(*home)
        self.home = tuple(home)
        self.tabs = tabs if tabs is not None else TabLocator(query=None)
        self._predicted = None   # (index, until) after a tab switch
        self.fps = FpsCounter()
        self.sound = sound if sound is not None else \
            Chime(enabled=cfg.sounds and not os.environ.get("MOSIGN_MUTE"))
        self.tour = None
        self.tour_required = False
        self.flow = None
        self._last_now = None
        if not cfg.onboarding_complete:
            # first run: welcome -> sign in -> camera -> tutorial -> ready
            self.start_tour(required=True)
            self.flow = flows.Flow(flows.WELCOME)
        elif start_tour:
            self.start_tour()
            self.flow = flows.Flow(flows.TUTORIAL)
        elif welcome_back:
            self.flow = flows.Flow(flows.BACK, name=cfg.user_name)

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
        if not self.controller.menu_visible:
            self.controller.toggle_menu()   # the tutorial may have hidden it
        if not self.controller.awake:
            self.controller.set_awake(True)

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

        flow = self.flow
        tour = self.tour
        in_tutorial = flow is None or flow.stage == flows.TUTORIAL
        if tour is not None and not tour.done and in_tutorial:
            dt = 0.0 if self._last_now is None else min(0.1, now - self._last_now)
            result = tour.update(now, dt, hand_present=norm is not None,
                                 scroll_mode=controller.scroll_mode, events=events)
            if result in ("step", "done"):
                self.sound.play()
                controller.last_tab_time = float("-inf")  # no cooldown between steps
                if not controller.awake:
                    controller.set_awake(True)    # rock horns pauses; keep going
            if result == "done":
                self.end_tour()
                cfg.onboarding_complete = True
                cfg.save()
                events.append("celebrate")
        if tour is not None and tour.done:
            if flow is not None and flow.stage == flows.TUTORIAL \
                    and now - tour.finished_at >= STEP_PAUSE:
                flow.go(flows.READY, now)       # let the last check mark show first
            if flow is None and not tour.celebrating(now):
                self.tour = None
        self._last_now = now
        if flow is not None:
            flow.update(now)
            if flow.finished:
                self._finish_flow()

        commands = list(commands) + self.ui.pop_commands()
        quit_now = "quit" in commands or (
            "flow_close" in commands and self.flow is not None
            and self.flow.stage in (flows.WELCOME, flows.LOGIN, flows.CAMERA))
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
            flow=self.flow,
        )
        self.overlay.update(view, now)
        self._move_cat(events, now)
        self.cat_face.update(now, events, view.scroll_mode, view.awake)
        motion = self.cat_motion
        ax, ay = self.cat_sprite.anchor
        return Output(
            main=self.ui.render(view, now),
            overlay=self.overlay.render(view, now),
            menu_visible=view.menu_visible,
            cat=self.cat_sprite.render_bgra(self.cat_face, motion.squash, motion.lean),
            cat_feet=(motion.x, motion.y),
            cat_anchor=(ax / self.overlay.scale, ay / self.overlay.scale),
            quit=quit_now,
            show_overlay=self.flow is None or self.flow.stage == flows.BACK,
        )

    # ---------- the cat ----------
    def set_home(self, x, y):
        """Where the cat sits when it isn't on a tab (set by the window code)."""
        first = self.home == (0.0, 0.0)
        self.home = (float(x), float(y))
        if first:
            self.cat_motion.place(x, y)

    def _tab_info(self, now):
        info = self.tabs.latest() if self.tabs is not None else None
        if info is None or (info.stamp and self.tabs.clock() - info.stamp > STALE_SECONDS):
            return None
        return info

    @staticmethod
    def perch(rect):
        """Where the cat sits on a tab: on its right side, next to the close
        button, standing on the tab's bottom edge. (Sitting on top of the tab
        doesn't work: in a maximised window the tabs touch the top of the screen.)"""
        x, y, w, h = rect
        half = CAT_HEIGHT * 0.5
        if w >= 2 * half + CLOSE_BUTTON_ROOM + 40:     # room left for the title
            cx = x + w - CLOSE_BUTTON_ROOM - half
        else:
            cx = x + w / 2                              # narrow tabs: centre
        return cx, y + h - FEET_INSET

    def _move_cat(self, events, now):
        info = self._tab_info(now)
        for event in events:
            if event in ("next_tab", "prev_tab"):
                direction = 1 if event == "next_tab" else -1
                self.tabs.poke()
                if info is not None and info.active >= 0:
                    # jump right away to where the tab will be; the browser
                    # takes a moment to report the new one
                    index = info.neighbour(direction)
                    self._predicted = (index, now + PREDICT_SECONDS)
                else:
                    self.cat_motion.hop(direction, now)

        target = self.home
        if info is not None and info.tabs:
            index = info.active
            if self._predicted and now < self._predicted[1] and 0 <= self._predicted[0] < len(info.tabs):
                index = self._predicted[0]
                if info.active == index:
                    self._predicted = None    # the browser caught up
            if 0 <= index < len(info.tabs):
                target = self.perch(info.tabs[index])
        self.cat_motion.go(*target, now)
        self.cat_motion.update(now)

    def _finish_flow(self):
        self.flow = None
        if self.tour is not None and self.tour.done:
            self.tour = None

    def _flow_command(self, cmd, now):
        """Clicks and keys on the onboarding screens. True if it was one."""
        flow = self.flow
        if cmd.startswith("type:"):
            flow.type_text(cmd[5:])
        elif cmd == "key:backspace":
            flow.backspace()
        elif cmd == "key:tab":
            flow.next_field()
        elif cmd == "focus_email":
            flow.focus = "email"
        elif cmd == "focus_password":
            flow.focus = "password"
        elif cmd == "toggle_password":
            flow.show_password = not flow.show_password
        elif cmd == "login_submit":
            if flow.stage == flows.LOGIN and flow.submit(now):
                self._signed_in(now)
        elif cmd in ("login_google", "login_apple"):
            flow.sign_in_with_provider(now)
            self._signed_in(now)
        elif cmd == "flow_next":
            self._advance_flow(now)
        elif cmd == "flow_close":
            if flow.stage in (flows.TUTORIAL, flows.READY, flows.BACK):
                if flow.stage == flows.TUTORIAL:
                    self._skip_tutorial()
                flow.finished = True
                self._finish_flow()
        else:
            return False
        return True

    def _signed_in(self, now):
        """Remember the sign-in details on this computer (no account behind them yet)."""
        self.cfg.user_name = self.flow.name or self.cfg.user_name
        self.cfg.email = self.flow.email or self.cfg.email
        self.cfg.save()
        self._after_advance(now)

    def _advance_flow(self, now):
        self.flow.advance(now)
        self._after_advance(now)
        if self.flow.finished:
            self._finish_flow()

    def _after_advance(self, now):
        if self.flow is not None and self.flow.stage == flows.TUTORIAL:
            self.start_tour(required=not self.cfg.onboarding_complete)

    def _skip_tutorial(self):
        self.end_tour()
        self.tour = None
        self.cfg.onboarding_complete = True
        self.cfg.save()

    def _run_command(self, cmd, now):
        controller = self.controller
        if self.flow is not None:
            if self._flow_command(cmd, now):
                return
            allowed = {"swap_camera": (flows.CAMERA,), "tour": (flows.TUTORIAL,)}
            if self.flow.stage not in allowed.get(cmd, ()):
                return   # shortcuts are off on these screens (typing must not trigger them)
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
                    self.flow = None
                    self.ui.toast("Tour ended", now)
            else:
                self.start_tour()
                self.flow = flows.Flow(flows.TUTORIAL, now=now)

    def close(self):
        self.tracker.close()
        self.camera.release()
        if self.tabs is not None:
            self.tabs.stop()
