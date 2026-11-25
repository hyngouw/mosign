"""The screens around the tutorial: welcome, sign in, camera, tutorial, ready.

Pure logic (no drawing, no Qt), so it is easy to test. The Engine owns one
Flow while the onboarding screens are showing and drops it when the normal
window should appear. Returning users get a short "Welcome back" instead.
"""

WELCOME = "welcome"
LOGIN = "login"
CAMERA = "camera"
TUTORIAL = "tutorial"
READY = "ready"
BACK = "back"

BACK_SHOW = 2.5        # seconds "Welcome back" stays up
BACK_FADE_IN = 0.8
BACK_FADE_OUT = 0.6
READY_SECONDS = 6.0    # "You're ready!" moves on by itself after this long

NEXT_STAGE = {WELCOME: LOGIN, LOGIN: CAMERA, CAMERA: TUTORIAL, TUTORIAL: READY}


def name_from_email(email):
    """'alex.smith@mail.com' -> 'Alex'. Empty when there is nothing sensible."""
    local = email.split("@")[0].strip()
    for part in local.replace("_", ".").replace("-", ".").split("."):
        letters = "".join(c for c in part if c.isalpha())
        if letters:
            return letters[:1].upper() + letters[1:].lower()
    return ""


def valid_email(email):
    local, _, domain = email.strip().partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


class Flow:
    def __init__(self, stage=WELCOME, name="", now=0.0):
        self.stage = stage
        self.name = name
        self.since = now
        self.email = ""
        self.password = ""
        self.show_password = False
        self.focus = "email"
        self.error = ""
        self.finished = False

    # ---------- movement ----------
    def go(self, stage, now):
        self.stage = stage
        self.since = now
        self.error = ""

    def advance(self, now):
        """Next screen; after the last one the flow is finished."""
        nxt = NEXT_STAGE.get(self.stage)
        if nxt is None:
            self.finished = True
        else:
            self.go(nxt, now)
        return self.stage

    def update(self, now):
        if self.stage == BACK and now - self.since >= BACK_SHOW + BACK_FADE_OUT:
            self.finished = True
        elif self.stage == READY and now - self.since >= READY_SECONDS:
            self.finished = True

    # ---------- sign in (stays on this computer; nothing is sent anywhere) ----------
    def type_text(self, text):
        text = "".join(c for c in text if c.isprintable())
        if not text or self.stage != LOGIN:
            return
        if self.focus == "email":
            self.email = (self.email + text.replace(" ", ""))[:80]
        else:
            self.password = (self.password + text)[:64]
        self.error = ""

    def backspace(self):
        if self.focus == "email":
            self.email = self.email[:-1]
        else:
            self.password = self.password[:-1]
        self.error = ""

    def next_field(self):
        self.focus = "password" if self.focus == "email" else "email"

    def submit(self, now):
        """The Continue button. Returns True if it moved on."""
        if not valid_email(self.email):
            self.focus = "email"
            self.error = "Enter your email address"
            return False
        if len(self.password) < 8:
            self.focus = "password"
            self.error = "Use at least 8 characters"
            return False
        self.name = name_from_email(self.email)
        self.advance(now)
        return True

    def sign_in_with_provider(self, now):
        """Google / Apple: there is no real account behind this in the desktop app yet."""
        self.advance(now)

    # ---------- fades for the welcome-back screen ----------
    def back_alpha(self, now):
        t = now - self.since
        if t < BACK_FADE_IN:
            return max(0.0, t / BACK_FADE_IN)
        if t > BACK_SHOW:
            return max(0.0, 1.0 - (t - BACK_SHOW) / BACK_FADE_OUT)
        return 1.0
