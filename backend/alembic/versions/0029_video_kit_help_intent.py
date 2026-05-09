"""video kit help intent

Revision ID: 0029_video_kit_help_intent
Revises: 0028_video_kit_selection_intent
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0029_video_kit_help_intent"
down_revision: str | None = "0028_video_kit_selection_intent"
branch_labels: str | None = None
depends_on: str | None = None

PATTERNS_BY_FACT_TYPE = {
    "intent_need": [
        {
            "source_text": "помогите собрать",
            "tokens": [
                {"normalized": "помочь"},
                {"normalized": "собрать"},
            ],
        },
        {
            "source_text": "помогите подобрать",
            "tokens": [
                {"normalized": "помочь"},
                {"normalized": "подобрать"},
            ],
        },
    ],
    "intent_consultation": [
        {
            "source_text": "помогите собрать комплект",
            "tokens": [
                {"normalized": "помочь"},
                {"normalized": "собрать"},
                {"normalized": "комплект"},
            ],
        },
        {
            "source_text": "помогите подобрать комплект",
            "tokens": [
                {"normalized": "помочь"},
                {"normalized": "подобрать"},
                {"normalized": "комплект"},
            ],
        },
    ],
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
        if _append_patterns(config):
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _append_patterns(config: dict[str, object]) -> bool:
    facts_document = config.get("facts")
    if not isinstance(facts_document, dict):
        return False
    facts = facts_document.get("facts")
    if not isinstance(facts, list):
        return False

    changed = False
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fact_type = str(fact.get("type") or "")
        patterns = PATTERNS_BY_FACT_TYPE.get(fact_type)
        if patterns is None:
            continue
        changed = _append_unique_patterns(fact, patterns) or changed
    return changed


def _append_unique_patterns(fact: dict[str, Any], new_patterns: list[dict[str, Any]]) -> bool:
    patterns = fact.setdefault("patterns", [])
    if not isinstance(patterns, list):
        fact["patterns"] = []
        patterns = fact["patterns"]

    changed = False
    existing = {_pattern_key(pattern) for pattern in patterns if isinstance(pattern, dict)}
    for pattern in new_patterns:
        key = _pattern_key(pattern)
        if key in existing:
            continue
        patterns.append(pattern)
        existing.add(key)
        changed = True
    return changed


def _pattern_key(pattern: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    raw_tokens = pattern.get("tokens")
    if not isinstance(raw_tokens, list):
        return ()
    key: list[tuple[str, str]] = []
    for token in raw_tokens:
        if not isinstance(token, dict):
            continue
        key.append((str(token.get("predicate", "normalized")), str(token.get("normalized", ""))))
    return tuple(key)
