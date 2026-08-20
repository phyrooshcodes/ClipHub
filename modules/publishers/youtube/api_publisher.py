"""Official YouTube Data API v3 Direct Publisher.

Provides 100% reliable, direct HTTP background uploads using official Google OAuth2.
No headless browsers, zero selector breakages, zero 2FA interception errors.
"""

from __future__ import annotations

import os
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Callable

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

CREDENTIALS_DIR = Path(__file__).parent.parent.parent / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "youtube_token.json"
CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "client_secrets.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
]


def has_oauth_token() -> bool:
    """Return True if a valid or refreshable OAuth token exists."""
    if not TOKEN_FILE.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        return creds and (creds.valid or creds.refresh_token is not None)
    except Exception:
        return False


def get_authenticated_service():
    """Build and return an authenticated YouTube Data API v3 service."""
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"OAuth token not found at {TOKEN_FILE}. Please connect your YouTube account via Google OAuth.")
    
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logger.info("[YouTube API] Refreshing expired OAuth access token...")
            creds.refresh(Request())
            CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("YouTube OAuth token is invalid and cannot be refreshed. Please re-authenticate.")
            
    return build("youtube", "v3", credentials=creds)


def get_channel_info_api() -> dict:
    """Retrieve authenticated channel metadata using YouTube Data API v3."""
    youtube = get_authenticated_service()
    res = youtube.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()
    items = res.get("items", [])
    if not items:
        return {}
    
    item = items[0]
    snippet = item.get("snippet", {})
    return {
        "channel_id": item.get("id"),
        "name": snippet.get("title", ""),
        "handle": snippet.get("customUrl", ""),
        "description": snippet.get("description", ""),
        "avatar": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
        "subscribers": item.get("statistics", {}).get("subscriberCount", "0"),
        "updated_at": time.time(),
        "auth_type": "oauth_api"
    }


def upload_video_via_api(
    video_path: str,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    thumbnail_path: Optional[str] = None,
    category_id: str = "22",
    privacy_status: str = "private",
    publish_at: Optional[datetime] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """Upload a video directly via YouTube Data API v3 with resumable chunking and scheduling."""
    path = Path(video_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Video file not found: {path}")

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        }
    }

    # If scheduled publishing is requested (e.g. 12:00 AM)
    if publish_at is not None:
        body["status"]["privacyStatus"] = "private"
        if publish_at.tzinfo is None:
            utc_dt = publish_at.astimezone(timezone.utc)
        else:
            utc_dt = publish_at.astimezone(timezone.utc)
        body["status"]["publishAt"] = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"[YouTube API] Scheduling video for {body['status']['publishAt']}")

    if progress_callback:
        progress_callback(10, "Initializing YouTube API resumable upload session...")

    media = MediaFileUpload(
        str(path),
        mimetype="video/*",
        chunksize=5 * 1024 * 1024,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    file_size = path.stat().st_size
    logger.info(f"[YouTube API] Uploading {path.name} ({file_size / (1024*1024):.1f} MB) via official API...")

    while response is None:
        status, response = request.next_chunk()
        if status:
            progress_pct = int(10 + (status.progress() * 80))
            msg = f"Uploading: {int(status.progress() * 100)}%"
            logger.info(f"[YouTube API] {msg}")
            if progress_callback:
                progress_callback(progress_pct, msg)

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"Upload failed. API response: {response}")

    short_url = f"https://www.youtube.com/shorts/{video_id}"
    logger.info(f"[YouTube API] ✅ Video successfully uploaded! Video ID: {video_id} (URL: {short_url})")

    # Set custom thumbnail if provided
    if thumbnail_path and Path(thumbnail_path).is_file():
        try:
            if progress_callback:
                progress_callback(92, "Setting video thumbnail...")
            thumb_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            logger.info(f"[YouTube API] Thumbnail applied successfully for {video_id}")
        except Exception as t_err:
            logger.warning(f"[YouTube API] Setting thumbnail note: {t_err}")

    if progress_callback:
        progress_callback(100, "YouTube upload complete!")

    return {
        "status": "scheduled" if publish_at else "completed",
        "success": True,
        "video_id": video_id,
        "url": short_url,
        "scheduled_time": body["status"].get("publishAt"),
        "title": title,
        "timestamp": time.time(),
        "auth_type": "oauth_api"
    }
