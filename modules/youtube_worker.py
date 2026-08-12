import threading
import queue
import time
import logging
from typing import Optional, Callable
from playwright.sync_api import sync_playwright

from modules.publishers.youtube.publisher import (
    _headless,
    _launch_persistent_context,
    _save_diagnostics,
    YouTubeUploadError,
    PROFILE_DIR,
)
from modules.publishers.youtube.uploader import (
    initiate_upload,
    wait_for_upload_completion,
    UploadNetworkTelemetry,
)
from modules.publishers.youtube.metadata import fill_metadata
from modules.publishers.youtube.scheduler import (
    calculate_schedule_target,
    apply_schedule,
    verify_schedule,
)

logger = logging.getLogger(__name__)

class YouTubePersistentWorker:
    def __init__(self):
        self._queue = queue.Queue()
        self._thread = None
        self._playwright = None
        self._context = None
        self._proc = None
        self.results = {}
        self.progress_callbacks = {}
        self._suspend_requested = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self.start()

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True, name="youtube-worker")
            self._thread.start()

    def enqueue(self, upload_id, video_path, title, description, tags, thumbnail_path, product_recommendations, amazon_store_tag, enable_comment_affiliate, enable_native_shopping, progress_cb):
        self.results[upload_id] = {"status": "queued"}
        self.progress_callbacks[upload_id] = progress_cb
        self._queue.put({
            "upload_id": upload_id,
            "video_path": video_path,
            "title": title,
            "description": description,
            "tags": tags,
            "thumbnail_path": thumbnail_path,
            "product_recommendations": product_recommendations,
            "amazon_store_tag": amazon_store_tag,
            "enable_comment_affiliate": enable_comment_affiliate,
            "enable_native_shopping": enable_native_shopping
        })
        return upload_id

    def _notify(self, upload_id, pct, msg):
        logger.info(f"[YouTube Worker] {msg}")
        cb = self.progress_callbacks.get(upload_id)
        if cb:
            try:
                cb(pct, msg)
            except:
                pass

    def suspend(self):
        """Signal the worker thread to release the browser lock."""
        logger.info("[YouTube Worker] Suspending persistent browser for manual login...")
        self._pause_event.clear()
        self._suspend_requested = True
        # Wait until the worker thread actually closes the context
        while self._context is not None:
            time.sleep(0.1)

    def resume(self):
        """Resume queue processing and restart the browser."""
        logger.info("[YouTube Worker] Resuming operations...")
        self._suspend_requested = False
        self._pause_event.set()

    def _run(self):
        while True:
            logger.info("[YouTube Worker] Starting persistent browser session...")
            try:
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except:
                        pass
                self._playwright = sync_playwright().start()
                
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                
                from modules.publishers.youtube.publisher import get_channel_profile_dir, get_youtube_channel_info
                channel_id = get_youtube_channel_info().get("channel_id")
                channel_profile_dir = get_channel_profile_dir(channel_id)
                channel_profile_dir.mkdir(parents=True, exist_ok=True)
                
                # Clean up any stale lock files left by the login browser
                for target_dir in (PROFILE_DIR, channel_profile_dir):
                    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                        lock_path = target_dir / lock_name
                        if lock_path.is_symlink() or lock_path.exists():
                            try:
                                lock_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                

                
                # Use native Playwright (no CDP port) — no conflicts with the login browser
                self._context, self._proc = _launch_persistent_context(
                    playwright=self._playwright,
                    user_data_dir=str(channel_profile_dir),
                    headless=_headless(),
                    viewport={"width": 1440, "height": 1000},
                    cdp_port=None,
                )
            except Exception as e:
                logger.error(f"[YouTube Worker] Failed to start browser: {e}. Retrying in 10s...")
                time.sleep(10)
                continue

            # Process jobs while the context is alive
            while True:
                if self._suspend_requested:
                    logger.info("[YouTube Worker] Worker thread closing browser for suspend...")
                    if self._context:
                        try:
                            self._context.close()
                        except: pass
                        self._context = None
                    if getattr(self, "_proc", None) and self._proc.poll() is None:
                        try:
                            self._proc.terminate()
                            self._proc.wait(timeout=5)
                        except: pass
                        self._proc = None
                    if self._playwright:
                        try:
                            self._playwright.stop()
                        except: pass
                        self._playwright = None
                    # Wait for resume
                    self._pause_event.wait()
                    break # Restart browser
                
                try:
                    # Poll so we can catch suspend requests quickly
                    job = self._queue.get(timeout=1.0)
                    self._process_job(job)
                    self._queue.task_done()
                except queue.Empty:
                    pass
                except Exception as e:
                    if str(e) == "RESTART_HEADFUL":
                        logger.info("[YouTube Worker] Restarting browser context in HEADFUL mode...")
                        if self._context:
                            try: self._context.close()
                            except: pass
                            self._context = None
                        break
                    logger.error(f"[YouTube Worker] Queue error: {e}")
                    time.sleep(1)

    def _process_job(self, job):
        upload_id = job["upload_id"]
        video_path = job["video_path"]
        title = job["title"]
        description = job["description"]
        tags = job["tags"]
        thumbnail_path = job["thumbnail_path"]
        product_recommendations = job.get("product_recommendations") or []
        amazon_store_tag = job.get("amazon_store_tag", "")
        enable_comment_affiliate = job.get("enable_comment_affiliate", True)
        enable_native_shopping = job.get("enable_native_shopping", False)

        affiliate_comment_text = ""
        if enable_comment_affiliate and product_recommendations:
            import urllib.parse
            prod = product_recommendations[0]
            query = prod.get("search_query") or prod.get("product_name") or ""
            link = f"https://www.amazon.com/s?k={urllib.parse.quote_plus(query)}"
            if amazon_store_tag:
                link += f"&tag={urllib.parse.quote_plus(amazon_store_tag)}"
            affiliate_comment_text = f"🛒 Featured in this clip: {prod.get('product_name', query)}\n👉 Check it out here on Amazon: {link}\n\n#ad"
            description = (description or "") + "\n\n" + affiliate_comment_text

        self.results[upload_id]["status"] = "uploading"
        self._notify(upload_id, 10, "Starting YouTube upload in persistent browser")
        
        page = None
        console_lines = []
        current_stage = "init"
        
        try:
            # Create a NEW page for every job to avoid memory leak with event listeners
            page = self._context.new_page()
            page.on("console", lambda msg: console_lines.append(f"{msg.type}: {msg.text}"))
            
            telemetry = UploadNetworkTelemetry(page)
            
            current_stage = "upload"
            self._notify(upload_id, 15, "Uploading video file")
            
            from modules.publishers.youtube.publisher import get_youtube_channel_info
            channel_id = get_youtube_channel_info().get("channel_id")
            initiate_upload(page, video_path, channel_id)
            
            current_stage = "metadata"
            self._notify(upload_id, 40, "Filling metadata")
            import re
            clean_title = re.sub(r'^(?:clip[_\s\-]*\d+[_\s\-]*)+', '', title, flags=re.I).strip()
            if "_" in clean_title and " " not in clean_title:
                clean_title = clean_title.replace("_", " ")
            clean_title = clean_title or title
            fill_metadata(page, clean_title, description, tags, thumbnail_path)
            
            current_stage = "transfer"
            self._notify(upload_id, 60, "Waiting for video file upload transfer to complete")
            wait_for_upload_completion(page, telemetry=telemetry, timeout=180_000)
            
            if product_recommendations and enable_native_shopping:
                current_stage = "affiliate_tagging"
                self._notify(upload_id, 65, "Tagging affiliate products via YouTube Shopping")
                from modules.publishers.youtube.affiliate import tag_products
                tag_products(page, product_recommendations)
            
            target_dt, date_str, time_str = calculate_schedule_target()
            scheduled_display_time = f"{date_str} at {time_str}"
            
            current_stage = "schedule"
            self._notify(upload_id, 75, "Scheduling upload")
            apply_schedule(page, date_str, time_str)
            
            current_stage = "verify"
            self._notify(upload_id, 90, "Verifying schedule")
            success, video_url = verify_schedule(page, timeout=30_000)
            
            if not success:
                raise RuntimeError("Schedule verification timed out.")
                
            self._notify(upload_id, 95, "Successfully scheduled YouTube video")
            self.results[upload_id] = {
                "status": "scheduled",
                "success": True,
                "url": video_url,
                "scheduled_time": scheduled_display_time
            }

            if affiliate_comment_text and video_url:
                self._notify(upload_id, 98, "Posting and pinning affiliate comment...")
                try:
                    from modules.publishers.youtube.affiliate import post_pinned_comment
                    post_pinned_comment(page, video_url, affiliate_comment_text)
                except Exception as c_exc:
                    logger.warning(f"[YouTube Worker] Could not post pinned comment: {c_exc}")

            self._notify(upload_id, 100, "Upload & affiliate monetization complete!")
            
        except Exception as exc:
            detail = f"Stage '{current_stage}' failed: {exc}"
            
            if "Google Security Verification required" in str(exc) and not getattr(self, "_force_headful", False):
                logger.info(f"[YouTube Worker] 2FA detected! Relaunching browser in HEADFUL mode to allow manual verification...")
                self._force_headful = True
                os.environ["CLIPHUB_YOUTUBE_HEADLESS"] = "0"
                os.environ["CLIPHUB_YOUTUBE_WAIT_FOR_2FA"] = "1"
                self._queue.put(job)
                raise RuntimeError("RESTART_HEADFUL")
                
            if self._context and page:
                diag_dir = _save_diagnostics(self._context, page, f"failure-{current_stage}", console_lines)
                detail += f" Diagnostics saved to {diag_dir}."
            logger.error(f"[YouTube Worker] {detail}")
            self.results[upload_id] = {
                "status": "failed",
                "success": False,
                "error": detail
            }
        finally:
            if page:
                try:
                    page.close()
                except:
                    pass

_youtube_worker = None
def get_youtube_worker():
    global _youtube_worker
    if _youtube_worker is None:
        _youtube_worker = YouTubePersistentWorker()
    return _youtube_worker
