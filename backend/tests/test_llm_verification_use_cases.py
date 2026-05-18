from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.llm_verification.use_cases import ListMessageLlmVerifications
from app.application.llm_verification.use_cases import VerifySourceMessageWithLlm
from app.domain.enrichment import EnrichmentMetrics, LeadAssessment, TextEnrichmentResult
from app.domain.llm_verification import LlmVerificationRun, SourceMessageForLlmVerification
from app.domain.settings import NlpConfigRevision


@pytest.mark.asyncio
async def test_verify_source_message_stores_completed_response() -> None:
    repository = InMemoryLlmVerificationRepository(_source_message())
    client = RecordingLlmClient(
        response={
            "verdict": "lead",
            "confidence": 0.91,
            "recommendation": "keep",
            "agrees_with_rule_engine": True,
            "matched_golden_ids": [],
            "missing_fact_types": [],
            "suspicious_fact_types": [],
            "missing_signal_types": [],
            "evidence": ["нужен подрядчик"],
            "anti_evidence": [],
        }
    )

    run = await VerifySourceMessageWithLlm(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(_revision()),
        client=client,
        model="lead-qwen-ru",
    ).execute(repository.source.source_message_id)

    assert run.status == "completed"
    assert run.response is not None
    assert run.response["recommendation"] == "keep"
    assert run.error is None
    assert repository.saved == [run]
    assert client.requests[0]["context_pack"]["message"]["text"] == "Нужен подрядчик на умный дом"
    assert "source_message_id" not in client.requests[0]["context_pack"]["message"]
    assert "golden_examples" not in client.requests[0]["context_pack"]


@pytest.mark.asyncio
async def test_verify_source_message_stores_failed_run_when_model_returns_invalid_json() -> None:
    repository = InMemoryLlmVerificationRepository(_source_message())
    client = RecordingLlmClient(response={"verdict": "lead", "confidence": 2, "recommendation": "keep"})

    run = await VerifySourceMessageWithLlm(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(_revision()),
        client=client,
        model="lead-qwen-ru",
    ).execute(repository.source.source_message_id)

    assert run.status == "failed"
    assert run.response is None
    assert "ValidationError" in (run.error or "")
    assert repository.saved == [run]


@pytest.mark.asyncio
async def test_verify_source_message_normalizes_percent_confidence() -> None:
    repository = InMemoryLlmVerificationRepository(_source_message())
    client = RecordingLlmClient(
        response={
            "verdict": "lead",
            "confidence": 35,
            "recommendation": "manual_review",
            "agrees_with_rule_engine": True,
            "matched_golden_ids": [],
            "missing_fact_types": [],
            "suspicious_fact_types": [],
            "missing_signal_types": [],
            "evidence": ["нужен подрядчик"],
            "anti_evidence": [],
        }
    )

    run = await VerifySourceMessageWithLlm(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(_revision()),
        client=client,
        model="lead-qwen-ru",
    ).execute(repository.source.source_message_id)

    assert run.status == "completed"
    assert run.response is not None
    assert run.response["confidence"] == 0.35


@pytest.mark.asyncio
async def test_verify_source_message_clears_diagnostics_when_model_agrees_with_rules() -> None:
    repository = InMemoryLlmVerificationRepository(_source_message())
    client = RecordingLlmClient(
        response={
            "verdict": "lead",
            "confidence": 0.92,
            "recommendation": "keep",
            "agrees_with_rule_engine": True,
            "matched_golden_ids": [],
            "missing_fact_types": ["Домен: умный дом"],
            "suspicious_fact_types": ["Сигнал: частное жилье"],
            "missing_signal_types": ["Умный дом"],
            "evidence": ["нужен подрядчик"],
            "anti_evidence": [],
        }
    )

    run = await VerifySourceMessageWithLlm(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(_revision()),
        client=client,
        model="lead-qwen-ru",
    ).execute(repository.source.source_message_id)

    assert run.response is not None
    assert run.response["missing_fact_types"] == []
    assert run.response["suspicious_fact_types"] == []
    assert run.response["missing_signal_types"] == []


