#!/usr/bin/env python3
# ============================================================
# server.py — Obscura Clips Web UI Server
# Orchestrator for the Obscura Clips Web UI
# ============================================================

import threading
import time
import webbrowser
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
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

UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UI_FILE    = BASE_DIR / "ui" / "index.html"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── FastAPI App ────────────────────────────────────────────
app = FastAPI(title="Obscura Clips")

@app.on_event("startup")
async def start_instagram_queue_worker() -> None:
    """The server is the only process allowed to run the browser uploader."""
    from modules.instagram_queue import get_instagram_queue
    from modules.youtube_worker import get_youtube_worker
    get_instagram_queue(start_worker=True)
    get_youtube_worker()

# ─── Include Routers ────────────────────────────────────────
app.include_router(pipeline_router)
app.include_router(social_router)
app.include_router(downloads_router)

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

# ─── Entry Point ─────────────────────────────────────────────
def _open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:7842")

if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    print("\n  *  Obscura Clips - UI server starting")
    print("  -> http://localhost:7842")
    print("  -> Press Ctrl+C to stop\n")
    uvicorn.run(app, host="127.0.0.1", port=7842, log_level="warning")
