"""YouTube automated auto-publisher using Playwright and persistent browser profile.

This module automates the installed user's YouTube Studio session.
Every upload is automatically scheduled for 12:00 AM (00:00).
"""

from __future__ import annotations

import logging
import os
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError,
    sync_playwright,
)

from modules.publishers.youtube.uploader import initiate_upload, wait_for_upload_completion, UploadNetworkTelemetry
from modules.publishers.youtube.metadata import fill_metadata
from modules.publishers.youtube.scheduler import calculate_schedule_target, apply_schedule, verify_schedule

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, str], None]
SUPPORTED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}


def _state_dir() -> Path:
    """Return user-private state directory for YouTube state."""
    root = os.getenv("XDG_STATE_HOME")
    if root:
        base = Path(root)
    elif os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "state"
    directory = base / "cliphub" / "youtube"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


PROFILE_DIR = _state_dir() / "browser-profile"
DEBUG_DIR = _state_dir() / "debug"


def get_channel_profile_dir(channel_id: str | None = None) -> Path:
    """Return isolated Chrome profile directory for a specific channel.
    
    Each YouTube channel gets its own isolated browser profile directory,
    preventing session cookie leakage between channels (e.g. Phyroosh vs Right Gravity).
    Falls back to shared PROFILE_DIR if no channel_id is provided.
    """
    if channel_id:
        profile = _state_dir() / "channel-profiles" / channel_id
        profile.mkdir(parents=True, exist_ok=True)
        # Symlink the global profile's cookies/sessions into the channel profile
        # if the channel profile is brand new and the global one has auth data
        global_cookies = PROFILE_DIR / "Default" / "Cookies"
        channel_cookies = profile / "Default" / "Cookies"
        if global_cookies.exists() and not channel_cookies.exists():
            (profile / "Default").mkdir(parents=True, exist_ok=True)
            try:
                import shutil as _shutil
                import sqlite3
                def _safe_copy_db(src_path, dst_path):
                    with sqlite3.connect(str(src_path)) as src_conn:
                        with sqlite3.connect(str(dst_path)) as dst_conn:
                            src_conn.backup(dst_conn)

                _safe_copy_db(global_cookies, channel_cookies)
                for extra in ("Login Data", "Web Data", "Preferences"):
                    src = PROFILE_DIR / "Default" / extra
                    dst = profile / "Default" / extra
                    if src.exists() and not dst.exists():
                        if extra == "Preferences":
                            _shutil.copy2(str(src), str(dst))
                        else:
                            _safe_copy_db(src, dst)
            except Exception as _e:
                logger.debug("[YouTube] Profile seed copy partial: %s", _e)
        return profile
    return PROFILE_DIR


_login_lock = threading.Lock()
_login_in_progress = False


class YouTubeUploadError(RuntimeError):
    """An upload failure during YouTube Studio automation."""

    def __init__(self, message: str, *, stage: str = "unknown", retryable: bool = True) -> None:
        super().__init__(message)
        self.stage = stage
        self.retryable = retryable


@dataclass(frozen=True)
class YouTubeUploadResult:
    """Observed result of a YouTube Studio upload & scheduling execution."""

    status: str  # scheduled, completed, needs_manual_verification
    video_url: Optional[str] = None
    scheduled_time: Optional[str] = None


def _headless() -> bool:
    return os.getenv("CLIPHUB_YOUTUBE_HEADLESS", os.getenv("CLIPHUB_HEADLESS", "1")).strip().lower() not in {"0", "false", "no"}


