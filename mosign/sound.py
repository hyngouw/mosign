"""The success chime: two soft notes (E5 then A5), like the prototype's.

The sound is generated once as a small WAV file in the settings folder and
played with whatever the operating system offers, so there is nothing extra
to install: afplay on macOS, winsound on Windows, paplay/aplay on Linux.
Playing never blocks the camera loop and never raises.
"""

import math
import shutil
import struct
import subprocess
import sys
import wave

from mosign.config import app_home

RATE = 44100
NOTES = [(659.25, 0.00), (880.00, 0.11)]   # (Hz, start second)
LENGTH = 0.65


def chime_samples():
    """Mono 16-bit samples: each note rings in quickly and fades out."""
    count = int(RATE * LENGTH)
    out = [0.0] * count
    for freq, start in NOTES:
        first = int(start * RATE)
        for i in range(first, count):
            t = (i - first) / RATE
            attack = min(1.0, t / 0.012)
            out[i] += 0.30 * attack * math.exp(-t * 6.5) * math.sin(2 * math.pi * freq * t)
    peak = max(abs(v) for v in out) or 1.0
    scale = 0.8 * 32767 / max(peak, 0.8)
    return [int(max(-1.0, min(1.0, v)) * scale) for v in out]


def write_chime(path):
    samples = chime_samples()
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return path


class Chime:
    def __init__(self, enabled=True, launch=subprocess.Popen, platform=sys.platform):
        self.enabled = enabled
        self._launch = launch
        self._platform = platform
        self._path = None
        self.plays = 0

    def _file(self):
        if self._path is None or not self._path.exists():
            self._path = app_home() / "chime.wav"
            self._path.parent.mkdir(parents=True, exist_ok=True)
            write_chime(self._path)
        return self._path

    def play(self):
        if not self.enabled:
            return False
        self.plays += 1
        try:
            path = self._file()
            if self._platform == "darwin":
                self._launch(["afplay", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            elif self._platform.startswith("win"):
                import winsound
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                for tool in ("paplay", "aplay", "play"):
                    if shutil.which(tool):
                        self._launch([tool, str(path)], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                        break
                else:
                    return False
            return True
        except Exception:
            return False   # a missing sound must never break the tutorial
