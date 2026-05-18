from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from typing import Literal
from uuid import UUID

AnalyticsReviewVerdict = Literal["lead", "not_lead", "uncertain", "noise"]


@dataclass(frozen=True)
class AnalyticsCandidateLlmSummary:
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


@dataclass(frozen=True)
class AnalyticsRun:
    id: UUID
    name: str
    source: str
    input_path: str
    run_dir: str
    processed: int
    skipped: int
    failed: int
    leads: int
    started_at: datetime | None
    finished_at: datetime | None
    imported_at: datetime
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_rate(self) -> float:
        if self.processed <= 0:
            return 0.0
        return round(self.leads * 100 / self.processed, 6)


@dataclass(frozen=True)
class AnalyticsAggregate:
    kind: str
    key: str
    label: str
    count: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyticsCandidate:
    run_id: UUID
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
    raw_payload: dict[str, Any] = field(default_factory=dict)
    llm: AnalyticsCandidateLlmSummary | None = None
    review: AnalyticsMessageReview | None = None


@dataclass(frozen=True)
class AnalyticsCandidatePage:
    total: int
    items: list[AnalyticsCandidate]


@dataclass(frozen=True)
class AnalyticsMessageReview:
    source_message_id: str
    verdict: AnalyticsReviewVerdict | None
    comment: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
