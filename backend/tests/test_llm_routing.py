from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.llm_verification.routing import matched_llm_routes
from app.application.llm_verification.use_cases import QueueMatchedLlmVerifications
from app.domain.enrichment import DomainSignal, LeadCategory, TextEnrichmentResult, TextRange
from app.domain.llm_settings import LlmRoute, LlmRouteConditions, LlmSettings
from app.domain.llm_verification import SourceMessageForLlmVerification
from app.domain.settings import NlpConfigRevision


def test_llm_route_matches_chat_score_and_excludes_operator_noise() -> None:
    source_chat_id = uuid4()
    settings = LlmSettings(
        enabled=True,
        model="lead-qwen-ru",
        endpoint="http://host.docker.internal:11434/api/chat",
        timeout_seconds=240,
        system_prompt="Return JSON",
        routes=[
            LlmRoute(
                id="designers_non_noise",
                name="Дизайнерские чаты без шума",
                enabled=True,
                priority=100,
                match_mode="all",
                conditions=LlmRouteConditions(
                    source_chat_ids=[str(source_chat_id)],
                    score_min=20,
                    review_lanes=["direct_pur_lead"],
                    include_signal_types=["pur_smart_home"],
                    exclude_signal_types=["operator_noise"],
                    exclude_fact_types=["operator_noise_fact"],
                ),
            )
        ],
        updated_at=None,
    )

    clean_source = _source(source_chat_id=source_chat_id, noise=False)
    noisy_source = _source(source_chat_id=source_chat_id, noise=True)

    assert [route.id for route in matched_llm_routes(settings, clean_source)] == ["designers_non_noise"]
    assert matched_llm_routes(settings, noisy_source) == []


@pytest.mark.asyncio
async def test_queue_matched_llm_verifications_publishes_only_matching_routes() -> None:
    source_chat_id = uuid4()
    settings = LlmSettings(
        enabled=True,
        model="lead-qwen-ru",
        endpoint="http://host.docker.internal:11434/api/chat",
        timeout_seconds=240,
        system_prompt="Return JSON",
        routes=[
            LlmRoute(
                id="designers_non_noise",
                name="Дизайнерские чаты без шума",
                enabled=True,
                priority=100,
                match_mode="all",
                conditions=LlmRouteConditions(
                    source_chat_ids=[str(source_chat_id)],
                    include_signal_types=["pur_smart_home"],
                    exclude_signal_types=["operator_noise"],
                ),
            )
        ],
        updated_at=None,
    )
    repository = InMemoryLlmVerificationRepository()
    publisher = RecordingPublisher()

    queued = await QueueMatchedLlmVerifications(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(),
        task_publisher=publisher,
        settings=settings,
    ).execute(_source(source_chat_id=source_chat_id, noise=False))
    skipped = await QueueMatchedLlmVerifications(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(),
        task_publisher=publisher,
        settings=settings,
    ).execute(_source(source_chat_id=source_chat_id, noise=True))

    assert [run.route_id for run in queued] == ["designers_non_noise"]
    assert skipped == []
    assert publisher.published == [queued[0].id]


def _source(*, source_chat_id: object, noise: bool) -> SourceMessageForLlmVerification:
    facts = []
    domain_signals = [
        DomainSignal(
            id="signal-1",
            text="умный дом",
            type="pur_smart_home",
            label="Умный дом",
            range=TextRange(0, 9),
            source="rule",
        )
    ]
    noise_signals = []
    if noise:
        facts.append(
            {
                "id": "fact-1",
                "text": "операторский шум",
                "type": "operator_noise_fact",
                "label": "Факт: операторский шум",
                "range": {"start": 0, "stop": 16},
                "source": "exact_phrase",
            }
        )
        noise_signals = [LeadCategory(type="operator_noise", label="Операторский шум", matched_types=["operator_noise_fact"])]
    return SourceMessageForLlmVerification(
        source_message_id=uuid4(),
        source_chat_id=source_chat_id,
        source_chat_title="Дизайнеры",
        telegram_message_id=101,
        text="Нужен умный дом",
        enrichment_job_id=uuid4(),
        enrichment_result=TextEnrichmentResult.from_dict(
            {
                "original_text": "Нужен умный дом",
                "normalized_text": "нужен умный дом",
                "sentences": [],
                "tokens": [],
                "entities": [],
                "facts": facts,
                "domain_signals": [signal.__dict__ | {"range": {"start": signal.range.start, "stop": signal.range.stop}} for signal in domain_signals],
                "syntax": [],
                "metrics": {
                    "character_count": 15,
                    "sentence_count": 1,
                    "token_count": 3,
                    "entity_count": 0,
                    "fact_count": len(facts),
                    "domain_signal_count": len(domain_signals),
                },
                "pipeline_trace": [],
                "lead_assessment": {
                    "is_lead": True,
                    "score": 80,
                    "temperature": "hot",
                    "solution_areas": [{"type": "smart_home", "label": "Умный дом", "matched_types": ["pur_smart_home"]}],
                    "customer_segments": [],
                    "intent_signals": [],
                    "noise_signals": [item.__dict__ for item in noise_signals],
                    "reasons": [
                        {
                            "source": "domain_signal",
                            "key": "pur_smart_home",
                            "label": "Умный дом",
                            "weight": 30,
                            "matched_texts": ["умный дом"],
                        }
                    ],
                    "review_lane": {
                        "key": "direct_pur_lead",
                        "label": "Прямой лид",
                        "description": None,
                        "matched_group_indexes": [0],
                    },
                },
            }
        ),
    )


class InMemoryLlmVerificationRepository:
    def __init__(self) -> None:
        self.saved = []

    async def save_run(self, run):
        self.saved.append(run)
        return run

    async def route_run_exists(self, *, source_message_id, route_id: str) -> bool:
        return any(run.source_message_id == source_message_id and run.route_id == route_id for run in self.saved)


class InMemoryNlpConfigRepository:
    async def get_active(self):
        return NlpConfigRevision(
            id=uuid4(),
            revision=1,
            documents={
                "facts": {"facts": []},
                "signals": {"signals": []},
                "catalogs": {"vendors": [], "protocols": [], "devices": [], "software": []},
                "lead_scoring": {},
                "pipeline": {"stages": []},
            },
            source="test",
            created_at=None,
        )


class RecordingPublisher:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, run_id) -> None:
        self.published.append(run_id)
