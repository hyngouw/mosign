import numpy as np
import pytest

from mosign.cat import CatFace, CatMotion, CatSprite, load_layers, to_premultiplied_bgra


def run_face(face, seconds, t0=0.0, **kw):
    t = t0
    for _ in range(int(seconds * 30)):
        t += 1 / 30
        face.update(t, **kw)
    return t


def test_all_layers_ship_with_the_app():
    layers = load_layers()
    for name in ("tail", "body", "foot", "head", "ear", "whiskers", "nose",
                 "eyes", "eyes_2", "mouth_1", "mouth_2"):
        assert layers[name].size == (420, 425)


def test_sleeps_when_paused_and_wakes_wide_eyed():
    f = CatFace()
    run_face(f, 0.5, awake=False)
    assert f.asleep and f.eyes == "closed" and f.zzz() and not f.mouth_open
    f.update(1.0, events=["wake"], awake=True)
    assert f.eyes == "wide" and not f.zzz()
    run_face(f, 1.0, t0=1.0)
    assert f.eyes in ("open", "closed")   # back to normal (maybe mid-blink)


def test_blinks_now_and_then():
    f = CatFace()
    states = set()
    t = 0.0
    for _ in range(30 * 10):
        t += 1 / 30
        f.update(t)
        states.add(f.eyes)
    assert states == {"open", "closed"}


def test_looks_up_and_down_while_scrolling():
    f = CatFace()
    run_face(f, 1.0, scroll_mode="up")
    assert f.look < -0.8
    run_face(f, 1.0, t0=2, scroll_mode="down")
    assert f.look > 0.8


def test_mouth_opens_on_tab_switch():
    f = CatFace()
    f.update(0.0, events=["next_tab"])
    assert f.mouth_open
    f.update(1.0)
    assert not f.mouth_open


def test_breathes_slower_and_deeper_asleep():
    awake, asleep = CatFace(), CatFace()
    a = [awake.update(i / 30) or awake.breath for i in range(90)]
    b = [asleep.update(i / 30, awake=False) or asleep.breath for i in range(90)]
    assert max(b) > max(a) * 1.5


@pytest.mark.parametrize("height", [64, 128])
def test_sprite_feet_stay_on_the_anchor(height):
    s = CatSprite(height)
    for squash in (0.0, 0.18, -0.1):
        img = np.asarray(s.render(CatFace(), squash=squash))
        ax, ay = s.anchor
        rows = np.where(img[..., 3].max(axis=1) > 128)[0]
        assert abs(rows.max() - ay) <= max(3, height * 0.04)     # feet on the ground
        cols = np.where(img[int(ay) - 3, :, 3] > 128)[0]
        assert abs(cols.mean() - ax) < height * 0.2               # roughly centred


def test_sprite_image_is_transparent_around_the_cat():
    img = CatSprite(64).render_bgra(CatFace())
    assert img[0, 0, 3] == 0 and img[..., 3].max() == 255
    assert np.all(img[..., :3] <= img[..., 3:4])                 # premultiplied


def test_sleeping_sprite_draws_zs_and_closed_eyes():
    s = CatSprite(100)
    awake, asleep = CatFace(), CatFace()
    awake.update(0.0)
    run_face(asleep, 0.5, awake=False)
    a, b = np.asarray(s.render(awake)), np.asarray(s.render(asleep))
    top = int(s.anchor[1] - 100)
    assert b[:top, :, 3].max() > a[:top, :, 3].max()   # Z's above the head


def test_premultiply():
    from PIL import Image
    im = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
    px = to_premultiplied_bgra(im)[0, 0]
    assert tuple(px) == (25, 50, 100, 128)


def test_jump_arcs_to_the_target_and_lands():
    m = CatMotion(0, 100)
    assert m.go(400, 100, now=0.0)
    ys, t = [], 0.0
    while m.jumping and t < 2:
        t += 1 / 60
        m.update(t)
        ys.append(m.y)
    assert not m.jumping and (m.x, m.y) == (400, 100)
    assert min(ys) < 100 - 40                      # it went up in an arc
    m.update(t + 0.05)
    assert m.squash > 0                            # squish on landing
    m.update(t + 1)
    assert m.squash == 0


def test_small_moves_follow_without_jumping():
    m = CatMotion(0, 0)
    assert not m.go(2, 1, now=0.0) and (m.x, m.y) == (0, 0)   # under the threshold
    assert not m.go(5, 2, now=0.0) and (m.x, m.y) == (5, 2)   # window nudged: follow


def test_hop_in_place_returns_home():
    m = CatMotion(50, 50)
    m.hop(-1, now=0.0)
    m.update(0.19)
    assert m.x < 50 and m.y < 50 and m.lean < 0
    m.update(1.0)
    assert (m.x, m.y) == (50, 50)
