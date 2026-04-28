"""Telegram userbot account persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.telegram_sources import userbot_accounts_table


@dataclass(frozen=True)
class UserbotAccountRecord:
    id: str
    display_name: str
    telegram_user_id: str | None
    telegram_username: str | None
    session_name: str
    session_path: str
    status: str
    priority: str
    max_parallel_telegram_jobs: int
    flood_sleep_threshold_seconds: int
    last_connected_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class UserbotAccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **values) -> UserbotAccountRecord:  # type: ignore[no-untyped-def]
        account_id = new_id()
        self.session.execute(insert(userbot_accounts_table).values(id=account_id, **values))
        return self.get(account_id)  # type: ignore[return-value]

    def get(self, account_id: str) -> UserbotAccountRecord | None:
        row = (
            self.session.execute(
                select(userbot_accounts_table).where(userbot_accounts_table.c.id == account_id)
            )
            .mappings()
            .first()
        )
        return UserbotAccountRecord(**dict(row)) if row is not None else None

    def list_accounts(self) -> list[UserbotAccountRecord]:
        rows = (
            self.session.execute(
                select(userbot_accounts_table).order_by(userbot_accounts_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [UserbotAccountRecord(**dict(row)) for row in rows]

    def first_active(self) -> UserbotAccountRecord | None:
        row = (
            self.session.execute(
                select(userbot_accounts_table)
                .where(userbot_accounts_table.c.status == "active")
                .order_by(userbot_accounts_table.c.created_at)
            )
            .mappings()
            .first()
        )
        return UserbotAccountRecord(**dict(row)) if row is not None else None

    def update(self, account_id: str, **values) -> UserbotAccountRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(userbot_accounts_table)
            .where(userbot_accounts_table.c.id == account_id)
            .values(**values)
        )
        account = self.get(account_id)
        if account is None:
            raise KeyError(account_id)
        return account
