import asyncio
import os
import re
import sys
import time
import uuid
import shutil
from pathlib import Path
from typing import Dict, List
import threading

from fastapi import APIRouter, WebSocket, Query
from fastapi.responses import JSONResponse, FileResponse
from api.jobs import registry
from api.security import websocket_is_authorized

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

MAX_CONCURRENT_DOWNLOADS = 5

class DownloadJob:
    def __init__(self, job_id, url):
        self.job_id = job_id
        self.url = url
        self.events = []
        self.done = False
        self.task = None
        self.created_at = time.time()

    def add_event(self, event: dict):
        self.events.append(event)

active_downloads: Dict[str, DownloadJob] = {}
_downloads_lock = threading.Lock()

def _clean_old_downloads():
    now = time.time()
    with _downloads_lock:
        stale_keys = [k for k, job in active_downloads.items() if job.done and (now - getattr(job, "created_at", now)) > 3600]
        for k in stale_keys:
            active_downloads.pop(k, None)
        if len(active_downloads) > 40:
            done_keys = [k for k, job in active_downloads.items() if job.done]
            for k in done_keys[:20]:
                active_downloads.pop(k, None)

@router.post("/prepare-download")
@router.post("/api/download-yt")
async def prepare_download():
    _clean_old_downloads()
    with _downloads_lock:
        active_count = sum(1 for j in active_downloads.values() if not j.done and j.task is not None)
        if active_count >= MAX_CONCURRENT_DOWNLOADS:
            return JSONResponse({"error": "Maximum concurrent downloads limit reached (5). Please wait for active downloads to finish."}, status_code=429)
        job_id = uuid.uuid4().hex[:16]
        active_downloads[job_id] = DownloadJob(job_id, "")
    return {"job_id": job_id}

