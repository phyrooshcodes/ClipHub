import asyncio
import os
import re
import sys
import time
import uuid
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, UploadFile, File, Request
from fastapi.responses import JSONResponse
from api.jobs import registry

logger = logging.getLogger(__name__)
router = APIRouter()
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

def _parse_log_line(text: str) -> dict:
    m = re.search(r"STAGE\s+(\d+)/6[^─\-]*[\-─]\s*(.+?)(?:\s*[═=]+\s*$|\s*$)", text)
    if m: return {"type": "stage", "stage": int(m.group(1)), "label": m.group(2).strip()}
    m = re.search(r"CLIP\s+(\d+)/(\d+)", text)
    if m: return {"type": "clip_start", "clip_num": int(m.group(1)), "total": int(m.group(2))}
    m = re.search(r"\[(\d+)/6\]\s+(.+)", text)
    if m: return {"type": "substage", "substage": int(m.group(1)), "label": m.group(2).strip()}
    m = re.search(r"Done.*?(?:→|->)\s*(output[/\\].+?\.mp4)", text, re.IGNORECASE)
    if m: return {"type": "clip_ready", "path": m.group(1)}
    low = text.lower()
    if "error" in low or "failed" in low or "traceback" in low:
        return {"type": "warning"}
    return {"type": "log"}

def clean_clip_title(raw_title: str) -> str:
    if not raw_title: return "Untitled Clip"
    title = str(raw_title).strip()
    if title.lower().endswith(".mp4"): title = title[:-4]
    title = re.sub(r'^(?:clip[_\s\-]*\d+[_\s\-]*)+', '', title, flags=re.I).strip()
    if "_" in title and " " not in title: title = title.replace("_", " ")
    return title.strip() or "Untitled Clip"

