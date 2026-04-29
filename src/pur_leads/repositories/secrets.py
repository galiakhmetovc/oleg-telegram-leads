"""Secret reference persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.secrets import secret_refs_table


@dataclass(frozen=True)
class SecretRefRecord:
    id: str
    secret_type: str
    display_name: str
    storage_backend: str
    storage_ref: str
    status: str
    last_rotated_at: datetime | None
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SecretRefsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        secret_id: str | None = None,
        secret_type: str,
        display_name: str,
        storage_backend: str,
        storage_ref: str,
        now: datetime,
    ) -> SecretRefRecord:
        secret_id = secret_id or new_id()
        self.session.execute(
            insert(secret_refs_table).values(
                id=secret_id,
                secret_type=secret_type,
                display_name=display_name,
                storage_backend=storage_backend,
                storage_ref=storage_ref,
                status="active",
                last_rotated_at=None,
                last_checked_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        return self.get(secret_id)  # type: ignore[return-value]

    def get(self, secret_id: str) -> SecretRefRecord | None:
        row = (
            self.session.execute(
                select(secret_refs_table).where(secret_refs_table.c.id == secret_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return SecretRefRecord(**dict(row))

    def mark_missing(self, secret_id: str, now: datetime) -> SecretRefRecord:
        self.session.execute(
            update(secret_refs_table)
            .where(secret_refs_table.c.id == secret_id)
            .values(status="missing", last_checked_at=now, updated_at=now)
        )
        return self.get(secret_id)  # type: ignore[return-value]
