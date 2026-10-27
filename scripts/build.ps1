# Builds MariaFreeDownload.exe + the Windows installer. Called by .github/workflows/build.yml
param([string]$Version = "1.11.1")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed ($LASTEXITCODE)" } }

python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller;                         Check "pip install"
python tests/test_engine.py;                                         Check "engine tests"
python tests/test_license.py;                                        Check "license tests"
if ((Get-Content app/license_key.py -Raw) -match 'PUBLIC_KEY = ""') { throw "No public key in app/license_key.py - run: python tools/keygen.py init  (then commit that file)" }

pyinstaller --noconfirm --clean --windowed --name MariaFreeDownload `
  --icon assets/jdm.ico --add-data "assets;assets" --paths app `
  --collect-all yt_dlp_ejs --hidden-import PySide6.QtMultimedia --hidden-import licensing --hidden-import license_key `
  --hidden-import PySide6.QtMultimediaWidgets app/main.py;                              Check "pyinstaller"

# ---- bundled tools: FFmpeg (merges HD video + audio) and Deno (needed by YouTube)
$tools = "dist/MariaFreeDownload/tools"
$tmp   = Join-Path $env:RUNNER_TEMP "jdmtools"
New-Item -ItemType Directory -Force $tools, $tmp | Out-Null

Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile "$tmp/ffmpeg.zip"
Expand-Archive "$tmp/ffmpeg.zip" "$tmp/ffmpeg" -Force
Get-ChildItem "$tmp/ffmpeg" -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $tools

Invoke-WebRequest "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" -OutFile "$tmp/deno.zip"
Expand-Archive "$tmp/deno.zip" "$tmp/deno" -Force
Copy-Item "$tmp/deno/deno.exe" $tools

Get-ChildItem $tools | ForEach-Object { "{0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB) }
if (!(Test-Path "$tools/ffmpeg.exe") -or !(Test-Path "$tools/deno.exe")) { throw "tools missing" }

# ---- installer
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (!(Test-Path $iscc)) { choco install innosetup -y --no-progress; Check "choco" }
& $iscc "/DMyAppVersion=$Version" installer\jdm.iss;                Check "Inno Setup"
