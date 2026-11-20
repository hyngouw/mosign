"""Turns a stream of per-frame gesture labels into actions."""

from mosign.gestures import (
    HOLD_SECONDS,
    NEXT_TAB,
    PREV_TAB,
    SCROLL_DOWN,
    SCROLL_UP,
    TOGGLE_MENU,
    TOGGLE_TRACKING,
    HoldTrigger,
    Stabilizer,
)


class Controller:
    """Scrolls while you hold a point up/down; switches a tab once per point.

    Holding the wake gesture (rock horns) for HOLD_SECONDS turns tracking off;
    holding it again turns it back on. While asleep nothing else does anything.

    Holding just the pinky for HOLD_SECONDS shows or hides the gesture menu.
    That works while asleep too, since it doesn't touch the browser.

    `events` lists what started on the latest frame (for on-screen feedback):
    "scroll_up", "scroll_down", "prev_tab", "next_tab", "sleep", "wake",
    "menu_on", "menu_off".
    """

    def __init__(self, actions, scroll_amount=1, stable_frames=3, tab_cooldown=1.0,
                 hold_seconds=HOLD_SECONDS, menu_visible=True):
        self.actions = actions
        self.scroll_amount = scroll_amount
        self.tab_cooldown = tab_cooldown
        self.stabilizer = Stabilizer(stable_frames)
        self.tracking_hold = HoldTrigger(hold_seconds)
        self.menu_hold = HoldTrigger(hold_seconds)
        self.awake = True
        self.menu_visible = menu_visible
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
        if self.menu_hold.progress > 0:
            return TOGGLE_MENU, self.menu_hold.progress
        return None

    def set_awake(self, awake):
        if awake == self.awake:
            return
        self.awake = awake
        self.scroll_mode = None
        self.events.append("wake" if awake else "sleep")

    def toggle_awake(self):
        self.set_awake(not self.awake)

    def toggle_menu(self):
        self.menu_visible = not self.menu_visible
        self.events.append("menu_on" if self.menu_visible else "menu_off")

    def update(self, raw, now):
        """Feed one frame's raw label. Returns the confirmed label."""
        self.events = []
        confirmed = self.stabilizer.update(raw)
        self.confirmed = confirmed

        if self.tracking_hold.update(confirmed == TOGGLE_TRACKING, now):
            self.toggle_awake()
        if self.menu_hold.update(confirmed == TOGGLE_MENU, now):
            self.toggle_menu()

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
        self.menu_hold.update(False, 0)
        self.last_gesture = None
        self.confirmed = None
        self.scroll_mode = None
        self.events = []
