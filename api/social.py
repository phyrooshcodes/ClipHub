import os
import sys
import time
import uuid
import json
import asyncio
import functools
from typing import List
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"

MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB safety quota

async def _save_bounded_upload_to_temp(file: UploadFile, suffix: str = ".mp4") -> str:
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        bytes_written = 0
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_SIZE:
                tmp.close()
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise ValueError("Uploaded file exceeds 2 GB limit.")
            tmp.write(chunk)
    return tmp_path

class InstagramConnectRequest(BaseModel):
    username: str
    password: str

class InstagramConnectSessionRequest(BaseModel):
    username: str
    session_id: str

from typing import Literal

class SocialPostRequest(BaseModel):
    job_id: str
    clip_filename: str
    title: str
    caption: str
    platforms: List[Literal["instagram", "youtube"]]
    allow_duplicate: bool = False
    product_recommendations: List[dict] = []
    amazon_store_tag: str = ""
    enable_comment_affiliate: bool = True
    enable_native_shopping: bool = False

class InstagramQueueActionRequest(BaseModel):
    action: str

social_uploads = {}
upload_lock = asyncio.Lock()

def _clean_stale_social_uploads(max_age_sec: int = 86400):
    now = time.time()
    stale = [k for k, v in social_uploads.items() if (now - v.get("created_at", now)) > max_age_sec]
    for k in stale:
        social_uploads.pop(k, None)

async def _bg_social_post(upload_id: str, job_id: str, clip_filename: str, title: str, caption: str, platforms: List[str], product_recommendations: List[dict] = None, amazon_store_tag: str = "", enable_comment_affiliate: bool = True, enable_native_shopping: bool = False):
    _clean_stale_social_uploads()
    if product_recommendations is None:
        product_recommendations = []
    social_uploads[upload_id] = {
        "status": "uploading",
        "results": {},
        "platform_progress": {p: 0 for p in platforms},
        "created_at": time.time()
    }
    video_path = (OUTPUT_DIR / job_id / clip_filename).resolve()
    if not video_path.is_relative_to(OUTPUT_DIR.resolve()) or not video_path.exists():
        social_uploads[upload_id] = {"status": "failed", "error": "Video file not found or invalid."}
        return
        
    try:
        from modules.publisher_ig import post_instagram_reel
        from modules.publisher_yt import post_youtube_short
    except Exception as e:
        social_uploads[upload_id] = {"status": "failed", "error": f"Failed to load publisher modules: {e}"}
        return
        
    results = {}
    has_errors = False
    
    def update_progress(platform: str, pct: int, msg: str):
        if upload_id in social_uploads:
            social_uploads[upload_id]["platform_progress"][platform] = pct
            avg_pct = int(sum(social_uploads[upload_id]["platform_progress"].values()) / max(1, len(platforms)))
            social_uploads[upload_id]["message"] = f"[{platform.upper()}] {msg}"
            social_uploads[upload_id]["progress"] = avg_pct
    
    async with upload_lock:
        if "instagram" in platforms:
            try:
                loop = asyncio.get_event_loop()
                ig_func = functools.partial(post_instagram_reel, str(video_path), caption, progress=lambda p, m: update_progress("instagram", p, m))
                url = await loop.run_in_executor(None, ig_func)
                results["instagram"] = {"success": True, "url": url}
            except Exception as e:
                results["instagram"] = {"success": False, "error": str(e)}
                has_errors = True
                
    if "youtube" in platforms:
        try:
            from modules.youtube_worker import get_youtube_worker
            worker = get_youtube_worker()
            worker.enqueue(upload_id, str(video_path), title, caption, [], None, product_recommendations, amazon_store_tag, enable_comment_affiliate, enable_native_shopping, lambda p, m: update_progress("youtube", p, m))
            
            # Poll for completion with bounded 10-minute timeout
            start_poll = time.time()
            res = {}
            while time.time() - start_poll < 600:
                res = worker.results.get(upload_id, {})
                st = res.get("status")
                if st in ["scheduled", "completed", "failed"]:
                    break
                await asyncio.sleep(1)
            else:
                res = {"status": "failed", "error": "YouTube upload polling timed out after 10 minutes."}
            
            if res.get("success"):
                results["youtube"] = {"success": True, "url": res.get("url")}
            else:
                results["youtube"] = {"success": False, "error": res.get("error", "Unknown error")}
                has_errors = True
        except Exception as e:
            results["youtube"] = {"success": False, "error": str(e)}
            has_errors = True
            
    status = "failed" if has_errors and len(results) == len(platforms) else "completed"
    if has_errors and status == "completed": status = "partial"
    social_uploads[upload_id]["status"] = status
    social_uploads[upload_id]["results"] = results

