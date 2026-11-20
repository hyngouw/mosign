# Build Mosign for Windows: dist\Mosign\Mosign.exe and dist\Mosign-<version>-windows.zip
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#
# Needs Python 3.12 from python.org (tick "Add python.exe to PATH").
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Stop on failing programs too (PowerShell only stops on its own errors by default)
function Run([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

$Python = if ($env:PYTHON) { $env:PYTHON } else { "py -3.12" }
$ModelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

Write-Host "==> Setting up build environment (.venv-build)"
Invoke-Expression "$Python -m venv .venv-build"
if ($LASTEXITCODE -ne 0) { throw "Creating the venv failed. Is Python 3.12 installed?" }
$Py = (Resolve-Path .\.venv-build\Scripts\python.exe).Path
Run "pip upgrade" { & $Py -m pip install --upgrade pip }
Run "Installing packages" { & $Py -m pip install -r requirements-dev.txt pyinstaller }

Write-Host "==> Running tests"
Run "Tests" { & $Py -m pytest -q }

Write-Host "==> Getting the hand model"
New-Item -ItemType Directory -Force models | Out-Null
if (-not (Test-Path models\hand_landmarker.task)) {
    Invoke-WebRequest -Uri $ModelUrl -OutFile models\hand_landmarker.task
}

Write-Host "==> Making the app icon"
Run "Icon" { & $Py scripts\make_icon.py packaging }

Write-Host "==> Building Mosign.exe"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
Run "PyInstaller" { & $Py -m PyInstaller --noconfirm mosign.spec }

Write-Host "==> Checking the built app"
# console=False apps don't print to this window, so check the exit code
$p = Start-Process -FilePath dist\Mosign\Mosign.exe -ArgumentList "--self-test" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Self-test failed (exit $($p.ExitCode))" }

$Version = (& $Py -c "import mosign; print(mosign.__version__)").Trim()
$Zip = "dist\Mosign-$Version-windows-x64.zip"
Compress-Archive -Path dist\Mosign -DestinationPath $Zip -Force

Write-Host ""
Write-Host "Done!"
Write-Host "  App folder: dist\Mosign  (run Mosign.exe)"
Write-Host "  Zip to share: $Zip"
