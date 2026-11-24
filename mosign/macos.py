"""macOS-only window tweaks (no-ops elsewhere or if PyObjC is missing).

PyObjC comes with pyautogui on macOS, so nothing extra is installed.
"""

import sys

NS_STATUS_WINDOW_LEVEL = 25           # above normal app windows (like the menu bar)
CAN_JOIN_ALL_SPACES = 1 << 0          # visible on every desktop / Space
STATIONARY = 1 << 4                   # doesn't slide away with Mission Control
IGNORES_CYCLE = 1 << 6                # not in Cmd-` window cycling
FULL_SCREEN_AUXILIARY = 1 << 8        # may appear next to full-screen apps

# NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical
ACTIVITY_OPTIONS = 0x00EFFFFF | 0xFF00000000


def _nswindow(widget):
    import objc

    view = objc.objc_object(c_void_p=int(widget.winId()))
    return view.window()


def configure_overlay(widget):
    """Keep the overlay above other apps, on every Space, ignoring the mouse."""
    if sys.platform != "darwin":
        return False
    try:
        win = _nswindow(widget)
        win.setLevel_(NS_STATUS_WINDOW_LEVEL)
        win.setCollectionBehavior_(CAN_JOIN_ALL_SPACES | STATIONARY | IGNORES_CYCLE
                                   | FULL_SCREEN_AUXILIARY)
        win.setHidesOnDeactivate_(False)   # Qt "tool" windows hide when Mosign isn't active
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(False)
        return True
    except Exception as exc:  # never crash over a cosmetic tweak
        print(f"Mosign: couldn't adjust the overlay window ({exc})")
        return False


def keep_app_awake():
    """Stop App Nap from slowing Mosign down while another app is in front.

    Returns a token that must be kept alive for as long as the app runs.
    """
    if sys.platform != "darwin":
        return None
    try:
        from Foundation import NSProcessInfo

        return NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            ACTIVITY_OPTIONS, "Watching the camera for hand gestures")
    except Exception:
        return None
