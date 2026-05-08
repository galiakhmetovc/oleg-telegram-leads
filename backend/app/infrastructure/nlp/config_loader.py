from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.application.review_lanes import ReviewLaneConfig, ReviewLaneMatchGroup


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
class AliasMatchConfig:
    catalogs: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.catalogs and not self.keys and not self.kinds


@dataclass(frozen=True)
class FactMatchConfig:
    types: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.types


@dataclass(frozen=True)
class RuleMatchConfig:
    aliases: tuple[AliasMatchConfig, ...] = ()
    facts: tuple[FactMatchConfig, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.aliases and not self.facts


@dataclass(frozen=True)
class PhraseRuleConfig:
    type: str
    label: str
    phrases: tuple[tuple[str, ...], ...]
    patterns: tuple[RulePatternConfig, ...]
    match: RuleMatchConfig = field(default_factory=RuleMatchConfig)
    group: str | None = None
    color: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class AliasRuleConfig:
    key: str
    catalog: str
    canonical: str
    kind: str
    aliases: tuple[str, ...]
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
    review_lanes: list[ReviewLaneConfig] = field(default_factory=list)


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
    match = _parse_rule_match(raw.get("match"), collection_name)
    if not phrases and not patterns and match.is_empty:
        raise ValueError(f"{collection_name} item must define phrases, patterns, or match")

    parsed_phrases: list[tuple[str, ...]] = []
    for phrase in phrases:
        if not isinstance(phrase, list) or not phrase:
            raise ValueError(f"{collection_name} phrases must be non-empty lists")
        parsed_phrases.append(tuple(str(word) for word in phrase))

    return PhraseRuleConfig(
        type=str(raw["type"]),
        label=str(raw.get("label", raw["type"])),
        group=str(raw["group"]) if raw.get("group") is not None else None,
        color=raw.get("color"),
        confidence=float(raw["confidence"]) if raw.get("confidence") is not None else None,
        phrases=tuple(parsed_phrases),
        patterns=_parse_patterns(patterns, collection_name),
        match=match,
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


def _parse_rule_match(raw_match: Any, collection_name: str) -> RuleMatchConfig:
    if raw_match is None:
        return RuleMatchConfig()
    if not isinstance(raw_match, dict):
        raise ValueError(f"{collection_name} match must be a mapping")

    aliases = _parse_alias_match_dependencies(raw_match.get("aliases", []), collection_name)
    facts = _parse_fact_match_dependencies(raw_match.get("facts", []), collection_name)
    return RuleMatchConfig(aliases=aliases, facts=facts)


def _parse_alias_match_dependencies(raw_dependencies: Any, collection_name: str) -> tuple[AliasMatchConfig, ...]:
    if not raw_dependencies:
        return ()
    if not isinstance(raw_dependencies, list):
        raise ValueError(f"{collection_name} match.aliases must be a list")

    dependencies: list[AliasMatchConfig] = []
    for raw_dependency in raw_dependencies:
        if not isinstance(raw_dependency, dict):
            raise ValueError(f"{collection_name} match.aliases item must be a mapping")
        catalogs = _parse_string_list(raw_dependency.get("catalogs", []), "match.aliases.catalogs")
        catalog = raw_dependency.get("catalog")
        if catalog is not None:
            catalogs.insert(0, str(catalog))
        dependency = AliasMatchConfig(
            catalogs=tuple(dict.fromkeys(catalogs)),
            keys=tuple(_parse_string_list(raw_dependency.get("keys", []), "match.aliases.keys")),
            kinds=tuple(_parse_string_list(raw_dependency.get("kinds", []), "match.aliases.kinds")),
        )
        if dependency.is_empty:
            raise ValueError(f"{collection_name} match.aliases item must define catalog, keys, or kinds")
        dependencies.append(dependency)

    return tuple(dependencies)


def _parse_fact_match_dependencies(raw_dependencies: Any, collection_name: str) -> tuple[FactMatchConfig, ...]:
    if not raw_dependencies:
        return ()
    if not isinstance(raw_dependencies, list):
        raise ValueError(f"{collection_name} match.facts must be a list")

    dependencies: list[FactMatchConfig] = []
    for raw_dependency in raw_dependencies:
        if isinstance(raw_dependency, str):
            dependency = FactMatchConfig(types=(raw_dependency,))
        elif isinstance(raw_dependency, dict):
            dependency = FactMatchConfig(
                types=tuple(_parse_string_list(raw_dependency.get("types", []), "match.facts.types"))
            )
        else:
            raise ValueError(f"{collection_name} match.facts item must be a string or mapping")
        if dependency.is_empty:
            raise ValueError(f"{collection_name} match.facts item must define types")
        dependencies.append(dependency)

    return tuple(dependencies)


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
        fact_types = _parse_string_list(raw.get("fact_types", []), f"{catalog_name}.fact_types")
        if not fact_types:
            raise ValueError(f"{catalog_name} item must define fact_types")
        items.append(
            AliasRuleConfig(
                key=str(raw["key"]),
                catalog=catalog_name,
                canonical=str(raw.get("canonical", raw.get("label", raw["key"]))),
                kind=str(raw.get("type", _catalog_item_kind(catalog_name))),
                aliases=tuple(aliases),
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
        review_lanes=_parse_review_lanes(raw.get("review_lanes", [])),
    )


def _parse_review_lanes(raw: Any) -> list[ReviewLaneConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("lead_scoring review_lanes must be a list")

    lanes: list[ReviewLaneConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("lead_scoring review_lanes item must be a mapping")
        lanes.append(
            ReviewLaneConfig(
                key=str(item["key"]),
                label=str(item.get("label", item["key"])),
                description=str(item["description"]) if item.get("description") is not None else None,
                priority=int(item.get("priority", 0)),
                min_score=int(item["min_score"]) if item.get("min_score") is not None else None,
                max_score=int(item["max_score"]) if item.get("max_score") is not None else None,
                temperatures=_parse_string_list(item.get("temperatures", []), "review_lanes.temperatures"),
                match_groups=_parse_review_lane_match_groups(item.get("match_groups", [])),
                excluded_signal_types=_parse_string_list(
                    item.get("excluded_signal_types", []),
                    "review_lanes.excluded_signal_types",
                ),
                excluded_fact_types=_parse_string_list(
                    item.get("excluded_fact_types", []),
                    "review_lanes.excluded_fact_types",
                ),
                excluded_reason_keys=_parse_string_list(
                    item.get("excluded_reason_keys", []),
                    "review_lanes.excluded_reason_keys",
                ),
                excluded_solution_area_types=_parse_string_list(
                    item.get("excluded_solution_area_types", []),
                    "review_lanes.excluded_solution_area_types",
                ),
                excluded_customer_segment_types=_parse_string_list(
                    item.get("excluded_customer_segment_types", []),
                    "review_lanes.excluded_customer_segment_types",
                ),
                excluded_intent_signal_types=_parse_string_list(
                    item.get("excluded_intent_signal_types", []),
                    "review_lanes.excluded_intent_signal_types",
                ),
                excluded_noise_signal_types=_parse_string_list(
                    item.get("excluded_noise_signal_types", []),
                    "review_lanes.excluded_noise_signal_types",
                ),
            )
        )
    return lanes


def _parse_review_lane_match_groups(raw: Any) -> list[ReviewLaneMatchGroup]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("lead_scoring review_lanes match_groups must be a list")

    groups: list[ReviewLaneMatchGroup] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("lead_scoring review_lanes match_group must be a mapping")
        groups.append(
            ReviewLaneMatchGroup(
                signal_types=_parse_string_list(item.get("signal_types", []), "match_group.signal_types"),
                fact_types=_parse_string_list(item.get("fact_types", []), "match_group.fact_types"),
                reason_keys=_parse_string_list(item.get("reason_keys", []), "match_group.reason_keys"),
                solution_area_types=_parse_string_list(
                    item.get("solution_area_types", []),
                    "match_group.solution_area_types",
                ),
                customer_segment_types=_parse_string_list(
                    item.get("customer_segment_types", []),
                    "match_group.customer_segment_types",
                ),
                intent_signal_types=_parse_string_list(
                    item.get("intent_signal_types", []),
                    "match_group.intent_signal_types",
                ),
                noise_signal_types=_parse_string_list(
                    item.get("noise_signal_types", []),
                    "match_group.noise_signal_types",
                ),
            )
        )
    return groups


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
