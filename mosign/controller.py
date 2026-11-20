"""Turns a stream of per-frame gesture labels into actions."""

from mosign.gestures import (
    HOLD_SECONDS,
    NEXT_TAB,
    PREV_TAB,
    SCROLL_DOWN,
    SCROLL_UP,
    TOGGLE_TRACKING,
    HoldTrigger,
    Stabilizer,
)


class Controller:
    """Scrolls while you hold a point up/down; switches a tab once per point.

    Holding the wake gesture (rock horns) for HOLD_SECONDS turns tracking off;
    holding it again turns it back on. While asleep nothing else does anything.

    `events` lists what started on the latest frame (for on-screen feedback):
    "scroll_up", "scroll_down", "prev_tab", "next_tab", "sleep", "wake".
    """

    def __init__(self, actions, scroll_amount=1, stable_frames=3, tab_cooldown=1.0,
                 hold_seconds=HOLD_SECONDS):
        self.actions = actions
        self.scroll_amount = scroll_amount
        self.tab_cooldown = tab_cooldown
        self.stabilizer = Stabilizer(stable_frames)
        self.tracking_hold = HoldTrigger(hold_seconds)
        self.awake = True
        self.scroll_mode = None          # None, "up", or "down"
        self.last_gesture = None         # last confirmed gesture (so tabs fire once)
        self.last_tab_time = float("-inf")
        self.confirmed = None
        self.events = []

    @property
    def holding(self):
        """(label, progress) of a special gesture being held, or None."""
        if self.tracking_hold.progress > 0:
            return TOGGLE_TRACKING, self.tracking_hold.progress
        return None

    def set_awake(self, awake):
        if awake == self.awake:
            return
        self.awake = awake
        self.scroll_mode = None
        self.events.append("wake" if awake else "sleep")

    def toggle_awake(self):
        self.set_awake(not self.awake)

    def update(self, raw, now):
        """Feed one frame's raw label. Returns the confirmed label."""
        self.events = []
        confirmed = self.stabilizer.update(raw)
        self.confirmed = confirmed

        if self.tracking_hold.update(confirmed == TOGGLE_TRACKING, now):
            self.toggle_awake()

        if not self.awake:
            self.scroll_mode = None
            self.last_gesture = confirmed
            return confirmed

        # Something new is being shown
        if confirmed != self.last_gesture:
            if confirmed in (NEXT_TAB, PREV_TAB):
                if now - self.last_tab_time > self.tab_cooldown:
                    if confirmed == NEXT_TAB:
                        self.actions.next_tab()
                    else:
                        self.actions.prev_tab()
                    self.last_tab_time = now
                    self.events.append(confirmed)
            elif confirmed in (SCROLL_UP, SCROLL_DOWN):
                self.events.append(confirmed)
            self.last_gesture = confirmed

        # Scroll only while the finger is still pointing up or down.
        if confirmed == SCROLL_UP:
            self.scroll_mode = "up"
            self.actions.scroll(self.scroll_amount)
        elif confirmed == SCROLL_DOWN:
            self.scroll_mode = "down"
            self.actions.scroll(-self.scroll_amount)
        else:
            self.scroll_mode = None
        return confirmed

    def reset(self):
        """Forget the current gesture (e.g. when the camera changes)."""
        self.stabilizer.reset()
        self.tracking_hold.update(False, 0)
        self.last_gesture = None
        self.confirmed = None
        self.scroll_mode = None
        self.events = []
