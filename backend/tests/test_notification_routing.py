from __future__ import annotations

from app.application.notifications.routing import NotificationMessageContext
from app.application.notifications.routing import match_notification_routes, render_notification_message
from app.domain.enrichment import LeadAssessment, LeadCategory, LeadReason, LeadReviewLane
from app.domain.enrichment import EnrichmentMetrics, TextEnrichmentResult
from app.domain.notifications import NotificationRoute, NotificationRouteConditions


def test_matches_notification_routes_from_enrichment_result() -> None:
    result = _result(
        assessment=LeadAssessment(
            is_lead=True,
            score=95,
            temperature="hot",
            solution_areas=[LeadCategory(type="smart_home", label="Умный дом", matched_types=[])],
            customer_segments=[
                LeadCategory(type="active_request", label="Активный запрос", matched_types=[])
            ],
            intent_signals=[],
            noise_signals=[],
            reasons=[
                LeadReason(
                    source="signal",
                    key="provider_search",
                    label="Поиск подрядчика",
                    weight=12,
                    matched_texts=["посоветуйте контакты"],
                )
            ],
            review_lane=LeadReviewLane(
                key="direct_pur_lead",
                label="Прямой лид",
                description=None,
                matched_group_indexes=[0],
            ),
        )
    )
    routes = [
        NotificationRoute(
            id="hot",
            name="Горячие лиды",
            enabled=True,
            priority=100,
            bot_id="main_bot",
            chat_id="sales_chat",
            match_mode="all",
            conditions=NotificationRouteConditions(
                is_lead=True,
                score_min=80,
                review_lanes=["direct_pur_lead"],
                solution_areas=["smart_home"],
            ),
            message_template="",
        ),
        NotificationRoute(
            id="noise",
            name="Шум",
            enabled=True,
            priority=200,
            bot_id="main_bot",
            chat_id="noise_chat",
            match_mode="all",
            conditions=NotificationRouteConditions(noise_signals=["diy"]),
            message_template="",
        ),
    ]

    matched = match_notification_routes(routes, result)

    assert [route.id for route in matched] == ["hot"]


def test_renders_notification_message_template_from_enrichment_result() -> None:
    result = _result(
        assessment=LeadAssessment(
            is_lead=True,
            score=95,
            temperature="hot",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            review_lane=LeadReviewLane(
                key="direct_pur_lead",
                label="Прямой лид",
                description=None,
                matched_group_indexes=[0],
            ),
        )
    )

    message = render_notification_message(
        "Температура {temperature}, score {score}, lane {review_lane}: {text}",
        result,
    )

    assert message == "Температура hot, score 95, lane direct_pur_lead: Нужен умный дом"


def test_renders_notification_message_links_from_context_even_for_old_templates() -> None:
    result = _result(
        assessment=LeadAssessment(
            is_lead=True,
            score=95,
            temperature="hot",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            review_lane=None,
        )
    )

    message = render_notification_message(
        "Лид {score}: {text}",
        result,
        NotificationMessageContext(
            telegram_message_url="https://t.me/channel/10",
            app_message_url="https://example.test/#/analytics/message/abc",
        ),
    )

    assert "Лид 95: Нужен умный дом" in message
    assert "Ссылки:" in message
    assert "Telegram: https://t.me/channel/10" in message
    assert "Аналитика: https://example.test/#/analytics/message/abc" in message


def _result(*, assessment: LeadAssessment | None) -> TextEnrichmentResult:
    return TextEnrichmentResult(
        original_text="Нужен умный дом",
        normalized_text="нужен умный дом",
        sentences=[],
        tokens=[],
        entities=[],
        facts=[],
        domain_signals=[],
        syntax=[],
        metrics=EnrichmentMetrics(
            character_count=15,
            sentence_count=1,
            token_count=3,
            entity_count=0,
            fact_count=0,
            domain_signal_count=0,
        ),
        pipeline_trace=[],
        lead_assessment=assessment,
    )
