from __future__ import annotations

from uuid import UUID

from app.application.enrichment.ports import EnrichmentJobRepository, EnrichmentTaskOutboxRepository
from app.application.enrichment.ports import EnrichmentTaskPublisher
from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentTaskOutboxItem

DEFAULT_ENRICHMENT_TASK_LIMIT = 100


class CreateEnrichmentJob:
    def __init__(
        self,
        *,
        repository: EnrichmentJobRepository,
        task_publisher: EnrichmentTaskPublisher,
        task_outbox_repository: EnrichmentTaskOutboxRepository,
    ) -> None:
        self._repository = repository
        self._task_publisher = task_publisher
        self._task_outbox_repository = task_outbox_repository

    async def execute(self, input_text: str) -> EnrichmentJobSnapshot:
        job = await self._create(input_text, publish_ready=True)
        await self.publish(job.id)
        return job

    async def create(self, input_text: str) -> EnrichmentJobSnapshot:
        return await self._create(input_text, publish_ready=False)

    async def _create(self, input_text: str, *, publish_ready: bool) -> EnrichmentJobSnapshot:
        stripped_text = input_text.strip()
        if not stripped_text:
            raise ValueError("input text is empty")

        return await self._repository.create_job(stripped_text, publish_ready=publish_ready)

    async def discard_unpublished(self, job_id: UUID) -> None:
        await self._repository.discard_unpublished_job(job_id)

    async def publish(self, job_id: UUID) -> None:
        await self._task_outbox_repository.mark_task_pending(job_id)
        await DispatchEnrichmentTasks(
            task_outbox_repository=self._task_outbox_repository,
            task_publisher=self._task_publisher,
        ).execute(limit=1, job_id=job_id)


class GetEnrichmentJob:
    def __init__(self, *, repository: EnrichmentJobRepository) -> None:
        self._repository = repository

    async def execute(self, job_id: UUID) -> EnrichmentJobSnapshot | None:
        return await self._repository.get_job(job_id)


class DispatchEnrichmentTasks:
    def __init__(
        self,
        *,
        task_outbox_repository: EnrichmentTaskOutboxRepository,
        task_publisher: EnrichmentTaskPublisher,
    ) -> None:
        self._task_outbox_repository = task_outbox_repository
        self._task_publisher = task_publisher

    async def execute(
        self,
        *,
        limit: int = DEFAULT_ENRICHMENT_TASK_LIMIT,
        job_id: UUID | None = None,
    ) -> list[EnrichmentTaskOutboxItem]:
        claimed = await self._task_outbox_repository.claim_pending_tasks(limit=limit, job_id=job_id)
        published: list[EnrichmentTaskOutboxItem] = []
        for item in claimed:
            try:
                await self._task_publisher.publish(item.job_id)
            except Exception as exc:
                await self._task_outbox_repository.release_tasks(
                    [item.job_id],
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue
            await self._task_outbox_repository.mark_tasks_published([item.job_id])
            published.append(item)
        return published
