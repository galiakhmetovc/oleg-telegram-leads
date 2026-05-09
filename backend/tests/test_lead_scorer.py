from app.application.review_lanes import ReviewLaneConfig, ReviewLaneMatchGroup
from app.domain.enrichment import DomainSignal, ExtractedFact, TextRange
from app.infrastructure.nlp.config_loader import LeadScoreCapConfig, LeadScoringConfig
from app.infrastructure.nlp.lead_scorer import LeadScorer


def test_scores_hot_pur_lead_from_intent_and_solution_evidence() -> None:
    scorer = LeadScorer(
        LeadScoringConfig(
            lead_threshold=35,
            warm_threshold=55,
            hot_threshold=80,
            signal_weights={
                "provider_search": 25,
                "installation_request": 25,
                "smart_home_automation": 30,
                "hot_lead_intent": 25,
            },
            fact_weights={"service_location": 5},
            solution_areas={
                "smart_home": {
                    "label": "Умный дом / автоматизация",
                    "signal_types": ["smart_home_automation"],
                    "fact_types": [],
                }
            },
            customer_segments={
                "moscow_private_client": {
                    "label": "Частный клиент в Москве",
                    "signal_types": ["provider_search"],
                    "fact_types": ["service_location"],
                }
            },
            intent_signal_types=["provider_search", "installation_request", "hot_lead_intent"],
            noise_signal_types=[],
        )
    )

    assessment = scorer.assess(
        signals=[
            _signal("provider_search", "Посоветуйте контакты"),
            _signal("installation_request", "Установить и подключить"),
            _signal("smart_home_automation", "zigbee шлюз"),
            _signal("hot_lead_intent", "запрос от клиента"),
        ],
        facts=[_fact("service_location", "Москве")],
    )

    assert assessment.is_lead is True
    assert assessment.temperature == "hot"
    assert assessment.score == 110
    assert [item.type for item in assessment.solution_areas] == ["smart_home"]
    assert [item.type for item in assessment.customer_segments] == ["moscow_private_client"]
    assert {item.type for item in assessment.intent_signals} == {
        "provider_search",
        "installation_request",
        "hot_lead_intent",
    }
    assert assessment.noise_signals == []
    assert any(reason.key == "smart_home_automation" and reason.weight == 30 for reason in assessment.reasons)


def test_noise_can_keep_weak_domain_match_below_lead_threshold() -> None:
    scorer = LeadScorer(
        LeadScoringConfig(
            lead_threshold=35,
            warm_threshold=55,
            hot_threshold=80,
            signal_weights={"video_surveillance": 25, "diy_only": -20},
            fact_weights={},
            solution_areas={
                "security": {
                    "label": "Безопасность",
                    "signal_types": ["video_surveillance"],
                    "fact_types": [],
                }
            },
            customer_segments={},
            intent_signal_types=[],
            noise_signal_types=["diy_only"],
        )
    )

    assessment = scorer.assess(
        signals=[
            _signal("video_surveillance", "камера"),
            _signal("diy_only", "сам поставлю"),
        ],
        facts=[],
    )

    assert assessment.is_lead is False
    assert assessment.temperature == "none"
    assert assessment.score == 5
    assert [item.type for item in assessment.noise_signals] == ["diy_only"]
    assert any(reason.key == "diy_only" and reason.weight == -20 for reason in assessment.reasons)


def test_hard_noise_signal_vetoes_positive_domain_score() -> None:
    scorer = LeadScorer(
        LeadScoringConfig(
            lead_threshold=35,
            warm_threshold=55,
            hot_threshold=80,
            signal_weights={
                "video_surveillance": 35,
                "smart_home_platform": 25,
                "diy_or_equipment_only": -10,
            },
            fact_weights={},
            solution_areas={
                "security": {
                    "label": "Безопасность",
                    "signal_types": ["video_surveillance", "smart_home_platform"],
                    "fact_types": [],
                }
            },
            customer_segments={},
            intent_signal_types=[],
            noise_signal_types=["diy_or_equipment_only"],
        )
    )

    assessment = scorer.assess(
        signals=[
            _signal("video_surveillance", "камера Hikvision"),
            _signal("smart_home_platform", "Hikvision"),
            _signal("diy_or_equipment_only", "самовывоз"),
        ],
        facts=[],
    )

    assert assessment.score == 50
    assert assessment.is_lead is False
    assert assessment.temperature == "none"
    assert [item.type for item in assessment.noise_signals] == ["diy_or_equipment_only"]


