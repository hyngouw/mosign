# PyInstaller recipe for Mosign. Build with:  pyinstaller --noconfirm mosign.spec
# (or just run scripts/build_mac.sh / scripts/build_windows.ps1, which do everything)
#
# The result bundles Python, OpenCV, MediaPipe and the hand model, so the
# people you give it to don't need Python or any packages installed.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

sys.path.insert(0, str(Path(SPECPATH)))
from mosign import __version__  # noqa: E402

ROOT = Path(SPECPATH)

# MediaPipe loads native libraries and model graphs at runtime: take all of it.
mp_datas, mp_binaries, mp_hidden = collect_all("mediapipe")

datas = list(mp_datas)
model = ROOT / "models" / "hand_landmarker.task"
if model.is_file():
    # newer MediaPipe needs this file; bundling it means no download on first run
    datas.append((str(model), "models"))

icon_png = ROOT / "packaging" / "icon.png"
icon_icns = ROOT / "packaging" / "Mosign.icns"
icon_ico = ROOT / "packaging" / "icon.ico"
if sys.platform == "darwin":
    icon = str(icon_icns) if icon_icns.is_file() else None
elif sys.platform == "win32":
    icon = str(icon_ico) if icon_ico.is_file() else None
else:
    icon = None

a = Analysis(
    ["run_mosign.py"],
    pathex=[str(ROOT)],
    binaries=mp_binaries,
    datas=datas,
    hiddenimports=mp_hidden + ["pyautogui", "PIL.ImageFont", "PySide6.QtWidgets"]
    + (["objc", "AppKit", "Foundation"] if sys.platform == "darwin" else []),
    excludes=["pytest", "IPython", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mosign",
    console=False,          # no terminal window: it's a normal app
    icon=icon,
    # macOS: build for the machine you're on (Apple Silicon or Intel)
    target_arch=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Mosign")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Mosign.app",
        icon=icon,
        bundle_identifier="com.hyngo.mosign",
        version=__version__,
        info_plist={
            "CFBundleName": "Mosign",
            "CFBundleDisplayName": "Mosign",
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # shown in the camera permission prompt
            "NSCameraUsageDescription": "Mosign watches your hand through the camera to "
                                        "turn gestures into scrolling and tab switching.",
            # shown when it asks to control the computer (keyboard / scrolling)
            "NSAppleEventsUsageDescription": "Mosign sends scroll and tab-switch keys to "
                                             "your browser.",
        },
    )
