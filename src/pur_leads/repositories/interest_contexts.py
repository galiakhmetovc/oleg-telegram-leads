"""Interest context persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.interest_contexts import interest_contexts_table


@dataclass(frozen=True)
class InterestContextRecord:
    id: str
    name: str
    description: str | None
    status: str
    created_by: str
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InterestContextRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **values) -> InterestContextRecord:  # type: ignore[no-untyped-def]
        context_id = new_id()
        self.session.execute(insert(interest_contexts_table).values(id=context_id, **values))
        return self.get(context_id)  # type: ignore[return-value]

    def get(self, context_id: str) -> InterestContextRecord | None:
        row = (
            self.session.execute(
                select(interest_contexts_table).where(interest_contexts_table.c.id == context_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return InterestContextRecord(**dict(row))

    def list_contexts(self) -> list[InterestContextRecord]:
        rows = (
            self.session.execute(
                select(interest_contexts_table).order_by(
                    interest_contexts_table.c.updated_at.desc()
                )
            )
            .mappings()
            .all()
        )
        return [InterestContextRecord(**dict(row)) for row in rows]

    def count_active_or_draft(self) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(interest_contexts_table)
                .where(interest_contexts_table.c.status.in_(["draft", "active"]))
            ).scalar_one()
        )

    def update(self, context_id: str, **values) -> InterestContextRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(interest_contexts_table)
            .where(interest_contexts_table.c.id == context_id)
            .values(**values)
        )
        record = self.get(context_id)
        if record is None:
            raise KeyError(context_id)
        return record
