from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
class SettingsReference:
    section: str
    key: str
    label: str
    kind: str
    catalog: str | None = None


@dataclass(frozen=True)
class ExtractedFact:
    id: str
    text: str
    type: str
    label: str
    range: TextRange
    source: str
    confidence: float | None = None
    explanation: str | None = None
    settings_refs: list[SettingsReference] = field(default_factory=list)


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
    explanation: str | None = None
    settings_refs: list[SettingsReference] = field(default_factory=list)


@dataclass(frozen=True)
class LeadCategory:
    type: str
    label: str
    matched_types: list[str]


@dataclass(frozen=True)
class LeadReason:
    source: str
    key: str
    label: str
    weight: int
    matched_texts: list[str]


@dataclass(frozen=True)
class LeadReviewLane:
    key: str
    label: str
    description: str | None
    matched_group_indexes: list[int]


@dataclass(frozen=True)
class LeadAssessment:
    is_lead: bool
    score: int
    temperature: str
    solution_areas: list[LeadCategory]
    customer_segments: list[LeadCategory]
    intent_signals: list[LeadCategory]
    noise_signals: list[LeadCategory]
    reasons: list[LeadReason]
    review_lane: LeadReviewLane | None = None


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
    lead_assessment: LeadAssessment | None = None

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
                    explanation=item.get("explanation"),
                    settings_refs=[
                        _settings_reference_from_dict(ref)
                        for ref in item.get("settings_refs", [])
                    ],
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
                    explanation=item.get("explanation"),
                    settings_refs=[
                        _settings_reference_from_dict(ref)
                        for ref in item.get("settings_refs", [])
                    ],
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
            lead_assessment=_lead_assessment_from_dict(data.get("lead_assessment")),
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
    nlp_config_revision_id: UUID | None = None
    nlp_config_revision: int | None = None


@dataclass(frozen=True)
class EnrichmentTaskOutboxItem:
    job_id: UUID
    task_name: str
    status: str
    attempts: int
    last_error: str | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


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


def _lead_assessment_from_dict(data: Any) -> LeadAssessment | None:
    if data is None:
        return None
    return LeadAssessment(
        is_lead=bool(data["is_lead"]),
        score=int(data["score"]),
        temperature=str(data["temperature"]),
        solution_areas=[
            LeadCategory(
                type=str(item["type"]),
                label=str(item["label"]),
                matched_types=[str(value) for value in item.get("matched_types", [])],
            )
            for item in data.get("solution_areas", [])
        ],
        customer_segments=[
            LeadCategory(
                type=str(item["type"]),
                label=str(item["label"]),
                matched_types=[str(value) for value in item.get("matched_types", [])],
            )
            for item in data.get("customer_segments", [])
        ],
        intent_signals=[
            LeadCategory(
                type=str(item["type"]),
                label=str(item["label"]),
                matched_types=[str(value) for value in item.get("matched_types", [])],
            )
            for item in data.get("intent_signals", [])
        ],
        noise_signals=[
            LeadCategory(
                type=str(item["type"]),
                label=str(item["label"]),
                matched_types=[str(value) for value in item.get("matched_types", [])],
            )
            for item in data.get("noise_signals", [])
        ],
        reasons=[
            LeadReason(
                source=str(item["source"]),
                key=str(item["key"]),
                label=str(item["label"]),
                weight=int(item["weight"]),
                matched_texts=[str(value) for value in item.get("matched_texts", [])],
            )
            for item in data.get("reasons", [])
        ],
        review_lane=_lead_review_lane_from_dict(data.get("review_lane")),
    )


def _settings_reference_from_dict(data: Any) -> SettingsReference:
    return SettingsReference(
        section=str(data["section"]),
        key=str(data["key"]),
        label=str(data["label"]),
        kind=str(data["kind"]),
        catalog=data.get("catalog"),
    )


def _lead_review_lane_from_dict(data: Any) -> LeadReviewLane | None:
    if data is None:
        return None
    return LeadReviewLane(
        key=str(data["key"]),
        label=str(data["label"]),
        description=data.get("description"),
        matched_group_indexes=[int(value) for value in data.get("matched_group_indexes", [])],
    )
