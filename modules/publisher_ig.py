"""Personal-desktop Instagram Reel uploader backed by Playwright.

This module intentionally automates the installed user's Instagram session.  It
does not use credentials, tokens, or cookies from the repository.  Browser
state and diagnostics live in the user's OS state directory instead.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page, TimeoutError, sync_playwright

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, str], None]


def _state_dir() -> Path:
    """Return a user-private state directory, never a repository path."""
    root = os.getenv("XDG_STATE_HOME")
    if root:
        base = Path(root)
    elif os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "state"
    directory = base / "cliphub" / "instagram"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


STATE_FILE = _state_dir() / "storage_state.json"
PROFILE_DIR = _state_dir().parent / "browser-profile"
DEBUG_DIR = _state_dir() / "debug"
LEGACY_STATE_FILE = Path(__file__).parent.parent / "credentials" / "instagram_state.json"
SUPPORTED_SUFFIXES = {".mp4", ".mov"}
_login_lock = threading.Lock()
_login_in_progress = False


class InstagramUploadError(RuntimeError):
    """An upload failure with retry safety metadata for the persistent queue."""

    def __init__(self, message: str, *, status: str = "failed", retryable: bool = False, share_clicked: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.share_clicked = share_clicked


@dataclass(frozen=True)
class InstagramUploadResult:
    """The observed result of a browser-driven upload."""

    status: str  # completed or needs_manual_verification
    reel_url: Optional[str] = None


def _headless() -> bool:
    val = os.getenv("CLIPHUB_INSTAGRAM_HEADLESS") or os.getenv("OBSCURA_INSTAGRAM_HEADLESS", "1")
    return val.strip().lower() not in {"0", "false", "no"}


def validate_reel_video(video_path: str) -> float:
    """Reject unreadable or clearly unsuitable local Reel files before a browser opens."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Instagram video not found: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"Instagram video is not readable: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Instagram uploads require an MP4 or MOV video file.")
    if path.stat().st_size == 0:
        raise ValueError("Instagram video is empty.")
    if path.stat().st_size > 1024 * 1024 * 1024:
        raise ValueError("Instagram video exceeds the 1 GB safety limit.")

    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
        duration = float(result.stdout.strip())
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is required to validate Instagram videos but was not found.") from exc
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise ValueError("Instagram video is corrupted or has no readable duration.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out while validating the Instagram video.") from exc
    if not 3 <= duration <= 900:
        raise ValueError(f"Instagram video duration must be between 3 and 900 seconds (got {duration:.1f}s).")
    return duration


def _is_login_page(page: Page) -> bool:
    return "accounts/login" in page.url or page.locator('input[name="username"]').count() > 0


def _blocking_status(page: Page) -> Optional[tuple[str, str]]:
    """Identify browser-visible terminal states before considering a retry."""
    try:
        body = page.locator("body").inner_text(timeout=2_000).lower()
    except PlaywrightError:
        return None
    if "challenge_required" in page.url or "security check" in body or "confirm it's you" in body:
        return "challenge_required", "Instagram requires a security challenge. Complete it manually, then submit the clip again."
    if "too many requests" in body or ("try again later" in body and "rate" in body):
        return "rate_limited", "Instagram rate-limited this upload. Wait and submit it manually later."
    if "couldn't process" in body or "cannot be uploaded" in body or "not allowed to post" in body:
        return "rejected", "Instagram rejected this video or post. Review the Reel in Instagram before submitting again."
    return None


def _open_login_browser_in_background() -> None:
    """Launch one login window without blocking the queue for five minutes."""
    global _login_in_progress
    with _login_lock:
        if _login_in_progress:
            return
        _login_in_progress = True

    def login() -> None:
        global _login_in_progress
        try:
            connect_instagram_playwright()
        except Exception as exc:
            logger.warning("[Instagram] Interactive login did not complete: %s", exc)
        finally:
            with _login_lock:
                _login_in_progress = False

    threading.Thread(target=login, name="instagram-login", daemon=True).start()


def _is_authenticated(page: Page) -> bool:
    if _is_login_page(page):
        return False
    # These are user-visible controls rather than DOM implementation details.
    navigation = page.get_by_role("link", name=re.compile(r"^(Home|New post|Create|Profile)$", re.I)).first
    try:
        navigation.wait_for(state="visible", timeout=12_000)
        return True
    except TimeoutError:
        return False


