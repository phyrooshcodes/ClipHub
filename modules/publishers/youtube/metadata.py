"""YouTube Studio metadata entry handler (title, description, tags, thumbnail, audience)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from playwright.sync_api import Page, TimeoutError, Error as PlaywrightError

from modules.publishers.youtube.selectors import (
    TITLE_TEXTBOX_SELECTORS,
    DESCRIPTION_TEXTBOX_SELECTORS,
    THUMBNAIL_INPUT_SELECTORS,
    NOT_MADE_FOR_KIDS_SELECTORS,
    SHOW_MORE_BUTTON_SELECTORS,
    TAGS_INPUT_SELECTORS,
)

logger = logging.getLogger(__name__)


def _set_contenteditable_text(page: Page, selectors: tuple[str, ...], text: str) -> bool:
    """Set text in a Polymer contenteditable textbox reliably."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                locator.click(timeout=3_000)
                # Clear existing text
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.wait_for_timeout(200)
                
                # Fill text using fill or keyboard
                try:
                    locator.fill(text, timeout=3_000)
                except PlaywrightError:
                    # Fallback to direct DOM innerText assignment + input event dispatch
                    page.evaluate(
                        """([sel, val]) => {
                            const el = document.querySelector(sel);
                            if (el) {
                                el.innerText = val;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }""",
                        [selector, text],
                    )
                return True
        except PlaywrightError:
            pass
    return False


def fill_metadata(
    page: Page,
    title: str,
    description: str,
    tags: list[str] | None = None,
    thumbnail_path: str | None = None,
) -> None:
    """Fill all metadata fields in YouTube Studio upload modal."""
    safe_title = (title or "Untitled Reel")[:100]
    safe_description = (description or "")[:5_000]

    # Fill Title
    if not _set_contenteditable_text(page, TITLE_TEXTBOX_SELECTORS, safe_title):
        logger.warning("[YouTube] Could not set title using primary selectors; attempting fallback...")

    # Fill Description
    if safe_description:
        _set_contenteditable_text(page, DESCRIPTION_TEXTBOX_SELECTORS, safe_description)

    # Upload Thumbnail if provided
    if thumbnail_path and os.path.isfile(thumbnail_path):
        try:
            thumb_path = str(Path(thumbnail_path).resolve())
            for selector in THUMBNAIL_INPUT_SELECTORS:
                thumb_input = page.locator(selector).first
                if thumb_input.count():
                    thumb_input.set_input_files(thumb_path, timeout=5_000)
                    logger.info("[YouTube] Thumbnail uploaded.")
                    break
        except Exception as exc:
            logger.warning("[YouTube] Thumbnail upload skipped or failed: %s", exc)

    # Select "No, it's not made for kids" (Mandatory)
    kids_selected = False
    for selector in NOT_MADE_FOR_KIDS_SELECTORS:
        try:
            radio = page.locator(selector).first
            if radio.count() and radio.is_visible():
                radio.click(timeout=3_000)
                kids_selected = True
                break
        except PlaywrightError:
            pass

    if not kids_selected:
        # Fallback click by text
        try:
            page.get_by_text("No, it's not made for kids", exact=False).first.click(timeout=3_000)
        except Exception:
            logger.warning("[YouTube] Could not explicitly click 'Not Made for Kids' option.")

    # Fill Tags if provided
    if tags:
        try:
            # Expand Show More
            for btn_sel in SHOW_MORE_BUTTON_SELECTORS:
                btn = page.locator(btn_sel).first
                if btn.count() and btn.is_visible():
                    btn.click(timeout=3_000)
                    page.wait_for_timeout(500)
                    break
            
            tags_str = ", ".join(tags)
            for tag_sel in TAGS_INPUT_SELECTORS:
                tag_input = page.locator(tag_sel).first
                if tag_input.count() and tag_input.is_visible():
                    tag_input.fill(tags_str, timeout=3_000)
                    break
        except Exception as exc:
            logger.warning("[YouTube] Tags entry skipped: %s", exc)

    logger.info("[YouTube] Metadata completed.")
