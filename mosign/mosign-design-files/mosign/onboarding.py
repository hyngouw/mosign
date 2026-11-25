"""The tutorial: try every control once before gestures go live.

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
    title: str                # heading while you try it ("Point up")
    instruction: str          # one line of help
    icon: str = None          # gesture label for the picture
    kind: str = "event"       # "hand", "scroll" or "event"
    target: tuple = ()        # scroll direction, or events that complete the step
    seconds: float = 0.0      # for "hand" and "scroll": how long to keep it up
    name: str = ""            # what the gesture does ("Scroll up")
    caption: str = ""         # small print under the name
    tray: str = ""            # short label in the "learned" tray


STEPS = [
    Step("scroll_up", "Point up", "Point your index finger up and keep it there.",
         SCROLL_UP, "scroll", ("up",), 0.8,
         "Scroll up", "Continues while you hold it", "Scroll up"),
    Step("scroll_down", "Point down", "Turn your hand so your index finger points down.",
         SCROLL_DOWN, "scroll", ("down",), 0.8,
         "Scroll down", "Continues while you hold it", "Scroll down"),
    Step("prev_tab", "Point left", "Point your index finger to your left.",
         PREV_TAB, target=("prev_tab",),
         name="Previous tab", caption="Moves one tab per gesture", tray="Previous tab"),
    Step("next_tab", "Point right", "Point your index finger to your right.",
         NEXT_TAB, target=("next_tab",),
         name="Next tab", caption="Moves one tab per gesture", tray="Next tab"),
    Step("pause", "Rock horns", "Index and pinky up, other fingers down.",
         TOGGLE_TRACKING, target=("sleep", "wake"),
         name="Turn tracking off or on", caption="Hold for 1 second", tray="Tracking off/on"),
    Step("menu", "Pinky up", "Hold up only your pinky.",
         TOGGLE_MENU, target=("menu_on", "menu_off"),
         name="Hide or show the gesture guide", caption="Hold for 1 second",
         tray="Show/hide guide"),
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
