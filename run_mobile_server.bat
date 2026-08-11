@echo off
chcp 65001 >nul 2>&1
title Obscura Clips - Mobile & Wi-Fi Server (Terminal Only)
color 0B
cls

echo:
echo  +==============================================================+
echo  |         *  O B S C U R A   C L I P S  *                    |
echo  |   Mobile & Wi-Fi Server Mode (Terminal Only)                 |
echo  |   Ryzen 7 + RTX 3050  |  Llama 3.3 70B  |  NVENC            |
echo  +==============================================================+
echo:

:: Change to the folder where this bat file lives
cd /d "%~dp0"

:: ── Include local bin directory in PATH ───────────────────
if exist "%~dp0bin\ffmpeg.exe" set "PATH=%~dp0bin;%PATH%"
if exist "C:\ffmpeg\bin\ffmpeg.exe" set "PATH=C:\ffmpeg\bin;%PATH%"

:: ── 1. Check & Auto-Install Python ─────────────────────────
python --version >nul 2>&1
if not errorlevel 1 goto PYTHON_OK

echo  [SETUP] Python not detected in PATH. Attempting automatic installation via Winget...
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
)

python --version >nul 2>&1
if not errorlevel 1 goto PYTHON_OK

echo  [ERROR] Python 3.10+ is required. Please install Python from https://python.org and re-run.
pause
exit /b 1

:PYTHON_OK

:: ── 2. Check & Auto-Install FFmpeg ─────────────────────────
where ffmpeg >nul 2>&1
if not errorlevel 1 goto FFMPEG_OK

echo  [SETUP] FFmpeg not found. Automatically installing FFmpeg...

:: Try Winget auto-install first
where winget >nul 2>&1
if not errorlevel 1 (
    echo  [SETUP] Installing FFmpeg via Winget package manager...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
)

where ffmpeg >nul 2>&1
if not errorlevel 1 goto FFMPEG_OK

if exist "C:\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=C:\ffmpeg\bin;%PATH%"
    goto FFMPEG_OK
)

:: PowerShell direct download fallback into local bin\
echo  [SETUP] Downloading standalone FFmpeg binaries to local project bin\ folder...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bin = Join-Path '%~dp0' 'bin'; if (-not (Test-Path $bin)) { New-Item -ItemType Directory -Path $bin | Out-Null }; $zip = Join-Path $env:TEMP 'ffmpeg_build.zip'; $ext = Join-Path $env:TEMP 'ffmpeg_temp_ext'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host ' [SETUP] Downloading FFmpeg zip release...'; Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile $zip; Write-Host ' [SETUP] Extracting binaries...'; Expand-Archive -Path $zip -DestinationPath $ext -Force; Get-ChildItem -Path $ext -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1 | Copy-Item -Destination (Join-Path $bin 'ffmpeg.exe'); Get-ChildItem -Path $ext -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1 | Copy-Item -Destination (Join-Path $bin 'ffprobe.exe'); Remove-Item -Path $zip -Force -ErrorAction SilentlyContinue; Remove-Item -Path $ext -Recurse -Force -ErrorAction SilentlyContinue;"

if exist "%~dp0bin\ffmpeg.exe" (
    set "PATH=%~dp0bin;%PATH%"
    echo  [SETUP] FFmpeg installation complete!
    goto FFMPEG_OK
)

where ffmpeg >nul 2>&1
if not errorlevel 1 goto FFMPEG_OK

echo  [ERROR] FFmpeg installation failed automatically.
echo          Please download FFmpeg manually from https://ffmpeg.org and add it to PATH.
pause
exit /b 1

:FFMPEG_OK

:: ── 3. Create Virtual Environment ─────────────────────────
if exist "venv\Scripts\activate.bat" goto VENV_OK

echo  [SETUP] Creating Python virtual environment (venv)...
set "PYCMD=python"
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "exit(0)" >nul 2>&1 && set "PYCMD=py -3.12"
    py -3.11 -c "exit(0)" >nul 2>&1 && set "PYCMD=py -3.11"
)

%PYCMD% -m venv venv
if errorlevel 1 (
    echo  [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

:VENV_OK
call venv\Scripts\activate.bat
set "PATH=%~dp0venv\Scripts;%PATH%"

:: ── 4. Setup Environment Config & Folders ──────────────────
if not exist "output" mkdir output
if not exist "temp" mkdir temp
if not exist "broll_cache" mkdir broll_cache
if not exist "credentials" mkdir credentials
if not exist "scratch" mkdir scratch

if not exist ".env" (
    if exist ".env.example" (
        echo  [SETUP] Creating .env file from template...
        copy .env.example .env >nul
    )
)

:: ── 5. Install & Verify Python Dependencies ────────────────
echo  [SETUP] Verifying & installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo  [SETUP] Installing Playwright Chromium browser...
python -m playwright install chromium

:: ── 6. Check & Auto-Install Rust Toolchain ──────────────────
where cargo >nul 2>&1
if not errorlevel 1 goto RUST_OK
if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto RUST_OK
)

echo  [SETUP] Rust compiler not detected. Attempting automatic installation via rustup-init...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$setup = Join-Path $env:TEMP 'rustup-init.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host ' [SETUP] Downloading rustup-init...'; Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile $setup; Write-Host ' [SETUP] Installing Rust (default toolchain)...'; Start-Process -FilePath $setup -ArgumentList '-y' -Wait; Remove-Item -Path $setup -Force -ErrorAction SilentlyContinue;"

if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    echo  [SETUP] Rust installation complete!
    goto RUST_OK
)

where winget >nul 2>&1
if not errorlevel 1 (
    echo  [SETUP] Attempting Winget installation for Rustup...
    winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements
)

if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto RUST_OK
)

:RUST_OK
where cargo >nul 2>&1
if not errorlevel 1 goto CHECK_RUST_CORE

echo  [INFO]  Rust compiler not found. Native acceleration skipped - Python fallback active.
goto LAUNCH_SERVER_ONLY

:CHECK_RUST_CORE
python -c "import clip_engine_core" >nul 2>&1
if not errorlevel 1 goto LAUNCH_SERVER_ONLY

echo  [SETUP] Building Rust native acceleration engine...
python -m pip install maturin
maturin develop --release --manifest-path clip_engine_core/Cargo.toml

:LAUNCH_SERVER_ONLY
echo:
echo  ==============================================================
echo   OBSCURA CLIPS — MOBILE ^& WI-FI SERVER MODE
echo  ==============================================================
echo   Server is running in terminal (local browser pop-up disabled).
echo   Access the app from any phone, tablet, or PC on your Wi-Fi!
echo:
echo   Press Ctrl+C in this terminal window to stop the server.
echo  ==============================================================
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set OBSCURA_OPEN_BROWSER=0
python server.py
pause
