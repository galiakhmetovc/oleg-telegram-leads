"""Web authentication behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import secrets
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.web_auth import WebAuthRepository, WebSessionRecord, WebUserRecord
from pur_leads.services.audit import AuditService

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 210_000
SESSION_TOKEN_BYTES = 32


class AuthError(ValueError):
    """Raised when authentication or authorization fails."""


@dataclass(frozen=True)
class LoginResult:
    user: WebUserRecord
    session: WebSessionRecord
    session_token: str


@dataclass(frozen=True)
class SessionValidationResult:
    user: WebUserRecord
    session: WebSessionRecord


class WebAuthService:
    def __init__(
        self,
        session: Session,
        *,
        telegram_bot_token: str | None = None,
        session_duration_hours: int = 24 * 14,
    ) -> None:
        self.session = session
        self.repository = WebAuthRepository(session)
        self.audit = AuditService(session)
        self.telegram_bot_token = telegram_bot_token
        self.session_duration = timedelta(hours=session_duration_hours)

    def ensure_bootstrap_admin(self, *, username: str, password: str) -> WebUserRecord:
        existing = self.repository.get_user_by_local_username(username)
        if existing is not None:
            return existing
        now = utc_now()
        user = self.repository.create_user(
            telegram_user_id=None,
            telegram_username=None,
            display_name="Bootstrap Admin",
            auth_type="local",
            local_username=username,
            password_hash=hash_password(password),
            must_change_password=True,
            role="admin",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
        )
        self.audit.record_change(
            actor="system",
            action="web_auth.bootstrap_admin_created",
            entity_type="web_user",
            entity_id=user.id,
            old_value_json=None,
            new_value_json={"local_username": username, "role": "admin"},
        )
        return user

    def login_local(
        self,
        *,
        username: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResult:
        user = self.repository.get_user_by_local_username(username)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            self._record_denied_login("local", username)
            raise AuthError("invalid credentials")
        self._require_active(user)
        return self._create_login(
            user, auth_method="local", ip_address=ip_address, user_agent=user_agent
        )

    def login_telegram(
        self,
        payload: dict[str, Any],
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResult:
        if self.telegram_bot_token is None:
            raise AuthError("Telegram auth is not configured")
        if not verify_telegram_payload(payload, self.telegram_bot_token):
            self._record_denied_login("telegram", str(payload.get("id")))
            raise AuthError("invalid Telegram auth")
        telegram_user_id = str(payload.get("id") or "")
        user = self.repository.get_user_by_telegram_id(telegram_user_id)
        if user is None:
            self._record_denied_login("telegram", telegram_user_id)
            raise AuthError("unknown Telegram user")
        self._require_active(user)
        now = utc_now()
        username = payload.get("username")
        first_name = payload.get("first_name")
        updated_user = self.repository.update_user(
            user.id,
            telegram_username=username if isinstance(username, str) else user.telegram_username,
            display_name=first_name if isinstance(first_name, str) else user.display_name,
            updated_at=now,
        )
        return self._create_login(
            updated_user,
            auth_method="telegram",
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def validate_session(self, session_token: str) -> SessionValidationResult:
        token_hash = hash_session_token(session_token)
        session = self.repository.get_session_by_token_hash(token_hash)
        now = utc_now()
        if (
            session is None
            or session.revoked_at is not None
            or _is_expired(session.expires_at, now)
        ):
            raise AuthError("invalid session")
        user = self.repository.get_user(session.user_id)
        if user is None:
            raise AuthError("invalid session")
        self._require_active(user)
        touched = self.repository.update_session(session.id, last_seen_at=now)
        self.session.commit()
        return SessionValidationResult(user=user, session=touched)

    def logout(self, session_token: str, *, actor: str) -> None:
        session = self.repository.get_session_by_token_hash(hash_session_token(session_token))
        if session is None:
            return
        self.repository.update_session(session.id, revoked_at=utc_now())
        self.audit.record_change(
            actor=actor,
            action="web_auth.logout",
            entity_type="web_auth_session",
            entity_id=session.id,
            old_value_json={"revoked_at": None},
            new_value_json={"revoked": True},
        )

    def change_password(self, user_id: str, *, new_password: str, actor: str) -> WebUserRecord:
        user = self.repository.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        updated = self.repository.update_user(
            user.id,
            password_hash=hash_password(new_password),
            must_change_password=False,
            updated_at=utc_now(),
        )
        self.audit.record_change(
            actor=actor,
            action="web_auth.password_changed",
            entity_type="web_user",
            entity_id=user.id,
            old_value_json={"must_change_password": user.must_change_password},
            new_value_json={"must_change_password": False},
        )
        return updated

    def add_telegram_admin(
        self,
        *,
        telegram_user_id: str,
        telegram_username: str | None,
        display_name: str | None,
        actor: str,
        actor_user_id: str,
    ) -> WebUserRecord:
        actor_user = self.repository.get_user(actor_user_id)
        if actor_user is None or actor_user.role != "admin" or actor_user.status != "active":
            raise AuthError("admin role required")
        now = utc_now()
        user = self.repository.create_user(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            display_name=display_name,
            auth_type="telegram",
            local_username=None,
            password_hash=None,
            must_change_password=False,
            role="admin",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
        )
        self.audit.record_change(
            actor=actor,
            action="web_auth.telegram_admin_created",
            entity_type="web_user",
            entity_id=user.id,
            old_value_json=None,
            new_value_json={
                "telegram_user_id": telegram_user_id,
                "telegram_username": telegram_username,
                "role": "admin",
            },
        )
        return user

    def disable_user(self, user_id: str, *, actor: str) -> WebUserRecord:
        user = self.repository.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        now = utc_now()
        updated = self.repository.update_user(user.id, status="disabled", updated_at=now)
        self.repository.revoke_user_sessions(user.id, revoked_at=now)
        self.audit.record_change(
            actor=actor,
            action="web_auth.user_disabled",
            entity_type="web_user",
            entity_id=user.id,
            old_value_json={"status": user.status},
            new_value_json={"status": "disabled"},
        )
        return updated

    def _create_login(
        self,
        user: WebUserRecord,
        *,
        auth_method: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResult:
        now = utc_now()
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        session = self.repository.create_session(
            user_id=user.id,
            auth_method=auth_method,
            session_token_hash=hash_session_token(token),
            created_at=now,
            expires_at=now + self.session_duration,
            last_seen_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
            revoked_at=None,
        )
        updated_user = self.repository.update_user(user.id, last_login_at=now, updated_at=now)
        self.audit.record_change(
            actor=user.local_username or user.telegram_user_id or user.id,
            action="web_auth.login_success",
            entity_type="web_user",
            entity_id=user.id,
            old_value_json=None,
            new_value_json={"auth_method": auth_method},
        )
        return LoginResult(user=updated_user, session=session, session_token=token)

    def _require_active(self, user: WebUserRecord) -> None:
        if user.status != "active":
            raise AuthError("user is not active")

    def _record_denied_login(self, auth_method: str, identifier: str) -> None:
        self.audit.record_event(
            event_type="access_check",
            severity="warning",
            message="login denied",
            entity_type="web_user",
            entity_id=None,
            details_json={"auth_method": auth_method, "identifier": identifier},
        )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$".join(
        [
            PBKDF2_ALGORITHM,
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def hash_session_token(session_token: str) -> str:
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()


def verify_telegram_payload(payload: dict[str, Any], bot_token: str) -> bool:
    provided_hash = payload.get("hash")
    if not isinstance(provided_hash, str) or not provided_hash:
        return False
    data = {
        key: str(value) for key, value in payload.items() if key != "hash" and value is not None
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_hash, expected_hash)


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    if getattr(expires_at, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
        now = now.replace(tzinfo=None)
    return expires_at <= now