def _dismiss_interstitials(page: Page) -> None:
    for name in ("Allow all cookies", "Allow essential cookies", "Not now", "Cancel"):
        button = page.get_by_role("button", name=re.compile(f"^{re.escape(name)}$", re.I))
        if button.count():
            try:
                button.first.click(timeout=1_500)
            except PlaywrightError:
                pass


def _save_diagnostics(context: BrowserContext, page: Page, reason: str, console_lines: list[str]) -> Path:
    """Persist screenshot, page HTML, console output, and trace for diagnosis."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^a-z0-9_-]+", "-", reason.lower())[:50]
    directory = DEBUG_DIR / f"{stamp}-{safe_reason}"
    directory.mkdir()
    try:
        page.screenshot(path=str(directory / "failure.png"), full_page=True)
        (directory / "page.html").write_text(page.content(), encoding="utf-8")
        (directory / "console.log").write_text("\n".join(console_lines), encoding="utf-8")
        context.tracing.stop(path=str(directory / "trace.zip"))
    except Exception as exc:  # Diagnostics must never hide the real upload failure.
        logger.warning("[Instagram] Could not save complete diagnostics: %s", exc)
    return directory


def _wait_for_login(page: Page) -> None:
    logger.info("[Instagram] Waiting for one-time interactive login in Chromium.")
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60_000)
    _dismiss_interstitials(page)
    page.get_by_role("link", name=re.compile(r"^(Home|New post|Create|Profile)$", re.I)).first.wait_for(
        state="visible", timeout=300_000
    )


def _launch_persistent_context(playwright, user_data_dir: str, headless: bool, viewport: dict) -> BrowserContext:
    """Launch persistent context, automatically installing chromium if missing."""
    kwargs = {
        "user_data_dir": str(Path(user_data_dir).resolve()),
        "headless": headless,
        "viewport": None if not headless else viewport,
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-default-browser-check",
            "--no-first-run",
            "--start-maximized",
            "--window-position=50,50",
            "--window-size=1366,850",
        ],
    }
    try:
        return playwright.chromium.launch_persistent_context(**kwargs)
    except Exception as exc:
        exc_str = str(exc)
        if "Executable doesn't exist" in exc_str or "playwright install" in exc_str:
            logger.info("[Instagram] Playwright Chromium executable not found. Running auto-installation...")
            try:
                import sys
                import subprocess
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                logger.info("[Instagram] Playwright Chromium installed successfully. Retrying launch...")
                return playwright.chromium.launch_persistent_context(**kwargs)
            except Exception as install_exc:
                logger.error("[Instagram] Failed to automatically install Playwright Chromium: %s", install_exc)
                raise exc
        else:
            raise


def _migrate_to_persistent_profile() -> bool:
    """Seed the persistent browser profile with cookies and localStorage from an
    existing ``storage_state.json``.

    Returns True if migration was performed, False if no migration was needed.
    """
    if PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir()):
        logger.info("[Instagram] Persistent browser profile already exists at %s", PROFILE_DIR)
        return False
    if not STATE_FILE.exists():
        logger.info("[Instagram] No storage_state.json to migrate — fresh profile will be created.")
        return False
    logger.info("[Instagram] Migrating storage_state.json → persistent browser profile at %s", PROFILE_DIR)
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[Instagram] Could not read storage_state.json for migration: %s", exc)
        return False
    try:
        with sync_playwright() as playwright:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            context = _launch_persistent_context(
                playwright=playwright,
                user_data_dir=str(PROFILE_DIR),
                headless=True,  # one-shot seed; user-facing login opens headful later
                viewport={"width": 1440, "height": 1000},
            )
            page = context.new_page()
            # Seed cookies into the persistent profile's native cookie store
            if state.get("cookies"):
                context.add_cookies(state["cookies"])
                logger.info("[Instagram] Seeded %d cookies into persistent profile.", len(state["cookies"]))
            # Seed localStorage origins (Instagram uses these for device trust)
            for origin_entry in state.get("origins", []):
                origin_url = origin_entry.get("origin", "")
                if not origin_url:
                    continue
                page.goto(origin_url, wait_until="domcontentloaded", timeout=15_000)
                for item in origin_entry.get("localStorage", []):
                    name = item["name"]
                    value = item["value"]
                    page.evaluate(
                        f"localStorage.setItem({json.dumps(name)}, {json.dumps(value)})"
                    )
                logger.info("[Instagram] Seeded localStorage for origin %s.", origin_url)
            # Navigate to Instagram so cookie/localStorage state reconciles
            # with the profile's IndexedDB / cache / service-worker stores
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)
            context.close()
            logger.info("[Instagram] Migration complete — profile seeded with existing session.")
            return True
    except Exception as exc:
        logger.warning("[Instagram] Profile migration failed (%s); will start fresh.", exc)
        # Don't leave a half-baked profile directory
        try:
            shutil.rmtree(str(PROFILE_DIR), ignore_errors=True)
        except Exception:
            pass
        return False


def connect_instagram_playwright(force_fresh: bool = False) -> bool:
    """Open a visible browser once, authenticate, and persist the session
    inside the dedicated persistent browser profile directory.

    All browser state — cookies, localStorage, IndexedDB, service workers,
    and device fingerprint — is retained by Chromium's user-data-dir.
    """
    if force_fresh:
        disconnect_instagram()
    _migrate_to_persistent_profile()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[Instagram] Opening login browser with persistent profile at %s (force_fresh=%s)", PROFILE_DIR, force_fresh)
    with sync_playwright() as playwright:
        context = _launch_persistent_context(
            playwright=playwright,
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        try:
            try:
                page.bring_to_front()
            except Exception:
                pass
            _wait_for_login(page)
            logger.info("[Instagram] Login successful — session persisted in %s", PROFILE_DIR)
            return True
        except TimeoutError as exc:
            raise RuntimeError(
                "Instagram login timed out after five minutes. "
                "Complete login and any security checks, then try again."
            ) from exc
        finally:
            context.close()


def connect_instagram_with_session(username: str, session_id: str) -> bool:
    """Import a manually supplied Instagram session cookie for legacy UI compatibility.

    Writes the JSON state file and immediately seeds the persistent browser
    profile so subsequent uploads use the new session.
    """
    if not username.strip() or not session_id.strip():
        raise ValueError("Instagram username and session ID are required.")
    state = {"cookies": [{"name": "sessionid", "value": session_id.strip(), "domain": ".instagram.com", "path": "/", "expires": -1, "httpOnly": True, "secure": True, "sameSite": "Lax"}], "origins": []}
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    logger.info("[Instagram] Saved manual session to %s; seeding persistent profile.", STATE_FILE)
    _migrate_to_persistent_profile()
    return True


def disconnect_instagram() -> None:
    """Remove locally stored Playwright browser state and persistent profile."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    if PROFILE_DIR.exists():
        logger.info("[Instagram] Removing persistent browser profile at %s", PROFILE_DIR)
        shutil.rmtree(str(PROFILE_DIR), ignore_errors=True)
    # Remove the old in-repository location only when the user explicitly
    # disconnects; normal startup migrates it without losing a valid session.
    if LEGACY_STATE_FILE.exists():
        LEGACY_STATE_FILE.unlink()
    logger.info("[Instagram] Local browser session disconnected.")


