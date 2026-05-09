from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.api.notifications import NotificationSettingsSnapshot
from app.api.notifications import get_notification_settings_repository
from app.api.notifications import read_notification_settings_snapshot
from app.api.telegram_ingestion import TelegramIngestionSettingsSnapshot
from app.api.telegram_ingestion import get_telegram_ingestion_repository
from app.api.telegram_ingestion import read_telegram_ingestion_settings_snapshot
from app.application.settings.use_cases import AddAliasFromSelection
from app.application.settings.use_cases import AddAliasFromSelectionCommand
from app.application.settings.use_cases import AddOperatorNoisePhrase
from app.application.settings.use_cases import AddOperatorNoisePhraseCommand
from app.application.settings.use_cases import AddRulePhraseFromSelection
from app.application.settings.use_cases import AddRulePhraseFromSelectionCommand
from app.application.settings.use_cases import SettingsReferenceResult
from app.core.config import Settings, get_settings
from app.db.session import create_sessionmaker
from app.domain.settings import NlpConfigRevision
from app.infrastructure.nlp.config_loader import load_nlp_config_from_documents
from app.infrastructure.nlp.config_loader import read_nlp_config_documents
from app.infrastructure.nlp.rule_phrase_normalizer import RussianRulePhraseNormalizer
from app.infrastructure.nlp.russian_text_enricher import RussianTextEnricher
from app.infrastructure.persistence.notification_settings_repository import (
    PostgresNotificationSettingsRepository,
)
from app.infrastructure.persistence.telegram_ingestion_repository import (
    PostgresTelegramIngestionRepository,
)
from app.infrastructure.persistence.nlp_config_repository import PostgresNlpConfigRepository

router = APIRouter(prefix="/settings", tags=["settings"])


class PipelineStageSettings(BaseModel):
    name: str
    enabled: bool = True


class PipelineSettings(BaseModel):
    stages: list[PipelineStageSettings]


class AliasMatchingSettings(BaseModel):
    normalize_separators: bool = True
    normalize_yo: bool = True
    normalize_latin_confusables: bool = True
    fuzzy_enabled: bool = True
    fuzzy_min_length: int = Field(default=5, ge=1)
    fuzzy_max_distance: int = Field(default=1, ge=0, le=3)
    fuzzy_long_min_length: int = Field(default=10, ge=1)
    fuzzy_long_max_distance: int = Field(default=2, ge=0, le=3)
    fuzzy_excluded_aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fuzzy_lengths(self) -> AliasMatchingSettings:
        if self.fuzzy_long_min_length < self.fuzzy_min_length:
            raise ValueError("fuzzy_long_min_length must be >= fuzzy_min_length")
        return self


class PatternTokenSettings(BaseModel):
    predicate: Literal["normalized"]
    value: str = Field(min_length=1)


class PatternSettings(BaseModel):
    source_text: str | None = None
    tokens: list[PatternTokenSettings] = Field(min_length=1)


class AliasMatchSettings(BaseModel):
    catalog: str | None = None
    catalogs: list[str] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_alias_match_source(self) -> AliasMatchSettings:
        if not self.catalog and not self.catalogs and not self.keys and not self.kinds:
            raise ValueError("alias match must define catalog, catalogs, keys, or kinds")
        return self


class FactMatchSettings(BaseModel):
    types: list[str] = Field(min_length=1)


class RuleMatchSettings(BaseModel):
    aliases: list[AliasMatchSettings] = Field(default_factory=list)
    facts: list[FactMatchSettings] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.aliases and not self.facts


class RuleSettings(BaseModel):
    type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    group: str | None = None
    phrases: list[list[str]] = Field(default_factory=list)
    patterns: list[PatternSettings] = Field(default_factory=list)
    match: RuleMatchSettings = Field(default_factory=RuleMatchSettings)
    color: str | None = None
    confidence: float | None = None

    @model_validator(mode="after")
    def validate_rule_source(self) -> RuleSettings:
        if not self.phrases and not self.patterns and self.match.is_empty:
            raise ValueError("rule must define phrases, patterns, or match")
        return self


class AliasSettings(BaseModel):
    key: str = Field(min_length=1)
    canonical: str = Field(min_length=1)
    type: Literal["vendor", "protocol", "device", "software", "model"]
    aliases: list[str] = Field(min_length=1)
    fact_types: list[str] = Field(min_length=1)
    color: str | None = None
    confidence: float | None = None


class LeadCategorySettings(BaseModel):
    label: str = Field(min_length=1)
    signal_types: list[str] = Field(default_factory=list)
    fact_types: list[str] = Field(default_factory=list)