def _list_clips(job_id: str = None, newer_than: float = 0) -> list:
    clips = []
    if not OUTPUT_DIR.exists(): return clips
    dirs = [OUTPUT_DIR / job_id] if job_id else [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
    for d in dirs:
        if not d.exists(): continue
        meta_list = []
        mf = d / "clips_metadata.json"
        if mf.exists():
            try:
                with open(mf, "r", encoding="utf-8") as f: meta_list = json.load(f)
            except Exception as e: logger.error(f"Failed to read clips metadata: {e}")
        
        mp4_files = sorted([f for f in d.glob("*.mp4")])
        for idx, f in enumerate(mp4_files):
            stat = f.stat()
            if stat.st_mtime < newer_than: continue
            
            match = re.search(r'clip[_\s\-]*(\d+)', f.name, re.I)
            cidx = (int(match.group(1)) - 1) if match else -1
            
            clip_meta = {}
            # 1. Match by stored filename in metadata
            for item in meta_list:
                if item.get("filename") == f.name:
                    clip_meta = item
                    break
            
            # 2. Match by clip index regex if present
            if not clip_meta and 0 <= cidx < len(meta_list):
                clip_meta = meta_list[cidx]
            
            # 3. Match by partial title (fuzzy / prefix)
            if not clip_meta:
                for item in meta_list:
                    it_title = clean_clip_title(item.get("title", "")).lower()
                    f_title  = clean_clip_title(f.name).lower()
                    if it_title and f_title and (it_title in f_title or f_title in it_title or it_title[:15] == f_title[:15]):
                        clip_meta = item
                        break
            
            # 4. Fallback to list order index if meta_list length matches mp4 file count
            if not clip_meta and idx < len(meta_list):
                clip_meta = meta_list[idx]
            
            raw_title = clip_meta.get("title") or f.name
            social_cap = clip_meta.get("social_caption", "")
            if social_cap: social_cap = re.sub(r'^(?:clip[_\s\-]*\d+[_\s\-]*)+', '', social_cap, flags=re.I).strip()
            
            clips.append({
                "filename": f.name, "size_mb": round(stat.st_size / 1024 / 1024, 1),
                "url": f"/output/{d.name}/{f.name}", "modified": stat.st_mtime,
                "title": clean_clip_title(raw_title), "clip_number": cidx + 1 if cidx >= 0 else (idx + 1),
                "social_caption": social_cap, "reason": clip_meta.get("reason", clip_meta.get("hook_explanation", "")),
                "hook_score": clip_meta.get("hook_score", clip_meta.get("viral_score", 90)), "viral_rating": clip_meta.get("viral_rating", None),
                "retention_score": clip_meta.get("retention_score", None), "viral_analysis": clip_meta.get("viral_analysis", ""),
                "broll_cues": clip_meta.get("broll_cues", []),
                "product_recommendations": clip_meta.get("product_recommendations", [])
            })
    return sorted(clips, key=lambda c: c["modified"], reverse=True)

async def _run_process(job_id: str, cmd: list, start_time: float):
    job = registry.get(job_id)
    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "QT_QPA_PLATFORM": "offscreen"}
        try:
            import site
            site_dirs = [str(BASE_DIR / "venv" / "Scripts" / "site-packages"), str(BASE_DIR / "venv" / "Lib" / "site-packages")]
            try: site_dirs.extend(site.getsitepackages())
            except Exception: pass
            
            nvidia_paths = []
            for sdir in site_dirs:
                nd = Path(sdir) / "nvidia"
                if nd.exists():
                    for sub in nd.iterdir():
                        for leaf in ["bin", "lib", ""]:
                            p = sub / leaf if leaf else sub
                            if p.exists() and str(p) not in nvidia_paths:
                                nvidia_paths.append(str(p))
            if nvidia_paths:
                sep = ";" if sys.platform == "win32" else ":"
                env["PATH"] = sep.join(nvidia_paths) + sep + env.get("PATH", "")
                env["LD_LIBRARY_PATH"] = ":".join(nvidia_paths) + (":" + env.get("LD_LIBRARY_PATH", "") if env.get("LD_LIBRARY_PATH") else "")
        except Exception as e: logger.warning(f"Failed to inject nvidia paths: {e}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR), env=env
        )
        if job: job.process = process

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes: break
            text = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not text.strip(): continue
            event = _parse_log_line(text)
            event["raw"] = text
            registry.add_event(job_id, event)

        await process.wait()
        success = process.returncode == 0
        if success:
            job_dir = OUTPUT_DIR / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            meta = {"job_id": job_id, "filename": job.filename if job else "unknown", "created": time.time()}
            with open(job_dir / "metadata.json", "w", encoding="utf-8") as f: json.dump(meta, f)

        clips = _list_clips(job_id=job_id, newer_than=start_time - 5)
        registry.add_event(job_id, {"type": "done", "success": success, "clips": clips})
    except Exception as e:
        registry.add_event(job_id, {"type": "error", "message": str(e)})
    finally:
        registry.mark_done(job_id)

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())[:8]
    suffix = Path(file.filename).suffix or ".mp4"
    save_path = UPLOAD_DIR / f"job_{job_id}{suffix}"
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk: break
            f.write(chunk)
    registry.register(job_id, str(save_path), file.filename)
    return {"job_id": job_id, "filename": file.filename}

@router.post("/api/start-from-upload/{filename}")
async def start_from_upload(filename: str):
    save_path = (UPLOAD_DIR / filename).resolve()
    if not save_path.is_relative_to(UPLOAD_DIR.resolve()) or not save_path.exists():
        m = re.match(r"job_([a-f0-9]{8})", filename)
        if m:
            clean_path = UPLOAD_DIR / f"job_{m.group(1)}.mp4"
            if clean_path.exists():
                save_path = clean_path
                filename = clean_path.name
    if not save_path.exists():
        return JSONResponse({"error": f"File not found: {filename}"}, status_code=404)
        
    job_id = str(uuid.uuid4())[:8]
    registry.register(job_id, str(save_path), filename)
    return {"job_id": job_id, "filename": filename}

