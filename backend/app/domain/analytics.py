from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from typing import Literal
from uuid import UUID

AnalyticsReviewVerdict = Literal["lead", "not_lead", "uncertain", "noise"]


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
    is_lead: bool = False
    received_at: datetime | None = None
    source_chat_id: str | None = None
    source_chat_title: str | None = None
    telegram_chat_id: str | None = None
    telegram_message_id: int | None = None
    telegram_message_url: str | None = None
    app_message_url: str | None = None
    testing_url: str | None = None
    enrichment_job_id: str | None = None
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
