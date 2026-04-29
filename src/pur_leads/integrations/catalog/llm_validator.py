"""LLM-backed catalog candidate quality validator."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.workers.runtime import CatalogCandidateValidationResult

PROMPT_VERSION = "catalog-candidate-validation-v1"
VALIDATOR_VERSION = "pur-llm-catalog-validator-v1"

DECISIONS = {"confirm", "revise", "reject", "merge", "needs_human"}


class LlmCatalogCandidateValidator:
    prompt_version = PROMPT_VERSION
    validator_version = VALIDATOR_VERSION

    def __init__(
        self,
        *,
        client: AiChatClient,
        model: str,
        session: Session,
        model_profile: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        validator_provider: str | None = None,
        provider_account_id: str | None = None,
        model_id: str | None = None,
        model_profile_id: str | None = None,
        agent_route_id: str | None = None,
        route_role: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.model_profile = model_profile
        self.session = session
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.validator_provider = validator_provider
        self.provider_account_id = provider_account_id
        self.model_id = model_id
        self.model_profile_id = model_profile_id
        self.agent_route_id = agent_route_id
        self.route_role = route_role
        self.last_token_usage_json: dict[str, Any] | None = None

    async def validate_catalog_candidate(
        self,
        *,
        candidate_id: str,
        payload: dict[str, Any],
    ) -> CatalogCandidateValidationResult:
        self.last_token_usage_json = None
        service = CatalogCandidateService(self.session)
        detail = service.get_candidate_detail(candidate_id)
        prompt_payload = _candidate_prompt_payload(
            detail.candidate,
            detail.evidence,
            extra_context=payload.get("extra_context"),
        )
        completion = await self.client.complete(
            messages=_prompt_messages(prompt_payload),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        self.last_token_usage_json = {
            **completion.usage,
            "request_id": completion.request_id,
            "model": completion.model,
        }
        parsed = _parse_json_object(completion.content)
        return _result_from_payload(parsed)


def _candidate_prompt_payload(candidate, evidence: list[dict[str, Any]], *, extra_context: Any):
    return {
        "candidate": {
            "id": candidate.id,
            "candidate_type": candidate.candidate_type,
            "proposed_action": candidate.proposed_action,
            "canonical_name": candidate.canonical_name,
            "normalized_value": candidate.normalized_value_json,
            "confidence": candidate.confidence,
            "status": candidate.status,
            "source_count": candidate.source_count,
            "evidence_count": candidate.evidence_count,
        },
        "evidence": [_evidence_prompt_item(row) for row in evidence[:8]],
        "extra_context": extra_context if isinstance(extra_context, dict | list) else None,
    }


def _evidence_prompt_item(row: dict[str, Any]) -> dict[str, Any]:
    chunk_text = row.get("chunk_text")
    source_text = row.get("source_raw_text")
    text = chunk_text if isinstance(chunk_text, str) and chunk_text.strip() else source_text
    return {
        "quote": row.get("quote"),
        "source_type": row.get("source_type"),
        "source_origin": row.get("source_origin"),
        "source_external_id": row.get("source_external_id"),
        "source_url": row.get("source_url"),
        "artifact_file_name": row.get("artifact_file_name"),
        "chunk_index": row.get("chunk_index"),
        "text": text[:5000] if isinstance(text, str) else None,
    }


def _prompt_messages(payload: dict[str, Any]) -> list[AiChatMessage]:
    system = (
        "Return strict JSON only. You validate one PUR catalog candidate against source evidence. "
        "Do not invent facts. Decide whether the candidate should be confirmed, revised, "
        "rejected, merged with another known entity, or sent to a human. "
        'Use this schema: {"decision":"confirm|revise|reject|merge|needs_human",'
        '"confidence":0.0,"reason":"...","proposed_changes":{},'
        '"evidence_quotes":["..."]}. '
        "Keep reason concise and operator-readable."
    )
    user = "Candidate review input:\n" + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )
    return [AiChatMessage(role="system", content=system), AiChatMessage(role="user", content=user)]


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM catalog validator expected valid JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("LLM catalog validator expected valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM catalog validator expected valid JSON object")
    return parsed


def _result_from_payload(payload: dict[str, Any]) -> CatalogCandidateValidationResult:
    decision = str(payload.get("decision") or "").strip().casefold()
    if decision not in DECISIONS:
        raise ValueError("LLM catalog validator returned unsupported decision")
    return CatalogCandidateValidationResult(
        decision=decision,
        confidence=_confidence(payload.get("confidence")),
        reason=_optional_string(payload.get("reason")),
        proposed_changes_json=payload.get("proposed_changes")
        if isinstance(payload.get("proposed_changes"), dict)
        else {},
        evidence_json={"quotes": _string_list(payload.get("evidence_quotes"))},
        raw_output_json=payload,
    )


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(1.0, parsed))


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
