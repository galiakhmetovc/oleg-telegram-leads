"""Task persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.tasks import tasks_table


@dataclass(frozen=True)
class TaskRecord:
    id: str
    client_id: str | None
    lead_cluster_id: str | None
    lead_event_id: str | None
    opportunity_id: str | None
    support_case_id: str | None
    contact_reason_id: str | None
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    owner_user_id: str | None
    assignee_user_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **values) -> TaskRecord:  # type: ignore[no-untyped-def]
        task_id = new_id()
        self.session.execute(insert(tasks_table).values(id=task_id, **values))
        return self.get(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> TaskRecord | None:
        row = (
            self.session.execute(select(tasks_table).where(tasks_table.c.id == task_id))
            .mappings()
            .first()
        )
        return TaskRecord(**dict(row)) if row is not None else None
