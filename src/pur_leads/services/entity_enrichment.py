"""Canonical entity enrichment over ranked Telegram entities."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import asyncio
import json
from pathlib import Path
import re
from typing import Any, Protocol

import pyarrow.parquet as pq
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.models.entity_enrichment import (
    canonical_entities_table,
    canonical_entity_aliases_table,
    canonical_merge_candidates_table,
    entity_enrichment_results_table,
    entity_enrichment_runs_table,
)
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

PROMPT_VERSION = "entity-enrichment-v1"
SERVICE_VERSION = "entity-enrichment-resolver-v1"
DEFAULT_INCLUDE_STATUSES = ("promote_candidate", "review_candidate")
MAX_CONTEXT_ENTITIES = 20
WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё-]+")


@dataclass(frozen=True)
class EntityEnrichmentDecision:
    action: str
    canonical_name: str | None = None
    canonical_entity_id: str | None = None
    entity_type: str = "unknown"
    confidence: float | None = None
    reason: str | None = None
    metadata: dict[str, Any] | None = None
    raw_response_json: dict[str, Any] | None = None

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "canonical_name": self.canonical_name,
            "canonical_entity_id": self.canonical_entity_id,
            "entity_type": self.entity_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "metadata": self.metadata or {},
        }


@dataclass(frozen=True)
class EntityEnrichmentRequest:
    ranked_entity: dict[str, Any]
    context_snapshot: dict[str, Any]
    prompt_text: str
    provider: str | None
    model: str | None
    model_profile: str | None
    prompt_version: str

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "model_profile": self.model_profile,
            "prompt_version": self.prompt_version,
            "ranked_entity": self.ranked_entity,
            "context_snapshot": self.context_snapshot,
            "messages": [
                {
                    "role": "system",
                    "content": "Return strict JSON according to the prompt schema.",
                },
                {"role": "user", "content": self.prompt_text},
            ],
        }


class EntityEnricher(Protocol):
    def enrich(self, request: EntityEnrichmentRequest) -> EntityEnrichmentDecision:
        """Return one structured enrichment decision."""


@dataclass(frozen=True)
class EntityEnrichmentRunResult:
    run_id: str
    raw_export_run_id: str
    ranked_entities_path: Path
    metrics: dict[str, Any]


class RuleBasedEntityEnricher:
    """Deterministic fallback that uses the same request/decision contract as an LLM."""

    def enrich(self, request: EntityEnrichmentRequest) -> EntityEnrichmentDecision:
        ranked = request.ranked_entity
        normalized_text = str(ranked.get("normalized_text") or "")
        known = request.context_snapshot.get("known_canonical_entities")
        if isinstance(known, list):
            for entity in known:
                if not isinstance(entity, dict):
                    continue
                if _matches_known_entity(normalized_text, entity):
                    return EntityEnrichmentDecision(
                        action="attach_to_existing",
                        canonical_entity_id=str(entity["id"]),
                        canonical_name=str(entity["canonical_name"]),
                        entity_type=str(entity["entity_type"]),
                        confidence=0.82,
                        reason="Matched existing canonical entity from registry context.",
                    )

        score = float(ranked.get("score") or 0)
        if str(ranked.get("ranking_status")) == "noise" or score < 0.35:
            return EntityEnrichmentDecision(
                action="reject_noise",
                canonical_name=normalized_text,
                entity_type="unknown",
                confidence=0.75,
                reason="Ranked entity is below enrichment threshold.",
            )

        return EntityEnrichmentDecision(
            action="propose_new",
            canonical_name=_canonicalize_label(str(ranked.get("canonical_text") or normalized_text)),
            entity_type="unknown",
            confidence=min(0.95, max(0.5, score)),
            reason="No matching canonical entity was present in the registry context.",
        )


class LlmEntityEnricher:
    """Synchronous adapter around the async chat-completion client."""

    def __init__(
        self,
        *,
        client: AiChatClient,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def enrich(self, request: EntityEnrichmentRequest) -> EntityEnrichmentDecision:
        completion = asyncio.run(
            self.client.complete(
                messages=[
                    AiChatMessage(
                        role="system",
                        content="Return strict JSON only. Do not add markdown fences.",
                    ),
                    AiChatMessage(role="user", content=request.prompt_text),
                ],
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        )
        parsed = _parse_json_object(completion.content)
        return EntityEnrichmentDecision(
            action=str(parsed.get("action") or "needs_review"),
            canonical_name=_optional_string(parsed.get("canonical_name")),
            canonical_entity_id=_optional_string(parsed.get("canonical_entity_id")),
            entity_type=_optional_string(parsed.get("entity_type")) or "unknown",
            confidence=_optional_float(parsed.get("confidence")),
            reason=_optional_string(parsed.get("reason")),
            metadata={"llm_parsed_output": parsed, "usage": completion.usage},
            raw_response_json={
                "content": completion.content,
                "model": completion.model,
                "request_id": completion.request_id,
                "usage": completion.usage,
                "raw_response": completion.raw_response,
            },
        )


class EntityEnrichmentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def write_enrichment(
        self,
        raw_export_run_id: str,
        *,
        client: EntityEnricher | None = None,
        limit: int = 50,
        include_statuses: tuple[str, ...] = DEFAULT_INCLUDE_STATUSES,
        provider: str | None = None,
        model: str | None = None,
        model_profile: str | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> EntityEnrichmentRunResult:
        run = self._require_run(raw_export_run_id)
        ranked_entities_path = _ranked_path_from_metadata(run)
        ranked_rows = pq.read_table(ranked_entities_path).to_pylist()
        selected_rows = _select_rows(ranked_rows, include_statuses=include_statuses, limit=limit)
        enricher = client or RuleBasedEntityEnricher()
        now = utc_now()
        enrichment_run_id = new_id()
        context_snapshot_id = f"{raw_export_run_id}:{int(now.timestamp())}"
        self.session.execute(
            insert(entity_enrichment_runs_table).values(
                id=enrichment_run_id,
                raw_export_run_id=raw_export_run_id,
                ranked_entities_path=str(ranked_entities_path),
                context_snapshot_id=context_snapshot_id,
                provider=provider,
                model=model,
                model_profile=model_profile,
                prompt_version=prompt_version,
                status="running",
                metrics_json={},
                error=None,
                started_at=now,
                finished_at=None,
                created_at=now,
            )
        )
        self.session.flush()

        counters: Counter[str] = Counter()
        try:
            for index, ranked_entity in enumerate(selected_rows):
                request = self._build_request(
                    ranked_entity,
                    provider=provider,
                    model=model,
                    model_profile=model_profile,
                    prompt_version=prompt_version,
                )
                decision = enricher.enrich(request)
                resolved = self._apply_decision(
                    enrichment_run_id=enrichment_run_id,
                    sequence_index=index,
                    ranked_entity=ranked_entity,
                    request=request,
                    decision=decision,
                )
                counters["processed_entities"] += 1
                counters[resolved["status"]] += 1
                if resolved["merge_review_created"]:
                    counters["merge_review_candidates"] += 1

            metrics = {
                "selected_entities": len(selected_rows),
                "processed_entities": counters["processed_entities"],
                "created_canonical": counters["created_canonical"],
                "attached_to_existing": counters["attached_to_existing"],
                "rejected_noise": counters["rejected_noise"],
                "needs_review": counters["needs_review"],
                "needs_merge_review": counters["needs_merge_review"],
                "merge_review_candidates": counters["merge_review_candidates"],
                "service_version": SERVICE_VERSION,
            }
            finished_at = utc_now()
            self.session.execute(
                update(entity_enrichment_runs_table)
                .where(entity_enrichment_runs_table.c.id == enrichment_run_id)
                .values(status="succeeded", metrics_json=metrics, finished_at=finished_at)
            )
            merge_raw_export_run_metadata(
                self.session,
                raw_export_run_id,
                key="entity_enrichment",
                value={
                    "stage": "entity_enrichment",
                    "stage_version": "1",
                    "service_version": SERVICE_VERSION,
                    "run_id": enrichment_run_id,
                    "ranked_entities_path": str(ranked_entities_path),
                    "provider": provider,
                    "model": model,
                    "model_profile": model_profile,
                    "prompt_version": prompt_version,
                    "metrics": metrics,
                    "generated_at": finished_at.isoformat(),
                },
            )
            self.session.commit()
            return EntityEnrichmentRunResult(
                run_id=enrichment_run_id,
                raw_export_run_id=raw_export_run_id,
                ranked_entities_path=ranked_entities_path,
                metrics=metrics,
            )
        except Exception as exc:
            self.session.execute(
                update(entity_enrichment_runs_table)
                .where(entity_enrichment_runs_table.c.id == enrichment_run_id)
                .values(status="failed", error=str(exc), finished_at=utc_now())
            )
            self.session.commit()
            raise

    def _build_request(
        self,
        ranked_entity: dict[str, Any],
        *,
        provider: str | None,
        model: str | None,
        model_profile: str | None,
        prompt_version: str,
    ) -> EntityEnrichmentRequest:
        context_snapshot = {
            "known_canonical_entities": self._known_canonical_entities_for(
                str(ranked_entity.get("normalized_text") or "")
            )
        }
        prompt_text = _prompt_text(ranked_entity, context_snapshot)
        return EntityEnrichmentRequest(
            ranked_entity=_compact_ranked_entity(ranked_entity),
            context_snapshot=context_snapshot,
            prompt_text=prompt_text,
            provider=provider,
            model=model,
            model_profile=model_profile,
            prompt_version=prompt_version,
        )

    def _known_canonical_entities_for(self, normalized_text: str) -> list[dict[str, Any]]:
        normalized_text = _normalize_name(normalized_text)
        entity_rows = self.session.execute(select(canonical_entities_table)).mappings().all()
        alias_rows = self.session.execute(select(canonical_entity_aliases_table)).mappings().all()
        aliases_by_entity: dict[str, list[dict[str, Any]]] = {}
        for alias in alias_rows:
            aliases_by_entity.setdefault(str(alias["canonical_entity_id"]), []).append(dict(alias))

        candidates: list[tuple[float, dict[str, Any]]] = []
        for entity in entity_rows:
            alias_values = aliases_by_entity.get(str(entity["id"]), [])
            entity_payload = {
                "id": entity["id"],
                "canonical_name": entity["canonical_name"],
                "normalized_name": entity["normalized_name"],
                "entity_type": entity["entity_type"],
                "status": entity["status"],
                "aliases": [
                    {
                        "alias": alias["alias"],
                        "normalized_alias": alias["normalized_alias"],
                        "status": alias["status"],
                    }
                    for alias in alias_values
                ],
            }
            score = _context_match_score(normalized_text, entity_payload)
            if score > 0:
                entity_payload["context_match_score"] = score
                candidates.append((score, entity_payload))
        candidates.sort(key=lambda item: (-item[0], str(item[1]["canonical_name"])))
        return [payload for _, payload in candidates[:MAX_CONTEXT_ENTITIES]]

    def _apply_decision(
        self,
        *,
        enrichment_run_id: str,
        sequence_index: int,
        ranked_entity: dict[str, Any],
        request: EntityEnrichmentRequest,
        decision: EntityEnrichmentDecision,
    ) -> dict[str, Any]:
        result_id = new_id()
        action = decision.action
        source_refs = _json_list(ranked_entity.get("source_refs_json"))
        ranked_text = str(ranked_entity.get("normalized_text") or "")
        canonical_entity_id: str | None = None
        status = "needs_review"
        merge_review_created = False

        if action == "attach_to_existing" and decision.canonical_entity_id:
            canonical = self._canonical_by_id(decision.canonical_entity_id)
            if canonical is not None:
                canonical_entity_id = str(canonical["id"])
                self._ensure_alias(
                    canonical_entity_id=canonical_entity_id,
                    alias=ranked_text,
                    confidence=decision.confidence,
                    evidence_refs=source_refs,
                    result_id=result_id,
                )
                status = "attached_to_existing"
        elif action == "reject_noise":
            status = "rejected_noise"
        elif action == "propose_new":
            canonical_name = (decision.canonical_name or ranked_text).strip()
            if canonical_name:
                normalized_name = _normalize_name(canonical_name)
                exact = self._canonical_by_normalized_name_or_alias(normalized_name)
                if exact is not None:
                    canonical_entity_id = str(exact["id"])
                    self._ensure_alias(
                        canonical_entity_id=canonical_entity_id,
                        alias=ranked_text,
                        confidence=decision.confidence,
                        evidence_refs=source_refs,
                        result_id=result_id,
                    )
                    status = "attached_to_existing"
                else:
                    conflict = self._find_fuzzy_canonical(normalized_name)
                    if conflict is not None:
                        canonical_entity_id = str(conflict["id"])
                        self._create_merge_candidate(
                            left_canonical_entity_id=canonical_entity_id,
                            proposed_name=canonical_name,
                            normalized_name=normalized_name,
                            reason=decision.reason,
                            evidence={
                                "ranked_entity_id": ranked_entity.get("entity_id"),
                                "ranked_entity_text": ranked_text,
                                "decision": decision.as_jsonable(),
                                "source_refs": source_refs,
                            },
                            result_id=result_id,
                        )
                        status = "needs_merge_review"
                        merge_review_created = True
                    else:
                        canonical_entity_id = self._create_canonical_entity(
                            canonical_name=canonical_name,
                            normalized_name=normalized_name,
                            entity_type=decision.entity_type or "unknown",
                            confidence=decision.confidence,
                            result_id=result_id,
                        )
                        self._ensure_alias(
                            canonical_entity_id=canonical_entity_id,
                            alias=ranked_text,
                            confidence=decision.confidence,
                            evidence_refs=source_refs,
                            result_id=result_id,
                        )
                        status = "created_canonical"

        self.session.execute(
            insert(entity_enrichment_results_table).values(
                id=result_id,
                run_id=enrichment_run_id,
                sequence_index=sequence_index,
                ranked_entity_id=str(ranked_entity.get("entity_id") or ""),
                ranked_entity_text=ranked_text,
                canonical_entity_id=canonical_entity_id,
                action=action,
                status=status,
                confidence=decision.confidence,
                reason=decision.reason,
                prompt_text=request.prompt_text,
                request_json=request.as_jsonable(),
                response_json=decision.raw_response_json or {"content": decision.as_jsonable()},
                parsed_response_json=decision.as_jsonable(),
                context_snapshot_json=request.context_snapshot,
                source_refs_json=source_refs,
                created_at=utc_now(),
            )
        )
        self.session.flush()
        return {"status": status, "merge_review_created": merge_review_created}

    def _create_canonical_entity(
        self,
        *,
        canonical_name: str,
        normalized_name: str,
        entity_type: str,
        confidence: float | None,
        result_id: str,
    ) -> str:
        now = utc_now()
        canonical_entity_id = new_id()
        self.session.execute(
            insert(canonical_entities_table).values(
                id=canonical_entity_id,
                canonical_name=canonical_name,
                normalized_name=normalized_name,
                entity_type=entity_type or "unknown",
                status="auto_pending",
                confidence=confidence,
                created_from_result_id=result_id,
                metadata_json={"service_version": SERVICE_VERSION},
                created_at=now,
                updated_at=now,
            )
        )
        self.session.flush()
        return canonical_entity_id

    def _ensure_alias(
        self,
        *,
        canonical_entity_id: str,
        alias: str,
        confidence: float | None,
        evidence_refs: list[str],
        result_id: str,
    ) -> None:
        normalized_alias = _normalize_name(alias)
        existing = (
            self.session.execute(
                select(canonical_entity_aliases_table).where(
                    canonical_entity_aliases_table.c.normalized_alias == normalized_alias
                )
            )
            .mappings()
            .first()
        )
        if existing is not None:
            return
        now = utc_now()
        self.session.execute(
            insert(canonical_entity_aliases_table).values(
                id=new_id(),
                canonical_entity_id=canonical_entity_id,
                alias=alias,
                normalized_alias=normalized_alias,
                alias_type="source_term",
                status="auto_pending",
                confidence=confidence,
                evidence_refs_json=evidence_refs,
                created_from_result_id=result_id,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.flush()

    def _create_merge_candidate(
        self,
        *,
        left_canonical_entity_id: str,
        proposed_name: str,
        normalized_name: str,
        reason: str | None,
        evidence: dict[str, Any],
        result_id: str,
    ) -> None:
        now = utc_now()
        self.session.execute(
            insert(canonical_merge_candidates_table).values(
                id=new_id(),
                left_canonical_entity_id=left_canonical_entity_id,
                right_canonical_entity_id=None,
                proposed_name=proposed_name,
                normalized_name=normalized_name,
                reason=reason,
                status="pending_review",
                evidence_json=evidence,
                created_from_result_id=result_id,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.flush()

    def _canonical_by_id(self, canonical_entity_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(canonical_entities_table).where(
                    canonical_entities_table.c.id == canonical_entity_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _canonical_by_normalized_name_or_alias(self, normalized_name: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(canonical_entities_table).where(
                    canonical_entities_table.c.normalized_name == normalized_name
                )
            )
            .mappings()
            .first()
        )
        if row is not None:
            return dict(row)
        alias = (
            self.session.execute(
                select(canonical_entity_aliases_table).where(
                    canonical_entity_aliases_table.c.normalized_alias == normalized_name
                )
            )
            .mappings()
            .first()
        )
        if alias is None:
            return None
        return self._canonical_by_id(str(alias["canonical_entity_id"]))

    def _find_fuzzy_canonical(self, normalized_name: str) -> dict[str, Any] | None:
        rows = self.session.execute(select(canonical_entities_table)).mappings().all()
        for row in rows:
            existing = _normalize_name(str(row["normalized_name"]))
            if _bounded_levenshtein(normalized_name, existing, max_distance=2) <= 2:
                return dict(row)
            if _token_overlap(normalized_name, existing) >= 0.75:
                return dict(row)
        return None

    def _require_run(self, raw_export_run_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(telegram_raw_export_runs_table).where(
                    telegram_raw_export_runs_table.c.id == raw_export_run_id
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(raw_export_run_id)
        if row["status"] != "succeeded":
            raise ValueError("entity enrichment requires a succeeded raw export run")
        return dict(row)


def _ranked_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    entity_ranking = metadata.get("entity_ranking")
    if not isinstance(entity_ranking, dict):
        raise ValueError("entity enrichment requires Stage 5.1 entity_ranking metadata")
    path_value = entity_ranking.get("ranked_entities_parquet_path")
    if not path_value:
        raise ValueError("entity enrichment requires entity_ranking.ranked_entities_parquet_path")
    path = Path(str(path_value))
    return path if path.is_absolute() else Path(".") / path


def _select_rows(
    rows: list[dict[str, Any]],
    *,
    include_statuses: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    allowed = set(include_statuses)
    selected = [row for row in rows if str(row.get("ranking_status")) in allowed]
    selected.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("normalized_text"))))
    return selected[: max(0, limit)]


def _prompt_text(ranked_entity: dict[str, Any], context_snapshot: dict[str, Any]) -> str:
    payload = {
        "task": "Resolve one ranked source entity into a canonical registry action.",
        "allowed_actions": [
            "attach_to_existing",
            "propose_new",
            "reject_noise",
            "needs_review",
        ],
        "output_schema": {
            "action": "attach_to_existing|propose_new|reject_noise|needs_review",
            "canonical_entity_id": "existing id when action=attach_to_existing",
            "canonical_name": "short stable Russian canonical name",
            "entity_type": "product|service|solution|term|unknown",
            "confidence": "0..1",
            "reason": "short operational explanation",
        },
        "ranked_entity": _compact_ranked_entity(ranked_entity),
        "known_canonical_entities": context_snapshot["known_canonical_entities"],
        "rules": [
            "Do not invent product facts not supported by source evidence.",
            "Prefer attach_to_existing when known canonical entity is equivalent.",
            "Use propose_new only when the concept is not represented in known entities.",
            "Use reject_noise for navigation, generic, malformed, or non-actionable terms.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _compact_ranked_entity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": row.get("entity_id"),
        "group_id": row.get("group_id"),
        "canonical_text": row.get("canonical_text"),
        "normalized_text": row.get("normalized_text"),
        "score": row.get("score"),
        "ranking_status": row.get("ranking_status"),
        "pos_pattern": _json_list(row.get("pos_pattern_json")),
        "reasons": _json_list(row.get("reasons_json")),
        "penalties": _json_list(row.get("penalties_json")),
        "source_refs": _json_list(row.get("source_refs_json")),
        "examples": _json_list(row.get("example_contexts_json"))[:3],
    }


def _matches_known_entity(normalized_text: str, entity: dict[str, Any]) -> bool:
    normalized_text = _normalize_name(normalized_text)
    if normalized_text == _normalize_name(str(entity.get("normalized_name") or "")):
        return True
    aliases = entity.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, dict) and normalized_text == _normalize_name(
                str(alias.get("normalized_alias") or "")
            ):
                return True
    return False


def _context_match_score(normalized_text: str, entity: dict[str, Any]) -> float:
    existing = _normalize_name(str(entity["normalized_name"]))
    if normalized_text == existing:
        return 1.0
    alias_scores = [
        _context_match_score(normalized_text, {"normalized_name": alias["normalized_alias"]})
        for alias in entity.get("aliases", [])
        if isinstance(alias, dict)
    ]
    best_alias = max(alias_scores) if alias_scores else 0.0
    distance = _bounded_levenshtein(normalized_text, existing, max_distance=2)
    if distance <= 2:
        return max(best_alias, 0.9 - distance * 0.1)
    overlap = _token_overlap(normalized_text, existing)
    return max(best_alias, overlap if overlap >= 0.5 else 0.0)


def _normalize_name(value: str) -> str:
    tokens = WORD_RE.findall(value.replace("ё", "е").casefold())
    return " ".join(tokens)


def _canonicalize_label(value: str) -> str:
    normalized = _normalize_name(value)
    return normalized[:1].upper() + normalized[1:] if normalized else value.strip()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(_normalize_name(left).split())
    right_tokens = set(_normalize_name(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _bounded_levenshtein(left: str, right: str, *, max_distance: int) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + cost,
                )
            )
            row_min = min(row_min, current[-1])
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("entity enrichment LLM expected a JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("entity enrichment LLM expected a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("entity enrichment LLM expected a JSON object")
    return parsed


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, parsed))
