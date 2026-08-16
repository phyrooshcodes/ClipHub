"""Small, explicit security boundary for optional LAN operation."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import WebSocket, Request


def lan_mode_enabled() -> bool:
    return os.environ.get("CLIPHUB_HOST", "127.0.0.1") == "0.0.0.0"


def lan_token() -> str:
    return os.environ.get("CLIPHUB_LAN_TOKEN", "")


def is_loopback(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


def http_is_authorized(request: Request) -> bool:
    """Require LAN token for non-loopback HTTP clients when LAN mode is active."""
    if not lan_mode_enabled() or is_loopback(request.client.host if request.client else None):
        return True
    token = lan_token()
    if not token:
        return True
    
    # Check headers, query params, or cookie
    auth_hdr = request.headers.get("authorization", "")
    if auth_hdr.startswith("Bearer ") and auth_hdr[7:] == token:
        return True
    if request.headers.get("x-lan-token") == token:
        return True
    if request.cookies.get("cliphub_lan_token") == token:
        return True
    if request.query_params.get("token") == token:
        return True
    return False


def websocket_is_authorized(websocket: WebSocket) -> bool:
    """Require the LAN token and reject browser cross-origin WebSockets."""
    origin = websocket.headers.get("origin")
    request_host = (websocket.headers.get("host") or "").split(":", 1)[0].strip("[]")
    if origin:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host != request_host.lower() and not (is_loopback(origin_host) and is_loopback(request_host)):
            return False

    if not lan_mode_enabled() or is_loopback(websocket.client.host if websocket.client else None):
        return True

    supplied = websocket.query_params.get("token") or websocket.cookies.get("cliphub_lan_token")
    return bool(lan_token()) and supplied == lan_token()
