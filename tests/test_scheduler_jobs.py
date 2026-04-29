from datetime import timedelta

import pytest

from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.services.scheduler import SchedulerService


@pytest.fixture
def scheduler_service(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield SchedulerService(session)


def test_enqueue_job_stores_structured_scope(scheduler_service):
    job = scheduler_service.enqueue(
        job_type="poll_monitored_source",
        scope_type="telegram_source",
        scope_id="source-1",
        userbot_account_id="userbot-1",
        monitored_source_id="source-1",
        idempotency_key="poll:source-1:1",
        payload_json={"limit": 100},
    )

    stored = scheduler_service.repository.get(job.id)
    assert stored is not None
    assert stored.job_type == "poll_monitored_source"
    assert stored.status == "queued"
    assert stored.scope_type == "telegram_source"
    assert stored.scope_id == "source-1"
    assert stored.userbot_account_id == "userbot-1"
    assert stored.monitored_source_id == "source-1"
    assert stored.idempotency_key == "poll:source-1:1"
    assert stored.payload_json == {"limit": 100}


def test_duplicate_idempotency_key_returns_existing_active_job(scheduler_service):
    first = scheduler_service.enqueue(
        job_type="sync_pur_channel",
        scope_type="telegram_source",
        idempotency_key="sync:pur:42",
    )
    second = scheduler_service.enqueue(
        job_type="sync_pur_channel",
        scope_type="telegram_source",
        idempotency_key="sync:pur:42",
    )

    assert second.id == first.id


def test_acquire_job_sets_lock_and_lease(scheduler_service):
    now = utc_now()
    scheduler_service.enqueue(
        job_type="extract_catalog_facts",
        scope_type="parser",
        run_after_at=now - timedelta(seconds=1),
    )

    acquired = scheduler_service.acquire_next("worker-a", now=now, lease_seconds=60)

    assert acquired is not None
    assert acquired.status == "running"
    assert acquired.locked_by == "worker-a"
    assert acquired.locked_at == now
    assert acquired.lease_expires_at == now + timedelta(seconds=60)


def test_expired_lease_can_be_recovered(scheduler_service):
    now = utc_now()
    scheduler_service.enqueue(job_type="parse_artifact", scope_type="parser", run_after_at=now)
    acquired = scheduler_service.acquire_next("worker-a", now=now, lease_seconds=10)
    assert acquired is not None

    recovered = scheduler_service.recover_expired_leases(now + timedelta(seconds=11))
    reacquired = scheduler_service.acquire_next(
        "worker-b",
        now=now + timedelta(seconds=12),
        lease_seconds=10,
    )

    assert recovered == 1
    assert reacquired is not None
    assert reacquired.id == acquired.id
    assert reacquired.locked_by == "worker-b"


def test_failed_job_is_requeued_with_retry_time(scheduler_service):
    now = utc_now()
    scheduler_service.enqueue(
        job_type="download_artifact",
        scope_type="archive",
        max_attempts=3,
        run_after_at=now,
    )
    acquired = scheduler_service.acquire_next("worker-a", now=now)
    assert acquired is not None

    retry_at = now + timedelta(minutes=5)
    scheduler_service.fail(acquired.id, error="network timeout", retry_at=retry_at)

    failed = scheduler_service.repository.get(acquired.id)
    assert failed is not None
    assert failed.status == "queued"
    assert failed.attempt_count == 1
    assert failed.next_retry_at == retry_at
    assert failed.run_after_at == retry_at
    assert failed.last_error == "network timeout"


def test_successful_retry_clears_previous_error_state(scheduler_service):
    now = utc_now()
    job = scheduler_service.enqueue(
        job_type="download_artifact",
        scope_type="archive",
        max_attempts=3,
        run_after_at=now,
    )
    acquired = scheduler_service.acquire_next("worker-a", now=now)
    assert acquired is not None
    retry_at = now + timedelta(minutes=5)
    scheduler_service.fail(acquired.id, error="database is locked", retry_at=retry_at)

    reacquired = scheduler_service.acquire_next("worker-a", now=retry_at + timedelta(seconds=1))
    assert reacquired is not None
    scheduler_service.succeed(
        job.id,
        checkpoint_after={"ok": True},
        result_summary={"done": True},
    )

    stored = scheduler_service.repository.get(job.id)
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.last_error is None
    assert stored.next_retry_at is None


def test_telegram_jobs_are_serialized_per_userbot(scheduler_service):
    now = utc_now()
    scheduler_service.enqueue(
        job_type="poll_monitored_source",
        scope_type="telegram_source",
        userbot_account_id="userbot-1",
        monitored_source_id="source-1",
        run_after_at=now,
    )
    scheduler_service.enqueue(
        job_type="check_source_access",
        scope_type="telegram_source",
        userbot_account_id="userbot-1",
        monitored_source_id="source-2",
        run_after_at=now,
    )

    first = scheduler_service.acquire_next("worker-a", now=now, lease_seconds=60)
    second = scheduler_service.acquire_next("worker-b", now=now, lease_seconds=60)

    assert first is not None
    assert second is None
