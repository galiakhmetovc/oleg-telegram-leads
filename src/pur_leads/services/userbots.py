"""Telegram userbot account behavior."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.userbots import UserbotAccountRecord, UserbotAccountRepository
from pur_leads.services.audit import AuditService
from pur_leads.services.settings import SettingsService

USERBOT_STATUSES = {"active", "paused", "needs_login", "banned", "disabled"}
USERBOT_PRIORITIES = {"low", "normal", "high"}


class UserbotAccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = UserbotAccountRepository(session)
        self.audit = AuditService(session)

    def create_account(
        self,
        *,
        display_name: str,
        session_name: str,
        session_path: str,
        actor: str,
        telegram_user_id: str | None = None,
        telegram_username: str | None = None,
        status: str = "active",
        priority: str = "normal",
        max_parallel_telegram_jobs: int = 1,
        flood_sleep_threshold_seconds: int = 60,
    ) -> UserbotAccountRecord:
        self._validate(
            display_name=display_name,
            session_name=session_name,
            session_path=session_path,
            status=status,
            priority=priority,
            max_parallel_telegram_jobs=max_parallel_telegram_jobs,
            flood_sleep_threshold_seconds=flood_sleep_threshold_seconds,
        )
        now = utc_now()
        account = self.repository.create(
            display_name=display_name.strip(),
            telegram_user_id=telegram_user_id or None,
            telegram_username=telegram_username or None,
            session_name=session_name.strip(),
            session_path=session_path.strip(),
            status=status,
            priority=priority,
            max_parallel_telegram_jobs=max_parallel_telegram_jobs,
            flood_sleep_threshold_seconds=flood_sleep_threshold_seconds,
            last_connected_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self.audit.record_change(
            actor=actor,
            action="userbot_account.create",
            entity_type="userbot_account",
            entity_id=account.id,
            old_value_json=None,
            new_value_json={
                "display_name": account.display_name,
                "session_name": account.session_name,
                "status": account.status,
                "priority": account.priority,
            },
        )
        self.session.commit()
        return account

    def list_accounts(self) -> list[UserbotAccountRecord]:
        return self.repository.list_accounts()

    def select_default_userbot(self) -> UserbotAccountRecord | None:
        configured_id = SettingsService(self.session).get("telegram_default_userbot_account_id")
        if isinstance(configured_id, str) and configured_id:
            account = self.repository.get(configured_id)
            if account is not None and account.status == "active":
                return account
        return self.repository.first_active()

    def public_payload(self, account: UserbotAccountRecord) -> dict[str, Any]:
        return {
            "id": account.id,
            "display_name": account.display_name,
            "telegram_user_id": account.telegram_user_id,
            "telegram_username": account.telegram_username,
            "session_name": account.session_name,
            "status": account.status,
            "priority": account.priority,
            "max_parallel_telegram_jobs": account.max_parallel_telegram_jobs,
            "flood_sleep_threshold_seconds": account.flood_sleep_threshold_seconds,
            "last_connected_at": account.last_connected_at,
            "last_error": account.last_error,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }

    @staticmethod
    def _validate(
        *,
        display_name: str,
        session_name: str,
        session_path: str,
        status: str,
        priority: str,
        max_parallel_telegram_jobs: int,
        flood_sleep_threshold_seconds: int,
    ) -> None:
        if not display_name.strip():
            raise ValueError("display_name is required")
        if not session_name.strip():
            raise ValueError("session_name is required")
        if not session_path.strip():
            raise ValueError("session_path is required")
        if status not in USERBOT_STATUSES:
            raise ValueError(f"Unsupported userbot status: {status}")
        if priority not in USERBOT_PRIORITIES:
            raise ValueError(f"Unsupported userbot priority: {priority}")
        if max_parallel_telegram_jobs < 1:
            raise ValueError("max_parallel_telegram_jobs must be positive")
        if flood_sleep_threshold_seconds < 0:
            raise ValueError("flood_sleep_threshold_seconds must be non-negative")
