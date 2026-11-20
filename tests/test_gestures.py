import pytest

from handgen import ALL, make_hand
from mosign.gestures import Stabilizer, classify, fingers_extended


@pytest.mark.parametrize("rotation", [0, 45, 90, 180, -90])
@pytest.mark.parametrize("fingers", [
    set(), {"index"}, {"index", "middle"}, {"thumb", "pinky"},
    {"index", "middle", "ring"}, ALL, {"index", "pinky"}, {"pinky"},
])
def test_fingers_extended_any_rotation(fingers, rotation):
    assert fingers_extended(make_hand(fingers, rotation)) == fingers


def test_classify_known_gestures():
    assert classify({"index"}) == "scroll_up"
    assert classify({"index", "middle"}) == "scroll_down"
    assert classify(ALL) == "stop"
    assert classify({"index", "middle", "ring"}) == "next_tab"
    assert classify({"thumb", "pinky"}) == "prev_tab"
    assert classify(set()) is None


def test_stabilizer_needs_steady_frames():
    s = Stabilizer(3)
    assert s.update("a") is None
    assert s.update("a") is None
    assert s.update("a") == "a"
    # one noisy frame doesn't change the confirmed label
    assert s.update("b") == "a"
    assert s.update("a") == "a"
    s.update(None)
    s.update(None)
    assert s.update(None) is None
