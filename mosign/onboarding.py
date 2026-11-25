"""The tutorial: try every control once before gestures go live.

While it runs the app is in practice mode: gestures are recognised but nothing
is sent to the browser. Every step is the same: hold the gesture for a moment
while a progress bar fills, so by the end you have done every control.
"""

from dataclasses import dataclass

from mosign.gestures import NEXT_TAB, PREV_TAB, SCROLL_DOWN, SCROLL_UP, TOGGLE_MENU, TOGGLE_TRACKING

HOLD_SECONDS = 0.8        # every gesture is held this long to pass its step
FLASH_SECONDS = 0.45      # the gesture pulses and glows when you pass
FLY_DELAY = 0.5           # then, after this long...
FLY_SECONDS = 0.65        # ...the hand flies into its slot in the tray
STEP_PAUSE = FLY_DELAY + FLY_SECONDS   # input is ignored while this plays
LAND_PAUSE = 0.7          # after the last hand lands, its slot stays in view this long
CELEBRATE_SECONDS = 3.0   # how long the "You're all set" card stays up


@dataclass(frozen=True)
class Step:
    key: str
    title: str                # heading while you try it ("Point up")
    instruction: str          # one line of help
    icon: str = None          # gesture label for the picture
    kind: str = "hold"        # "hold": keep the gesture up for `seconds`; "hand": any hand
    seconds: float = HOLD_SECONDS
    name: str = ""            # what the gesture does ("Scroll up")
    caption: str = ""         # small print under the name
    tray: str = ""            # short label in the "learned" tray


STEPS = [
    Step("scroll_up", "Point up", "Point your index finger up and keep it there.",
         SCROLL_UP, name="Scroll up", caption="Continues while you hold it", tray="Scroll up"),
    Step("scroll_down", "Point down", "Turn your hand so your index finger points down.",
         SCROLL_DOWN, name="Scroll down", caption="Continues while you hold it",
         tray="Scroll down"),
    Step("prev_tab", "Point left", "Point your index finger to your left.",
         PREV_TAB, name="Previous tab", caption="Moves one tab per gesture", tray="Previous tab"),
    Step("next_tab", "Point right", "Point your index finger to your right.",
         NEXT_TAB, name="Next tab", caption="Moves one tab per gesture", tray="Next tab"),
    Step("pause", "Rock horns", "Index and pinky up, other fingers down.",
         TOGGLE_TRACKING, name="Turn tracking off or on", caption="Hold 1 second in everyday use",
         tray="Tracking off/on"),
    Step("menu", "Pinky up", "Hold up only your pinky.",
         TOGGLE_MENU, name="Hide or show the gesture guide", caption="Hold 1 second in everyday use",
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

    def since_pass(self, now):
        """Seconds since the last gesture was passed (while its animation plays), else None."""
        if self.done and self.finished_at is not None:
            return now - self.finished_at
        if self._paused_until is not None and now < self._paused_until:
            return now - (self._paused_until - STEP_PAUSE)
        return None

    def filled(self, now):
        """How many tray slots are full: a slot fills when the flying hand lands in it."""
        t = self.since_pass(now)
        n = self.index - (1 if t is not None and t < STEP_PAUSE else 0)
        return max(0, n)

    def between_steps(self, now):
        return self._paused_until is not None and now < self._paused_until

    def text_for(self, template, menu_visible=True, awake=True):
        return template.format(
            menu_action="hide" if menu_visible else "show",
            tracking_action="pause" if awake else "wake up",
        )

    def update(self, now, dt, gesture=None, hand_present=False):
        """Advance the tutorial by one frame. `gesture` is the steady gesture label the
        camera sees. Every step works the same way: keep the right gesture up until the
        bar fills; the bar drains if you drop it. Returns "step" when a step was
        finished, "done" when the whole tutorial was, otherwise None."""
        if self.done:
            return None
        if self._paused_until is not None:
            if now < self._paused_until:
                return None
            self._paused_until = None

        step = self.steps[self.index]
        holding = hand_present if step.kind == "hand" else gesture == step.icon
        if holding:
            self.progress = min(1.0, self.progress + dt / step.seconds)
        else:
            self.progress = max(0.0, self.progress - 2 * dt / step.seconds)
        if self.progress < 1.0:
            return None

        self.index += 1
        self.progress = 0.0
        if self.index >= len(self.steps):
            self.done = True
            self.finished_at = now
            return "done"
        self._paused_until = now + STEP_PAUSE
        return "step"
