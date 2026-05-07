from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PipelineStageConfig:
    name: str
    enabled: bool


@dataclass(frozen=True)
class RuleTokenConfig:
    predicate: str
    value: str


@dataclass(frozen=True)
class RulePatternConfig:
    tokens: tuple[RuleTokenConfig, ...]


@dataclass(frozen=True)
class PhraseRuleConfig:
    type: str
    label: str
    phrases: tuple[tuple[str, ...], ...]
    patterns: tuple[RulePatternConfig, ...]
    color: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class AliasRuleConfig:
    key: str
    canonical: str
    kind: str
    aliases: tuple[str, ...]
    signal_types: tuple[str, ...]
    fact_types: tuple[str, ...]
    color: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class LeadScoringConfig:
    lead_threshold: int
    warm_threshold: int
    hot_threshold: int
    signal_weights: dict[str, int]
    fact_weights: dict[str, int]
    solution_areas: dict[str, dict[str, Any]]
    customer_segments: dict[str, dict[str, Any]]
    intent_signal_types: list[str]
    noise_signal_types: list[str]


@dataclass(frozen=True)
class NlpPipelineConfig:
    stages: tuple[PipelineStageConfig, ...]
    signals: tuple[PhraseRuleConfig, ...]
    facts: tuple[PhraseRuleConfig, ...]
    aliases: tuple[AliasRuleConfig, ...]
    lead_scoring: LeadScoringConfig

    @property
    def enabled_stages(self) -> tuple[PipelineStageConfig, ...]:
        return tuple(stage for stage in self.stages if stage.enabled)

    def is_enabled(self, stage_name: str) -> bool:
        return any(stage.name == stage_name and stage.enabled for stage in self.stages)


def load_nlp_config(config_dir: Path) -> NlpPipelineConfig:
    return load_nlp_config_from_documents(read_nlp_config_documents(config_dir))


def read_nlp_config_documents(config_dir: Path) -> dict[str, dict[str, Any]]:
    facts_path = config_dir / "facts.yaml"
    lead_scoring_path = config_dir / "lead_scoring.yaml"
    alias_documents = {
        catalog_name: _load_yaml(config_dir / f"{catalog_name}.yaml")
        if (config_dir / f"{catalog_name}.yaml").exists()
        else {catalog_name: []}
        for catalog_name in _alias_catalog_names()
    }
    return {
        "pipeline": _load_yaml(config_dir / "pipeline.yaml"),
        "signals": _load_yaml(config_dir / "signals.yaml"),
        "facts": _load_yaml(facts_path) if facts_path.exists() else {"facts": []},
        "lead_scoring": (
            _load_yaml(lead_scoring_path) if lead_scoring_path.exists() else {"lead_scoring": {}}
        ),
        **alias_documents,
    }


def load_nlp_config_from_documents(documents: dict[str, dict[str, Any]]) -> NlpPipelineConfig:
    pipeline = documents["pipeline"]
    signals = documents["signals"]
    facts = documents.get("facts", {"facts": []})
    lead_scoring = documents.get("lead_scoring", {"lead_scoring": {}})
    return NlpPipelineConfig(
        stages=tuple(_parse_stage(item) for item in pipeline.get("stages", [])),
        signals=tuple(_parse_phrase_rule(item, "signals") for item in signals.get("signals", [])),
        facts=tuple(_parse_phrase_rule(item, "facts") for item in facts.get("facts", [])),
        aliases=tuple(
            alias
            for catalog_name in _alias_catalog_names()
            for alias in _parse_alias_catalog(
                documents.get(catalog_name, {catalog_name: []}),
                catalog_name,
            )
        ),
        lead_scoring=_parse_lead_scoring(lead_scoring.get("lead_scoring", {})),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def _parse_stage(raw: Any) -> PipelineStageConfig:
    if not isinstance(raw, dict):
        raise ValueError("pipeline stage must be a mapping")
    return PipelineStageConfig(name=str(raw["name"]), enabled=bool(raw.get("enabled", True)))


def _parse_phrase_rule(raw: Any, collection_name: str) -> PhraseRuleConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"{collection_name} item must be a mapping")

    phrases = raw.get("phrases", [])
    patterns = raw.get("patterns", [])
    if not phrases and not patterns:
        raise ValueError(f"{collection_name} item must define phrases or patterns")

    parsed_phrases: list[tuple[str, ...]] = []
    for phrase in phrases:
        if not isinstance(phrase, list) or not phrase:
            raise ValueError(f"{collection_name} phrases must be non-empty lists")
        parsed_phrases.append(tuple(str(word) for word in phrase))

    return PhraseRuleConfig(
        type=str(raw["type"]),
        label=str(raw.get("label", raw["type"])),
        color=raw.get("color"),
        confidence=float(raw["confidence"]) if raw.get("confidence") is not None else None,
        phrases=tuple(parsed_phrases),
        patterns=_parse_patterns(patterns, collection_name),
    )


