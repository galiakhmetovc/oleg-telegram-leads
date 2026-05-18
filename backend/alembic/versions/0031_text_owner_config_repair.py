"""repair NLP text ownership config

Revision ID: 0031_text_owner_config_repair
Revises: 0030_enrich_config_rev
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0031_text_owner_config_repair"
down_revision: str | None = "0030_enrich_config_rev"
branch_labels: str | None = None
depends_on: str | None = None

OPERATOR_NOISE_SIGNAL_TYPE = "operator_noise"
OPERATOR_NOISE_FACT_TYPE = "operator_noise_fact"
OPERATOR_NOISE_FACT_LABEL = "Факт: операторский шум"
OPERATOR_NOISE_GROUP = "Шум / ручная разметка"
OPERATOR_NOISE_SIGNAL_WEIGHT = -50
HARD_NOISE_SCORE_CAP_KEY = "hard_noise"
HARD_NOISE_SCORE_CAP_LABEL = "Явный шум / нецелевой запрос"

CONSULTATION_DUPLICATE_SOURCE_TEXTS = {
    "помогите собрать комплект",
    "помогите подобрать комплект",
}

CONSULTATION_HELP_PATTERN = {
    "source_text": "помогите",
    "tokens": [{"normalized": "помочь"}],
}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("select id, config from nlp_config_revisions where is_active is true")
    ).mappings()
    statement = sa.text(
        """
        update nlp_config_revisions
        set config = :config
        where id = :id
        """
    ).bindparams(sa.bindparam("config", type_=JSONB))

    for row in rows:
        config = dict(row["config"] or {})
        if _repair_documents(config):
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _repair_documents(config: dict[str, Any]) -> bool:
    changed = _move_signal_text_rules_to_facts(config)
    changed = _repair_video_kit_help_duplicates(config) or changed
    changed = _remove_unknown_fact_references(config) or changed
    changed = _ensure_operator_noise_scoring(config) or changed
    changed = _remove_unknown_signal_references(config) or changed
    return changed


def _move_signal_text_rules_to_facts(config: dict[str, Any]) -> bool:
    signals = _document_list(config, "signals", "signals")
    facts = _document_list(config, "facts", "facts")
    changed = False

    for signal in signals:
        if not isinstance(signal, dict):
            continue
        phrases = signal.pop("phrases", [])
        patterns = signal.pop("patterns", [])
        if phrases:
            changed = True
        if patterns:
            changed = True
        if not _is_non_empty_list(phrases) and not _is_non_empty_list(patterns):
            continue

        signal_type = str(signal.get("type", "signal"))
        fact_type = (
            OPERATOR_NOISE_FACT_TYPE
            if signal_type == OPERATOR_NOISE_SIGNAL_TYPE
            else f"{signal_type}_fact"
        )
        fact = _find_rule(facts, fact_type)
        if fact is None:
            fact = {
                "type": fact_type,
                "label": (
                    OPERATOR_NOISE_FACT_LABEL
                    if fact_type == OPERATOR_NOISE_FACT_TYPE
                    else f"Факт: {signal.get('label', signal_type)}"
                ),
                "group": signal.get("group") or OPERATOR_NOISE_GROUP,
                "confidence": signal.get("confidence", 0.5),
            }
            facts.append(fact)
            changed = True

        if _append_unique_items(fact, "phrases", phrases):
            changed = True
        if _append_unique_items(fact, "patterns", patterns):
            changed = True
        if _ensure_signal_fact_dependency(signal, fact_type):
            changed = True

    return changed


def _repair_video_kit_help_duplicates(config: dict[str, Any]) -> bool:
    facts = _document_list(config, "facts", "facts")
    fact = _find_rule(facts, "intent_consultation")
    if fact is None:
        return False

    changed = False
    patterns = fact.get("patterns", [])
    if isinstance(patterns, list):
        next_patterns = [
            pattern
            for pattern in patterns
            if not (
                isinstance(pattern, dict)
                and str(pattern.get("source_text", "")) in CONSULTATION_DUPLICATE_SOURCE_TEXTS
            )
        ]
        if len(next_patterns) != len(patterns):
            fact["patterns"] = next_patterns
            patterns = next_patterns
            changed = True
    else:
        fact["patterns"] = []
        patterns = fact["patterns"]
        changed = True

    if _append_unique_items(fact, "patterns", [CONSULTATION_HELP_PATTERN]):
        changed = True
    return changed


def _remove_unknown_fact_references(config: dict[str, Any]) -> bool:
    emitted_fact_types = _emitted_fact_types(config)
    changed = False

    for signal in _document_list(config, "signals", "signals"):
        if not isinstance(signal, dict):
            continue
        match = signal.get("match")
        if not isinstance(match, dict):
            continue
        facts = match.get("facts")
        if not isinstance(facts, list):
            continue
        next_facts: list[Any] = []
        for dependency in facts:
            if isinstance(dependency, str):
                if dependency in emitted_fact_types:
                    next_facts.append(dependency)
                else:
                    changed = True
                continue
            if not isinstance(dependency, dict):
                next_facts.append(dependency)
                continue
            types = dependency.get("types")
            if not isinstance(types, list):
                next_facts.append(dependency)
                continue
            next_types = [fact_type for fact_type in types if str(fact_type) in emitted_fact_types]
            if len(next_types) != len(types):
                changed = True
            if next_types:
                next_dependency = dict(dependency)
                next_dependency["types"] = next_types
                next_facts.append(next_dependency)
        if next_facts != facts:
            match["facts"] = next_facts
            changed = True

    scoring = config.get("lead_scoring", {}).get("lead_scoring", {})
    if isinstance(scoring, dict):
        if _filter_fact_weight_refs(scoring, emitted_fact_types):
            changed = True
        if _filter_fact_type_lists(scoring, emitted_fact_types):
            changed = True
    return changed


def _ensure_operator_noise_scoring(config: dict[str, Any]) -> bool:
    if OPERATOR_NOISE_SIGNAL_TYPE not in _defined_signal_types(config):
        return False

    scoring = _lead_scoring(config)
    changed = False
    weights = scoring.setdefault("weights", {})
    if not isinstance(weights, dict):
        scoring["weights"] = {}
        weights = scoring["weights"]
        changed = True
    signal_weights = weights.setdefault("signals", {})
    if not isinstance(signal_weights, dict):
        weights["signals"] = {}
        signal_weights = weights["signals"]
        changed = True
    if signal_weights.get(OPERATOR_NOISE_SIGNAL_TYPE) is None:
        signal_weights[OPERATOR_NOISE_SIGNAL_TYPE] = OPERATOR_NOISE_SIGNAL_WEIGHT
        changed = True

    if _append_unique_value(scoring.setdefault("noise_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
        changed = True
    if _append_unique_value(scoring.setdefault("lead_veto_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
        changed = True
    if _ensure_operator_noise_score_cap(scoring):
        changed = True
    for lane in scoring.get("review_lanes", []) or []:
        if not isinstance(lane, dict):
            continue
        if lane.get("key") == "noise":
            for match_group in lane.setdefault("match_groups", []):
                if not isinstance(match_group, dict):
                    continue
                if _append_unique_value(match_group.setdefault("noise_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
                    changed = True
                if _append_unique_value(match_group.setdefault("signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
                    changed = True
        elif _append_unique_value(lane.setdefault("excluded_noise_signal_types", []), OPERATOR_NOISE_SIGNAL_TYPE):
            changed = True
    return changed


def _remove_unknown_signal_references(config: dict[str, Any]) -> bool:
    defined_signal_types = _defined_signal_types(config)
    scoring = config.get("lead_scoring", {}).get("lead_scoring", {})
    if not isinstance(scoring, dict):
        return False

    changed = False
    weights = scoring.get("weights", {})
    if isinstance(weights, dict):
        signal_weights = weights.get("signals")
        if isinstance(signal_weights, dict):
            stale_keys = [key for key in signal_weights if str(key) not in defined_signal_types]
            for key in stale_keys:
                signal_weights.pop(key, None)
            if stale_keys:
                changed = True

    for key in ("intent_signal_types", "noise_signal_types", "lead_veto_signal_types"):
        if _filter_string_list(scoring, key, defined_signal_types):
            changed = True

    for group_name in ("solution_areas", "customer_segments"):
        groups = scoring.get(group_name, {})
        if not isinstance(groups, dict):
            continue
        for group in groups.values():
            if isinstance(group, dict) and _filter_string_list(group, "signal_types", defined_signal_types):
                changed = True

    for cap in scoring.get("score_caps", []) or []:
        if not isinstance(cap, dict):
            continue
        for key in (
            "signal_types",
            "noise_signal_types",
            "excluded_signal_types",
            "excluded_noise_signal_types",
        ):
            if _filter_string_list(cap, key, defined_signal_types):
                changed = True

    for lane in scoring.get("review_lanes", []) or []:
        if not isinstance(lane, dict):
            continue
        if _filter_string_list(lane, "excluded_noise_signal_types", defined_signal_types):
            changed = True
        for group in lane.get("match_groups", []) or []:
            if not isinstance(group, dict):
                continue
            for key in ("signal_types", "intent_signal_types", "noise_signal_types"):
                if _filter_string_list(group, key, defined_signal_types):
                    changed = True
    return changed


def _lead_scoring(config: dict[str, Any]) -> dict[str, Any]:
    document = config.setdefault("lead_scoring", {})
    if not isinstance(document, dict):
        config["lead_scoring"] = {}
        document = config["lead_scoring"]
    scoring = document.setdefault("lead_scoring", {})
    if not isinstance(scoring, dict):
        document["lead_scoring"] = {}
        scoring = document["lead_scoring"]
    return scoring


def _ensure_operator_noise_score_cap(scoring: dict[str, Any]) -> bool:
    score_caps = scoring.setdefault("score_caps", [])
    if not isinstance(score_caps, list):
        scoring["score_caps"] = []
        score_caps = scoring["score_caps"]
    for cap in score_caps:
        if not isinstance(cap, dict) or cap.get("key") != HARD_NOISE_SCORE_CAP_KEY:
            continue
        changed = False
        cap.setdefault("label", HARD_NOISE_SCORE_CAP_LABEL)
        cap.setdefault("max_score", 0)
        noise_signal_types = cap.get("noise_signal_types")
        if not isinstance(noise_signal_types, list):
            noise_signal_types = []
            cap["noise_signal_types"] = noise_signal_types
            changed = True
        return _append_unique_value(noise_signal_types, OPERATOR_NOISE_SIGNAL_TYPE) or changed
    score_caps.append(
        {
            "key": HARD_NOISE_SCORE_CAP_KEY,
            "label": HARD_NOISE_SCORE_CAP_LABEL,
            "max_score": 0,
            "signal_types": [],
            "fact_types": [],
            "reason_keys": [],
            "noise_signal_types": [OPERATOR_NOISE_SIGNAL_TYPE],
        }
    )
    return True


def _filter_fact_weight_refs(scoring: dict[str, Any], emitted_fact_types: set[str]) -> bool:
    weights = scoring.get("weights", {})
    if not isinstance(weights, dict):
        return False
    fact_weights = weights.get("facts")
    if not isinstance(fact_weights, dict):
        return False
    stale_keys = [key for key in fact_weights if str(key) not in emitted_fact_types]
    for key in stale_keys:
        fact_weights.pop(key, None)
    return bool(stale_keys)


def _filter_fact_type_lists(scoring: dict[str, Any], emitted_fact_types: set[str]) -> bool:
    changed = False
    for group_name in ("solution_areas", "customer_segments"):
        groups = scoring.get(group_name, {})
        if not isinstance(groups, dict):
            continue
        for group in groups.values():
            if isinstance(group, dict) and _filter_string_list(group, "fact_types", emitted_fact_types):
                changed = True

    for cap in scoring.get("score_caps", []) or []:
        if not isinstance(cap, dict):
            continue
        for key in ("fact_types", "excluded_fact_types"):
            if _filter_string_list(cap, key, emitted_fact_types):
                changed = True

    for lane in scoring.get("review_lanes", []) or []:
        if not isinstance(lane, dict):
            continue
        if _filter_string_list(lane, "excluded_fact_types", emitted_fact_types):
            changed = True
        for group in lane.get("match_groups", []) or []:
            if isinstance(group, dict) and _filter_string_list(group, "fact_types", emitted_fact_types):
                changed = True
    return changed


def _filter_string_list(target: dict[str, Any], key: str, allowed: set[str]) -> bool:
    values = target.get(key)
    if not isinstance(values, list):
        return False
    next_values = [value for value in values if str(value) in allowed]
    if next_values == values:
        return False
    target[key] = next_values
    return True


def _emitted_fact_types(config: dict[str, Any]) -> set[str]:
    fact_types: set[str] = set()
    for fact in _document_list(config, "facts", "facts"):
        if isinstance(fact, dict) and fact.get("type") is not None:
            fact_types.add(str(fact["type"]))
    for catalog_name in ("vendors", "protocols", "devices", "software"):
        for item in _document_list(config, catalog_name, catalog_name):
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if key is not None:
                fact_types.add(f"alias:{catalog_name}:{key}")
            raw_fact_types = item.get("fact_types", [])
            if isinstance(raw_fact_types, list):
                fact_types.update(str(fact_type) for fact_type in raw_fact_types)
    return fact_types


def _defined_signal_types(config: dict[str, Any]) -> set[str]:
    return {
        str(signal["type"])
        for signal in _document_list(config, "signals", "signals")
        if isinstance(signal, dict) and signal.get("type") is not None
    }


def _document_list(config: dict[str, Any], document_key: str, list_key: str) -> list[Any]:
    document = config.setdefault(document_key, {})
    if not isinstance(document, dict):
        config[document_key] = {}
        document = config[document_key]
    items = document.setdefault(list_key, [])
    if not isinstance(items, list):
        document[list_key] = []
        items = document[list_key]
    return items


def _find_rule(rules: list[Any], rule_type: str) -> dict[str, Any] | None:
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == rule_type:
            return rule
    return None


def _append_unique_items(target: dict[str, Any], key: str, raw_items: Any) -> bool:
    if not _is_non_empty_list(raw_items):
        return False
    items = target.setdefault(key, [])
    if not isinstance(items, list):
        target[key] = []
        items = target[key]

    changed = False
    existing = {_stable_key(item) for item in items}
    for item in raw_items:
        item_key = _stable_key(item)
        if item_key in existing:
            continue
        items.append(item)
        existing.add(item_key)
        changed = True
    return changed


def _append_unique_value(values: Any, value: str) -> bool:
    if not isinstance(values, list) or value in values:
        return False
    values.append(value)
    return True


def _ensure_signal_fact_dependency(signal: dict[str, Any], fact_type: str) -> bool:
    match = signal.setdefault("match", {})
    if not isinstance(match, dict):
        signal["match"] = {}
        match = signal["match"]
    facts = match.setdefault("facts", [])
    if not isinstance(facts, list):
        match["facts"] = []
        facts = match["facts"]
    for dependency in facts:
        if dependency == fact_type:
            return False
        if isinstance(dependency, dict) and fact_type in dependency.get("types", []):
            return False
    facts.append({"types": [fact_type]})
    return True


def _is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _stable_key(value: Any) -> str:
    return repr(value)
