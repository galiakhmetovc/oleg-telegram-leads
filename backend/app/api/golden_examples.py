from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.enrichments import get_repository as _get_enrichment_repository
from app.api.enrichments import get_task_publisher, serialize_job
from app.application.enrichment.use_cases import CreateEnrichmentJob
from app.db.session import create_sessionmaker
from app.domain.golden_examples import GoldenExample
from app.infrastructure.persistence.enrichment_repository import PostgresEnrichmentJobRepository
from app.infrastructure.persistence.golden_examples_repository import PostgresGoldenExamplesRepository
from app.infrastructure.queue.celery_publisher import CeleryEnrichmentTaskPublisher

router = APIRouter(prefix="/golden-examples", tags=["golden-examples"])

GoldenVerdictValue = Literal["lead", "not_lead", "uncertain", "noise"]


class GoldenExampleCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    expected_verdict: GoldenVerdictValue | None = None
    comment: str = ""


class GoldenExampleResponse(BaseModel):
    id: UUID
    title: str
    text: str
    expected_verdict: GoldenVerdictValue | None
    comment: str
    source_message_id: UUID | None
    source_chat_title: str | None
    telegram_message_id: int | None
    telegram_message_url: str | None
    last_enrichment_job_id: UUID | None
    created_at: datetime
    updated_at: datetime


class GoldenExamplePageResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[GoldenExampleResponse]


class GoldenExampleRunResponse(BaseModel):
    example: GoldenExampleResponse
    job: dict[str, Any]


def get_golden_examples_repository() -> PostgresGoldenExamplesRepository:
    return PostgresGoldenExamplesRepository(create_sessionmaker())


def get_enrichment_repository() -> PostgresEnrichmentJobRepository:
    return _get_enrichment_repository()


@router.get("", response_model=GoldenExamplePageResponse)
async def list_golden_examples(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: PostgresGoldenExamplesRepository = Depends(get_golden_examples_repository),
) -> GoldenExamplePageResponse:
    total, items = await repository.list_examples(limit=limit, offset=offset)
    return GoldenExamplePageResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_golden_example_response(item) for item in items],
    )


@router.post("", response_model=GoldenExampleResponse, status_code=status.HTTP_201_CREATED)
async def create_golden_example(
    request: GoldenExampleCreateRequest,
    repository: PostgresGoldenExamplesRepository = Depends(get_golden_examples_repository),
) -> GoldenExampleResponse:
    stripped_text = request.text.strip()
    if not stripped_text:
        raise HTTPException(status_code=422, detail="input text is empty")
    example = await repository.create_example(
        text=stripped_text,
        title=request.title,
        expected_verdict=request.expected_verdict,
        comment=request.comment,
    )
    return _golden_example_response(example)


@router.post("/from-message/{source_message_id}", response_model=GoldenExampleResponse)
async def create_golden_example_from_message(
    source_message_id: UUID,
    response: Response,
    repository: PostgresGoldenExamplesRepository = Depends(get_golden_examples_repository),
) -> GoldenExampleResponse:
    existing = await repository.get_by_source_message_id(source_message_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _golden_example_response(existing)

    example = await repository.create_from_source_message(source_message_id)
    if example is None:
        raise HTTPException(status_code=404, detail="source message not found")
    response.status_code = status.HTTP_201_CREATED
    return _golden_example_response(example)


@router.post("/{example_id}/run", response_model=GoldenExampleRunResponse)
async def run_golden_example(
    example_id: UUID,
    golden_repository: PostgresGoldenExamplesRepository = Depends(get_golden_examples_repository),
    enrichment_repository: PostgresEnrichmentJobRepository = Depends(get_enrichment_repository),
    task_publisher: CeleryEnrichmentTaskPublisher = Depends(get_task_publisher),
) -> GoldenExampleRunResponse:
    example = await golden_repository.get_example(example_id)
    if example is None:
        raise HTTPException(status_code=404, detail="golden example not found")

    try:
        job = await CreateEnrichmentJob(
            repository=enrichment_repository,
            task_publisher=task_publisher,
            task_outbox_repository=enrichment_repository,
        ).execute(example.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    updated = await golden_repository.set_last_enrichment_job(example_id=example_id, job_id=job.id)
    return GoldenExampleRunResponse(
        example=_golden_example_response(updated or example),
        job=serialize_job(job),
    )


def _golden_example_response(example: GoldenExample) -> GoldenExampleResponse:
    return GoldenExampleResponse(
        id=example.id,
        title=example.title,
        text=example.text,
        expected_verdict=example.expected_verdict,
        comment=example.comment,
        source_message_id=example.source_message_id,
        source_chat_title=example.source_chat_title,
        telegram_message_id=example.telegram_message_id,
        telegram_message_url=example.telegram_message_url,
        last_enrichment_job_id=example.last_enrichment_job_id,
        created_at=example.created_at,
        updated_at=example.updated_at,
    )
