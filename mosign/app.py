"""Start-up: read options, build the engine, open the windows."""

import argparse

import cv2

from mosign.config import Config
from mosign.engine import Engine
from mosign.tracker import HandTracker
from mosign.ui import HEIGHT, WIDTH, render_message


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Control your browser with hand gestures.")
    parser.add_argument("--camera", type=int, default=None,
                        help="camera index to start with (default: last used)")
    parser.add_argument("--tour", action="store_true", help="run the quick tour again")
    parser.add_argument("--skip-tour", action="store_true",
                        help="skip the first-run tour (e.g. if the camera can't see you)")
    parser.add_argument("--hide-dock-icon", action="store_true",
                        help="macOS: run without a Dock icon (remembered). Most reliable "
                             "way to keep the overlay over full-screen apps")
    parser.add_argument("--show-dock-icon", action="store_true",
                        help="macOS: undo --hide-dock-icon")
    parser.add_argument("--self-test", action="store_true",
                        help="check the install (no camera or window needed) and exit")
    parser.add_argument("--max-frames", type=int, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def self_test():
    """Check that everything a packaged app needs is present. Exit code 0 = OK."""
    import mosign
    from mosign import tracker as tracker_mod
    from mosign.overlay import Overlay
    from mosign.ui import UI, View

    ok = True
    print(f"Mosign {mosign.__version__} self-test")
    try:
        import mediapipe
        print(f"  ok   mediapipe {getattr(mediapipe, '__version__', '?')}, opencv {cv2.__version__}")
    except Exception as exc:
        print(f"  FAIL import mediapipe: {exc}")
        return 1
    try:
        import importlib

        import PySide6
        importlib.import_module("mosign.qt_app")   # the window code loads
        print(f"  ok   Qt windows (PySide6 {PySide6.__version__})")
    except Exception as exc:
        print(f"  FAIL import PySide6: {exc}")
        ok = False
    try:
        img = UI().render(View(), now=0.0)
        assert img.shape == (HEIGHT, WIDTH, 3)
        over = Overlay(2).render(View(), now=0.0)
        assert over.shape[2] == 4 and over[..., 3].max() == 255 and over[..., 3].min() == 0
        print("  ok   window and overlay render")
    except Exception as exc:
        print(f"  FAIL render: {exc}")
        ok = False
    print(f"  info model file: {tracker_mod.find_model() or 'not bundled (downloads on first run)'}")
    try:
        t = HandTracker()
        print(f"  ok   hand tracker ({t.backend} API)")
        t.close()
    except Exception as exc:
        print(f"  FAIL hand tracker: {exc}")
        ok = False
    print("PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        return self_test()
    cfg = Config.load()
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.hide_dock_icon or args.show_dock_icon:
        cfg.hide_dock_icon = bool(args.hide_dock_icon)
        cfg.save()
    if args.skip_tour and not cfg.onboarding_complete:
        cfg.onboarding_complete = True
        cfg.save()

    from mosign import qt_app  # Qt only once we know we need windows

    try:
        tracker = HandTracker()
    except Exception as exc:  # missing model, broken install, ...
        # packaged apps have no terminal, so show the problem in a window
        qt_app.show_message(render_message("Hand tracking could not start", str(exc)),
                            args.max_frames)
        return 1

    def make_engine(overlay_scale):
        return Engine(cfg, overlay_scale=overlay_scale, start_tour=args.tour, tracker=tracker)

    return qt_app.run(make_engine, max_frames=args.max_frames,
                      hide_dock_icon=cfg.hide_dock_icon)
