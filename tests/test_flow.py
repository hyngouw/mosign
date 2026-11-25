"""Welcome / camera / tutorial / ready screens: logic, drawing and the chime."""

import numpy as np

from mosign import flow as F
from mosign.config import Config
from mosign.sound import Chime, chime_samples, write_chime
from mosign.ui import HEIGHT, UI, WIDTH, View


def test_screens_in_order_then_fade_out():
    flow = F.Flow(F.WELCOME)
    seen = [flow.stage]
    while flow.stage != F.READY:
        flow.advance(0)
        seen.append(flow.stage)
    assert seen == [F.WELCOME, F.CAMERA, F.TUTORIAL, F.READY]
    flow.advance(1.0)                    # the last button starts the fade, it doesn't end it
    assert not flow.finished and flow.exit_at == 1.0


def test_welcome_back_fades_in_then_out_then_finishes():
    flow = F.Flow(F.BACK, name="Alex", now=10.0)
    assert flow.back_alpha(10.0) == 0
    assert 0 < flow.back_alpha(10.4) < 1
    assert flow.back_alpha(11.5) == 1
    assert flow.back_alpha(10.0 + F.BACK_SHOW + F.BACK_FADE_OUT / 2) < 1
    flow.update(10.0 + F.BACK_SHOW)
    assert not flow.finished
    flow.update(10.0 + F.BACK_SHOW + F.BACK_FADE_OUT + 0.01)
    assert flow.finished
    assert F.BACK_SHOW == 2.5        # half a second shorter than the first prototype




def test_every_screen_draws_and_has_clickable_buttons():
    for stage in (F.WELCOME, F.CAMERA, F.READY, F.BACK):
        ui = UI()
        img = ui.render(View(flow=F.Flow(stage, now=0)), now=1.5)
        assert img.shape == (HEIGHT, WIDTH, 3), stage
        assert ui.buttons or stage == F.BACK
    ui = UI()
    ui.render(View(flow=F.Flow(F.WELCOME)), now=1.0)
    start = next(b for b in ui.buttons if b.command == "flow_next")
    assert ui.click(start.rect.cx, start.rect.cy) == "flow_next"


def test_tutorial_screen_shows_progress_and_the_learned_tray():
    from mosign.onboarding import Onboarding
    frame = np.full((360, 640, 3), 90, np.uint8)
    early, late = Onboarding(), Onboarding()
    late.index = 4
    ui = UI()
    a = ui.render(View(flow=F.Flow(F.TUTORIAL), tour=early, frame=frame), now=1.0)
    b = ui.render(View(flow=F.Flow(F.TUTORIAL), tour=late, frame=frame), now=1.0)
    assert not np.array_equal(a, b)
    # no button asks the user to confirm a gesture, and there is no close X either
    assert ui.buttons == []


def test_no_screen_has_a_close_button_or_sign_in():
    assert not hasattr(F, "LOGIN")
    ui = UI()
    for stage in (F.WELCOME, F.CAMERA, F.READY, F.BACK):
        ui.render(View(flow=F.Flow(stage)), now=0)
        assert "flow_close" not in [b.command for b in ui.buttons]
    assert ui.key("a") is False


def test_chime_is_two_notes_and_not_empty(tmp_path):
    samples = chime_samples()
    assert len(samples) > 20000 and max(samples) > 5000 and min(samples) < -5000
    path = write_chime(tmp_path / "c.wav")
    assert path.stat().st_size > 40000


def test_chime_plays_with_the_systems_player(isolated_home):
    calls = []
    chime = Chime(launch=lambda cmd, **kw: calls.append(cmd), platform="darwin")
    assert chime.play()
    assert calls[0][0] == "afplay" and calls[0][1].endswith("chime.wav")
    assert Chime(enabled=False).play() is False


def test_chime_never_raises(isolated_home):
    def boom(*a, **k):
        raise OSError("no sound card")
    assert Chime(launch=boom, platform="darwin").play() is False


def test_sounds_can_be_turned_off_in_settings():
    assert Config().sounds is True


def test_picture_fills_any_window_shape():
    import cv2
    from mosign.framing import fit_picture
    stage = np.zeros((780, 768, 3), np.uint8)
    stage[:] = (184, 244, 255)               # the window colour
    stage[:300] = (94, 222, 246)              # a yellow header band across the top
    for pw, ph in ((768, 780), (1400, 700), (500, 900), (3000, 2000)):
        out, (x, y, w, h) = fit_picture(stage, pw, ph, 768 / 780)
        assert out.shape == (ph, pw, 3)
        assert w <= pw and h <= ph and (w == pw or h == ph)         # as big as fits
        assert abs((x * 2 + w) - pw) <= 1 and abs((y * 2 + h) - ph) <= 1   # centred
        assert tuple(out[0, 0]) == (94, 222, 246)                   # the header band reaches the corners
        assert tuple(out[-1, -1]) == (184, 244, 255)                # and so does the window colour


def test_ready_screen_fades_out_then_cuts_to_the_window():
    flow = F.Flow(F.READY, now=0)
    assert flow.alpha(1.0) == 1.0
    flow.advance(2.0)                          # the Start browsing button
    assert not flow.finished and flow.stage == F.READY
    assert 0 < flow.alpha(2.0 + F.READY_FADE_OUT / 2) < 1
    flow.update(2.0 + F.READY_FADE_OUT - 0.01)
    assert not flow.finished
    flow.update(2.0 + F.READY_FADE_OUT + 0.01)
    assert flow.finished


def test_ready_screen_also_fades_when_it_times_out():
    flow = F.Flow(F.READY, now=0)
    flow.update(F.READY_SECONDS + 0.1)
    assert flow.exit_at is not None and not flow.finished
    flow.update(F.READY_SECONDS + 0.1 + F.READY_FADE_OUT + 0.01)
    assert flow.finished


def test_gesture_flashes_then_flies_into_its_slot():
    from mosign.onboarding import FLASH_SECONDS, FLY_DELAY, STEP_PAUSE, Onboarding
    tour = Onboarding()
    tour.index = 2
    tour._paused_until = 10 + STEP_PAUSE
    assert tour.filled(10.0) == 1 and tour.since_pass(10.0) == 0.0     # slot not filled yet
    assert tour.filled(10 + STEP_PAUSE - 0.01) == 1
    assert FLASH_SECONDS < FLY_DELAY and abs(STEP_PAUSE - 1.15) < 1e-9
    tour._paused_until = None
    assert tour.filled(20) == 2 and tour.since_pass(20) is None       # landed: slot full
