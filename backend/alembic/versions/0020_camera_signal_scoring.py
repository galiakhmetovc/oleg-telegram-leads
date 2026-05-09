"""camera signal scoring

Revision ID: 0020_camera_signal_scoring
Revises: 0019_operator_noise_score_cap
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020_camera_signal_scoring"
down_revision: str | None = "0019_operator_noise_score_cap"
branch_labels: str | None = None
depends_on: str | None = None

VIDEO_DEVICE_KEYS = {"camera", "nvr_dvr"}


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
        changed = _set_video_device_facts(config)
        changed = _lower_video_surveillance_weight(config) or changed
        if changed:
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _set_video_device_facts(config: dict[str, object]) -> bool:
    devices_document = config.get("devices")
    if not isinstance(devices_document, dict):
        return False
    devices = devices_document.get("devices")
    if not isinstance(devices, list):
        return False

    changed = False
    for device in devices:
        if not isinstance(device, dict) or device.get("key") not in VIDEO_DEVICE_KEYS:
            continue
        if device.get("fact_types") != ["video_device"]:
            device["fact_types"] = ["video_device"]
            changed = True
    return changed


def _lower_video_surveillance_weight(config: dict[str, object]) -> bool:
    scoring_document = config.get("lead_scoring")
    if not isinstance(scoring_document, dict):
        return False
    scoring = scoring_document.get("lead_scoring")
    if not isinstance(scoring, dict):
        return False
    weights = scoring.get("weights")
    if not isinstance(weights, dict):
        return False
    signal_weights = weights.get("signals")
    if not isinstance(signal_weights, dict):
        return False
    if signal_weights.get("video_surveillance") == 25:
        return False
    signal_weights["video_surveillance"] = 25
    return True
