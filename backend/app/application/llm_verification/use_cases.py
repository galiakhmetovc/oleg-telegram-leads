from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.application.llm_verification.context import build_llm_context_pack
from app.application.llm_verification.routing import matched_llm_routes
from app.application.llm_verification.ports import ActiveNlpConfigReader
from app.application.llm_verification.ports import LlmTaskPublisher, LlmVerificationClient, LlmVerificationRepository
from app.domain.llm_settings import DEFAULT_LLM_SYSTEM_PROMPT, LlmSettings
from app.domain.llm_verification import LLM_VERIFICATION_SCHEMA_VERSION, LlmVerificationResponse
from app.domain.llm_verification import LlmVerificationRun, SourceMessageForLlmVerification

class SourceMessageForLlmVerificationNotFound(Exception):
    pass


class ActiveNlpConfigForLlmVerificationNotFound(Exception):
    pass


class VerifySourceMessageWithLlm:
    def __init__(
        self,
        *,
        repository: LlmVerificationRepository,
        nlp_config_repository: ActiveNlpConfigReader,
        client: LlmVerificationClient,
        model: str,
        system_prompt: str = DEFAULT_LLM_SYSTEM_PROMPT,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._nlp_config_repository = nlp_config_repository
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._now = now or (lambda: datetime.now(UTC))

    async def execute(self, source_message_id: UUID) -> LlmVerificationRun:
        source = await self._repository.get_source_message(source_message_id)
        if source is None:
            raise SourceMessageForLlmVerificationNotFound(str(source_message_id))

        active_revision = await self._nlp_config_repository.get_active()
        if active_revision is None:
            raise ActiveNlpConfigForLlmVerificationNotFound()

        context_pack = build_llm_context_pack(
            message_text=source.text,
            enrichment_result=source.enrichment_result,
            active_revision=active_revision,
        )

        created_at = self._now()
        try:
            response_payload, raw_response = await self._client.verify(
                model=self._model,
                context_pack=context_pack,
                system_prompt=self._system_prompt,
            )
            parsed = LlmVerificationResponse.model_validate(_normalize_response_payload(response_payload))
            parsed = _reconcile_response_with_context(parsed, context_pack)
            parsed = _ground_response_evidence(parsed, context_pack)
            run = LlmVerificationRun(
                id=uuid4(),
                source_message_id=source.source_message_id,
                enrichment_job_id=source.enrichment_job_id,
                model=self._model,
                schema_version=LLM_VERIFICATION_SCHEMA_VERSION,
                status="completed",
                context_pack=context_pack,
                response=parsed.model_dump(mode="json"),
                raw_response=raw_response,
                error=None,
                created_at=created_at,
                updated_at=created_at,
            )
        except Exception as exc:
            run = LlmVerificationRun(
                id=uuid4(),
                source_message_id=source.source_message_id,
                enrichment_job_id=source.enrichment_job_id,
                model=self._model,
                schema_version=LLM_VERIFICATION_SCHEMA_VERSION,
                status="failed",
                context_pack=context_pack,
                response=None,
                raw_response=raw_response if "raw_response" in locals() else None,
                error=_error_message(exc),
                created_at=created_at,
                updated_at=created_at,
            )
        return await self._repository.save_run(run)


class QueueSourceMessageForLlm:
    def __init__(
        self,
        *,
        repository: LlmVerificationRepository,
        nlp_config_repository: ActiveNlpConfigReader,
        settings: LlmSettings,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._nlp_config_repository = nlp_config_repository
        self._settings = settings
        self._now = now or (lambda: datetime.now(UTC))

    async def execute(self, source_message_id: UUID, *, route_id: str | None = None) -> LlmVerificationRun:
        source = await self._repository.get_source_message(source_message_id)
        if source is None:
            raise SourceMessageForLlmVerificationNotFound(str(source_message_id))
        context_pack = await _build_context_pack(
            source=source,
            nlp_config_repository=self._nlp_config_repository,
        )
        created_at = self._now()
        return await self._repository.save_run(
            _queued_run(
                source=source,
                settings=self._settings,
                context_pack=context_pack,
                route_id=route_id,
                created_at=created_at,
            )
        )


class QueueMatchedLlmVerifications:
    def __init__(
        self,
        *,
        repository: LlmVerificationRepository,
        nlp_config_repository: ActiveNlpConfigReader,
        task_publisher: LlmTaskPublisher,
        settings: LlmSettings,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._nlp_config_repository = nlp_config_repository
        self._task_publisher = task_publisher
        self._settings = settings
        self._now = now or (lambda: datetime.now(UTC))

    async def execute(self, source: SourceMessageForLlmVerification) -> list[LlmVerificationRun]:
        queued: list[LlmVerificationRun] = []
        for route in matched_llm_routes(self._settings, source):
            if await self._repository.route_run_exists(source_message_id=source.source_message_id, route_id=route.id):
                continue
            context_pack = await _build_context_pack(
                source=source,
                nlp_config_repository=self._nlp_config_repository,
            )
            run = await self._repository.save_run(
                _queued_run(
                    source=source,
                    settings=self._settings,
                    context_pack=context_pack,
                    route_id=route.id,
                    created_at=self._now(),
                )
            )
            await self._task_publisher.publish(run.id)
            queued.append(run)
        return queued


class ExecuteQueuedLlmVerification:
    def __init__(
        self,
        *,
        repository: LlmVerificationRepository,
        client: LlmVerificationClient,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._client = client
        self._now = now or (lambda: datetime.now(UTC))

    async def execute(self, run_id: UUID) -> LlmVerificationRun | None:
        run = await self._repository.claim_run(run_id)
        if run is None:
            return None
        raw_response: str | None = None
        try:
            response_payload, raw_response = await self._client.verify(
                model=run.model,
                context_pack=run.context_pack,
                system_prompt=run.prompt or DEFAULT_LLM_SYSTEM_PROMPT,
            )
            parsed = LlmVerificationResponse.model_validate(_normalize_response_payload(response_payload))
            parsed = _reconcile_response_with_context(parsed, run.context_pack)
            parsed = _ground_response_evidence(parsed, run.context_pack)
            return await self._repository.complete_run(
                run.id,
                response=parsed.model_dump(mode="json"),
                raw_response=raw_response,
                completed_at=self._now(),
            )
        except Exception as exc:
            return await self._repository.fail_run(
                run.id,
                error=_error_message(exc),
                raw_response=raw_response,
                failed_at=self._now(),
            )


class ListMessageLlmVerifications:
    def __init__(self, *, repository: LlmVerificationRepository) -> None:
        self._repository = repository

    async def execute(self, source_message_id: UUID) -> list[LlmVerificationRun]:
        return await self._repository.list_runs(source_message_id)


class ListLlmVerifications:
    def __init__(self, *, repository: LlmVerificationRepository) -> None:
        self._repository = repository

    async def execute(self, *, limit: int, offset: int) -> tuple[int, list[LlmVerificationRun]]:
        return await self._repository.list_all_runs(limit=limit, offset=offset)


async def _build_context_pack(
    *,
    source: SourceMessageForLlmVerification,
    nlp_config_repository: ActiveNlpConfigReader,
) -> dict[str, object]:
    active_revision = await nlp_config_repository.get_active()
    if active_revision is None:
        raise ActiveNlpConfigForLlmVerificationNotFound()
    return build_llm_context_pack(
        message_text=source.text,
        enrichment_result=source.enrichment_result,
        active_revision=active_revision,
    )


def _queued_run(
    *,
    source: SourceMessageForLlmVerification,
    settings: LlmSettings,
    context_pack: dict[str, object],
    route_id: str | None,
    created_at: datetime,
) -> LlmVerificationRun:
    return LlmVerificationRun(
        id=uuid4(),
        source_message_id=source.source_message_id,
        enrichment_job_id=source.enrichment_job_id,
        model=settings.model,
        route_id=route_id,
        prompt=settings.system_prompt,
        schema_version=LLM_VERIFICATION_SCHEMA_VERSION,
        status="queued",
        attempts=0,
        claimed_at=None,
        context_pack=context_pack,
        response=None,
        raw_response=None,
        error=None,
        created_at=created_at,
        updated_at=created_at,
    )


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return f"ValidationError: {exc}"
    return f"{type(exc).__name__}: {exc}"


def _normalize_response_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    confidence = normalized.get("confidence")
    if isinstance(confidence, int | float) and 1 < confidence <= 100:
        normalized["confidence"] = confidence / 100
    return normalized


def _reconcile_response_with_context(
    response: LlmVerificationResponse,
    context_pack: dict[str, object],
) -> LlmVerificationResponse:
    if response.agrees_with_rule_engine:
        return response.model_copy(
            update={
                "missing_fact_types": [],
                "suspicious_fact_types": [],
                "missing_signal_types": [],
            }
        )

    rule_result = context_pack.get("rule_engine_result")
    fact_labels = set(rule_result.get("fact_labels", [])) if isinstance(rule_result, dict) else set()
    return response.model_copy(
        update={
            "suspicious_fact_types": [
                label for label in response.suspicious_fact_types if label in fact_labels
            ],
        }
    )


def _ground_response_evidence(
    response: LlmVerificationResponse,
    context_pack: dict[str, object],
) -> LlmVerificationResponse:
    allowed_terms = _context_terms(context_pack)
    return response.model_copy(
        update={
            "matched_golden_ids": _grounded_golden_ids(response.matched_golden_ids, context_pack),
            "evidence": _grounded_items(response.evidence, allowed_terms),
            "anti_evidence": _grounded_items(response.anti_evidence, allowed_terms),
        }
    )


def _grounded_golden_ids(ids: list[str], context_pack: dict[str, object]) -> list[str]:
    allowed_ids: set[str] = set()
    examples = context_pack.get("golden_examples")
    if isinstance(examples, list):
        for item in examples:
            if isinstance(item, dict) and item.get("id") is not None:
                allowed_ids.add(str(item["id"]))
    return [item for item in ids if item in allowed_ids]


def _context_terms(context_pack: dict[str, object]) -> set[str]:
    terms: set[str] = set()
    message = context_pack.get("message")
    if isinstance(message, dict):
        terms.update(_terms(str(message.get("text") or "")))

    rule_result = context_pack.get("rule_engine_result")
    if isinstance(rule_result, dict):
        for fact in rule_result.get("facts", []):
            if isinstance(fact, dict):
                terms.update(_terms(str(fact.get("text") or "")))
        for signal in rule_result.get("signals", []):
            if isinstance(signal, dict):
                terms.update(_terms(str(signal.get("text") or "")))
        for reason in rule_result.get("reasons", []):
            if isinstance(reason, dict):
                for matched_text in reason.get("matched_texts", []):
                    terms.update(_terms(str(matched_text)))
    return terms


def _grounded_items(items: list[str], allowed_terms: set[str]) -> list[str]:
    return [
        item
        for item in items
        if _term_overlap(_terms(item), allowed_terms) > 0
    ]


def _terms(text: str) -> set[str]:
    return {
        value.casefold()
        for value in re.findall(r"[\wа-яА-ЯёЁ-]{4,}", text)
    }


def _term_overlap(left: set[str], right: set[str]) -> int:
    unmatched = set(right)
    count = 0
    for left_term in left:
        for right_term in list(unmatched):
            if _loosely_same_term(left_term, right_term):
                count += 1
                unmatched.remove(right_term)
                break
    return count


def _loosely_same_term(left: str, right: str) -> bool:
    if left == right:
        return True
    prefix_len = min(len(left), len(right), 8)
    return prefix_len >= 4 and left[:prefix_len] == right[:prefix_len]
