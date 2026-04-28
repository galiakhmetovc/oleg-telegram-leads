"""Web auth persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.web_auth import web_auth_sessions_table, web_users_table


@dataclass(frozen=True)
class WebUserRecord:
    id: str
    telegram_user_id: str | None
    telegram_username: str | None
    display_name: str | None
    auth_type: str
    local_username: str | None
    password_hash: str | None
    must_change_password: bool
    role: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


@dataclass(frozen=True)
class WebSessionRecord:
    id: str
    user_id: str
    auth_method: str
    session_token_hash: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    ip_address: str | None
    user_agent: str | None
    revoked_at: datetime | None


class WebAuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user(self, user_id: str) -> WebUserRecord | None:
        row = (
            self.session.execute(select(web_users_table).where(web_users_table.c.id == user_id))
            .mappings()
            .first()
        )
        return WebUserRecord(**dict(row)) if row is not None else None

    def get_user_by_local_username(self, username: str) -> WebUserRecord | None:
        row = (
            self.session.execute(
                select(web_users_table).where(web_users_table.c.local_username == username)
            )
            .mappings()
            .first()
        )
        return WebUserRecord(**dict(row)) if row is not None else None

    def get_user_by_telegram_id(self, telegram_user_id: str) -> WebUserRecord | None:
        row = (
            self.session.execute(
                select(web_users_table).where(
                    web_users_table.c.telegram_user_id == telegram_user_id
                )
            )
            .mappings()
            .first()
        )
        return WebUserRecord(**dict(row)) if row is not None else None

    def create_user(self, **values) -> WebUserRecord:  # type: ignore[no-untyped-def]
        user_id = new_id()
        self.session.execute(insert(web_users_table).values(id=user_id, **values))
        return self.get_user(user_id)  # type: ignore[return-value]

    def update_user(self, user_id: str, **values) -> WebUserRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(web_users_table).where(web_users_table.c.id == user_id).values(**values)
        )
        user = self.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        return user

    def create_session(self, **values) -> WebSessionRecord:  # type: ignore[no-untyped-def]
        session_id = new_id()
        self.session.execute(insert(web_auth_sessions_table).values(id=session_id, **values))
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> WebSessionRecord | None:
        row = (
            self.session.execute(
                select(web_auth_sessions_table).where(web_auth_sessions_table.c.id == session_id)
            )
            .mappings()
            .first()
        )
        return WebSessionRecord(**dict(row)) if row is not None else None

    def get_session_by_token_hash(self, token_hash: str) -> WebSessionRecord | None:
        row = (
            self.session.execute(
                select(web_auth_sessions_table).where(
                    web_auth_sessions_table.c.session_token_hash == token_hash
                )
            )
            .mappings()
            .first()
        )
        return WebSessionRecord(**dict(row)) if row is not None else None

    def update_session(
        self,
        session_id: str,
        **values,
    ) -> WebSessionRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(web_auth_sessions_table)
            .where(web_auth_sessions_table.c.id == session_id)
            .values(**values)
        )
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def revoke_user_sessions(self, user_id: str, *, revoked_at: datetime) -> None:
        self.session.execute(
            update(web_auth_sessions_table)
            .where(
                web_auth_sessions_table.c.user_id == user_id,
                web_auth_sessions_table.c.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
