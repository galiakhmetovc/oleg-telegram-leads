"""domain without intent config guard

Revision ID: 0023_domain_intent_guard
Revises: 0022_ir_signal_disambiguation
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023_domain_intent_guard"
down_revision: str | None = "0022_ir_signal_disambiguation"
branch_labels: str | None = None
depends_on: str | None = None

DEVELOPER_SMART_HOME_PATTERNS = [
    {
        "tokens": [
            {"normalized": "умный"},
            {"normalized": "дом"},
            {"normalized": "от"},
            {"normalized": "застройщик"},
        ]
    },
    {"tokens": [{"normalized": "от"}, {"normalized": "застройщик"}]},
    {"tokens": [{"normalized": "застройщик"}, {"normalized": "говорить"}]},
]

SIGNAL_DEPENDENCIES_TO_REMOVE = {
    "protocol_gateway": {
        "alias:protocols:modbus",
        "alias:protocols:rs_485",
        "alias:protocols:mqtt",
        "alias:protocols:poe",
        "alias:protocols:ethernet",
        "alias:protocols:dali",
        "alias:protocols:one_wire",
        "alias:protocols:opentherm",
        "alias:protocols:ebus",
        "alias:protocols:rtsp",
        "alias:protocols:onvif",
    },
    "video_surveillance": {"alias:protocols:poe"},
    "power_backup": {"alias:protocols:poe", "alias:devices:smart_socket"},
    "climate_automation": {
        "alias:devices:smoke_gas_sensor",
        "alias:devices:climate_control_device",
    },
}

PLAIN_LIGHTING_ALIASES = [
    "светодиодная лента",
    "LED лента",
    "RGB лента",
    "трековый свет",
    "треки",
    "бра",
    "ночной свет",
    "дежурный свет",
    "закарнизная подсветка",
]

DOMAIN_WITHOUT_INTENT_CAP = {
    "key": "domain_without_intent",
    "label": "Домен без явного намерения",
    "max_score": 34,
    "signal_types": [
        "smart_home_automation",
        "smart_home_platform",
        "protocol_gateway",
        "video_surveillance",
        "smart_relay_control",
        "water_leak_protection",
        "leak_protection",
        "access_control",
        "intercom",
        "security_alarm",
        "gate_automation",
        "power_quality",
        "power_backup",
        "climate_control",
        "climate_automation",
        "lighting_control",
        "lighting_automation",
        "motion_lighting_automation",
        "electric_curtain_control",
        "network_infrastructure",
    ],
    "fact_types": [],
    "reason_keys": [],
    "noise_signal_types": [],
    "excluded_signal_types": [
        "need",
        "customer_intent",
        "provider_search",
        "installation_request",
        "consultation_request",
        "solution_selection_request",
        "education_request",
        "smart_home_value_question",
        "budget_constraint",
        "installation_context",
        "implementation_intent",
        "hot_lead_intent",
        "electrical_design_context",
        "developer_smart_home_context",
        "renovation_modification_context",
        "warranty_risk",
        "designer_context",
        "commercial_object",
        "country_house",
        "apartment_context",
        "family_apartment_context",
    ],
    "excluded_fact_types": [
        "solution_area",
        "property_type",
        "design_scope",
        "service_location",
        "work_type",
        "installation_surface",
        "wiring_output",
        "network_scope",
    ],
    "excluded_reason_keys": [],
    "excluded_noise_signal_types": [],
}

LIGHTING_FIXTURE_ALIAS = {
    "key": "lighting_fixture",
    "canonical": "Осветительный прибор",
    "type": "device",
    "aliases": PLAIN_LIGHTING_ALIASES,
    "fact_types": ["controlled_device"],
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
        changed = _replace_developer_context_patterns(config)
        changed = _remove_cross_domain_signal_dependencies(config) or changed
        changed = _move_plain_lighting_aliases(config) or changed
        changed = _ensure_domain_without_intent_cap(config) or changed
        if changed:
            bind.execute(statement, {"id": row["id"], "config": config})


def downgrade() -> None:
    pass


def _replace_developer_context_patterns(config: dict[str, object]) -> bool:
    signal = _find_item(_document_items(config, "signals"), "developer_smart_home_context", id_field="type")
    if signal is None or signal.get("patterns") == DEVELOPER_SMART_HOME_PATTERNS:
        return False
    signal["patterns"] = list(DEVELOPER_SMART_HOME_PATTERNS)
    return True


def _remove_cross_domain_signal_dependencies(config: dict[str, object]) -> bool:
    changed = False
    for signal in _document_items(config, "signals"):
        if not isinstance(signal, dict):
            continue
        to_remove = SIGNAL_DEPENDENCIES_TO_REMOVE.get(str(signal.get("type")))
        if not to_remove:
            continue
        changed = _remove_match_fact_types(signal, to_remove) or changed
    return changed


def _move_plain_lighting_aliases(config: dict[str, object]) -> bool:
    devices = _document_items(config, "devices")
    smart_lighting = _find_item(devices, "smart_lighting")
    lighting_fixture = _find_item(devices, "lighting_fixture")
    changed = False

    if smart_lighting is not None:
        for alias in PLAIN_LIGHTING_ALIASES:
            changed = _remove_alias(smart_lighting, alias) or changed

    if lighting_fixture is None:
        devices.append(dict(LIGHTING_FIXTURE_ALIAS))
        return True

    for alias in PLAIN_LIGHTING_ALIASES:
        changed = _append_alias(lighting_fixture, alias) or changed
    fact_types = lighting_fixture.get("fact_types")
    if not isinstance(fact_types, list):
        lighting_fixture["fact_types"] = ["controlled_device"]
        changed = True
    elif "controlled_device" not in fact_types:
        fact_types.append("controlled_device")
        changed = True
    return changed


def _ensure_domain_without_intent_cap(config: dict[str, object]) -> bool:
    scoring_document = config.get("lead_scoring")
    if not isinstance(scoring_document, dict):
        return False
    scoring = scoring_document.get("lead_scoring")
    if not isinstance(scoring, dict):
        return False
    score_caps = scoring.get("score_caps")
    if not isinstance(score_caps, list):
        scoring["score_caps"] = [dict(DOMAIN_WITHOUT_INTENT_CAP)]
        return True
    for index, cap in enumerate(score_caps):
        if isinstance(cap, dict) and cap.get("key") == DOMAIN_WITHOUT_INTENT_CAP["key"]:
            if cap == DOMAIN_WITHOUT_INTENT_CAP:
                return False
            score_caps[index] = dict(DOMAIN_WITHOUT_INTENT_CAP)
            return True
    score_caps.append(dict(DOMAIN_WITHOUT_INTENT_CAP))
    return True


def _remove_match_fact_types(signal: dict[str, Any], to_remove: set[str]) -> bool:
    match = signal.get("match")
    if not isinstance(match, dict):
        return False
    facts = match.get("facts")
    if not isinstance(facts, list):
        return False
    changed = False
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
    if not match["facts"]:
        signal.pop("match", None)
    return changed


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


def _append_alias(item: dict[str, Any], alias: str) -> bool:
    aliases = item.get("aliases")
    if not isinstance(aliases, list):
        item["aliases"] = [alias]
        return True
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
