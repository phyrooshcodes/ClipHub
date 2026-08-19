"""YouTube Studio upload initiation and file transfer handler."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from playwright.sync_api import Page, TimeoutError, Error as PlaywrightError

from modules.publishers.youtube.selectors import (
    CREATE_BUTTON_SELECTORS,
    UPLOAD_ITEM_SELECTORS,
    DIRECT_UPLOAD_BUTTON_SELECTORS,
    FILE_INPUT_SELECTORS,
    TITLE_TEXTBOX_SELECTORS,
)

logger = logging.getLogger(__name__)


def _click_any(page: Page, selectors: tuple[str, ...], timeout: int = 10_000) -> bool:
    """Attempt clicking the first matching element from a tuple of selectors."""
    deadline = time.monotonic() + (timeout / 1000.0)
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible() and locator.is_enabled():
                    locator.click(timeout=2_000)
                    return True
            except PlaywrightError:
                pass
        page.wait_for_timeout(300)
    return False


def _find_file_input(page: Page, timeout: int = 15_000):
    """Locate the attached file input for uploading the video."""
    deadline = time.monotonic() + (timeout / 1000.0)
    while time.monotonic() < deadline:
        for selector in FILE_INPUT_SELECTORS:
            locator = page.locator(selector).first
            if locator.count():
                return locator
        page.wait_for_timeout(300)
    raise TimeoutError("Could not locate YouTube Studio file input for video upload.")


def get_active_channel_name(page: Page) -> str:
    """Read the currently active channel name from YouTube Studio navigation or header."""
    for sel in (
        "#entity-name",
        "#channel-name",
        "ytcp-navigation-drawer #entity-name",
        "ytcp-header #channel-name",
        "ytcp-header #account-name",
        "ytcp-app-header #entity-name",
    ):
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                txt = el.inner_text().strip()
                if txt:
                    return txt
        except Exception:
            pass
    return ""


def ensure_correct_channel(page: Page, channel_id: str | None = None, channel_name: str | None = None) -> str:
    """Verify and switch to the target YouTube channel if needed."""
    if not channel_id and not channel_name:
        return get_active_channel_name(page)

    logger.info(f"[YouTube] Verifying channel context (Target: Name='{channel_name}', ID='{channel_id}')...")

    # 1. First navigate directly to the target channel Studio URL
    target_url = f"https://studio.youtube.com/channel/{channel_id}" if channel_id else "https://studio.youtube.com/"
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(2500)
    except Exception as e:
        logger.warning(f"[YouTube] Initial studio navigation warning: {e}")

    active_name = get_active_channel_name(page)
    if channel_name and active_name and (channel_name.lower() in active_name.lower() or active_name.lower() in channel_name.lower()):
        logger.info(f"[YouTube] ✅ Confirmed active channel: '{active_name}'")
        return active_name

    # 2. If active channel name does not match, use YouTube Channel Switcher
    if (channel_name and active_name and channel_name.lower() not in active_name.lower()) or (not active_name):
        logger.info(f"[YouTube] Current channel '{active_name}' != target '{channel_name}'. Attempting Channel Switcher...")
        try:
            import urllib.parse
            next_url = f"https://studio.youtube.com/channel/{channel_id}" if channel_id else "https://studio.youtube.com/"
            switcher_url = f"https://www.youtube.com/channel_switcher?next={urllib.parse.quote(next_url)}"
            page.goto(switcher_url, wait_until="domcontentloaded", timeout=25_000)
            page.wait_for_timeout(3000)

            switched = False
            # Look for channel by name on switcher page
            if channel_name:
                for sel in (
                    f"ytd-account-item-renderer:has-text('{channel_name}')",
                    f"#channel-title:has-text('{channel_name}')",
                    f"tp-yt-paper-item:has-text('{channel_name}')",
                    f"[role='link']:has-text('{channel_name}')",
                    f"a:has-text('{channel_name}')",
                ):
                    try:
                        link = page.locator(sel).first
                        if link.count() and link.is_visible():
                            link.click(timeout=4000)
                            switched = True
                            logger.info(f"[YouTube] Clicked target channel '{channel_name}' on switcher via '{sel}'")
                            page.wait_for_timeout(4000)
                            break
                    except Exception:
                        pass

            if not switched and channel_id:
                for sel in (
                    f"a[href*='{channel_id}']",
                    f"ytd-account-item-renderer:has-text('{channel_id}')",
                ):
                    try:
                        link = page.locator(sel).first
                        if link.count() and link.is_visible():
                            link.click(timeout=4000)
                            switched = True
                            logger.info(f"[YouTube] Clicked target channel ID '{channel_id}' on switcher")
                            page.wait_for_timeout(4000)
                            break
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning(f"[YouTube] Channel switcher step note: {exc}")

    # 3. Ensure we are back on Studio
    if "studio.youtube.com" not in page.url:
        studio_target = f"https://studio.youtube.com/channel/{channel_id}" if channel_id else "https://studio.youtube.com/"
        page.goto(studio_target, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2500)

    # 4. If still not on the right channel, try Studio in-page Account Switcher menu
    active_name = get_active_channel_name(page)
    if channel_name and active_name and channel_name.lower() not in active_name.lower():
        logger.info(f"[YouTube] Attempting in-page Studio account switch from '{active_name}' to '{channel_name}'...")
        try:
            avatar_btn = page.locator("#avatar-btn, ytcp-header #avatar-btn, button#avatar-btn, ytcp-icon-button#avatar-btn").first
            if avatar_btn.count() and avatar_btn.is_visible():
                avatar_btn.click(timeout=3000)
                page.wait_for_timeout(1000)
                
                switch_item = page.locator("ytcp-text-menu-item:has-text('Switch account'), tp-yt-paper-item:has-text('Switch account'), [aria-label*='Switch account']").first
                if switch_item.count() and switch_item.is_visible():
                    switch_item.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    
                    target_entry = page.locator(f"ytcp-text-menu-item:has-text('{channel_name}'), tp-yt-paper-item:has-text('{channel_name}'), ytd-account-item-renderer:has-text('{channel_name}')").first
                    if target_entry.count() and target_entry.is_visible():
                        target_entry.click(timeout=3000)
                        logger.info(f"[YouTube] Selected '{channel_name}' from Studio Switch Account menu.")
                        page.wait_for_timeout(4000)
        except Exception as e:
            logger.warning(f"[YouTube] In-page Studio account switch note: {e}")

    active_name = get_active_channel_name(page)
    logger.info(f"[YouTube] Active channel context: '{active_name or 'Default'}' (Target: '{channel_name or channel_id}')")
    return active_name


def initiate_upload(page: Page, video_path: str, channel_id: str | None = None, channel_name: str | None = None) -> None:
    """Open YouTube Studio, switch to target channel, and upload the video file."""
    logger.info("[YouTube]\nLaunching Studio...")
    
    ensure_correct_channel(page, channel_id=channel_id, channel_name=channel_name)

    # Check for authentication redirect
    if "accounts.google.com" in page.url:
        raise RuntimeError("YouTube Studio requires authentication. Please log in to YouTube Studio first.")

    logger.info("[YouTube] Locating video upload interface...")
    
    # 1. Ensure the upload dialog is open
    deadline = time.monotonic() + 35.0
    while time.monotonic() < deadline:
        select_btn = page.locator("#select-files-button, ytcp-button#select-files-button, ytcp-button:has-text('Select files'), ytcp-uploads-dialog").first
        if select_btn.count() and select_btn.is_visible():
            break
            
        # Attempt opening create / upload dialog
        if _click_any(page, CREATE_BUTTON_SELECTORS, timeout=3_000):
            page.wait_for_timeout(1_000)
            _click_any(page, UPLOAD_ITEM_SELECTORS, timeout=5_000)
        else:
            _click_any(page, DIRECT_UPLOAD_BUTTON_SELECTORS, timeout=3_000)

        page.wait_for_timeout(1_000)

    # 2. Upload video file via file chooser or direct input
    resolved_path = str(Path(video_path).resolve())
    logger.info(f"[YouTube] Uploading video file ({resolved_path})...")
    uploaded = False

    # Strategy A: Use expect_file_chooser clicking "Select files"
    try:
        select_btn = page.locator("#select-files-button, ytcp-button#select-files-button, ytcp-button:has-text('Select files')").first
        if select_btn.count() and select_btn.is_visible():
            with page.expect_file_chooser(timeout=8_000) as fc_info:
                select_btn.click(timeout=4_000)
            file_chooser = fc_info.value
            file_chooser.set_files(resolved_path)
            uploaded = True
            logger.info("[YouTube] File set via Playwright FileChooser successfully.")
    except Exception as e:
        logger.info(f"[YouTube] FileChooser fallback: {e}")

    # Strategy B: Direct input targeting inside active dialog or last input
    if not uploaded:
        for selector in (
            "ytcp-uploads-dialog input[type='file']",
            "#select-files-button input[type='file']",
            "input[type='file'][name='Filedata']",
            "input[type='file']"
        ):
            try:
                inputs = page.locator(selector)
                cnt = inputs.count()
                if cnt > 0:
                    inputs.nth(cnt - 1).set_input_files(resolved_path, timeout=10_000)
                    uploaded = True
                    logger.info(f"[YouTube] File set via input selector '{selector}' successfully.")
                    break
            except Exception as ex:
                logger.debug(f"[YouTube] Selector '{selector}' failed: {ex}")

    if not uploaded:
        raise TimeoutError("Could not upload video file to YouTube Studio upload dialog.")

    logger.info("[YouTube] Processing upload...")
    
    # Wait for the metadata form (title box) to become attached & visible
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        for selector in TITLE_TEXTBOX_SELECTORS:
            title_box = page.locator(selector).first
            if title_box.count() and title_box.is_visible():
                logger.info("[YouTube] Upload dialog ready for metadata entry.")
                return
        page.wait_for_timeout(500)
        
    raise TimeoutError("Timed out waiting for YouTube Studio metadata upload dialog to appear.")


class UploadNetworkTelemetry:
    """Tracks low-level network HTTP upload requests and responses to upload.youtube.com."""

    def __init__(self, page: Page):
        self.page = page
        self.upload_finished: bool = False
        self.last_status: int | None = None
        self._setup_listeners()

    def _setup_listeners(self):
        def on_response(response):
            url = response.url.lower()
            if "upload.youtube.com" in url or "upload/resumable" in url or "resumableupload" in url:
                status = response.status
                self.last_status = status
                
                req_url = response.request.url.lower()
                # Ignore the initial session creation request which doesn't upload the file body
                if "upload_id=" in req_url and status in (200, 201):
                    self.upload_finished = True
                    logger.info(f"[Network Telemetry] HTTP {status} OK received from YouTube upload endpoint.")

        self.page.on("response", on_response)


def wait_for_upload_completion(page: Page, telemetry: UploadNetworkTelemetry | None = None, timeout: int | None = None) -> None:
    """Wait until YouTube Studio confirms that the raw video file upload transfer is 100% complete across the network."""
    if timeout is None:
        timeout = int(os.environ.get("CLIPHUB_UPLOAD_TIMEOUT_S", "300")) * 1000
        
    logger.info("[YouTube] Waiting for file upload transfer across network to complete...")
    deadline = time.monotonic() + (timeout / 1000.0)
    
    last_logged_text = ""
    while time.monotonic() < deadline:
        try:
            progress_el = page.locator("ytcp-video-upload-progress .progress-label, ytcp-uploads-dialog .progress-label").first
            if progress_el.count() and progress_el.is_visible():
                text = progress_el.inner_text().strip()
                text_lower = text.lower()
                
                if text and text != last_logged_text:
                    logger.info(f"[YouTube] Current Transfer Status: {text.splitlines()[0]}")
                    last_logged_text = text

                # Strict checking: Only explicitly positive completion keywords
                explicit_complete = any(kw in text_lower for kw in ("upload complete", "processing", "checks", "sd complete", "hd complete", "saved as draft"))
                
                if explicit_complete:
                    logger.info(f"[YouTube] File upload transfer complete! Final Status: {text.splitlines()[0] if text else 'Complete'}")
                    return
        except PlaywrightError:
            pass
        page.wait_for_timeout(1000)

    logger.warning(f"[YouTube] Upload wait timeout reached ({timeout/1000.0}s). Proceeding with schedule...")
