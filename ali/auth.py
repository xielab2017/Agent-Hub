"""Optional password auth for remote access."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from http.cookies import SimpleCookie
from typing import Optional

from .config import AUTH_PASSWORD, AUTH_PASSWORD_SHA256

COOKIE_NAME = "hermes_ali_token"
_TOKENS: dict[str, float] = {}  # token -> expiry epoch
_TOKEN_TTL = 60 * 60 * 24 * 7  # 7 days


def auth_required() -> bool:
    return bool(AUTH_PASSWORD or AUTH_PASSWORD_SHA256)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str) -> bool:
    if AUTH_PASSWORD:
        return hmac.compare_digest(_hash_password(password), _hash_password(AUTH_PASSWORD))
    if AUTH_PASSWORD_SHA256:
        return hmac.compare_digest(_hash_password(password), AUTH_PASSWORD_SHA256)
    if not AUTH_PASSWORD and not AUTH_PASSWORD_SHA256:
        return True
    return False


def issue_token() -> str:
    token = secrets.token_urlsafe(32)
    _TOKENS[token] = time.time() + _TOKEN_TTL
    # prune
    now = time.time()
    expired = [k for k, exp in _TOKENS.items() if exp < now]
    for k in expired:
        _TOKENS.pop(k, None)
    return token


def token_valid(token: Optional[str]) -> bool:
    if not auth_required():
        return True
    if not token:
        return False
    exp = _TOKENS.get(token)
    if exp is None or exp < time.time():
        _TOKENS.pop(token, None)
        return False
    return True


def extract_token(handler) -> Optional[str]:
    # Authorization: Bearer <token>
    auth = handler.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # Cookie
    raw = handler.headers.get("Cookie") or ""
    if raw:
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:  # noqa: BLE001
            return None
        morsel = cookie.get(COOKIE_NAME)
        if morsel:
            return morsel.value
    # Query ?token=
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(handler.path).query)
    if "token" in qs and qs["token"]:
        return qs["token"][0]
    return None


def is_authenticated(handler) -> bool:
    if not auth_required():
        return True
    return token_valid(extract_token(handler))
