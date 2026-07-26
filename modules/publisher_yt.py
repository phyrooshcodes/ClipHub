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

from modules.publishers.youtube.publisher import (
    post_youtube_video,
    connect_youtube_playwright,
    is_youtube_connected as is_playwright_connected,
    disconnect_youtube as disconnect_playwright,
    get_youtube_channel_info,
    inspect_youtube_channel,
    YouTubeUploadResult,
    YouTubeUploadError,
)

logger = logging.getLogger(__name__)

CREDENTIALS_DIR = Path(__file__).parent.parent / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "youtube_token.json"
CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def is_youtube_connected() -> bool:
    """Return True if YouTube persistent browser session or OAuth token exists."""
    return is_playwright_connected() or TOKEN_FILE.exists()


def has_client_secrets() -> bool:
    """Return True if client_secrets.json exists."""
    return CLIENT_SECRETS_FILE.exists()


def disconnect_youtube():
    """Remove YouTube browser session and OAuth token.json."""
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
    Backward-compatible entry point to post a video/Short to YouTube.
    Automatically schedules the video for 12:00 AM (00:00).
    """
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


# OAuth Legacy Helpers for backward compatibility
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
