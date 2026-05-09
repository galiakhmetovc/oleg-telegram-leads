"""signal fact dependencies

Revision ID: 0021_signal_fact_dependencies
Revises: 0020_camera_signal_scoring
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0021_signal_fact_dependencies"
down_revision: str | None = "0020_camera_signal_scoring"
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
        if _convert_signal_alias_dependencies(config):
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _convert_signal_alias_dependencies(config: dict[str, object]) -> bool:
    signals_document = config.get("signals")
    if not isinstance(signals_document, dict):
        return False
    signals = signals_document.get("signals")
    if not isinstance(signals, list):
        return False

    changed = False
    catalog_keys = _catalog_keys(config)
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        match = signal.get("match")
        if not isinstance(match, dict):
            continue
        aliases = match.pop("aliases", None)
        if aliases is None:
            continue
        changed = True
        fact_types = _alias_dependencies_to_fact_types(aliases, catalog_keys)
        if fact_types:
            facts = match.setdefault("facts", [])
            if not isinstance(facts, list):
                facts = []
                match["facts"] = facts
            facts.append({"types": fact_types})
        if not match.get("facts"):
            match.pop("facts", None)
        if not match:
            signal.pop("match", None)
    return changed


def _catalog_keys(config: dict[str, object]) -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for catalog in ("vendors", "protocols", "devices", "software"):
        document = config.get(catalog)
        if not isinstance(document, dict):
            continue
        items = document.get(catalog)
        if not isinstance(items, list):
            continue
        keys[catalog] = [
            str(item["key"])
            for item in items
            if isinstance(item, dict) and item.get("key")
        ]
    return keys


def _alias_dependencies_to_fact_types(
    aliases: Any,
    catalog_keys: dict[str, list[str]],
) -> list[str]:
    if not isinstance(aliases, list):
        return []

    fact_types: list[str] = []
    for dependency in aliases:
        if not isinstance(dependency, dict):
            continue
        catalogs = _dependency_catalogs(dependency)
        explicit_keys = [
            str(key)
            for key in dependency.get("keys", []) or []
            if key
        ]
        for catalog in catalogs:
            keys = explicit_keys or catalog_keys.get(catalog, [])
            for key in keys:
                fact_type = f"alias:{catalog}:{key}"
                if fact_type not in fact_types:
                    fact_types.append(fact_type)
    return fact_types


def _dependency_catalogs(dependency: dict[str, Any]) -> list[str]:
    catalogs: list[str] = []
    if dependency.get("catalog"):
        catalogs.append(str(dependency["catalog"]))
    for catalog in dependency.get("catalogs", []) or []:
        if catalog:
            catalogs.append(str(catalog))
    return catalogs
