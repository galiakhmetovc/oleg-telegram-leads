"""repair alias-owned fact text duplicates

Revision ID: 0032_alias_fact_duplicate_repair
Revises: 0031_text_owner_config_repair
Create Date: 2026-05-10
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0032_alias_fact_duplicate_repair"
down_revision: str | None = "0031_text_owner_config_repair"
branch_labels: str | None = None
depends_on: str | None = None


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
    changed = _remove_alias_owned_fact_texts(config)
    changed = _remove_empty_fact_rules(config) or changed
    changed = _remove_unknown_fact_references(config) or changed
    return changed


def _remove_alias_owned_fact_texts(config: dict[str, Any]) -> bool:
    alias_text_keys = _alias_text_keys(config)
    if not alias_text_keys:
        return False

    changed = False
    for fact in _document_list(config, "facts", "facts"):
        if not isinstance(fact, dict):
            continue
        if _filter_text_items(fact, "phrases", alias_text_keys, _phrase_source_text):
            changed = True
        if _filter_text_items(fact, "patterns", alias_text_keys, _pattern_source_text):
            changed = True
    return changed


def _remove_empty_fact_rules(config: dict[str, Any]) -> bool:
    facts = _document_list(config, "facts", "facts")
    next_facts = [
        fact
        for fact in facts
        if not (
            isinstance(fact, dict)
            and not fact.get("phrases")
            and not fact.get("patterns")
            and not fact.get("match")
        )
    ]
    if len(next_facts) == len(facts):
        return False
    config["facts"]["facts"] = next_facts
    return True


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


def _filter_text_items(
    target: dict[str, Any],
    key: str,
    alias_text_keys: set[str],
    source_text: Any,
) -> bool:
    items = target.get(key)
    if not isinstance(items, list):
        return False
    next_items = [
        item
        for item in items
        if (text := source_text(item)) is None or _text_ownership_key(text) not in alias_text_keys
    ]
    if next_items == items:
        return False
    if next_items:
        target[key] = next_items
    else:
        target.pop(key, None)
    return True


def _phrase_source_text(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    return " ".join(str(token) for token in value)


def _pattern_source_text(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("source_text") is None:
        return None
    return str(value["source_text"])


def _alias_text_keys(config: dict[str, Any]) -> set[str]:
    text_keys: set[str] = set()
    for catalog_name in ("vendors", "protocols", "devices", "software"):
        for item in _document_list(config, catalog_name, catalog_name):
            if not isinstance(item, dict):
                continue
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                continue
            text_keys.update(_text_ownership_key(str(alias)) for alias in aliases)
    return {text_key for text_key in text_keys if text_key}


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


def _text_ownership_key(value: str) -> str:
    chars: list[str] = []
    for token in re.findall(r"\w+", value, flags=re.UNICODE):
        target_script = _dominant_script(token)
        normalized_token = token.casefold().replace("ё", "е")
        for char in normalized_token:
            if target_script == "cyrillic":
                normalized = _LATIN_TO_CYRILLIC_CONFUSABLES.get(char, char)
            elif target_script == "latin":
                normalized = _CYRILLIC_TO_LATIN_CONFUSABLES.get(char, char)
            else:
                normalized = char
            if normalized.isalnum():
                chars.append(normalized)
    return "".join(chars)


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
