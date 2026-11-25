"""Find where the browser's tabs are on screen, so the cat can sit on the active one.

On macOS this reads the front window through the Accessibility API (the same
permission Mosign already needs to send scroll / tab keys). Browsers show
their tab strip there as an "AXTabGroup" whose tabs are radio buttons; the
selected tab has AXValue 1. That works for Chrome, Safari, Edge, Brave and
Firefox. Anywhere else (Windows, a full-screen browser with its tab strip
hidden, a non-browser app) there are no tabs and the cat stays in its
corner.

Reading another app can be slow, so it happens on a background thread a few
times a second, and right after a tab switch (poke()).
"""

import os
import sys
import threading
import time
from dataclasses import dataclass, field

TAB_ROLES = ("AXRadioButton", "AXTab")
MAX_DEPTH = 10
MAX_NODES = 800
KEEP = object()   # query result meaning "Mosign itself is in front: keep the last answer"


@dataclass
class TabInfo:
    tabs: list = field(default_factory=list)   # [(x, y, w, h)] in screen points
    active: int = -1
    stamp: float = 0.0

    @property
    def active_rect(self):
        if 0 <= self.active < len(self.tabs):
            return self.tabs[self.active]
        return None

    def neighbour(self, direction):
        """Index of the tab to the right (+1) / left (-1), wrapping like browsers do."""
        if not self.tabs or self.active < 0:
            return -1
        return (self.active + direction) % len(self.tabs)


def find_tabs(root, attr):
    """Search an accessibility tree for the tab strip.

    attr(element, name) returns the attribute's value or None; names used:
    AXRole, AXChildren, AXPosition (x, y), AXSize (w, h), AXValue, AXSelected.
    Returns TabInfo, or None if there's no tab strip.
    """
    best = None
    queue = [(root, 0)]
    seen = 0
    while queue and seen < MAX_NODES:
        node, depth = queue.pop(0)
        seen += 1
        role = attr(node, "AXRole")
        children = attr(node, "AXChildren") or []
        if role == "AXTabGroup":
            tabs = [c for c in children if attr(c, "AXRole") in TAB_ROLES]
            if tabs and (best is None or len(tabs) > len(best)):
                best = tabs
            continue
        if depth < MAX_DEPTH:
            queue.extend((c, depth + 1) for c in children)
    if not best:
        return None

    rects, active = [], -1
    for tab in best:
        pos, size = attr(tab, "AXPosition"), attr(tab, "AXSize")
        if not pos or not size or size[0] <= 0 or size[1] <= 0:
            continue
        if attr(tab, "AXValue") in (1, True) or attr(tab, "AXSelected") is True:
            active = len(rects)
        rects.append((float(pos[0]), float(pos[1]), float(size[0]), float(size[1])))
    if not rects:
        return None
    order = sorted(range(len(rects)), key=lambda i: (rects[i][1], rects[i][0]))  # left to right
    if active >= 0:
        active = order.index(active)
    return TabInfo([rects[i] for i in order], active)


# ---------------- macOS ----------------

def _mac_query():
    """Tabs of the front app's focused window (None if none, KEEP if it's Mosign)."""
    from AppKit import NSWorkspace
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        AXUIElementSetMessagingTimeout,
        AXValueGetValue,
        kAXValueCGPointType,
        kAXValueCGSizeType,
    )

    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None:
        return None
    pid = front.processIdentifier()
    if pid == os.getpid():
        return KEEP
    app = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(app, 0.3)   # never hang on a busy app

    def attr(elem, name):
        err, value = AXUIElementCopyAttributeValue(elem, name, None)
        if err != 0 or value is None:
            return None
        if name == "AXPosition":
            ok, p = AXValueGetValue(value, kAXValueCGPointType, None)
            return (p.x, p.y) if ok else None
        if name == "AXSize":
            ok, s = AXValueGetValue(value, kAXValueCGSizeType, None)
            return (s.width, s.height) if ok else None
        if name == "AXChildren":
            return list(value)
        if name in ("AXRole",):
            return str(value)
        return value

    window = attr(app, "AXFocusedWindow")
    if window is None:
        return None
    return find_tabs(window, attr)


def default_query():
    return _mac_query if sys.platform == "darwin" else None


class TabLocator:
    """Polls tab positions on a background thread. latest() never blocks."""

    def __init__(self, query=None, interval=0.4, clock=time.monotonic):
        self.query = query if query is not None else default_query()
        self.interval = interval
        self.clock = clock
        self._info = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self.failures = 0

    @property
    def available(self):
        return self.query is not None

    def start(self):
        if self.available and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="mosign-tabs", daemon=True)
            self._thread.start()
        return self

    def poke(self):
        """Look again soon (after a tab switch the browser needs a moment)."""
        self._wake.set()

    def latest(self):
        with self._lock:
            return self._info

    def refresh(self):
        """Run one query now (also used by tests)."""
        try:
            info = self.query()
        except Exception:
            self.failures += 1
            info = None
        if info is KEEP:
            return self.latest()
        if info is not None:
            info.stamp = self.clock()
        with self._lock:
            self._info = info
        return info

    def _run(self):
        while not self._stop.is_set():
            poked = self._wake.wait(self.interval)
            if self._stop.is_set():
                break
            if poked:
                self._wake.clear()
                time.sleep(0.12)   # let the browser finish switching
            self.refresh()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
