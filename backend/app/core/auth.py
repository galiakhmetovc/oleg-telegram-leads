from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class AuthSession:
    username: str
    expires_at: int


def credentials_are_valid(*, username: str, password: str, settings: Settings) -> bool:
    return hmac.compare_digest(username, settings.auth_username) and hmac.compare_digest(
        password,
        settings.auth_password,
    )


def create_session_token(*, username: str, settings: Settings, now: int | None = None) -> str:
    current_time = int(now if now is not None else time.time())
    expires_at = current_time + settings.auth_session_ttl_seconds
    payload = f"{username}:{expires_at}"
    payload_part = _b64encode(payload.encode())
    signature_part = _signature(payload_part, settings.auth_session_secret)
    return f"{payload_part}.{signature_part}"


def verify_session_token(token: str | None, *, settings: Settings, now: int | None = None) -> AuthSession | None:
    if not token or "." not in token:
        return None
    payload_part, signature_part = token.split(".", 1)
    expected_signature = _signature(payload_part, settings.auth_session_secret)
    if not hmac.compare_digest(signature_part, expected_signature):
        return None
    try:
        payload = _b64decode(payload_part).decode()
        username, expires_at_text = payload.rsplit(":", 1)
        expires_at = int(expires_at_text)
    except (ValueError, UnicodeDecodeError):
        return None
    if expires_at < int(now if now is not None else time.time()):
        return None
    if not hmac.compare_digest(username, settings.auth_username):
        return None
    return AuthSession(username=username, expires_at=expires_at)


def _signature(payload_part: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload_part.encode(), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode())