class ReviewLaneMatchGroupSettings(BaseModel):
    signal_types: list[str] = Field(default_factory=list)
    fact_types: list[str] = Field(default_factory=list)
    reason_keys: list[str] = Field(default_factory=list)
    solution_area_types: list[str] = Field(default_factory=list)
    customer_segment_types: list[str] = Field(default_factory=list)
    intent_signal_types: list[str] = Field(default_factory=list)
    noise_signal_types: list[str] = Field(default_factory=list)


class ReviewLaneSettings(BaseModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str | None = None
    priority: int = 0
    min_score: int | None = Field(default=None, ge=0)
    max_score: int | None = Field(default=None, ge=0)
    temperatures: list[str] = Field(default_factory=list)
    match_groups: list[ReviewLaneMatchGroupSettings] = Field(default_factory=list)
    excluded_signal_types: list[str] = Field(default_factory=list)
    excluded_fact_types: list[str] = Field(default_factory=list)
    excluded_reason_keys: list[str] = Field(default_factory=list)
    excluded_solution_area_types: list[str] = Field(default_factory=list)
    excluded_customer_segment_types: list[str] = Field(default_factory=list)
    excluded_intent_signal_types: list[str] = Field(default_factory=list)
    excluded_noise_signal_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_score_bounds(self) -> ReviewLaneSettings:
        if self.min_score is not None and self.max_score is not None and self.min_score > self.max_score:
            raise ValueError("review lane min_score must be <= max_score")
        return self


class LeadScoreCapSettings(BaseModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    max_score: int = Field(ge=0)
    signal_types: list[str] = Field(default_factory=list)
    fact_types: list[str] = Field(default_factory=list)
    reason_keys: list[str] = Field(default_factory=list)
    noise_signal_types: list[str] = Field(default_factory=list)


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
    lead_veto_signal_types: list[str] = Field(default_factory=list)
    score_caps: list[LeadScoreCapSettings] = Field(default_factory=list)
    review_lanes: list[ReviewLaneSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> LeadScoringSettings:
        if not (self.lead_threshold <= self.warm_threshold <= self.hot_threshold):
            raise ValueError("lead scoring thresholds must be ordered: lead <= warm <= hot")
        return self


class NlpSettings(BaseModel):
    pipeline: PipelineSettings
    alias_matching: AliasMatchingSettings = Field(default_factory=AliasMatchingSettings)
    signals: list[RuleSettings]
    facts: list[RuleSettings]
    vendors: list[AliasSettings] = Field(default_factory=list)
    protocols: list[AliasSettings] = Field(default_factory=list)
    devices: list[AliasSettings] = Field(default_factory=list)
    software: list[AliasSettings] = Field(default_factory=list)
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
    notifications: NotificationSettingsSnapshot
    telegram_ingestion: TelegramIngestionSettingsSnapshot
    system: list[SystemSetting]


class PreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    nlp: NlpSettings


class SemanticPatternRequest(BaseModel):
    text: str = Field(min_length=1)


class SemanticPatternResponse(BaseModel):
    source_text: str
    lemma_text: str
    tokens: list[PatternTokenSettings]


class ConstructorNoiseRequest(BaseModel):
    text: str = Field(min_length=1)
    source_message_id: str | None = None


class ConstructorNoiseResponse(BaseModel):
    text: str
    signal_type: str
    signal_label: str
    phrase: list[str]
    created_rule: bool
    created_phrase: bool
    nlp: NlpSettingsSnapshot


class ConstructorSettingsRef(BaseModel):
    section: str
    key: str
    label: str
    catalog: str | None = None


class ConstructorAliasRequest(BaseModel):
    text: str = Field(min_length=1)
    source_message_id: str | None = None
    catalog: Literal["vendors", "protocols", "devices", "software"]
    key: str = Field(min_length=1)
    canonical: str | None = None
    alias_type: Literal["vendor", "protocol", "device", "software", "model"] | None = None
    fact_types: list[str] | None = None
    color: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ConstructorAliasResponse(BaseModel):
    text: str
    catalog: str
    key: str
    canonical: str
    created_target: bool
    created_entry: bool
    settings_ref: ConstructorSettingsRef
    nlp: NlpSettingsSnapshot


class ConstructorRuleRequest(BaseModel):
    text: str = Field(min_length=1)
    source_message_id: str | None = None
    target_type: str = Field(min_length=1)
    target_label: str | None = None
    group: str | None = None
    phrase_kind: Literal["exact", "semantic"]
    color: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ConstructorRuleResponse(BaseModel):
    text: str
    collection: str
    rule_type: str
    rule_label: str
    phrase_kind: str
    created_target: bool
    created_entry: bool
    settings_ref: ConstructorSettingsRef
    nlp: NlpSettingsSnapshot
    exact_phrase: list[str] | None = None
    semantic_pattern: dict[str, Any] | None = None


def get_nlp_config_dir(settings: Settings = Depends(get_settings)) -> Path:
    return settings.nlp_config_dir


def get_nlp_config_repository() -> PostgresNlpConfigRepository:
    return PostgresNlpConfigRepository(create_sessionmaker())


@lru_cache(maxsize=1)
def get_rule_phrase_normalizer() -> RussianRulePhraseNormalizer:
    return RussianRulePhraseNormalizer()


@router.get("", response_model=SettingsSnapshot)
async def get_all_settings(
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
    notification_repository: PostgresNotificationSettingsRepository = Depends(
        get_notification_settings_repository
    ),
    telegram_ingestion_repository: PostgresTelegramIngestionRepository = Depends(
        get_telegram_ingestion_repository
    ),
    settings: Settings = Depends(get_settings),
) -> SettingsSnapshot:
    return SettingsSnapshot(
        nlp=await _read_nlp_snapshot(config_dir, repository),
        notifications=await read_notification_settings_snapshot(notification_repository),
        telegram_ingestion=await read_telegram_ingestion_settings_snapshot(
            telegram_ingestion_repository
        ),
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


@router.post("/nlp/semantic-pattern", response_model=SemanticPatternResponse)
async def build_semantic_pattern(
    request: SemanticPatternRequest,
    normalizer: RussianRulePhraseNormalizer = Depends(get_rule_phrase_normalizer),
) -> SemanticPatternResponse:
    try:
        semantic_phrase = normalizer.to_semantic_phrase(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SemanticPatternResponse(
        source_text=semantic_phrase.source_text,
        lemma_text=semantic_phrase.lemma_text,
        tokens=[
            PatternTokenSettings(predicate="normalized", value=lemma)
            for lemma in semantic_phrase.lemmas
        ],
    )


@router.post("/nlp/constructor/noise", response_model=ConstructorNoiseResponse)
async def add_constructor_noise_phrase(
    request: ConstructorNoiseRequest,
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
) -> ConstructorNoiseResponse:
    defaults = read_nlp_config_documents(config_dir)

    def validate_documents(documents: dict[str, dict[str, Any]]) -> None:
        load_nlp_config_from_documents(documents)

    use_case = AddOperatorNoisePhrase(
        repository=repository,
        default_documents=defaults,
        validate_documents=validate_documents,
    )
    try:
        result = await use_case.execute(
            AddOperatorNoisePhraseCommand(
                text=request.text,
                source_message_id=request.source_message_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConstructorNoiseResponse(
        text=result.text,
        signal_type=result.signal_type,
        signal_label=result.signal_label,
        phrase=result.phrase,
        created_rule=result.created_rule,
        created_phrase=result.created_phrase,
        nlp=_nlp_snapshot_from_revision(result.revision),
    )


@router.post(
    "/nlp/constructor/alias",
    response_model=ConstructorAliasResponse,
    response_model_exclude_none=True,
)
async def add_constructor_alias(
    request: ConstructorAliasRequest,
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
) -> ConstructorAliasResponse:
    defaults = read_nlp_config_documents(config_dir)

    def validate_documents(documents: dict[str, dict[str, Any]]) -> None:
        load_nlp_config_from_documents(documents)

    use_case = AddAliasFromSelection(
        repository=repository,
        default_documents=defaults,
        validate_documents=validate_documents,
    )
    try:
        result = await use_case.execute(
            AddAliasFromSelectionCommand(
                text=request.text,
                source_message_id=request.source_message_id,
                catalog=request.catalog,
                key=request.key,
                canonical=request.canonical,
                alias_type=request.alias_type,
                fact_types=request.fact_types,
                color=request.color,
                confidence=request.confidence,
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConstructorAliasResponse(
        text=result.text,
        catalog=result.catalog,
        key=result.key,
        canonical=result.canonical,
        created_target=result.created_target,
        created_entry=result.created_entry,
        settings_ref=_constructor_settings_ref(result.settings_ref),
        nlp=_nlp_snapshot_from_revision(result.revision),
    )


@router.post(
    "/nlp/constructor/fact",
    response_model=ConstructorRuleResponse,
    response_model_exclude_none=True,
)
async def add_constructor_fact(
    request: ConstructorRuleRequest,
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
    normalizer: RussianRulePhraseNormalizer = Depends(get_rule_phrase_normalizer),
) -> ConstructorRuleResponse:
    return await _add_constructor_rule(
        request=request,
        collection="facts",
        config_dir=config_dir,
        repository=repository,
        normalizer=normalizer,
    )


@router.post(
    "/nlp/constructor/signal",
    response_model=ConstructorRuleResponse,
    response_model_exclude_none=True,
)
async def add_constructor_signal(
    request: ConstructorRuleRequest,
    config_dir: Path = Depends(get_nlp_config_dir),
    repository: PostgresNlpConfigRepository = Depends(get_nlp_config_repository),
    normalizer: RussianRulePhraseNormalizer = Depends(get_rule_phrase_normalizer),
) -> ConstructorRuleResponse:
    return await _add_constructor_rule(
        request=request,
        collection="signals",
        config_dir=config_dir,
        repository=repository,
        normalizer=normalizer,
    )


async def _add_constructor_rule(
    *,
    request: ConstructorRuleRequest,
    collection: Literal["signals", "facts"],
    config_dir: Path,
    repository: PostgresNlpConfigRepository,
    normalizer: RussianRulePhraseNormalizer,
) -> ConstructorRuleResponse:
    defaults = read_nlp_config_documents(config_dir)

    def validate_documents(documents: dict[str, dict[str, Any]]) -> None:
        load_nlp_config_from_documents(documents)

    def semantic_pattern_builder(text: str) -> dict[str, Any]:
        semantic_phrase = normalizer.to_semantic_phrase(text)
        return {
            "source_text": semantic_phrase.source_text,
            "tokens": [{"normalized": lemma} for lemma in semantic_phrase.lemmas],
        }

    use_case = AddRulePhraseFromSelection(
        repository=repository,
        default_documents=defaults,
        validate_documents=validate_documents,
        semantic_pattern_builder=semantic_pattern_builder,
    )
    try:
        result = await use_case.execute(
            AddRulePhraseFromSelectionCommand(
                text=request.text,
                source_message_id=request.source_message_id,
                collection=collection,
                target_type=request.target_type,
                target_label=request.target_label,
                group=request.group,
                phrase_kind=request.phrase_kind,
                color=request.color,
                confidence=request.confidence,
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConstructorRuleResponse(
        text=result.text,
        collection=result.collection,
        rule_type=result.rule_type,
        rule_label=result.rule_label,
        phrase_kind=result.phrase_kind,
        exact_phrase=result.exact_phrase,
        semantic_pattern=result.semantic_pattern,
        created_target=result.created_target,
        created_entry=result.created_entry,
        settings_ref=_constructor_settings_ref(result.settings_ref),
        nlp=_nlp_snapshot_from_revision(result.revision),
    )


async def _read_nlp_snapshot(
    config_dir: Path,
    repository: PostgresNlpConfigRepository,
) -> NlpSettingsSnapshot:
    bootstrap_documents = read_nlp_config_documents(config_dir)
    revision = await repository.get_active_or_seed(bootstrap_documents)
    return _nlp_snapshot_from_revision(revision)


def _constructor_settings_ref(reference: SettingsReferenceResult) -> ConstructorSettingsRef:
    return ConstructorSettingsRef(
        section=reference.section,
        catalog=reference.catalog,
        key=reference.key,
        label=reference.label,
    )


def _nlp_snapshot_from_revision(revision: NlpConfigRevision) -> NlpSettingsSnapshot:
    documents = revision.documents
    return NlpSettingsSnapshot(
        pipeline=PipelineSettings.model_validate(documents["pipeline"]),
        alias_matching=_alias_matching_from_document(documents["pipeline"]),
        signals=[_rule_from_document(item) for item in documents["signals"].get("signals", [])],
        facts=[_rule_from_document(item) for item in documents["facts"].get("facts", [])],
        vendors=[_alias_from_document(item) for item in documents.get("vendors", {}).get("vendors", [])],
        protocols=[
            _alias_from_document(item) for item in documents.get("protocols", {}).get("protocols", [])
        ],
        devices=[_alias_from_document(item) for item in documents.get("devices", {}).get("devices", [])],
        software=[_alias_from_document(item) for item in documents.get("software", {}).get("software", [])],
        lead_scoring=_lead_scoring_from_document(documents.get("lead_scoring", {})),
        source=NlpSettingsSource(
            type="postgres",
            path="nlp_config_revisions.config",
            editable=True,
            revision=revision.revision,
        ),
    )


def _nlp_settings_to_documents(payload: NlpSettings) -> dict[str, dict[str, Any]]:
    pipeline = payload.pipeline.model_dump()
    pipeline["alias_matching"] = payload.alias_matching.model_dump()
    return {
        "pipeline": pipeline,
        "signals": {"signals": [_rule_to_document(rule) for rule in payload.signals]},
        "facts": {"facts": [_rule_to_document(rule) for rule in payload.facts]},
        "vendors": {"vendors": [_alias_to_document(alias) for alias in payload.vendors]},
        "protocols": {"protocols": [_alias_to_document(alias) for alias in payload.protocols]},
        "devices": {"devices": [_alias_to_document(alias) for alias in payload.devices]},
        "software": {"software": [_alias_to_document(alias) for alias in payload.software]},
        "lead_scoring": _lead_scoring_to_document(payload.lead_scoring),
    }


def _alias_matching_from_document(raw_pipeline: dict[str, Any]) -> AliasMatchingSettings:
    return AliasMatchingSettings.model_validate(raw_pipeline.get("alias_matching", {}))


def _rule_to_document(rule: RuleSettings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": rule.type,
        "label": rule.label,
    }
    if rule.group:
        payload["group"] = rule.group
    if rule.color:
        payload["color"] = rule.color
    if rule.confidence is not None:
        payload["confidence"] = rule.confidence
    if rule.phrases:
        payload["phrases"] = rule.phrases
    if rule.patterns:
        payload["patterns"] = [
            {
                **({"source_text": pattern.source_text} if pattern.source_text else {}),
                "tokens": [{token.predicate: token.value} for token in pattern.tokens],
            }
            for pattern in rule.patterns
        ]
    if not rule.match.is_empty:
        payload["match"] = _rule_match_to_document(rule.match)
    return payload


def _rule_from_document(raw_rule: dict[str, Any]) -> RuleSettings:
    payload = dict(raw_rule)
    payload["phrases"] = payload.get("phrases", [])
    payload["patterns"] = [
        {
            "source_text": raw_pattern.get("source_text"),
            "tokens": [
                {"predicate": str(predicate), "value": str(value)}
                for raw_token in raw_pattern.get("tokens", [])
                for predicate, value in raw_token.items()
            ]
        }
        for raw_pattern in payload.get("patterns", [])
    ]
    payload["match"] = _rule_match_from_document(payload.get("match", {}))
    return RuleSettings.model_validate(payload)


def _rule_match_to_document(match: RuleMatchSettings) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if match.aliases:
        payload["aliases"] = [dependency.model_dump(exclude_none=True) for dependency in match.aliases]
    if match.facts:
        payload["facts"] = [dependency.model_dump() for dependency in match.facts]
    return payload


def _rule_match_from_document(raw_match: Any) -> dict[str, Any]:
    if not raw_match:
        return {"aliases": [], "facts": []}
    if not isinstance(raw_match, dict):
        return {"aliases": [], "facts": []}

    facts = []
    for raw_fact in raw_match.get("facts", []):
        if isinstance(raw_fact, str):
            facts.append({"types": [raw_fact]})
        else:
            facts.append(raw_fact)
    return {
        "aliases": raw_match.get("aliases", []),
        "facts": facts,
    }


def _alias_to_document(alias: AliasSettings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": alias.key,
        "canonical": alias.canonical,
        "type": alias.type,
        "aliases": alias.aliases,
        "fact_types": alias.fact_types,
    }
    if alias.color:
        payload["color"] = alias.color
    if alias.confidence is not None:
        payload["confidence"] = alias.confidence
    return payload


def _alias_from_document(raw_alias: dict[str, Any]) -> AliasSettings:
    return AliasSettings.model_validate(
        {
            "key": raw_alias.get("key"),
            "canonical": raw_alias.get("canonical", raw_alias.get("label", raw_alias.get("key"))),
            "type": raw_alias.get("type"),
            "aliases": raw_alias.get("aliases", []),
            "fact_types": raw_alias.get("fact_types", []),
            "color": raw_alias.get("color"),
            "confidence": raw_alias.get("confidence"),
        }
    )


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
            "lead_veto_signal_types": settings.lead_veto_signal_types,
            "score_caps": [cap.model_dump() for cap in settings.score_caps],
            "review_lanes": [lane.model_dump(exclude_none=True) for lane in settings.review_lanes],
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
        lead_veto_signal_types=[str(value) for value in raw.get("lead_veto_signal_types", [])],
        score_caps=[
            LeadScoreCapSettings.model_validate(value)
            for value in raw.get("score_caps", [])
        ],
        review_lanes=[
            ReviewLaneSettings.model_validate(value)
            for value in raw.get("review_lanes", [])
        ],
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
