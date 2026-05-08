from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot, EnrichmentStatus
from app.domain.enrichment import EnrichmentTaskOutboxItem, TextEnrichmentResult
from app.infrastructure.persistence.runtime_retention import trim_enrichment_events
from app.infrastructure.persistence.tables import enrichment_events, enrichment_jobs
from app.infrastructure.persistence.tables import enrichment_results
from app.infrastructure.persistence.tables import enrichment_task_outbox

ENRICHMENT_TASK_NAME = "app.worker.tasks.enrich_text_job"
TASK_CLAIM_TIMEOUT = timedelta(minutes=5)


class PostgresEnrichmentJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_job(self, input_text: str, *, publish_ready: bool = False) -> EnrichmentJobSnapshot:
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
            await session.execute(
                enrichment_task_outbox.insert().values(
                    job_id=job_id,
                    task_name=ENRICHMENT_TASK_NAME,
                    status="pending" if publish_ready else "blocked",
                    attempts=0,
                    last_error=None,
                    claimed_at=None,
                    created_at=now,
                    updated_at=now,
                    published_at=None,
                )
            )
            await session.commit()

        snapshot = await self.get_job(job_id)
        if snapshot is None:
            raise RuntimeError("created enrichment job is not readable")
        return snapshot

    async def discard_unpublished_job(self, job_id: UUID) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(enrichment_jobs.c.id)
                .where(enrichment_jobs.c.id == job_id)
                .where(enrichment_jobs.c.status == EnrichmentStatus.QUEUED.value)
                .where(enrichment_jobs.c.started_at.is_(None))
            )
            if result.scalar_one_or_none() is not None:
                await session.execute(enrichment_task_outbox.delete().where(enrichment_task_outbox.c.job_id == job_id))
                await session.execute(enrichment_events.delete().where(enrichment_events.c.job_id == job_id))
                await session.execute(enrichment_jobs.delete().where(enrichment_jobs.c.id == job_id))
            await session.commit()

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

    async def mark_task_pending(self, job_id: UUID) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            await session.execute(
                enrichment_task_outbox.update()
                .where(enrichment_task_outbox.c.job_id == job_id)
                .where(enrichment_task_outbox.c.status != "published")
                .values(
                    status="pending",
                    claimed_at=None,
                    updated_at=now,
                )
            )
            await session.commit()

    async def claim_pending_tasks(
        self,
        *,
        limit: int,
        job_id: UUID | None = None,
    ) -> list[EnrichmentTaskOutboxItem]:
        now = datetime.now(UTC)
        stale_before = now - TASK_CLAIM_TIMEOUT
        job_filter = ""
        parameters: dict[str, Any] = {
            "limit": limit,
            "claimed_at": now,
            "stale_before": stale_before,
        }
        if job_id is not None:
            job_filter = "and job_id = :job_id"
            parameters["job_id"] = job_id
        async with self._session_factory() as session:
            result = await session.execute(
                sa.text(
                    f"""
                    with next_items as (
                        select job_id
                        from enrichment_task_outbox
                        where (
                            status = 'pending'
                            or (status = 'sending' and claimed_at < :stale_before)
                        )
                        {job_filter}
                        order by created_at asc, job_id asc
                        limit :limit
                        for update skip locked
                    )
                    update enrichment_task_outbox
                    set status = 'sending',
                        attempts = attempts + 1,
                        claimed_at = :claimed_at,
                        updated_at = :claimed_at
                    where job_id in (select job_id from next_items)
                    returning job_id,
                              task_name,
                              status,
                              attempts,
                              last_error,
                              claimed_at,
                              created_at,
                              updated_at,
                              published_at
                    """
                ),
                parameters,
            )
            rows = result.mappings().all()
            await session.commit()
        return [_task_outbox_item_from_row(row) for row in rows]

    async def mark_tasks_published(self, job_ids: list[UUID]) -> None:
        if not job_ids:
            return
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            await session.execute(
                enrichment_task_outbox.update()
                .where(enrichment_task_outbox.c.job_id.in_(job_ids))
                .values(
                    status="published",
                    last_error=None,
                    claimed_at=None,
                    updated_at=now,
                    published_at=now,
                )
            )
            await session.commit()

    async def release_tasks(self, job_ids: list[UUID], *, error: str) -> None:
        if not job_ids:
            return
        async with self._session_factory() as session:
            await session.execute(
                enrichment_task_outbox.update()
                .where(enrichment_task_outbox.c.job_id.in_(job_ids))
                .where(enrichment_task_outbox.c.status == "sending")
                .values(
                    status="pending",
                    last_error=error,
                    claimed_at=None,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def claim_queued_job(self, job_id: UUID, *, stage_count: int) -> EnrichmentJobSnapshot | None:
        async with self._session_factory() as session:
            result = await session.execute(
                enrichment_jobs.update()
                .where(enrichment_jobs.c.id == job_id)
                .where(enrichment_jobs.c.status == EnrichmentStatus.QUEUED.value)
                .values(
                    status=EnrichmentStatus.RUNNING.value,
                    progress_percent=1,
                    current_stage="queued",
                    stage_index=0,
                    stage_count=stage_count,
                    stage_progress_percent=0,
                    message="Обработка запущена",
                    started_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                .returning(enrichment_jobs)
            )
            row = result.mappings().first()
            if row is None:
                await session.commit()
                return None
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
        return _job_from_row(row)

    async def mark_running(self, job_id: UUID, *, stage_count: int) -> None:
        await self.claim_queued_job(job_id, stage_count=stage_count)

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


def _task_outbox_item_from_row(row: Any) -> EnrichmentTaskOutboxItem:
    return EnrichmentTaskOutboxItem(
        job_id=row["job_id"],
        task_name=row["task_name"],
        status=row["status"],
        attempts=row["attempts"],
        last_error=row["last_error"],
        claimed_at=row["claimed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
    )
