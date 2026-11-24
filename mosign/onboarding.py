"""First-run tour: try every control once before gestures go live.

While the tour runs the app is in practice mode: gestures are recognised,
Pip reacts and the menu works, but nothing is sent to the browser. Each step
finishes when you actually do the gesture, so by the end you have used
every control at least once.
"""

from dataclasses import dataclass

from mosign.gestures import NEXT_TAB, PREV_TAB, SCROLL_DOWN, SCROLL_UP, TOGGLE_MENU, TOGGLE_TRACKING

STEP_PAUSE = 0.9          # seconds of "Nice!" between steps (input ignored)
CELEBRATE_SECONDS = 3.0   # how long the "You're all set" card stays up


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    instruction: str
    icon: str = None          # gesture label for the picture, or None
    kind: str = "event"       # "hand", "scroll" or "event"
    target: tuple = ()        # scroll direction, or events that complete the step
    seconds: float = 0.0      # for "hand" and "scroll": how long to keep it up


STEPS = [
    Step("hand", "Show your hand",
         "Hold one hand up in front of the camera, palm facing it.",
         kind="hand", seconds=0.6),
    Step("scroll_up", "Point up to scroll up",
         "Point your index finger up and keep it there. Lower it to stop.",
         SCROLL_UP, "scroll", ("up",), 0.8),
    Step("scroll_down", "Point down to scroll down",
         "Turn your hand so your index finger points down. Lower it to stop.",
         SCROLL_DOWN, "scroll", ("down",), 0.8),
    Step("prev_tab", "Point left for the previous tab",
         "Point your index finger to your left.",
         PREV_TAB, target=("prev_tab",)),
    Step("next_tab", "Point right for the next tab",
         "Point your index finger to your right.",
         NEXT_TAB, target=("next_tab",)),
    Step("menu", "Hold your pinky up",
         "Hold up only your pinky for 1 second to {menu_action} the gesture menu "
         "in the top-right corner of your screen.",
         TOGGLE_MENU, target=("menu_on", "menu_off")),
    Step("menu_again", "Again, to {menu_action} it",
         "Hold your pinky up once more to {menu_action} the menu.",
         TOGGLE_MENU, target=("menu_on", "menu_off")),
    Step("pause", "Hold rock horns to {tracking_action}",
         "Index and pinky up, other fingers down. Hold it for 1 second.",
         TOGGLE_TRACKING, target=("sleep", "wake")),
    Step("resume", "Rock horns again to {tracking_action}",
         "This is how you turn gestures off and on without touching the laptop.",
         TOGGLE_TRACKING, target=("sleep", "wake")),
]


class Onboarding:
    def __init__(self, steps=STEPS):
        self.steps = list(steps)
        self.index = 0
        self.progress = 0.0          # 0..1 within "hand" / "scroll" steps
        self.done = False
        self.finished_at = None
        self._paused_until = None    # short "Nice!" break after a step

    @property
    def total(self):
        return len(self.steps)

    @property
    def step(self):
        return None if self.done else self.steps[self.index]

    def celebrating(self, now):
        return self.done and self.finished_at is not None and \
            now - self.finished_at < CELEBRATE_SECONDS

    def between_steps(self, now):
        return self._paused_until is not None and now < self._paused_until

    def text_for(self, template, menu_visible=True, awake=True):
        return template.format(
            menu_action="hide" if menu_visible else "show",
            tracking_action="pause" if awake else "wake up",
        )

    def update(self, now, dt, hand_present=False, scroll_mode=None, events=()):
        """Advance the tour. Returns "step" when a step was finished,
        "done" when the whole tour was finished, otherwise None."""
        if self.done:
            return None
        if self._paused_until is not None:
            if now < self._paused_until:
                return None
            self._paused_until = None

        step = self.steps[self.index]
        complete = False
        if step.kind == "hand":
            self.progress = min(1.0, self.progress + dt / step.seconds) if hand_present \
                else max(0.0, self.progress - dt / step.seconds)
            complete = self.progress >= 1.0
        elif step.kind == "scroll":
            if scroll_mode in step.target:
                self.progress = min(1.0, self.progress + dt / step.seconds)
            complete = self.progress >= 1.0
        else:
            complete = any(e in step.target for e in events)

        if not complete:
            return None
        self.index += 1
        self.progress = 0.0
        if self.index >= len(self.steps):
            self.done = True
            self.finished_at = now
            return "done"
        self._paused_until = now + STEP_PAUSE
        return "step"
