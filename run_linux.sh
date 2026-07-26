#!/usr/bin/env bash
# Obscura Clips Linux launcher.
# Run this file from any directory: it always starts the server from this folder.
#
# Double-click from a file manager? The script detects the missing terminal
# and re-launches itself inside Konsole (or any available terminal emulator)
# so you can see the server output and stop it with Ctrl+C.

set -u

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$DIR" || {
    echo "[ERROR] Cannot open the Obscura Clips folder: $DIR" >&2
    exit 1
}

log() { echo "[SETUP] $*"; }
warn() { echo "[WARNING] $*"; }
err() { echo "[ERROR] $*" >&2; }

# ── Re-launch inside a visible terminal when not already attached to one ──
if [ ! -t 0 ] || [ -z "${TERM:-}" ]; then
    for candidate in konsole x-terminal-emulator xterm gnome-terminal kgx ptyxis kitty alacritty terminology; do
        if command -v "$candidate" >/dev/null 2>&1; then
            case "$candidate" in
                konsole)
                    exec konsole --hold -e bash -- "$0" "$@"
                    ;;
                xterm|kitty|alacritty|terminology)
                    exec "$candidate" --hold -e bash -- "$0" "$@"
                    ;;
                *)
                    # gnome-terminal, kgx, ptyxis, x-terminal-emulator, tilix, etc.
                    exec "$candidate" -- bash -- "$0" "$@"
                    ;;
            esac
        fi
    done
    # No terminal emulator available — continue headless; the server still starts.
fi

echo
log "=============================================================="
log "                      O B S C U R A   C L I P S"
log "=============================================================="
echo

# Keep application state with this installation. This avoids a failed launch
# when the desktop session cannot write to ~/.local/state (a common issue with
# file-manager and sandbox launches).
export XDG_STATE_HOME="$DIR/.state"
mkdir -p "$XDG_STATE_HOME" || {
    err "Cannot create application state directory: $XDG_STATE_HOME"
    exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
    err "Python 3 is required. Install Python 3 and run this launcher again."
    exit 1
fi

if [ ! -x "$DIR/venv/bin/python" ]; then
    log "Creating a Python virtual environment..."

    # Prefer a Python version known to have mature, well-tested GPU wheels for
    # ctranslate2/faster-whisper. A bare `python3` can resolve to whatever is
    # newest on the system (e.g. 3.13/3.14), where GPU support in some
    # dependencies is brand new or still shaky even if CPU works fine.
    PYBIN=""
    for candidate in python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYBIN="$candidate"
            break
        fi
    done

    if [ -z "$PYBIN" ]; then
        err "No usable Python 3 interpreter was found."
        exit 1
    fi

    PYVER="$($PYBIN -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    case "$PYVER" in
        3.13|3.14|3.15|3.16)
            warn "Only Python $PYVER was found. GPU acceleration (faster-whisper/ctranslate2)"
            warn "may be unreliable on very new Python versions — if transcription keeps"
            warn "falling back to CPU or erroring on GPU, install Python 3.11 or 3.12 and"
            warn "delete the venv/ folder to rebuild against it."
            ;;
    esac

    "$PYBIN" -m venv "$DIR/venv" || {
        err "Could not create the virtual environment. Install the python3-venv package and retry."
        exit 1
    }
fi

PYTHON="$DIR/venv/bin/python"
PIP="$DIR/venv/bin/pip"

ensure_pip_tools() {
    "$PYTHON" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
}

ensure_cuda_wheels() {
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        return 0
    fi

    # Skip the expensive install path when libcublas is already usable in this environment.
    if "$PYTHON" - <<'PY' >/dev/null 2>&1
import ctypes
ctypes.CDLL("libcublas.so.12")
PY
    then
        return 0
    fi

    log "NVIDIA GPU detected, but libcublas.so.12 is not loadable yet. Installing CUDA runtime wheels into the project venv..."
    ensure_pip_tools

    CUDA_PACKAGES=(
        nvidia-cuda-runtime-cu12
        nvidia-cublas-cu12
        nvidia-cudnn-cu12
    )

    if ! "$PYTHON" -m pip install --upgrade "${CUDA_PACKAGES[@]}"; then
        warn "Direct CUDA wheel install failed. Retrying through NVIDIA's package index..."
        "$PYTHON" -m pip install --upgrade nvidia-pyindex || {
            warn "Could not install nvidia-pyindex either. GPU acceleration may stay unavailable."
            return 1
        }
        "$PYTHON" -m pip install --upgrade "${CUDA_PACKAGES[@]}" || {
            warn "CUDA wheels still failed to install. GPU acceleration may stay unavailable."
            return 1
        }
    fi

    return 0
}

inject_cuda_library_paths() {
    local extra_paths
    extra_paths="$("$PYTHON" - <<'PY'
import site
from pathlib import Path
paths = []
seen = set()
for site_pkg in site.getsitepackages():
    sp = Path(site_pkg)
    for p in sp.glob('nvidia/*'):
        for leaf in ('lib', 'lib64', 'bin'):
            candidate = p / leaf
            if candidate.exists() and candidate.is_dir():
                s = str(candidate)
                if s not in seen:
                    seen.add(s)
                    paths.append(s)
print(':'.join(paths))
PY
)"

    if [ -n "${extra_paths:-}" ]; then
        export LD_LIBRARY_PATH="$extra_paths${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export PATH="$extra_paths${PATH:+:$PATH}"
    fi
}

ensure_cuda_wheels || true
inject_cuda_library_paths

# ── Ensure runtime directories exist ──
mkdir -p "$DIR/output" "$DIR/temp" "$DIR/broll_cache" "$DIR/credentials" "$DIR/scratch"

# ── Ensure .env exists ──
if [ ! -f "$DIR/.env" ] && [ -f "$DIR/.env.example" ]; then
    log "Creating default .env from .env.example..."
    cp "$DIR/.env.example" "$DIR/.env"
fi

if ! "$PYTHON" -c 'import fastapi, uvicorn, playwright' >/dev/null 2>&1; then
    log "Installing Python dependencies..."
    "$PYTHON" -m pip install -r "$DIR/requirements.txt" || {
        err "Dependency installation failed. Check your internet connection and retry."
        exit 1
    }
    log "Installing Playwright Chromium browser..."
    "$PYTHON" -m playwright install chromium || {
        warn "Playwright browser installation failed. The application will attempt to auto-install it on first browser login."
    }
fi

# ── Build Rust Native Acceleration ──
if ! command -v cargo >/dev/null 2>&1; then
    warn "Rust compiler (cargo) is not installed. Native acceleration will be skipped."
else
    if ! "$PYTHON" -c 'import clip_engine_core' >/dev/null 2>&1; then
        log "Building Rust native acceleration engine..."
        "$PYTHON" -m pip install maturin || true
        "$PYTHON" -m maturin develop --release --manifest-path "$DIR/clip_engine_core/Cargo.toml" || {
            warn "Rust acceleration engine failed to build. Ensure Rust is up to date."
        }
    fi
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    warn "FFmpeg was not found. The web interface will start, but video processing will require FFmpeg."
fi

log "Starting server at http://127.0.0.1:7842"
log "Press Ctrl+C to stop."
echo

exec "$PYTHON" "$DIR/server.py"
