from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.session import create_sessionmaker
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsRun
from app.infrastructure.persistence.analytics_repository import PostgresAnalyticsRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalyticsRunResponse(BaseModel):
    id: UUID
    name: str
    source: str
    input_path: str
    run_dir: str
    processed: int
    skipped: int
    failed: int
    leads: int
    candidate_rate: float
    started_at: datetime | None
    finished_at: datetime | None
    imported_at: datetime
    summary: dict[str, Any]


class AnalyticsRunsResponse(BaseModel):
    runs: list[AnalyticsRunResponse]


class AnalyticsAggregateResponse(BaseModel):
    kind: str
    key: str
    label: str
    count: int
    payload: dict[str, Any]


class AnalyticsSummaryResponse(BaseModel):
    run: AnalyticsRunResponse
    aggregates: dict[str, list[AnalyticsAggregateResponse]]


class AnalyticsCandidateResponse(BaseModel):
    message_id: str
    text: str
    score: int
    temperature: str
    review_lane: str
    solution_areas: list[dict[str, Any]]
    customer_segments: list[dict[str, Any]]
    intent_signals: list[dict[str, Any]]
    noise_signals: list[dict[str, Any]]
    reasons: list[dict[str, Any]]
    domain_signals: list[dict[str, Any]]
    facts: list[dict[str, Any]]


class AnalyticsCandidatePageResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AnalyticsCandidateResponse]


def get_analytics_repository() -> PostgresAnalyticsRepository:
    return PostgresAnalyticsRepository(create_sessionmaker())


@router.get("/runs", response_model=AnalyticsRunsResponse)
async def list_analytics_runs(
    repository: PostgresAnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsRunsResponse:
    return AnalyticsRunsResponse(
        runs=[_run_response(run) for run in await repository.list_runs()],
    )


@router.get("/runs/{run_id}/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    run_id: UUID,
    repository: PostgresAnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsSummaryResponse:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analytics run not found")

    grouped: dict[str, list[AnalyticsAggregateResponse]] = defaultdict(list)
    for aggregate in await repository.list_aggregates(run_id):
        grouped[aggregate.kind].append(_aggregate_response(aggregate))

    return AnalyticsSummaryResponse(run=_run_response(run), aggregates=dict(grouped))


@router.get("/runs/{run_id}/candidates", response_model=AnalyticsCandidatePageResponse)
async def list_analytics_candidates(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    score_min: int | None = Query(default=None, ge=0),
    temperature: str | None = None,
    signal: str | None = None,
    reason: str | None = None,
    solution_area: str | None = None,
    customer_segment: str | None = None,
    lane: str | None = None,
    q: str | None = Query(default=None, min_length=1),
    repository: PostgresAnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsCandidatePageResponse:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analytics run not found")

    page = await repository.list_candidates(
        run_id,
        limit=limit,
        offset=offset,
        score_min=score_min,
        temperature=temperature,
        signal=signal,
        reason=reason,
        solution_area=solution_area,
        customer_segment=customer_segment,
        lane=lane,
        q=q,
    )
    return AnalyticsCandidatePageResponse(
        total=page.total,
        limit=limit,
        offset=offset,
        items=[_candidate_response(candidate) for candidate in page.items],
    )


def _run_response(run: AnalyticsRun) -> AnalyticsRunResponse:
    return AnalyticsRunResponse(
        id=run.id,
        name=run.name,
        source=run.source,
        input_path=run.input_path,
        run_dir=run.run_dir,
        processed=run.processed,
        skipped=run.skipped,
        failed=run.failed,
        leads=run.leads,
        candidate_rate=run.candidate_rate,
        started_at=run.started_at,
        finished_at=run.finished_at,
        imported_at=run.imported_at,
        summary=run.summary,
    )


def _aggregate_response(aggregate: AnalyticsAggregate) -> AnalyticsAggregateResponse:
    return AnalyticsAggregateResponse(
        kind=aggregate.kind,
        key=aggregate.key,
        label=aggregate.label,
        count=aggregate.count,
        payload=aggregate.payload,
    )


def _candidate_response(candidate: AnalyticsCandidate) -> AnalyticsCandidateResponse:
    return AnalyticsCandidateResponse(
        message_id=candidate.message_id,
        text=candidate.text,
        score=candidate.score,
        temperature=candidate.temperature,
        review_lane=candidate.review_lane,
        solution_areas=candidate.solution_areas,
        customer_segments=candidate.customer_segments,
        intent_signals=candidate.intent_signals,
        noise_signals=candidate.noise_signals,
        reasons=candidate.reasons,
        domain_signals=candidate.domain_signals,
        facts=candidate.facts,
    )