@pytest.mark.asyncio
async def test_verify_source_message_filters_evidence_not_grounded_in_source_message() -> None:
    repository = InMemoryLlmVerificationRepository(_source_message())
    client = RecordingLlmClient(
        response={
            "verdict": "not_lead",
            "confidence": 0.91,
            "recommendation": "keep",
            "agrees_with_rule_engine": True,
            "matched_golden_ids": [],
            "missing_fact_types": [],
            "suspicious_fact_types": [],
            "missing_signal_types": [],
            "evidence": [
                "no_lead",
                "The text discusses fire exit compliance",
                "умный дом указан в сообщении",
            ],
            "anti_evidence": [
                "no_suspicious",
                "сообщение запрашивает подрядчика",
            ],
        }
    )

    run = await VerifySourceMessageWithLlm(
        repository=repository,
        nlp_config_repository=InMemoryNlpConfigRepository(_revision()),
        client=client,
        model="lead-qwen-ru",
    ).execute(repository.source.source_message_id)

    assert run.status == "completed"
    assert run.response is not None
    assert run.response["evidence"] == ["умный дом указан в сообщении"]
    assert run.response["anti_evidence"] == ["сообщение запрашивает подрядчика"]


@pytest.mark.asyncio
async def test_verify_source_message_drops_matched_golden_ids_because_golden_is_not_sent_to_model() -> None:
    source = _source_message()
    golden_id = uuid4()
    client = RecordingLlmClient(
        response={
            "verdict": "lead",
            "confidence": 0.91,
            "recommendation": "keep",
            "agrees_with_rule_engine": True,
            "matched_golden_ids": [str(golden_id), "fact-2", str(uuid4())],
            "missing_fact_types": [],
            "suspicious_fact_types": [],
            "missing_signal_types": [],
            "evidence": ["нужен подрядчик"],
            "anti_evidence": [],
        }
    )

    run = await VerifySourceMessageWithLlm(
        repository=InMemoryLlmVerificationRepository(source),
        nlp_config_repository=InMemoryNlpConfigRepository(_revision()),
        client=client,
        model="lead-qwen-ru",
    ).execute(source.source_message_id)

    assert run.response is not None
    assert run.response["matched_golden_ids"] == []


@pytest.mark.asyncio
async def test_list_message_llm_verifications_returns_saved_runs() -> None:
    source = _source_message()
    repository = InMemoryLlmVerificationRepository(source)
    expected = _run(source.source_message_id)
    repository.saved = [expected]

    runs = await ListMessageLlmVerifications(repository=repository).execute(source.source_message_id)

    assert runs == [expected]


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
        return [run for run in self.saved if run.source_message_id == source_message_id]


class InMemoryNlpConfigRepository:
    def __init__(self, revision: NlpConfigRevision | None) -> None:
        self.revision = revision

    async def get_active(self) -> NlpConfigRevision | None:
        return self.revision


class RecordingLlmClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    async def verify(
        self,
        *,
        model: str,
        context_pack: dict[str, object],
        system_prompt: str,
    ) -> tuple[dict[str, object], str]:
        self.requests.append({"model": model, "context_pack": context_pack})
        return self.response, "raw response"


def _source_message() -> SourceMessageForLlmVerification:
    source_message_id = uuid4()
    enrichment_job_id = uuid4()
    return SourceMessageForLlmVerification(
        source_message_id=source_message_id,
        source_chat_id=uuid4(),
        source_chat_title="Чат дизайнеров",
        telegram_message_id=10,
        text="Нужен подрядчик на умный дом",
        enrichment_job_id=enrichment_job_id,
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


def _run(source_message_id: UUID) -> LlmVerificationRun:
    now = datetime(2026, 5, 13, tzinfo=UTC)
    return LlmVerificationRun(
        id=uuid4(),
        source_message_id=source_message_id,
        enrichment_job_id=uuid4(),
        model="lead-qwen-ru",
        schema_version="llm_verification.v1",
        status="completed",
        context_pack={},
        response={"verdict": "lead"},
        raw_response="{}",
        error=None,
        created_at=now,
        updated_at=now,
    )
