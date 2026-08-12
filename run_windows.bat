@echo off
chcp 65001 >nul 2>&1
title Obscura Clips - Zero-Click AI Video Clipper
cls

:: Enable ANSI Escapes in Windows Command Prompt / Terminal
for /f "delims=" %%A in ('powershell -NoProfile -Command "[char]27"') do set "ESC=%%A"

set "C_CYAN=%ESC%[1;36m"
set "C_PURPLE=%ESC%[1;35m"
set "C_GOLD=%ESC%[1;33m"
set "C_GREEN=%ESC%[1;32m"
set "C_WHITE=%ESC%[1;37m"
set "C_GRAY=%ESC%[90m"
set "C_RESET=%ESC%[0m"
set "C_NEON=%ESC%[38;2;0;240;255m"
set "C_MAGENTA=%ESC%[38;2;236;72;153m"

echo:
echo %C_PURPLE%  ╔══════════════════════════════════════════════════════════════════╗%C_RESET%
echo %C_PURPLE%  ║%C_NEON%   ██████╗ ██████╗ ███████╗██╗   ██╗██████╗  █████╗ %C_PURPLE%       ║%C_RESET%
echo %C_PURPLE%  ║%C_NEON%  ██╔═══██╗██╔══██╗██╔════╝██║   ██║██╔══██╗██╔══██╗%C_PURPLE%       ║%C_RESET%
echo %C_PURPLE%  ║%C_NEON%  ██║   ██║██████╔╝███████╗██║   ██║██████╔╝███████║%C_PURPLE%       ║%C_RESET%
echo %C_PURPLE%  ║%C_NEON%  ██║   ██║██╔══██╗╚════██║██║   ██║██╔══██╗██╔══██╗%C_PURPLE%       ║%C_RESET%
echo %C_PURPLE%  ║%C_NEON%  ╚██████╔╝██████╔╝███████║╚██████╔╝██║  ██║██║  ██║%C_PURPLE%       ║%C_RESET%
echo %C_PURPLE%  ║%C_GRAY%   Zero-Strain Local-Hybrid AI Video Clipper               %C_PURPLE% ║%C_RESET%
echo %C_PURPLE%  ║%C_GOLD%   ⚡ Llama 3.3 70B  │  ⚡ Hardware NVENC  │  ⚡ AutoPost  %C_PURPLE% ║%C_RESET%
echo %C_PURPLE%  ╚══════════════════════════════════════════════════════════════════╝%C_RESET%
echo:

:: Change to the folder where this bat file lives
cd /d "%~dp0"

:: ── Include local bin directory in PATH ───────────────────
if exist "%~dp0bin\ffmpeg.exe" set "PATH=%~dp0bin;%PATH%"
if exist "C:\ffmpeg\bin\ffmpeg.exe" set "PATH=C:\ffmpeg\bin;%PATH%"

:: ── 1. Check & Auto-Install Python ─────────────────────────
python --version >nul 2>&1
if not errorlevel 1 goto PYTHON_OK

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Python not detected in PATH. Attempting automatic installation via Winget...%C_RESET%
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
)

python --version >nul 2>&1
if not errorlevel 1 goto PYTHON_OK

echo  %C_MAGENTA%[ERROR]%C_RESET% %C_WHITE%Python 3.10+ is required. Please install Python from https://python.org and re-run.%C_RESET%
pause
exit /b 1

:PYTHON_OK

:: ── 2. Check & Auto-Install FFmpeg ─────────────────────────
where ffmpeg >nul 2>&1
if not errorlevel 1 goto FFMPEG_OK

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%FFmpeg not found. Automatically installing FFmpeg...%C_RESET%

:: Try Winget auto-install first
where winget >nul 2>&1
if not errorlevel 1 (
    echo  %C_CYAN%[SETUP]%C_RESET% %C_GRAY%Installing FFmpeg via Winget package manager...%C_RESET%
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
)

where ffmpeg >nul 2>&1
if not errorlevel 1 goto FFMPEG_OK

if exist "C:\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=C:\ffmpeg\bin;%PATH%"
    goto FFMPEG_OK
)

