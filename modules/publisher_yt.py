# ============================================================
# publisher_yt.py — YouTube Publisher Entry Point & Bridge
# Purpose: Exposes unified YouTube publishing methods backed by
#          the automated Playwright YouTube Studio publisher.
# ============================================================

import os
import json
import logging
from pathlib import Path
from typing import Optional, Callable

from modules.publishers.youtube.api_publisher import (
    has_oauth_token,
    get_channel_info_api,
    upload_video_via_api,
    TOKEN_FILE,
    CLIENT_SECRETS_FILE,
    SCOPES,
)
from modules.publishers.youtube.publisher import (
    post_youtube_video,
    connect_youtube_playwright,
    is_youtube_connected as is_playwright_connected,
    disconnect_youtube as disconnect_playwright,
    get_youtube_channel_info as get_browser_channel_info,
    inspect_youtube_channel,
    YouTubeUploadResult,
    YouTubeUploadError,
)

logger = logging.getLogger(__name__)

CREDENTIALS_DIR = Path(__file__).parent.parent / "credentials"


def is_youtube_connected() -> bool:
    """Return True if YouTube OAuth token or persistent browser session exists."""
    return has_oauth_token() or is_playwright_connected()


def has_client_secrets() -> bool:
    """Return True if client_secrets.json exists."""
    return CLIENT_SECRETS_FILE.exists()


def get_youtube_channel_info() -> dict:
    """Return channel metadata from official API if available, else browser profile."""
    if has_oauth_token():
        try:
            return get_channel_info_api()
        except Exception as e:
            logger.warning(f"[YouTube] API channel info fetch note: {e}")
    return get_browser_channel_info()


def disconnect_youtube():
    """Remove YouTube OAuth token and browser session."""
    disconnect_playwright()
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    logger.info("[YouTube] Channel disconnected.")


def post_youtube_short(
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: Optional[str] = None,
    tags: Optional[list[str]] = None,
    progress: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Publish a video/Short to YouTube.
    Prioritizes official YouTube Data API v3 if OAuth token exists, else browser automation.
    Automatically schedules for 12:00 AM (00:00).
    """
    if has_oauth_token():
        from modules.publishers.youtube.scheduler import calculate_schedule_target
        target_dt, date_str, time_str = calculate_schedule_target()
        res = upload_video_via_api(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=thumbnail_path,
            publish_at=target_dt,
            progress_callback=progress,
        )
        return res["url"]

    result = post_youtube_video(
        video_path=video_path,
        title=title,
        description=description,
        thumbnail_path=thumbnail_path,
        tags=tags,
        progress=progress,
    )
    url = result.video_url or f"https://studio.youtube.com/ (Scheduled for {result.scheduled_time})"
    logger.info("[YouTube] Scheduled upload outcome: %s (URL: %s)", result.status, url)
    return url


# OAuth Helpers for Google Cloud App Flow
def get_youtube_flow(redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"):
    from google_auth_oauthlib.flow import Flow
    if not CLIENT_SECRETS_FILE.exists():
        raise FileNotFoundError("client_secrets.json is missing in credentials/ directory.")
    return Flow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), scopes=SCOPES, redirect_uri=redirect_uri)


def connect_youtube_with_code(code: str, redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob") -> bool:
    try:
        flow = get_youtube_flow(redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("[YouTube] Successfully connected YouTube channel via OAuth.")
        return True
    except Exception as e:
        logger.error(f"[YouTube] Exchange code failed: {e}")
        raise RuntimeError(f"Failed to authenticate YouTube: {e}")
