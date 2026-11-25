import threading
import time

from mosign.tabs import KEEP, TabInfo, TabLocator, find_tabs


def node(role, children=(), pos=None, size=None, value=None):
    return {"AXRole": role, "AXChildren": list(children), "AXPosition": pos,
            "AXSize": size, "AXValue": value}


def attr(n, name):
    return n.get(name)


def tab(x, selected=False, y=40, w=200, h=34):
    return node("AXRadioButton", pos=(x, y), size=(w, h), value=1 if selected else 0)


def chrome_like(selected=1, n=4):
    tabs = [tab(80 + i * 210, i == selected) for i in range(n)]
    strip = node("AXTabGroup", tabs + [node("AXButton", pos=(900, 40), size=(30, 30))])
    toolbar = node("AXToolbar", [node("AXButton"), node("AXTextField")])
    return node("AXWindow", [node("AXGroup", [node("AXGroup", [strip, toolbar])])])


def test_finds_tabs_and_active_one():
    info = find_tabs(chrome_like(selected=2), attr)
    assert len(info.tabs) == 4 and info.active == 2
    assert info.active_rect == (500.0, 40.0, 200.0, 34.0)


def test_tabs_sorted_left_to_right_even_if_tree_order_differs():
    tabs = [tab(500), tab(80, True), tab(290)]
    info = find_tabs(node("AXWindow", [node("AXTabGroup", tabs)]), attr)
    assert [t[0] for t in info.tabs] == [80, 290, 500] and info.active == 0


def test_safari_style_selected_flag():
    t = tab(100)
    t["AXValue"] = None
    t["AXSelected"] = True
    info = find_tabs(node("AXWindow", [node("AXTabGroup", [tab(0), t])]), attr)
    assert info.active == 1


def test_no_tab_strip():
    assert find_tabs(node("AXWindow", [node("AXGroup", [node("AXButton")])]), attr) is None
    assert find_tabs(node("AXWindow", [node("AXTabGroup", [node("AXButton")])]), attr) is None


def test_hidden_tabs_with_no_size_are_skipped():
    hidden = tab(0)
    hidden["AXSize"] = (0, 0)
    info = find_tabs(node("AXWindow", [node("AXTabGroup", [hidden, tab(10, True)])]), attr)
    assert len(info.tabs) == 1 and info.active == 0


def test_picks_the_biggest_tab_group():
    small = node("AXTabGroup", [tab(0, True)])            # e.g. a settings pane
    big = node("AXTabGroup", [tab(0), tab(210, True), tab(420)])
    info = find_tabs(node("AXWindow", [small, big]), attr)
    assert len(info.tabs) == 3 and info.active == 1


def test_huge_trees_stop_early():
    deep = node("AXGroup")
    cur = deep
    for _ in range(50):
        nxt = node("AXGroup")
        cur["AXChildren"] = [nxt]
        cur = nxt
    cur["AXChildren"] = [node("AXTabGroup", [tab(0, True)])]
    assert find_tabs(deep, attr) is None      # too deep: give up rather than crawl


def test_neighbour_wraps():
    info = TabInfo([(0, 0, 1, 1)] * 3, active=2)
    assert info.neighbour(1) == 0 and info.neighbour(-1) == 1
    assert TabInfo().neighbour(1) == -1


def test_locator_refresh_keep_and_errors():
    answers = [find_tabs(chrome_like(), attr), KEEP, RuntimeError("busy"), None]

    def query():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    loc = TabLocator(query=query, clock=lambda: 5.0)
    assert loc.refresh().active == 1 and loc.latest().stamp == 5.0
    assert loc.refresh().active == 1          # Mosign in front: keep last answer
    assert loc.refresh() is None and loc.failures == 1
    assert loc.refresh() is None and loc.latest() is None


def test_locator_thread_polls_and_poke_wakes_it():
    calls = []
    done = threading.Event()

    def query():
        calls.append(time.monotonic())
        if len(calls) >= 2:
            done.set()
        return TabInfo([(0, 0, 10, 10)], 0)

    loc = TabLocator(query=query, interval=5.0).start()
    try:
        loc.poke()
        loc.poke()
        time.sleep(0.3)
        loc.poke()
        assert done.wait(3.0)                 # pokes wake it long before 5 s
        assert loc.latest().active == 0
    finally:
        loc.stop()


def test_unavailable_off_mac():
    loc = TabLocator(query=None)
    loc.query = None
    assert not loc.available
    assert loc.start() is loc and loc._thread is None