def is_instagram_connected() -> bool:
    """Return whether a reusable local browser session exists (not its validity).

    Checks the persistent browser profile first; falls back to the legacy JSON
    state file for backward compatibility with sessions created before the
    persistent-profile migration.
    """
    # Persistent profile — the canonical source after migration
    if PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir()):
        return True

    # Legacy JSON state file — migrate to persistent profile on first use
    if not STATE_FILE.exists() and LEGACY_STATE_FILE.is_file():
        try:
            shutil.move(str(LEGACY_STATE_FILE), str(STATE_FILE))
            logger.info("[Instagram] Migrated legacy browser session outside the repository.")
        except OSError as exc:
            logger.warning("[Instagram] Could not migrate legacy browser session: %s", exc)

    if STATE_FILE.is_file() and STATE_FILE.stat().st_size > 0:
        _migrate_to_persistent_profile()
        return PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())

    return False


def _open_authenticated_context(playwright, progress: ProgressCallback) -> tuple[object, BrowserContext, Page]:
    """Open Instagram inside the persistent browser profile.

    Every upload reuses the SAME Chromium user-data directory so cookies,
    localStorage, IndexedDB, service workers, and device fingerprint are all
    retained.  There is no separate Browser handle — the persistent context
    encapsulates both launcher and context, so close() tears everything down.
    """
    is_instagram_connected()  # Migrates a legacy session before opening Chromium.
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile_exists = PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())
    headless = _headless()
    logger.info(
        "[Instagram] Opening persistent context | profile=%s | exists=%s | headless=%s",
        PROFILE_DIR, profile_exists, headless,
    )
    context = _launch_persistent_context(
        playwright=playwright,
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1440, "height": 1000},
    )
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60_000)
    _dismiss_interstitials(page)
    blocking = _blocking_status(page)
    if blocking:
        logger.warning("[Instagram] Blocking status detected: %s — closing context", blocking[0])
        context.close()
        raise InstagramUploadError(blocking[1], status=blocking[0])
    if not _is_authenticated(page):
        current_url = page.url
        logger.warning(
            "[Instagram] Not authenticated after loading persistent profile "
            "(page url: %s, profile existed: %s). Triggering interactive login.",
            current_url, profile_exists,
        )
        context.close()
        progress(5, "Login required; opening Instagram login browser")
        _open_login_browser_in_background()
        raise InstagramUploadError(
            "Login required. Complete login in the browser, then submit this clip again.",
            status="login_required",
        )
    logger.info("[Instagram] Authenticated — reusing persistent browser session.")
    # With a persistent context there is no separate Browser object.
    return None, context, page


