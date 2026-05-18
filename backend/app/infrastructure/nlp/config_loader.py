from __future__ import annotations

import re
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
class AliasMatchingConfig:
    normalize_separators: bool = True
    normalize_yo: bool = True
    normalize_latin_confusables: bool = True
    fuzzy_enabled: bool = True
    fuzzy_min_length: int = 5
    fuzzy_max_distance: int = 1
    fuzzy_long_min_length: int = 10
    fuzzy_long_max_distance: int = 2
    fuzzy_excluded_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleTokenConfig:
    predicate: str
    value: str


@dataclass(frozen=True)
class RulePatternConfig:
    tokens: tuple[RuleTokenConfig, ...]


@dataclass(frozen=True)
class FactMatchConfig:
    types: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.types


@dataclass(frozen=True)
class RuleMatchConfig:
    facts: tuple[FactMatchConfig, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.facts


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
    lead_veto_signal_types: list[str] | None = None
    score_caps: list[LeadScoreCapConfig] = field(default_factory=list)
    review_lanes: list[ReviewLaneConfig] = field(default_factory=list)


@dataclass(frozen=True)
class LeadScoreCapConfig:
    key: str
    label: str
    max_score: int
    signal_types: list[str] = field(default_factory=list)
    fact_types: list[str] = field(default_factory=list)
    reason_keys: list[str] = field(default_factory=list)
    noise_signal_types: list[str] = field(default_factory=list)
    excluded_signal_types: list[str] = field(default_factory=list)
    excluded_fact_types: list[str] = field(default_factory=list)
    excluded_reason_keys: list[str] = field(default_factory=list)
    excluded_noise_signal_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NlpPipelineConfig:
    stages: tuple[PipelineStageConfig, ...]
    signals: tuple[PhraseRuleConfig, ...]
    facts: tuple[PhraseRuleConfig, ...]
    aliases: tuple[AliasRuleConfig, ...]
    lead_scoring: LeadScoringConfig
    alias_matching: AliasMatchingConfig = field(default_factory=AliasMatchingConfig)

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
    alias_matching = _parse_alias_matching(pipeline.get("alias_matching", {}))
    _validate_no_signal_text_rules(signals)
    _validate_rule_text_ownership(documents, alias_matching)
    _validate_references(documents)
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
        alias_matching=alias_matching,
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


def _parse_alias_matching(raw: Any) -> AliasMatchingConfig:
    if raw is None:
        return AliasMatchingConfig()
    if not isinstance(raw, dict):
        raise ValueError("pipeline alias_matching must be a mapping")
    min_length = _parse_int(raw.get("fuzzy_min_length", 5), "alias_matching.fuzzy_min_length")
    max_distance = _parse_int(raw.get("fuzzy_max_distance", 1), "alias_matching.fuzzy_max_distance")
    long_min_length = _parse_int(raw.get("fuzzy_long_min_length", 10), "alias_matching.fuzzy_long_min_length")
    long_max_distance = _parse_int(
        raw.get("fuzzy_long_max_distance", 2),
        "alias_matching.fuzzy_long_max_distance",
    )
    if min_length < 1:
        raise ValueError("alias_matching.fuzzy_min_length must be >= 1")
    if max_distance < 0 or long_max_distance < 0:
        raise ValueError("alias_matching fuzzy distance must be >= 0")
    if long_min_length < min_length:
        raise ValueError("alias_matching.fuzzy_long_min_length must be >= fuzzy_min_length")
    return AliasMatchingConfig(
        normalize_separators=bool(raw.get("normalize_separators", True)),
        normalize_yo=bool(raw.get("normalize_yo", True)),
        normalize_latin_confusables=bool(raw.get("normalize_latin_confusables", True)),
        fuzzy_enabled=bool(raw.get("fuzzy_enabled", True)),
        fuzzy_min_length=min_length,
        fuzzy_max_distance=max_distance,
        fuzzy_long_min_length=long_min_length,
        fuzzy_long_max_distance=long_max_distance,
        fuzzy_excluded_aliases=tuple(
            item.casefold()
            for item in _parse_string_list(
                raw.get("fuzzy_excluded_aliases", []),
                "alias_matching.fuzzy_excluded_aliases",
            )
        ),
    )


def _parse_int(raw: Any, name: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_phrase_rule(raw: Any, collection_name: str) -> PhraseRuleConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"{collection_name} item must be a mapping")

    phrases = raw.get("phrases", [])
    patterns = raw.get("patterns", [])
    match = _parse_rule_match(raw.get("match"), collection_name)
    if collection_name == "signals":
        if phrases or patterns or match.is_empty:
            raise ValueError(
                "signals must use match.facts; put text phrases in facts or alias catalogs"
            )
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


def _validate_rule_text_ownership(
    documents: dict[str, dict[str, Any]],
    alias_matching: AliasMatchingConfig,
) -> None:
    text_owners: dict[str, tuple[str, str]] = {}
    for catalog_name in _alias_catalog_names():
        raw_items = documents.get(catalog_name, {catalog_name: []}).get(catalog_name, [])
        if not raw_items:
            continue
        if not isinstance(raw_items, list):
            raise ValueError(f"{catalog_name} must be a list")
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise ValueError(f"{catalog_name} item must be a mapping")
            key = str(raw_item.get("key", ""))
            owner = ("alias", f"{catalog_name}:{key}")
            for alias_text in _raw_string_list(raw_item.get("aliases", [])):
                _register_text_owner(text_owners, alias_text, owner, alias_matching)

    for collection_name in ("facts", "signals"):
        raw_rules = documents.get(collection_name, {collection_name: []}).get(collection_name, [])
        if not raw_rules:
            continue
        if not isinstance(raw_rules, list):
            raise ValueError(f"{collection_name} must be a list")
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                raise ValueError(f"{collection_name} item must be a mapping")
            rule_type = str(raw_rule.get("type", ""))
            for source_text in _rule_source_texts(raw_rule):
                _register_text_owner(
                    text_owners,
                    source_text,
                    (collection_name, rule_type),
                    alias_matching,
                )


def _register_text_owner(
    text_owners: dict[str, tuple[str, str]],
    raw_text: str,
    owner: tuple[str, str],
    alias_matching: AliasMatchingConfig,
) -> None:
    text_key = _text_ownership_key(raw_text, alias_matching)
    if not text_key:
        return
    existing = text_owners.get(text_key)
    if existing is None:
        text_owners[text_key] = owner
        return
    if existing == owner:
        return

    owner_kind, owner_name = owner
    existing_kind, existing_name = existing
    if owner_kind in {"facts", "signals"} and existing_kind == "alias":
        raise ValueError(
            f"{owner_kind} rule {owner_name} duplicates alias text {raw_text!r}; "
            f"alias text is already owned by {existing_name}"
        )
    if owner_kind == "alias" and existing_kind == "alias":
        raise ValueError(
            f"alias text {raw_text!r} is already owned by {existing_name}; "
            f"duplicate owner {owner_name}"
        )
    raise ValueError(
        f"{owner_kind} rule {owner_name} duplicates text {raw_text!r}; "
        f"text is already owned by {existing_kind}:{existing_name}"
    )


def _validate_no_signal_text_rules(signals_document: dict[str, Any]) -> None:
    raw_signals = signals_document.get("signals", [])
    if not isinstance(raw_signals, list):
        return
    for raw_signal in raw_signals:
        if not isinstance(raw_signal, dict):
            continue
        if raw_signal.get("phrases") or raw_signal.get("patterns"):
            raise ValueError(
                "signals must use match.facts; put text phrases in facts or alias catalogs"
            )


def _rule_source_texts(raw_rule: dict[str, Any]) -> tuple[str, ...]:
    source_texts: list[str] = []
    for raw_phrase in raw_rule.get("phrases", []) or []:
        if isinstance(raw_phrase, list):
            source_texts.append(" ".join(str(token) for token in raw_phrase))
    for raw_pattern in raw_rule.get("patterns", []) or []:
        if isinstance(raw_pattern, dict) and raw_pattern.get("source_text") is not None:
            source_texts.append(str(raw_pattern["source_text"]))
    return tuple(source_texts)


def _raw_string_list(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("aliases must be a list")
    return tuple(str(item) for item in raw)


def _validate_references(documents: dict[str, dict[str, Any]]) -> None:
    emitted_fact_types = _emitted_fact_types(documents)
    defined_signal_types = _defined_signal_types(documents)
    for raw_signal in documents.get("signals", {"signals": []}).get("signals", []) or []:
        if not isinstance(raw_signal, dict):
            continue
        signal_type = str(raw_signal.get("type", ""))
        for fact_type in _rule_match_fact_types(raw_signal):
            if fact_type not in emitted_fact_types:
                raise ValueError(
                    f"signals rule {signal_type} references unknown fact type {fact_type}"
                )

    lead_scoring = documents.get("lead_scoring", {}).get("lead_scoring", {})
    if not isinstance(lead_scoring, dict):
        return
    for path, fact_type in _lead_scoring_fact_references(lead_scoring):
        if fact_type not in emitted_fact_types:
            raise ValueError(f"lead_scoring {path} references unknown fact type {fact_type}")
    for path, signal_type in _lead_scoring_signal_references(lead_scoring):
        if signal_type not in defined_signal_types:
            raise ValueError(f"lead_scoring {path} references unknown signal type {signal_type}")


def _emitted_fact_types(documents: dict[str, dict[str, Any]]) -> set[str]:
    fact_types: set[str] = set()
    for raw_rule in documents.get("facts", {"facts": []}).get("facts", []) or []:
        if isinstance(raw_rule, dict) and raw_rule.get("type") is not None:
            fact_types.add(str(raw_rule["type"]))
    for catalog_name in _alias_catalog_names():
        for raw_item in documents.get(catalog_name, {catalog_name: []}).get(catalog_name, []) or []:
            if not isinstance(raw_item, dict):
                continue
            key = raw_item.get("key")
            if key is not None:
                fact_types.add(f"alias:{catalog_name}:{key}")
            fact_types.update(_raw_string_list(raw_item.get("fact_types", [])))
    return fact_types


def _defined_signal_types(documents: dict[str, dict[str, Any]]) -> set[str]:
    return {
        str(raw_rule["type"])
        for raw_rule in documents.get("signals", {"signals": []}).get("signals", []) or []
        if isinstance(raw_rule, dict) and raw_rule.get("type") is not None
    }


def _rule_match_fact_types(raw_rule: dict[str, Any]) -> tuple[str, ...]:
    raw_match = raw_rule.get("match")
    if not isinstance(raw_match, dict):
        return ()
    raw_facts = raw_match.get("facts", [])
    if not isinstance(raw_facts, list):
        return ()
    fact_types: list[str] = []
    for dependency in raw_facts:
        if isinstance(dependency, str):
            fact_types.append(dependency)
        elif isinstance(dependency, dict):
            fact_types.extend(_raw_string_list(dependency.get("types", [])))
    return tuple(fact_types)


def _lead_scoring_signal_references(raw: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    references: list[tuple[str, str]] = []
    weights = raw.get("weights", {})
    if isinstance(weights, dict) and isinstance(weights.get("signals"), dict):
        references.extend(("weights.signals", str(signal_type)) for signal_type in weights["signals"])
    for signal_type in _raw_string_list(raw.get("intent_signal_types", [])):
        references.append(("intent_signal_types", signal_type))
    for signal_type in _raw_string_list(raw.get("noise_signal_types", [])):
        references.append(("noise_signal_types", signal_type))
    for signal_type in _raw_string_list(raw.get("lead_veto_signal_types", [])):
        references.append(("lead_veto_signal_types", signal_type))
    for group_name in ("solution_areas", "customer_segments"):
        groups = raw.get(group_name, {})
        if not isinstance(groups, dict):
            continue
        for key, value in groups.items():
            if not isinstance(value, dict):
                continue
            references.extend(
                (f"{group_name}.{key}.signal_types", signal_type)
                for signal_type in _raw_string_list(value.get("signal_types", []))
            )
    for index, cap in enumerate(raw.get("score_caps", []) or []):
        if not isinstance(cap, dict):
            continue
        for list_name in (
            "signal_types",
            "noise_signal_types",
            "excluded_signal_types",
            "excluded_noise_signal_types",
        ):
            references.extend(
                (f"score_caps[{index}].{list_name}", signal_type)
                for signal_type in _raw_string_list(cap.get(list_name, []))
            )
    for index, lane in enumerate(raw.get("review_lanes", []) or []):
        if not isinstance(lane, dict):
            continue
        references.extend(
            (f"review_lanes[{index}].excluded_noise_signal_types", signal_type)
            for signal_type in _raw_string_list(lane.get("excluded_noise_signal_types", []))
        )
        for group_index, group in enumerate(lane.get("match_groups", []) or []):
            if not isinstance(group, dict):
                continue
            for list_name in ("signal_types", "intent_signal_types", "noise_signal_types"):
                references.extend(
                    (f"review_lanes[{index}].match_groups[{group_index}].{list_name}", signal_type)
                    for signal_type in _raw_string_list(group.get(list_name, []))
                )
    return tuple(references)


def _lead_scoring_fact_references(raw: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    references: list[tuple[str, str]] = []
    weights = raw.get("weights", {})
    if isinstance(weights, dict) and isinstance(weights.get("facts"), dict):
        references.extend(("weights.facts", str(fact_type)) for fact_type in weights["facts"])
    for group_name in ("solution_areas", "customer_segments"):
        groups = raw.get(group_name, {})
        if not isinstance(groups, dict):
            continue
        for key, value in groups.items():
            if not isinstance(value, dict):
                continue
            references.extend(
                (f"{group_name}.{key}.fact_types", fact_type)
                for fact_type in _raw_string_list(value.get("fact_types", []))
            )
    for index, cap in enumerate(raw.get("score_caps", []) or []):
        if not isinstance(cap, dict):
            continue
        references.extend(
            (f"score_caps[{index}].fact_types", fact_type)
            for fact_type in _raw_string_list(cap.get("fact_types", []))
        )
        references.extend(
            (f"score_caps[{index}].excluded_fact_types", fact_type)
            for fact_type in _raw_string_list(cap.get("excluded_fact_types", []))
        )
    for index, lane in enumerate(raw.get("review_lanes", []) or []):
        if not isinstance(lane, dict):
            continue
        references.extend(
            (f"review_lanes[{index}].excluded_fact_types", fact_type)
            for fact_type in _raw_string_list(lane.get("excluded_fact_types", []))
        )
        for group_index, group in enumerate(lane.get("match_groups", []) or []):
            if not isinstance(group, dict):
                continue
            references.extend(
                (f"review_lanes[{index}].match_groups[{group_index}].fact_types", fact_type)
                for fact_type in _raw_string_list(group.get("fact_types", []))
            )
    return tuple(references)


def _text_ownership_key(value: str, alias_matching: AliasMatchingConfig) -> str:
    chars: list[str] = []
    for token in re.findall(r"\w+", value, flags=re.UNICODE):
        target_script = _dominant_script(token) if alias_matching.normalize_latin_confusables else None
        for char in token:
            normalized = _normalize_ownership_char(char, alias_matching, target_script)
            chars.extend(item for item in normalized if item.isalnum())
    return "".join(chars)


def _normalize_ownership_char(
    char: str,
    alias_matching: AliasMatchingConfig,
    target_script: str | None,
) -> str:
    value = char.casefold()
    if alias_matching.normalize_yo:
        value = value.replace("ё", "е")
    if target_script == "cyrillic":
        return "".join(_LATIN_TO_CYRILLIC_CONFUSABLES.get(item, item) for item in value)
    if target_script == "latin":
        return "".join(_CYRILLIC_TO_LATIN_CONFUSABLES.get(item, item) for item in value)
    return value


def _dominant_script(token: str) -> str | None:
    value = token.casefold()
    latin_count = sum(1 for char in value if "a" <= char <= "z")
    cyrillic_count = sum(1 for char in value if "а" <= char <= "я" or char == "ё")
    if cyrillic_count > 0 and cyrillic_count >= latin_count:
        return "cyrillic"
    if latin_count > 0:
        return "latin"
    return None


_LATIN_TO_CYRILLIC_CONFUSABLES = {
    "a": "а",
    "b": "в",
    "c": "с",
    "e": "е",
    "h": "н",
    "k": "к",
    "m": "м",
    "o": "о",
    "p": "р",
    "t": "т",
    "x": "х",
    "y": "у",
}

_CYRILLIC_TO_LATIN_CONFUSABLES = {
    "а": "a",
    "в": "b",
    "с": "c",
    "е": "e",
    "н": "h",
    "к": "k",
    "м": "m",
    "о": "o",
    "р": "p",
    "т": "t",
    "х": "x",
    "у": "y",
}


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

    if "aliases" in raw_match:
        raise ValueError(f"{collection_name} match.aliases is not supported; use match.facts with alias:<catalog>:<key>")
    facts = _parse_fact_match_dependencies(raw_match.get("facts", []), collection_name)
    return RuleMatchConfig(facts=facts)


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
        lead_veto_signal_types=(
            _parse_string_list(raw["lead_veto_signal_types"], "lead_veto_signal_types")
            if "lead_veto_signal_types" in raw
            else None
        ),
        score_caps=_parse_score_caps(raw.get("score_caps", [])),
        review_lanes=_parse_review_lanes(raw.get("review_lanes", [])),
    )


def _parse_score_caps(raw: Any) -> list[LeadScoreCapConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("lead_scoring score_caps must be a list")

    caps: list[LeadScoreCapConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("lead_scoring score_caps item must be a mapping")
        caps.append(
            LeadScoreCapConfig(
                key=str(item["key"]),
                label=str(item.get("label", item["key"])),
                max_score=int(item.get("max_score", 0)),
                signal_types=_parse_string_list(item.get("signal_types", []), "score_caps.signal_types"),
                fact_types=_parse_string_list(item.get("fact_types", []), "score_caps.fact_types"),
                reason_keys=_parse_string_list(item.get("reason_keys", []), "score_caps.reason_keys"),
                noise_signal_types=_parse_string_list(
                    item.get("noise_signal_types", []),
                    "score_caps.noise_signal_types",
                ),
                excluded_signal_types=_parse_string_list(
                    item.get("excluded_signal_types", []),
                    "score_caps.excluded_signal_types",
                ),
                excluded_fact_types=_parse_string_list(
                    item.get("excluded_fact_types", []),
                    "score_caps.excluded_fact_types",
                ),
                excluded_reason_keys=_parse_string_list(
                    item.get("excluded_reason_keys", []),
                    "score_caps.excluded_reason_keys",
                ),
                excluded_noise_signal_types=_parse_string_list(
                    item.get("excluded_noise_signal_types", []),
                    "score_caps.excluded_noise_signal_types",
                ),
            )
        )
    return caps


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
