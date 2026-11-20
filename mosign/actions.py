"""The things a gesture can do on the computer.

PyAutoGuiActions talks to the real OS. RecordingActions just writes down what
would have happened, which is used by the tests and by practice mode.
"""


class PyAutoGuiActions:
    def __init__(self):
        import pyautogui  # imported here so tests never need a display

        pyautogui.PAUSE = 0        # no built-in delay after each action
        pyautogui.FAILSAFE = True  # slam the mouse into a corner to abort
        self._pg = pyautogui

    def scroll(self, amount):
        self._pg.scroll(amount)

    def next_tab(self):
        self._pg.hotkey("ctrl", "tab")

    def prev_tab(self):
        self._pg.hotkey("ctrl", "shift", "tab")


class RecordingActions:
    def __init__(self):
        self.calls = []

    def scroll(self, amount):
        self.calls.append(("scroll", amount))

    def next_tab(self):
        self.calls.append(("next_tab",))

    def prev_tab(self):
        self.calls.append(("prev_tab",))
