"""domain cap intent only

Revision ID: 0025_domain_cap_intent_only
Revises: 0024_config_guard_tuning
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0025_domain_cap_intent_only"
down_revision: str | None = "0024_config_guard_tuning"
branch_labels: str | None = None
depends_on: str | None = None

INTENT_EXCLUDED_SIGNAL_TYPES = [
    "need",
    "customer_intent",
    "provider_search",
    "installation_request",
    "consultation_request",
    "solution_selection_request",
    "education_request",
    "smart_home_value_question",
    "implementation_intent",
    "hot_lead_intent",
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
        if _tune_domain_without_intent_cap(config):
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _tune_domain_without_intent_cap(config: dict[str, object]) -> bool:
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
        changed = False
        if cap.get("excluded_signal_types") != INTENT_EXCLUDED_SIGNAL_TYPES:
            cap["excluded_signal_types"] = list(INTENT_EXCLUDED_SIGNAL_TYPES)
            changed = True
        for field_name in ("excluded_fact_types", "excluded_reason_keys", "excluded_noise_signal_types"):
            if cap.get(field_name) != []:
                cap[field_name] = []
                changed = True
        return changed
    return False
