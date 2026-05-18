from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _migration_module() -> Any:
    path = Path("alembic/versions/0031_text_owner_config_repair.py")
    spec = importlib.util.spec_from_file_location("text_owner_config_repair", path)
    if spec is None or spec.loader is None:
        raise AssertionError("migration module must be importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alias_fact_migration_module() -> Any:
    path = Path("alembic/versions/0032_alias_fact_duplicate_repair.py")
    spec = importlib.util.spec_from_file_location("alias_fact_duplicate_repair", path)
    if spec is None or spec.loader is None:
        raise AssertionError("migration module must be importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repairs_legacy_signal_text_rules_and_operator_noise() -> None:
    migration = _migration_module()
    config: dict[str, Any] = {
        "signals": {
            "signals": [
                {
                    "type": "operator_noise",
                    "label": "Операторский шум",
                    "phrases": [["dss", "express"]],
                },
                {
                    "type": "smart_home",
                    "label": "Умный дом",
                    "group": "Домены",
                    "phrases": [["умный", "дом"]],
                    "patterns": [
                        {
                            "source_text": "умный дом",
                            "tokens": [{"normalized": "умный"}, {"normalized": "дом"}],
                        }
                    ],
                    "match": {"facts": [{"types": ["intent_need"]}]},
                },
            ]
        },
        "facts": {"facts": [{"type": "intent_need", "label": "Нужно", "phrases": [["хочу"]]}]},
        "lead_scoring": {"lead_scoring": {}},
    }

    assert migration._repair_documents(config) is True

    operator_noise = config["signals"]["signals"][0]
    smart_home = config["signals"]["signals"][1]
    assert "phrases" not in operator_noise
    assert operator_noise["match"] == {"facts": [{"types": ["operator_noise_fact"]}]}
    assert "phrases" not in smart_home
    assert "patterns" not in smart_home
    assert {"types": ["smart_home_fact"]} in smart_home["match"]["facts"]
    operator_noise_fact = next(
        fact for fact in config["facts"]["facts"] if fact["type"] == "operator_noise_fact"
    )
    assert operator_noise_fact["phrases"] == [["dss", "express"]]
    scoring = config["lead_scoring"]["lead_scoring"]
    assert scoring["weights"]["signals"]["operator_noise"] == -50
    assert "operator_noise" in scoring["noise_signal_types"]
    assert "operator_noise" in scoring["lead_veto_signal_types"]
    assert "operator_noise" in scoring["score_caps"][0]["noise_signal_types"]
    smart_home_fact = next(fact for fact in config["facts"]["facts"] if fact["type"] == "smart_home_fact")
    assert smart_home_fact["phrases"] == [["умный", "дом"]]
    assert smart_home_fact["patterns"][0]["source_text"] == "умный дом"


def test_repairs_duplicate_video_kit_help_and_stale_fact_refs() -> None:
    migration = _migration_module()
    config: dict[str, Any] = {
        "signals": {
            "signals": [
                {
                    "type": "pur_gate_automation",
                    "label": "Ворота",
                    "match": {
                        "facts": [
                            {
                                "types": [
                                    "domain_gate_automation",
                                    "alias:devices:gate_barrier",
                                ]
                            }
                        ]
                    },
                }
            ]
        },
        "facts": {
            "facts": [
                {
                    "type": "intent_consultation",
                    "label": "Консультация",
                    "patterns": [
                        {
                            "source_text": "помогите собрать комплект",
                            "tokens": [
                                {"normalized": "помочь"},
                                {"normalized": "собрать"},
                                {"normalized": "комплект"},
                            ],
                        }
                    ],
                }
            ]
        },
        "devices": {
            "devices": [
                {
                    "key": "gate_barrier",
                    "canonical": "Ворота",
                    "aliases": ["ворота"],
                    "fact_types": ["access_device"],
                }
            ]
        },
        "lead_scoring": {
            "lead_scoring": {
                "weights": {"facts": {"domain_gate_automation": 5, "access_device": 2}},
                "customer_segments": {
                    "test": {
                        "label": "Test",
                        "signal_types": [],
                        "fact_types": ["domain_gate_automation", "access_device"],
                    }
                },
            }
        },
    }

    assert migration._repair_documents(config) is True

    signal_dependency = config["signals"]["signals"][0]["match"]["facts"][0]
    assert signal_dependency == {"types": ["alias:devices:gate_barrier"]}
    patterns = config["facts"]["facts"][0]["patterns"]
    assert [pattern["source_text"] for pattern in patterns] == ["помогите"]
    scoring = config["lead_scoring"]["lead_scoring"]
    assert scoring["weights"]["facts"] == {"access_device": 2}
    assert scoring["customer_segments"]["test"]["fact_types"] == ["access_device"]


def test_removes_alias_owned_fact_texts_and_stale_refs() -> None:
    migration = _alias_fact_migration_module()
    config: dict[str, Any] = {
        "pipeline": {"stages": []},
        "signals": {
            "signals": [
                {
                    "type": "pur_gate_automation",
                    "label": "Ворота",
                    "match": {
                        "facts": [
                            {
                                "types": [
                                    "domain_gate_automation",
                                    "alias:devices:network_equipment",
                                ]
                            }
                        ]
                    },
                },
                {
                    "type": "project_context",
                    "label": "Проект",
                    "match": {"facts": [{"types": ["context_wiring_output"]}]},
                },
            ]
        },
        "facts": {
            "facts": [
                {
                    "type": "context_wiring_output",
                    "label": "Выводы",
                    "patterns": [
                        {"source_text": "вывод", "tokens": [{"normalized": "вывод"}]},
                        {
                            "source_text": "слаботочный щит",
                            "tokens": [{"normalized": "слаботочный"}, {"normalized": "щит"}],
                        },
                    ],
                },
                {
                    "type": "domain_gate_automation",
                    "label": "Ворота",
                    "patterns": [
                        {"source_text": "ворота", "tokens": [{"normalized": "ворота"}]},
                    ],
                },
            ]
        },
        "devices": {
            "devices": [
                {
                    "key": "network_equipment",
                    "canonical": "Сетевое оборудование",
                    "aliases": ["слаботочный щит", "ворота"],
                    "fact_types": ["network_scope"],
                }
            ]
        },
        "lead_scoring": {
            "lead_scoring": {
                "weights": {
                    "facts": {
                        "context_wiring_output": 1,
                        "domain_gate_automation": 5,
                    }
                },
                "solution_areas": {
                    "network": {
                        "label": "Сеть",
                        "signal_types": [],
                        "fact_types": ["context_wiring_output", "domain_gate_automation"],
                    }
                },
                "review_lanes": [
                    {
                        "key": "direct",
                        "label": "Прямой лид",
                        "match_groups": [
                            {"fact_types": ["context_wiring_output", "domain_gate_automation"]}
                        ],
                    }
                ],
            }
        },
    }

    assert migration._repair_documents(config) is True

    facts = {fact["type"]: fact for fact in config["facts"]["facts"]}
    assert [pattern["source_text"] for pattern in facts["context_wiring_output"]["patterns"]] == ["вывод"]
    assert "domain_gate_automation" not in facts
    signal_dependency = config["signals"]["signals"][0]["match"]["facts"][0]
    assert signal_dependency == {"types": ["alias:devices:network_equipment"]}
    scoring = config["lead_scoring"]["lead_scoring"]
    assert scoring["weights"]["facts"] == {"context_wiring_output": 1}
    assert scoring["solution_areas"]["network"]["fact_types"] == ["context_wiring_output"]
    assert scoring["review_lanes"][0]["match_groups"][0]["fact_types"] == ["context_wiring_output"]
