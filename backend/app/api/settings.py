from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.core.config import Settings, get_settings
from app.db.session import create_sessionmaker
from app.domain.settings import NlpConfigRevision
from app.infrastructure.nlp.config_loader import load_nlp_config_from_documents
from app.infrastructure.nlp.config_loader import read_nlp_config_documents
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher
from app.infrastructure.persistence.nlp_config_repository import PostgresNlpConfigRepository

router = APIRouter(prefix="/settings", tags=["settings"])


class PipelineStageSettings(BaseModel):
    name: str
    enabled: bool = True


class PipelineSettings(BaseModel):
    stages: list[PipelineStageSettings]


class PatternTokenSettings(BaseModel):
    predicate: Literal["caseless", "normalized"]
    value: str = Field(min_length=1)


class PatternSettings(BaseModel):
    tokens: list[PatternTokenSettings] = Field(min_length=1)


class RuleSettings(BaseModel):
    type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    phrases: list[list[str]] = Field(default_factory=list)
    patterns: list[PatternSettings] = Field(default_factory=list)
    color: str | None = None
    confidence: float | None = None

    @model_validator(mode="after")
    def validate_rule_source(self) -> RuleSettings:
        if not self.phrases and not self.patterns:
            raise ValueError("rule must define phrases or patterns")
        return self


class LeadCategorySettings(BaseModel):
    label: str = Field(min_length=1)
    signal_types: list[str] = Field(default_factory=list)
    fact_types: list[str] = Field(default_factory=list)


class LeadScoringSettings(BaseModel):
    lead_threshold: int = Field(ge=0)
    warm_threshold: int = Field(ge=0)
    hot_threshold: int = Field(ge=0)
    signal_weights: dict[str, int] = Field(default_factory=dict)
    fact_weights: dict[str, int] = Field(default_factory=dict)
    solution_areas: dict[str, LeadCategorySettings] = Field(default_factory=dict)
    customer_segments: dict[str, LeadCategorySettings] = Field(default_factory=dict)
    intent_signal_types: list[str] = Field(default_factory=list)
    noise_signal_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> LeadScoringSettings:
        if not (self.lead_threshold <= self.warm_threshold <= self.hot_threshold):
            raise ValueError("lead scoring thresholds must be ordered: lead <= warm <= hot")
        return self


class NlpSettings(BaseModel):
    pipeline: PipelineSettings
    signals: list[RuleSettings]
    facts: list[RuleSettings]
    lead_scoring: LeadScoringSettings


class NlpSettingsSource(BaseModel):
    type: Literal["postgres"]
    path: str
    editable: bool
    revision: int


class NlpSettingsSnapshot(NlpSettings):
    source: NlpSettingsSource


class SystemSetting(BaseModel):
    key: str
    value: str
    editable: bool
    sensitive: bool = False
    source: Literal["env"]


class SettingsSnapshot(BaseModel):
    nlp: NlpSettingsSnapshot
    system: list[SystemSetting]


class PreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    nlp: NlpSettings


def get_nlp_config_dir(settings: Settings = Depends(get_settings)) -> Path:
    return settings.nlp_config_dir


def get_nlp_config_repository() -> PostgresNlpConfigRepository:
    return PostgresNlpConfigRepository(create_sessionmaker())


@router.get("", response_model=SettingsSnapshot)
async def get_all_settings(
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
    settings: Settings = Depends(get_settings),
) -> SettingsSnapshot:
    return SettingsSnapshot(
        nlp=await _read_nlp_snapshot(config_dir, repository),
        system=_system_settings(settings),
    )


@router.put("/nlp", response_model=NlpSettingsSnapshot)
async def update_nlp_settings(
    payload: NlpSettings,
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
) -> NlpSettingsSnapshot:
    documents = _nlp_settings_to_documents(payload)
    try:
        load_nlp_config_from_documents(documents)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    revision = await repository.replace_active(documents, source="ui")
    return _nlp_snapshot_from_revision(revision)


@router.post("/nlp/preview")
async def preview_nlp_settings(request: PreviewRequest) -> dict[str, Any]:
    documents = _nlp_settings_to_documents(request.nlp)
    try:
        config = load_nlp_config_from_documents(documents)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RussianTextEnricher(config).enrich(request.text).to_dict()


async def _read_nlp_snapshot(
    config_dir: Path,
    repository: PostgresNlpConfigRepository,
) -> NlpSettingsSnapshot:
    bootstrap_documents = read_nlp_config_documents(config_dir)
    revision = await repository.get_active_or_seed(bootstrap_documents)
    return _nlp_snapshot_from_revision(revision)


