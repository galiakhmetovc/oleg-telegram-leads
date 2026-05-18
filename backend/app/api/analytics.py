from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.application.evaluation.review_eval import ReviewEvalReport, build_review_eval_report
from app.db.session import create_sessionmaker
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidateLlmSummary
from app.domain.analytics import AnalyticsMessageReview
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


class AnalyticsCandidateLlmResponse(BaseModel):
    processed: bool
    latest_run_id: str | None = None
    status: str | None = None
    verdict: str | None = None
    confidence: float | None = None
    recommendation: str | None = None
    agrees_with_rule_engine: bool | None = None
    model: str | None = None
    route_id: str | None = None
    attempts: int | None = None
    has_error: bool = False
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    source_type: str = "telegram"
    is_lead: bool = False
    auto_is_lead: bool = False
    effective_is_lead: bool = False
    lead_status_source: Literal["auto", "review"] = "auto"
    message_date: datetime | None = None
    received_at: datetime | None = None
    sender_id: str | None = None
    sender_username: str | None = None
    source_account_id: str | None = None
    source_chat_id: str | None = None
    source_chat_title: str | None = None
    source_input_ref: str | None = None
    source_chat_status: str | None = None
    source_chat_enabled: bool | None = None
    source_chat_last_message_id: int | None = None
    source_chat_last_error: str | None = None
    telegram_chat_id: str | None = None
    telegram_message_id: int | None = None
    telegram_message_url: str | None = None
    app_message_url: str | None = None
    testing_url: str | None = None
    enrichment_job_id: str | None = None
    enrichment_status: str | None = None
    enrichment_created_at: datetime | None = None
    enrichment_started_at: datetime | None = None
    enrichment_finished_at: datetime | None = None
    enrichment_updated_at: datetime | None = None
    enrichment_error: dict[str, Any] | None = None
    raw_payload: dict[str, Any]
    llm: AnalyticsCandidateLlmResponse | None = None
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


class ReviewEvalExampleResponse(BaseModel):
    source_message_id: str
    telegram_message_id: int | None = None
    source_chat_title: str | None = None
    verdict: str | None = None
    predicted_is_lead: bool | None = None
    score: int
    temperature: str
    review_lane: str
    text_preview: str


class ReviewEvalReportResponse(BaseModel):
    reviewed: int
    evaluated: int
    skipped_uncertain: int
    skipped_missing_prediction: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    specificity: float
    accuracy: float
    f1: float
    by_verdict: dict[str, int]
    false_positives: list[ReviewEvalExampleResponse]
    false_negatives: list[ReviewEvalExampleResponse]


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


@router.get("/review-eval", response_model=ReviewEvalReportResponse)
async def get_review_eval_report(
    limit: int | None = Query(default=None, ge=1, le=10000),
    examples: int = Query(default=20, ge=0, le=100),
    repository: PostgresAnalyticsRepository = Depends(get_analytics_repository),
) -> ReviewEvalReportResponse:
    rows = await repository.list_review_eval_rows(limit=limit)
    return _review_eval_response(build_review_eval_report(rows, example_limit=examples))


