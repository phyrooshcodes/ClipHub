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
    _clean_old_downloads()
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
        self.created_at = time.time()

active_downloads: Dict[str, DownloadJob] = {}

def _clean_old_downloads():
    now = time.time()
    # Remove jobs older than 1 hour or evict oldest when size > 40
    stale_keys = [k for k, job in active_downloads.items() if (now - getattr(job, "created_at", now)) > 3600 and job.done]
    for k in stale_keys:
        active_downloads.pop(k, None)
    if len(active_downloads) > 40:
        for k in list(active_downloads.keys())[:20]:
            active_downloads.pop(k, None)

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
    env = os.environ.copy()
    local_bin = str(BASE_DIR / "bin")
    c_ffmpeg = r"C:\ffmpeg\bin"
    current_path = env.get("PATH", "")
    paths_to_add = [p for p in [local_bin, c_ffmpeg] if Path(p).exists() and p not in current_path]
    if paths_to_add:
        env["PATH"] = os.pathsep.join(paths_to_add) + os.pathsep + current_path

    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    async def execute_cmd(use_cookies: bool) -> bool:
        cmd = [
            python_exe, "-m", "yt_dlp",
        ]
        if use_cookies:
            cmd.extend(_get_cookies_args())
        cmd.extend([
            "--remote-components", "ejs:github",
            "--js-runtimes", "node",
            "--format", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "--output", save_path,
            "--newline", "--no-playlist", "--no-part", "--", job.url
        ])

        job.events.append({"type": "ytdl_start", "url": job.url})
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env=env
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
                    print(f"[YouTube Download] {text}", flush=True)
                    continue
                job.events.append({"type": "ytdl_log", "raw": text})
                print(f"[YouTube Download] {text}", flush=True)

            await process.wait()
            return process.returncode == 0 and Path(save_path).exists()
        except Exception as e:
            job.events.append({"type": "ytdl_log", "raw": f"Execution error: {e}"})
            print(f"[YouTube Download Error] {e}", flush=True)
            return False

    try:
        # First attempt: Try standard download (fast, no browser cookie database locks)
        success = await execute_cmd(use_cookies=False)
        if not success and not Path(save_path).exists():
            # Second attempt: Try with cookies if standard download failed (for age-restricted/private videos)
            job.events.append({"type": "ytdl_log", "raw": "Standard download unfulfilled. Retrying with browser cookies..."})
            success = await execute_cmd(use_cookies=True)

        if success and Path(save_path).exists():
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
async def download_url_ws(websocket: WebSocket, job_id: str, url: str = ""):
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
        _clean_old_downloads()
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
