"""Scheduler persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.scheduler import scheduler_jobs_table

ACTIVE_IDEMPOTENT_STATUSES = {"queued", "running"}
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


@dataclass(frozen=True)
class SchedulerJobRecord:
    id: str
    job_type: str
    status: str
    priority: str
    scope_type: str
    scope_id: str | None
    userbot_account_id: str | None
    monitored_source_id: str | None
    source_message_id: str | None
    idempotency_key: str | None
    run_after_at: datetime
    next_retry_at: datetime | None
    locked_by: str | None
    locked_at: datetime | None
    lease_expires_at: datetime | None
    attempt_count: int
    max_attempts: int
    checkpoint_before_json: Any
    checkpoint_after_json: Any
    result_summary_json: Any
    payload_json: Any
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class SchedulerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> SchedulerJobRecord | None:
        row = (
            self.session.execute(
                select(scheduler_jobs_table).where(scheduler_jobs_table.c.id == job_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._record_from_row(row)

    def find_active_by_idempotency(self, idempotency_key: str) -> SchedulerJobRecord | None:
        row = (
            self.session.execute(
                select(scheduler_jobs_table).where(
                    scheduler_jobs_table.c.idempotency_key == idempotency_key,
                    scheduler_jobs_table.c.status.in_(ACTIVE_IDEMPOTENT_STATUSES),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._record_from_row(row)

    def create(
        self,
        *,
        job_type: str,
        scope_type: str,
        now: datetime,
        priority: str = "normal",
        status: str = "queued",
        scope_id: str | None = None,
        userbot_account_id: str | None = None,
        monitored_source_id: str | None = None,
        source_message_id: str | None = None,
        idempotency_key: str | None = None,
        run_after_at: datetime | None = None,
        max_attempts: int = 3,
        checkpoint_before_json: Any = None,
        payload_json: Any = None,
    ) -> SchedulerJobRecord:
        job_id = new_id()
        self.session.execute(
            insert(scheduler_jobs_table).values(
                id=job_id,
                job_type=job_type,
                status=status,
                priority=priority,
                scope_type=scope_type,
                scope_id=scope_id,
                userbot_account_id=userbot_account_id,
                monitored_source_id=monitored_source_id,
                source_message_id=source_message_id,
                idempotency_key=idempotency_key,
                run_after_at=self._to_db_datetime(run_after_at or now),
                next_retry_at=None,
                locked_by=None,
                locked_at=None,
                lease_expires_at=None,
                attempt_count=0,
                max_attempts=max_attempts,
                checkpoint_before_json=checkpoint_before_json,
                checkpoint_after_json=None,
                result_summary_json=None,
                payload_json=payload_json,
                last_error=None,
                created_at=self._to_db_datetime(now),
                updated_at=self._to_db_datetime(now),
            )
        )
        return self.get(job_id)  # type: ignore[return-value]

    def due_queued_jobs(self, now: datetime) -> list[SchedulerJobRecord]:
        rows = (
            self.session.execute(
                select(scheduler_jobs_table).where(scheduler_jobs_table.c.status == "queued")
            )
            .mappings()
            .all()
        )
        jobs = [self._record_from_row(row) for row in rows]
        jobs = [job for job in jobs if job.run_after_at <= self._to_aware_utc(now)]
        return sorted(jobs, key=lambda job: (PRIORITY_ORDER[job.priority], job.created_at))

    def has_running_userbot_job(self, userbot_account_id: str, now: datetime) -> bool:
        rows = (
            self.session.execute(
                select(scheduler_jobs_table).where(
                    scheduler_jobs_table.c.userbot_account_id == userbot_account_id,
                    scheduler_jobs_table.c.status == "running",
                    scheduler_jobs_table.c.lease_expires_at.is_not(None),
                )
            )
            .mappings()
            .all()
        )
        current_time = self._to_aware_utc(now)
        return any(
            (record := self._record_from_row(row)).lease_expires_at is not None
            and record.lease_expires_at > current_time
            for row in rows
        )

    def mark_running(
        self,
        job_id: str,
        *,
        worker_name: str,
        locked_at: datetime,
        lease_expires_at: datetime,
    ) -> SchedulerJobRecord:
        self.session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == job_id)
            .values(
                status="running",
                locked_by=worker_name,
                locked_at=self._to_db_datetime(locked_at),
                lease_expires_at=self._to_db_datetime(lease_expires_at),
                updated_at=self._to_db_datetime(locked_at),
            )
        )
        return self.get(job_id)  # type: ignore[return-value]

    def recover_expired_leases(self, now: datetime) -> int:
        rows = (
            self.session.execute(
                select(scheduler_jobs_table).where(
                    scheduler_jobs_table.c.status == "running",
                    scheduler_jobs_table.c.lease_expires_at.is_not(None),
                )
            )
            .mappings()
            .all()
        )
        current_time = self._to_aware_utc(now)
        expired_ids = [
            record.id
            for row in rows
            if (record := self._record_from_row(row)).lease_expires_at is not None
            and record.lease_expires_at <= current_time
        ]
        if not expired_ids:
            return 0
        result = self.session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id.in_(expired_ids))
            .values(
                status="queued",
                locked_by=None,
                locked_at=None,
                lease_expires_at=None,
                updated_at=self._to_db_datetime(now),
            )
        )
        return result.rowcount or 0

    def succeed(
        self, job_id: str, *, checkpoint_after: Any, result_summary: Any, now: datetime
    ) -> None:
        self.session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == job_id)
            .values(
                status="succeeded",
                checkpoint_after_json=checkpoint_after,
                result_summary_json=result_summary,
                locked_by=None,
                locked_at=None,
                lease_expires_at=None,
                updated_at=self._to_db_datetime(now),
            )
        )

    def fail(
        self, job_id: str, *, error: str, retry_at: datetime, now: datetime
    ) -> SchedulerJobRecord:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        attempt_count = job.attempt_count + 1
        retryable = attempt_count < job.max_attempts
        self.session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == job_id)
            .values(
                status="queued" if retryable else "failed",
                attempt_count=attempt_count,
                next_retry_at=self._to_db_datetime(retry_at) if retryable else None,
                run_after_at=(
                    self._to_db_datetime(retry_at)
                    if retryable
                    else self._to_db_datetime(job.run_after_at)
                ),
                locked_by=None,
                locked_at=None,
                lease_expires_at=None,
                last_error=error,
                updated_at=self._to_db_datetime(now),
            )
        )
        return self.get(job_id)  # type: ignore[return-value]

    @classmethod
    def _record_from_row(cls, row) -> SchedulerJobRecord:  # type: ignore[no-untyped-def]
        data = dict(row)
        for key in (
            "run_after_at",
            "next_retry_at",
            "locked_at",
            "lease_expires_at",
            "created_at",
            "updated_at",
        ):
            data[key] = cls._to_aware_utc(data[key]) if data[key] is not None else None
        return SchedulerJobRecord(**data)

    @staticmethod
    def _to_db_datetime(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    @staticmethod
    def _to_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