def validate_youtube_video(video_path: str) -> float:
    """Reject non-existent or unreadable local video files before opening browser."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"YouTube video not found: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"YouTube video is not readable: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"YouTube upload requires a supported video format ({', '.join(SUPPORTED_SUFFIXES)}).")
    if path.stat().st_size == 0:
        raise ValueError("YouTube video is empty.")

    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
        duration = float(result.stdout.strip())
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is required to validate YouTube videos but was not found.") from exc
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise ValueError("YouTube video is corrupted or has no readable duration.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out while validating YouTube video.") from exc

    if duration < 1.0:
        raise ValueError("YouTube video duration must be at least 1 second.")
    return duration


def _get_platform_user_agent() -> str:
    if os.name == "nt":
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    elif sys.platform == "darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def _find_system_chrome() -> Optional[str]:
    """Find installed system Google Chrome binary to bypass automation detection."""
    for binary in ("google-chrome-stable", "google-chrome", "chromium-browser", "chromium", "chrome"):
        path = shutil.which(binary)
        if path:
            return path
            
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
                
    if sys.platform == "darwin":
        mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if mac_chrome.is_file():
            return str(mac_chrome)

    return None


def _find_free_port(start: int = 9300) -> int:
    """Find a free TCP port starting from `start`."""
    import socket
    for port in range(start, start + 200):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start  # fallback


def _clean_stale_chrome_lock(user_data_dir: Path | str):
    """Safely cleans stale SingletonLock only if the holding process is dead."""
    lock_file = Path(user_data_dir) / "SingletonLock"
    if not (lock_file.is_symlink() or lock_file.exists()):
        return
    stale = True
    try:
        if lock_file.is_symlink():
            target = os.readlink(str(lock_file))
            parts = target.split("-")
            if len(parts) >= 2 and parts[-1].isdigit():
                pid = int(parts[-1])
                try:
                    os.kill(pid, 0)
                    stale = False  # Process is actively running!
                except (OSError, ProcessLookupError):
                    stale = True
        if stale:
            lock_file.unlink(missing_ok=True)
    except Exception:
        pass


def _launch_persistent_context(playwright, user_data_dir: str, headless: bool, viewport: dict, cdp_port: int | None = None) -> tuple[BrowserContext, Optional[subprocess.Popen]]:
    """Launch persistent context using system Chrome with anti-bot detection evasions."""
    _clean_stale_chrome_lock(user_data_dir)

    user_agent_str = _get_platform_user_agent()
    system_chrome = _find_system_chrome()
    if system_chrome:
        if cdp_port is None:
            cdp_port = _find_free_port(start=9400)
            
        # Use CDP connect — caller picks the port to avoid conflicts
        port = cdp_port
        cmd = [
            system_chrome,
            f"--user-data-dir={Path(user_data_dir).resolve()}",
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1440,1000",
            f"--user-agent={user_agent_str}",
            "about:blank",
        ]
        if headless:
            cmd.append("--headless=new")

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3.0)
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context(viewport=viewport)
            return context, proc
        except Exception as e:
            logger.warning(f"[YouTube] CDP connect failed on port {port}: {e}, falling back to standard launch...")
            try:
                proc.terminate()
            except Exception:
                pass

    # Fallback to standard launch
    kwargs = {
        "user_data_dir": user_data_dir,
        "headless": headless,
        "viewport": viewport,
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
        ],
        "user_agent": user_agent_str,
    }
    if system_chrome:
        kwargs["executable_path"] = system_chrome

    context = playwright.chromium.launch_persistent_context(**kwargs)
    return context, None


def _save_diagnostics(context: BrowserContext, page: Page, reason: str, console_lines: list[str]) -> Path:
    """Persist failure screenshot, page HTML, console output, and trace for debugging."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^a-z0-9_-]+", "-", reason.lower())[:50]
    directory = DEBUG_DIR / f"{stamp}-{safe_reason}"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(directory / "failure.png"), full_page=True)
        (directory / "page.html").write_text(page.content(), encoding="utf-8")
        (directory / "console.log").write_text("\n".join(console_lines), encoding="utf-8")
        context.tracing.stop(path=str(directory / "trace.zip"))
    except Exception as exc:
        logger.warning("[YouTube] Could not save complete diagnostics: %s", exc)
    return directory


CHANNEL_INFO_FILE = _state_dir() / "channel_info.json"


