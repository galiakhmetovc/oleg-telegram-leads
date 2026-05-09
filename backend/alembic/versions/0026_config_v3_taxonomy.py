"""config v3 taxonomy

Revision ID: 0026_config_v3_taxonomy
Revises: 0025_domain_cap_intent_only
Create Date: 2026-05-09
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0026_config_v3_taxonomy"
down_revision: str | None = "0025_domain_cap_intent_only"
branch_labels: str | None = None
depends_on: str | None = None

OPERATOR_NOISE_SIGNAL_TYPE = "operator_noise"
V3_DOCUMENT_NAMES = ("facts", "signals", "lead_scoring")


def upgrade() -> None:
    bind = op.get_bind()
    active_row = bind.execute(
        sa.text(
            """
            select id, revision, config
            from nlp_config_revisions
            where is_active is true
            order by revision desc
            limit 1
            """
        )
    ).mappings().first()
    if active_row is None:
        return

    active_config = dict(active_row["config"] or {})
    v3_documents = _read_v3_documents()
    new_config = deepcopy(active_config)
    for document_name in V3_DOCUMENT_NAMES:
        new_config[document_name] = deepcopy(v3_documents[document_name])

    operator_noise_signal = _find_signal(active_config, OPERATOR_NOISE_SIGNAL_TYPE)
    if operator_noise_signal is not None:
        _append_signal(new_config, operator_noise_signal)
        _connect_operator_noise_to_scoring(new_config)

    next_revision = int(
        bind.execute(sa.text("select coalesce(max(revision), 0) + 1 from nlp_config_revisions")).scalar_one()
    )
    bind.execute(
        sa.text("update nlp_config_revisions set is_active = false where is_active is true")
    )
    bind.execute(
        sa.text(
            """
            insert into nlp_config_revisions (id, revision, config, is_active, source, created_at)
            values (:id, :revision, :config, true, :source, :created_at)
            """
        ).bindparams(sa.bindparam("config", type_=JSONB)),
        {
            "id": uuid4(),
            "revision": next_revision,
            "config": new_config,
            "source": "migration_0026_config_v3_taxonomy",
            "created_at": datetime.now(UTC),
        },
    )


def downgrade() -> None:
    pass


def _read_v3_documents() -> dict[str, dict[str, object]]:
    config_dir = Path(__file__).resolve().parents[2] / "config" / "nlp"
    return {
        document_name: _load_yaml(config_dir / f"{document_name}.yaml")
        for document_name in V3_DOCUMENT_NAMES
    }


def _load_yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def _find_signal(config: dict[str, object], signal_type: str) -> dict[str, object] | None:
    signals_document = config.get("signals")
    if not isinstance(signals_document, dict):
        return None
    signals = signals_document.get("signals")
    if not isinstance(signals, list):
        return None
    for signal in signals:
        if isinstance(signal, dict) and signal.get("type") == signal_type:
            return deepcopy(signal)
    return None


def _append_signal(config: dict[str, object], signal: dict[str, object]) -> None:
    signals_document = config.get("signals")
    if not isinstance(signals_document, dict):
        return
    signals = signals_document.setdefault("signals", [])
    if not isinstance(signals, list):
        signals_document["signals"] = [signal]
        return
    if any(isinstance(item, dict) and item.get("type") == signal.get("type") for item in signals):
        return
    signals.append(signal)


def _connect_operator_noise_to_scoring(config: dict[str, object]) -> None:
    scoring = _scoring(config)
    if scoring is None:
        return
    weights = scoring.setdefault("weights", {})
    if isinstance(weights, dict):
        signal_weights = weights.setdefault("signals", {})
        if isinstance(signal_weights, dict):
            signal_weights.setdefault(OPERATOR_NOISE_SIGNAL_TYPE, -50)

    for field_name in ("noise_signal_types", "lead_veto_signal_types"):
        values = scoring.setdefault(field_name, [])
        if isinstance(values, list) and OPERATOR_NOISE_SIGNAL_TYPE not in values:
            values.append(OPERATOR_NOISE_SIGNAL_TYPE)

    score_caps = scoring.setdefault("score_caps", [])
    if isinstance(score_caps, list):
        hard_noise = _find_mapping_by_key(score_caps, "hard_noise")
        if hard_noise is not None:
            values = hard_noise.setdefault("noise_signal_types", [])
            if isinstance(values, list) and OPERATOR_NOISE_SIGNAL_TYPE not in values:
                values.append(OPERATOR_NOISE_SIGNAL_TYPE)

    review_lanes = scoring.setdefault("review_lanes", [])
    if isinstance(review_lanes, list):
        noise_lane = _find_mapping_by_key(review_lanes, "noise")
        if noise_lane is not None:
            match_groups = noise_lane.setdefault("match_groups", [])
            if isinstance(match_groups, list) and match_groups:
                first_group = match_groups[0]
                if isinstance(first_group, dict):
                    values = first_group.setdefault("noise_signal_types", [])
                    if isinstance(values, list) and OPERATOR_NOISE_SIGNAL_TYPE not in values:
                        values.append(OPERATOR_NOISE_SIGNAL_TYPE)


def _scoring(config: dict[str, object]) -> dict[str, object] | None:
    scoring_document = config.get("lead_scoring")
    if not isinstance(scoring_document, dict):
        return None
    scoring = scoring_document.get("lead_scoring")
    return scoring if isinstance(scoring, dict) else None


def _find_mapping_by_key(items: list[object], key: str) -> dict[str, object] | None:
    for item in items:
        if isinstance(item, dict) and item.get("key") == key:
            return item
    return None