@router.post("/config/{job_id}")
async def set_job_config(job_id: str, request: Request):
    registry.set_config(job_id, await request.json())
    return {"status": "ok"}

@router.post("/api/cancel/{job_id}")
async def cancel_job(job_id: str):
    job = registry.get(job_id)
    if job and job.process:
        try:
            if job.process.returncode is None:
                job.process.terminate()
                registry.add_event(job_id, {"type": "error", "message": "Job was cancelled by user."})
                return {"status": "cancelled"}
            else:
                return {"status": "already_finished"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return {"status": "not_running"}

@router.websocket("/ws/{job_id}")
async def run_pipeline_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = registry.get(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found."})
        await websocket.close()
        return

    config = registry.get_config(job_id)
    force_restart = config.get("force_restart", False)
    
    if force_restart or not registry.get_events(job_id):
        if force_restart:
            registry._events[job_id] = []
            job.done = False
        registry.add_event(job_id, {"type": "start", "filename": job.filename})

        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
        if not Path(python_exe).exists():
            python_exe = str(BASE_DIR / "venv" / "bin" / "python")
            if not Path(python_exe).exists():
                python_exe = sys.executable

        music = config.get("music", "none")
        if music == "off": music = "none"

        cmd = [
            python_exe, str(BASE_DIR / "local_clipping_pipeline.py"),
            "--input", job.path, "--output-dir", str(job_dir),
            "--model", config.get("model", "small"),
            "--max-clips", str(config.get("max_clips", 10)),
            "--music", music,
            "--caption-style", config.get("caption_style", "kinetic_slide"),
            "--font-preset", config.get("font_preset", "default"),
            "--font-name", config.get("font_name", ""),
            "--font-size", str(config.get("font_size", 48)),
            "--primary-color", config.get("primary_color", "#FFFFFF"),
            "--outline-color", config.get("outline_color", "#000000"),
        ]
        if config.get("no_title"): cmd += ["--no-title"]
        if config.get("broll") and config.get("pexels_key", "").strip():
            cmd += ["--broll", "--pexels-key", config.get("pexels_key").strip()]
        if config.get("language", "").strip():
            cmd += ["--language", config.get("language").strip()]
        

        asyncio.create_task(_run_process(job_id, cmd, job.start_time))

    try:
        last_index = 0
        while True:
            events = registry.get_events(job_id)
            if last_index < len(events):
                event = events[last_index]
                await websocket.send_json(event)
                last_index += 1
                if event.get("type") in ("done", "error"): break
            elif job.done:
                break
            else:
                await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"WebSocket error for {job_id}: {e}")
    finally:
        try: await websocket.close()
        except: pass

@router.get("/clips")
async def list_clips_endpoint():
    return {"clips": _list_clips()}

@router.get("/clips/{job_id}")
async def get_clips_for_job(job_id: str):
    return {"clips": _list_clips(job_id=job_id)}

@router.get("/history")
async def get_history():
    history = []
    if OUTPUT_DIR.exists():
        for d in OUTPUT_DIR.iterdir():
            if d.is_dir():
                has_meta = (d / "metadata.json").exists()
                has_clips_meta = (d / "clips_metadata.json").exists()
                if has_meta or has_clips_meta:
                    try:
                        if has_meta:
                            with open(d / "metadata.json", "r", encoding="utf-8") as f:
                                meta = json.load(f)
                        else:
                            meta = {"job_id": d.name, "filename": "CLI Job", "created": d.stat().st_mtime}
                        clips = list(d.glob("*.mp4"))
                        if clips:
                            meta["clip_count"] = len(clips)
                            history.append(meta)
                    except Exception as e: logger.error(f"Error reading metadata for {d.name}: {e}")
    return {"history": sorted(history, key=lambda x: x.get("created", 0), reverse=True)}

@router.get("/history/{job_id}/clips")
async def get_history_clips(job_id: str):
    return {"clips": _list_clips(job_id=job_id)}
