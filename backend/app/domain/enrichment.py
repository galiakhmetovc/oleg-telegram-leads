from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class EnrichmentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class TextRange:
    start: int
    stop: int


@dataclass(frozen=True)
class EnrichedSentence:
    id: str
    text: str
    range: TextRange


@dataclass(frozen=True)
class EnrichedToken:
    id: str
    text: str
    range: TextRange
    lemma: str | None
    pos: str | None
    features: dict[str, str]


@dataclass(frozen=True)
class EnrichedEntity:
    id: str
    text: str
    type: str
    range: TextRange
    source: str


@dataclass(frozen=True)
class ExtractedFact:
    id: str
    text: str
    type: str
    label: str
    range: TextRange
    source: str
    confidence: float | None = None


@dataclass(frozen=True)
class DomainSignal:
    id: str
    text: str
    type: str
    label: str
    range: TextRange
    source: str
    confidence: float | None = None
    color: str | None = None


@dataclass(frozen=True)
class SyntaxDependency:
    token_id: str
    head_id: str | None
    relation: str | None


@dataclass(frozen=True)
class EnrichmentMetrics:
    character_count: int
    sentence_count: int
    token_count: int
    entity_count: int
    fact_count: int
    domain_signal_count: int


@dataclass(frozen=True)
class PipelineTraceItem:
    stage: str
    status: str
    message: str
    progress_percent: int


@dataclass(frozen=True)
class TextEnrichmentResult:
    original_text: str
    normalized_text: str
    sentences: list[EnrichedSentence]
    tokens: list[EnrichedToken]
    entities: list[EnrichedEntity]
    facts: list[ExtractedFact]
    domain_signals: list[DomainSignal]
    syntax: list[SyntaxDependency]
    metrics: EnrichmentMetrics
    pipeline_trace: list[PipelineTraceItem]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TextEnrichmentResult:
        return cls(
            original_text=str(data["original_text"]),
            normalized_text=str(data["normalized_text"]),
            sentences=[
                EnrichedSentence(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    range=TextRange(**item["range"]),
                )
                for item in data.get("sentences", [])
            ],
            tokens=[
                EnrichedToken(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    range=TextRange(**item["range"]),
                    lemma=item.get("lemma"),
                    pos=item.get("pos"),
                    features=dict(item.get("features", {})),
                )
                for item in data.get("tokens", [])
            ],
            entities=[
                EnrichedEntity(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    type=str(item["type"]),
                    range=TextRange(**item["range"]),
                    source=str(item["source"]),
                )
                for item in data.get("entities", [])
            ],
            facts=[
                ExtractedFact(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    type=str(item["type"]),
                    label=str(item["label"]),
                    range=TextRange(**item["range"]),
                    source=str(item["source"]),
                    confidence=item.get("confidence"),
                )
                for item in data.get("facts", [])
            ],
            domain_signals=[
                DomainSignal(
                    id=str(item["id"]),
                    text=str(item["text"]),
                    type=str(item["type"]),
                    label=str(item["label"]),
                    range=TextRange(**item["range"]),
                    source=str(item["source"]),
                    confidence=item.get("confidence"),
                    color=item.get("color"),
                )
                for item in data.get("domain_signals", [])
            ],
            syntax=[
                SyntaxDependency(
                    token_id=str(item["token_id"]),
                    head_id=item.get("head_id"),
                    relation=item.get("relation"),
                )
                for item in data.get("syntax", [])
            ],
            metrics=EnrichmentMetrics(**data["metrics"]),
            pipeline_trace=[PipelineTraceItem(**item) for item in data.get("pipeline_trace", [])],
        )


@dataclass(frozen=True)
class EnrichmentJobSnapshot:
    id: UUID
    input_text: str
    status: EnrichmentStatus
    progress_percent: int
    current_stage: str | None
    stage_index: int
    stage_count: int
    stage_progress_percent: int
    message: str
    result: TextEnrichmentResult | None
    error: dict[str, Any] | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class EnrichmentEvent:
    sequence: int
    job_id: UUID
    event_type: str
    progress_percent: int
    current_stage: str | None
    stage_index: int
    stage_count: int
    stage_progress_percent: int
    message: str
    payload: dict[str, Any]
    created_at: datetime