:: PowerShell direct download fallback into local bin\
echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Downloading standalone FFmpeg binaries to local project bin\ folder...%C_RESET%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bin = Join-Path '%~dp0' 'bin'; if (-not (Test-Path $bin)) { New-Item -ItemType Directory -Path $bin | Out-Null }; $zip = Join-Path $env:TEMP 'ffmpeg_build.zip'; $ext = Join-Path $env:TEMP 'ffmpeg_temp_ext'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host ' [SETUP] Downloading FFmpeg zip release...'; Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile $zip; Write-Host ' [SETUP] Extracting binaries...'; Expand-Archive -Path $zip -DestinationPath $ext -Force; Get-ChildItem -Path $ext -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1 | Copy-Item -Destination (Join-Path $bin 'ffmpeg.exe'); Get-ChildItem -Path $ext -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1 | Copy-Item -Destination (Join-Path $bin 'ffprobe.exe'); Remove-Item -Path $zip -Force -ErrorAction SilentlyContinue; Remove-Item -Path $ext -Recurse -Force -ErrorAction SilentlyContinue;"

if exist "%~dp0bin\ffmpeg.exe" (
    set "PATH=%~dp0bin;%PATH%"
    echo  %C_GREEN%[SETUP]%C_RESET% %C_WHITE%FFmpeg installation complete!%C_RESET%
    goto FFMPEG_OK
)

where ffmpeg >nul 2>&1
if not errorlevel 1 goto FFMPEG_OK

echo  %C_MAGENTA%[ERROR]%C_RESET% %C_WHITE%FFmpeg installation failed automatically.%C_RESET%
echo          %C_GRAY%Please download FFmpeg manually from https://ffmpeg.org and add it to PATH.%C_RESET%
pause
exit /b 1

:FFMPEG_OK

:: ── 3. Check & Auto-Install Node.js ──────────────────────
node -v >nul 2>&1
if not errorlevel 1 goto NODE_OK

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Node.js not detected in PATH. Attempting automatic installation via Winget...%C_RESET%
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id OpenJS.NodeJS -e --accept-source-agreements --accept-package-agreements
)

node -v >nul 2>&1
if not errorlevel 1 goto NODE_OK

echo  %C_MAGENTA%[ERROR]%C_RESET% %C_WHITE%Node.js is required for the new UI. Please install it from https://nodejs.org and re-run.%C_RESET%
pause
exit /b 1

:NODE_OK

:: ── 3. Create Virtual Environment ─────────────────────────
if exist "venv\Scripts\activate.bat" goto VENV_OK

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Creating Python virtual environment (venv)...%C_RESET%
set "PYCMD=python"
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "exit(0)" >nul 2>&1 && set "PYCMD=py -3.12"
    py -3.11 -c "exit(0)" >nul 2>&1 && set "PYCMD=py -3.11"
)

%PYCMD% -m venv venv
if errorlevel 1 (
    echo  %C_MAGENTA%[ERROR]%C_RESET% %C_WHITE%Failed to create virtual environment.%C_RESET%
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
        echo  %C_CYAN%[SETUP]%C_RESET% %C_GRAY%Creating .env file from template...%C_RESET%
        copy .env.example .env >nul
    )
)

:: ── 5. Install & Verify Python Dependencies ────────────────
echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Verifying & installing Python packages...%C_RESET%
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Installing Playwright Chromium browser...%C_RESET%
python -m playwright install chromium

:: ── 6. Check & Auto-Install Rust Toolchain ──────────────────
where cargo >nul 2>&1
if not errorlevel 1 goto RUST_OK
if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto RUST_OK
)

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Rust compiler not detected. Attempting automatic installation via rustup-init...%C_RESET%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$setup = Join-Path $env:TEMP 'rustup-init.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host ' [SETUP] Downloading rustup-init...'; Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile $setup; Write-Host ' [SETUP] Installing Rust (default toolchain)...'; Start-Process -FilePath $setup -ArgumentList '-y' -Wait; Remove-Item -Path $setup -Force -ErrorAction SilentlyContinue;"

if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    echo  %C_GREEN%[SETUP]%C_RESET% %C_WHITE%Rust installation complete!%C_RESET%
    goto RUST_OK
)