@router.get("/api/check-nvidia-key")
async def check_nvidia_key():
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=True)
    key = os.environ.get("NVIDIA_API_KEY", "")
    is_set = len(key) > 0 and key.startswith("nvapi-")
    return {"is_set": is_set}

@router.post("/api/save-nvidia-key")
async def save_nvidia_key(payload: dict):
    key = payload.get("key", "").strip()
    key = key.replace("\n", "").replace("\r", "")
    env_path = BASE_DIR / ".env"
    lines = []
    key_found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("NVIDIA_API_KEY="):
                    lines.append(f"NVIDIA_API_KEY={key}\n")
                    key_found = True
                else:
                    lines.append(line)
    if not key_found: lines.append(f"NVIDIA_API_KEY={key}\n")
    with open(env_path, "w", encoding="utf-8") as f: f.writelines(lines)
    os.environ["NVIDIA_API_KEY"] = key
    return {"success": True, "message": "NVIDIA API Key saved permanently to backend."}

@router.get("/api/music/tracks")
async def get_music_tracks():
    return []

def _parse_subprocess_json(stdout_str: str) -> dict:
    cleaned = stdout_str.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Search lines backwards for valid JSON in case warnings/logs were output
        lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except Exception:
                continue
        raise ValueError(f"No valid JSON found in process output: {cleaned[:200]}")

@router.post("/api/tools/generate-caption")
async def api_tools_generate_caption(file: UploadFile = File(...)):
    import subprocess
    try:
        tmp_path = await _save_bounded_upload_to_temp(file)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=413)

    try:
        python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
        if not Path(python_exe).exists():
            python_exe = str(BASE_DIR / "venv" / "bin" / "python")
            if not Path(python_exe).exists():
                python_exe = sys.executable
        cmd = [python_exe, str(BASE_DIR / "tools_generate_caption.py"), tmp_path]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, check=True)
        return _parse_subprocess_json(result.stdout)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

@router.post("/api/tools/generate-products")
async def api_tools_generate_products(file: UploadFile = File(...)):
    import subprocess
    try:
        tmp_path = await _save_bounded_upload_to_temp(file)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=413)

    try:
        python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
        if not Path(python_exe).exists():
            python_exe = str(BASE_DIR / "venv" / "bin" / "python")
            if not Path(python_exe).exists():
                python_exe = sys.executable
        cmd = [python_exe, str(BASE_DIR / "tools_generate_products.py"), tmp_path]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, check=True)
        return _parse_subprocess_json(result.stdout)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

@router.post("/api/tools/add-captions")
async def api_tools_add_captions(file: UploadFile = File(...), style: str = Form("kinetic_slide")):
    import subprocess
    try:
        tmp_path = await _save_bounded_upload_to_temp(file)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=413)
        
    out_dir = OUTPUT_DIR / "caption_studio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_filename = f"captions_{uuid.uuid4().hex[:8]}.mp4"
    out_path = out_dir / out_filename
    
    try:
        python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
        if not Path(python_exe).exists():
            python_exe = str(BASE_DIR / "venv" / "bin" / "python")
            if not Path(python_exe).exists():
                python_exe = sys.executable
        cmd = [python_exe, str(BASE_DIR / "tools_add_captions.py"), tmp_path, style, str(out_path)]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, check=True)
        data = _parse_subprocess_json(result.stdout)
        if "error" in data and not data.get("success"):
            return JSONResponse(data, status_code=400)
        return {"success": True, "video_url": f"/output/caption_studio/{out_filename}", "words_count": data.get("words_count", 0)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

@router.get("/api/social/status")
async def social_status():
    from modules.publisher_ig import is_instagram_connected
    from modules.publisher_yt import is_youtube_connected, has_client_secrets, get_youtube_channel_info
    ig_user = None
    if is_instagram_connected():
        try:
            config_path = BASE_DIR / "credentials" / "instagram_config.json"
            if config_path.exists():
                with open(config_path, "r") as f: ig_user = json.load(f).get("username")
        except: pass
    yt_channel = None
    if is_youtube_connected():
        try: yt_channel = get_youtube_channel_info()
        except: pass
    return {
        "instagram_connected": is_instagram_connected(),
        "instagram_username": ig_user or ("Saved browser session" if is_instagram_connected() else None),
        "youtube_connected": is_youtube_connected(),
        "youtube_channel": yt_channel,
        "youtube_client_secrets_present": has_client_secrets()
    }

@router.post("/api/social/instagram/connect-playwright")
async def connect_ig_playwright():
    from modules.publisher_ig import connect_instagram_playwright
    try:
        await asyncio.to_thread(connect_instagram_playwright)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@router.post("/api/social/instagram/connect-session")
async def connect_ig_session(req: InstagramConnectSessionRequest):
    from modules.publisher_ig import connect_instagram_with_session
    try:
        connect_instagram_with_session(req.username, req.session_id)
        return {"success": True}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=400)

