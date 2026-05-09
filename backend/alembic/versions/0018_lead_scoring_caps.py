"""lead scoring caps

Revision ID: 0018_lead_scoring_caps
Revises: 0017_enrichment_task_outbox
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018_lead_scoring_caps"
down_revision: str | None = "0017_enrichment_task_outbox"
branch_labels: str | None = None
depends_on: str | None = None

HARD_NOISE_CAP = {
    "key": "hard_noise",
    "label": "Явный шум / нецелевой запрос",
    "max_score": 0,
    "signal_types": [],
    "fact_types": [],
    "reason_keys": [],
    "noise_signal_types": [
        "supply",
        "diy_or_equipment_only",
        "irrelevant_or_sale",
        "price_only",
        "ordinary_household_system",
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
        changed = _ensure_hard_noise_score_cap(config)
        changed = _remove_broad_relay_alias(config) or changed
        if changed:
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _ensure_hard_noise_score_cap(config: dict[str, object]) -> bool:
    scoring_document = config.get("lead_scoring")
    if not isinstance(scoring_document, dict):
        return False
    scoring = scoring_document.get("lead_scoring")
    if not isinstance(scoring, dict):
        return False

    score_caps = scoring.get("score_caps")
    if not isinstance(score_caps, list):
        scoring["score_caps"] = [dict(HARD_NOISE_CAP)]
        return True
    if any(isinstance(item, dict) and item.get("key") == HARD_NOISE_CAP["key"] for item in score_caps):
        return False
    score_caps.append(dict(HARD_NOISE_CAP))
    return True


def _remove_broad_relay_alias(config: dict[str, object]) -> bool:
    devices_document = config.get("devices")
    if not isinstance(devices_document, dict):
        return False
    devices = devices_document.get("devices")
    if not isinstance(devices, list):
        return False

    changed = False
    for item in devices:
        if not isinstance(item, dict) or item.get("key") != "relay_module":
            continue
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            continue
        filtered_aliases = [alias for alias in aliases if alias != "модуль управления"]
        if filtered_aliases != aliases:
            item["aliases"] = filtered_aliases
            changed = True
    return changed