def _click_first_available(page: Page, names: tuple[str, ...], timeout: int = 20_000) -> None:
    """Click a visible action by accessible role, falling back to exact text.

    Instagram's creator menu currently exposes its menu entries as a nested
    ``span`` inside an anchor.  The anchor is not always represented as a
    Playwright accessibility link, so role-only lookup misses it.  Exact,
    visible text is a deliberately narrow final fallback for those entries.
    """
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        for name in names:
            locator = page.get_by_role("button", name=re.compile(f"^{re.escape(name)}$", re.I))
            if not locator.count():
                locator = page.get_by_role("link", name=re.compile(f"^{re.escape(name)}$", re.I))
            if locator.count():
                try:
                    logger.info("[Instagram] Clicking %s", name)
                    locator.first.click(timeout=2_000)
                    return
                except PlaywrightError:
                    # A stale/hidden menu item should not prevent the exact
                    # text fallback below from reaching the active one.
                    pass
            text_locator = page.get_by_text(name, exact=True)
            if text_locator.count():
                for index in range(text_locator.count()):
                    candidate = text_locator.nth(index)
                    try:
                        if not candidate.is_visible():
                            continue
                        logger.info("[Instagram] Clicking visible text %s", name)
                        candidate.click(timeout=2_000)
                        return
                    except PlaywrightError:
                        continue
        page.wait_for_timeout(250)
    raise TimeoutError(f"Timed out waiting for one of: {', '.join(names)}")


def _open_reel_creator(page: Page) -> object:
    """Open Instagram's media chooser across both known creator layouts.

    Older layouts expose the native file input immediately after ``Create``.
    The current desktop layout opens a second menu containing ``Post`` first.
    This waits for the input before selecting that second menu action so it
    does not introduce an unnecessary click on accounts using the old layout.
    """
    _click_first_available(page, ("New post", "Create"))
    file_input = page.locator('input[type="file"]').first
    try:
        file_input.wait_for(state="attached", timeout=3_000)
        return file_input
    except TimeoutError:
        logger.info("[Instagram] Creator menu requires a post-type selection.")
    _click_first_available(page, ("Post", "Reel"), timeout=15_000)
    file_input.wait_for(state="attached", timeout=20_000)
    return file_input


def _caption_field(page: Page) -> object:
    """Return the current caption editor without depending on one DOM shape."""
    selectors = (
        'div[contenteditable="true"][aria-label*="caption" i]',
        'div[contenteditable="true"][aria-label*="Write" i]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        'textarea[aria-label*="caption" i]',
        'textarea[placeholder*="caption" i]',
    )
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() and locator.is_visible():
            return locator
    return page.locator('[role="dialog"] div[contenteditable="true"]').first


