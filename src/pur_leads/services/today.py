"""Daily work overview behavior."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.audit import operational_events_table
from pur_leads.models.catalog import catalog_candidates_table
from pur_leads.models.crm import clients_table, contact_reasons_table, support_cases_table
from pur_leads.models.leads import lead_clusters_table
from pur_leads.models.tasks import tasks_table
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.audit import AuditService


ACTIVE_TASK_STATUSES = {"open", "snoozed"}
ACTIVE_CONTACT_REASON_STATUSES = {"new", "accepted", "snoozed"}
OPEN_SUPPORT_CASE_STATUSES = {"new", "in_progress", "waiting_client"}
PENDING_CANDIDATE_STATUSES = {"auto_pending", "needs_review"}


class TodayService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def summary(self, *, now: datetime | None = None, limit: int = 12) -> dict[str, Any]:
        current_time = _aware_utc(now or utc_now())
        day_end = datetime.combine(current_time.date(), time.max, tzinfo=UTC)
        day_start = datetime.combine(current_time.date(), time.min, tzinfo=UTC)
        leads = self._lead_rows(limit=limit)
        tasks = self._task_rows(day_end=day_end, limit=limit)
        contact_reasons = self._contact_reason_rows(
            now=current_time,
            day_end=day_end,
            limit=limit,
        )
        support_cases = self._support_case_rows(limit=limit)
        catalog_candidates = self._catalog_candidate_rows(limit=limit)
        operational_issues = self._operational_issue_rows(limit=limit)
        return {
            "generated_at": current_time,
            "counts": {
                "new_leads": self._count_leads("new"),
                "maybe_leads": self._count_leads("maybe"),
                "due_tasks": self._count_due_tasks(day_end=day_end),
                "overdue_tasks": self._count_overdue_tasks(day_start=day_start),
                "contact_reasons": self._count_contact_reasons(
                    now=current_time,
                    day_end=day_end,
                ),
                "support_cases": self._count_support_cases(),
                "catalog_candidates": self._count_catalog_candidates(),
                "operational_issues": self._count_operational_issues(),
            },
            "leads": leads,
            "tasks": tasks,
            "contact_reasons": contact_reasons,
            "support_cases": support_cases,
            "catalog_candidates": catalog_candidates,
            "operational_issues": operational_issues,
        }

    def create_task(
        self,
        *,
        actor: str,
        title: str,
        description: str | None = None,
        priority: str = "normal",
        due_at: datetime | None = None,
        client_id: str | None = None,
        lead_cluster_id: str | None = None,
        contact_reason_id: str | None = None,
        owner_user_id: str | None = None,
        assignee_user_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        task_id = self._new_id()
        self.session.execute(
            tasks_table.insert().values(
                id=task_id,
                client_id=client_id,
                lead_cluster_id=lead_cluster_id,
                lead_event_id=None,
                opportunity_id=None,
                support_case_id=None,
                contact_reason_id=contact_reason_id,
                title=title,
                description=description,
                status="open",
                priority=priority,
                due_at=_db_datetime(due_at),
                owner_user_id=owner_user_id,
                assignee_user_id=assignee_user_id,
                created_at=_db_datetime(now),
                updated_at=_db_datetime(now),
                completed_at=None,
            )
        )
        self.audit.record_change(
            actor=actor,
            action="today.task_created",
            entity_type="task",
            entity_id=task_id,
            old_value_json=None,
            new_value_json={"title": title, "status": "open"},
        )
        self.session.commit()
        return self._get_task(task_id)

    def complete_task(self, task_id: str, *, actor: str) -> dict[str, Any]:
        return self._update_task(
            task_id,
            actor=actor,
            action="today.task_completed",
            status="done",
            completed_at=utc_now(),
        )

    def snooze_task(self, task_id: str, *, actor: str, due_at: datetime) -> dict[str, Any]:
        return self._update_task(
            task_id,
            actor=actor,
            action="today.task_snoozed",
            status="snoozed",
            due_at=due_at,
            completed_at=None,
        )

    def accept_contact_reason(self, reason_id: str, *, actor: str) -> dict[str, Any]:
        return self._update_contact_reason(
            reason_id,
            actor=actor,
            action="today.contact_reason_accepted",
            status="accepted",
            snoozed_until=None,
        )

    def complete_contact_reason(self, reason_id: str, *, actor: str) -> dict[str, Any]:
        return self._update_contact_reason(
            reason_id,
            actor=actor,
            action="today.contact_reason_done",
            status="done",
            snoozed_until=None,
        )

    def dismiss_contact_reason(self, reason_id: str, *, actor: str) -> dict[str, Any]:
        return self._update_contact_reason(
            reason_id,
            actor=actor,
            action="today.contact_reason_dismissed",
            status="dismissed",
            snoozed_until=None,
        )

    def snooze_contact_reason(
        self,
        reason_id: str,
        *,
        actor: str,
        snoozed_until: datetime,
    ) -> dict[str, Any]:
        return self._update_contact_reason(
            reason_id,
            actor=actor,
            action="today.contact_reason_snoozed",
            status="snoozed",
            snoozed_until=snoozed_until,
        )

    def _lead_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(
                    lead_clusters_table.c.id.label("cluster_id"),
                    lead_clusters_table.c.cluster_status.label("status"),
                    lead_clusters_table.c.review_status,
                    lead_clusters_table.c.summary,
                    lead_clusters_table.c.confidence_max,
                    lead_clusters_table.c.primary_sender_name,
                    lead_clusters_table.c.last_message_at,
                    source_messages_table.c.text.label("message_text"),
                    source_messages_table.c.telegram_message_id,
                )
                .select_from(
                    lead_clusters_table.outerjoin(
                        source_messages_table,
                        lead_clusters_table.c.primary_source_message_id
                        == source_messages_table.c.id,
                    )
                )
                .where(lead_clusters_table.c.cluster_status.in_(["new", "maybe"]))
                .order_by(lead_clusters_table.c.last_message_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _task_rows(self, *, day_end: datetime, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(tasks_table)
                .where(
                    tasks_table.c.status.in_(ACTIVE_TASK_STATUSES),
                    tasks_table.c.due_at.is_not(None),
                    tasks_table.c.due_at <= _db_datetime(day_end),
                )
                .order_by(tasks_table.c.due_at, tasks_table.c.priority.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _contact_reason_rows(
        self,
        *,
        now: datetime,
        day_end: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(
                    contact_reasons_table,
                    clients_table.c.display_name.label("client_display_name"),
                    clients_table.c.status.label("client_status"),
                )
                .select_from(
                    contact_reasons_table.join(
                        clients_table,
                        contact_reasons_table.c.client_id == clients_table.c.id,
                    )
                )
                .where(
                    contact_reasons_table.c.status.in_(ACTIVE_CONTACT_REASON_STATUSES),
                    or_(
                        contact_reasons_table.c.due_at <= _db_datetime(day_end),
                        contact_reasons_table.c.snoozed_until <= _db_datetime(now),
                    ),
                )
                .order_by(contact_reasons_table.c.due_at, contact_reasons_table.c.priority.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [
            {
                **{key: row[key] for key in contact_reasons_table.c.keys() if key in row},
                "client": {
                    "id": row["client_id"],
                    "display_name": row["client_display_name"],
                    "status": row["client_status"],
                },
            }
            for row in rows
        ]

    def _support_case_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(
                    support_cases_table,
                    clients_table.c.display_name.label("client_display_name"),
                )
                .select_from(
                    support_cases_table.join(
                        clients_table,
                        support_cases_table.c.client_id == clients_table.c.id,
                    )
                )
                .where(support_cases_table.c.status.in_(OPEN_SUPPORT_CASE_STATUSES))
                .order_by(
                    support_cases_table.c.priority.desc(), support_cases_table.c.updated_at.desc()
                )
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [
            {
                **{key: row[key] for key in support_cases_table.c.keys() if key in row},
                "client": {
                    "id": row["client_id"],
                    "display_name": row["client_display_name"],
                },
            }
            for row in rows
        ]

    def _catalog_candidate_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(catalog_candidates_table)
                .where(catalog_candidates_table.c.status.in_(PENDING_CANDIDATE_STATUSES))
                .order_by(catalog_candidates_table.c.updated_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _operational_issue_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(operational_events_table)
                .where(operational_events_table.c.severity.in_(["error", "critical"]))
                .order_by(operational_events_table.c.created_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _count_leads(self, status: str) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(lead_clusters_table)
                .where(lead_clusters_table.c.cluster_status == status)
            ).scalar_one()
        )

    def _count_due_tasks(self, *, day_end: datetime) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(tasks_table)
                .where(
                    tasks_table.c.status.in_(ACTIVE_TASK_STATUSES),
                    tasks_table.c.due_at.is_not(None),
                    tasks_table.c.due_at <= _db_datetime(day_end),
                )
            ).scalar_one()
        )

    def _count_overdue_tasks(self, *, day_start: datetime) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(tasks_table)
                .where(
                    tasks_table.c.status.in_(ACTIVE_TASK_STATUSES),
                    tasks_table.c.due_at.is_not(None),
                    tasks_table.c.due_at < _db_datetime(day_start),
                )
            ).scalar_one()
        )

    def _count_contact_reasons(self, *, now: datetime, day_end: datetime) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(contact_reasons_table)
                .where(
                    contact_reasons_table.c.status.in_(ACTIVE_CONTACT_REASON_STATUSES),
                    or_(
                        contact_reasons_table.c.due_at <= _db_datetime(day_end),
                        contact_reasons_table.c.snoozed_until <= _db_datetime(now),
                    ),
                )
            ).scalar_one()
        )

    def _count_support_cases(self) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(support_cases_table)
                .where(support_cases_table.c.status.in_(OPEN_SUPPORT_CASE_STATUSES))
            ).scalar_one()
        )

    def _count_catalog_candidates(self) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(catalog_candidates_table)
                .where(catalog_candidates_table.c.status.in_(PENDING_CANDIDATE_STATUSES))
            ).scalar_one()
        )

    def _count_operational_issues(self) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(operational_events_table)
                .where(operational_events_table.c.severity.in_(["error", "critical"]))
            ).scalar_one()
        )

    def _get_task(self, task_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(select(tasks_table).where(tasks_table.c.id == task_id))
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def _update_task(
        self,
        task_id: str,
        *,
        actor: str,
        action: str,
        status: str,
        due_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        old = self._get_task(task_id)
        now = utc_now()
        values: dict[str, Any] = {
            "status": status,
            "updated_at": _db_datetime(now),
            "completed_at": _db_datetime(completed_at),
        }
        if due_at is not None:
            values["due_at"] = _db_datetime(due_at)
        self.session.execute(
            update(tasks_table).where(tasks_table.c.id == task_id).values(**values)
        )
        self.audit.record_change(
            actor=actor,
            action=action,
            entity_type="task",
            entity_id=task_id,
            old_value_json={"status": old["status"]},
            new_value_json={"status": status, "due_at": due_at},
        )
        self.session.commit()
        return self._get_task(task_id)

    def _get_contact_reason(self, reason_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(contact_reasons_table).where(contact_reasons_table.c.id == reason_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(reason_id)
        return dict(row)

    def _update_contact_reason(
        self,
        reason_id: str,
        *,
        actor: str,
        action: str,
        status: str,
        snoozed_until: datetime | None,
    ) -> dict[str, Any]:
        old = self._get_contact_reason(reason_id)
        now = utc_now()
        self.session.execute(
            update(contact_reasons_table)
            .where(contact_reasons_table.c.id == reason_id)
            .values(
                status=status,
                snoozed_until=_db_datetime(snoozed_until),
                updated_at=_db_datetime(now),
            )
        )
        self.audit.record_change(
            actor=actor,
            action=action,
            entity_type="contact_reason",
            entity_id=reason_id,
            old_value_json={"status": old["status"]},
            new_value_json={"status": status, "snoozed_until": snoozed_until},
        )
        self.session.commit()
        return self._get_contact_reason(reason_id)

    @staticmethod
    def _new_id() -> str:
        from pur_leads.core.ids import new_id

        return new_id()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
