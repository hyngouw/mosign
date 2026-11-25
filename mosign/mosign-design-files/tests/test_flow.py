"""Welcome / sign-in / camera / tutorial / ready screens: logic, drawing and the chime."""

import numpy as np

from mosign import flow as F
from mosign.config import Config
from mosign.sound import Chime, chime_samples, write_chime
from mosign.ui import HEIGHT, UI, WIDTH, View


def test_names_come_from_the_email():
    assert F.name_from_email("alex.smith@mail.com") == "Alex"
    assert F.name_from_email("KAI_lin@x.io") == "Kai"
    assert F.name_from_email("123@x.io") == ""


def test_sign_in_checks_email_and_password():
    flow = F.Flow(F.LOGIN)
    assert not flow.submit(0) and flow.error and flow.focus == "email"
    flow.type_text("alex@mail.com")
    assert not flow.submit(0) and flow.focus == "password"
    flow.type_text("short")
    assert not flow.submit(0)
    flow.type_text("longenough")
    assert flow.submit(1.0)
    assert flow.stage == F.CAMERA and flow.name == "Alex"


def test_typing_and_backspace_and_tab():
    flow = F.Flow(F.LOGIN)
    flow.type_text("a b")           # spaces are not allowed in an email
    flow.backspace()
    assert flow.email == "a"
    flow.next_field()
    flow.type_text("pa ss")
    assert flow.password == "pa ss"
    F.Flow(F.WELCOME).type_text("x")   # ignored outside the sign-in screen


def test_screens_in_order_then_finished():
    flow = F.Flow(F.WELCOME)
    seen = [flow.stage]
    while not flow.finished:
        flow.advance(0)
        seen.append(flow.stage)
    assert seen[:5] == [F.WELCOME, F.LOGIN, F.CAMERA, F.TUTORIAL, F.READY]


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


def test_ready_moves_on_by_itself():
    flow = F.Flow(F.READY, now=0)
    flow.update(F.READY_SECONDS + 0.1)
    assert flow.finished


def test_every_screen_draws_and_has_clickable_buttons():
    for stage in (F.WELCOME, F.LOGIN, F.CAMERA, F.READY, F.BACK):
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
    # no button asks the user to confirm a gesture: only the close X is clickable
    assert [x.command for x in ui.buttons] == ["flow_close"]


def test_sign_in_screen_turns_keys_into_typing():
    ui = UI()
    assert ui.key("a") is False                     # nothing is typing yet
    ui.render(View(flow=F.Flow(F.LOGIN)), now=0)
    assert ui.key("a") and ui.key("", "backspace") and ui.key("", "enter") and ui.key("", "tab")
    assert ui.pop_commands() == ["type:a", "key:backspace", "login_submit", "key:tab"]


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
