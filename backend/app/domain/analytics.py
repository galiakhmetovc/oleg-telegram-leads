from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


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
    solution_areas: list[dict[str, Any]]
    customer_segments: list[dict[str, Any]]
    intent_signals: list[dict[str, Any]]
    noise_signals: list[dict[str, Any]]
    reasons: list[dict[str, Any]]
    domain_signals: list[dict[str, Any]]
    facts: list[dict[str, Any]]


@dataclass(frozen=True)
class AnalyticsCandidatePage:
    total: int
    items: list[AnalyticsCandidate]
