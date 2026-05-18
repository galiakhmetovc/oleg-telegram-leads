from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.llm_verifications import get_llm_task_publisher
from app.api.llm_verifications import get_llm_client
from app.api.llm_verifications import get_llm_verification_config
from app.api.llm_verifications import get_llm_verification_model, get_llm_verification_repository
from app.api.llm_verifications import get_llm_settings_repository, get_nlp_config_repository
from app.domain.enrichment import EnrichmentMetrics, LeadAssessment, TextEnrichmentResult
from app.domain.llm_settings import default_llm_settings
from app.domain.llm_verification import LlmVerificationRun, SourceMessageForLlmVerification
from app.domain.settings import NlpConfigRevision
from app.main import create_app


def test_runs_and_lists_llm_verification_for_source_message() -> None:
    source = _source_message()
    repository = InMemoryLlmVerificationRepository(source)
    publisher = RecordingLlmTaskPublisher()
    app = create_app()
    app.dependency_overrides[get_llm_verification_repository] = lambda: repository
    app.dependency_overrides[get_nlp_config_repository] = lambda: InMemoryNlpConfigRepository(_revision())
    app.dependency_overrides[get_llm_client] = lambda: RecordingLlmClient()
    app.dependency_overrides[get_llm_verification_model] = lambda: "lead-qwen-ru"
    app.dependency_overrides[get_llm_task_publisher] = lambda: publisher
    app.dependency_overrides[get_llm_settings_repository] = lambda: InMemoryLlmSettingsRepository()
    client = TestClient(app)

    response = client.post(f"/api/v1/llm-verifications/messages/{source.source_message_id}")

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["model"] == "lead-qwen-ru"
    assert payload["response"] is None
    assert publisher.published == [UUID(payload["id"])]

    list_response = client.get(f"/api/v1/llm-verifications/messages/{source.source_message_id}")

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["id"] == payload["id"]


def test_returns_404_for_missing_source_message() -> None:
    app = create_app()
    app.dependency_overrides[get_llm_verification_repository] = lambda: InMemoryLlmVerificationRepository(None)
    app.dependency_overrides[get_nlp_config_repository] = lambda: InMemoryNlpConfigRepository(_revision())
    app.dependency_overrides[get_llm_client] = lambda: RecordingLlmClient()
    app.dependency_overrides[get_llm_verification_model] = lambda: "lead-qwen-ru"
    app.dependency_overrides[get_llm_settings_repository] = lambda: InMemoryLlmSettingsRepository()
    app.dependency_overrides[get_llm_task_publisher] = lambda: RecordingLlmTaskPublisher()
    client = TestClient(app)

    response = client.post(f"/api/v1/llm-verifications/messages/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "source message not found"


def test_returns_llm_verification_runtime_config() -> None:
    app = create_app()
    app.dependency_overrides[get_llm_verification_config] = lambda: {
        "model": "lead-qwen-ru",
        "endpoint": "http://host.docker.internal:11434/api/chat",
        "timeout_seconds": 240.0,
        "execution_mode": "backend_inline",
    }
    client = TestClient(app)

    response = client.get("/api/v1/llm-verifications/config")

    assert response.status_code == 200
    assert response.json() == {
        "model": "lead-qwen-ru",
        "endpoint": "http://host.docker.internal:11434/api/chat",
        "timeout_seconds": 240.0,
        "execution_mode": "backend_inline",
    }


class InMemoryLlmVerificationRepository:
    def __init__(self, source: SourceMessageForLlmVerification | None) -> None:
        self.source = source
        self.saved: list[LlmVerificationRun] = []

    async def get_source_message(self, source_message_id: UUID) -> SourceMessageForLlmVerification | None:
        if self.source and self.source.source_message_id == source_message_id:
            return self.source
        return None

    async def save_run(self, run: LlmVerificationRun) -> LlmVerificationRun:
        self.saved.append(run)
        return run

    async def list_runs(self, source_message_id: UUID) -> list[LlmVerificationRun]:
        return [item for item in self.saved if item.source_message_id == source_message_id]


class InMemoryNlpConfigRepository:
    def __init__(self, revision: NlpConfigRevision | None) -> None:
        self.revision = revision

    async def get_active(self) -> NlpConfigRevision | None:
        return self.revision


class InMemoryLlmSettingsRepository:
    async def get_settings(self):
        return default_llm_settings(
            model="lead-qwen-ru",
            endpoint="http://host.docker.internal:11434/api/chat",
            timeout_seconds=240,
        )


class RecordingLlmClient:
    async def verify(
        self,
        *,
        model: str,
        context_pack: dict[str, object],
        system_prompt: str,
    ) -> tuple[dict[str, object], str]:
        return (
            {
                "verdict": "lead",
                "confidence": 0.88,
                "recommendation": "keep",
                "agrees_with_rule_engine": True,
                "matched_golden_ids": [],
                "missing_fact_types": [],
                "suspicious_fact_types": [],
                "missing_signal_types": [],
                "evidence": ["нужен подрядчик"],
                "anti_evidence": [],
            },
            "{}",
        )


class RecordingLlmTaskPublisher:
    def __init__(self) -> None:
        self.published: list[UUID] = []

    async def publish(self, run_id: UUID) -> None:
        self.published.append(run_id)


def _source_message() -> SourceMessageForLlmVerification:
    return SourceMessageForLlmVerification(
        source_message_id=uuid4(),
        source_chat_id=uuid4(),
        source_chat_title="Чат дизайнеров",
        telegram_message_id=10,
        text="Нужен подрядчик на умный дом",
        enrichment_job_id=uuid4(),
        enrichment_result=TextEnrichmentResult(
            original_text="Нужен подрядчик на умный дом",
            normalized_text="нужен подрядчик на умный дом",
            sentences=[],
            tokens=[],
            entities=[],
            facts=[],
            domain_signals=[],
            syntax=[],
            metrics=EnrichmentMetrics(
                character_count=28,
                sentence_count=1,
                token_count=5,
                entity_count=0,
                fact_count=0,
                domain_signal_count=0,
            ),
            pipeline_trace=[],
            lead_assessment=LeadAssessment(
                is_lead=True,
                score=80,
                temperature="hot",
                solution_areas=[],
                customer_segments=[],
                intent_signals=[],
                noise_signals=[],
                reasons=[],
            ),
        ),
    )


def _revision() -> NlpConfigRevision:
    return NlpConfigRevision(
        id=uuid4(),
        revision=55,
        documents={
            "facts": {"facts": []},
            "signals": {"signals": []},
            "vendors": {"vendors": []},
            "protocols": {"protocols": []},
            "devices": {"devices": []},
            "software": {"software": []},
        },
        source="ui",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )
