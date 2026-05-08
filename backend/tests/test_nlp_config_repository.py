from typing import Any

from app.infrastructure.persistence.nlp_config_repository import merge_missing_default_documents


def test_merge_missing_default_documents_adds_new_document_and_pipeline_stage() -> None:
    active: dict[str, dict[str, Any]] = {
        "pipeline": {
            "stages": [
                {"name": "segmentation", "enabled": True},
                {"name": "domain_signals", "enabled": True},
            ]
        },
        "signals": {"signals": [{"type": "custom", "label": "Custom", "phrases": [["x"]]}]},
        "facts": {"facts": []},
    }
    defaults: dict[str, dict[str, Any]] = {
        "pipeline": {
            "stages": [
                {"name": "segmentation", "enabled": True},
                {"name": "domain_signals", "enabled": True},
                {"name": "lead_scoring", "enabled": True},
            ]
        },
        "signals": {"signals": [{"type": "default", "label": "Default", "phrases": [["y"]]}]},
        "facts": {"facts": []},
        "lead_scoring": {"lead_scoring": {"thresholds": {"lead": 35, "warm": 60, "hot": 90}}},
    }

    merged = merge_missing_default_documents(defaults, active)

    assert merged["signals"] == active["signals"]
    assert merged["lead_scoring"] == defaults["lead_scoring"]
    assert [stage["name"] for stage in merged["pipeline"]["stages"]] == [
        "segmentation",
        "domain_signals",
        "lead_scoring",
    ]


def test_merge_missing_default_documents_adds_new_lead_scoring_sections_without_overwriting() -> None:
    active: dict[str, dict[str, Any]] = {
        "lead_scoring": {
            "lead_scoring": {
                "thresholds": {"lead": 20, "warm": 50, "hot": 90},
                "weights": {"signals": {"custom": 99}, "facts": {}},
            }
        }
    }
    defaults: dict[str, dict[str, Any]] = {
        "lead_scoring": {
            "lead_scoring": {
                "thresholds": {"lead": 35, "warm": 60, "hot": 90},
                "weights": {"signals": {"default": 10}, "facts": {}},
                "review_lanes": [{"key": "direct_pur_lead", "label": "Прямой лид ПУР"}],
            }
        }
    }

    merged = merge_missing_default_documents(defaults, active)

    assert merged["lead_scoring"]["lead_scoring"]["thresholds"]["lead"] == 20
    assert merged["lead_scoring"]["lead_scoring"]["weights"]["signals"] == {"custom": 99}
    assert merged["lead_scoring"]["lead_scoring"]["review_lanes"] == [
        {"key": "direct_pur_lead", "label": "Прямой лид ПУР"}
    ]