@router.post("/api/social/instagram/disconnect")
async def disconnect_ig():
    from modules.publisher_ig import disconnect_instagram
    disconnect_instagram()
    return {"success": True}

@router.post("/api/social/youtube/connect-playwright")
async def connect_yt_playwright():
    from modules.publisher_yt import connect_youtube_playwright
    from modules.youtube_worker import get_youtube_worker
    worker = get_youtube_worker()
    was_running = worker.running
    if was_running:
        suspended = await asyncio.to_thread(worker.suspend, 10.0)
        if not suspended:
            return JSONResponse({"error": "YouTube browser worker could not be suspended in time. Please retry."}, status_code=503)
        await asyncio.sleep(0.5)
    try:
        await asyncio.to_thread(connect_youtube_playwright)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        if was_running:
            worker.resume()

@router.get("/api/social/youtube/auth-url")
async def youtube_auth_url():
    from modules.publisher_yt import get_youtube_flow, has_client_secrets
    if not has_client_secrets(): return JSONResponse({"error": "client_secrets.json missing"}, status_code=400)
    try:
        flow = get_youtube_flow(redirect_uri="http://localhost:7842/api/social/youtube/callback")
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        return {"auth_url": auth_url}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/api/social/youtube/callback")
async def youtube_callback(code: str):
    from modules.publisher_yt import connect_youtube_with_code
    try:
        connect_youtube_with_code(code, redirect_uri="http://localhost:7842/api/social/youtube/callback")
        return HTMLResponse("<html><head><title>YouTube Connected</title></head><body><h2>✅ YouTube Connected!</h2><script>setTimeout(()=>window.close(), 2000);</script></body></html>")
    except Exception as e: return HTMLResponse(f"<html><body><h2>❌ Connection Failed</h2><p>{e}</p></body></html>")

@router.post("/api/social/youtube/disconnect")
async def disconnect_yt():
    from modules.publisher_yt import disconnect_youtube
    disconnect_youtube()
    return {"success": True}

@router.get("/api/publisher/health")
async def publisher_health():
    from modules.publishers.youtube.publisher import get_youtube_channel_info, get_channel_profile_dir, PROFILE_DIR, _state_dir, is_youtube_connected
    import time as _time
    channel_info = get_youtube_channel_info() if is_youtube_connected() else {}
    profile_dir = get_channel_profile_dir()
    profiles_root = PROFILE_DIR
    return {
        "status": "ready" if is_youtube_connected() else "unconfigured",
        "youtube_connected": is_youtube_connected(),
        "channel_id": channel_info.get("channel_id"),
        "channel_title": channel_info.get("name")
    }

@router.get("/api/channels")
async def list_channels():
    from modules.publishers.youtube.publisher import get_youtube_channel_info, _state_dir
    channel_info = get_youtube_channel_info()
    profiles_root = _state_dir() / "channel-profiles"
    channels = []
    if channel_info.get("channel_id"): channels.append({"channel_id": channel_info["channel_id"], "name": channel_info.get("name", ""), "handle": channel_info.get("handle", ""), "is_active": True, "profile_isolated": (profiles_root / channel_info["channel_id"]).exists()})
    if profiles_root.exists():
        for child in sorted(profiles_root.iterdir()):
            if child.is_dir() and child.name != channel_info.get("channel_id"): channels.append({"channel_id": child.name, "name": "", "handle": "", "is_active": False, "profile_isolated": True})
    return {"channels": channels}