def test_score_cap_limits_overheated_noise_score() -> None:
    scorer = LeadScorer(
        LeadScoringConfig(
            lead_threshold=35,
            warm_threshold=55,
            hot_threshold=80,
            signal_weights={
                "video_surveillance": 35,
                "access_control": 35,
                "diy_or_equipment_only": -10,
            },
            fact_weights={"automation_component": 12},
            solution_areas={},
            customer_segments={},
            intent_signal_types=[],
            noise_signal_types=["diy_or_equipment_only"],
            lead_veto_signal_types=["diy_or_equipment_only"],
            score_caps=[
                LeadScoreCapConfig(
                    key="hard_noise",
                    label="Явный шум",
                    max_score=0,
                    signal_types=["diy_or_equipment_only"],
                )
            ],
        )
    )

    assessment = scorer.assess(
        signals=[
            _signal("video_surveillance", "камера Dahua"),
            _signal("access_control", "Dahua"),
            _signal("diy_or_equipment_only", "без монтажа"),
        ],
        facts=[_fact("automation_component", "камера")],
    )

    assert assessment.score == 0
    assert assessment.is_lead is False
    assert assessment.temperature == "none"
    assert any(
        reason.source == "score_cap"
        and reason.key == "hard_noise"
        and reason.weight == -72
        and reason.matched_texts == ["без монтажа"]
        for reason in assessment.reasons
    )


def test_score_cap_can_be_skipped_by_excluded_signal_type() -> None:
    scorer = LeadScorer(
        LeadScoringConfig(
            lead_threshold=35,
            warm_threshold=60,
            hot_threshold=90,
            signal_weights={"video_surveillance": 40, "provider_search": 12},
            fact_weights={},
            solution_areas={},
            customer_segments={},
            intent_signal_types=["provider_search"],
            noise_signal_types=[],
            score_caps=[
                LeadScoreCapConfig(
                    key="domain_without_intent",
                    label="Домен без намерения",
                    max_score=34,
                    signal_types=["video_surveillance"],
                    excluded_signal_types=["provider_search"],
                )
            ],
        ),
        signal_labels={
            "video_surveillance": "Видеонаблюдение",
            "provider_search": "Поиск исполнителя",
        },
    )

    capped = scorer.assess(signals=[_signal("video_surveillance", "камера")], facts=[])
    with_intent = scorer.assess(
        signals=[
            _signal("video_surveillance", "камера"),
            _signal("provider_search", "где заказать"),
        ],
        facts=[],
    )

    assert capped.score == 34
    assert capped.is_lead is False
    assert any(reason.source == "score_cap" and reason.key == "domain_without_intent" for reason in capped.reasons)
    assert with_intent.score == 52
    assert with_intent.is_lead is True
    assert all(reason.key != "domain_without_intent" for reason in with_intent.reasons)


def test_uses_human_labels_and_assigns_review_lane() -> None:
    scorer = LeadScorer(
        LeadScoringConfig(
            lead_threshold=35,
            warm_threshold=60,
            hot_threshold=90,
            signal_weights={"provider_search": 12, "smart_home_automation": 35},
            fact_weights={"automation_component": 12},
            solution_areas={
                "smart_home": {
                    "label": "Умный дом / автоматизация",
                    "signal_types": ["smart_home_automation"],
                    "fact_types": ["automation_component"],
                }
            },
            customer_segments={
                "active_request": {
                    "label": "Активный запрос",
                    "signal_types": ["provider_search"],
                    "fact_types": [],
                }
            },
            intent_signal_types=["provider_search"],
            noise_signal_types=[],
            review_lanes=[
                ReviewLaneConfig(
                    key="direct_pur_lead",
                    label="Прямой лид ПУР",
                    description="Есть домен и активное намерение",
                    priority=900,
                    match_groups=[
                        ReviewLaneMatchGroup(signal_types=["smart_home_automation"]),
                        ReviewLaneMatchGroup(customer_segment_types=["active_request"]),
                    ],
                )
            ],
        ),
        signal_labels={
            "provider_search": "Поиск исполнителя / контактов",
            "smart_home_automation": "Умный дом / автоматизация",
        },
        fact_labels={"automation_component": "Компонент автоматизации"},
    )

    assessment = scorer.assess(
        signals=[
            _signal("provider_search", "Посоветуйте контакты"),
            _signal("smart_home_automation", "zigbee шлюз"),
        ],
        facts=[_fact("automation_component", "zigbee шлюз")],
    )

    reason_labels = {reason.key: reason.label for reason in assessment.reasons}
    assert reason_labels["provider_search"] == "Поиск исполнителя / контактов"
    assert reason_labels["automation_component"] == "Компонент автоматизации"
    assert assessment.review_lane is not None
    assert assessment.review_lane.key == "direct_pur_lead"
    assert assessment.review_lane.label == "Прямой лид ПУР"
    assert assessment.review_lane.matched_group_indexes == [0, 1]


def _signal(signal_type: str, text: str) -> DomainSignal:
    return DomainSignal(
        id=f"signal-{signal_type}",
        text=text,
        type=signal_type,
        label=signal_type,
        range=TextRange(start=0, stop=len(text)),
        source="test",
    )


def _fact(fact_type: str, text: str) -> ExtractedFact:
    return ExtractedFact(
        id=f"fact-{fact_type}",
        text=text,
        type=fact_type,
        label=fact_type,
        range=TextRange(start=0, stop=len(text)),
        source="test",
    )
