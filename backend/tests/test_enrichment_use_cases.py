from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.application.enrichment.use_cases import CreateEnrichmentJob
from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot, EnrichmentStatus


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.created_texts: list[str] = []

    async def create_job(self, input_text: str) -> EnrichmentJobSnapshot:
        self.created_texts.append(input_text)
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


@pytest.mark.asyncio
async def test_create_enrichment_job_persists_job_and_publishes_worker_task() -> None:
    repository = InMemoryJobRepository()
    publisher = RecordingTaskPublisher()
    use_case = CreateEnrichmentJob(repository=repository, task_publisher=publisher)

    job = await use_case.execute("Нужна поставка завтра")

    assert repository.created_texts == ["Нужна поставка завтра"]
    assert publisher.published == [job.id]
    assert job.status is EnrichmentStatus.QUEUED


@pytest.mark.asyncio
async def test_create_enrichment_job_rejects_empty_text() -> None:
    use_case = CreateEnrichmentJob(
        repository=InMemoryJobRepository(),
        task_publisher=RecordingTaskPublisher(),
    )

    with pytest.raises(ValueError, match="empty"):
        await use_case.execute("   ")
