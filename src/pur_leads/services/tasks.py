"""Task behavior."""

from __future__ import annotations

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.tasks import TaskRecord, TaskRepository


class TaskService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TaskRepository(session)

    def create_contact_task_for_lead(
        self,
        *,
        lead_cluster_id: str,
        lead_event_id: str | None,
        title: str,
        description: str | None,
        owner_user_id: str | None,
        assignee_user_id: str | None,
    ) -> TaskRecord:
        now = utc_now()
        task = self.repository.create(
            client_id=None,
            lead_cluster_id=lead_cluster_id,
            lead_event_id=lead_event_id,
            opportunity_id=None,
            support_case_id=None,
            contact_reason_id=None,
            title=title,
            description=description,
            status="open",
            priority="normal",
            due_at=now,
            owner_user_id=owner_user_id,
            assignee_user_id=assignee_user_id,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        self.session.commit()
        return task
