"""macOS overlay setup, checked with stand-ins for the real Cocoa objects."""

import pytest

from mosign import macos


class FakeNSPanel:
    def __init__(self, fail=()):
        self.calls = []
        self.mask = 0b1
        self.fail = set(fail)

    def __getattr__(self, name):
        if not name.endswith("_") and name not in ("orderFrontRegardless",):
            raise AttributeError(name)

        def method(*args):
            if name in self.fail:
                raise RuntimeError("nope")
            self.calls.append((name, *args))
            if name == "setStyleMask_":
                self.mask = args[0]
        return method

    def styleMask(self):
        return self.mask

    # NSPanel-only method (its presence marks this as a panel)
    def setFloatingPanel_(self, value):
        self.calls.append(("setFloatingPanel_", value))


class FakeNSApp:
    def __init__(self):
        self.policies = []

    def setActivationPolicy_(self, p):
        self.policies.append(p)


@pytest.fixture
def cocoa(monkeypatch):
    win, app = FakeNSPanel(), FakeNSApp()
    monkeypatch.setattr(macos, "_nswindow", lambda widget: win)
    monkeypatch.setattr(macos, "_nsapp", lambda: app)
    return win, app


def called(win, name):
    return [c[1:] for c in win.calls if c[0] == name]


def test_does_nothing_off_mac(cocoa):
    win, app = cocoa
    assert macos.configure_overlay(object(), platform="win32") is False
    assert win.calls == [] and app.policies == []


def test_overlay_joins_every_space_including_full_screen(cocoa):
    win, app = cocoa
    assert macos.configure_overlay(object(), platform="darwin")
    behavior = called(win, "setCollectionBehavior_")[0][0]
    assert behavior & macos.FULL_SCREEN_AUXILIARY and behavior & macos.CAN_JOIN_ALL_SPACES
    assert called(win, "setLevel_") == [(macos.NS_STATUS_WINDOW_LEVEL,)]
    assert called(win, "setIgnoresMouseEvents_") == [(True,)]
    assert called(win, "setHidesOnDeactivate_") == [(False,)]
    assert win.mask & macos.NONACTIVATING_PANEL and win.mask & 0b1   # added, kept old bits


def test_briefly_becomes_accessory_then_dock_icon_returns(cocoa):
    win, app = cocoa
    scheduled = []
    macos.configure_overlay(object(), schedule=lambda ms, fn: scheduled.append((ms, fn)),
                            platform="darwin")
    assert app.policies == [macos.POLICY_ACCESSORY]
    # the panel is shown while Mosign is an accessory app
    assert ("orderFrontRegardless",) in win.calls
    assert len(scheduled) == 1 and scheduled[0][0] > 0
    scheduled[0][1]()
    assert app.policies == [macos.POLICY_ACCESSORY, macos.POLICY_REGULAR]


def test_hide_dock_icon_stays_accessory(cocoa):
    win, app = cocoa
    scheduled = []
    macos.configure_overlay(object(), schedule=lambda ms, fn: scheduled.append(fn),
                            hide_dock_icon=True, platform="darwin")
    assert app.policies == [macos.POLICY_ACCESSORY] and scheduled == []


def test_one_failing_setting_does_not_stop_the_rest(cocoa, capsys):
    win, app = cocoa
    win.fail = {"setLevel_"}
    assert macos.configure_overlay(object(), platform="darwin")
    assert called(win, "setCollectionBehavior_")
    assert app.policies[-1] == macos.POLICY_REGULAR
    assert "level" in capsys.readouterr().out


def test_missing_pyobjc_is_harmless(monkeypatch):
    def boom(widget):
        raise ImportError("No module named objc")

    monkeypatch.setattr(macos, "_nswindow", boom)
    assert macos.configure_overlay(object(), platform="darwin") is False
