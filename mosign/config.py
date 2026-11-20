"""User settings, saved as JSON in ~/.mosign/config.json."""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def app_home():
    """Folder for settings and downloaded models (override with MOSIGN_HOME)."""
    return Path(os.environ.get("MOSIGN_HOME", Path.home() / ".mosign"))


def config_path():
    return app_home() / "config.json"


@dataclass
class Config:
    camera_index: int = 0
    scroll_amount: int = 1       # per frame; raise on macOS if scrolling feels slow
    stable_frames: int = 3       # gesture must be steady this many frames to count
    tab_cooldown: float = 1.0    # seconds between tab switches
    hold_seconds: float = 1.0    # how long to hold the special gestures
    menu_visible: bool = True    # gesture reference menu in the top right
    onboarding_complete: bool = False  # first-run tour finished

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else config_path()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        cfg = cls()
        for f in fields(cls):
            if f.name in data:
                value = data[f.name]
                if isinstance(f.default, bool) and not isinstance(value, bool):
                    continue  # bool("false") would be True; skip junk
                try:
                    setattr(cfg, f.name, type(f.default)(value))
                except (TypeError, ValueError):
                    pass  # keep the default for a bad value
        return cfg

    def save(self, path=None):
        path = Path(path) if path else config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2))
        except OSError:
            pass  # settings are a convenience; never crash over them
