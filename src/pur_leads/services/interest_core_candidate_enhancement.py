"""LLM-assisted review of rule-based interest-core candidates."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.services.interest_context_drafts import InterestContextDraftService
from pur_leads.services.interest_core_briefs import (
    InterestCoreBriefService,
    parse_interest_core_brief_response,
)

ENHANCE_INTEREST_CORE_CANDIDATES_JOB = "enhance_interest_core_candidates"
INTEREST_CORE_CANDIDATE_ENHANCEMENT_PROMPT_VERSION = "interest-core-candidate-enhancement-v1"
DEFAULT_ENHANCEMENT_CANDIDATE_LIMIT = 80
DEFAULT_ENHANCEMENT_CHUNK_SIZE = 10

ProgressCallback = Callable[[dict[str, Any]], None]


class InterestCoreCandidateEnhancementService:
    """Use the active brief to improve deterministic interest-core candidates."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def enhance_async(
        self,
        context_id: str,
        *,
        client: AiChatClient,
        actor: str,
        provider: str,
        model: str,
        model_profile: str | None = None,
        max_items: int = DEFAULT_ENHANCEMENT_CANDIDATE_LIMIT,
        candidate_chunk_size: int = DEFAULT_ENHANCEMENT_CHUNK_SIZE,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        ai_provider_account_id: str | None = None,
        ai_model_id: str | None = None,
        ai_model_profile_id: str | None = None,
        ai_agent_route_id: str | None = None,
        progress: ProgressCallback | None = None,
        resume_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.build_payload(context_id, max_items=max_items)
        chunk_size = max(
            1,
            min(50, int(candidate_chunk_size or DEFAULT_ENHANCEMENT_CHUNK_SIZE)),
        )
        chunks = _chunks(
            payload["candidates"],
            size=chunk_size,
        )
        resume = _resume_state(resume_state, chunk_count=len(chunks))
        parsed = resume["partial_result"]
        chunk_results = resume["chunk_results"]
        request_ids = resume["request_ids"]
        usage_by_chunk = resume["usage_by_chunk"]
        completed_chunk_count = int(resume["completed_chunk_count"])

        for chunk_index, candidates in enumerate(chunks, start=1):
            if chunk_index <= completed_chunk_count:
                continue
            chunk_payload = {
                **payload,
                "candidates": candidates,
                "chunk": {
                    "index": chunk_index,
                    "count": len(chunks),
                    "candidate_count": len(candidates),
                    "candidate_offset": (chunk_index - 1) * len(candidates),
                },
                "canonical_registry": _canonical_registry(parsed),
            }
            _report(
                progress,
                status="running",
                current_stage="llm_enhancement",
                current_stage_label=f"LLM-фрагмент {chunk_index}/{len(chunks)}",
                overall_percent=_progress_percent(chunk_index - 1, len(chunks)),
                stage_percent=0,
                message=f"Улучшаю кандидатов {chunk_index}/{len(chunks)} через {model}",
                context_id=context_id,
                candidate_count=len(payload["candidates"]),
                processed_candidate_count=(chunk_index - 1) * chunk_size,
                chunk_index=chunk_index,
                chunk_count=len(chunks),
                chunk_size=len(candidates),
                completed_chunk_count=completed_chunk_count,
                improved_count=len(parsed["improved_candidates"]),
                new_count=len(parsed["new_candidates"]),
                rejected_count=len(parsed["rejected_candidates"]),
                partial_result=parsed,
                chunk_results=chunk_results,
                usage_by_chunk=usage_by_chunk,
                request_ids=request_ids,
                model=model,
                model_profile=model_profile,
            )
            prompt_text = render_interest_core_candidate_enhancement_prompt(chunk_payload)
            messages = [
                AiChatMessage(
                    role="system",
                    content=(
                        "Ты улучшаешь проверяемое ядро интересов. "
                        "Отвечай только валидным JSON без markdown."
                    ),
                ),
                AiChatMessage(role="user", content=prompt_text),
            ]
            completion = await client.complete(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            chunk_parsed = normalize_candidate_enhancement_response(
                parse_interest_core_brief_response(completion.content)
            )
            _merge_enhancement_result(parsed, chunk_parsed)
            if completion.request_id:
                request_ids.append(completion.request_id)
            usage_by_chunk.append(
                {
                    "chunk_index": chunk_index,
                    "usage": completion.usage,
                    "request_id": completion.request_id,
                }
            )
            chunk_results.append(
                {
                    "chunk_index": chunk_index,
                    "candidate_count": len(candidates),
                    "improved_count": len(chunk_parsed["improved_candidates"]),
                    "new_count": len(chunk_parsed["new_candidates"]),
                    "rejected_count": len(chunk_parsed["rejected_candidates"]),
                    "summary": chunk_parsed.get("summary"),
                }
            )
            completed_chunk_count = chunk_index
            _report(
                progress,
                status="running",
                current_stage="llm_enhancement",
                current_stage_label=f"LLM-фрагмент {chunk_index}/{len(chunks)}",
                overall_percent=_progress_percent(chunk_index, len(chunks)),
                stage_percent=100,
                message=f"Готов фрагмент {chunk_index}/{len(chunks)}",
                context_id=context_id,
                candidate_count=len(payload["candidates"]),
                processed_candidate_count=min(
                    len(payload["candidates"]), chunk_index * chunk_size
                ),
                chunk_index=chunk_index,
                chunk_count=len(chunks),
                chunk_size=len(candidates),
                completed_chunk_count=completed_chunk_count,
                improved_count=len(parsed["improved_candidates"]),
                new_count=len(parsed["new_candidates"]),
                rejected_count=len(parsed["rejected_candidates"]),
                partial_result=parsed,
                chunk_results=chunk_results,
                usage_by_chunk=usage_by_chunk,
                request_ids=request_ids,
                model=model,
                model_profile=model_profile,
            )

        parsed["summary"] = _combined_summary(parsed, chunk_results)
        return {
            "kind": "interest_core_candidate_enhancement",
            "status": "succeeded",
            "current_stage": "done",
            "current_stage_label": "Готово",
            "overall_percent": 100,
            "stage_percent": 100,
            "message": _summary_message(parsed),
            "context_id": context_id,
            "brief_id": payload["brief"]["id"],
            "brief_version": payload["brief"]["version"],
            "draft_run_id": payload["draft_run"]["id"],
            "candidate_count": len(payload["candidates"]),
            "candidate_chunk_size": chunk_size,
            "chunk_count": len(chunks),
            "improved_count": len(parsed["improved_candidates"]),
            "new_count": len(parsed["new_candidates"]),
            "rejected_count": len(parsed["rejected_candidates"]),
            "prompt_version": INTEREST_CORE_CANDIDATE_ENHANCEMENT_PROMPT_VERSION,
            "provider": provider,
            "model": model,
            "model_profile": model_profile,
            "ai_provider_account_id": ai_provider_account_id,
            "ai_model_id": ai_model_id,
            "ai_model_profile_id": ai_model_profile_id,
            "ai_agent_route_id": ai_agent_route_id,
            "requested_by": actor,
            "result": parsed,
            "chunk_results": chunk_results,
            "usage_by_chunk": usage_by_chunk,
            "request_ids": request_ids,
        }

    def build_payload(self, context_id: str, *, max_items: int) -> dict[str, Any]:
        brief = InterestCoreBriefService(self.session).active_brief(context_id)
        if brief is None:
            raise ValueError("Сначала создайте или сформируйте активный LLM-бриф ядра")

        draft_payload = InterestContextDraftService(self.session).latest_payload(
            context_id,
            limit=max(1, max_items),
        )
        draft_run = draft_payload.get("draft_run")
        if not draft_run:
            raise ValueError("Сначала сформируйте rule-based ядро интересов")
        if str(draft_run.get("status") or "") != "succeeded":
            raise ValueError("Последняя сборка rule-based ядра еще не завершилась успешно")

        candidates = [
            _candidate_prompt_row(item)
            for item in (draft_payload.get("items") or [])[: max(1, max_items)]
        ]
        if not candidates:
            raise ValueError("В rule-based ядре нет кандидатов для LLM-улучшения")

        return {
            "brief": {
                "id": brief.id,
                "version": brief.version,
                "title": brief.title,
                "brief_text": brief.brief_text,
                "brief_json": brief.brief_json,
            },
            "draft_run": {
                "id": draft_run["id"],
                "algorithm_version": draft_run.get("algorithm_version"),
                "summary": draft_run.get("output_summary_json"),
            },
            "candidates": candidates,
        }


def render_interest_core_candidate_enhancement_prompt(payload: dict[str, Any]) -> str:
    return (
        "Улучши список кандидатов ядра интересов.\n"
        "На входе есть активный бизнес-бриф и rule-based кандидаты из NLP/POS/ranking. "
        "Твоя задача: нормализовать названия, объединить дубли, отсеять шум, добавить "
        "важные кандидаты, если они явно следуют из брифа и evidence.\n\n"
        "Правила:\n"
        "- не применяй изменения сам, только верни рекомендации;\n"
        "- сейчас обрабатывается один фрагмент кандидатов, не весь список сразу;\n"
        "- canonical_registry содержит уже выбранные имена из прошлых фрагментов: "
        "используй их, чтобы не плодить дубли;\n"
        "- если два кандидата означают одно и то же, укажи decision=merge "
        "и merge_into_candidate_id;\n"
        "- не придумывай факты без evidence;\n"
        "- lead_signals должны описывать, какие сообщения считать потенциальным интересом/лидом;\n"
        "- noise_patterns должны описывать похожий, но нерелевантный шум;\n"
        "- canonical_name должен быть коротким и стабильным, чтобы следующий кандидат "
        "не получил дубль.\n\n"
        "Верни строго JSON-объект со схемой:\n"
        "{\n"
        '  "summary": string,\n'
        '  "improved_candidates": [\n'
        "    {\n"
        '      "source_candidate_id": string,\n'
        '      "canonical_name": string,\n'
        '      "category": string,\n'
        '      "decision": "keep|merge|reject|needs_review",\n'
        '      "merge_into_candidate_id": string|null,\n'
        '      "confidence": "low|medium|high",\n'
        '      "description": string,\n'
        '      "synonyms": string[],\n'
        '      "lead_signals": string[],\n'
        '      "noise_patterns": string[],\n'
        '      "evidence_refs": string[],\n'
        '      "rationale": string\n'
        "    }\n"
        "  ],\n"
        '  "new_candidates": [\n'
        "    {\n"
        '      "canonical_name": string,\n'
        '      "category": string,\n'
        '      "confidence": "low|medium|high",\n'
        '      "description": string,\n'
        '      "synonyms": string[],\n'
        '      "lead_signals": string[],\n'
        '      "noise_patterns": string[],\n'
        '      "evidence_refs": string[],\n'
        '      "rationale": string\n'
        "    }\n"
        "  ],\n"
        '  "rejected_candidates": [{"source_candidate_id": string, "reason": string}]\n'
        "}\n\n"
        "ДАННЫЕ:\n"
        f"{json.dumps(_prompt_payload(payload), ensure_ascii=False, indent=2)}"
    )


def normalize_candidate_enhancement_response(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": _string(value.get("summary"))[:2000],
        "improved_candidates": [
            _normalize_improved(item)
            for item in _object_list(value.get("improved_candidates"))[:300]
        ],
        "new_candidates": [
            _normalize_new(item) for item in _object_list(value.get("new_candidates"))[:100]
        ],
        "rejected_candidates": [
            {
                "source_candidate_id": _string(item.get("source_candidate_id"))[:80],
                "reason": _string(item.get("reason"))[:1000],
            }
            for item in _object_list(value.get("rejected_candidates"))[:300]
        ],
    }


def _candidate_prompt_row(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata_json") if isinstance(item.get("metadata_json"), dict) else {}
    evidence = item.get("evidence_json") if isinstance(item.get("evidence_json"), list) else []
    return {
        "id": item.get("id"),
        "item_type": item.get("item_type"),
        "title": item.get("title"),
        "normalized_key": item.get("normalized_key"),
        "description": item.get("description"),
        "score": item.get("score"),
        "confidence": item.get("confidence"),
        "status": item.get("status"),
        "mention_count": metadata.get("mention_count"),
        "reasons": _string_list(metadata.get("reasons"))[:8],
        "penalties": _string_list(metadata.get("penalties"))[:8],
        "pos_patterns": _string_list(metadata.get("pos_patterns"))[:8],
        "evidence": [
            {
                "source_ref": _string(row.get("source_ref"))[:500],
                "example": _string(row.get("example"))[:700],
            }
            for row in evidence[:4]
            if isinstance(row, dict)
        ],
    }


def _prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    brief = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    return {
        "brief": {
            "id": brief.get("id"),
            "version": brief.get("version"),
            "title": brief.get("title"),
            "brief_text": brief.get("brief_text"),
            "brief_json": brief.get("brief_json"),
        },
        "draft_run": payload.get("draft_run"),
        "chunk": payload.get("chunk"),
        "canonical_registry": payload.get("canonical_registry", []),
        "candidates": payload.get("candidates", []),
    }


def _normalize_improved(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_candidate_id": _string(item.get("source_candidate_id"))[:80],
        "canonical_name": _string(item.get("canonical_name"))[:300],
        "category": _string(item.get("category"))[:160],
        "decision": _enum(
            item.get("decision"),
            {"keep", "merge", "reject", "needs_review"},
            "needs_review",
        ),
        "merge_into_candidate_id": _nullable_string(item.get("merge_into_candidate_id"), 80),
        "confidence": _enum(item.get("confidence"), {"low", "medium", "high"}, "medium"),
        "description": _string(item.get("description"))[:1200],
        "synonyms": _string_list(item.get("synonyms"))[:20],
        "lead_signals": _string_list(item.get("lead_signals"))[:20],
        "noise_patterns": _string_list(item.get("noise_patterns"))[:20],
        "evidence_refs": _string_list(item.get("evidence_refs"))[:20],
        "rationale": _string(item.get("rationale"))[:1200],
    }


def _normalize_new(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_name": _string(item.get("canonical_name"))[:300],
        "category": _string(item.get("category"))[:160],
        "confidence": _enum(item.get("confidence"), {"low", "medium", "high"}, "medium"),
        "description": _string(item.get("description"))[:1200],
        "synonyms": _string_list(item.get("synonyms"))[:20],
        "lead_signals": _string_list(item.get("lead_signals"))[:20],
        "noise_patterns": _string_list(item.get("noise_patterns"))[:20],
        "evidence_refs": _string_list(item.get("evidence_refs"))[:20],
        "rationale": _string(item.get("rationale"))[:1200],
    }


def _summary_message(parsed: dict[str, Any]) -> str:
    return (
        f"LLM-рекомендации готовы: {len(parsed['improved_candidates'])} улучшено, "
        f"{len(parsed['new_candidates'])} добавлено, "
        f"{len(parsed['rejected_candidates'])} отклонено"
    )


def _report(progress: ProgressCallback | None, **payload: Any) -> None:
    if progress is not None:
        progress({"kind": "interest_core_candidate_enhancement", **payload})


def _progress_percent(done: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, round(done * 100 / total)))


def _chunks(items: list[dict[str, Any]], *, size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _empty_enhancement_result() -> dict[str, Any]:
    return {
        "summary": "",
        "improved_candidates": [],
        "new_candidates": [],
        "rejected_candidates": [],
    }


def _resume_state(value: dict[str, Any] | None, *, chunk_count: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "completed_chunk_count": 0,
            "partial_result": _empty_enhancement_result(),
            "chunk_results": [],
            "usage_by_chunk": [],
            "request_ids": [],
        }
    if value.get("kind") != "interest_core_candidate_enhancement":
        return {
            "completed_chunk_count": 0,
            "partial_result": _empty_enhancement_result(),
            "chunk_results": [],
            "usage_by_chunk": [],
            "request_ids": [],
        }
    completed = _positive_int(value.get("completed_chunk_count"), default=0)
    completed = max(0, min(completed, chunk_count))
    partial = value.get("partial_result")
    if not isinstance(partial, dict):
        partial = value.get("result")
    parsed = (
        normalize_candidate_enhancement_response(partial)
        if isinstance(partial, dict)
        else _empty_enhancement_result()
    )
    return {
        "completed_chunk_count": completed,
        "partial_result": parsed,
        "chunk_results": _object_list(value.get("chunk_results"))[:chunk_count],
        "usage_by_chunk": _object_list(value.get("usage_by_chunk"))[:chunk_count],
        "request_ids": _string_list(value.get("request_ids"))[:chunk_count],
    }


def _merge_enhancement_result(target: dict[str, Any], chunk: dict[str, Any]) -> None:
    target["improved_candidates"].extend(chunk.get("improved_candidates") or [])
    target["new_candidates"].extend(chunk.get("new_candidates") or [])
    target["rejected_candidates"].extend(chunk.get("rejected_candidates") or [])


def _canonical_registry(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    for item in parsed.get("improved_candidates") or []:
        name = _string(item.get("canonical_name"))
        if not name:
            continue
        registry.append(
            {
                "canonical_name": name,
                "source_candidate_id": item.get("source_candidate_id"),
                "category": item.get("category"),
                "decision": item.get("decision"),
                "synonyms": item.get("synonyms") or [],
            }
        )
    for item in parsed.get("new_candidates") or []:
        name = _string(item.get("canonical_name"))
        if not name:
            continue
        registry.append(
            {
                "canonical_name": name,
                "source_candidate_id": None,
                "category": item.get("category"),
                "decision": "new",
                "synonyms": item.get("synonyms") or [],
            }
        )
    return _dedupe_registry(registry)[-120:]


def _dedupe_registry(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _string(item.get("canonical_name")).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _combined_summary(parsed: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
    return (
        f"Обработано {len(chunks)} фрагментов. "
        f"Улучшено: {len(parsed['improved_candidates'])}; "
        f"новых: {len(parsed['new_candidates'])}; "
        f"к отклонению: {len(parsed['rejected_candidates'])}."
    )


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _nullable_string(value: Any, limit: int) -> str | None:
    text = _string(value)
    return text[:limit] if text else None


def _enum(value: Any, allowed: set[str], default: str) -> str:
    text = _string(value).casefold()
    return text if text in allowed else default


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