def get_youtube_channel_info() -> dict:
    """Return stored YouTube channel metadata if available."""
    if CHANNEL_INFO_FILE.exists():
        try:
            return json.loads(CHANNEL_INFO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def update_youtube_channel_info(name: str, handle: str = "", channel_id: str = "") -> dict:
    """Update stored YouTube channel metadata."""
    data = {
        "name": name,
        "handle": handle,
        "channel_id": channel_id,
        "updated_at": time.time(),
    }
    CHANNEL_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANNEL_INFO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def extract_channel_info_from_page(page: Page) -> tuple[str, str, str]:
    """Extract (name, handle, channel_id) from an open YouTube Studio page."""
    try:
        url = page.url
        channel_id = ""
        if "/channel/" in url:
            channel_id = url.split("/channel/")[1].split("/")[0].split("?")[0]

        name = ""
        for sel in ("#entity-name", "#channel-name", "ytcp-navigation-drawer #entity-name", "ytcp-header #channel-name"):
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible():
                    text = el.inner_text().strip()
                    if text:
                        name = text
                        break
            except Exception:
                pass

        handle = ""
        for sel in ("#channel-handle", "[id='channel-handle']", "ytcp-navigation-drawer #channel-handle"):
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible():
                    text = el.inner_text().strip()
                    if text:
                        handle = text
                        break
            except Exception:
                pass

        if not name and channel_id:
            name = "Saved Session"

        if name or channel_id:
            update_youtube_channel_info(name=name, handle=handle, channel_id=channel_id)
        return name, handle, channel_id
    except Exception as exc:
        logger.warning("[YouTube] Could not extract channel info from page: %s", exc)
        return "", "", ""


def inspect_youtube_channel() -> dict:
    """Inspect YouTube Studio headlessly to refresh active channel name & handle."""
    if not is_youtube_connected():
        return {}
    proc = None
    try:
        with sync_playwright() as playwright:
            context, proc = _launch_persistent_context(
                playwright=playwright,
                user_data_dir=str(PROFILE_DIR),
                headless=True,
                viewport={"width": 1280, "height": 800},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(2_000)
                name, handle, cid = extract_channel_info_from_page(page)
                if name:
                    logger.info("[YouTube] Detected active channel: %s (%s)", name, handle or "no handle")
                    return get_youtube_channel_info()
            finally:
                context.close()
    except Exception as exc:
        logger.warning("[YouTube] Inspect active channel failed: %s", exc)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    return get_youtube_channel_info()


def is_youtube_connected() -> bool:
    """Return whether a persistent browser profile exists for YouTube Studio."""
    return PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())


def disconnect_youtube() -> None:
    """Remove locally stored YouTube Playwright browser profile and session cookies."""
    # Suspend the worker first so it releases file locks
    try:
        from modules.youtube_worker import get_youtube_worker
        get_youtube_worker().suspend()
    except Exception:
        pass

    if PROFILE_DIR.exists():
        logger.info("[YouTube] Removing persistent browser profile at %s", PROFILE_DIR)
        shutil.rmtree(str(PROFILE_DIR), ignore_errors=True)
    if CHANNEL_INFO_FILE.exists():
        CHANNEL_INFO_FILE.unlink(missing_ok=True)
    logger.info("[YouTube] Local browser session disconnected.")


def connect_youtube_playwright() -> bool:
    """Open a visible browser window for YouTube Studio login, extract channel info, save cookies, and auto-close."""
    try:
        from modules.youtube_worker import get_youtube_worker
        get_youtube_worker().suspend()
    except Exception:
        pass

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[YouTube] Launching visible Playwright browser for login")

    try:
        with sync_playwright() as playwright:
            cdp_port = _find_free_port(start=9300)
            context, proc = _launch_persistent_context(
                playwright=playwright,
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1280, "height": 800},
                cdp_port=cdp_port,
            )
            page = context.pages[0] if context.pages else context.new_page()

            page.goto("https://studio.youtube.com/")
            logger.info("[YouTube] Waiting for user to log in...")

            deadline = time.monotonic() + 300.0
            logged_in = False
            login_success_count = 0
            while time.monotonic() < deadline and not page.is_closed():
                try:
                    url = page.url.lower()
                    if "accounts.google.com" not in url and "channel_switcher" not in url:
                        if page.locator("#create-icon, ytcp-header #avatar-btn, ytcp-header").count() > 0:
                            logged_in = True
                            name, handle, cid = extract_channel_info_from_page(page)
                            login_success_count += 1
                            try:
                                page.evaluate(f"""() => {{
                                    if (!document.getElementById('cliphub-login-banner')) {{
                                        const div = document.createElement('div');
                                        div.id = 'cliphub-login-banner';
                                        div.innerHTML = '<h2>✅ Connected to {name or "YouTube Channel"}! Saving session...</h2>';
                                        div.style.position = 'fixed'; div.style.top = '10px'; div.style.left = '50%';
                                        div.style.transform = 'translateX(-50%)'; div.style.background = '#4CAF50';
                                        div.style.color = 'white'; div.style.padding = '15px 25px'; div.style.zIndex = '999999';
                                        div.style.borderRadius = '8px'; div.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
                                        div.style.fontFamily = 'sans-serif';
                                        document.body.appendChild(div);
                                    }}
                                }}""")
                            except Exception:
                                pass
                            
                            # If we confirmed channel details or spent 2 seconds after login, exit loop cleanly
                            if login_success_count >= 2:
                                logger.info("[YouTube] Successfully saved session for channel: %s (%s)", name, cid)
                                page.wait_for_timeout(1500)
                                break
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(1000)
                except Exception:
                    break

            if logged_in:
                logger.info("[YouTube] Auth completed! User closed window.")

            try:
                context.close()
            except Exception:
                pass
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    pass

            if logged_in:
                # Get the channel_id from the latest channel info
                channel_info = get_youtube_channel_info()
                c_id = channel_info.get("channel_id")
                if c_id:
                    try:
                        import shutil
                        target_dir = get_channel_profile_dir(c_id)
                        if target_dir != PROFILE_DIR:
                            temp_target = target_dir.parent / f"{c_id}_tmp_{int(time.time())}"
                            shutil.copytree(PROFILE_DIR, temp_target, dirs_exist_ok=True)
                            if target_dir.exists():
                                backup_dir = target_dir.parent / f"{c_id}_bak"
                                if backup_dir.exists():
                                    shutil.rmtree(backup_dir, ignore_errors=True)
                                target_dir.rename(backup_dir)
                            temp_target.rename(target_dir)
                            logger.info("[YouTube] Profile cleanly isolated to %s", target_dir)
                    except Exception as e:
                        logger.error("[YouTube] Failed to isolate profile: %s", e)
    except Exception as e:
        logger.error(f"[YouTube] Connection workflow error: {e}")
    finally:
        try:
            from modules.youtube_worker import get_youtube_worker
            get_youtube_worker().resume()
        except Exception:
            pass

    return True


def post_youtube_video(
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: str | None = None,
    tags: list[str] | None = None,
    progress: Optional[ProgressCallback] = None,
) -> YouTubeUploadResult:
    """Upload a video to YouTube Studio and schedule it for 12:00 AM.
    
    The video is NEVER published immediately.
    """
    validate_youtube_video(video_path)
    notify = progress or (lambda _percent, _message: None)
    console_lines: list[str] = []
    
    # Calculate schedule date & time (12:00 AM, next calendar day if current time > 00:00)
    target_dt, date_str, time_str = calculate_schedule_target()
    scheduled_display_time = f"{date_str} at {time_str}"
    
    channel_profile_dir = get_channel_profile_dir(get_youtube_channel_info().get("channel_id"))
    channel_profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = None
    context = None
    proc = None
    page = None
    current_stage = "init"

    try:
        notify(5, "Opening YouTube Studio")
        playwright = sync_playwright().start()
        logger.info("[YouTube] Using isolated channel profile: %s", channel_profile_dir)
        context, proc = _launch_persistent_context(
            playwright=playwright,
            user_data_dir=str(channel_profile_dir),
            headless=_headless(),
            viewport={"width": 1440, "height": 1000},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.on("console", lambda msg: console_lines.append(f"{msg.type}: {msg.text}"))

        # Attach CDP network telemetry listener BEFORE file upload begins
        # so every HTTP response from upload.youtube.com is captured
        channel_id = get_youtube_channel_info().get("channel_id")
        telemetry = UploadNetworkTelemetry(page)
        logger.info("[YouTube] CDP Network Telemetry listener attached.")

        # Step 1: Initiate upload
        current_stage = "upload"
        notify(15, "Uploading video file")
        initiate_upload(page, video_path, channel_id=channel_id)

        # Step 2: Fill metadata
        current_stage = "metadata"
        notify(40, "Filling metadata")
        clean_title = re.sub(r'^(?:clip[_\s\-]*\d+[_\s\-]*)+', '', title, flags=re.I).strip()
        if "_" in clean_title and " " not in clean_title:
            clean_title = clean_title.replace("_", " ")
        clean_title = clean_title or title
        fill_metadata(page, clean_title, description, tags, thumbnail_path)

        # Step 3: Wait for raw video file upload transfer to complete 100% across the network
        # Uses dual-mode verification: CDP network telemetry + DOM progress element polling
        notify(60, "Waiting for video file upload transfer to complete")
        wait_for_upload_completion(page, telemetry=telemetry, timeout=180_000)

        # Step 4: Apply schedule
        current_stage = "schedule"
        notify(75, "Scheduling upload")
        apply_schedule(page, date_str, time_str)

        # Step 4: Verify schedule
        current_stage = "verify"
        notify(90, "Verifying schedule")
        success, video_url = verify_schedule(page, timeout=30_000)
        
        if not success:
            raise RuntimeError("Schedule verification timed out. The video may not have been saved or YouTube Studio blocked the save request (e.g. daily upload limit exceeded).")

        notify(100, "Successfully scheduled YouTube video")
        return YouTubeUploadResult(
            status="scheduled",
            video_url=video_url,
            scheduled_time=scheduled_display_time,
        )

    except (TimeoutError, PlaywrightError) as exc:
        detail = f"[YouTube] Stage '{current_stage}' failed: {exc}"
        if context is not None and page is not None:
            diag_dir = _save_diagnostics(context, page, f"failure-{current_stage}", console_lines)
            detail += f" Diagnostics saved to {diag_dir}."
        logger.error(detail)
        raise YouTubeUploadError(detail, stage=current_stage, retryable=True) from exc
    except Exception as exc:
        detail = f"[YouTube] Unexpected failure during stage '{current_stage}': {exc}"
        if context is not None and page is not None:
            diag_dir = _save_diagnostics(context, page, f"unexpected-{current_stage}", console_lines)
            detail += f" Diagnostics saved to {diag_dir}."
        logger.error(detail)
        raise YouTubeUploadError(detail, stage=current_stage, retryable=False) from exc
    finally:
        if context is not None:
            try:
                context.tracing.stop()
            except Exception:
                pass
            try:
                context.close()
            except Exception:
                pass
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
