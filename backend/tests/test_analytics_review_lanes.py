from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.application.review_lanes import ReviewLaneConfig, ReviewLaneMatchGroup, assign_review_lane
from app.cli.import_analytics import _build_aggregates, _read_candidates
from app.domain.analytics import AnalyticsCandidate


def test_assigns_first_matching_review_lane_by_priority() -> None:
    lanes = [
        ReviewLaneConfig(
            key="domain_interest",
            label="Доменный интерес",
            priority=100,
            match_groups=[
                ReviewLaneMatchGroup(solution_area_types=["smart_home"]),
            ],
        ),
        ReviewLaneConfig(
            key="direct_pur_lead",
            label="Прямой лид",
            priority=200,
            match_groups=[
                ReviewLaneMatchGroup(solution_area_types=["smart_home"]),
                ReviewLaneMatchGroup(reason_keys=["provider_search", "installation_request"]),
            ],
        ),
    ]
    candidate = _candidate(
        solution_areas=[{"type": "smart_home"}],
        reasons=[{"key": "provider_search"}],
    )

    assignment = assign_review_lane(candidate, lanes)

    assert assignment.key == "direct_pur_lead"
    assert assignment.label == "Прямой лид"
    assert assignment.matched_group_indexes == [0, 1]


def test_review_lane_excludes_noise_even_when_positive_groups_match() -> None:
    lanes = [
        ReviewLaneConfig(
            key="direct_pur_lead",
            label="Прямой лид",
            priority=200,
            match_groups=[
                ReviewLaneMatchGroup(solution_area_types=["smart_home"]),
                ReviewLaneMatchGroup(reason_keys=["provider_search"]),
            ],
            excluded_noise_signal_types=["diy_or_equipment_only"],
        ),
    ]
    candidate = _candidate(
        solution_areas=[{"type": "smart_home"}],
        noise_signals=[{"type": "diy_or_equipment_only"}],
        reasons=[{"key": "provider_search"}],
    )

    assignment = assign_review_lane(candidate, lanes)

    assert assignment.key == "other_candidate"


def test_read_candidates_assigns_review_lane_from_config(tmp_path: Path) -> None:
    input_path = tmp_path / "lead-candidates.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "message_id": "672162",
                "text": "Посоветуйте контакты по Москве, подключить zigbee шлюз к Алисе",
                "domain_signals": [{"type": "protocol_gateway"}],
                "facts": [],
                "lead_assessment": {
                    "score": 120,
                    "temperature": "hot",
                    "solution_areas": [{"type": "smart_home"}],
                    "customer_segments": [{"type": "active_request"}],
                    "intent_signals": [],
                    "noise_signals": [],
                    "reasons": [{"key": "provider_search", "matched_texts": ["контакты"]}],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    lanes = [
        ReviewLaneConfig(
            key="direct_pur_lead",
            label="Прямой лид",
            priority=200,
            match_groups=[
                ReviewLaneMatchGroup(solution_area_types=["smart_home"]),
                ReviewLaneMatchGroup(reason_keys=["provider_search"]),
            ],
        )
    ]

    candidates = _read_candidates(input_path, review_lanes=lanes)

    assert candidates[0].review_lane == "direct_pur_lead"


def test_build_aggregates_counts_review_lanes_with_configured_labels() -> None:
    lanes = [
        ReviewLaneConfig(
            key="direct_pur_lead",
            label="Прямой лид",
            priority=200,
            description="Сначала смотреть руками",
            match_groups=[],
        )
    ]
    candidates = [
        _candidate(review_lane="direct_pur_lead"),
        _candidate(review_lane="direct_pur_lead"),
        _candidate(review_lane="domain_interest"),
    ]

    aggregates = _build_aggregates(candidates, review_lanes=lanes)

    lane_aggregates = [item for item in aggregates if item.kind == "review_lane"]
    assert lane_aggregates[0].key == "direct_pur_lead"
    assert lane_aggregates[0].label == "Прямой лид"
    assert lane_aggregates[0].count == 2
    assert lane_aggregates[0].payload["description"] == "Сначала смотреть руками"
    assert lane_aggregates[1].key == "domain_interest"
    assert lane_aggregates[1].label == "domain_interest"
    assert lane_aggregates[1].count == 1


def _candidate(
    *,
    review_lane: str = "other_candidate",
    solution_areas: list[dict[str, object]] | None = None,
    customer_segments: list[dict[str, object]] | None = None,
    intent_signals: list[dict[str, object]] | None = None,
    noise_signals: list[dict[str, object]] | None = None,
    reasons: list[dict[str, object]] | None = None,
    domain_signals: list[dict[str, object]] | None = None,
    facts: list[dict[str, object]] | None = None,
) -> AnalyticsCandidate:
    return AnalyticsCandidate(
        run_id=uuid4(),
        message_id=str(uuid4()),
        text="example",
        score=50,
        temperature="cold",
        review_lane=review_lane,
        solution_areas=solution_areas or [],
        customer_segments=customer_segments or [],
        intent_signals=intent_signals or [],
        noise_signals=noise_signals or [],
        reasons=reasons or [],
        domain_signals=domain_signals or [],
        facts=facts or [],
    )
