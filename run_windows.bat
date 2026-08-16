@echo off
chcp 65001 >nul 2>&1
title ClipHub - Zero-Click AI Video Clipper
color 0B
cls

echo:
echo  +==============================================================+
echo  ^|         *  O B S C U R A   C L I P S  *                    ^|
echo  ^|   Zero-Strain Local-Hybrid AI Video Clipper                  ^|
echo  ^|   Ryzen 7 + RTX GPU Acceleration  ^|  Llama 3.3 70B          ^|
echo  +==============================================================+
echo:

:: Change to the folder where this bat file lives
cd /d "%~dp0"

:: --- Include local bin directory in PATH ---
if exist "%~dp0bin\ffmpeg.exe" set "PATH=%~dp0bin;%PATH%"
if exist "C:\ffmpeg\bin\ffmpeg.exe" set "PATH=C:\ffmpeg\bin;%PATH%"

:: --- 1. Check & Auto-Install Python ---
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

:: --- 2. Check & Auto-Install FFmpeg ---
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
echo  [SETUP] Downloading standalone FFmpeg binaries to local project bin folder...
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

:: --- 3. Check & Auto-Install Node.js ---
node -v >nul 2>&1
if not errorlevel 1 goto NODE_OK

echo  [SETUP] Node.js not detected in PATH. Attempting automatic installation via Winget...
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id OpenJS.NodeJS -e --accept-source-agreements --accept-package-agreements
)

node -v >nul 2>&1
if not errorlevel 1 goto NODE_OK

echo  [ERROR] Node.js is required for the UI. Please install it from https://nodejs.org and re-run.
pause
exit /b 1

:NODE_OK

:: --- 4. Create Virtual Environment ---
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

:: --- 5. Setup Environment Config & Folders ---
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

:: --- 6. Install & Verify Python Dependencies ---
echo  [SETUP] Verifying ^& installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo  [SETUP] Installing Playwright Chromium browser...
python -m playwright install chromium

:: --- 7. Check & Auto-Install Rust Toolchain ---
where cargo >nul 2>&1
if not errorlevel 1 goto RUST_OK
if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto RUST_OK
)

echo  [SETUP] Rust compiler not detected. Attempting automatic installation via rustup-init...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$setup = Join-Path '%~dp0' 'bin'; if (-not (Test-Path $setup)) { New-Item -ItemType Directory -Path $setup | Out-Null }; $exe = Join-Path $env:TEMP 'rustup-init.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host ' [SETUP] Downloading rustup-init...'; Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile $exe; Write-Host ' [SETUP] Installing Rust (default toolchain)...'; Start-Process -FilePath $exe -ArgumentList '-y' -Wait; Remove-Item -Path $exe -Force -ErrorAction SilentlyContinue;"

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
goto LAUNCH

:CHECK_RUST_CORE
python -c "import clip_engine_core" >nul 2>&1
if not errorlevel 1 goto LAUNCH

echo  [SETUP] Building Rust native acceleration engine...
python -m pip install maturin
maturin develop --release --manifest-path clip_engine_core/Cargo.toml

:LAUNCH

:: --- 8. Choose UI and Launch App Server ---
if not "%UI_CHOICE%"=="" goto PROCESS_CHOICE

echo:
echo  +==============================================================+
echo  ^|                 SELECT USER INTERFACE MODE                   ^|
echo  +==============================================================+
echo  ^| [1] Native Desktop App (Recommended, PyWebView)              ^|
echo  ^| [2] Beta UI (Tauri + React Modern Desktop UI)                ^|
echo  ^| [3] Mobile ^& Wi-Fi Mode (Terminal Only - Phone/Tablet)        ^|
echo  ^| [4] Classic Web UI (FastAPI - Launches local browser)        ^|
echo  +==============================================================+
echo:
set /p UI_CHOICE="Enter your choice (1, 2, 3, or 4) [1]: "
if "%UI_CHOICE%"=="" set UI_CHOICE=1

:PROCESS_CHOICE
if "%UI_CHOICE%"=="1" goto LAUNCH_NATIVE_DESKTOP
if "%UI_CHOICE%"=="2" goto LAUNCH_BETA
if "%UI_CHOICE%"=="3" goto LAUNCH_MOBILE_SERVER
if "%UI_CHOICE%"=="4" goto LAUNCH_CLASSIC

:LAUNCH_NATIVE_DESKTOP
echo:
echo  +==============================================================+
echo  ^|                 CLIPHUB NATIVE DESKTOP                       ^|
echo  ^|                 Starting Desktop Interface...                ^|
echo  +==============================================================+
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

python desktop.py
goto END_LAUNCH

