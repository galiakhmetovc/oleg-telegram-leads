"""config guard tuning

Revision ID: 0024_config_guard_tuning
Revises: 0023_domain_intent_guard
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0024_config_guard_tuning"
down_revision: str | None = "0023_domain_intent_guard"
branch_labels: str | None = None
depends_on: str | None = None

LIGHTING_CONTROL_STALE_PATTERNS = [
    [{"normalized": "бра"}],
    [{"normalized": "трек"}],
]
SMART_RELAY_STALE_PATTERNS = [
    [
        {"normalized": "устройство"},
        {"normalized": "с"},
        {"normalized": "пульт"},
        {"normalized": "от"},
        {"normalized": "застройщик"},
    ],
    [{"normalized": "от"}, {"normalized": "застройщик"}],
    [{"normalized": "застройщик"}, {"normalized": "говорить"}],
]


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
        changed = _remove_stale_signal_patterns(config)
        changed = _remove_solution_area_from_domain_cap_exclusions(config) or changed
        if changed:
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _remove_stale_signal_patterns(config: dict[str, object]) -> bool:
    changed = False
    signals = _document_items(config, "signals")
    lighting_control = _find_item(signals, "lighting_control", id_field="type")
    if lighting_control is not None:
        changed = _remove_patterns(lighting_control, LIGHTING_CONTROL_STALE_PATTERNS) or changed

    smart_relay_control = _find_item(signals, "smart_relay_control", id_field="type")
    if smart_relay_control is not None:
        changed = _remove_patterns(smart_relay_control, SMART_RELAY_STALE_PATTERNS) or changed
    return changed


def _remove_solution_area_from_domain_cap_exclusions(config: dict[str, object]) -> bool:
    scoring_document = config.get("lead_scoring")
    if not isinstance(scoring_document, dict):
        return False
    scoring = scoring_document.get("lead_scoring")
    if not isinstance(scoring, dict):
        return False
    score_caps = scoring.get("score_caps")
    if not isinstance(score_caps, list):
        return False
    for cap in score_caps:
        if not isinstance(cap, dict) or cap.get("key") != "domain_without_intent":
            continue
        excluded_fact_types = cap.get("excluded_fact_types")
        if not isinstance(excluded_fact_types, list) or "solution_area" not in excluded_fact_types:
            return False
        cap["excluded_fact_types"] = [value for value in excluded_fact_types if value != "solution_area"]
        return True
    return False


def _remove_patterns(signal: dict[str, Any], token_patterns: list[list[dict[str, str]]]) -> bool:
    patterns = signal.get("patterns")
    if not isinstance(patterns, list):
        return False
    next_patterns = [
        pattern
        for pattern in patterns
        if not isinstance(pattern, dict) or pattern.get("tokens") not in token_patterns
    ]
    if next_patterns == patterns:
        return False
    signal["patterns"] = next_patterns
    return True


def _document_items(config: dict[str, object], document_name: str) -> list[Any]:
    document = config.get(document_name)
    if not isinstance(document, dict):
        return []
    items = document.get(document_name)
    return items if isinstance(items, list) else []


def _find_item(items: list[Any], key: str, *, id_field: str = "key") -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get(id_field) == key:
            return item
    return None
