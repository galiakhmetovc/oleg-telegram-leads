"""operator noise score cap

Revision ID: 0019_operator_noise_score_cap
Revises: 0018_lead_scoring_caps
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0019_operator_noise_score_cap"
down_revision: str | None = "0018_lead_scoring_caps"
branch_labels: str | None = None
depends_on: str | None = None

HARD_NOISE_CAP_KEY = "hard_noise"
HARD_NOISE_CAP_LABEL = "Явный шум / нецелевой запрос"
OPERATOR_NOISE_SIGNAL_TYPE = "operator_noise"


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
        if _ensure_operator_noise_score_cap(config):
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _ensure_operator_noise_score_cap(config: dict[str, object]) -> bool:
    scoring_document = config.get("lead_scoring")
    if not isinstance(scoring_document, dict):
        return False
    scoring = scoring_document.get("lead_scoring")
    if not isinstance(scoring, dict):
        return False

    score_caps = scoring.get("score_caps")
    if not isinstance(score_caps, list):
        scoring["score_caps"] = [_operator_noise_score_cap()]
        return True

    for cap in score_caps:
        if not isinstance(cap, dict) or cap.get("key") != HARD_NOISE_CAP_KEY:
            continue
        noise_signal_types = cap.get("noise_signal_types")
        if not isinstance(noise_signal_types, list):
            cap["noise_signal_types"] = [OPERATOR_NOISE_SIGNAL_TYPE]
            return True
        if OPERATOR_NOISE_SIGNAL_TYPE in noise_signal_types:
            return False
        noise_signal_types.append(OPERATOR_NOISE_SIGNAL_TYPE)
        return True

    score_caps.append(_operator_noise_score_cap())
    return True


def _operator_noise_score_cap() -> dict[str, object]:
    return {
        "key": HARD_NOISE_CAP_KEY,
        "label": HARD_NOISE_CAP_LABEL,
        "max_score": 0,
        "signal_types": [],
        "fact_types": [],
        "reason_keys": [],
        "noise_signal_types": [OPERATOR_NOISE_SIGNAL_TYPE],
    }
