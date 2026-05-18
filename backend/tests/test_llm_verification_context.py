from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.llm_verification.context import build_llm_context_pack
from app.domain.enrichment import DomainSignal, EnrichmentMetrics, ExtractedFact
from app.domain.enrichment import LeadAssessment, LeadCategory, LeadReason, TextEnrichmentResult
from app.domain.enrichment import TextRange
from app.domain.llm_verification import LlmVerificationResponse
from app.domain.settings import NlpConfigRevision


def test_builds_compact_context_pack_for_model_analysis() -> None:
    result = _enrichment_result()
    revision = _active_revision()

    pack = build_llm_context_pack(
        message_text="Подскажите, где заказать видеонаблюдение для квартиры",
        enrichment_result=result,
        active_revision=revision,
    )

    assert "schema_version" not in pack
    assert "config_revision" not in pack
    assert "config_revision_id" not in pack
    assert "golden_examples" not in pack
    assert pack["message"] == {"text": "Подскажите, где заказать видеонаблюдение для квартиры"}
    assert pack["rule_engine_result"]["verdict"] == "lead"
    assert pack["rule_engine_result"]["score"] == 78
    assert pack["rule_engine_result"]["temperature"] == "hot"
    assert pack["rule_engine_result"]["fact_labels"] == ["Поиск исполнителя / контактов", "Видеонаблюдение"]
    assert pack["rule_engine_result"]["signal_labels"] == ["Активное намерение", "Видеонаблюдение"]
    assert pack["rule_engine_result"]["reason_labels"] == ["Активное намерение"]
    assert pack["rule_engine_result"]["solution_area_labels"] == ["Видеонаблюдение"]
    assert pack["rule_engine_result"]["customer_segment_labels"] == []
    assert pack["rule_engine_result"]["intent_signal_labels"] == []
    assert pack["rule_engine_result"]["noise_signal_labels"] == []
    assert "facts" not in pack["rule_engine_result"]
    assert "signals" not in pack["rule_engine_result"]
    assert "reasons" not in pack["rule_engine_result"]
    assert "review_lane" not in pack["rule_engine_result"]
    assert pack["available_taxonomy"] == {
        "signal_labels": "Активное намерение; Видеонаблюдение",
        "fact_rule_labels": "Поиск исполнителя / контактов; Видеонаблюдение",
        "dictionary_labels": "Устройства: Камера",
    }
    assert "aliases" not in str(pack["available_taxonomy"])
    assert "canonical" not in str(pack["available_taxonomy"])
    assert "fact_types" not in pack["available_taxonomy"]
    assert "catalogs" not in pack["available_taxonomy"]
    assert "devices:camera" not in str(pack["available_taxonomy"])


def test_llm_verification_response_rejects_unknown_recommendation() -> None:
    with pytest.raises(ValidationError):
        LlmVerificationResponse.model_validate(
            {
                "verdict": "lead",
                "confidence": 0.8,
                "recommendation": "accept",
                "agrees_with_rule_engine": True,
                "matched_golden_ids": [],
                "missing_fact_types": [],
                "suspicious_fact_types": [],
                "missing_signal_types": [],
                "evidence": [],
                "anti_evidence": [],
            }
        )


def test_llm_verification_response_requires_all_structured_fields() -> None:
    with pytest.raises(ValidationError):
        LlmVerificationResponse.model_validate(
            {
                "verdict": "lead",
                "confidence": 0.8,
                "recommendation": "keep",
                "agrees_with_rule_engine": True,
            }
        )


def test_context_pack_does_not_send_golden_examples_to_model() -> None:
    text = "В поисках двух человек для раскопки водопровода за смену"

    pack = build_llm_context_pack(
        message_text=text,
        enrichment_result=_empty_enrichment_result(text),
        active_revision=_active_revision(),
    )

    assert "golden_examples" not in pack


def _active_revision() -> NlpConfigRevision:
    return NlpConfigRevision(
        id=uuid4(),
        revision=55,
        documents={
            "facts": {
                "facts": [
                    {
                        "type": "intent_provider_search",
                        "label": "Поиск исполнителя / контактов",
                        "group": "V3: намерение",
                    },
                    {
                        "type": "domain_video_surveillance",
                        "label": "Видеонаблюдение",
                        "group": "V3: домен",
                    },
                ]
            },
            "signals": {
                "signals": [
                    {
                        "type": "lead_active_intent",
                        "label": "Активное намерение",
                        "group": "V3: намерение",
                    },
                    {
                        "type": "pur_video_surveillance",
                        "label": "Видеонаблюдение",
                        "group": "V3: целевой домен",
                    },
                ]
            },
            "vendors": {"vendors": []},
            "protocols": {"protocols": []},
            "devices": {
                "devices": [
                    {
                        "key": "camera",
                        "canonical": "Камера",
                        "type": "device",
                        "aliases": ["камера", "камеры"],
                        "fact_types": ["domain_video_surveillance"],
                    }
                ]
            },
            "software": {"software": []},
        },
        source="ui",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )


def _enrichment_result() -> TextEnrichmentResult:
    return TextEnrichmentResult(
        original_text="Подскажите, где заказать видеонаблюдение для квартиры",
        normalized_text="подскажите где заказать видеонаблюдение для квартиры",
        sentences=[],
        tokens=[],
        entities=[],
        facts=[
            ExtractedFact(
                id="fact_1",
                text="где заказать",
                type="intent_provider_search",
                label="Поиск исполнителя / контактов",
                range=TextRange(start=13, stop=25),
                source="exact_phrase",
            ),
            ExtractedFact(
                id="fact_2",
                text="видеонаблюдение",
                type="domain_video_surveillance",
                label="Видеонаблюдение",
                range=TextRange(start=26, stop=41),
                source="exact_phrase",
            ),
        ],
        domain_signals=[
            DomainSignal(
                id="signal_1",
                text="где заказать",
                type="lead_active_intent",
                label="Активное намерение",
                range=TextRange(start=13, stop=25),
                source="facts",
                source_fact_ids=["fact_1"],
            ),
            DomainSignal(
                id="signal_2",
                text="видеонаблюдение",
                type="pur_video_surveillance",
                label="Видеонаблюдение",
                range=TextRange(start=26, stop=41),
                source="facts",
                source_fact_ids=["fact_2"],
            ),
        ],
        syntax=[],
        metrics=EnrichmentMetrics(
            character_count=55,
            sentence_count=1,
            token_count=6,
            entity_count=0,
            fact_count=2,
            domain_signal_count=2,
        ),
        pipeline_trace=[],
        lead_assessment=LeadAssessment(
            is_lead=True,
            score=78,
            temperature="hot",
            solution_areas=[
                LeadCategory(
                    type="video_surveillance",
                    label="Видеонаблюдение",
                    matched_types=["pur_video_surveillance"],
                )
            ],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[
                LeadReason(
                    source="signal",
                    key="lead_active_intent",
                    label="Активное намерение",
                    weight=40,
                    matched_texts=["где заказать"],
                )
            ],
        ),
    )


def _empty_enrichment_result(text: str) -> TextEnrichmentResult:
    return TextEnrichmentResult(
        original_text=text,
        normalized_text=text.casefold(),
        sentences=[],
        tokens=[],
        entities=[],
        facts=[],
        domain_signals=[],
        syntax=[],
        metrics=EnrichmentMetrics(
            character_count=len(text),
            sentence_count=1,
            token_count=0,
            entity_count=0,
            fact_count=0,
            domain_signal_count=0,
        ),
        pipeline_trace=[],
        lead_assessment=LeadAssessment(
            is_lead=False,
            score=0,
            temperature="none",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
        ),
    )
