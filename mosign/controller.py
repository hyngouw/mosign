"""Turns a stream of per-frame gesture labels into actions."""

from mosign.gestures import Stabilizer


class Controller:
    def __init__(self, actions, scroll_amount=1, stable_frames=3, tab_cooldown=1.0):
        self.actions = actions
        self.scroll_amount = scroll_amount
        self.tab_cooldown = tab_cooldown
        self.stabilizer = Stabilizer(stable_frames)
        self.scroll_mode = None          # None, "up", or "down"
        self.last_gesture = None         # last confirmed gesture (so tabs fire once)
        self.last_tab_time = float("-inf")
        self.events = []                 # what happened on the latest frame

    def update(self, raw, now):
        """Feed one frame's raw label. Returns the confirmed label."""
        self.events = []
        confirmed = self.stabilizer.update(raw)

        # A gesture "fires" when it changes to something new
        if confirmed != self.last_gesture:
            if confirmed == "scroll_up":
                self.scroll_mode = "up"
            elif confirmed == "scroll_down":
                self.scroll_mode = "down"
            elif confirmed == "stop":
                self.scroll_mode = None
            elif confirmed in ("next_tab", "prev_tab"):
                if now - self.last_tab_time > self.tab_cooldown:
                    if confirmed == "next_tab":
                        self.actions.next_tab()
                    else:
                        self.actions.prev_tab()
                    self.last_tab_time = now
                    self.events.append(confirmed)
            self.last_gesture = confirmed

        # Keep scrolling every frame until "stop" is shown
        if self.scroll_mode == "up":
            self.actions.scroll(self.scroll_amount)
        elif self.scroll_mode == "down":
            self.actions.scroll(-self.scroll_amount)
        return confirmed
