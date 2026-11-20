# Build Mosign for Windows: dist\Mosign\Mosign.exe and dist\Mosign-<version>-windows.zip
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#
# Needs Python 3.12 from python.org (tick "Add python.exe to PATH").
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Python = if ($env:PYTHON) { $env:PYTHON } else { "py -3.12" }
$ModelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

Write-Host "==> Setting up build environment (.venv-build)"
Invoke-Expression "$Python -m venv .venv-build"
. .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements-dev.txt pyinstaller

Write-Host "==> Running tests"
python -m pytest -q

Write-Host "==> Getting the hand model"
New-Item -ItemType Directory -Force models | Out-Null
if (-not (Test-Path models\hand_landmarker.task)) {
    Invoke-WebRequest -Uri $ModelUrl -OutFile models\hand_landmarker.task
}

Write-Host "==> Making the app icon"
python scripts\make_icon.py packaging | Out-Null

Write-Host "==> Building Mosign.exe"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
pyinstaller --noconfirm mosign.spec

Write-Host "==> Checking the built app"
# console=False apps don't print to this window, so check the exit code
$p = Start-Process -FilePath dist\Mosign\Mosign.exe -ArgumentList "--self-test" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Self-test failed (exit $($p.ExitCode))" }

$Version = python -c "import mosign; print(mosign.__version__)"
$Zip = "dist\Mosign-$Version-windows.zip"
Compress-Archive -Path dist\Mosign -DestinationPath $Zip -Force

Write-Host ""
Write-Host "Done!"
Write-Host "  App folder: dist\Mosign  (run Mosign.exe)"
Write-Host "  Zip to share: $Zip"