def _parse_patterns(raw_patterns: Any, collection_name: str) -> tuple[RulePatternConfig, ...]:
    if not raw_patterns:
        return ()
    if not isinstance(raw_patterns, list):
        raise ValueError(f"{collection_name} patterns must be a list")

    patterns: list[RulePatternConfig] = []
    for raw_pattern in raw_patterns:
        if not isinstance(raw_pattern, dict):
            raise ValueError(f"{collection_name} pattern must be a mapping")
        raw_tokens = raw_pattern.get("tokens")
        if not isinstance(raw_tokens, list) or not raw_tokens:
            raise ValueError(f"{collection_name} pattern tokens must be a non-empty list")

        tokens: list[RuleTokenConfig] = []
        for raw_token in raw_tokens:
            if not isinstance(raw_token, dict) or len(raw_token) != 1:
                raise ValueError(f"{collection_name} pattern token must define one predicate")
            predicate, value = next(iter(raw_token.items()))
            predicate_name = str(predicate)
            if predicate_name != "normalized":
                raise ValueError(f"unsupported {collection_name} pattern predicate: {predicate_name}")
            tokens.append(RuleTokenConfig(predicate=predicate_name, value=str(value)))

        patterns.append(RulePatternConfig(tokens=tuple(tokens)))

    return tuple(patterns)


def _parse_alias_catalog(
    raw_document: dict[str, Any],
    catalog_name: str,
) -> tuple[AliasRuleConfig, ...]:
    raw_items = raw_document.get(catalog_name, [])
    if raw_items is None:
        return ()
    if not isinstance(raw_items, list):
        raise ValueError(f"{catalog_name} must be a list")

    items: list[AliasRuleConfig] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError(f"{catalog_name} item must be a mapping")
        aliases = _parse_string_list(raw.get("aliases", []), f"{catalog_name}.aliases")
        if not aliases:
            raise ValueError(f"{catalog_name} item must define aliases")
        signal_types = _parse_string_list(raw.get("signal_types", []), f"{catalog_name}.signal_types")
        fact_types = _parse_string_list(raw.get("fact_types", []), f"{catalog_name}.fact_types")
        if not signal_types and not fact_types:
            raise ValueError(f"{catalog_name} item must define signal_types or fact_types")
        items.append(
            AliasRuleConfig(
                key=str(raw["key"]),
                canonical=str(raw.get("canonical", raw.get("label", raw["key"]))),
                kind=str(raw.get("type", _catalog_item_kind(catalog_name))),
                aliases=tuple(aliases),
                signal_types=tuple(signal_types),
                fact_types=tuple(fact_types),
                color=raw.get("color"),
                confidence=float(raw["confidence"]) if raw.get("confidence") is not None else None,
            )
        )

    return tuple(items)


def _parse_lead_scoring(raw: Any) -> LeadScoringConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("lead_scoring must be a mapping")

    thresholds = raw.get("thresholds", {})
    if thresholds and not isinstance(thresholds, dict):
        raise ValueError("lead_scoring thresholds must be a mapping")

    weights = raw.get("weights", {})
    if weights and not isinstance(weights, dict):
        raise ValueError("lead_scoring weights must be a mapping")

    signal_weights = _parse_weight_mapping(weights.get("signals", {}), "lead_scoring weights.signals")
    fact_weights = _parse_weight_mapping(weights.get("facts", {}), "lead_scoring weights.facts")

    return LeadScoringConfig(
        lead_threshold=int(thresholds.get("lead", 1)),
        warm_threshold=int(thresholds.get("warm", 1)),
        hot_threshold=int(thresholds.get("hot", 1)),
        signal_weights=signal_weights,
        fact_weights=fact_weights,
        solution_areas=_parse_category_mapping(raw.get("solution_areas", {}), "solution_areas"),
        customer_segments=_parse_category_mapping(raw.get("customer_segments", {}), "customer_segments"),
        intent_signal_types=_parse_string_list(raw.get("intent_signal_types", []), "intent_signal_types"),
        noise_signal_types=_parse_string_list(raw.get("noise_signal_types", []), "noise_signal_types"),
    )


def _parse_weight_mapping(raw: Any, name: str) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be a mapping")
    return {str(key): int(value) for key, value in raw.items()}


def _parse_category_mapping(raw: Any, name: str) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"lead_scoring {name} must be a mapping")

    categories: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"lead_scoring {name}.{key} must be a mapping")
        categories[str(key)] = {
            "label": str(value.get("label", key)),
            "signal_types": _parse_string_list(value.get("signal_types", []), f"{name}.{key}.signal_types"),
            "fact_types": _parse_string_list(value.get("fact_types", []), f"{name}.{key}.fact_types"),
        }
    return categories


def _parse_string_list(raw: Any, name: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{name} must be a list")
    return [str(item) for item in raw if str(item).strip()]


def _alias_catalog_names() -> tuple[str, ...]:
    return ("vendors", "protocols", "devices", "software")


def _catalog_item_kind(catalog_name: str) -> str:
    return {
        "vendors": "vendor",
        "protocols": "protocol",
        "devices": "device",
        "software": "software",
    }.get(catalog_name, catalog_name.rstrip("s"))
