from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot


class EnrichmentJobRepository(Protocol):
    async def create_job(self, input_text: str) -> EnrichmentJobSnapshot: ...

    async def discard_unpublished_job(self, job_id: UUID) -> None: ...

    async def get_job(self, job_id: UUID) -> EnrichmentJobSnapshot | None: ...

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
