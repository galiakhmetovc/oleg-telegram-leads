"""Telegram Stage 5.1 rule-based entity cleanup and ranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

STAGE_NAME = "telegram_entity_ranking"
STAGE_VERSION = "1"
RANKING_POLICY = "rule_based_v1"

PROMOTE_THRESHOLD = 0.65
REVIEW_THRESHOLD = 0.35
TOP_JSON_LIMIT = 200

POS_PATTERN_WEIGHTS = {
    "NOUN": 0.05,
    "PROPN": 0.10,
    "PROPN PROPN": 0.25,
    "NOUN NOUN": 0.25,
    "ADJ NOUN": 0.20,
}
NAVIGATION_TERMS = {
    "telegram-канал",
    "канал",
    "категория",
    "город",
    "подписка",
    "запрос",
    "раздел",
    "меню",
    "страница",
}
NAVIGATION_CONTEXT_MARKERS = {
    "перейти",
    "категория",
    "выбрать город",
    "ваш город",
    "популярные запросы",
    "подписаться",
}
LOW_INFORMATION_TERMS = {
    "база",
    "вопрос",
    "время",
    "выпуск",
    "группа",
    "тема",
    "тело",
    "ночь",
    "ноль",
    "гость",
    "гост",
    "штука",
    "вещь",
    "часть",
    "пример",
}
NON_SPECIFIC_MODIFIERS = {"наш", "ваш", "свой", "этот", "любой", "каждый", "самый"}
STOP_TERMS = {
    "url",
    "это",
    "как",
    "для",
    "или",
    "при",
    "что",
    "наш",
    "ваш",
    "который",
    "быть",
}
PHONE_LIKE_RE = re.compile(r"(?:\d[\s().-]*){7,}")
LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
DIGIT_RE = re.compile(r"\d")


@dataclass(frozen=True)
class TelegramEntityRankingResult:
    raw_export_run_id: str
    output_dir: Path
    ranked_entities_parquet_path: Path
    ranked_entities_json_path: Path
    noise_report_path: Path
    summary_path: Path
    metrics: dict[str, Any]


class TelegramEntityRankingService:
    """Rank raw Stage 5 entities while preserving all extracted entities."""

    def __init__(
        self,
        session: Session,
        *,
        enriched_root: Path | str = "./data/enriched",
    ) -> None:
        self.session = session
        self.enriched_root = Path(enriched_root)

    def write_rankings(self, raw_export_run_id: str) -> TelegramEntityRankingResult:
        run = self._require_run(raw_export_run_id)
        entities_path = _entities_path_from_metadata(run)
        entity_rows = pq.read_table(entities_path).to_pylist()

        output_dir = (
            self.enriched_root
            / "telegram_entity_rankings"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        ranked_entities_parquet_path = output_dir / "ranked_entities.parquet"
        ranked_entities_json_path = output_dir / "ranked_entities.json"
        noise_report_path = output_dir / "entity_noise_report.json"
        summary_path = output_dir / "entity_ranking_summary.json"

        ranked_rows = [_rank_row(row) for row in entity_rows]
        ranked_rows.sort(key=lambda row: (-float(row["score"]), str(row["normalized_text"])))
        metrics = _metrics(ranked_rows)
        ranked_payload = _ranked_payload(ranked_rows, metrics)
        noise_payload = _noise_payload(ranked_rows)
        generated_at = utc_now().isoformat()

        _write_ranked_parquet(ranked_entities_parquet_path, ranked_rows)
        _write_json(ranked_entities_json_path, ranked_payload)
        _write_json(noise_report_path, noise_payload)
        summary = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": generated_at,
            "input": {
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "entities_parquet_path": str(entities_path),
            },
            "outputs": {
                "ranked_entities_parquet_path": str(ranked_entities_parquet_path),
                "ranked_entities_json_path": str(ranked_entities_json_path),
                "noise_report_path": str(noise_report_path),
                "summary_path": str(summary_path),
            },
            "policy": {
                "ranking_policy": RANKING_POLICY,
                "promote_threshold": PROMOTE_THRESHOLD,
                "review_threshold": REVIEW_THRESHOLD,
                "domain_profiles_applied": False,
            },
            "metrics": metrics,
        }
        _write_json(summary_path, summary)

        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="entity_ranking",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": generated_at,
                "ranked_entities_parquet_path": str(ranked_entities_parquet_path),
                "ranked_entities_json_path": str(ranked_entities_json_path),
                "noise_report_path": str(noise_report_path),
                "summary_path": str(summary_path),
                "ranked_entity_rows": metrics["ranked_entity_rows"],
                "promote_candidate_rows": metrics["promote_candidate_rows"],
                "review_candidate_rows": metrics["review_candidate_rows"],
                "noise_rows": metrics["noise_rows"],
                "ranking_policy": RANKING_POLICY,
            },
        )
        self.session.commit()
        return TelegramEntityRankingResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            ranked_entities_parquet_path=ranked_entities_parquet_path,
            ranked_entities_json_path=ranked_entities_json_path,
            noise_report_path=noise_report_path,
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
            raise ValueError("entity ranking requires a succeeded raw export run")
        return dict(row)


def _rank_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized_text = str(row.get("normalized_text") or "")
    mention_count = int(row.get("mention_count") or 0)
    source_count = int(row.get("source_count") or 0)
    pos_pattern = _json_list(row.get("pos_pattern_json"))
    pos_key = " ".join(pos_pattern)
    entity_type_counts = _json_dict(row.get("entity_type_counts_json"))
    examples = _json_list(row.get("example_contexts_json"))

    score = 0.20
    reasons: list[str] = []
    penalties: list[str] = []

    pos_weight = POS_PATTERN_WEIGHTS.get(pos_key, 0.0)
    if pos_weight:
        score += pos_weight
        reasons.append(f"pos_pattern:{pos_key.replace(' ', '_')}")

    if mention_count <= 1:
        score -= 0.25
        penalties.append("single_mention")
    elif mention_count <= 3:
        score += 0.10
        reasons.append(f"mention_count:{mention_count}")
    elif mention_count < 10:
        score += 0.25
        reasons.append(f"mention_count:{mention_count}")
    else:
        score += 0.35
        reasons.append(f"mention_count:{mention_count}")

    if source_count >= 4:
        score += 0.30
        reasons.append(f"source_count:{source_count}")
    elif source_count >= 2:
        score += 0.20
        reasons.append(f"source_count:{source_count}")

    if int(entity_type_counts.get("telegram_artifact") or 0) > 0:
        score += 0.15
        reasons.append("artifact_mentions")

    score = _apply_quality_penalties(
        normalized_text=normalized_text,
        examples=examples,
        score=score,
        penalties=penalties,
    )
    score = round(max(0.0, min(1.0, score)), 6)
    status = _ranking_status(score)

    result = dict(row)
    result.update(
        {
            "score": score,
            "ranking_status": status,
            "reasons_json": _json_string(reasons),
            "penalties_json": _json_string(penalties),
        }
    )
    return result


def _apply_quality_penalties(
    *,
    normalized_text: str,
    examples: list[str],
    score: float,
    penalties: list[str],
) -> float:
    compact = normalized_text.replace(" ", "")
    if len(compact) < 4:
        score -= 0.35
        penalties.append("too_short")

    if not LETTER_RE.search(normalized_text):
        score -= 0.50
        penalties.append("low_information")

    if _mostly_numeric(normalized_text):
        score -= 0.50
        penalties.append("mostly_numeric")

    if PHONE_LIKE_RE.search(normalized_text):
        score -= 0.50
        penalties.append("contact_noise")

    term_parts = set(normalized_text.split())
    if normalized_text in STOP_TERMS or term_parts <= STOP_TERMS:
        score -= 0.40
        penalties.append("stop_term")

    if normalized_text in LOW_INFORMATION_TERMS:
        score -= 0.25
        penalties.append("low_information")

    if _has_navigation_noise(normalized_text, examples):
        score -= 0.45
        penalties.append("navigation_noise")

    if _has_non_specific_modifier(normalized_text):
        score -= 0.45
        penalties.append("non_specific_modifier")

    if _is_plain_single_token(normalized_text):
        score = min(score, 0.60)
        penalties.append("single_token_generic")

    return score


def _has_navigation_noise(normalized_text: str, examples: list[str]) -> bool:
    term_parts = set(normalized_text.split())
    if normalized_text in NAVIGATION_TERMS or term_parts.intersection(NAVIGATION_TERMS):
        return True
    joined_examples = " ".join(examples).casefold()
    return any(marker in joined_examples for marker in NAVIGATION_CONTEXT_MARKERS)


def _mostly_numeric(value: str) -> bool:
    digits = len(DIGIT_RE.findall(value))
    letters = len(LETTER_RE.findall(value))
    return digits > 0 and digits >= letters


def _has_non_specific_modifier(value: str) -> bool:
    parts = value.split()
    return len(parts) > 1 and parts[0] in NON_SPECIFIC_MODIFIERS


def _is_plain_single_token(value: str) -> bool:
    if " " in value:
        return False
    if "-" in value or DIGIT_RE.search(value):
        return False
    return not _has_mixed_script(value)


def _has_mixed_script(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value)) and bool(re.search(r"[А-Яа-яЁё]", value))


def _ranking_status(score: float) -> str:
    if score >= PROMOTE_THRESHOLD:
        return "promote_candidate"
    if score >= REVIEW_THRESHOLD:
        return "review_candidate"
    return "noise"


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row["ranking_status"]) for row in rows)
    penalties = Counter(
        penalty
        for row in rows
        for penalty in _json_list(row.get("penalties_json"))
    )
    reasons = Counter(
        reason
        for row in rows
        for reason in _json_list(row.get("reasons_json"))
    )
    return {
        "ranked_entity_rows": len(rows),
        "promote_candidate_rows": statuses.get("promote_candidate", 0),
        "review_candidate_rows": statuses.get("review_candidate", 0),
        "noise_rows": statuses.get("noise", 0),
        "status_counts": dict(sorted(statuses.items())),
        "penalty_counts": dict(sorted(penalties.items())),
        "reason_counts": dict(sorted(reasons.items())),
    }


def _ranked_payload(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "ranking_policy": RANKING_POLICY,
        "metrics": metrics,
        "promote_candidates": _compact_rows(rows, "promote_candidate"),
        "review_candidates": _compact_rows(rows, "review_candidate"),
        "noise": _compact_rows(rows, "noise"),
    }


def _noise_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    noise_rows = [row for row in rows if row["ranking_status"] == "noise"]
    penalty_counts = Counter(
        penalty
        for row in noise_rows
        for penalty in _json_list(row.get("penalties_json"))
    )
    return {
        "stage": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "ranking_policy": RANKING_POLICY,
        "noise_rows": len(noise_rows),
        "penalty_counts": dict(sorted(penalty_counts.items())),
        "samples": _compact_rows(rows, "noise", limit=100),
    }


def _compact_rows(
    rows: list[dict[str, Any]],
    status: str,
    *,
    limit: int = TOP_JSON_LIMIT,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if row["ranking_status"] != status:
            continue
        result.append(
            {
                "entity_id": row["entity_id"],
                "group_id": row["group_id"],
                "normalized_text": row["normalized_text"],
                "canonical_text": row["canonical_text"],
                "score": row["score"],
                "mention_count": row["mention_count"],
                "source_count": row["source_count"],
                "pos_pattern": _json_list(row["pos_pattern_json"]),
                "reasons": _json_list(row["reasons_json"]),
                "penalties": _json_list(row["penalties_json"]),
                "examples": _json_list(row["example_contexts_json"])[:2],
            }
        )
        if len(result) >= limit:
            break
    return result


def _entities_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    entity_extraction = metadata.get("entity_extraction")
    if not isinstance(entity_extraction, dict):
        raise ValueError("entity ranking requires Stage 5 entity_extraction metadata")
    path_value = entity_extraction.get("entities_parquet_path")
    if not path_value:
        raise ValueError("entity ranking requires entity_extraction.entities_parquet_path")
    return _resolve_path(path_value)


def _write_ranked_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    schema = pa.schema(
        [
            ("entity_id", pa.string()),
            ("group_id", pa.string()),
            ("canonical_text", pa.string()),
            ("normalized_text", pa.string()),
            ("lemma_text", pa.string()),
            ("pos_pattern_json", pa.string()),
            ("mention_count", pa.int64()),
            ("source_count", pa.int64()),
            ("source_refs_json", pa.string()),
            ("example_contexts_json", pa.string()),
            ("entity_type_counts_json", pa.string()),
            ("group_confidence", pa.string()),
            ("group_method", pa.string()),
            ("score", pa.float64()),
            ("ranking_status", pa.string()),
            ("reasons_json", pa.string()),
            ("penalties_json", pa.string()),
        ]
    )
    table = (
        pa.Table.from_pylist(rows, schema=schema)
        if rows
        else pa.Table.from_pylist([], schema=schema)
    )
    pq.write_table(table, path, compression="zstd")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _json_dict(value: Any) -> dict[str, Any]:
    parsed = _json_any(value, default={})
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[str]:
    parsed = _json_any(value, default=[])
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_any(value: Any, *, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
