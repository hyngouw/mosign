#!/usr/bin/env bash
# Build Mosign.app and a drag-to-install Mosign.dmg on macOS.
#
#   ./scripts/build_mac.sh
#
# Output: dist/Mosign.app and dist/Mosign-<version>-<arch>.dmg
# Build on an Apple Silicon Mac for Apple Silicon users and on an Intel Mac
# for Intel users (MediaPipe doesn't ship universal builds).
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3.12}"   # MediaPipe needs Python 3.9-3.12 for the old API
VENV=".venv-build"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Can't find $PYTHON. Install it (e.g. 'brew install python@3.12') or run:"
  echo "  PYTHON=python3 ./scripts/build_mac.sh"
  exit 1
fi

echo "==> Setting up build environment ($VENV)"
"$PYTHON" -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements-dev.txt pyinstaller

echo "==> Running tests"
python -m pytest -q

echo "==> Getting the hand model (bundled so users never need to download it)"
mkdir -p models
if [ ! -s models/hand_landmarker.task ]; then
  curl -fL --retry 3 -o models/hand_landmarker.task "$MODEL_URL"
fi

echo "==> Making the app icon"
python scripts/make_icon.py packaging >/dev/null
ICONSET="packaging/Mosign.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z $size $size packaging/icon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z $double $double packaging/icon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o packaging/Mosign.icns
rm -rf "$ICONSET"

echo "==> Building Mosign.app"
rm -rf build dist
pyinstaller --noconfirm mosign.spec

echo "==> Checking the built app"
./dist/Mosign.app/Contents/MacOS/Mosign --self-test

echo "==> Making the .dmg"
VERSION=$(python -c "import mosign; print(mosign.__version__)")
ARCH=$(uname -m)
DMG="dist/Mosign-${VERSION}-${ARCH}.dmg"
STAGE="build/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R dist/Mosign.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # drag-to-install shortcut
for attempt in 1 2 3; do
  if hdiutil create -volname "Mosign" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null; then
    break
  fi
  [ "$attempt" = 3 ] && { echo "hdiutil failed"; exit 1; }
  echo "hdiutil busy, retrying..."; sleep 5
done

echo
echo "Done!"
echo "  App: dist/Mosign.app"
echo "  Installer: $DMG"
echo "See PACKAGING.md for what to tell the people you share it with."
