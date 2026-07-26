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


def initiate_upload(page: Page, video_path: str, channel_id: str | None = None) -> None:
    """Open YouTube Studio, initiate file chooser, and upload the video file."""
    logger.info("[YouTube]\nLaunching Studio...")
    
    if channel_id:
        logger.info(f"[YouTube] Ensuring correct channel context for {channel_id}...")
        # First go to channel switcher to force the session to the correct channel
        page.goto(f"https://www.youtube.com/channel_switcher?next=https%3A%2F%2Fstudio.youtube.com%2F", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        
        # If the channel is listed, click it. If not, it means we might already be on studio or it's not a switcher page
        try:
            channel_link = page.locator(f'a[href*="{channel_id}"]').first
            if channel_link.count() and channel_link.is_visible():
                channel_link.click(timeout=5000)
                page.wait_for_timeout(3000)
        except Exception:
            pass

    target_url = "https://studio.youtube.com/"
    page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
    
    try:
        page.wait_for_selector("ytcp-app, ytcp-header, #create-icon", timeout=15_000)
    except Exception:
        pass

    # Check for authentication redirect
    if "accounts.google.com" in page.url:
        raise RuntimeError("YouTube Studio requires authentication. Please log in to YouTube Studio first.")

    logger.info("[YouTube] Uploading video...")
    
    file_input = page.locator('input[type="file"]').first
    if file_input.count() == 0:
        opened = _click_any(page, CREATE_BUTTON_SELECTORS, timeout=10_000)
        if opened:
            page.wait_for_timeout(1_200)
            _click_any(page, UPLOAD_ITEM_SELECTORS, timeout=8_000)
        else:
            _click_any(page, DIRECT_UPLOAD_BUTTON_SELECTORS, timeout=10_000)

        file_input = _find_file_input(page, timeout=25_000)

    file_input.set_input_files(str(Path(video_path).resolve()), timeout=30_000)

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
                if status in (200, 201):
                    self.upload_finished = True
                    logger.info(f"[Network Telemetry] HTTP {status} OK received from YouTube upload endpoint.")

        self.page.on("response", on_response)


def wait_for_upload_completion(page: Page, telemetry: UploadNetworkTelemetry | None = None, timeout: int | None = None) -> None:
    """Wait until YouTube Studio confirms that the raw video file upload transfer is 100% complete across the network."""
    if timeout is None:
        timeout = int(os.environ.get("OBSCURA_UPLOAD_TIMEOUT_S", "300")) * 1000
        
    logger.info("[YouTube] Waiting for file upload transfer across network to complete...")
    deadline = time.monotonic() + (timeout / 1000.0)
    
    last_logged_text = ""
    while time.monotonic() < deadline:
        # Check network telemetry signal first
        if telemetry and telemetry.upload_finished:
            logger.info("[YouTube] Network Telemetry confirmed 100% video payload transfer.")
            return

        try:
            progress_el = page.locator("ytcp-video-upload-progress, .progress-label, ytcp-uploads-dialog-header, .ytcp-uploads-dialog").first
            if progress_el.count():
                text = progress_el.inner_text().strip()
                text_lower = text.lower()
                
                if text and text != last_logged_text and ("uploading" in text_lower or "%" in text_lower):
                    logger.info(f"[YouTube] Current Transfer Status: {text.splitlines()[0]}")
                    last_logged_text = text

                # Check for completion keywords or absence of 'uploading' + '%'
                if any(kw in text_lower for kw in ("upload complete", "processing", "checks", "sd complete", "hd complete")) or ("uploading" not in text_lower and "%" not in text_lower):
                    logger.info(f"[YouTube] File upload transfer complete! Final Status: {text.splitlines()[0] if text else 'Complete'}")
                    return
        except PlaywrightError:
            pass
        page.wait_for_timeout(1000)

    logger.warning(f"[YouTube] Upload wait timeout reached ({timeout/1000.0}s). Proceeding with schedule...")