where winget >nul 2>&1
if not errorlevel 1 (
    echo  %C_CYAN%[SETUP]%C_RESET% %C_GRAY%Attempting Winget installation for Rustup...%C_RESET%
    winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements
)

if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    goto RUST_OK
)

:RUST_OK
where cargo >nul 2>&1
if not errorlevel 1 goto CHECK_RUST_CORE

echo  %C_GRAY%[INFO]%C_RESET%  %C_GRAY%Rust compiler not found. Native acceleration skipped - Python fallback active.%C_RESET%
goto LAUNCH

:CHECK_RUST_CORE
python -c "import clip_engine_core" >nul 2>&1
if not errorlevel 1 goto LAUNCH

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Building Rust native acceleration engine...%C_RESET%
python -m pip install maturin
maturin develop --release --manifest-path clip_engine_core/Cargo.toml

:LAUNCH

:: ── 7. Choose UI and Launch App Server ────────────────────
if not "%UI_CHOICE%"=="" goto PROCESS_CHOICE

echo:
echo %C_NEON%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_NEON%  │%C_WHITE%   SELECT USER INTERFACE MODE                                  %C_NEON%│%C_RESET%
echo %C_NEON%  ├──────────────────────────────────────────────────────────────┤%C_RESET%
echo %C_NEON%  │%C_GOLD%   [1]%C_WHITE% Classic Web UI %C_GRAY%(FastAPI - Launches local browser)  %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GOLD%   [2]%C_WHITE% Beta UI %C_GRAY%(Tauri + React Modern Desktop UI)           %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GOLD%   [3]%C_WHITE% Mobile & Wi-Fi Mode %C_GRAY%(Terminal Only - Phone/Tablet)   %C_NEON%│%C_RESET%
echo %C_NEON%  └──────────────────────────────────────────────────────────────┘%C_RESET%
echo:
set /p UI_CHOICE="%C_CYAN%Enter your choice (1, 2, or 3) [1]: %C_RESET%"
if "%UI_CHOICE%"=="" set UI_CHOICE=1

:PROCESS_CHOICE
if "%UI_CHOICE%"=="2" goto LAUNCH_BETA
if "%UI_CHOICE%"=="3" goto LAUNCH_MOBILE_SERVER

:LAUNCH_CLASSIC
echo:
echo %C_NEON%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_NEON%  │%C_WHITE%   🚀 OBSCURA CLIPS IS LIVE! %C_GRAY%(Classic Web UI)            %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   ---------------------------------------------------------- %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_WHITE%   🔗 Server URL: %C_GOLD%http://localhost:7842                     %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_WHITE%   🌐 Status:     %C_GREEN%Active & Listening...                   %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   ---------------------------------------------------------- %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   Press Ctrl+C in this terminal window to stop the server.   %C_NEON%│%C_RESET%
echo %C_NEON%  └──────────────────────────────────────────────────────────────┘%C_RESET%
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set OBSCURA_OPEN_BROWSER=1
python server.py
goto END_LAUNCH

:LAUNCH_MOBILE_SERVER
echo:
echo %C_PURPLE%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_PURPLE%  │%C_WHITE%   📱 OBSCURA CLIPS — MOBILE & WI-FI SERVER MODE              %C_PURPLE%│%C_RESET%
echo %C_PURPLE%  │%C_GRAY%   ---------------------------------------------------------- %C_PURPLE%│%C_RESET%
echo %C_PURPLE%  │%C_WHITE%   🌐 Status:     %C_GREEN%Active & Ready for Phone Connections!     %C_PURPLE%│%C_RESET%
echo %C_PURPLE%  │%C_WHITE%   📱 Mobile Access: Connect to your PC's IP on port %C_GOLD%7842     %C_PURPLE%│%C_RESET%
echo %C_PURPLE%  │%C_GRAY%   ---------------------------------------------------------- %C_PURPLE%│%C_RESET%
echo %C_PURPLE%  │%C_GRAY%   Press Ctrl+C in this terminal window to stop the server.   %C_PURPLE%│%C_RESET%
echo %C_PURPLE%  └──────────────────────────────────────────────────────────────┘%C_RESET%
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set OBSCURA_OPEN_BROWSER=0
python server.py
goto END_LAUNCH