@router.get("/runs/{run_id}/candidates", response_model=AnalyticsCandidatePageResponse)
async def list_analytics_candidates(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    score_min: int | None = Query(default=None, ge=0),
    temperature: str | None = None,
    score_max: int | None = Query(default=None, ge=0),
    signal: str | None = None,
    reason: str | None = None,
    solution_area: str | None = None,
    customer_segment: str | None = None,
    lane: str | None = None,
    message_id: str | None = Query(default=None, min_length=1),
    source_chat: str | None = Query(default=None, min_length=1),
    source_chat_id: str | None = None,
    source_input_ref: str | None = Query(default=None, min_length=1),
    source_chat_status: str | None = Query(default=None, min_length=1),
    telegram_message_id: int | None = Query(default=None, ge=0),
    telegram_chat_id: str | None = Query(default=None, min_length=1),
    sender: str | None = Query(default=None, min_length=1),
    source_account_id: str | None = Query(default=None, min_length=1),
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    review_status: Literal["reviewed", "unreviewed"] | None = None,
    verdict: AnalyticsReviewVerdict | None = None,
    source_type: Literal["telegram", "max"] | None = None,
    llm_processed: bool | None = None,
    llm_status: str | None = None,
    llm_verdict: str | None = None,
    llm_recommendation: str | None = None,
    llm_model: str | None = None,
    llm_route: str | None = None,
    llm_agrees_with_rules: bool | None = None,
    llm_has_error: bool | None = None,
    llm_confidence_min: float | None = Query(default=None, ge=0, le=1),
    llm_confidence_max: float | None = Query(default=None, ge=0, le=1),
    llm_attempts_min: int | None = Query(default=None, ge=0),
    llm_attempts_max: int | None = Query(default=None, ge=0),
    enrichment_status: str | None = Query(default=None, min_length=1),
    sort_by: str | None = Query(default=None, min_length=1),
    sort_direction: Literal["asc", "desc"] | None = None,
    q: str | None = Query(default=None, min_length=1),
    grid_filter: list[str] | None = Query(default=None),
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
        score_max=score_max,
        temperature=temperature,
        signal=signal,
        reason=reason,
        solution_area=solution_area,
        customer_segment=customer_segment,
        lane=lane,
        message_id=message_id,
        source_chat=source_chat,
        source_chat_id=source_chat_id,
        source_input_ref=source_input_ref,
        source_chat_status=source_chat_status,
        telegram_message_id=telegram_message_id,
        telegram_chat_id=telegram_chat_id,
        sender=sender,
        source_account_id=source_account_id,
        received_from=received_from,
        received_to=received_to,
        review_status=review_status,
        verdict=verdict,
        source_type=source_type,
        llm_processed=llm_processed,
        llm_status=llm_status,
        llm_verdict=llm_verdict,
        llm_recommendation=llm_recommendation,
        llm_model=llm_model,
        llm_route=llm_route,
        llm_agrees_with_rules=llm_agrees_with_rules,
        llm_has_error=llm_has_error,
        llm_confidence_min=llm_confidence_min,
        llm_confidence_max=llm_confidence_max,
        llm_attempts_min=llm_attempts_min,
        llm_attempts_max=llm_attempts_max,
        enrichment_status=enrichment_status,
        sort_by=sort_by,
        sort_direction=sort_direction,
        q=q,
        grid_filters=_parse_grid_filters(grid_filter),
    )
    return AnalyticsCandidatePageResponse(
        total=page.total,
        limit=limit,
        offset=offset,
        items=[_candidate_response(candidate) for candidate in page.items],
    )


def _parse_grid_filters(values: list[str] | None) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    for raw in values or []:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        field = str(parsed.get("field") or "").strip()
        operator = str(parsed.get("operator") or "").strip() or "contains"
        value = str(parsed.get("value") or "").strip()
        if field and value:
            filters.append({"field": field, "operator": operator, "value": value})
    return filters


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


def _review_eval_response(report: ReviewEvalReport) -> ReviewEvalReportResponse:
    return ReviewEvalReportResponse.model_validate(report.to_dict())


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
        source_type=candidate.source_type,
        is_lead=effective_is_lead,
        auto_is_lead=candidate.is_lead,
        effective_is_lead=effective_is_lead,
        lead_status_source=lead_status_source,
        message_date=candidate.message_date,
        received_at=candidate.received_at,
        sender_id=candidate.sender_id,
        sender_username=candidate.sender_username,
        source_account_id=candidate.source_account_id,
        source_chat_id=candidate.source_chat_id,
        source_chat_title=candidate.source_chat_title,
        source_input_ref=candidate.source_input_ref,
        source_chat_status=candidate.source_chat_status,
        source_chat_enabled=candidate.source_chat_enabled,
        source_chat_last_message_id=candidate.source_chat_last_message_id,
        source_chat_last_error=candidate.source_chat_last_error,
        telegram_chat_id=candidate.telegram_chat_id,
        telegram_message_id=candidate.telegram_message_id,
        telegram_message_url=candidate.telegram_message_url,
        app_message_url=candidate.app_message_url,
        testing_url=candidate.testing_url,
        enrichment_job_id=candidate.enrichment_job_id,
        enrichment_status=candidate.enrichment_status,
        enrichment_created_at=candidate.enrichment_created_at,
        enrichment_started_at=candidate.enrichment_started_at,
        enrichment_finished_at=candidate.enrichment_finished_at,
        enrichment_updated_at=candidate.enrichment_updated_at,
        enrichment_error=candidate.enrichment_error,
        raw_payload=candidate.raw_payload,
        llm=_candidate_llm_response(candidate.llm),
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


def _candidate_llm_response(llm: AnalyticsCandidateLlmSummary | None) -> AnalyticsCandidateLlmResponse | None:
    if llm is None:
        return None
    return AnalyticsCandidateLlmResponse(
        processed=llm.processed,
        latest_run_id=llm.latest_run_id,
        status=llm.status,
        verdict=llm.verdict,
        confidence=llm.confidence,
        recommendation=llm.recommendation,
        agrees_with_rule_engine=llm.agrees_with_rule_engine,
        model=llm.model,
        route_id=llm.route_id,
        attempts=llm.attempts,
        has_error=llm.has_error,
        error=llm.error,
        created_at=llm.created_at,
        updated_at=llm.updated_at,
    )


def _normalized_review_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        value = tag.strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized
