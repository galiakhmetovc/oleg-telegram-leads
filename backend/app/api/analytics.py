from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.session import create_sessionmaker
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsMessageReview
from app.domain.analytics import AnalyticsReviewVerdict
from app.domain.analytics import AnalyticsRun
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
    is_lead: bool = False
    auto_is_lead: bool = False
    effective_is_lead: bool = False
    lead_status_source: Literal["auto", "review"] = "auto"
    received_at: datetime | None = None
    source_chat_id: str | None = None
    source_chat_title: str | None = None
    telegram_chat_id: str | None = None
    telegram_message_id: int | None = None
    telegram_message_url: str | None = None
    app_message_url: str | None = None
    testing_url: str | None = None
    enrichment_job_id: str | None = None
    review: AnalyticsMessageReviewResponse | None = None


class AnalyticsMessageReviewResponse(BaseModel):
    source_message_id: str
    verdict: AnalyticsReviewVerdict | None
    comment: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class AnalyticsMessageReviewUpdate(BaseModel):
    verdict: AnalyticsReviewVerdict | None = None
    comment: str = ""
    tags: list[str] = []


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
    source_chat_id: str | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    review_status: Literal["reviewed", "unreviewed"] | None = None,
    verdict: AnalyticsReviewVerdict | None = None,
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
        source_chat_id=source_chat_id,
        received_from=received_from,
        received_to=received_to,
        review_status=review_status,
        verdict=verdict,
        q=q,
    )
    return AnalyticsCandidatePageResponse(
        total=page.total,
        limit=limit,
        offset=offset,
        items=[_candidate_response(candidate) for candidate in page.items],
    )


@router.get("/messages/{message_id}", response_model=AnalyticsCandidateResponse)
async def get_analytics_message(
    message_id: str,
    repository: PostgresAnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsCandidateResponse:
    candidate = await repository.get_live_candidate_by_message_id(message_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="analytics message not found")
    review = await repository.get_message_review(message_id)
    return _candidate_response(candidate, review=review)


@router.put("/messages/{message_id}/review", response_model=AnalyticsCandidateResponse)
async def update_analytics_message_review(
    message_id: str,
    payload: AnalyticsMessageReviewUpdate,
    repository: PostgresAnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsCandidateResponse:
    candidate = await repository.get_live_candidate_by_message_id(message_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="analytics message not found")
    review = await repository.save_message_review(
        message_id=message_id,
        verdict=payload.verdict,
        comment=payload.comment.strip(),
        tags=_normalized_review_tags(payload.tags),
    )
    if payload.verdict in {"not_lead", "noise"}:
        await repository.cancel_unsent_notifications_for_message(
            message_id,
            reason=f"review:{payload.verdict}",
        )
    return _candidate_response(candidate, review=review)


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


def _candidate_response(
    candidate: AnalyticsCandidate,
    *,
    review: AnalyticsMessageReview | None = None,
) -> AnalyticsCandidateResponse:
    review_value = review if review is not None else candidate.review
    effective_is_lead, lead_status_source = _effective_lead_status(candidate, review_value)
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
        is_lead=effective_is_lead,
        auto_is_lead=candidate.is_lead,
        effective_is_lead=effective_is_lead,
        lead_status_source=lead_status_source,
        received_at=candidate.received_at,
        source_chat_id=candidate.source_chat_id,
        source_chat_title=candidate.source_chat_title,
        telegram_chat_id=candidate.telegram_chat_id,
        telegram_message_id=candidate.telegram_message_id,
        telegram_message_url=candidate.telegram_message_url,
        app_message_url=candidate.app_message_url,
        testing_url=candidate.testing_url,
        enrichment_job_id=candidate.enrichment_job_id,
        review=_review_response(review_value) if review_value is not None else None,
    )


def _effective_lead_status(
    candidate: AnalyticsCandidate,
    review: AnalyticsMessageReview | None,
) -> tuple[bool, Literal["auto", "review"]]:
    if review is None or review.verdict is None or review.verdict == "uncertain":
        return candidate.is_lead, "auto"
    if review.verdict == "lead":
        return True, "review"
    return False, "review"


def _review_response(review: AnalyticsMessageReview) -> AnalyticsMessageReviewResponse:
    return AnalyticsMessageReviewResponse(
        source_message_id=review.source_message_id,
        verdict=review.verdict,
        comment=review.comment,
        tags=review.tags,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _normalized_review_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        value = tag.strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized
