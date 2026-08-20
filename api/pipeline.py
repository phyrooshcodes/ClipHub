import asyncio
import os
import re
import sys
import time
import uuid
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, WebSocket, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse
from api.jobs import registry
from api.security import websocket_is_authorized

logger = logging.getLogger(__name__)
router = APIRouter()
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

def get_video_metadata(video_path: str) -> dict:
    meta = {
        "type": "video_metadata",
        "resolution": "—",
        "fps": "—",
        "format": "—",
        "audio": "—",
        "duration": "—",
        "path": str(video_path),
        "error": False
    }
    if not os.path.exists(video_path):
        meta["error"] = True
        return meta

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,r_frame_rate,codec_type,codec_name:format=format_name,duration",
            "-of", "json", str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15.0)
        data = json.loads(result.stdout)
        
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        format_info = data.get("format", {})
        
        if video_stream:
            w = video_stream.get("width")
            h = video_stream.get("height")
            if w and h:
                meta["resolution"] = f"{w}x{h}"
            r_fps = video_stream.get("r_frame_rate", "30/1")
            if "/" in r_fps:
                num, den = r_fps.split("/")
                fps_val = round(float(num) / float(den), 1) if float(den) != 0 else 30.0
            else:
                fps_val = round(float(r_fps), 1)
            meta["fps"] = str(fps_val)
        
        if audio_stream:
            meta["audio"] = audio_stream.get("codec_name", "Stereo").upper()
        else:
            meta["audio"] = "None"
            
        fmt_name = format_info.get("format_name", Path(video_path).suffix.lstrip(".").upper())
        meta["format"] = fmt_name.split(",")[0].upper()
        
        dur_s = float(format_info.get("duration", 0))
        meta["duration_s"] = dur_s
        if dur_s > 0:
            mins = int(dur_s // 60)
            secs = int(dur_s % 60)
            meta["duration"] = f"{mins:02d}:{secs:02d}"
    except subprocess.TimeoutExpired:
        logger.warning(f"FFprobe timed out probing metadata for {video_path}")
        meta["error"] = True
    except Exception as e:
        logger.warning(f"Failed to probe video metadata for {video_path}: {e}")
        meta["error"] = True
    return meta

def _parse_log_line(text: str) -> dict:
    # 1. Match STAGE X/6 or STAGE X.Y/6
    m = re.search(r"STAGE\s+([\d\.]+)/6[^─\-]*[\-─]\s*(.+?)(?:\s*[═=]+\s*$|\s*$)", text, re.IGNORECASE)
    if m:
        stg_str = m.group(1)
        stg = float(stg_str) if "." in stg_str else int(stg_str)
        return {"type": "stage", "stage": stg, "label": m.group(2).strip()}
    
    # 2. Match bracketed substages [4/6], [4.5/6], [5/6], [6/6]
    m = re.search(r"\[([\d\.]+)/6\]\s+(.+)", text)
    if m:
        stg_str = m.group(1)
        stg = float(stg_str) if "." in stg_str else int(stg_str)
        return {"type": "substage", "substage": stg, "label": m.group(2).strip()}
    
    # 3. Match clip progress
    m = re.search(r"CLIP\s+(\d+)/(\d+)", text, re.IGNORECASE)
    if m:
        return {"type": "clip_start", "clip_num": int(m.group(1)), "total": int(m.group(2))}
    
    # 4. Match Commentary / AI generation markers
    if "[CommentaryGenerator]" in text or "Generating commentary" in text or "AI Commentary" in text:
        m_clip = re.search(r"clip\s+(\d+)", text, re.IGNORECASE)
        clip_lbl = f"AI Commentary (Clip {m_clip.group(1)})" if m_clip else "AI Commentary Generation"
        return {"type": "stage", "stage": 3.5, "label": clip_lbl}
    
    if "[HookDetector]" in text or "Detecting viral hooks" in text:
        return {"type": "stage", "stage": 3, "label": "Hook Detection"}

    if "[FaceTracker]" in text or "Face detected" in text:
        return {"type": "substage", "substage": 4, "label": "Face Tracking & Framing"}

    if "Generating TTS" in text or "TTS generated" in text or "Building Editorial Timeline" in text:
        return {"type": "substage", "substage": 4.5, "label": "AI Speech Synthesis"}

    if "[SubtitleEngine]" in text or "subtitle groups" in text:
        return {"type": "substage", "substage": 5, "label": "Kinetic Subtitles"}

    if "[Renderer]" in text or "Explainer Clip" in text or "Assembling" in text:
        return {"type": "substage", "substage": 6, "label": "NVENC Video Rendering"}

    m = re.search(r"Done.*?(?:→|->)\s*(output[/\\].+?\.mp4)", text, re.IGNORECASE)
    if m:
        return {"type": "clip_ready", "path": m.group(1)}

    low = text.lower()
    if "error" in low or "traceback" in low:
        return {"type": "warning", "raw": text}
    if "warning" in low or "failed" in low or "timeout" in low or "timed out" in low:
        return {"type": "warning", "raw": text}

    return {"type": "log", "raw": text}

def clean_clip_title(raw_title: str) -> str:
    if not raw_title: return "Untitled Clip"
    title = str(raw_title).strip()
    if title.lower().endswith(".mp4"): title = title[:-4]
    title = re.sub(r'^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+', '', title, flags=re.I).strip()
    if "_" in title and " " not in title: title = title.replace("_", " ")
    return title.strip() or "Untitled Clip"

def _list_clips(job_id: str = None, newer_than: float = 0) -> list:
    clips = []
    if not OUTPUT_DIR.exists(): return clips
    if job_id:
        clean_jid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(job_id))
        target_dir = (OUTPUT_DIR / clean_jid).resolve()
        if not target_dir.is_relative_to(OUTPUT_DIR.resolve()) or not target_dir.is_dir():
            return []
        dirs = [target_dir]
    else:
        dirs = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
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
                    item_title = item.get("title", "")
                    clean_item = re.sub(r'[^\w\s]', '', item_title).strip().replace(" ", "_")
                    clean_file = re.sub(r'[^\w\s]', '', f.name).strip()
                    if clean_item and (clean_item.lower() in clean_file.lower() or clean_file.lower() in clean_item.lower()):
                        clip_meta = item
                        break
            
            # 4. Fallback to positional mapping
            if not clip_meta and idx < len(meta_list):
                clip_meta = meta_list[idx]
                
            title_text = clean_clip_title(clip_meta.get("title") or f.stem)
            hook_score = clip_meta.get("hook_score")
            social_caption = clip_meta.get("social_caption") or clip_meta.get("caption", "")
            editorial_data = clip_meta.get("editorial_data", {})
            ai_audio_events = clip_meta.get("ai_audio_events", [])

            thumb_f = d / f"{f.stem}_thumb.jpg"
            thumb_url = f"/output/{d.name}/{thumb_f.name}" if thumb_f.exists() else "/assets/covers/default_cover.jpg"

            clips.append({
                "job_id": d.name,
                "filename": f.name,
                "title": title_text,
                "hook_score": hook_score,
                "social_caption": social_caption,
                "editorial_data": editorial_data,
                "ai_audio_events": ai_audio_events,
                "url": f"/output/{d.name}/{f.name}",
                "thumbnail_url": thumb_url,
                "modified": stat.st_mtime,
                "size_mb": round(stat.st_size / (1024 * 1024), 2)
            })
    clips.sort(key=lambda x: x["modified"], reverse=True)
    return clips

