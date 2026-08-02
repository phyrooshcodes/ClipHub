import asyncio
import os
import re
import sys
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, WebSocket, Query
from fastapi.responses import JSONResponse, FileResponse
from api.jobs import registry

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

@router.post("/prepare-download")
async def prepare_download():
    job_id = str(uuid.uuid4())[:8]
    return {"job_id": job_id}

import asyncio
from typing import Dict, List

class DownloadJob:
    def __init__(self, job_id, url):
        self.job_id = job_id
        self.url = url
        self.events = []
        self.done = False
        self.task = None

active_downloads: Dict[str, DownloadJob] = {}

def _get_cookies_args():
    home = Path.home()
    if (home / ".mozilla" / "firefox").exists() or (home / "Library" / "Application Support" / "Firefox").exists():
        return ["--cookies-from-browser", "firefox"]
    if (home / ".config" / "google-chrome").exists() or (home / "Library" / "Application Support" / "Google" / "Chrome").exists() or (home / "AppData" / "Local" / "Google" / "Chrome" / "User Data").exists():
        return ["--cookies-from-browser", "chrome"]
    if (home / ".config" / "chromium").exists() or (home / "AppData" / "Local" / "Chromium" / "User Data").exists():
        return ["--cookies-from-browser", "chromium"]
    if (home / ".config" / "BraveSoftware" / "Brave-Browser").exists() or (home / "AppData" / "Local" / "BraveSoftware" / "Brave-Browser" / "User Data").exists():
        return ["--cookies-from-browser", "brave"]
    if (home / ".config" / "microsoft-edge").exists() or (home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data").exists():
        return ["--cookies-from-browser", "edge"]
    return ["--cookies-from-browser", "firefox"]

async def _run_ytdl(job: DownloadJob, python_exe: str, save_path: str):
    cmd = [
        python_exe, "-m", "yt_dlp",
        *_get_cookies_args(),
        "--remote-components", "ejs:github",
        "--js-runtimes", "node",
        "--format", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--output", save_path,
        "--newline", "--no-playlist", "--no-part", "--", job.url
    ]
    job.events.append({"type": "ytdl_start", "url": job.url})
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        )
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes: break
            text = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not text.strip(): continue

            m = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+([~\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+(\S+)", text)
            if m:
                job.events.append({
                    "type": "ytdl_progress", "percent": float(m.group(1)),
                    "size": m.group(2), "speed": m.group(3), "eta": m.group(4),
                })
                continue
            job.events.append({"type": "ytdl_log", "raw": text})

        await process.wait()
        if process.returncode == 0 and Path(save_path).exists():
            registry.register(job.job_id, save_path, f"job_{job.job_id}.mp4")
            job.events.append({
                "type": "ytdl_done", "job_id": job.job_id,
                "filename": f"job_{job.job_id}.mp4",
                "size_mb": round(Path(save_path).stat().st_size / 1024 / 1024, 1),
            })
        else:
            job.events.append({"type": "error", "message": "Download failed."})
    except Exception as e:
        job.events.append({"type": "error", "message": str(e)})
    finally:
        job.done = True

@router.websocket("/ws-ytdl/{job_id}")
async def download_url_ws(websocket: WebSocket, job_id: str, url: str = Query(...)):
    await websocket.accept()
    
    python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
    if not Path(python_exe).exists():
        python_exe = str(BASE_DIR / "venv" / "bin" / "python")
        if not Path(python_exe).exists():
            python_exe = sys.executable

    save_path = str(UPLOAD_DIR / f"job_{job_id}.mp4")
    
    if job_id not in active_downloads:
        job = DownloadJob(job_id, url)
        active_downloads[job_id] = job
        job.task = asyncio.create_task(_run_ytdl(job, python_exe, save_path))
    else:
        job = active_downloads[job_id]

    try:
        last_index = 0
        while True:
            if last_index < len(job.events):
                event = job.events[last_index]
                await websocket.send_json(event)
                last_index += 1
                if event.get("type") in ("ytdl_done", "error"):
                    break
            elif job.done:
                break
            else:
                await asyncio.sleep(0.2)


    except Exception as e:
        try: await websocket.send_json({"type": "error", "message": str(e)})
        except: pass
    finally:
        try: await websocket.close()
        except: pass

@router.get("/uploads")
async def list_uploads():
    uploads = []
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.glob("job_*.mp4"):
            m = re.match(r"job_([a-f0-9]{8})\.mp4", f.name)
            if m:
                jid = m.group(1)
                stat = f.stat()
                job = registry.get(jid)
                if not job:
                    job = registry.register(jid, str(f), f.name)
                    job.start_time = stat.st_mtime
                uploads.append({
                    "job_id": jid,
                    "filename": job.filename,
                    "size_mb": round(stat.st_size / 1024 / 1024, 1),
                    "created": stat.st_mtime
                })
    return {"uploads": sorted(uploads, key=lambda x: x["created"], reverse=True)}

@router.get("/output/{filename}")
async def serve_output(filename: str):
    path = (OUTPUT_DIR / filename).resolve()
    if not path.is_relative_to(OUTPUT_DIR.resolve()) or not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")

@router.get("/output/{job_id}/{filename}")
async def serve_job_output(job_id: str, filename: str):
    path = (OUTPUT_DIR / job_id / filename).resolve()
    if not path.is_relative_to(OUTPUT_DIR.resolve()) or not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")
