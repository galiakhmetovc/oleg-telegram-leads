from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot, EnrichmentTaskOutboxItem


class EnrichmentJobRepository(Protocol):
    async def create_job(self, input_text: str, *, publish_ready: bool = False) -> EnrichmentJobSnapshot: ...

    async def discard_unpublished_job(self, job_id: UUID) -> None: ...

    async def get_job(self, job_id: UUID) -> EnrichmentJobSnapshot | None: ...

    async def claim_queued_job(
        self,
        job_id: UUID,
        *,
        stage_count: int,
        nlp_config_revision_id: UUID,
        nlp_config_revision: int,
    ) -> EnrichmentJobSnapshot | None: ...

    async def list_events_after(self, job_id: UUID, after_sequence: int) -> list[EnrichmentEvent]: ...

    def iter_events(
        self,
        job_id: UUID,
        *,
        after_sequence: int = 0,
        poll_interval_seconds: float = 0.3,
    ) -> AsyncIterator[EnrichmentEvent]: ...


class EnrichmentTaskPublisher(Protocol):
    async def publish(self, job_id: UUID) -> None: ...


class EnrichmentTaskOutboxRepository(Protocol):
    async def mark_task_pending(self, job_id: UUID) -> None: ...

    async def claim_pending_tasks(
        self,
        *,
        limit: int,
        job_id: UUID | None = None,
    ) -> list[EnrichmentTaskOutboxItem]: ...

    async def mark_tasks_published(self, job_ids: list[UUID]) -> None: ...

    async def release_tasks(self, job_ids: list[UUID], *, error: str) -> None: ...