:LAUNCH_CLASSIC
echo:
echo  +==============================================================+
echo  ^|                 CLIPHUB CLIPS IS LIVE!                       ^|
echo  ^|                 Classic Web UI Mode                          ^|
echo  ^|                 Server URL: http://localhost:7842            ^|
echo  ^|                 Status: Active ^& Listening...                 ^|
echo  ^|                                                              ^|
echo  ^|   Press Ctrl+C in this terminal window to stop the server.   ^|
echo  +==============================================================+
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set CLIPHUB_OPEN_BROWSER=1
python server.py
goto END_LAUNCH

:LAUNCH_MOBILE_SERVER
echo:
echo  +==============================================================+
echo  ^|         CLIPHUB CLIPS - MOBILE ^& WI-FI SERVER MODE           ^|
echo  ^|                                                              ^|
echo  ^|   Status: Active ^& Ready for Phone Connections!               ^|
echo  ^|   Mobile Access: Connect to your PC IP on port 7842          ^|
echo  ^|                                                              ^|
echo  ^|   Press Ctrl+C in this terminal window to stop the server.   ^|
echo  +==============================================================+
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set CLIPHUB_OPEN_BROWSER=0
python server.py
goto END_LAUNCH

:LAUNCH_BETA
echo:
echo  +==============================================================+
echo  ^|                 BETA UI MODE SELECTION                       ^|
echo  +==============================================================+
echo  ^| [Enter] Launch in Browser Localhost                          ^|
echo  ^| [B/b]   Install C++ Tools ^& Launch Native Desktop App (Tauri) ^|
echo  +==============================================================+
echo:
set /p BETA_MODE="Enter your choice [Browser]: "

if /i "%BETA_MODE%"=="B" goto LAUNCH_TAURI_NATIVE

:LAUNCH_BROWSER
echo:
echo  +==============================================================+
echo  ^|                 CLIPHUB CLIPS IS LIVE!                       ^|
echo  ^|                 Beta UI - Browser Localhost                  ^|
echo  ^|                 Server URL: http://localhost:5173            ^|
echo  ^|                                                              ^|
echo  ^|   Press Ctrl+C in this terminal window to stop.              ^|
echo  +==============================================================+
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set CLIPHUB_OPEN_BROWSER=0
start "ClipHub Backend" python server.py

if not exist "cliphub-ui\node_modules" (
    echo  [SETUP] Installing frontend dependencies for Beta UI...
    cd cliphub-ui
    call npm install
    cd ..
)

cd cliphub-ui
start "" "http://localhost:5173"
call npm run dev
goto END_LAUNCH

:LAUNCH_TAURI_NATIVE
echo:
echo  +==============================================================+
echo  ^|              CHECKING NATIVE TAURI DEPENDENCIES...           ^|
echo  +==============================================================+
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

:: 1. Check/Install Rust
where cargo >nul 2>&1
if not errorlevel 1 goto TAURI_RUST_OK
if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto TAURI_RUST_OK
)

echo  [SETUP] Installing Rust toolchain via rustup-init...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$setup = Join-Path $env:TEMP 'rustup-init.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile $setup; Start-Process -FilePath $setup -ArgumentList '-y' -Wait; Remove-Item -Path $setup -Force -ErrorAction SilentlyContinue;"
if exist "%USERPROFILE%\.cargo\bin\cargo.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

:TAURI_RUST_OK

:: 2. Check/Install MSVC C++ Build Tools
where link >nul 2>&1
if not errorlevel 1 goto TAURI_BUILD_TOOLS_OK

echo  [SETUP] MSVC C++ Build Tools (link.exe) not detected.
echo  [SETUP] Installing Microsoft Visual C++ Build Tools via Winget...
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-source-agreements --accept-package-agreements --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools"
)

:TAURI_BUILD_TOOLS_OK
echo:
echo  +==============================================================+
echo  ^|                 CLIPHUB CLIPS IS LIVE!                       ^|
echo  ^|                 Beta UI - Native Desktop App                 ^|
echo  ^|                                                              ^|
echo  ^|   Starting Python Backend and Tauri Desktop App...           ^|
echo  ^|   Press Ctrl+C in this terminal window to stop.              ^|
echo  +==============================================================+
echo:
set CLIPHUB_OPEN_BROWSER=0
start "ClipHub Backend" python server.py

if not exist "cliphub-ui\node_modules" (
    echo  [SETUP] Installing frontend dependencies for Beta UI...
    cd cliphub-ui
    call npm install
    cd ..
)

cd cliphub-ui
call npm run tauri dev
if errorlevel 1 (
    echo:
    echo  [WARNING] Native Tauri build failed. Falling back to Browser Localhost...
    start "" "http://localhost:5173"
    call npm run dev
)

:END_LAUNCH
echo:
echo  [INFO] Server stopped.
pause
exit /b 0
