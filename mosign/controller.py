"""Turns a stream of per-frame gesture labels into actions."""

from mosign.gestures import NEXT_TAB, PREV_TAB, SCROLL_DOWN, SCROLL_UP, Stabilizer


class Controller:
    """Scrolls while you hold a point up/down; switches a tab once per point.

    `events` lists what started on the latest frame (for on-screen feedback):
    "scroll_up", "scroll_down", "prev_tab", "next_tab".
    """

    def __init__(self, actions, scroll_amount=1, stable_frames=3, tab_cooldown=1.0):
        self.actions = actions
        self.scroll_amount = scroll_amount
        self.tab_cooldown = tab_cooldown
        self.stabilizer = Stabilizer(stable_frames)
        self.scroll_mode = None          # None, "up", or "down"
        self.last_gesture = None         # last confirmed gesture (so tabs fire once)
        self.last_tab_time = float("-inf")
        self.events = []

    def update(self, raw, now):
        """Feed one frame's raw label. Returns the confirmed label."""
        self.events = []
        confirmed = self.stabilizer.update(raw)

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
        """Forget the current gesture (e.g. when tracking is paused)."""
        self.stabilizer.reset()
        self.last_gesture = None
        self.scroll_mode = None
        self.events = []
