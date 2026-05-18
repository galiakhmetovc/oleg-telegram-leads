from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentStatus
from app.domain.settings import NlpConfigRevision
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
async def test_worker_queues_llm_notification_after_completed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    session_factory = object()
    completed_run = SimpleNamespace(
        status="completed",
        source_message_id=uuid4(),
        enrichment_job_id=uuid4(),
    )
    queued: list[tuple[object, object]] = []

    class RecordingLlmSettingsRepository:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def get_settings(self) -> SimpleNamespace:
            return SimpleNamespace(endpoint="http://llm.local/api/chat", timeout_seconds=600)

    class RecordingLlmExecutor:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def execute(self, requested_run_id: object) -> object:
            assert requested_run_id == run_id
            return completed_run

    async def record_llm_notification(requested_session_factory: object, run: object) -> None:
        queued.append((requested_session_factory, run))

    monkeypatch.setattr(tasks, "create_sessionmaker", lambda: session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(
            llm_verification_model="lead-qwen-ru",
            llm_verification_endpoint="http://llm.local/api/chat",
            llm_verification_timeout_seconds=600,
        ),
    )
    monkeypatch.setattr(tasks, "PostgresLlmSettingsRepository", RecordingLlmSettingsRepository)
    monkeypatch.setattr(tasks, "ExecuteQueuedLlmVerification", RecordingLlmExecutor)
    monkeypatch.setattr(tasks, "_queue_llm_notification", record_llm_notification)

    await tasks._run_llm_verification(run_id)

    assert queued == [(session_factory, completed_run)]


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


@pytest.mark.asyncio
async def test_worker_marks_queued_job_failed_when_active_config_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    revision_id = uuid4()
    calls: list[tuple[str, object]] = []

    class RecordingRepository:
        def __init__(self, session_factory: object) -> None:
            pass

        async def get_job(self, requested_job_id: object) -> EnrichmentJobSnapshot | None:
            calls.append(("get", requested_job_id))
            return EnrichmentJobSnapshot(
                id=job_id,
                input_text="тест",
                status=EnrichmentStatus.QUEUED,
                progress_percent=0,
                current_stage=None,
                stage_index=0,
                stage_count=0,
                stage_progress_percent=0,
                message="queued",
                result=None,
                error=None,
                created_at=datetime(2026, 5, 10, tzinfo=UTC),
                started_at=None,
                finished_at=None,
            )

        async def claim_queued_job(self, requested_job_id: object, **kwargs: object) -> None:
            calls.append(("claim", requested_job_id))

        async def fail_job(self, requested_job_id: object, error: object) -> None:
            calls.append(("fail", (requested_job_id, error)))

    class ActiveRevisionRepository:
        def __init__(self, session_factory: object) -> None:
            pass

        async def get_active_or_seed(self, default_documents: object) -> NlpConfigRevision:
            calls.append(("active_revision", default_documents))
            return NlpConfigRevision(
                id=revision_id,
                revision=88,
                documents={"pipeline": {"stages": []}},
                source="test",
                created_at=datetime(2026, 5, 10, tzinfo=UTC),
            )

    def raise_invalid_config(documents: object) -> object:
        raise ValueError("invalid active NLP config")

    monkeypatch.setattr(tasks, "create_sessionmaker", lambda: object())
    monkeypatch.setattr(tasks, "PostgresEnrichmentJobRepository", RecordingRepository)
    monkeypatch.setattr(tasks, "PostgresNlpConfigRepository", ActiveRevisionRepository)
    monkeypatch.setattr(tasks, "read_nlp_config_documents", lambda path: {"pipeline": {"stages": []}})
    monkeypatch.setattr(tasks, "load_nlp_config_from_documents", raise_invalid_config)
    tasks._PIPELINE_CACHE.clear()

    with pytest.raises(ValueError, match="invalid active NLP config"):
        await tasks._run_enrichment_job(job_id)

    assert ("claim", job_id) not in calls
    assert (
        "fail",
        (
            job_id,
            {"type": "ValueError", "message": "invalid active NLP config"},
        ),
    ) in calls


