"""Review-only LLM arbitration over Telegram lead candidates."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

STAGE_NAME = "telegram_lead_candidate_llm_arbitration"
STAGE_VERSION = "1"
PROMPT_VERSION = "lead-candidate-arbitration-v1"

SYSTEM_PROMPT = (
    "Return strict JSON only. You are an operator-assist lead arbitrator for PUR, "
    "a business that sells and supports smart-home, CCTV, intercom, security, access-control, "
    "networking, electrical automation, and related installation/configuration services. "
    "Classify only the candidate Telegram message and its provided context. Use lead when a "
    "person likely needs equipment, installation, configuration, repair, selection, or operator "
    "help. Use maybe when a human should inspect it. Use not_lead for sellers, ads, pure peer "
    "discussion, already solved cases, jokes, unrelated goods, and generic mentions without a "
    "current actionable need. Do not create catalog facts."
)


@dataclass(frozen=True)
class TelegramLeadCandidateLlmArbitrationResult:
    raw_export_run_id: str
    output_dir: Path
    arbitration_json_path: Path
    traces_jsonl_path: Path
    summary_path: Path
    metrics: dict[str, Any]

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "raw_export_run_id": self.raw_export_run_id,
            "output_dir": str(self.output_dir),
            "arbitration_json_path": str(self.arbitration_json_path),
            "traces_jsonl_path": str(self.traces_jsonl_path),
            "summary_path": str(self.summary_path),
            "metrics": self.metrics,
        }


class TelegramLeadCandidateLlmArbitrationService:
    """Ask an LLM to rerank rule-discovered candidates without mutating CRM leads."""

    def __init__(
        self,
        session: Session,
        *,
        output_root: Path | str = "./data/enriched",
    ) -> None:
        self.session = session
        self.output_root = Path(output_root)

    def write_arbitration(
        self,
        raw_export_run_id: str,
        *,
        client: AiChatClient,
        provider: str,
        model: str,
        model_profile: str | None = None,
        candidates_json_path: Path | str | None = None,
        limit: int = 100,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        context_window: int = 2,
        thread_context_limit: int = 8,
    ) -> TelegramLeadCandidateLlmArbitrationResult:
        run = self._require_run(raw_export_run_id)
        candidate_payload_path = (
            _resolve_path(candidates_json_path)
            if candidates_json_path is not None
            else _lead_candidates_path_from_metadata(run)
        )
        search_db_path = _fts_path_from_metadata(run)
        candidate_payload = _json_file(candidate_payload_path)
        candidates = _candidate_items(candidate_payload)[: max(1, limit)]

        output_dir = (
            self.output_root
            / "telegram_lead_candidate_arbitration"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        arbitration_json_path = output_dir / "lead_candidate_llm_arbitration.json"
        traces_jsonl_path = output_dir / "lead_candidate_llm_traces.jsonl"
        summary_path = output_dir / "lead_candidate_llm_arbitration_summary.json"
        generated_at = utc_now()

        results: list[dict[str, Any]] = []
        counters: Counter[str] = Counter()
        traces: list[str] = []
        with sqlite3.connect(search_db_path) as connection:
            connection.row_factory = sqlite3.Row
            for sequence_index, candidate in enumerate(candidates):
                context = _context_for_candidate(
                    connection,
                    candidate,
                    raw_export_run_id=raw_export_run_id,
                    context_window=max(0, context_window),
                    thread_context_limit=max(1, thread_context_limit),
                )
                prompt_text = _prompt_text(candidate, context)
                started = perf_counter()
                response_json: dict[str, Any] | None = None
                raw_response = ""
                try:
                    completion = asyncio.run(
                        client.complete(
                            messages=[
                                AiChatMessage(role="system", content=SYSTEM_PROMPT),
                                AiChatMessage(role="user", content=prompt_text),
                            ],
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                    )
                    raw_response = completion.content
                    response_json = {
                        "content": completion.content,
                        "model": completion.model,
                        "request_id": completion.request_id,
                        "usage": completion.usage,
                        "raw_response": completion.raw_response,
                    }
                    decision = _decision_from_llm_json(completion.content)
                except Exception as exc:  # noqa: BLE001
                    counters["error_count"] += 1
                    decision = _error_decision(exc)
                    if response_json is None:
                        response_json = {
                            "content": raw_response,
                            "model": model,
                            "request_id": None,
                            "usage": {},
                            "raw_response": {},
                        }
                    response_json["error"] = str(exc)
                elapsed_ms = round((perf_counter() - started) * 1000, 3)
                decision_value = str(decision["decision"])
                counters[f"{decision_value}_count"] += 1
                counters["processed_candidates"] += 1

                result_item = {
                    "sequence_index": sequence_index,
                    "candidate": candidate,
                    "context": context,
                    "prompt_version": PROMPT_VERSION,
                    "prompt_text": prompt_text,
                    "provider": provider,
                    "model": model,
                    "model_profile": model_profile,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "elapsed_ms": elapsed_ms,
                    "raw_response": raw_response,
                    "response_json": response_json,
                    "decision": decision,
                }
                results.append(result_item)
                traces.append(json.dumps(result_item, ensure_ascii=False, sort_keys=True))

        metrics = {
            "selected_candidates": len(candidates),
            "processed_candidates": counters["processed_candidates"],
            "lead_count": counters["lead_count"],
            "maybe_count": counters["maybe_count"],
            "not_lead_count": counters["not_lead_count"],
            "error_count": counters["error_count"],
            "prompt_version": PROMPT_VERSION,
            "stage_version": STAGE_VERSION,
        }
        payload = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "prompt_version": PROMPT_VERSION,
            "generated_at": generated_at.isoformat(),
            "raw_export_run_id": raw_export_run_id,
            "provider": provider,
            "model": model,
            "model_profile": model_profile,
            "source": {
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "source_kind": run["source_kind"],
                "username": run["username"],
            },
            "input": {
                "candidates_json_path": str(candidate_payload_path),
                "search_db_path": str(search_db_path),
                "limit": max(1, limit),
                "context_window": max(0, context_window),
                "thread_context_limit": max(1, thread_context_limit),
            },
            "metrics": metrics,
            "results": results,
        }
        arbitration_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        traces_jsonl_path.write_text("\n".join(traces) + ("\n" if traces else ""), encoding="utf-8")
        summary_path.write_text(
            json.dumps(
                {key: value for key, value in payload.items() if key != "results"},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="lead_candidate_llm_arbitration",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "generated_at": generated_at.isoformat(),
                "arbitration_json_path": str(arbitration_json_path),
                "traces_jsonl_path": str(traces_jsonl_path),
                "summary_path": str(summary_path),
                "provider": provider,
                "model": model,
                "model_profile": model_profile,
                "metrics": metrics,
            },
        )
        self.session.commit()
        return TelegramLeadCandidateLlmArbitrationResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            arbitration_json_path=arbitration_json_path,
            traces_jsonl_path=traces_jsonl_path,
            summary_path=summary_path,
            metrics=metrics,
        )

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
            raise ValueError("lead candidate LLM arbitration requires a succeeded raw export run")
        return dict(row)


def _context_for_candidate(
    connection: sqlite3.Connection,
    candidate: dict[str, Any],
    *,
    raw_export_run_id: str,
    context_window: int,
    thread_context_limit: int,
) -> list[dict[str, Any]]:
    rows_by_key: dict[str, sqlite3.Row] = {}
    message_id = int(candidate["telegram_message_id"])
    row_index = int(candidate.get("row_index") or 0)
    thread_key = str(candidate.get("thread_key") or message_id)
    for row in connection.execute(
        """
        SELECT telegram_message_id, row_index, reply_to_message_id, thread_key, date,
               message_url, clean_text, token_count
        FROM messages
        WHERE raw_export_run_id = ?
          AND entity_type = 'telegram_message'
          AND row_index BETWEEN ? AND ?
        ORDER BY row_index
        """,
        (raw_export_run_id, row_index - context_window, row_index + context_window),
    ).fetchall():
        rows_by_key[str(row["telegram_message_id"])] = row
    for row in connection.execute(
        """
        SELECT telegram_message_id, row_index, reply_to_message_id, thread_key, date,
               message_url, clean_text, token_count
        FROM messages
        WHERE raw_export_run_id = ?
          AND entity_type = 'telegram_message'
          AND thread_key = ?
        ORDER BY row_index
        LIMIT ?
        """,
        (raw_export_run_id, thread_key, thread_context_limit),
    ).fetchall():
        rows_by_key[str(row["telegram_message_id"])] = row
    reply_to = candidate.get("reply_to_message_id")
    if reply_to is not None:
        row = connection.execute(
            """
            SELECT telegram_message_id, row_index, reply_to_message_id, thread_key, date,
                   message_url, clean_text, token_count
            FROM messages
            WHERE raw_export_run_id = ?
              AND entity_type = 'telegram_message'
              AND telegram_message_id = ?
            LIMIT 1
            """,
            (raw_export_run_id, int(reply_to)),
        ).fetchone()
        if row is not None:
            rows_by_key[str(row["telegram_message_id"])] = row
    rows = sorted(rows_by_key.values(), key=lambda item: int(item["row_index"]))
    return [_context_item(row, candidate_message_id=message_id) for row in rows]


def _context_item(row: sqlite3.Row, *, candidate_message_id: int) -> dict[str, Any]:
    message_id = int(row["telegram_message_id"])
    role = "candidate" if message_id == candidate_message_id else "neighbor"
    return {
        "role": role,
        "telegram_message_id": message_id,
        "row_index": int(row["row_index"]),
        "reply_to_message_id": (
            int(row["reply_to_message_id"]) if row["reply_to_message_id"] is not None else None
        ),
        "thread_key": str(row["thread_key"] or ""),
        "date": str(row["date"] or ""),
        "message_url": str(row["message_url"] or ""),
        "clean_text": str(row["clean_text"] or ""),
        "token_count": int(row["token_count"] or 0),
    }


def _prompt_text(candidate: dict[str, Any], context: list[dict[str, Any]]) -> str:
    payload = {
        "candidate": _compact_candidate(candidate),
        "neighbor_context": context,
        "output_schema": {
            "decision": "lead | maybe | not_lead",
            "confidence": "number 0..1",
            "need_operator": "boolean",
            "why": "short Russian explanation",
            "matched_need": "short concrete need or empty string",
            "relevant_catalog_items": ["catalog item names if explicitly matched, otherwise []"],
            "false_positive_reason": "null or short Russian explanation",
        },
    }
    return (
        "Определи, является ли кандидат лидом для ПУР.\n"
        "Критерии:\n"
        "- lead: есть практический запрос на подбор, покупку, монтаж, настройку, ремонт, "
        "поддержку или срочную помощь оператора.\n"
        "- maybe: сигнал неполный, но оператору стоит посмотреть.\n"
        "- not_lead: обсуждение, объявление продавца, реклама, шутка, уже решено, "
        "нерелевантный товар или нет действия для оператора.\n"
        "Верни только JSON по схеме. Не добавляй markdown.\n\n"
        "Соседний контекст нужен только для понимания реплаев и уточнений; решение принимай "
        "по кандидату и явной связи с контекстом.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}"
    )


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "telegram_message_id": candidate.get("telegram_message_id"),
        "date": candidate.get("date"),
        "message_url": candidate.get("message_url"),
        "clean_text": candidate.get("clean_text"),
        "score": candidate.get("score"),
        "matched_intents": candidate.get("matched_intents") or [],
        "matched_topics": candidate.get("matched_topics") or [],
        "negative_signals": candidate.get("negative_signals") or [],
        "reason_codes": candidate.get("reason_codes") or [],
    }


def _decision_from_llm_json(content: str) -> dict[str, Any]:
    parsed = _parse_json_object(content)
    decision = _decision(parsed.get("decision"))
    confidence = _score(parsed.get("confidence"), default=0.5)
    return {
        "decision": decision,
        "confidence": confidence,
        "need_operator": _bool(parsed.get("need_operator"), default=decision in {"lead", "maybe"}),
        "why": _optional_string(parsed.get("why")) or _optional_string(parsed.get("reason")) or "",
        "matched_need": _optional_string(parsed.get("matched_need")) or "",
        "relevant_catalog_items": _string_list(parsed.get("relevant_catalog_items")),
        "false_positive_reason": _optional_string(parsed.get("false_positive_reason")),
        "parsed_response": parsed,
    }


def _error_decision(exc: Exception) -> dict[str, Any]:
    return {
        "decision": "maybe",
        "confidence": 0.0,
        "need_operator": True,
        "why": "LLM arbitration failed; operator review is required.",
        "matched_need": "",
        "relevant_catalog_items": [],
        "false_positive_reason": None,
        "error": str(exc),
    }


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM arbitration expected valid JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("LLM arbitration expected valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM arbitration expected valid JSON object")
    return parsed


def _decision(value: Any) -> str:
    decision = str(value or "").casefold()
    if decision in {"lead", "maybe", "not_lead"}:
        return decision
    raise ValueError(f"LLM arbitration returned unsupported decision: {value!r}")


def _score(value: Any, *, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _candidate_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("lead candidate payload must contain candidates array")
    return [item for item in candidates if isinstance(item, dict)]


def _json_file(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def _lead_candidates_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    block = metadata.get("lead_candidate_discovery")
    if not isinstance(block, dict):
        raise ValueError("LLM arbitration requires lead_candidate_discovery metadata")
    path_value = block.get("candidates_json_path")
    if not path_value:
        raise ValueError("LLM arbitration requires lead_candidate_discovery.candidates_json_path")
    return _resolve_path(path_value)


def _fts_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    block = metadata.get("fts_index")
    if not isinstance(block, dict):
        raise ValueError("LLM arbitration requires fts_index metadata")
    path_value = block.get("search_db_path")
    if not path_value:
        raise ValueError("LLM arbitration requires fts_index.search_db_path")
    return _resolve_path(path_value)


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
