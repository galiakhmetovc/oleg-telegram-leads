from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.enrichment.use_cases import CreateEnrichmentJob
from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot, EnrichmentStatus
from app.domain.enrichment import EnrichmentTaskOutboxItem


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.created_texts: list[str] = []
        self.publish_ready_flags: list[bool] = []

    async def create_job(self, input_text: str, *, publish_ready: bool = False) -> EnrichmentJobSnapshot:
        self.created_texts.append(input_text)
        self.publish_ready_flags.append(publish_ready)
        return EnrichmentJobSnapshot(
            id=uuid4(),
            input_text=input_text,
            status=EnrichmentStatus.QUEUED,
            progress_percent=0,
            current_stage=None,
            stage_index=0,
            stage_count=0,
            stage_progress_percent=0,
            message="Задача поставлена в очередь",
            result=None,
            error=None,
            created_at=None,
            started_at=None,
            finished_at=None,
        )

    async def claim_queued_job(
        self,
        job_id: UUID,
        *,
        stage_count: int,
        nlp_config_revision_id: UUID,
        nlp_config_revision: int,
    ) -> EnrichmentJobSnapshot | None:
        return None

    async def discard_unpublished_job(self, job_id: UUID) -> None:
        return None

    async def get_job(self, job_id: UUID) -> EnrichmentJobSnapshot | None:
        return None

    async def list_events_after(self, job_id: UUID, after_sequence: int) -> list[EnrichmentEvent]:
        return []

    async def iter_events(
        self,
        job_id: UUID,
        *,
        after_sequence: int = 0,
        poll_interval_seconds: float = 0.3,
    ) -> AsyncIterator[EnrichmentEvent]:
        if False:
            yield cast(EnrichmentEvent, None)


class RecordingTaskPublisher:
    def __init__(self) -> None:
        self.published: list[UUID] = []

    async def publish(self, job_id: UUID) -> None:
        self.published.append(job_id)


class FailingTaskPublisher:
    def __init__(self) -> None:
        self.published: list[UUID] = []

    async def publish(self, job_id: UUID) -> None:
        self.published.append(job_id)
        raise RuntimeError("broker unavailable")


class InMemoryTaskOutboxRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, EnrichmentTaskOutboxItem] = {}
        self.released_errors: list[str] = []

    async def mark_task_pending(self, job_id: UUID) -> None:
        now = datetime.now(UTC)
        self.items[job_id] = EnrichmentTaskOutboxItem(
            job_id=job_id,
            task_name="app.worker.tasks.enrich_text_job",
            status="pending",
            attempts=0,
            last_error=None,
            claimed_at=None,
            created_at=now,
            updated_at=now,
            published_at=None,
        )

    async def claim_pending_tasks(self, *, limit: int, job_id: UUID | None = None) -> list[EnrichmentTaskOutboxItem]:
        claimed: list[EnrichmentTaskOutboxItem] = []
        for item in self.items.values():
            if job_id is not None and item.job_id != job_id:
                continue
            if item.status != "pending":
                continue
            claimed_item = EnrichmentTaskOutboxItem(
                job_id=item.job_id,
                task_name=item.task_name,
                status="sending",
                attempts=item.attempts + 1,
                last_error=item.last_error,
                claimed_at=datetime.now(UTC),
                created_at=item.created_at,
                updated_at=datetime.now(UTC),
                published_at=item.published_at,
            )
            self.items[item.job_id] = claimed_item
            claimed.append(claimed_item)
            if len(claimed) >= limit:
                break
        return claimed

    async def mark_tasks_published(self, job_ids: list[UUID]) -> None:
        for job_id in job_ids:
            item = self.items[job_id]
            self.items[job_id] = EnrichmentTaskOutboxItem(
                job_id=item.job_id,
                task_name=item.task_name,
                status="published",
                attempts=item.attempts,
                last_error=None,
                claimed_at=None,
                created_at=item.created_at,
                updated_at=datetime.now(UTC),
                published_at=datetime.now(UTC),
            )

    async def release_tasks(self, job_ids: list[UUID], *, error: str) -> None:
        self.released_errors.append(error)
        for job_id in job_ids:
            item = self.items[job_id]
            self.items[job_id] = EnrichmentTaskOutboxItem(
                job_id=item.job_id,
                task_name=item.task_name,
                status="pending",
                attempts=item.attempts,
                last_error=error,
                claimed_at=None,
                created_at=item.created_at,
                updated_at=datetime.now(UTC),
                published_at=item.published_at,
            )


@pytest.mark.asyncio
async def test_create_enrichment_job_persists_job_and_publishes_worker_task() -> None:
    repository = InMemoryJobRepository()
    publisher = RecordingTaskPublisher()
    outbox = InMemoryTaskOutboxRepository()
    use_case = CreateEnrichmentJob(
        repository=repository,
        task_publisher=publisher,
        task_outbox_repository=outbox,
    )

    job = await use_case.execute("Нужна поставка завтра")

    assert repository.created_texts == ["Нужна поставка завтра"]
    assert repository.publish_ready_flags == [True]
    assert publisher.published == [job.id]
    assert outbox.items[job.id].status == "published"
    assert job.status is EnrichmentStatus.QUEUED


@pytest.mark.asyncio
async def test_create_enrichment_job_keeps_retryable_outbox_item_when_publish_fails() -> None:
    repository = InMemoryJobRepository()
    publisher = FailingTaskPublisher()
    outbox = InMemoryTaskOutboxRepository()
    use_case = CreateEnrichmentJob(
        repository=repository,
        task_publisher=publisher,
        task_outbox_repository=outbox,
    )

    job = await use_case.execute("Нужна поставка завтра")

    assert publisher.published == [job.id]
    assert outbox.items[job.id].status == "pending"
    assert outbox.items[job.id].attempts == 1
    assert outbox.items[job.id].last_error == "RuntimeError: broker unavailable"


@pytest.mark.asyncio
async def test_create_enrichment_job_rejects_empty_text() -> None:
    use_case = CreateEnrichmentJob(
        repository=InMemoryJobRepository(),
        task_publisher=RecordingTaskPublisher(),
        task_outbox_repository=InMemoryTaskOutboxRepository(),
    )

    with pytest.raises(ValueError, match="empty"):
        await use_case.execute("   ")
