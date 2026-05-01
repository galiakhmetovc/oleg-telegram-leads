"""Review-only lead candidate discovery over prepared Telegram archives."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.integrations.leads.fuzzy_classifier import (
    BUYING_INTENT_TERMS,
    GENERIC_EQUIPMENT_TERMS,
    NEGATIVE_INTENT_TERMS,
)
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

STAGE_NAME = "telegram_lead_candidate_discovery"
STAGE_VERSION = "1"

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)
DEFAULT_TOPIC_TERMS = (
    *GENERIC_EQUIPMENT_TERMS,
    "dahua",
    "hikvision",
    "ezviz",
    "щиток",
    "электрик",
    "слаботочка",
    "ip камера",
    "wifi камера",
    "wi-fi камера",
)


@dataclass(frozen=True)
class TelegramLeadCandidateDiscoveryResult:
    raw_export_run_id: str
    output_dir: Path
    candidates_json_path: Path
    summary_path: Path
    candidates: list[dict[str, Any]]
    metrics: dict[str, Any]

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "raw_export_run_id": self.raw_export_run_id,
            "output_dir": str(self.output_dir),
            "candidates_json_path": str(self.candidates_json_path),
            "summary_path": str(self.summary_path),
            "metrics": self.metrics,
        }


class TelegramLeadCandidateDiscoveryService:
    """Find review candidates without creating CRM leads or notifications."""

    def __init__(
        self,
        session: Session,
        *,
        output_root: Path | str = "./data/enriched",
    ) -> None:
        self.session = session
        self.output_root = Path(output_root)

    def write_candidates(
        self,
        raw_export_run_id: str,
        *,
        limit: int = 200,
        min_score: float = 0.6,
        batch_size: int = 5000,
        intent_terms: list[str] | None = None,
        topic_terms: list[str] | None = None,
        negative_terms: list[str] | None = None,
    ) -> TelegramLeadCandidateDiscoveryResult:
        run = self._require_run(raw_export_run_id)
        search_db_path = _fts_path_from_metadata(run)
        output_dir = (
            self.output_root
            / "telegram_lead_candidates"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        candidates_json_path = output_dir / "lead_candidates.json"
        summary_path = output_dir / "lead_candidate_discovery_summary.json"
        discovered_at = utc_now()

        scan = _scan_candidates(
            search_db_path,
            raw_export_run_id=raw_export_run_id,
            intent_terms=_normalize_terms(intent_terms or list(BUYING_INTENT_TERMS)),
            topic_terms=_normalize_terms(topic_terms or list(DEFAULT_TOPIC_TERMS)),
            negative_terms=_normalize_terms(negative_terms or list(NEGATIVE_INTENT_TERMS)),
            min_score=min_score,
            batch_size=max(1, batch_size),
        )
        candidates = sorted(
            scan["candidates"],
            key=lambda item: (float(item["score"]), str(item.get("date") or "")),
            reverse=True,
        )[: max(1, limit)]
        metrics = {
            "scanned_documents": scan["scanned_documents"],
            "candidate_count": len(candidates),
            "total_candidate_matches": len(scan["candidates"]),
            "negative_filtered_count": scan["negative_filtered_count"],
            "intent_only_count": scan["intent_only_count"],
            "topic_only_count": scan["topic_only_count"],
            "min_score": min_score,
            "limit": max(1, limit),
        }
        payload = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": discovered_at.isoformat(),
            "raw_export_run_id": raw_export_run_id,
            "source": {
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "source_kind": run["source_kind"],
                "username": run["username"],
            },
            "metrics": metrics,
            "candidates": candidates,
        }
        candidates_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(
                {key: value for key, value in payload.items() if key != "candidates"},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="lead_candidate_discovery",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": discovered_at.isoformat(),
                "candidates_json_path": str(candidates_json_path),
                "summary_path": str(summary_path),
                "candidate_count": len(candidates),
                "total_candidate_matches": len(scan["candidates"]),
            },
        )
        self.session.commit()
        return TelegramLeadCandidateDiscoveryResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            candidates_json_path=candidates_json_path,
            summary_path=summary_path,
            candidates=candidates,
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
            raise ValueError("lead candidate discovery requires a succeeded raw export run")
        return dict(row)


def _scan_candidates(
    search_db_path: Path,
    *,
    raw_export_run_id: str,
    intent_terms: list[str],
    topic_terms: list[str],
    negative_terms: list[str],
    min_score: float,
    batch_size: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    scanned = 0
    negative_filtered = 0
    intent_only = 0
    topic_only = 0
    last_row_id = 0
    with sqlite3.connect(search_db_path) as connection:
        connection.row_factory = sqlite3.Row
        while True:
            rows = connection.execute(
                """
                SELECT
                    row_id,
                    raw_export_run_id,
                    monitored_source_id,
                    telegram_message_id,
                    row_index,
                    reply_to_message_id,
                    thread_id,
                    thread_key,
                    date,
                    message_url,
                    clean_text,
                    lemmas_text,
                    token_count
                FROM messages
                WHERE entity_type = 'telegram_message' AND row_id > ?
                ORDER BY row_id
                LIMIT ?
                """,
                (last_row_id, batch_size),
            ).fetchall()
            if not rows:
                break
            for row in rows:
                scanned += 1
                last_row_id = int(row["row_id"])
                candidate = _candidate_from_row(
                    row,
                    raw_export_run_id=raw_export_run_id,
                    intent_terms=intent_terms,
                    topic_terms=topic_terms,
                    negative_terms=negative_terms,
                    min_score=min_score,
                )
                if candidate is None:
                    clean_text = str(row["clean_text"] or "")
                    lemmas_text = str(row["lemmas_text"] or "")
                    terms = _row_terms(clean_text, lemmas_text)
                    intents = _matched_terms(clean_text, terms, intent_terms)
                    topics = _matched_terms(clean_text, terms, topic_terms)
                    negatives = _matched_terms(clean_text, terms, negative_terms)
                    if intents and negatives:
                        negative_filtered += 1
                    elif intents and not topics:
                        intent_only += 1
                    elif topics and not intents:
                        topic_only += 1
                    continue
                candidates.append(candidate)
    return {
        "candidates": candidates,
        "scanned_documents": scanned,
        "negative_filtered_count": negative_filtered,
        "intent_only_count": intent_only,
        "topic_only_count": topic_only,
    }


def _candidate_from_row(
    row: sqlite3.Row,
    *,
    raw_export_run_id: str,
    intent_terms: list[str],
    topic_terms: list[str],
    negative_terms: list[str],
    min_score: float,
) -> dict[str, Any] | None:
    clean_text = str(row["clean_text"] or "")
    terms = _row_terms(clean_text, str(row["lemmas_text"] or ""))
    matched_intents = _matched_terms(clean_text, terms, intent_terms)
    matched_topics = _matched_terms(clean_text, terms, topic_terms)
    negative_signals = _matched_terms(clean_text, terms, negative_terms)
    if not matched_intents or not matched_topics or negative_signals:
        return None
    score = _score_candidate(clean_text, matched_intents, matched_topics)
    if score < min_score:
        return None
    message_id = int(row["telegram_message_id"])
    return {
        "raw_export_run_id": raw_export_run_id,
        "monitored_source_id": row["monitored_source_id"],
        "telegram_message_id": message_id,
        "row_index": int(row["row_index"]),
        "date": str(row["date"] or ""),
        "message_url": str(row["message_url"] or ""),
        "thread_key": str(row["thread_key"] or message_id),
        "reply_to_message_id": (
            int(row["reply_to_message_id"]) if row["reply_to_message_id"] is not None else None
        ),
        "thread_id": str(row["thread_id"] or ""),
        "clean_text": clean_text,
        "token_count": int(row["token_count"] or 0),
        "score": score,
        "status": "needs_review",
        "sources": ["fts_intent_scan"],
        "matched_intents": matched_intents,
        "matched_topics": matched_topics,
        "negative_signals": negative_signals,
        "reason_codes": ["intent_and_topic"],
    }


def _score_candidate(
    clean_text: str,
    matched_intents: list[str],
    matched_topics: list[str],
) -> float:
    question_bonus = 0.04 if "?" in clean_text else 0.0
    score = (
        0.52
        + min(0.18, len(matched_intents) * 0.08)
        + min(0.22, len(matched_topics) * 0.06)
        + question_bonus
    )
    return round(min(0.99, score), 4)


def _matched_terms(clean_text: str, row_terms: set[str], terms: list[str]) -> list[str]:
    matches: list[str] = []
    for term in terms:
        if " " in term or "-" in term:
            if term in clean_text:
                matches.append(term)
            continue
        if term in row_terms:
            matches.append(term)
    return matches


def _row_terms(clean_text: str, lemmas_text: str) -> set[str]:
    return {
        token.casefold()
        for token in [*TOKEN_RE.findall(clean_text), *TOKEN_RE.findall(lemmas_text)]
        if token
    }


def _normalize_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = re.sub(r"\s+", " ", str(term).casefold().strip())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _fts_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    fts_index = metadata.get("fts_index")
    if not isinstance(fts_index, dict):
        raise ValueError("lead candidate discovery requires Stage FTS metadata")
    path_value = fts_index.get("search_db_path")
    if not path_value:
        raise ValueError("lead candidate discovery requires fts_index.search_db_path")
    path = Path(str(path_value))
    return path if path.is_absolute() else Path(".") / path