async def _run_process(job_id: str, cmd: list, start_time: float):
    job = registry.get(job_id)
    try:
        env = os.environ.copy()
        env.update({
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
            "QT_QPA_PLATFORM": "offscreen"
        })
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
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
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
        is_phase_1 = "--phase" in cmd and "1" in cmd[cmd.index("--phase") + 1:]
        is_prompt_mode = "--phase" in cmd and any(p in cmd[cmd.index("--phase") + 1:] for p in ("asr_only", "prompt_mode"))
        
        if success:
            job_dir = OUTPUT_DIR / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            meta = {"job_id": job_id, "filename": job.filename if job else "unknown", "created": time.time()}
            with open(job_dir / "metadata.json", "w", encoding="utf-8") as f: json.dump(meta, f)
            
            if is_prompt_mode:
                temp_dir = BASE_DIR / "temp" / f"processing_{job_id}"
                words_files = list(temp_dir.glob("words_*.json"))
                if words_files:
                    with open(words_files[0], "r", encoding="utf-8") as f:
                        words = json.load(f)
                    from modules.audio_demux import get_video_duration
                    from modules.hook_detector import build_hook_prompt
                    duration = get_video_duration(job.path) if job else 0.0
                    prompt_text, char_count = build_hook_prompt(words, duration, 0)
                    
                    prompt_cache = job_dir / "prompt_mode_prompt.txt"
                    with open(prompt_cache, "w", encoding="utf-8") as f:
                        f.write(prompt_text)

                    words_cache = job_dir / "prompt_mode_words.json"
                    with open(words_cache, "w", encoding="utf-8") as f:
                        json.dump({"words": words, "duration": duration}, f)

                    registry.set_state(job_id, "prompt_ready")
                    registry.add_event(job_id, {
                        "type": "prompt_ready",
                        "prompt": prompt_text,
                        "char_count": char_count
                    })
                else:
                    registry.set_state(job_id, "failed")
                    registry.add_event(job_id, {"type": "error", "message": "Transcript words file not found."})
            elif is_phase_1:
                clips_meta_path = job_dir / "clips_metadata.json"
                if clips_meta_path.exists():
                    with open(clips_meta_path, "r", encoding="utf-8") as f:
                        clips_meta = json.load(f)
                    registry.set_state(job_id, "waiting_for_review")
                    registry.add_event(job_id, {"type": "phase_1_complete", "metadata": clips_meta})
                else:
                    registry.set_state(job_id, "completed")
            else:
                registry.set_state(job_id, "completed")
        else:
            registry.set_state(job_id, "failed")
            registry.add_event(job_id, {
                "type": "error",
                "message": f"Pipeline exited with code {process.returncode}. Check the log for details."
            })

        clips = _list_clips(job_id=job_id, newer_than=start_time - 5)
        registry.add_event(job_id, {"type": "done", "success": success, "clips": clips, "is_phase_1": is_phase_1 or is_prompt_mode})
    except Exception as e:
        registry.set_state(job_id, "failed")
        registry.add_event(job_id, {"type": "error", "message": str(e)})
    finally:
        if job and job.state != "waiting_for_review":
            registry.mark_done(job_id)