def _fill_caption(page: Page, caption_box: object, caption_text: str) -> None:
    """Fill caption in Instagram's contenteditable editor using keyboard events and JS fallback."""
    caption_str = (caption_text or "").strip()[:2_200]
    if not caption_str:
        return

    logger.info("[Instagram] Entering caption (%d chars)...", len(caption_str))
    try:
        caption_box.focus()
        page.wait_for_timeout(300)
        # Select all and delete any existing draft text
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(200)

        # Type text using keyboard events so Draft.js / Lexical React state registers it
        page.keyboard.type(caption_str, delay=2)
        page.wait_for_timeout(500)

        # Check if text was registered into the DOM
        box_text = caption_box.inner_text().strip()
        if not box_text:
            logger.info("[Instagram] Keyboard typing check empty; applying JS innerText injection...")
            caption_box.evaluate(
                "(el, text) => { el.innerText = text; el.dispatchEvent(new Event('input', { bubbles: true })); }",
                caption_str
            )
    except Exception as e:
        logger.warning("[Instagram] Caption filling fallback notice: %s", e)


def _dismiss_video_post_reel_notice(page: Page) -> None:
    """Dismiss Instagram's one-time informational Reel notice, if shown.

    It appears immediately after selecting a video and overlays the Crop
    dialog's Next button.  This is intentionally scoped to the notice text so
    a generic confirmation dialog is never accepted automatically.
    """
    # The notice is rendered asynchronously after the file chooser event.
    # Poll briefly instead of racing directly to the covered Crop button.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        notice = page.get_by_text(re.compile(r"^Video posts are now shared as reels$", re.I))
        if notice.count() and notice.first.is_visible():
            dialog = notice.first.locator('xpath=ancestor-or-self::*[@role="dialog"]').first
            ok = dialog.get_by_role("button", name=re.compile(r"^OK$", re.I))
            if not ok.count():
                ok = dialog.get_by_text("OK", exact=True)
            logger.info("[Instagram] Dismissing video-posts-are-reels notice.")
            ok.first.click(timeout=10_000)
            return
        page.wait_for_timeout(100)


def _upload_cover_photo(page: Page, cover_image_path: str) -> bool:
    """Upload a custom cover photo/thumbnail to Instagram Reel creator."""
    if not cover_image_path or not os.path.isfile(cover_image_path):
        return False
    
    resolved_cover = str(Path(cover_image_path).resolve())
    logger.info("[Instagram] Setting custom universal cover photo: %s", resolved_cover)
    try:
        # Step 1: Ensure Cover Photo tab is active (if Edit tab layout is shown)
        cover_tab = page.get_by_role("tab", name=re.compile(r"^Cover photo$", re.I)).first
        if not cover_tab.count():
            cover_tab = page.get_by_text(re.compile(r"^Cover photo$", re.I)).first
        if cover_tab.count() and cover_tab.is_visible():
            try:
                cover_tab.click(timeout=2_000)
            except Exception:
                pass
            page.wait_for_timeout(300)

        # Step 2: Search for image file input or "Select from computer" button
        # Method A: Dedicated file input
        file_inputs = page.locator('input[type="file"]')
        for idx in range(file_inputs.count()):
            f_inp = file_inputs.nth(idx)
            accept = (f_inp.get_attribute("accept") or "").lower()
            if any(ext in accept for ext in ["image", "jpg", "jpeg", "png"]):
                logger.info("[Instagram] Found image file input (accept='%s'). Uploading cover...", accept)
                f_inp.set_input_files(resolved_cover, timeout=10_000)
                page.wait_for_timeout(1_000)
                return True

        # Method B: Click "Select from computer" / "Add from computer" button
        for btn_label in ("Select from computer", "Add from computer", "Upload cover photo"):
            btn = page.get_by_role("button", name=re.compile(f"^{re.escape(btn_label)}$", re.I)).first
            if not btn.count():
                btn = page.get_by_text(re.compile(f"^{re.escape(btn_label)}$", re.I)).first
            if btn.count() and btn.is_visible():
                logger.info("[Instagram] Found '%s' button. Triggering file chooser...", btn_label)
                try:
                    with page.expect_file_chooser(timeout=5_000) as fc_info:
                        btn.click(timeout=2_000)
                    chooser = fc_info.value
                    chooser.set_files(resolved_cover)
                    page.wait_for_timeout(1_000)
                    logger.info("[Instagram] ✅ Universal cover photo uploaded successfully.")
                    return True
                except Exception as fc_err:
                    logger.warning("[Instagram] File chooser error on '%s': %s", btn_label, fc_err)

        # Method C: If on caption/details screen, look for "Edit cover"
        edit_cover = page.get_by_text(re.compile(r"^Edit cover$", re.I)).first
        if not edit_cover.count():
            edit_cover = page.get_by_role("button", name=re.compile(r"^Edit cover$", re.I)).first
        if edit_cover.count() and edit_cover.is_visible():
            logger.info("[Instagram] Found 'Edit cover' button on details screen. Opening modal...")
            edit_cover.click(timeout=2_000)
            page.wait_for_timeout(500)
            for btn_label in ("Select from computer", "Add from computer"):
                btn = page.get_by_text(re.compile(f"^{re.escape(btn_label)}$", re.I)).first
                if btn.count() and btn.is_visible():
                    try:
                        with page.expect_file_chooser(timeout=5_000) as fc_info:
                            btn.click(timeout=2_000)
                        chooser = fc_info.value
                        chooser.set_files(resolved_cover)
                        page.wait_for_timeout(1_000)
                        done = page.get_by_role("button", name=re.compile(r"^(Done|Save)$", re.I)).first
                        if done.count() and done.is_visible():
                            done.click(timeout=2_000)
                        return True
                    except Exception as err:
                        logger.warning("[Instagram] Error in Edit Cover dialog: %s", err)

    except Exception as e:
        logger.warning("[Instagram] Notice while attempting to set universal cover photo: %s", e)
    return False


