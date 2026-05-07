from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from app.application.enrichment.use_cases import CreateEnrichmentJob, GetEnrichmentJob
from app.db.session import create_sessionmaker
from app.domain.enrichment import EnrichmentEvent, EnrichmentJobSnapshot, TextEnrichmentResult
from app.infrastructure.persistence.enrichment_repository import PostgresEnrichmentJobRepository
from app.infrastructure.queue.celery_publisher import CeleryEnrichmentTaskPublisher

router = APIRouter(prefix="/enrichments", tags=["enrichments"])


class CreateEnrichmentRequest(BaseModel):
    text: str = Field(min_length=1)


def get_repository() -> PostgresEnrichmentJobRepository:
    return PostgresEnrichmentJobRepository(create_sessionmaker())


def get_task_publisher() -> CeleryEnrichmentTaskPublisher:
    return CeleryEnrichmentTaskPublisher()


@router.post("")
async def create_enrichment(
    request: CreateEnrichmentRequest,
    repository: PostgresEnrichmentJobRepository = Depends(get_repository),
    task_publisher: CeleryEnrichmentTaskPublisher = Depends(get_task_publisher),
) -> dict[str, Any]:
    try:
        job = await CreateEnrichmentJob(
            repository=repository,
            task_publisher=task_publisher,
        ).execute(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return serialize_job(job)


@router.get("/{job_id}")
async def get_enrichment(
    job_id: UUID,
    repository: PostgresEnrichmentJobRepository = Depends(get_repository),
) -> dict[str, Any]:
    job = await GetEnrichmentJob(repository=repository).execute(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="enrichment job not found")
    return serialize_job(job)


@router.get("/{job_id}/events")
async def stream_enrichment_events(
    job_id: UUID,
    repository: PostgresEnrichmentJobRepository = Depends(get_repository),
) -> EventSourceResponse:
    if await repository.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="enrichment job not found")

    async def event_generator() -> Any:
        async for event in repository.iter_events(job_id):
            yield ServerSentEvent(
                data=json.dumps(serialize_event(event), ensure_ascii=False),
                event=event.event_type,
                id=str(event.sequence),
            )

    return EventSourceResponse(event_generator())


def serialize_job(job: EnrichmentJobSnapshot) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "input_text": job.input_text,
        "status": job.status.value,
        "progress_percent": job.progress_percent,
        "current_stage": job.current_stage,
        "stage_index": job.stage_index,
        "stage_count": job.stage_count,
        "stage_progress_percent": job.stage_progress_percent,
        "message": job.message,
        "result": _to_jsonable(job.result),
        "error": job.error,
        "created_at": _datetime_or_none(job.created_at),
        "started_at": _datetime_or_none(job.started_at),
        "finished_at": _datetime_or_none(job.finished_at),
    }


def serialize_event(event: EnrichmentEvent) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "job_id": str(event.job_id),
        "event_type": event.event_type,
        "progress_percent": event.progress_percent,
        "current_stage": event.current_stage,
        "stage_index": event.stage_index,
        "stage_count": event.stage_count,
        "stage_progress_percent": event.stage_progress_percent,
        "message": event.message,
        "payload": _to_jsonable(event.payload),
        "created_at": event.created_at.isoformat(),
    }


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, TextEnrichmentResult):
        return _to_jsonable(value.to_dict())
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _datetime_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
