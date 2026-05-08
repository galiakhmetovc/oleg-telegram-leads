from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot, EnrichmentStatus
from app.domain.enrichment import TextEnrichmentResult
from app.infrastructure.persistence.runtime_retention import trim_enrichment_events
from app.infrastructure.persistence.tables import enrichment_events, enrichment_jobs
from app.infrastructure.persistence.tables import enrichment_results


class PostgresEnrichmentJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_job(self, input_text: str) -> EnrichmentJobSnapshot:
        job_id = uuid4()
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            await session.execute(
                enrichment_jobs.insert().values(
                    id=job_id,
                    input_text=input_text,
                    status=EnrichmentStatus.QUEUED.value,
                    progress_percent=0,
                    current_stage=None,
                    stage_index=0,
                    stage_count=0,
                    stage_progress_percent=0,
                    message="Задача поставлена в очередь",
                    error=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await self._insert_event(
                session,
                job_id=job_id,
                event_type="job_queued",
                progress_percent=0,
                current_stage=None,
                stage_index=0,
                stage_count=0,
                stage_progress_percent=0,
                message="Задача поставлена в очередь",
                payload={},
            )
            await session.commit()

        snapshot = await self.get_job(job_id)
        if snapshot is None:
            raise RuntimeError("created enrichment job is not readable")
        return snapshot

    async def get_job(self, job_id: UUID) -> EnrichmentJobSnapshot | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(enrichment_jobs, enrichment_results.c.result)
                .select_from(
                    enrichment_jobs.outerjoin(
                        enrichment_results,
                        enrichment_jobs.c.id == enrichment_results.c.job_id,
                    )
                )
                .where(enrichment_jobs.c.id == job_id)
            )
            row = result.mappings().first()
        return _job_from_row(row) if row is not None else None

    async def list_events_after(self, job_id: UUID, after_sequence: int) -> list[EnrichmentEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(enrichment_events)
                .where(enrichment_events.c.job_id == job_id)
                .where(enrichment_events.c.sequence > after_sequence)
                .order_by(enrichment_events.c.sequence.asc())
            )
            rows = result.mappings().all()
        return [_event_from_row(row) for row in rows]

    async def iter_events(
        self,
        job_id: UUID,
        *,
        after_sequence: int = 0,
        poll_interval_seconds: float = 0.3,
    ) -> AsyncIterator[EnrichmentEvent]:
        last_sequence = after_sequence
        while True:
            events = await self.list_events_after(job_id, last_sequence)
            for event in events:
                last_sequence = event.sequence
                yield event

            snapshot = await self.get_job(job_id)
            if snapshot is None or snapshot.status in {EnrichmentStatus.COMPLETED, EnrichmentStatus.FAILED}:
                if not events:
                    break

            await asyncio.sleep(poll_interval_seconds)

    async def mark_running(self, job_id: UUID, *, stage_count: int) -> None:
        async with self._session_factory() as session:
            await self._update_job(
                session,
                job_id,
                status=EnrichmentStatus.RUNNING,
                progress_percent=1,
                current_stage="queued",
                stage_index=0,
                stage_count=stage_count,
                stage_progress_percent=0,
                message="Обработка запущена",
                started_at=datetime.now(UTC),
            )
            await self._insert_event(
                session,
                job_id=job_id,
                event_type="job_started",
                progress_percent=1,
                current_stage="queued",
                stage_index=0,
                stage_count=stage_count,
                stage_progress_percent=0,
                message="Обработка запущена",
                payload={},
            )
            await session.commit()

    async def record_stage_progress(
        self,
        job_id: UUID,
        *,
        stage_name: str,
        stage_index: int,
        stage_count: int,
        progress_percent: int,
        message: str,
    ) -> None:
        async with self._session_factory() as session:
            await self._update_job(
                session,
                job_id,
                status=EnrichmentStatus.RUNNING,
                progress_percent=progress_percent,
                current_stage=stage_name,
                stage_index=stage_index,
                stage_count=stage_count,
                stage_progress_percent=100,
                message=message,
            )
            await self._insert_event(
                session,
                job_id=job_id,
                event_type="stage_completed",
                progress_percent=progress_percent,
                current_stage=stage_name,
                stage_index=stage_index,
                stage_count=stage_count,
                stage_progress_percent=100,
                message=message,
                payload={"stage": stage_name},
            )
            await session.commit()

    async def complete_job(self, job_id: UUID, result: TextEnrichmentResult) -> None:
        async with self._session_factory() as session:
            result_payload = result.to_dict()
            await session.execute(
                insert(enrichment_results)
                .values(job_id=job_id, result=result_payload)
                .on_conflict_do_update(
                    index_elements=[enrichment_results.c.job_id],
                    set_={"result": result_payload, "created_at": datetime.now(UTC)},
                )
            )
            await self._update_job(
                session,
                job_id,
                status=EnrichmentStatus.COMPLETED,
                progress_percent=100,
                current_stage="completed",
                stage_index=0,
                stage_count=0,
                stage_progress_percent=100,
                message="Обработка завершена",
                finished_at=datetime.now(UTC),
            )
            await self._insert_event(
                session,
                job_id=job_id,
                event_type="job_completed",
                progress_percent=100,
                current_stage="completed",
                stage_index=0,
                stage_count=0,
                stage_progress_percent=100,
                message="Обработка завершена",
                payload={"result": result_payload},
            )
            await trim_enrichment_events(
                session,
                max_rows=get_settings().runtime_enrichment_event_retention_rows,
            )
            await session.commit()

    async def fail_job(self, job_id: UUID, error: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            await self._update_job(
                session,
                job_id,
                status=EnrichmentStatus.FAILED,
                progress_percent=100,
                current_stage="failed",
                stage_index=0,
                stage_count=0,
                stage_progress_percent=100,
                message="Обработка завершилась ошибкой",
                error=error,
                finished_at=datetime.now(UTC),
            )
            await self._insert_event(
                session,
                job_id=job_id,
                event_type="job_failed",
                progress_percent=100,
                current_stage="failed",
                stage_index=0,
                stage_count=0,
                stage_progress_percent=100,
                message="Обработка завершилась ошибкой",
                payload={"error": error},
            )
            await trim_enrichment_events(
                session,
                max_rows=get_settings().runtime_enrichment_event_retention_rows,
            )
            await session.commit()

    async def _update_job(
        self,
        session: AsyncSession,
        job_id: UUID,
        **values: Any,
    ) -> None:
        if isinstance(values.get("status"), EnrichmentStatus):
            values["status"] = values["status"].value
        values["updated_at"] = datetime.now(UTC)
        await session.execute(
            enrichment_jobs.update()
            .where(enrichment_jobs.c.id == job_id)
            .values(**values)
        )

    async def _insert_event(
        self,
        session: AsyncSession,
        *,
        job_id: UUID,
        event_type: str,
        progress_percent: int,
        current_stage: str | None,
        stage_index: int,
        stage_count: int,
        stage_progress_percent: int,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        await session.execute(
            enrichment_events.insert().values(
                job_id=job_id,
                event_type=event_type,
                progress_percent=progress_percent,
                current_stage=current_stage,
                stage_index=stage_index,
                stage_count=stage_count,
                stage_progress_percent=stage_progress_percent,
                message=message,
                payload=payload,
            )
        )


def _job_from_row(row: Any) -> EnrichmentJobSnapshot:
    result_payload = row.get("result")
    return EnrichmentJobSnapshot(
        id=row["id"],
        input_text=row["input_text"],
        status=EnrichmentStatus(row["status"]),
        progress_percent=row["progress_percent"],
        current_stage=row["current_stage"],
        stage_index=row["stage_index"],
        stage_count=row["stage_count"],
        stage_progress_percent=row["stage_progress_percent"],
        message=row["message"],
        result=TextEnrichmentResult.from_dict(result_payload) if result_payload else None,
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _event_from_row(row: Any) -> EnrichmentEvent:
    return EnrichmentEvent(
        sequence=row["sequence"],
        job_id=row["job_id"],
        event_type=row["event_type"],
        progress_percent=row["progress_percent"],
        current_stage=row["current_stage"],
        stage_index=row["stage_index"],
        stage_count=row["stage_count"],
        stage_progress_percent=row["stage_progress_percent"],
        message=row["message"],
        payload=row["payload"],
        created_at=row["created_at"],
    )