:LAUNCH_BETA
echo:
echo %C_CYAN%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_CYAN%  │%C_WHITE%   BETA UI MODE SELECTION                                      %C_CYAN%│%C_RESET%
echo %C_CYAN%  ├──────────────────────────────────────────────────────────────┤%C_RESET%
echo %C_CYAN%  │%C_GOLD%   [Enter]%C_WHITE% Launch in Browser Localhost                     %C_CYAN%│%C_RESET%
echo %C_CYAN%  │%C_GOLD%   [B/b]  %C_WHITE% Install C++ Tools & Launch Native Desktop App (Tauri) %C_CYAN%│%C_RESET%
echo %C_CYAN%  └──────────────────────────────────────────────────────────────┘%C_RESET%
echo:
set /p BETA_MODE="%C_CYAN%Enter your choice [Browser]: %C_RESET%"

if /i "%BETA_MODE%"=="B" goto LAUNCH_TAURI_NATIVE

:LAUNCH_BROWSER
echo:
echo %C_NEON%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_NEON%  │%C_WHITE%   🚀 OBSCURA CLIPS IS LIVE! %C_GRAY%(Beta UI - Browser Localhost)%C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   ---------------------------------------------------------- %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_WHITE%   🔗 Server URL: %C_GOLD%http://localhost:5173                     %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   Press Ctrl+C in this terminal window to stop.              %C_NEON%│%C_RESET%
echo %C_NEON%  └──────────────────────────────────────────────────────────────┘%C_RESET%
echo:

:: Free port 7842 if a previous server instance is still running
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :7842 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

set OBSCURA_OPEN_BROWSER=0
start "Obscura Backend" python server.py
cd obscura-ui
start "" "http://localhost:5173"
call npm run dev
goto END_LAUNCH

:LAUNCH_TAURI_NATIVE
echo:
echo %C_CYAN%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_CYAN%  │%C_WHITE%   CHECKING NATIVE TAURI DEPENDENCIES...                       %C_CYAN%│%C_RESET%
echo %C_CYAN%  └──────────────────────────────────────────────────────────────┘%C_RESET%
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

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Installing Rust toolchain via rustup-init...%C_RESET%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$setup = Join-Path $env:TEMP 'rustup-init.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile $setup; Start-Process -FilePath $setup -ArgumentList '-y' -Wait; Remove-Item -Path $setup -Force -ErrorAction SilentlyContinue;"
if exist "%USERPROFILE%\.cargo\bin\cargo.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

:TAURI_RUST_OK

:: 2. Check/Install MSVC C++ Build Tools
where link >nul 2>&1
if not errorlevel 1 goto TAURI_BUILD_TOOLS_OK

echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%MSVC C++ Build Tools (link.exe) not detected.%C_RESET%
echo  %C_CYAN%[SETUP]%C_RESET% %C_WHITE%Installing Microsoft Visual C++ Build Tools via Winget...%C_RESET%
where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-source-agreements --accept-package-agreements --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools"
)

:TAURI_BUILD_TOOLS_OK
echo:
echo %C_NEON%  ┌──────────────────────────────────────────────────────────────┐%C_RESET%
echo %C_NEON%  │%C_WHITE%   🚀 OBSCURA CLIPS IS LIVE! %C_GRAY%(Beta UI - Native Desktop App)  %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   ---------------------------------------------------------- %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_WHITE%   Starting Python Backend and Tauri Desktop App...           %C_NEON%│%C_RESET%
echo %C_NEON%  │%C_GRAY%   Press Ctrl+C in this terminal window to stop.              %C_NEON%│%C_RESET%
echo %C_NEON%  └──────────────────────────────────────────────────────────────┘%C_RESET%
echo:
set OBSCURA_OPEN_BROWSER=0
start "Obscura Backend" python server.py
cd obscura-ui
call npm run tauri dev
if errorlevel 1 (
    echo:
    echo  %C_GOLD%[WARNING]%C_RESET% %C_WHITE%Native Tauri build failed. Falling back to Browser Localhost...%C_RESET%
    start "" "http://localhost:5173"
    call npm run dev
)

:END_LAUNCH
echo:
echo  %C_GRAY%[INFO] Server stopped.%C_RESET%
pause
exit /b 0
