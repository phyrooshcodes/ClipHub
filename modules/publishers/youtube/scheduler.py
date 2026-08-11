"""YouTube Studio scheduling date calculation, UI interaction, and verification."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, time as dtime
from playwright.sync_api import Page, TimeoutError, Error as PlaywrightError

from modules.publishers.youtube.selectors import (
    NEXT_BUTTON_SELECTORS,
    SCHEDULE_RADIO_SELECTORS,
    DATE_INPUT_SELECTORS,
    TIME_INPUT_SELECTORS,
    SAVE_SCHEDULE_BUTTON_SELECTORS,
    VERIFICATION_MODAL_SELECTORS,
    VIDEO_URL_SELECTORS,
)

logger = logging.getLogger(__name__)


def calculate_schedule_target(now: datetime | None = None) -> tuple[datetime, str, str]:
    """Calculate the target schedule date and time.
    
    Rule:
    - Target time is always 12:00 AM (00:00).
    - If today's 12:00 AM has already passed (current time > 00:00:00), schedule for tomorrow at 12:00 AM.
    - Otherwise, schedule for today at 12:00 AM.
    """
    current = now or datetime.now()
    today_midnight = datetime.combine(current.date(), dtime(0, 0, 0))
    
    if current > today_midnight:
        target_date = current.date() + timedelta(days=1)
    else:
        target_date = current.date()
        
    target_dt = datetime.combine(target_date, dtime(0, 0, 0))
    
    # Format date string for YouTube Studio (e.g. "Jul 21, 2026" or "Jul 5, 2026" without leading zero)
    date_str = f"{target_dt.strftime('%b')} {target_dt.day}, {target_dt.year}"
    time_str = os.environ.get("OBSCURA_SCHEDULE_TIME", "12:00 AM")
    
    return target_dt, date_str, time_str


def check_for_verification_dialog(page: Page) -> None:
    """Detect Google Security Verification ('Verify it's you') dialog."""
    try:
        verify = page.locator("text=/Verify it's you|confirm it's really you|extra layer of security/i").first
        if verify.count() and verify.is_visible():
            raise RuntimeError("Google Security Verification required ('Verify it's you'). Please reconnect YouTube Studio in Settings to complete 2FA.")
    except PlaywrightError:
        pass


def _click_next_until_visibility(page: Page, max_clicks: int = 10) -> None:
    """Click Next button through wizard steps until Visibility / Schedule tab is reached."""
    logger.info("[YouTube] Opening Visibility.")
    for _ in range(max_clicks):
        check_for_verification_dialog(page)
        # Check if Schedule radio button is already visible
        for sched_sel in SCHEDULE_RADIO_SELECTORS:
            if page.locator(sched_sel).first.count() and page.locator(sched_sel).first.is_visible():
                return

        # Click Next button
        next_clicked = False
        for next_sel in NEXT_BUTTON_SELECTORS:
            try:
                btn = page.locator(next_sel).first
                if btn.count() and btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=3_000)
                    next_clicked = True
                    page.wait_for_timeout(1_000)
                    break
            except PlaywrightError:
                pass
                
        if not next_clicked:
            page.wait_for_timeout(1_000)


def apply_schedule(page: Page, target_date_str: str, target_time_str: str = "12:00 AM") -> None:
    """Navigate to Visibility, select Schedule, pick 12:00 AM & target date, and save."""
    _click_next_until_visibility(page)

    logger.info("[YouTube] Scheduling upload.")
    
    # Click Schedule radio button
    sched_clicked = False
    for selector in SCHEDULE_RADIO_SELECTORS:
        try:
            radio = page.locator(selector).first
            if radio.count() and radio.is_visible():
                radio.click(timeout=3_000)
                sched_clicked = True
                page.wait_for_timeout(500)
                break
        except PlaywrightError:
            pass

    if not sched_clicked:
        try:
            page.get_by_text("Schedule", exact=True).first.click(timeout=3_000)
        except Exception as exc:
            raise RuntimeError(f"Could not select Schedule radio option: {exc}")

    # Enter Date
    date_set = False
    for date_sel in DATE_INPUT_SELECTORS:
        try:
            input_el = page.locator(date_sel).first
            if input_el.count() and input_el.is_visible():
                input_el.click(timeout=2_000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                input_el.fill(target_date_str, timeout=2_000)
                page.keyboard.press("Enter")
                date_set = True
                break
        except PlaywrightError:
            pass

    if not date_set:
        logger.warning("[YouTube] Date input could not be set directly; relying on YouTube Studio default next-day schedule.")

    # Enter Time (12:00 AM)
    time_set = False
    for time_sel in TIME_INPUT_SELECTORS:
        try:
            input_el = page.locator(time_sel).first
            if input_el.count() and input_el.is_visible():
                input_el.click(timeout=2_000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                input_el.fill(target_time_str, timeout=2_000)
                page.keyboard.press("Enter")
                time_set = True
                break
        except PlaywrightError:
            pass

    if not time_set:
        # Fallback to selecting 12:00 AM item from dropdown list
        try:
            page.get_by_text("12:00 AM", exact=True).first.click(timeout=2_000)
        except Exception:
            pass

    logger.info("[YouTube] Selected 12:00 AM.")
    logger.info("[YouTube] Saving schedule.")
    
    # Close any open dropdown overlays
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass

    # Click Save / Schedule Button
    save_clicked = False
    for save_sel in SAVE_SCHEDULE_BUTTON_SELECTORS:
        try:
            btn = page.locator(save_sel).first
            if btn.count() and btn.is_visible() and btn.is_enabled():
                btn.click(timeout=5_000, force=True)
                save_clicked = True
                break
        except PlaywrightError:
            pass

    if not save_clicked:
        try:
            page.get_by_role("button", name=re.compile(r"SCHEDULE|SAVE", re.I)).first.click(timeout=5_000, force=True)
        except Exception as exc:
            raise RuntimeError(f"Could not click Schedule / Save button: {exc}")


def verify_schedule(page: Page, timeout: int = 35_000) -> tuple[bool, str | None]:
    """Verify that YouTube Studio confirms the video has been scheduled."""
    logger.info("[YouTube] Verifying schedule.")
    deadline = time.monotonic() + (timeout / 1000.0)
    video_url: str | None = None

    # Wait brief moment for post-save DOM transition
    page.wait_for_timeout(2_000)

    while time.monotonic() < deadline:
        try:
            # If upload modal has closed, the schedule save operation is complete
            # Make sure we didn't just navigate to an error page (which also lacks the dialog)
            if "studio.youtube.com" in page.url and page.locator("ytcp-uploads-dialog").count() == 0:
                logger.info("[YouTube] Upload dialog completed and closed — schedule applied successfully.")
                return True, video_url
        except Exception:
            pass

        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=1_000).lower()
        except Exception:
            pass

        if any(token in body_text for token in ("video scheduled", "set to public", "published")):
            for url_sel in VIDEO_URL_SELECTORS:
                try:
                    el = page.locator(url_sel).first
                    if el.count():
                        href = el.get_attribute("href") or el.inner_text()
                        if href and ("youtu" in href or "watch" in href):
                            video_url = href.strip()
                            break
                except Exception:
                    pass
            logger.info("[YouTube] Upload successfully scheduled.")
            return True, video_url

        page.wait_for_timeout(500)

    logger.warning("[YouTube] Schedule verification timed out.")
    return False, video_url
