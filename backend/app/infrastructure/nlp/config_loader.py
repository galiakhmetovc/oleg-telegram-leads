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
class NlpPipelineConfig:
    stages: tuple[PipelineStageConfig, ...]
    signals: tuple[PhraseRuleConfig, ...]
    facts: tuple[PhraseRuleConfig, ...]

    @property
    def enabled_stages(self) -> tuple[PipelineStageConfig, ...]:
        return tuple(stage for stage in self.stages if stage.enabled)

    def is_enabled(self, stage_name: str) -> bool:
        return any(stage.name == stage_name and stage.enabled for stage in self.stages)


def load_nlp_config(config_dir: Path) -> NlpPipelineConfig:
    pipeline = _load_yaml(config_dir / "pipeline.yaml")
    signals = _load_yaml(config_dir / "signals.yaml")
    facts_path = config_dir / "facts.yaml"
    facts = _load_yaml(facts_path) if facts_path.exists() else {"facts": []}

    return NlpPipelineConfig(
        stages=tuple(_parse_stage(item) for item in pipeline.get("stages", [])),
        signals=tuple(_parse_phrase_rule(item, "signals") for item in signals.get("signals", [])),
        facts=tuple(_parse_phrase_rule(item, "facts") for item in facts.get("facts", [])),
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
            if predicate_name not in {"caseless", "normalized"}:
                raise ValueError(f"unsupported {collection_name} pattern predicate: {predicate_name}")
            tokens.append(RuleTokenConfig(predicate=predicate_name, value=str(value)))

        patterns.append(RulePatternConfig(tokens=tuple(tokens)))

    return tuple(patterns)
