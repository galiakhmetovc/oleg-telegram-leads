"""IR signal disambiguation

Revision ID: 0022_ir_signal_disambiguation
Revises: 0021_signal_fact_dependencies
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022_ir_signal_disambiguation"
down_revision: str | None = "0021_signal_fact_dependencies"
branch_labels: str | None = None
depends_on: str | None = None

BARE_IR_PROTOCOL_ALIASES = {"IR", "ИК", "инфракрасный пульт"}
SIGNAL_FACT_DEPENDENCIES_TO_REMOVE = {
    "protocol_gateway": {"alias:protocols:infrared", "alias:devices:ir_remote"},
    "climate_automation": {"alias:protocols:infrared", "alias:devices:ir_remote"},
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
        changed = _disambiguate_ir_aliases(config)
        changed = _remove_ir_signal_dependencies(config) or changed
        if changed:
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _disambiguate_ir_aliases(config: dict[str, object]) -> bool:
    changed = False
    protocols = _document_items(config, "protocols")
    for protocol in protocols:
        if not isinstance(protocol, dict) or protocol.get("key") != "infrared":
            continue
        aliases = protocol.get("aliases")
        if not isinstance(aliases, list):
            continue
        next_aliases = [
            alias for alias in aliases if not (isinstance(alias, str) and alias in BARE_IR_PROTOCOL_ALIASES)
        ]
        if next_aliases != aliases:
            protocol["aliases"] = next_aliases
            changed = True

    devices = _document_items(config, "devices")
    climate_device = _find_item(devices, "climate_control_device")
    if climate_device is not None:
        changed = _append_alias(climate_device, "пульт для кондиционера") or changed

    ir_remote = _find_item(devices, "ir_remote")
    if ir_remote is not None:
        changed = _append_alias(ir_remote, "инфракрасный пульт") or changed
        changed = _remove_alias(ir_remote, "пульт для кондиционера") or changed

    return changed


def _remove_ir_signal_dependencies(config: dict[str, object]) -> bool:
    signals = _document_items(config, "signals")
    changed = False
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        signal_type = signal.get("type")
        to_remove = SIGNAL_FACT_DEPENDENCIES_TO_REMOVE.get(str(signal_type))
        if not to_remove:
            continue
        match = signal.get("match")
        if not isinstance(match, dict):
            continue
        facts = match.get("facts")
        if not isinstance(facts, list):
            continue
        for dependency in facts:
            if not isinstance(dependency, dict):
                continue
            types = dependency.get("types")
            if not isinstance(types, list):
                continue
            next_types = [
                fact_type
                for fact_type in types
                if not (isinstance(fact_type, str) and fact_type in to_remove)
            ]
            if next_types != types:
                dependency["types"] = next_types
                changed = True
        match["facts"] = [
            dependency
            for dependency in facts
            if not isinstance(dependency, dict)
            or not isinstance(dependency.get("types"), list)
            or dependency["types"]
        ]
    return changed


def _document_items(config: dict[str, object], document_name: str) -> list[Any]:
    document = config.get(document_name)
    if not isinstance(document, dict):
        return []
    items = document.get(document_name)
    return items if isinstance(items, list) else []


def _find_item(items: list[Any], key: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get("key") == key:
            return item
    return None


def _append_alias(item: dict[str, Any], alias: str) -> bool:
    aliases = item.get("aliases")
    if not isinstance(aliases, list):
        return False
    if alias in aliases:
        return False
    aliases.append(alias)
    return True


def _remove_alias(item: dict[str, Any], alias: str) -> bool:
    aliases = item.get("aliases")
    if not isinstance(aliases, list) or alias not in aliases:
        return False
    item["aliases"] = [value for value in aliases if value != alias]
    return True