@pytest.mark.asyncio
async def test_worker_claims_job_with_active_config_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    revision_id = uuid4()
    calls: list[tuple[str, object]] = []
    result = object()

    class RecordingRepository:
        def __init__(self, session_factory: object) -> None:
            pass

        async def get_job(self, requested_job_id: object) -> EnrichmentJobSnapshot | None:
            calls.append(("get", requested_job_id))
            return EnrichmentJobSnapshot(
                id=job_id,
                input_text="помогите собрать комплект видеонаблюдения",
                status=EnrichmentStatus.QUEUED,
                progress_percent=0,
                current_stage=None,
                stage_index=0,
                stage_count=0,
                stage_progress_percent=0,
                message="queued",
                result=None,
                error=None,
                created_at=datetime(2026, 5, 9, tzinfo=UTC),
                started_at=None,
                finished_at=None,
            )

        async def claim_queued_job(
            self,
            requested_job_id: object,
            *,
            stage_count: int,
            nlp_config_revision_id: object,
            nlp_config_revision: int,
        ) -> EnrichmentJobSnapshot | None:
            calls.append(
                (
                    "claim",
                    (
                        requested_job_id,
                        stage_count,
                        nlp_config_revision_id,
                        nlp_config_revision,
                    ),
                )
            )
            return EnrichmentJobSnapshot(
                id=job_id,
                input_text="помогите собрать комплект видеонаблюдения",
                status=EnrichmentStatus.RUNNING,
                progress_percent=1,
                current_stage="queued",
                stage_index=0,
                stage_count=stage_count,
                stage_progress_percent=0,
                message="running",
                result=None,
                error=None,
                created_at=datetime(2026, 5, 9, tzinfo=UTC),
                started_at=datetime(2026, 5, 9, tzinfo=UTC),
                finished_at=None,
                nlp_config_revision_id=revision_id,
                nlp_config_revision=77,
            )

        async def record_stage_progress(self, *args: object, **kwargs: object) -> None:
            calls.append(("progress", kwargs))

        async def complete_job(self, requested_job_id: object, completed_result: object) -> None:
            calls.append(("complete", (requested_job_id, completed_result)))

        async def fail_job(self, requested_job_id: object, error: object) -> None:
            calls.append(("fail", (requested_job_id, error)))

    class ActiveRevisionRepository:
        def __init__(self, session_factory: object) -> None:
            pass

        async def get_active_or_seed(self, default_documents: object) -> NlpConfigRevision:
            calls.append(("active_revision", default_documents))
            return NlpConfigRevision(
                id=revision_id,
                revision=77,
                documents={"pipeline": {"stages": []}},
                source="test",
                created_at=datetime(2026, 5, 9, tzinfo=UTC),
            )

    class FakeEnricher:
        def __init__(self, config: object) -> None:
            calls.append(("enricher", config))

        def enrich(self, text: str, progress: object | None = None) -> object:
            calls.append(("enrich", text))
            return result

    async def no_notifications(session_factory: object, completed_result: object, requested_job_id: object) -> None:
        calls.append(("notifications", (completed_result, requested_job_id)))

    monkeypatch.setattr(tasks, "create_sessionmaker", lambda: object())
    monkeypatch.setattr(tasks, "PostgresEnrichmentJobRepository", RecordingRepository)
    monkeypatch.setattr(tasks, "PostgresNlpConfigRepository", ActiveRevisionRepository)
    monkeypatch.setattr(tasks, "read_nlp_config_documents", lambda path: {"pipeline": {"stages": []}})
    monkeypatch.setattr(
        tasks,
        "load_nlp_config_from_documents",
        lambda documents: SimpleNamespace(enabled_stages=[SimpleNamespace(name="segmentation")]),
    )
    monkeypatch.setattr(tasks, "RussianTextEnricher", FakeEnricher)
    monkeypatch.setattr(tasks, "_queue_notifications", no_notifications)
    tasks._PIPELINE_CACHE.clear()

    await tasks._run_enrichment_job(job_id)

    assert (
        "claim",
        (job_id, 1, revision_id, 77),
    ) in calls
    assert ("complete", (job_id, result)) in calls
