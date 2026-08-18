"""Small, explicit security boundary for optional LAN operation."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import WebSocket, Request


def lan_mode_enabled(app_state=None) -> bool:
    if app_state and isinstance(getattr(app_state, "host", None), str):
        return getattr(app_state, "host") == "0.0.0.0"
    return os.environ.get("CLIPHUB_HOST", "127.0.0.1") == "0.0.0.0"


def lan_token(app_state=None) -> str:
    if app_state and isinstance(getattr(app_state, "lan_token", None), str):
        return str(app_state.lan_token).strip()
    return os.environ.get("CLIPHUB_LAN_TOKEN", "").strip()


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    clean_host = host.split("%")[0].lower()  # Strip IPv6 scope ID if present
    return clean_host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _extract_token(headers: dict, cookies: dict, query_params: dict) -> str | None:
    # 1. X-ClipHub-Token or x-lan-token header
    for h in ("x-cliphub-token", "x-lan-token"):
        val = headers.get(h)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    # 2. Authorization: Bearer <token>
    auth = headers.get("authorization", "")
    if auth and auth.startswith("Bearer "):
        val = auth[7:].strip()
        if val:
            return val
    # 3. Cookie
    cookie_val = cookies.get("cliphub_lan_token")
    if cookie_val and isinstance(cookie_val, str) and cookie_val.strip():
        return cookie_val.strip()
    # 4. Query param
    q_val = query_params.get("token")
    if q_val and isinstance(q_val, str) and q_val.strip():
        return q_val.strip()
    return None


def http_is_authorized(request: Request) -> bool:
    """Require LAN token for non-loopback HTTP clients when LAN mode is active."""
    app_state = getattr(request.app, "state", None) if hasattr(request, "app") else None
    if not lan_mode_enabled(app_state) or is_loopback(request.client.host if request.client else None):
        return True
    token = lan_token(app_state)
    if not token:
        return True
    
    headers_lower = {k.lower(): v for k, v in request.headers.items()}
    supplied = _extract_token(headers_lower, request.cookies, request.query_params)
    if not supplied:
        return False
    import secrets
    return secrets.compare_digest(supplied, token)


def websocket_is_authorized(websocket: WebSocket) -> bool:
    """Require the LAN token and reject browser cross-origin WebSockets."""
    origin = websocket.headers.get("origin")
    request_host = (websocket.headers.get("host") or "").split(":", 1)[0].strip("[]")
    if origin:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host != request_host.lower() and not (is_loopback(origin_host) and is_loopback(request_host)):
            return False

    app_state = getattr(websocket.app, "state", None) if hasattr(websocket, "app") else None
    if is_loopback(websocket.client.host if websocket.client else None):
        return True

    token = lan_token(app_state)
    if not token:
        return True

    headers_lower = {k.lower(): v for k, v in websocket.headers.items()}
    supplied = _extract_token(headers_lower, websocket.cookies, websocket.query_params)
    if not supplied:
        return False
    import secrets
    return secrets.compare_digest(supplied, token)