from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional, List, Dict, Any

class JobConfigModel(BaseModel):
    model: Literal["tiny", "base", "small"] = "small"
    max_clips: int = Field(default=0, ge=0, le=100)
    caption_style: str = "kinetic_slide"
    font_preset: Literal["default", "hormozi", "beast", "minimal"] = "default"
    font_name: str = ""
    font_size: int = Field(default=48, ge=12, le=140)
    primary_color: str = Field(default="#FFFFFF", pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
    outline_color: str = Field(default="#000000", pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
    no_title: bool = False
    commentary_mode: Literal["off", "hook_only", "hook_commentary", "full_editorial"] = "hook_commentary"
    commentary_voice: str = "af_sarah"
    character: str = "anime_presenter.png"
    cover: str = "default_cover.jpg"
    language: str = ""
    auto_publish: bool = False
    music: str = "auto"
    music_volume: float = 0.14
    phase: Literal["1", "2", "all"] = "all"
    force_restart: bool = False

class ClipReviewItem(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    title: Optional[str] = "Untitled Clip"
    hook_score: Optional[Any] = None
    social_caption: Optional[str] = None
    editorial_data: Optional[Dict[str, Any]] = None
    filename: Optional[str] = None
    ai_audio_events: Optional[List[Dict[str, Any]]] = None

    @model_validator(mode="after")
    def validate_range_and_paths(self):
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be strictly greater than start_ms ({self.start_ms})")
        if self.ai_audio_events:
            temp_dir = (BASE_DIR / "temp").resolve()
            out_dir = (BASE_DIR / "output").resolve()
            for ev in self.ai_audio_events:
                audio_path = ev.get("audio_path")
                if audio_path:
                    p = Path(audio_path).resolve()
                    if not (p.is_relative_to(temp_dir) or p.is_relative_to(out_dir)):
                        raise ValueError(f"Invalid audio event path: {audio_path}")
        return self

MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB safety quota

@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    character: Optional[str] = Form(None),
    cover: Optional[str] = Form(None),
    caption_style: Optional[str] = Form(None)
):
    job_id = uuid.uuid4().hex[:16]
    suffix = Path(file.filename).suffix or ".mp4"
    if suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
        return JSONResponse({"error": "Unsupported video format. MP4, MOV, MKV, WebM allowed."}, status_code=400)

    save_path = UPLOAD_DIR / f"job_{job_id}{suffix}"
    bytes_written = 0
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk: break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_SIZE:
                f.close()
                if save_path.exists():
                    save_path.unlink(missing_ok=True)
                return JSONResponse({"error": "Upload exceeds 2 GB limit."}, status_code=413)
            f.write(chunk)
            
    registry.register(job_id, str(save_path), file.filename)
    init_cfg = {}
    if character: init_cfg["character"] = character
    if cover: init_cfg["cover"] = cover
    if caption_style: init_cfg["caption_style"] = caption_style
    if init_cfg:
        registry.set_config(job_id, init_cfg)
    return {"job_id": job_id, "filename": file.filename}

@router.get("/api/uploads")
@router.get("/uploads")
async def list_recent_uploads():
    """Lists all recent uploaded or downloaded source videos from UPLOAD_DIR."""
    uploads = []
    if UPLOAD_DIR.exists():
        video_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        files = [f for f in UPLOAD_DIR.iterdir() if f.is_file() and f.suffix.lower() in video_extensions]
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for f in files[:50]:
            stat = f.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            mtime = stat.st_mtime
            orig_name = f.name
            m = re.match(r"job_([a-f0-9]{8,32})", f.name)
            if m:
                jid = m.group(1)
                orig_job = registry.get(jid)
                if orig_job and orig_job.filename:
                    orig_name = orig_job.filename
            uploads.append({
                "filename": f.name,
                "original_name": orig_name,
                "size_mb": size_mb,
                "timestamp": mtime,
                "formatted_date": time.strftime("%b %d, %Y · %H:%M", time.localtime(mtime))
            })
    return {"success": True, "uploads": uploads}

@router.delete("/api/uploads/{filename}")
async def delete_upload(filename: str):
    if Path(filename).name != filename:
        return JSONResponse({"error": "Invalid filename."}, status_code=400)
    target = (UPLOAD_DIR / filename).resolve()
    if target.exists() and target.is_relative_to(UPLOAD_DIR.resolve()) and target.is_file():
        target.unlink(missing_ok=True)
        return {"success": True, "message": f"Deleted {filename}"}
    return JSONResponse({"error": "File not found"}, status_code=404)

@router.post("/api/start-from-upload/{filename}")
async def start_from_upload(
    filename: str,
    character: Optional[str] = Query(None),
    cover: Optional[str] = Query(None),
    caption_style: Optional[str] = Query(None)
):
    if Path(filename).name != filename:
        return JSONResponse({"error": "Invalid upload filename."}, status_code=400)
    save_path = (UPLOAD_DIR / filename).resolve()
    orig_name = filename
    if not save_path.is_relative_to(UPLOAD_DIR.resolve()) or not save_path.exists():
        m = re.match(r"job_([a-f0-9]{8,32})", filename)
        if m:
            jid = m.group(1)
            for ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
                candidate = UPLOAD_DIR / f"job_{jid}{ext}"
                if candidate.exists():
                    save_path = candidate
                    orig_job = registry.get(jid)
                    if orig_job:
                        orig_name = orig_job.filename
                    else:
                        orig_name = candidate.name
                    break
    if not save_path.is_relative_to(UPLOAD_DIR.resolve()) or not save_path.is_file():
        return JSONResponse({"error": f"File not found: {filename}"}, status_code=404)
        
    job_id = uuid.uuid4().hex[:16]
    registry.register(job_id, str(save_path), orig_name)
    init_cfg = {}
    if character: init_cfg["character"] = character
    if cover: init_cfg["cover"] = cover
    if caption_style: init_cfg["caption_style"] = caption_style
    if init_cfg:
        registry.set_config(job_id, init_cfg)
    return {"job_id": job_id, "filename": orig_name}

@router.post("/config/{job_id}")
async def set_job_config(job_id: str, config: JobConfigModel):
    job = registry.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    existing = registry.get_config(job_id)
    merged = {**existing, **config.model_dump()}
    registry.set_config(job_id, merged)
    logger.info(f"[Config] Configured job {job_id}: character='{merged.get('character')}', cover='{merged.get('cover')}', caption_style='{merged.get('caption_style')}'")
    return {"status": "ok", "job_id": job_id}

@router.post("/api/cancel/{job_id}")
async def cancel_job(job_id: str):
    job = registry.get(job_id)
    if job and job.process:
        try:
            if job.process.returncode is None:
                pid = job.process.pid
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                else:
                    job.process.terminate()
                registry.set_state(job_id, "cancelled")
                registry.add_event(job_id, {"type": "error", "message": "Job was cancelled by user."})
                return {"status": "cancelled"}
            else:
                return {"status": "already_finished"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return {"status": "not_running"}

@router.post("/api/submit-review/{job_id}")
async def submit_review(job_id: str, request: Request):
    try:
        raw_body = await request.json()
        if isinstance(raw_body, list):
            validated_clips = [ClipReviewItem(**c).model_dump() for c in raw_body]
        elif isinstance(raw_body, dict) and "clips" in raw_body:
            validated_clips = [ClipReviewItem(**c).model_dump() for c in raw_body["clips"]]
        else:
            return JSONResponse({"error": "Invalid review payload. Array of clips expected."}, status_code=400)

        job = registry.get(job_id)
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        if getattr(job, "state", "") == "phase_1_running":
            return JSONResponse({"error": "Job is still processing Phase 1 analysis. Review cannot be submitted until Phase 1 is complete."}, status_code=409)

        # Bounds check against probed video duration if available
        meta = get_video_metadata(job.path)
        dur_s = meta.get("duration_s", 0.0)
        if dur_s and dur_s > 0:
            max_ms = int(dur_s * 1000)
            for c in validated_clips:
                if c["start_ms"] >= max_ms:
                    return JSONResponse({"error": f"Clip start timestamp ({c['start_ms']}ms) exceeds video duration ({max_ms}ms)"}, status_code=400)
                c["end_ms"] = min(c["end_ms"], max_ms)
            
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return JSONResponse({"error": "Job output dir not found"}, status_code=404)
            
        # Overwrite the clips_metadata.json with the validated user version
        clips_meta_path = job_dir / "clips_metadata.json"
        with open(clips_meta_path, "w", encoding="utf-8") as f:
            json.dump(validated_clips, f, indent=2, ensure_ascii=False)
            
        # Synchronized atomic restart for phase 2 execution
        restarted = registry.restart_job(job_id, phase="2")
        if not restarted:
            return JSONResponse({"error": "Failed to schedule Phase 2 execution."}, status_code=500)
        
        return {"status": "ok", "job_id": job_id}
    except Exception as e:
        logger.error(f"Error in submit-review: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)

@router.websocket("/ws/{job_id}")
async def run_pipeline_ws(websocket: WebSocket, job_id: str):
    if not websocket_is_authorized(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    job = registry.get(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found."})
        await websocket.close()
        return

    config = registry.get_config(job_id)
    qp = dict(websocket.query_params)
    for key in ("character", "cover", "caption_style", "model", "commentary_mode", "commentary_voice", "music", "music_volume"):
        val = qp.get(key)
        if val:
            if not config.get(key) or (config.get(key) in ("anime_presenter.png", "default_cover.jpg") and val not in ("anime_presenter.png", "default_cover.jpg")):
                config[key] = val
    registry.set_config(job_id, config)

    logger.info(f"[Pipeline WS] Job {job_id} connected | Presenter='{config.get('character')}', Cover='{config.get('cover')}', Style='{config.get('caption_style')}'")

    should_launch = registry.claim_execution(job_id)

    if should_launch:
        meta_event = await asyncio.to_thread(get_video_metadata, job.path)
        registry.add_event(job_id, meta_event)
        registry.add_event(job_id, {"type": "start", "filename": job.filename})

        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
        if not Path(python_exe).exists():
            python_exe = str(BASE_DIR / "venv" / "bin" / "python")
            if not Path(python_exe).exists():
                python_exe = sys.executable

        cmd = [
            python_exe, str(BASE_DIR / "local_clipping_pipeline.py"),
            "--input", job.path, "--output-dir", str(job_dir),
            "--model", config.get("model", "small"),
            "--max-clips", str(config.get("max_clips", 0)),
            "--caption-style", config.get("caption_style", "aftereffect_preset"),
            "--font-preset", config.get("font_preset", "default"),
            "--font-name", config.get("font_name", ""),
            "--font-size", str(config.get("font_size", 48)),
            "--primary-color", config.get("primary_color", "#FFFFFF"),
            "--outline-color", config.get("outline_color", "#000000"),
        ]
        if config.get("no_title"): cmd += ["--no-title"]
        commentary_mode = config.get("commentary_mode", "hook_commentary")
        cmd += ["--commentary-mode", commentary_mode]
        if config.get("commentary_voice"):
            cmd += ["--commentary-voice", config.get("commentary_voice")]
        if config.get("character"):
            cmd += ["--character", str(config.get("character"))]
        if config.get("cover") is not None:
            cmd += ["--cover", str(config.get("cover"))]
        lang = (config.get("language") or "").strip()
        if lang:
            cmd += ["--language", lang]
        if config.get("auto_publish"): 
            cmd += ["--auto-publish"]
        if config.get("music"):
            cmd += ["--music", str(config.get("music"))]
        if config.get("music_volume") is not None:
            cmd += ["--music-volume", str(config.get("music_volume"))]
            
        phase = config.get("phase", "all")
        cmd += ["--phase", phase]
        
        # reset phase back to all for future runs
        if "phase" in config:
            config["phase"] = "all"
            registry.set_config(job_id, config)

        asyncio.create_task(_run_process(job_id, cmd, getattr(job, "execution_start_time", job.start_time)))

    try:
        last_index = 0
        while True:
            events = registry.get_events(job_id)
            while last_index < len(events):
                event = events[last_index]
                last_index += 1
                await websocket.send_json(event)
                if event.get("type") in ("done", "error"):
                    return
            if job.done:
                while last_index < len(events):
                    event = events[last_index]
                    last_index += 1
                    await websocket.send_json(event)
                break
            await asyncio.sleep(0.05)
    except Exception as e:
        logger.error(f"WebSocket error for {job_id}: {e}")
    finally:
        try: await websocket.close()
        except: pass

@router.get("/api/script/{job_id}")
async def get_job_script(job_id: str):
    clean_jid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(job_id))
    out_file = (OUTPUT_DIR / clean_jid / "clips_metadata.json").resolve()
    temp_file = (BASE_DIR / "temp" / f"processing_{clean_jid}" / "clips_metadata.json").resolve()
    data = []
    if out_file.is_relative_to(OUTPUT_DIR.resolve()) and out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception: pass
    elif temp_file.is_relative_to((BASE_DIR / "temp").resolve()) and temp_file.exists():
        try:
            with open(temp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception: pass
    else:
        p_dir = (BASE_DIR / "temp" / f"processing_{clean_jid}").resolve()
        if p_dir.exists():
            for hf in p_dir.glob("hooks_*.json"):
                try:
                    with open(hf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data: break
                except Exception: pass
    return {"job_id": clean_jid, "script": data}

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
                meta_file = d / "metadata.json"
                clips_meta_file = d / "clips_metadata.json"
                clips = _list_clips(job_id=d.name)
                if clips:
                    meta = {"job_id": d.name, "created": d.stat().st_mtime}
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                if isinstance(data, dict):
                                    meta.update(data)
                        except Exception: pass
                    elif clips_meta_file.exists():
                        try:
                            with open(clips_meta_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                if isinstance(data, dict):
                                    meta.update(data)
                        except Exception: pass
                    meta["filename"] = meta.get("filename") or d.name
                    meta["clip_count"] = len(clips)
                    meta["clips"] = clips
                    history.append(meta)
    return {"history": sorted(history, key=lambda x: x.get("created", 0), reverse=True)}

@router.get("/history/{job_id}/clips")
async def get_history_clips(job_id: str):
    return {"clips": _list_clips(job_id=job_id)}


# ─── Prompt Mode Endpoints ────────────────────────────────────

@router.post("/api/pipeline/{job_id}/prompt-mode")
async def start_prompt_mode(job_id: str, websocket: WebSocket = None):
    """
    Prompt Mode: runs Demux + Whisper ASR (phase=1 minus hook detection) and
    returns the copyable LLM prompt once transcription is done.
    This endpoint is called via HTTP POST. The frontend then polls
    GET /api/pipeline/{job_id}/prompt to retrieve the generated prompt.
    """
    clean_jid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(job_id))
    job = registry.get(clean_jid)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    config = registry.get_config(clean_jid)
    # Mark as prompt-mode so the WS handler does NOT start full pipeline
    config["phase"] = "prompt_mode"
    registry.set_config(clean_jid, config)

    python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
    if not Path(python_exe).exists():
        python_exe = str(BASE_DIR / "venv" / "bin" / "python")
        if not Path(python_exe).exists():
            python_exe = sys.executable

    job_dir = OUTPUT_DIR / clean_jid
    job_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        python_exe, str(BASE_DIR / "local_clipping_pipeline.py"),
        "--input", job.path,
        "--output-dir", str(job_dir),
        "--model", config.get("model", "small"),
        "--max-clips", str(config.get("max_clips", 0)),
        "--phase", "asr_only",   # Run Demux + Whisper ASR only, exit before hook detection
    ]
    lang = (config.get("language") or "").strip()
    if lang:
        cmd += ["--language", lang]

    async def _run_asr_only():
        try:
            registry.set_state(clean_jid, "phase_1_running")
            registry.add_event(clean_jid, {"type": "start", "filename": job.filename})

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            job_ref = registry.get(clean_jid)
            if job_ref:
                job_ref.process = proc

            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                parsed = _parse_log_line(line)
                parsed["raw"] = line
                registry.add_event(clean_jid, parsed)

            await proc.wait()

            # After ASR completes, build the prompt
            temp_dir = BASE_DIR / "temp" / f"processing_{clean_jid}"
            import hashlib, json as _json
            from modules.audio_demux import get_video_duration
            from modules.transcriber import words_to_timed_transcript

            words_files = list(temp_dir.glob("words_*.json"))
            if not words_files:
                registry.add_event(clean_jid, {"type": "error", "message": "ASR transcript not found. Transcription may have failed."})
                return

            words_path = words_files[0]
            with open(words_path, "r", encoding="utf-8") as f:
                words = _json.load(f)

            duration = get_video_duration(job.path)
            max_clips = config.get("max_clips", 0)

            from modules.hook_detector import build_hook_prompt
            prompt_text, char_count = build_hook_prompt(words, duration, max_clips)

            # Cache prompt and words path for submit-response
            prompt_cache = job_dir / "prompt_mode_prompt.txt"
            with open(prompt_cache, "w", encoding="utf-8") as f:
                f.write(prompt_text)

            words_cache = job_dir / "prompt_mode_words.json"
            with open(words_cache, "w", encoding="utf-8") as f:
                _json.dump({"words": words, "duration": duration}, f)

            registry.set_state(clean_jid, "prompt_ready")
            registry.add_event(clean_jid, {
                "type": "prompt_ready",
                "prompt": prompt_text,
                "char_count": char_count
            })

        except Exception as e:
            logger.error(f"[PromptMode] ASR error for {clean_jid}: {e}")
            registry.add_event(clean_jid, {"type": "error", "message": str(e)})

    asyncio.create_task(_run_asr_only())
    return {"status": "started", "job_id": clean_jid}


@router.get("/api/pipeline/{job_id}/prompt")
async def get_prompt_for_job(job_id: str):
    """Return the cached prompt text generated during Prompt Mode ASR."""
    clean_jid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(job_id))
    job_dir = OUTPUT_DIR / clean_jid
    prompt_file = job_dir / "prompt_mode_prompt.txt"
    if not prompt_file.exists():
        events = registry.get_events(clean_jid)
        pr = next((e for e in reversed(events) if e.get("type") == "prompt_ready"), None)
        if pr:
            return {"status": "ready", "prompt": pr["prompt"], "char_count": pr.get("char_count", 0)}
        state = getattr(registry.get(clean_jid), "state", "")
        return JSONResponse({"status": state or "not_found"}, status_code=202)
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt_text = f.read()
    return {"status": "ready", "prompt": prompt_text, "char_count": len(prompt_text)}


@router.post("/api/pipeline/{job_id}/submit-response")
async def submit_external_response(job_id: str, request: Request):
    """
    Accepts the raw text pasted from an external LLM (Claude / ChatGPT / DeepSeek),
    parses clips, saves clips_metadata.json, and kicks off Phase 2 rendering.
    """
    clean_jid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(job_id))
    job = registry.get(clean_jid)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    try:
        body = await request.json()
        response_text = body.get("response_text", "").strip()
        character = body.get("character")
        cover = body.get("cover")
        caption_style = body.get("caption_style")
        if not response_text:
            return JSONResponse({"error": "response_text is required"}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    job_dir = OUTPUT_DIR / clean_jid
    words_cache = job_dir / "prompt_mode_words.json"
    if not words_cache.exists():
        # Fallback: find words cache in temp dir
        temp_dir = BASE_DIR / "temp" / f"processing_{clean_jid}"
        found = list(temp_dir.glob("words_*.json"))
        if not found:
            return JSONResponse({"error": "Transcript data not found. Please run Prompt Mode first."}, status_code=404)
        import json as _json
        from modules.audio_demux import get_video_duration
        with open(found[0], "r", encoding="utf-8") as f:
            words_data = _json.load(f)
        words = words_data if isinstance(words_data, list) else words_data.get("words", [])
        duration = get_video_duration(job.path)
    else:
        import json as _json
        with open(words_cache, "r", encoding="utf-8") as f:
            cache = _json.load(f)
        words = cache.get("words", [])
        duration = cache.get("duration", 0.0)

    try:
        from modules.hook_detector import parse_external_llm_response
        clips = parse_external_llm_response(response_text, words, duration)
    except Exception as e:
        return JSONResponse({"error": f"Could not parse clips from response: {e}"}, status_code=422)

    clips_meta_path = job_dir / "clips_metadata.json"
    job_dir.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(clips_meta_path, "w", encoding="utf-8") as f:
        _json.dump(clips, f, indent=2, ensure_ascii=False)

    # Set phase=2 in config so the WS pipeline only runs rendering
    config = registry.get_config(clean_jid)
    if character:
        config["character"] = character
    if cover:
        config["cover"] = cover
    if caption_style:
        config["caption_style"] = caption_style
    config["phase"] = "2"
    registry.set_config(clean_jid, config)

    restarted = registry.restart_job(clean_jid, phase="2")
    if not restarted:
        return JSONResponse({"error": "Failed to schedule Phase 2 rendering."}, status_code=500)

    return {"status": "ok", "job_id": clean_jid, "clip_count": len(clips)}

