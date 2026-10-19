# Build RemoteMyRig.exe (Windows, Python 3.13).
#
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Wheel <path to rigplane wheel>
#
# Result: %USERPROFILE%\RemoteMyRig\RemoteMyRig\RemoteMyRig.exe
param(
    [Parameter(Mandatory = $true)][string]$Wheel
)
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $env:LOCALAPPDATA "RemoteMyRig-build\venv"
$work = Join-Path $env:LOCALAPPDATA "RemoteMyRig-build\work"
$dist = Join-Path $env:USERPROFILE "RemoteMyRig"

if (-not (Test-Path $venv)) {
    py -3.13 -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"

& $py -m pip install --upgrade pip
& $py -m pip install --force-reinstall --no-deps "$Wheel"
& $py -m pip install "$Wheel[rc28]" pywebview keyring pyinstaller

# PyInstaller works on a local copy of the launcher (the source may sit on
# a \\wsl$ share).
New-Item -ItemType Directory -Force -Path $work | Out-Null
Copy-Item (Join-Path $here "remotemyrig.py") (Join-Path $work "RemoteMyRig.py") -Force

& $py -m PyInstaller `
    --noconfirm `
    --windowed `
    --name RemoteMyRig `
    --distpath $dist `
    --workpath (Join-Path $work "build") `
    --specpath $work `
    --collect-all rigplane `
    --copy-metadata rigplane `
    --collect-all webview `
    --collect-all sounddevice `
    --collect-all _sounddevice_data `
    --collect-submodules keyring `
    --hidden-import hid `
    (Join-Path $work "RemoteMyRig.py")

Write-Host ""
Write-Host "RemoteMyRig.exe : $dist\RemoteMyRig\RemoteMyRig.exe"
