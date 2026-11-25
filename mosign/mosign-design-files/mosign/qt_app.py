"""Windows: the main Mosign window and the on-screen overlay (Qt / PySide6).

The overlay is a frameless, transparent, always-on-top window in the
top-right corner of the screen. Clicks go straight through it and it never
takes keyboard focus, so the browser stays the active window and keeps
receiving the scroll / tab keys.
"""

import os
import sys
import time

# opencv-python on Linux points Qt at its own (incompatible) plugins; undo that.
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

from PySide6.QtCore import QPoint, QRect, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QKeySequence, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from mosign import macos, overlay as overlay_mod  # noqa: E402
from mosign.engine import KEY_COMMANDS  # noqa: E402
from mosign.tabs import TabLocator  # noqa: E402
from mosign.ui import HEIGHT, WIDTH, WINDOW_TITLE  # noqa: E402


def bgr_to_qimage(img):
    h, w = img.shape[:2]
    return QImage(img.data, w, h, img.strides[0], QImage.Format.Format_BGR888).copy()


def bgra_to_qimage(img):
    """BGRA premultiplied numpy -> QImage (ARGB32 is B,G,R,A in memory)."""
    h, w = img.shape[:2]
    return QImage(img.data, w, h, img.strides[0],
                  QImage.Format.Format_ARGB32_Premultiplied).copy()


def get_app():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Mosign")
    app.setQuitOnLastWindowClosed(False)  # the overlay alone shouldn't keep it alive
    return app


def screen_scale():
    screen = QGuiApplication.primaryScreen()
    return max(1.0, screen.devicePixelRatio()) if screen else 1.0


