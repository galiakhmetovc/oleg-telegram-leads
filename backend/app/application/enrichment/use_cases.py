from __future__ import annotations

from uuid import UUID

from app.application.enrichment.ports import EnrichmentJobRepository, EnrichmentTaskPublisher
from app.domain.enrichment import EnrichmentJobSnapshot


class CreateEnrichmentJob:
    def __init__(
        self,
        *,
        repository: EnrichmentJobRepository,
        task_publisher: EnrichmentTaskPublisher,
    ) -> None:
        self._repository = repository
        self._task_publisher = task_publisher

    async def execute(self, input_text: str) -> EnrichmentJobSnapshot:
        job = await self.create(input_text)
        await self.publish(job.id)
        return job

    async def create(self, input_text: str) -> EnrichmentJobSnapshot:
        stripped_text = input_text.strip()
        if not stripped_text:
            raise ValueError("input text is empty")

        return await self._repository.create_job(stripped_text)

    async def publish(self, job_id: UUID) -> None:
        await self._task_publisher.publish(job_id)


class GetEnrichmentJob:
    def __init__(self, *, repository: EnrichmentJobRepository) -> None:
        self._repository = repository

    async def execute(self, job_id: UUID) -> EnrichmentJobSnapshot | None:
        return await self._repository.get_job(job_id)