async def _run_ytdl(job: DownloadJob, python_exe: str, save_path: str):
    env = os.environ.copy()
    ffmpeg_bin = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"
    ffmpeg_dir = str(Path(ffmpeg_bin).parent) if (ffmpeg_bin and Path(ffmpeg_bin).exists()) else ""
    local_bin = str(BASE_DIR / "bin")
    node_dir = r"C:\Program Files\nodejs"
    current_path = env.get("PATH", "")
    paths_to_add = [p for p in [local_bin, ffmpeg_dir, node_dir] if p and Path(p).exists() and p not in current_path]
    if paths_to_add:
        env["PATH"] = os.pathsep.join(paths_to_add) + os.pathsep + current_path

    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    node_bin = shutil.which("node") or (r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else "node")

    async def run_command_stream(cmd_args: list) -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            current_phase = "video"
            saw_100 = False
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes: break
                text = line_bytes.decode("utf-8", errors="replace").rstrip()
                if not text.strip(): continue

                if "[Merger]" in text or "Merging formats" in text:
                    current_phase = "merging"
                    job.add_event({
                        "type": "ytdl_progress", "percent": 99.0,
                        "phase": "merging", "size": "Finalizing MP4",
                        "speed": "Merging streams...", "eta": "00:01"
                    })
                    print(f"[YouTube Download] {text}", flush=True)
                    continue

                m = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+([~\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+(\S+)", text)
                if m:
                    raw_pct = float(m.group(1))
                    if raw_pct >= 99.0 and not saw_100:
                        saw_100 = True
                    elif saw_100 and raw_pct < 50.0:
                        current_phase = "audio"
                    
                    if current_phase == "audio":
                        scaled_pct = round(85.0 + (raw_pct * 0.14), 1)
                    elif current_phase == "merging":
                        scaled_pct = 99.0
                    else:
                        scaled_pct = round(raw_pct * 0.85, 1)

                    job.add_event({
                        "type": "ytdl_progress", "percent": scaled_pct,
                        "raw_percent": raw_pct, "phase": current_phase,
                        "size": m.group(2), "speed": m.group(3), "eta": m.group(4),
                    })
                    print(f"[YouTube Download] {text}", flush=True)
                    continue

                job.add_event({"type": "ytdl_log", "raw": text})
                print(f"[YouTube Download] {text}", flush=True)

            await process.wait()
            return process.returncode == 0 and Path(save_path).exists()
        except Exception as e:
            job.add_event({"type": "ytdl_log", "raw": f"Execution error: {e}"})
            print(f"[YouTube Download Error] {e}", flush=True)
            return False

    try:
        job.add_event({"type": "ytdl_start", "url": job.url})
        node_str = f"node:{node_bin}" if Path(str(node_bin)).exists() else "node"

        # Primary high-definition 1080p command
        primary_cmd = [
            python_exe, "-m", "yt_dlp",
            "--no-playlist",
            "--force-overwrites",
            "--format", "bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "--retries", "5",
            "--fragment-retries", "5",
            "--newline",
            "--no-part",
            "-o", save_path,
        ]
        if ffmpeg_dir:
            primary_cmd.extend(["--ffmpeg-location", ffmpeg_dir])
        if Path(str(node_bin)).exists():
            primary_cmd.extend(["--js-runtimes", node_str])
        primary_cmd.extend(["--", job.url])

        success = await run_command_stream(primary_cmd)
        
        # Resilient fallback if 403 Forbidden or DASH signing throttled
        if not success or not Path(save_path).exists():
            job.add_event({"type": "ytdl_log", "raw": "[Info] High-definition DASH stream restricted. Switching to Android/Web stream fallback..."})
            fallback_cmd = [
                python_exe, "-m", "yt_dlp",
                "--no-playlist",
                "--force-overwrites",
                "--extractor-args", "youtube:player_client=ios,android,web",
                "--format", "best[height<=1080]/best",
                "--merge-output-format", "mp4",
                "--retries", "5",
                "--newline",
                "-o", save_path,
            ]
            if ffmpeg_dir:
                fallback_cmd.extend(["--ffmpeg-location", ffmpeg_dir])
            if Path(str(node_bin)).exists():
                fallback_cmd.extend(["--js-runtimes", node_str])
            fallback_cmd.extend(["--", job.url])

            success = await run_command_stream(fallback_cmd)

        if success and Path(save_path).exists():
            registry.register(job.job_id, save_path, f"job_{job.job_id}.mp4")
            job.add_event({
                "type": "ytdl_done", "job_id": job.job_id,
                "filename": f"job_{job.job_id}.mp4",
                "size_mb": round(Path(save_path).stat().st_size / 1024 / 1024, 1),
            })
        else:
            job.add_event({"type": "error", "message": "Public download failed or URL is invalid."})
    except Exception as e:
        job.add_event({"type": "error", "message": str(e)})
    finally:
        job.done = True

@router.websocket("/ws-ytdl/{job_id}")
async def download_url_ws(websocket: WebSocket, job_id: str, url: str = ""):
    if not websocket_is_authorized(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    
    python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
    if not Path(python_exe).exists():
        python_exe = str(BASE_DIR / "venv" / "bin" / "python")
        if not Path(python_exe).exists():
            python_exe = sys.executable

    save_path = str(UPLOAD_DIR / f"job_{job_id}.mp4")
    
    with _downloads_lock:
        if job_id not in active_downloads:
            active_count = sum(1 for j in active_downloads.values() if not j.done and j.task is not None)
            if active_count >= MAX_CONCURRENT_DOWNLOADS:
                await websocket.send_json({"type": "error", "message": "Maximum concurrent downloads limit reached (5)."})
                await websocket.close()
                return
            job = DownloadJob(job_id, url)
            active_downloads[job_id] = job
        else:
            job = active_downloads[job_id]
            if url and not job.url:
                job.url = url

        if job.task is None and not job.done and job.url:
            job.task = asyncio.create_task(_run_ytdl(job, python_exe, save_path))

    try:
        last_index = 0
        while True:
            while last_index < len(job.events):
                event = job.events[last_index]
                last_index += 1
                await websocket.send_json(event)
                if event.get("type") in ("ytdl_done", "error"):
                    return
            if job.done:
                while last_index < len(job.events):
                    event = job.events[last_index]
                    last_index += 1
                    await websocket.send_json(event)
                break
            await asyncio.sleep(0.05)
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
        valid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        for f in UPLOAD_DIR.iterdir():
            if not f.is_file() or f.suffix.lower() not in valid_exts:
                continue
            stat = f.stat()
            m = re.match(r"job_([a-f0-9]{8,32})(\.[a-zA-Z0-9]+)$", f.name)
            if m:
                jid = m.group(1)
                job = registry.get(jid)
                display_name = job.filename if job else f.name
            else:
                jid = f.stem
                job = registry.get(jid)
                display_name = job.filename if job else f.name
                
            uploads.append({
                "job_id": jid,
                "filename": display_name,
                "file_path": f.name,
                "size_mb": round(stat.st_size / 1024 / 1024, 1),
                "created": stat.st_mtime
            })
    return {"uploads": sorted(uploads, key=lambda x: x["created"], reverse=True)}

@router.get("/output/{filename}")
async def serve_output(filename: str):
    path = (OUTPUT_DIR / filename).resolve()
    if not path.is_relative_to(OUTPUT_DIR.resolve()) or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")

@router.get("/output/caption_studio/{filename}")
async def serve_caption_studio_output(filename: str):
    path = (OUTPUT_DIR / "caption_studio" / filename).resolve()
    if not path.is_relative_to(OUTPUT_DIR.resolve()) or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")

@router.get("/output/{job_id}/{filename}")
async def serve_job_output(job_id: str, filename: str):
    path = (OUTPUT_DIR / job_id / filename).resolve()
    if not path.is_relative_to(OUTPUT_DIR.resolve()) or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")
