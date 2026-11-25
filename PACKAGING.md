# Packaging Mosign as a double-clickable app

You can turn Mosign into a normal app that other people install like any other, with no Terminal, Python or `pip install`. The build bundles Python, OpenCV, MediaPipe, Qt (for the windows and the on-screen overlay), the hand model and Mosign itself into one app.

- **macOS:** `Mosign.app`, shipped inside a `Mosign.dmg` installer
- **Windows:** a `Mosign` folder with `Mosign.exe`, shipped as a `.zip`

The tool doing the work is [PyInstaller](https://pyinstaller.org). The recipe is in `mosign.spec`, and the build scripts wrap it.

## Build on macOS

You only do this once per release, on your own Mac.

1. Install Python 3.12 (e.g. `brew install python@3.12`).
2. From the project folder run:

   ```bash
   ./scripts/build_mac.sh
   ```

The script:

1. makes a clean build environment (`.venv-build`) and installs everything
2. runs the tests (it stops if any fail)
3. downloads the MediaPipe hand model into `models/` so it gets bundled
4. draws the app icon (the cat face on a yellow tile)
5. builds `dist/Mosign.app`
6. runs the built app's `--self-test`, which checks MediaPipe, the window and the hand model with no camera needed
7. wraps it in `dist/Mosign-<version>-<arch>.dmg` with a drag-to-Applications shortcut

**Apple Silicon vs Intel:** the app only runs on the kind of Mac it was built on, because MediaPipe doesn't ship "universal" builds. `arm64` in the file name means Apple Silicon (M1 and later), `x86_64` means Intel. Build on each kind of Mac if you need both.

## Build on Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Output: `dist\Mosign\Mosign.exe` and `dist\Mosign-<version>-windows.zip`. Share the zip. People unzip it and double-click `Mosign.exe`. To get a Start-menu or desktop shortcut, right-click `Mosign.exe` and choose **Pin to Start**, or **Send to → Desktop (create shortcut)**.

## What to tell people you share it with (macOS)

1. Open `Mosign.dmg` and drag **Mosign** into **Applications**.
2. **First launch:** the app isn't signed by Apple (see below), so macOS will block a normal double-click. **Right-click Mosign → Open → Open** once. After that it opens normally from Launchpad, Spotlight or the Dock.
   - On newer macOS versions, if there's no Open button: try to open it once, then go to **System Settings → Privacy & Security**, scroll down and click **Open Anyway**.
3. Click **Allow** when it asks for the camera.
4. Give it permission to control the computer. Without this, gestures are recognised but scrolling and tab switching silently do nothing: **System Settings → Privacy & Security → Accessibility → turn on Mosign** (use **+** to add it from Applications if it isn't listed), then quit and reopen Mosign.
5. The quick tour starts on first launch.

To keep it in the Dock, right-click its Dock icon while it's running → **Options → Keep in Dock**.

## Optional: sign and notarize (no security warning)

The right-click → Open step goes away if you sign the app with an Apple Developer ID ($99/year Apple Developer Program) and have Apple notarize it:

```bash
# sign everything inside the app with your Developer ID
codesign --deep --force --options runtime --timestamp \
  --sign "Developer ID Application: Your Name (TEAMID)" dist/Mosign.app

# rebuild the dmg from the signed app (rerun the last part of build_mac.sh), then:
xcrun notarytool submit dist/Mosign-*.dmg --apple-id you@example.com \
  --team-id TEAMID --password <app-specific-password> --wait
xcrun stapler staple dist/Mosign-*.dmg
```

Windows has a similar warning ("Windows protected your PC" → **More info → Run anyway**), which goes away with a code-signing certificate.

## Troubleshooting

- **App opens and closes right away / shows "Hand tracking could not start":** the hand model is missing. Make sure `models/hand_landmarker.task` exists before building, which the build script handles. You can also run the built app from Terminal to see details:
  `./dist/Mosign.app/Contents/MacOS/Mosign --self-test`
- **Gestures show in the app but nothing happens in the browser:** Accessibility permission (step 4 above). If you rebuilt the app, remove the old Mosign entry from the Accessibility list and add the new one, because macOS ties the permission to that exact build.
- **Wrong camera:** press `C` (or **Swap camera**) in the app. The choice is remembered.
- **App size:** expect roughly 250–550 MB, mostly MediaPipe, OpenCV and Qt.
- **Overlay not showing over a full-screen browser (macOS):** Mosign briefly runs as a background app while the overlay opens, so it can float over full-screen apps. If it still doesn't appear, run Mosign once with `--hide-dock-icon` (Terminal: `/Applications/Mosign.app/Contents/MacOS/Mosign --hide-dock-icon`). It's remembered, and Mosign then runs without a Dock icon, which macOS reliably allows over full-screen apps. `--show-dock-icon` undoes it.
- **Settings and reset:** settings live in `~/.mosign/config.json`. Delete that file to start fresh, including the first-run tour.