@router.post("/api/social/post")
async def start_social_post(req: SocialPostRequest, background_tasks: BackgroundTasks):
    requested = [platform.lower() for platform in req.platforms]
    if not requested or not set(requested).issubset({"instagram", "youtube"}): return JSONResponse({"error": "Platforms must contain instagram and/or youtube."}, status_code=400)
    if requested == ["instagram"]:
        try:
            job_dir = (OUTPUT_DIR / req.job_id).resolve()
            video_path = (job_dir / req.clip_filename).resolve()
            if not video_path.is_relative_to(OUTPUT_DIR.resolve()) or not video_path.is_file(): return JSONResponse({"error": "Video file not found or invalid."}, status_code=404)
            from modules.instagram_queue import get_instagram_queue
            upload = get_instagram_queue().enqueue(str(video_path), req.caption, allow_duplicate=req.allow_duplicate)
            return {"upload_id": upload["id"], "status": upload["status"], "upload": upload}
        except Exception as exc: return JSONResponse({"error": str(exc)}, status_code=500)
    upload_id = str(uuid.uuid4())
    background_tasks.add_task(_bg_social_post, upload_id, req.job_id, req.clip_filename, req.title, req.caption, requested, req.product_recommendations, req.amazon_store_tag, req.enable_comment_affiliate, req.enable_native_shopping)
    return {"upload_id": upload_id, "status": "pending"}

@router.get("/api/social/post-status/{upload_id}")
async def get_social_post_status(upload_id: str):
    from modules.instagram_queue import get_instagram_queue
    queued_upload = get_instagram_queue().get(upload_id)
    if queued_upload: return queued_upload
    if upload_id not in social_uploads: return JSONResponse({"error": "Upload ID not found"}, status_code=404)
    return social_uploads[upload_id]

def _instagram_upload_payload(item: dict) -> dict:
    payload = dict(item)
    path = Path(item["video_path"])
    try: payload["file_size"] = path.stat().st_size
    except: payload["file_size"] = None
    try:
        parts = path.resolve().relative_to(OUTPUT_DIR.resolve()).parts
        if len(parts) >= 2: payload["video_url"] = f"/output/{parts[0]}/{parts[-1]}"
    except: payload["video_url"] = None
    return payload

@router.get("/api/social/instagram/history")
async def instagram_upload_history():
    from modules.instagram_queue import get_instagram_queue
    return {"uploads": [_instagram_upload_payload(item) for item in get_instagram_queue().history()]}

@router.get("/api/social/instagram/center")
async def instagram_upload_center():
    from modules.instagram_queue import get_instagram_queue
    queue = get_instagram_queue()
    return {"summary": queue.summary(), "uploads": [_instagram_upload_payload(item) for item in queue.history(200)]}

@router.get("/api/social/instagram/uploads/{upload_id}/events")
async def instagram_upload_events(upload_id: str):
    from modules.instagram_queue import get_instagram_queue
    queue = get_instagram_queue()
    if not queue.get(upload_id): return JSONResponse({"error": "Upload not found"}, status_code=404)
    return {"events": queue.events(upload_id)}

@router.post("/api/social/instagram/queue/{upload_id}")
async def instagram_queue_action(upload_id: str, req: InstagramQueueActionRequest):
    from modules.instagram_queue import get_instagram_queue
    queue = get_instagram_queue()
    if req.action == "retry":
        item = queue.retry(upload_id)
        if not item: return JSONResponse({"error": "Cannot retry."}, status_code=400)
        return _instagram_upload_payload(item)
    if req.action == "remove":
        if not queue.remove(upload_id): return JSONResponse({"error": "Cannot remove."}, status_code=400)
        return {"success": True}
    if req.action == "mark_completed":
        item = queue.mark_completed(upload_id)
        if not item: return JSONResponse({"error": "Cannot mark completed."}, status_code=400)
        return _instagram_upload_payload(item)
    if req.action == "cancel":
        item = queue.cancel(upload_id)
        if not item: return JSONResponse({"error": "Cannot cancel."}, status_code=400)
        return _instagram_upload_payload(item)
    if req.action in {"move_up", "move_down"}:
        item = queue.move(upload_id, -1 if req.action == "move_up" else 1)
        if not item: return JSONResponse({"error": "Cannot move."}, status_code=400)
        return _instagram_upload_payload(item)
    return JSONResponse({"error": "Unknown action."}, status_code=400)

@router.post("/api/social/instagram/queue")
async def instagram_queue_control(req: InstagramQueueActionRequest):
    from modules.instagram_queue import get_instagram_queue
    queue = get_instagram_queue()
    if req.action == "pause": queue.set_paused(True)
    elif req.action == "resume": queue.set_paused(False)
    elif req.action == "clear_failed": return {"removed": queue.clear({"failed", "login_required", "challenge_required", "rate_limited", "rejected"})}
    elif req.action == "remove_completed": return {"removed": queue.clear({"completed"})}
    else: return JSONResponse({"error": "Unknown action."}, status_code=400)
    return queue.summary()