class CanvasWindow(QWidget):
    """Shows a numpy image, scaled to fit, and turns clicks/keys into commands."""

    def __init__(self, title=WINDOW_TITLE, size=(WIDTH, HEIGHT)):
        super().__init__()
        self.setWindowTitle(title)
        self.canvas_size = size
        self.image = None
        self.commands = []
        self.closed = False
        self.on_click = None    # callable(x, y) in canvas pixels
        self.on_hover = None
        self.on_key = None      # callable(text, name) -> True if the key was typed into a field
        self.setMouseTracking(True)
        self.setMinimumSize(size[0] // 3, size[1] // 3)
        self.resize(*self._initial_size())

    def _initial_size(self):
        w, h = self.canvas_size
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return w, h
        avail = screen.availableGeometry()
        k = min(1.0, avail.width() * 0.9 / w, avail.height() * 0.9 / h)
        return int(w * k), int(h * k)

    def _target(self):
        """Where the image is drawn inside the window (keeps its shape)."""
        w, h = self.canvas_size
        k = min(self.width() / w, self.height() / h)
        tw, th = int(w * k), int(h * k)
        return QRect((self.width() - tw) // 2, (self.height() - th) // 2, tw, th), k

    def to_canvas(self, pos):
        rect, k = self._target()
        return (pos.x() - rect.x()) / k, (pos.y() - rect.y()) / k

    def set_image(self, qimage):
        self.image = qimage
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        if self.image is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            rect, _ = self._target()
            p.drawImage(rect, self.image)
        p.end()

    def mouseMoveEvent(self, event):
        if self.on_hover:
            self.on_hover(*self.to_canvas(event.position()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_click:
            self.on_click(*self.to_canvas(event.position()))

    def keyPressEvent(self, event):
        if self.on_key:
            names = {Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Tab: "tab",
                     Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter"}
            text = event.text()
            if event.matches(QKeySequence.StandardKey.Paste):
                text = QApplication.clipboard().text().strip().splitlines()[0:1] and \
                    QApplication.clipboard().text().strip().splitlines()[0] or ""
            if self.on_key(text, names.get(event.key(), "")):
                return
        cmd = KEY_COMMANDS.get(event.text().lower())
        if cmd:
            self.commands.append(cmd)

    def closeEvent(self, event):
        self.closed = True
        self.commands.append("quit")
        event.accept()


class OverlayWindow(QWidget):
    """Transparent, click-through, always-on-top corner overlay."""

    def __init__(self):
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowTransparentForInput
                 | Qt.WindowType.WindowDoesNotAcceptFocus
                 | Qt.WindowType.Tool)          # no taskbar / Dock entry
        super().__init__(None, flags)
        self.setWindowTitle("Mosign overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.image = None
        self._configured = False
        self.hide_dock_icon = False

    @staticmethod
    def corner_position(w, h=0):
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        m = overlay_mod.MARGIN
        return QPoint(avail.right() - w - m + 1, avail.top() + m)

    def set_image(self, qimage, dpr):
        qimage.setDevicePixelRatio(dpr)
        w = round(qimage.width() / dpr)
        h = round(qimage.height() / dpr)
        if (w, h) != (self.width(), self.height()) or not self.isVisible():
            self.resize(w, h)
            self.move(self.corner_position(w, h))
        self.image = qimage
        if not self.isVisible():
            self.show()
        self._configure_once()
        self.update()

    def _configure_once(self):
        if self._configured:
            return
        self._configured = True
        # Only real macOS windows have an NSWindow behind them (not the
        # "offscreen" platform used by tests and CI): never poke a fake one.
        if QGuiApplication.platformName() == "cocoa":
            # stay on top across apps and Spaces, including full-screen apps
            macos.configure_overlay(
                self, schedule=lambda ms, fn: QTimer.singleShot(ms, fn),
                hide_dock_icon=self.hide_dock_icon)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if self.image is not None:
            p.drawImage(0, 0, self.image)
        p.end()


class CatWindow(OverlayWindow):
    """The cat's own little window. It moves every frame to wherever the cat is,
    so the cat can jump across the screen to the browser tab you're on."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mosign cat")

    def set_frame(self, qimage, dpr, feet, anchor):
        qimage.setDevicePixelRatio(dpr)
        w = round(qimage.width() / dpr)
        h = round(qimage.height() / dpr)
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)
        pos = QPoint(round(feet[0] - anchor[0]), round(feet[1] - anchor[1]))
        if pos != self.pos():
            self.move(pos)
        self.image = qimage
        if not self.isVisible():
            self.show()
        self._configure_once()
        self.update()


def show_message(img, max_frames=None):
    """A window with a fixed image (e.g. a start-up error). Q or close quits."""
    app = get_app()
    win = CanvasWindow()
    win.set_image(bgr_to_qimage(img))
    win.show()
    frames = 0

    def tick():
        nonlocal frames
        frames += 1
        if "quit" in win.commands or (max_frames and frames >= max_frames):
            timer.stop()
            win.close()
            app.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(30)
    app.exec()


def run(make_engine, max_frames=None, clock=time.time, hide_dock_icon=False):
    """Show both windows and run the engine until the user quits.

    make_engine(overlay_scale) builds the Engine once Qt knows the screen's
    pixel density, so the overlay is drawn sharp on Retina screens.
    """
    app = get_app()
    dpr = screen_scale()
    engine = make_engine(dpr)
    main = CanvasWindow()
    main.activity = macos.keep_app_awake()  # stops App Nap slowing us down; keep a reference
    main.on_click = lambda x, y: engine.ui.click(x, y)
    main.on_hover = lambda x, y: engine.ui.hover(x, y)
    main.on_key = lambda text, name: engine.ui.key(text, name)
    overlay = OverlayWindow()
    overlay.hide_dock_icon = hide_dock_icon
    cat = CatWindow()
    cat.hide_dock_icon = hide_dock_icon

    # the cat's home is the top of the corner overlay; it finds browser tabs itself
    corner = OverlayWindow.corner_position(overlay_mod.WIDTH)
    engine.set_home(*overlay_mod.home_feet(corner.x(), corner.y()))
    if engine.tabs is None or not engine.tabs.available:
        engine.tabs = TabLocator()
    engine.tabs.start()
    main.show()

    frames = 0

    def tick():
        nonlocal frames
        commands, main.commands = main.commands, []
        out = engine.step(clock(), commands)
        if main.isVisible():
            main.set_image(bgr_to_qimage(out.main))
        if not out.show_overlay:
            overlay.hide()      # welcome / tutorial screens: just the window
            cat.hide()
        else:
            overlay.set_image(bgra_to_qimage(out.overlay), engine.overlay.scale)
        if out.show_overlay and out.cat is not None:
            cat.set_frame(bgra_to_qimage(out.cat), engine.overlay.scale, out.cat_feet,
                          out.cat_anchor)
        frames += 1
        if out.quit or main.closed or (max_frames and frames >= max_frames):
            timer.stop()
            overlay.close()
            cat.close()
            if not main.closed:
                main.close()
            app.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1)   # camera.read() paces the loop to the camera's frame rate
    try:
        app.exec()
    finally:
        engine.close()
    return 0
