# Mosign

A Python program that uses your webcam to control a web browser with hand gestures. You can scroll up and down, stop scrolling, and switch tabs without touching the keyboard or mouse.

## How it works

1. **MediaPipe Hands** finds 21 landmark points on your hand in each webcam frame.
2. The program checks which fingers are extended (a finger counts as "up" when its tip is farther from the wrist than its middle joint).
3. The pattern of raised fingers is matched to a gesture.
4. **PyAutoGUI** sends the matching scroll or keyboard action to the active window.

A gesture must be held steady for a few frames before it counts, which prevents accidental triggers.

## Gestures

Point your index finger the way you want to go (other fingers curled, thumb either way).

| Gesture | Action |
|---|---|
| Point up | Scroll up (keeps going while you point) |
| Point down | Scroll down (keeps going while you point) |
| Point left | Previous tab (Ctrl+Shift+Tab) |
| Point right | Next tab (Ctrl+Tab) |
| Rock horns (index + pinky), hold 1 second | Turn tracking off / back on |
| Pinky up (only the pinky), hold 1 second | Hide / show the gesture menu |
| Anything else / lower your hand | Stop / no action |

The camera view is mirrored, so "left" means your left.

While tracking is off, only the rock-horns gesture is watched for, so you can rest your hands or talk with them freely.

## The app window

Mosign opens a light-green window that shows your camera with your hand's skeleton drawn on top, plus a "Right now" card that says which gesture it sees and what it's doing. **Pip the penguin** on the left copies what you do: it hops up while you scroll up, slides down while you scroll down, waddles left or right when you switch tabs, waves when you toggle the menu, and naps while tracking is paused. The **Gestures** menu in the top right shows every gesture with a small animated hand, and lights up the one you're doing.

| Key / button | Action |
|---|---|
| `C` / **Swap camera** | Switch to the next working camera (remembered next time) |
| `S` / **Pause tracking** | Pause or resume tracking |
| `M` / **Hide menu** | Hide or show the gesture menu |
| `Q` / **Quit** | Quit |

Settings are saved in `~/.mosign/config.json` (camera, scroll speed, hold time, etc.).

## Requirements

- macOS (Intel or Apple Silicon)
- Python 3.9 to 3.12 (MediaPipe does not install on newer versions such as 3.13+)
- A webcam

## Setup

```bash
cd path/to/project-folder
python3.12 -m venv gestures
source gestures/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Check that the environment uses the right version:

```bash
python --version
```

It should print `Python 3.12.x`.

If MediaPipe fails to install on an Intel Mac, try an older release:

```bash
python -m pip install "mediapipe==0.10.14"
```

## macOS permissions

Go to **System Settings > Privacy & Security** and enable your terminal app (Terminal, iTerm, or VS Code) under:

- **Camera**
- **Accessibility**

Quit and reopen the terminal afterward.

## Run

```bash
source gestures/bin/activate
python gesture_control.py
```

Click on your browser window so it is the active window, then show your gestures to the camera.

Press `q` in the webcam window to quit, or `Ctrl+C` in the terminal.

**Emergency stop:** move your mouse into a corner of the screen (PyAutoGUI failsafe).
