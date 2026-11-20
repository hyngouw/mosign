import pytest

from handgen import ALL, make_hand
from mosign.gestures import (
    Stabilizer,
    classify_landmarks,
    fingers_extended,
    pointing_direction,
)


@pytest.mark.parametrize("rotation", [0, 45, 90, 180, -90])
@pytest.mark.parametrize("fingers", [
    set(), {"index"}, {"index", "middle"}, {"thumb", "pinky"},
    {"index", "middle", "ring"}, ALL, {"index", "pinky"}, {"pinky"},
])
def test_fingers_extended_any_rotation(fingers, rotation):
    assert fingers_extended(make_hand(fingers, rotation)) == fingers


@pytest.mark.parametrize("thumb", [False, True])
@pytest.mark.parametrize("rotation,label", [
    (0, "scroll_up"),       # finger points up
    (15, "scroll_up"),      # a little tilt is fine
    (180, "scroll_down"),   # finger points down
    (-165, "scroll_down"),
    (90, "prev_tab"),       # finger points left
    (-90, "next_tab"),      # finger points right
])
def test_point_direction_maps_to_action(rotation, label, thumb):
    fingers = {"index", "thumb"} if thumb else {"index"}
    assert classify_landmarks(make_hand(fingers, rotation)) == label


def test_diagonal_point_is_ignored():
    assert classify_landmarks(make_hand({"index"}, 45)) is None
    assert classify_landmarks(make_hand({"index"}, -135)) is None


def test_finger_aimed_at_camera_is_ignored():
    hand = make_hand({"index"}, 0)
    # squash the index finger toward its knuckle (foreshortened)
    kx, ky = hand[5]
    for i in (6, 7, 8):
        x, y = hand[i]
        hand[i] = (kx + (x - kx) * 0.3, ky + (y - ky) * 0.3)
    assert pointing_direction(hand) is None


@pytest.mark.parametrize("fingers", [
    set(), ALL, {"index", "middle"}, {"index", "middle", "ring"}, {"thumb", "pinky"},
])
def test_other_poses_do_nothing(fingers):
    assert classify_landmarks(make_hand(fingers)) is None


def test_no_hand():
    assert classify_landmarks(None) is None


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
