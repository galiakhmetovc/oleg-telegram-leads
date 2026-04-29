from datetime import timedelta

import pytest
from sqlalchemy import select, update

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import operational_events_table
from pur_leads.models.scheduler import job_runs_table, scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.runtime import JobHandlerResult, WorkerRuntime


@pytest.fixture
def runtime_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_worker_once_reports_idle_without_due_jobs(runtime_session):
    runtime = WorkerRuntime(runtime_session, handlers={})

    result = await runtime.run_once()

    assert result.status == "idle"
    assert result.job_id is None


@pytest.mark.asyncio
async def test_worker_once_schedules_due_active_source_poll_before_idling(runtime_session):
    source = TelegramSourceService(runtime_session).create_draft(
        "@example",
        purpose="lead_monitoring",
        added_by="admin",
    )
    TelegramSourceService(runtime_session).activate(source.id, actor="admin")
    due_at = utc_now() - timedelta(seconds=1)
    runtime_session.execute(
        update(monitored_sources_table)
        .where(monitored_sources_table.c.id == source.id)
        .values(next_poll_at=due_at, poll_interval_seconds=60)
    )
    runtime_session.commit()
    handled: list[str] = []

    async def handler(acquired_job):
        handled.append(acquired_job.monitored_source_id)
        return JobHandlerResult(result_summary={"handled": acquired_job.monitored_source_id})

    runtime = WorkerRuntime(runtime_session, handlers={"poll_monitored_source": handler})

    result = await runtime.run_once()

    poll_job = (
        runtime_session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "poll_monitored_source"
            )
        )
        .mappings()
        .one()
    )
    assert result.status == "succeeded"
    assert handled == [source.id]
    assert poll_job["status"] == "succeeded"
    assert poll_job["monitored_source_id"] == source.id
    assert poll_job["idempotency_key"] == f"source:{source.id}:poll:active"


@pytest.mark.asyncio
async def test_worker_once_executes_registered_handler_and_marks_succeeded(runtime_session):
    scheduler = SchedulerService(runtime_session)
    job = scheduler.enqueue(
        job_type="build_ai_batch", scope_type="global", payload_json={"value": 3}
    )
    handled: list[str] = []

    async def handler(acquired_job):
        handled.append(acquired_job.id)
        return JobHandlerResult(result_summary={"value": acquired_job.payload_json["value"] + 1})

    runtime = WorkerRuntime(runtime_session, handlers={"build_ai_batch": handler})

    result = await runtime.run_once()

    stored = scheduler.repository.get(job.id)
    assert stored is not None
    assert result.status == "succeeded"
    assert handled == [job.id]
    assert stored.status == "succeeded"
    assert stored.result_summary_json == {"value": 4}
    run = runtime_session.execute(select(job_runs_table)).mappings().one()
    assert run["scheduler_job_id"] == job.id
    assert run["worker_name"] == "worker"
    assert run["status"] == "succeeded"
    assert run["finished_at"] is not None
    assert run["duration_ms"] is not None
    assert run["result_json"] == {"value": 4}
    assert run["error"] is None
    assert run["log_correlation_id"]


@pytest.mark.asyncio
async def test_worker_once_delays_retry_when_handler_exposes_retry_after(runtime_session):
    class RetryLaterError(Exception):
        retry_after_seconds = 37

    scheduler = SchedulerService(runtime_session)
    job = scheduler.enqueue(job_type="send_notifications", scope_type="global")
    queued_peer = scheduler.enqueue(job_type="send_notifications", scope_type="global")
    before = utc_now()

    async def handler(acquired_job):
        raise RetryLaterError("Telegram rate limit")

    runtime = WorkerRuntime(runtime_session, handlers={"send_notifications": handler})

    result = await runtime.run_once()

    stored = scheduler.repository.get(job.id)
    stored_peer = scheduler.repository.get(queued_peer.id)
    assert stored is not None
    assert stored_peer is not None
    assert result.status == "failed"
    assert stored.status == "queued"
    assert stored.last_error == "Telegram rate limit"
    assert stored.next_retry_at is not None
    assert stored.next_retry_at >= before + timedelta(seconds=37)
    assert stored_peer.status == "queued"
    assert stored_peer.run_after_at >= stored.next_retry_at
    run = runtime_session.execute(select(job_runs_table)).mappings().one()
    assert run["scheduler_job_id"] == job.id
    assert run["status"] == "failed"
    assert run["finished_at"] is not None
    assert run["duration_ms"] is not None
    assert run["error"] == "Telegram rate limit"


@pytest.mark.asyncio
async def test_worker_once_fails_unsupported_job_with_operational_event(runtime_session):
    scheduler = SchedulerService(runtime_session)
    job = scheduler.enqueue(job_type="parse_artifact", scope_type="parser")
    runtime = WorkerRuntime(runtime_session, handlers={})

    result = await runtime.run_once()

    stored = scheduler.repository.get(job.id)
    event = runtime_session.execute(select(operational_events_table)).mappings().one()
    assert stored is not None
    assert result.status == "failed"
    assert stored.status == "failed"
    assert stored.last_error == "unsupported job type: parse_artifact"
    assert event["event_type"] == "scheduler"
    assert event["severity"] == "error"
    assert event["entity_id"] == job.id
    assert event["details_json"]["reason"] == "unsupported_job_type"


@pytest.mark.asyncio
async def test_worker_once_respects_userbot_serialization(runtime_session):
    scheduler = SchedulerService(runtime_session)
    scheduler.enqueue(
        job_type="poll_monitored_source",
        scope_type="telegram_source",
        userbot_account_id="userbot-1",
        monitored_source_id="source-1",
    )
    scheduler.enqueue(
        job_type="poll_monitored_source",
        scope_type="telegram_source",
        userbot_account_id="userbot-1",
        monitored_source_id="source-2",
    )
    first = scheduler.acquire_next("other-worker")
    assert first is not None

    async def handler(acquired_job):
        return JobHandlerResult(result_summary={"handled": acquired_job.id})

    runtime = WorkerRuntime(runtime_session, handlers={"poll_monitored_source": handler})

    result = await runtime.run_once()

    assert result.status == "idle"


def test_scheduler_repository_does_not_reacquire_running_job(runtime_session):
    scheduler = SchedulerService(runtime_session)
    job = scheduler.enqueue(job_type="build_ai_batch", scope_type="global")
    now = utc_now()

    first = scheduler.repository.mark_running(
        job.id,
        worker_name="worker-1",
        locked_at=now,
        lease_expires_at=now + timedelta(seconds=300),
    )
    second = scheduler.repository.mark_running(
        job.id,
        worker_name="worker-2",
        locked_at=now,
        lease_expires_at=now + timedelta(seconds=300),
    )

    assert first is not None
    assert second is None
