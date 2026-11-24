"""macOS-only window tweaks (no-ops elsewhere or if PyObjC is missing).

PyObjC comes with pyautogui on macOS, so nothing extra is installed.

Why the overlay needs special handling over full-screen apps: macOS puts
each full-screen app on its own Space, and only lets windows from
"accessory" (background, no Dock icon) apps float there. So while the
overlay window is set up we briefly make Mosign an accessory app, which
lets the overlay join full-screen Spaces, then switch back so the Dock
icon returns. This is the same trick Electron apps use. With
`hide_dock_icon` Mosign stays an accessory app for good, which is the most
reliable option.
"""

import sys

NS_STATUS_WINDOW_LEVEL = 25           # above normal app windows (like the menu bar)
CAN_JOIN_ALL_SPACES = 1 << 0          # visible on every desktop / Space
STATIONARY = 1 << 4                   # doesn't slide away with Mission Control
IGNORES_CYCLE = 1 << 6                # not in Cmd-` window cycling
FULL_SCREEN_AUXILIARY = 1 << 8        # may appear over full-screen apps
OVERLAY_BEHAVIOR = CAN_JOIN_ALL_SPACES | STATIONARY | IGNORES_CYCLE | FULL_SCREEN_AUXILIARY

NONACTIVATING_PANEL = 1 << 7          # a panel that never makes Mosign the active app
POLICY_REGULAR = 0                    # normal app with a Dock icon
POLICY_ACCESSORY = 1                  # background app: no Dock icon, can float over full screen
RESTORE_DOCK_ICON_MS = 400

# NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical
ACTIVITY_OPTIONS = 0x00EFFFFF | 0xFF00000000


def _nswindow(widget):
    import objc

    view = objc.objc_object(c_void_p=int(widget.winId()))
    return view.window()


def _nsapp():
    from AppKit import NSApplication

    return NSApplication.sharedApplication()


def configure_overlay(widget, schedule=None, hide_dock_icon=False, platform=None):
    """Keep the overlay above every app, on every Space (full-screen ones too).

    schedule(ms, fn) runs fn later on the GUI thread (QTimer.singleShot);
    it's used to bring the Dock icon back once the overlay is in place.
    Returns True if the window was adjusted.
    """
    if (platform or sys.platform) != "darwin":
        return False
    try:
        win = _nswindow(widget)
        app = _nsapp()
    except Exception as exc:  # never crash over a cosmetic tweak
        print(f"Mosign: couldn't adjust the overlay window ({exc})")
        return False

    def attempt(what, fn):
        try:
            fn()
        except Exception as exc:
            print(f"Mosign: overlay setting '{what}' failed ({exc})")

    # Qt "tool" windows are NSPanels; make it one that never takes focus.
    if hasattr(win, "setFloatingPanel_"):
        attempt("non-activating panel",
                lambda: win.setStyleMask_(win.styleMask() | NONACTIVATING_PANEL))
        attempt("floating panel", lambda: win.setFloatingPanel_(True))
        attempt("works when modal", lambda: win.setWorksWhenModal_(True))
    attempt("level", lambda: win.setLevel_(NS_STATUS_WINDOW_LEVEL))
    attempt("all spaces", lambda: win.setCollectionBehavior_(OVERLAY_BEHAVIOR))
    attempt("stay visible", lambda: win.setHidesOnDeactivate_(False))
    attempt("click-through", lambda: win.setIgnoresMouseEvents_(True))
    attempt("no shadow", lambda: win.setHasShadow_(False))

    # The full-screen part: become an accessory app while the panel shows.
    attempt("accessory app", lambda: app.setActivationPolicy_(POLICY_ACCESSORY))
    attempt("show", lambda: win.orderFrontRegardless())
    if not hide_dock_icon:
        def restore():
            attempt("dock icon", lambda: app.setActivationPolicy_(POLICY_REGULAR))

        if schedule is not None:
            schedule(RESTORE_DOCK_ICON_MS, restore)
        else:
            restore()
    return True


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
