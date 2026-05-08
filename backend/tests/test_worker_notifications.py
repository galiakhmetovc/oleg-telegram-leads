from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentStatus
from app.worker import tasks


@pytest.mark.asyncio
async def test_worker_skips_notifications_for_non_telegram_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    queued: list[object] = []

    async def no_context(session_factory: object, job_id: object) -> None:
        return None

    class RecordingQueueNotifications:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def execute(self, result: object, context: object) -> list[object]:
            queued.append((result, context))
            return []

    monkeypatch.setattr(tasks, "_notification_context", no_context)
    monkeypatch.setattr(tasks, "QueueNotificationsForEnrichment", RecordingQueueNotifications)

    await tasks._queue_notifications(object(), object(), uuid4())

    assert queued == []


@pytest.mark.asyncio
async def test_worker_redelivery_does_not_rerun_non_queued_job(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = uuid4()
    calls: list[str] = []

    class NonQueuedRepository:
        def __init__(self, session_factory: object) -> None:
            pass

        async def get_job(self, requested_job_id: object) -> EnrichmentJobSnapshot | None:
            calls.append(f"get:{requested_job_id}")
            return EnrichmentJobSnapshot(
                id=job_id,
                input_text="already done",
                status=EnrichmentStatus.COMPLETED,
                progress_percent=100,
                current_stage="completed",
                stage_index=0,
                stage_count=0,
                stage_progress_percent=100,
                message="done",
                result=None,
                error=None,
                created_at=datetime(2026, 5, 8, tzinfo=UTC),
                started_at=datetime(2026, 5, 8, tzinfo=UTC),
                finished_at=datetime(2026, 5, 8, tzinfo=UTC),
            )

        async def claim_queued_job(self, requested_job_id: object, *, stage_count: int) -> EnrichmentJobSnapshot | None:
            calls.append(f"claim:{requested_job_id}:{stage_count}")
            return None

        async def mark_running(self, requested_job_id: object, *, stage_count: int) -> None:
            calls.append(f"mark_running:{requested_job_id}:{stage_count}")

        async def complete_job(self, requested_job_id: object, result: object) -> None:
            calls.append(f"complete:{requested_job_id}")

        async def fail_job(self, requested_job_id: object, error: object) -> None:
            calls.append(f"fail:{requested_job_id}")

    monkeypatch.setattr(tasks, "create_sessionmaker", lambda: object())
    monkeypatch.setattr(tasks, "PostgresEnrichmentJobRepository", NonQueuedRepository)

    await tasks._run_enrichment_job(job_id)

    assert calls == [f"get:{job_id}"]
