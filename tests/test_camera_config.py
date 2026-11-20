from mosign.camera import LOST_AFTER_FAILURES, Camera
from mosign.config import Config, config_path


class Cap:
    def __init__(self, ok=True, frames=None):
        self.ok = ok
        self.frames = frames   # None = endless
        self.released = False

    def isOpened(self):
        return self.ok

    def read(self):
        if not self.ok or self.frames == 0:
            return False, None
        if self.frames:
            self.frames -= 1
        return True, "frame"

    def release(self):
        self.released = True


def opener_for(working):
    return lambda i: Cap(ok=i in working)


def test_swap_skips_missing_cameras_and_wraps():
    cam = Camera(0, opener=opener_for({0, 3}), max_cameras=5)
    assert cam.label == "Camera 0"
    assert cam.next_camera() and cam.index == 3
    assert cam.next_camera() and cam.index == 0


def test_swap_with_only_one_camera_keeps_it():
    cam = Camera(0, opener=opener_for({0}), max_cameras=4)
    assert not cam.next_camera()
    assert cam.index == 0 and cam.is_open


def test_start_with_missing_camera():
    cam = Camera(2, opener=opener_for({0}), max_cameras=4)
    assert not cam.is_open and cam.read() is None and cam.label == "No camera"
    assert cam.next_camera() and cam.index == 0


def test_camera_counts_as_lost_after_many_failures():
    caps = []

    def opener(i):
        c = Cap(frames=2)  # 1 read used by the open check
        caps.append(c)
        return c

    cam = Camera(0, opener=opener)
    assert cam.read() == "frame"
    for _ in range(LOST_AFTER_FAILURES):
        assert cam.read() is None
    assert not cam.is_open and caps[0].released


def test_config_roundtrip(isolated_home):
    cfg = Config.load()
    assert cfg.camera_index == 0
    cfg.camera_index = 2
    cfg.scroll_amount = 5
    cfg.save()
    again = Config.load()
    assert again.camera_index == 2 and again.scroll_amount == 5
    assert config_path().parent == isolated_home


def test_config_survives_bad_files(isolated_home):
    isolated_home.mkdir(parents=True, exist_ok=True)
    config_path().write_text("{not json")
    assert Config.load() == Config()
    config_path().write_text('{"camera_index": "oops", "unknown": 1, "scroll_amount": 4}')
    cfg = Config.load()
    assert cfg.camera_index == 0 and cfg.scroll_amount == 4
    config_path().write_text("[1, 2]")
    assert Config.load() == Config()


def test_bool_setting_ignores_string_junk(isolated_home):
    isolated_home.mkdir(parents=True, exist_ok=True)
    config_path().write_text('{"menu_visible": "false"}')
    assert Config.load().menu_visible is True
    config_path().write_text('{"menu_visible": false}')
    assert Config.load().menu_visible is False