def _nlp_snapshot_from_revision(revision: NlpConfigRevision) -> NlpSettingsSnapshot:
    documents = revision.documents
    return NlpSettingsSnapshot(
        pipeline=PipelineSettings.model_validate(documents["pipeline"]),
        signals=[_rule_from_document(item) for item in documents["signals"].get("signals", [])],
        facts=[_rule_from_document(item) for item in documents["facts"].get("facts", [])],
        lead_scoring=_lead_scoring_from_document(documents.get("lead_scoring", {})),
        source=NlpSettingsSource(
            type="postgres",
            path="nlp_config_revisions.config",
            editable=True,
            revision=revision.revision,
        ),
    )


def _nlp_settings_to_documents(payload: NlpSettings) -> dict[str, dict[str, Any]]:
    return {
        "pipeline": payload.pipeline.model_dump(),
        "signals": {"signals": [_rule_to_document(rule) for rule in payload.signals]},
        "facts": {"facts": [_rule_to_document(rule) for rule in payload.facts]},
        "lead_scoring": _lead_scoring_to_document(payload.lead_scoring),
    }


def _rule_to_document(rule: RuleSettings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": rule.type,
        "label": rule.label,
    }
    if rule.color:
        payload["color"] = rule.color
    if rule.confidence is not None:
        payload["confidence"] = rule.confidence
    if rule.phrases:
        payload["phrases"] = rule.phrases
    if rule.patterns:
        payload["patterns"] = [
            {"tokens": [{token.predicate: token.value} for token in pattern.tokens]}
            for pattern in rule.patterns
        ]
    return payload


def _rule_from_document(raw_rule: dict[str, Any]) -> RuleSettings:
    payload = dict(raw_rule)
    payload["phrases"] = payload.get("phrases", [])
    payload["patterns"] = [
        {
            "tokens": [
                {"predicate": str(predicate), "value": str(value)}
                for raw_token in raw_pattern.get("tokens", [])
                for predicate, value in raw_token.items()
            ]
        }
        for raw_pattern in payload.get("patterns", [])
    ]
    return RuleSettings.model_validate(payload)


def _lead_scoring_to_document(settings: LeadScoringSettings) -> dict[str, Any]:
    return {
        "lead_scoring": {
            "thresholds": {
                "lead": settings.lead_threshold,
                "warm": settings.warm_threshold,
                "hot": settings.hot_threshold,
            },
            "weights": {
                "signals": settings.signal_weights,
                "facts": settings.fact_weights,
            },
            "solution_areas": {
                key: value.model_dump() for key, value in settings.solution_areas.items()
            },
            "customer_segments": {
                key: value.model_dump() for key, value in settings.customer_segments.items()
            },
            "intent_signal_types": settings.intent_signal_types,
            "noise_signal_types": settings.noise_signal_types,
        }
    }


def _lead_scoring_from_document(raw_document: dict[str, Any]) -> LeadScoringSettings:
    raw = raw_document.get("lead_scoring", raw_document)
    thresholds = raw.get("thresholds", {})
    weights = raw.get("weights", {})
    return LeadScoringSettings(
        lead_threshold=int(thresholds.get("lead", 1)),
        warm_threshold=int(thresholds.get("warm", thresholds.get("lead", 1))),
        hot_threshold=int(thresholds.get("hot", thresholds.get("warm", thresholds.get("lead", 1)))),
        signal_weights={str(key): int(value) for key, value in weights.get("signals", {}).items()},
        fact_weights={str(key): int(value) for key, value in weights.get("facts", {}).items()},
        solution_areas={
            str(key): LeadCategorySettings.model_validate(value)
            for key, value in raw.get("solution_areas", {}).items()
        },
        customer_segments={
            str(key): LeadCategorySettings.model_validate(value)
            for key, value in raw.get("customer_segments", {}).items()
        },
        intent_signal_types=[str(value) for value in raw.get("intent_signal_types", [])],
        noise_signal_types=[str(value) for value in raw.get("noise_signal_types", [])],
    )


def _system_settings(settings: Settings) -> list[SystemSetting]:
    return [
        SystemSetting(
            key="environment",
            value=settings.environment,
            editable=False,
            source="env",
        ),
        SystemSetting(
            key="database_url",
            value=_redact_connection_url(settings.database_url),
            editable=False,
            sensitive=True,
            source="env",
        ),
        SystemSetting(
            key="redis_url",
            value=_redact_connection_url(settings.redis_url),
            editable=False,
            sensitive=True,
            source="env",
        ),
        SystemSetting(
            key="nlp_config_dir",
            value=str(settings.nlp_config_dir),
            editable=False,
            source="env",
        ),
        SystemSetting(
            key="cors_origins",
            value=settings.cors_origins,
            editable=False,
            source="env",
        ),
    ]


def _redact_connection_url(value: str) -> str:
    if "@" not in value or "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    credentials, host = rest.split("@", 1)
    if ":" not in credentials:
        return f"{scheme}://***@{host}"
    username, _ = credentials.split(":", 1)
    return f"{scheme}://{username}:***@{host}"
