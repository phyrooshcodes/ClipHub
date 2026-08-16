import os
import threading
import time
import webbrowser
import logging
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import API Routers
from api.pipeline import router as pipeline_router
from api.social import router as social_router
from api.downloads import router as downloads_router

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server")

# ─── Paths ──────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# LAN mode is opt-in.  A token is generated when the launcher enables it so a
# device on the same Wi-Fi cannot silently operate the user's social accounts.
if os.environ.get("CLIPHUB_HOST") == "0.0.0.0" and not os.environ.get("CLIPHUB_LAN_TOKEN"):
    os.environ["CLIPHUB_LAN_TOKEN"] = secrets.token_urlsafe(24)

UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UI_FILE    = BASE_DIR / "ui" / "index.html"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """The server is the only process allowed to run the background upload workers."""
    try:
        from modules.instagram_queue import get_instagram_queue
        from modules.youtube_worker import get_youtube_worker
        get_instagram_queue(start_worker=True)
        get_youtube_worker()
    except Exception as e:
        logger.warning(f"[Server] Worker initialization notice: {e}")
    yield

# ─── FastAPI App ────────────────────────────────────────────
app = FastAPI(title="ClipHub", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "tauri://localhost", "http://tauri.localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-ClipHub-Token"],
)

from api.security import is_loopback, lan_mode_enabled, lan_token

@app.middleware("http")
async def require_lan_token(request, call_next):
    """Protect every HTTP route when the server is intentionally LAN-visible."""
    client_host = request.client.host if request.client else None
    if lan_mode_enabled() and not is_loopback(client_host):
        supplied = (
            request.headers.get("X-ClipHub-Token")
            or request.cookies.get("cliphub_lan_token")
            or request.query_params.get("token")
        )
        if supplied != lan_token():
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "LAN authorization required."}, status_code=401)
    response = await call_next(request)
    if lan_mode_enabled() and request.query_params.get("token") == lan_token():
        response.set_cookie("cliphub_lan_token", lan_token(), httponly=True, samesite="strict")
    return response

from fastapi.staticfiles import StaticFiles

# ─── Include Routers ────────────────────────────────────────
app.include_router(pipeline_router)
app.include_router(social_router)
app.include_router(downloads_router)

# ─── Static Output Mounting (supports video streaming & Range headers) ──
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# ─── Static UI Routes ───────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return UI_FILE.read_text(encoding="utf-8")

@app.get("/style.css", response_class=FileResponse)
async def get_style():
    return FileResponse(BASE_DIR / "ui" / "style.css")

@app.get("/app.js", response_class=FileResponse)
async def get_app():
    return FileResponse(BASE_DIR / "ui" / "app.js")

@app.get("/logo.jpg", response_class=FileResponse)
async def get_logo():
    return FileResponse(BASE_DIR / "ui" / "logo.jpg")

# ─── Helper ─────────────────────────────────────────────────
def get_local_ip() -> str:
    import socket
    # 1. Primary method: probe outbound routing table (no traffic sent)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass

    # 2. Secondary method: query hostname IP list (works offline/airgapped)
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"

@app.get("/api/server-info")
async def server_info():
    ip = get_local_ip()
    host = os.environ.get("CLIPHUB_HOST", "127.0.0.1")
    is_lan = host == "0.0.0.0"
    return {
        "local_url": "http://localhost:7842",
        "wifi_url": f"http://{ip}:7842" if is_lan else None,
        "wifi_ip": ip if is_lan else "127.0.0.1",
        "is_lan_mode": is_lan
    }

@app.get("/api/system-status")
async def get_system_status():
    import subprocess
    status = {
        "gpu": "Detecting...",
        "nvenc": "Detecting...",
        "kokoro": "Ready",
        "whisper": "Ready"
    }
    
    # Try detecting GPU via nvidia-smi
    try:
        res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            gpu_name = res.stdout.strip().split("\n")[0]
            status["gpu"] = gpu_name
            status["nvenc"] = "Ready" if "RTX" in gpu_name or "GTX" in gpu_name else "Unsupported"
        else:
            status["gpu"] = "CPU / Unknown"
            status["nvenc"] = "Not available"
    except Exception:
        status["gpu"] = "CPU Only"
        status["nvenc"] = "Not available"
        
    return status

# ─── Entry Point ─────────────────────────────────────────────
def _open_browser(port: int = 7842):
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{port}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ClipHub Desktop Server")
    parser.add_argument("--host", default=os.environ.get("CLIPHUB_HOST", "127.0.0.1"), help="Host IP to bind (default: 127.0.0.1 for desktop security)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CLIPHUB_PORT", "7842")), help="Port to bind (default: 7842)")
    cli_args = parser.parse_args()

    host = cli_args.host
    port = cli_args.port
    if host == "0.0.0.0":
        # Support direct CLI use as well as the Windows launcher.
        os.environ["CLIPHUB_HOST"] = host
        os.environ.setdefault("CLIPHUB_LAN_TOKEN", secrets.token_urlsafe(24))

    if os.environ.get("CLIPHUB_OPEN_BROWSER", "1") == "1":
        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    local_ip = get_local_ip()
    print("\n" + "=" * 55)
    print("  ✦  CLIPHUB STUDIO SERVER STARTED")
    print("=" * 55)
    print(f"  • Local Interface : http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"  • LAN Access      : http://{local_ip}:{port}/?token={lan_token()} (LAN Mode Active)")
    else:
        print(f"  • Security Mode   : Desktop Only (Loopback 127.0.0.1)")
        print(f"  • LAN Sharing     : Pass --host 0.0.0.0 to enable")
    print("=" * 55 + "\n")

    uvicorn.run(app, host=host, port=port, log_level="warning")
