"""The screens around the tutorial: welcome, camera, tutorial, ready.

Pure logic (no drawing, no Qt), so it is easy to test. The Engine owns one
Flow while the onboarding screens are showing and drops it when the normal
window should appear. Returning users get a short "Welcome back" instead.
"""

WELCOME = "welcome"
CAMERA = "camera"
TUTORIAL = "tutorial"
READY = "ready"
BACK = "back"

BACK_SHOW = 2.5        # seconds "Welcome back" stays up
BACK_FADE_IN = 0.8
BACK_FADE_OUT = 0.6
READY_SECONDS = 6.0    # "You're ready!" moves on by itself after this long
READY_FADE_OUT = 0.6   # the ready screen fades out, then the window simply appears

NEXT_STAGE = {WELCOME: CAMERA, CAMERA: TUTORIAL, TUTORIAL: READY}


class Flow:
    def __init__(self, stage=WELCOME, name="", now=0.0):
        self.stage = stage
        self.name = name
        self.since = now
        self.finished = False
        self.exit_at = None     # when the fade-out began (ready screen)

    # ---------- movement ----------
    def go(self, stage, now):
        self.stage = stage
        self.since = now

    def advance(self, now):
        """Next screen; after the last one the flow is finished."""
        if self.stage == READY:
            self.begin_exit(now)      # fade out first; the window is cut to afterwards
            return self.stage
        nxt = NEXT_STAGE.get(self.stage)
        if nxt is None:
            self.finished = True
        else:
            self.go(nxt, now)
        return self.stage

    def begin_exit(self, now):
        if self.exit_at is None:
            self.exit_at = now

    def update(self, now):
        if self.stage == BACK and now - self.since >= BACK_SHOW + BACK_FADE_OUT:
            self.finished = True
        elif self.stage == READY:
            if self.exit_at is None and now - self.since >= READY_SECONDS:
                self.begin_exit(now)
            if self.exit_at is not None and now - self.exit_at >= READY_FADE_OUT:
                self.finished = True

    # ---------- fades for the welcome-back screen ----------
    def back_alpha(self, now):
        t = now - self.since
        if t < BACK_FADE_IN:
            return max(0.0, t / BACK_FADE_IN)
        if t > BACK_SHOW:
            return max(0.0, 1.0 - (t - BACK_SHOW) / BACK_FADE_OUT)
        return 1.0

    def alpha(self, now):
        """How visible the screen is: fades in/out for welcome-back, out for ready."""
        if self.stage == BACK:
            return self.back_alpha(now)
        if self.stage == READY and self.exit_at is not None:
            return max(0.0, 1.0 - (now - self.exit_at) / READY_FADE_OUT)
        return 1.0