_upload_lock = threading.Lock()

def post_instagram_reel(video_path: str, caption: str, progress: Optional[ProgressCallback] = None, cover_path: Optional[str] = None) -> InstagramUploadResult:
    """Upload one Reel and return only an observed, verified outcome.

    Browser failures before Share are marked retryable. Once Share is clicked,
    uncertainty is never retried automatically to prevent duplicate posts.
    """
    with _upload_lock:
        validate_reel_video(video_path)
    notify = progress or (lambda _percent, _message: None)

    # Auto-detect custom cover thumbnail if not explicitly passed
    if not cover_path:
        v_path = Path(video_path)
        for cand in [
            v_path.with_name(f"{v_path.stem}_thumb.jpg"),
            v_path.with_name(f"{v_path.stem}_thumb.png"),
            v_path.with_name(f"{v_path.stem}.jpg"),
            v_path.with_name(f"{v_path.stem}.png"),
        ]:
            if cand.is_file() and cand.stat().st_size > 100:
                cover_path = str(cand.resolve())
                break

    console_lines: list[str] = []
    share_clicked = False
    browser = context = page = None
    playwright = None
    try:
        notify(5, "Opening Instagram")
        # Keep Playwright alive through the exception handler so screenshots,
        # HTML, network records, and traces can be written before shutdown.
        playwright = sync_playwright().start()
        if playwright is not None:
            browser, context, page = _open_authenticated_context(playwright, notify)
            logger.info("[Instagram] Authenticated browser context opened; navigating Reel creator.")
            page.on("console", lambda message: console_lines.append(f"{message.type}: {message.text}"))
            page.on("requestfailed", lambda request: console_lines.append(
                f"requestfailed: {request.method} {request.url} {request.failure}"
            ))
            page.on("response", lambda response: console_lines.append(
                f"http {response.status}: {response.url}"
            ) if response.status >= 400 else None)
            page.on("dialog", lambda dialog: (console_lines.append(f"dialog: {dialog.type} {dialog.message}"), dialog.dismiss()))
            page.on("popup", lambda popup: console_lines.append(f"popup: {popup.url}"))
            notify(15, "Opening Reel creator")
            file_input = _open_reel_creator(page)
            notify(25, "Sending video to Instagram")
            file_input.set_input_files(video_path, timeout=30_000)
            _dismiss_video_post_reel_notice(page)
            
            # Ensure the video uses original aspect ratio (9:16) instead of 1:1 square crop
            try:
                page.wait_for_timeout(1000)
                crop_btn = page.locator('button[aria-label="Select crop"]').first
                if not crop_btn.count():
                    crop_btn = page.get_by_role("button", name=re.compile(r"^Select crop$", re.I)).first
                if crop_btn.count() and crop_btn.is_visible():
                    logger.info("[Instagram] Found crop aspect ratio button, opening menu.")
                    crop_btn.click(timeout=3_000)
                    page.wait_for_timeout(500)
                    orig_btn = page.get_by_role("button", name=re.compile(r"^(Original|9:16)$", re.I)).first
                    if not orig_btn.count():
                        orig_btn = page.get_by_text(re.compile(r"^(Original|9:16)$", re.I)).first
                    if orig_btn.count() and orig_btn.is_visible():
                        logger.info("[Instagram] Setting crop to Original/9:16.")
                        orig_btn.click(timeout=3_000)
                        page.wait_for_timeout(500)
            except Exception as e:
                logger.info(f"[Instagram] Crop to Original failed or was not needed: {e}")

            notify(40, "Waiting for Instagram to prepare the video")
            _click_first_available(page, ("Next",), timeout=90_000)
            notify(55, "Setting cover photo & preparing Reel")
            
            # Upload universal cover photo/thumbnail if available
            if cover_path and os.path.isfile(cover_path):
                notify(58, "Applying universal cover thumbnail")
                _upload_cover_photo(page, cover_path)

            # Some accounts show a crop/cover step, others go directly to caption.
            caption_box = _caption_field(page)
            if not caption_box.count():
                notify(65, "Opening Reel details")
                _click_first_available(page, ("Next",), timeout=30_000)
                caption_box = _caption_field(page)

            # Check cover on details screen if not set yet
            if cover_path and os.path.isfile(cover_path):
                _upload_cover_photo(page, cover_path)

            caption_box.wait_for(state="visible", timeout=30_000)
            _fill_caption(page, caption_box, caption)
            notify(75, "Ready to share")
            _click_first_available(page, ("Share",), timeout=30_000)
            share_clicked = True
            notify(85, "Instagram is publishing the Reel")
            confirmation = page.get_by_text(
                re.compile(
                    r"(your (reel|post) has been shared|(reel|post)( has been)? shared)",
                    re.I,
                )
            ).first
            try:
                confirmation.wait_for(state="visible", timeout=120_000)
            except TimeoutError:
                directory = _save_diagnostics(context, page, "manual-verification", console_lines)
                logger.warning("[Instagram] Share confirmation was not observed; diagnostics saved to %s", directory)
                notify(100, "Share was clicked; confirmation was not visible")
                return InstagramUploadResult("needs_manual_verification")
            notify(100, "Instagram confirmed the Reel was shared")
            return InstagramUploadResult("completed", page.url if "/reel/" in page.url else None)
    except InstagramUploadError:
        raise
    except (TimeoutError, PlaywrightError) as exc:
        detail = f"Browser upload failed: {exc}"
        blocking = _blocking_status(page) if page is not None else None
        if context is not None and page is not None:
            directory = _save_diagnostics(context, page, "upload-failure", console_lines)
            detail += f" Diagnostics saved to {directory}."
        if blocking:
            raise InstagramUploadError(f"{blocking[1]} {detail}", status=blocking[0], share_clicked=share_clicked) from exc
        lower = str(exc).lower()
        if "429" in lower:
            raise InstagramUploadError(f"Instagram rate-limited this upload. {detail}", status="rate_limited", share_clicked=share_clicked) from exc
        transient = isinstance(exc, TimeoutError) or any(token in lower for token in (
            "net::", "connection reset", "connection refused", "connection timed out",
            "target page, context or browser has been closed", "browser has been closed", "503", "502",
        ))
        raise InstagramUploadError(detail, retryable=transient and not share_clicked, share_clicked=share_clicked) from exc
    except Exception as exc:
        detail = f"Unexpected Instagram automation failure: {exc}"
        if context is not None and page is not None:
            directory = _save_diagnostics(context, page, "unexpected-failure", console_lines)
            detail += f" Diagnostics saved to {directory}."
        raise InstagramUploadError(detail, retryable=not share_clicked, share_clicked=share_clicked) from exc
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
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
