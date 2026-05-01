"""Scheduler job behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.core.tracing import TraceContext, current_trace_context
from pur_leads.repositories.scheduler import SchedulerJobRecord, SchedulerRepository


class SchedulerService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SchedulerRepository(session)

    def enqueue(
        self,
        *,
        job_type: str,
        scope_type: str,
        priority: str = "normal",
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
        if idempotency_key is not None:
            existing = self.repository.find_active_by_idempotency(idempotency_key)
            if existing is not None:
                return existing

        trace_context = current_trace_context()
        trace_context_json = _trace_context_payload(trace_context)
        job = self.repository.create(
            job_type=job_type,
            scope_type=scope_type,
            priority=priority,
            scope_id=scope_id,
            userbot_account_id=userbot_account_id,
            monitored_source_id=monitored_source_id,
            source_message_id=source_message_id,
            idempotency_key=idempotency_key,
            run_after_at=run_after_at,
            max_attempts=max_attempts,
            checkpoint_before_json=checkpoint_before_json,
            payload_json=payload_json,
            trace_id=trace_context.trace_id if trace_context is not None else None,
            parent_span_id=trace_context.span_id if trace_context is not None else None,
            trace_context_json=trace_context_json,
            now=utc_now(),
        )
        self.session.commit()
        return job

    def start_run(
        self,
        job_id: str,
        *,
        worker_name: str,
        trace_context: TraceContext | None = None,
    ) -> str:
        run = self.repository.start_run(
            scheduler_job_id=job_id,
            worker_name=worker_name,
            started_at=utc_now(),
            log_correlation_id=trace_context.trace_id
            if trace_context is not None
            else f"job:{job_id}",
            trace_id=trace_context.trace_id if trace_context is not None else None,
            span_id=trace_context.span_id if trace_context is not None else None,
            parent_span_id=trace_context.parent_span_id if trace_context is not None else None,
        )
        self.session.commit()
        return run.id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        result_json: Any = None,
        error: str | None = None,
    ) -> None:
        self.repository.finish_run(
            run_id,
            status=status,
            finished_at=utc_now(),
            result_json=result_json,
            error=error,
        )
        self.session.commit()

    def acquire_next(
        self,
        worker_name: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> SchedulerJobRecord | None:
        current_time = now or utc_now()
        for job in self.repository.due_queued_jobs(current_time):
            if job.userbot_account_id is not None and self.repository.has_running_userbot_job(
                job.userbot_account_id,
                current_time,
            ):
                continue

            acquired = self.repository.mark_running(
                job.id,
                worker_name=worker_name,
                locked_at=current_time,
                lease_expires_at=current_time + timedelta(seconds=lease_seconds),
            )
            if acquired is not None:
                self.session.commit()
                return acquired
            self.session.rollback()
        return None

    def has_due_or_running_work_above_priority(
        self,
        priority: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        return self.repository.has_due_or_running_work_above_priority(
            priority,
            now or utc_now(),
        )

    def recover_expired_leases(self, now: datetime | None = None) -> int:
        recovered = self.repository.recover_expired_leases(now or utc_now())
        self.session.commit()
        return recovered

    def succeed(
        self,
        job_id: str,
        *,
        checkpoint_after: Any = None,
        result_summary: Any = None,
    ) -> None:
        self.repository.succeed(
            job_id,
            checkpoint_after=checkpoint_after,
            result_summary=result_summary,
            now=utc_now(),
        )
        self.session.commit()

    def fail(self, job_id: str, *, error: str, retry_at: datetime) -> SchedulerJobRecord:
        job = self.repository.fail(job_id, error=error, retry_at=retry_at, now=utc_now())
        self.session.commit()
        return job

    def defer(self, job_id: str, *, reason: str, retry_at: datetime) -> SchedulerJobRecord:
        job = self.repository.defer(job_id, reason=reason, retry_at=retry_at, now=utc_now())
        self.session.commit()
        return job

    def fail_permanently(self, job_id: str, *, error: str) -> SchedulerJobRecord:
        job = self.repository.fail_permanently(job_id, error=error, now=utc_now())
        self.session.commit()
        return job


def _trace_context_payload(context: TraceContext | None) -> dict[str, Any] | None:
    return context.as_jsonable() if context is not None else None
