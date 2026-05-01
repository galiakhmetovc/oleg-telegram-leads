"""Telegram Stage 5 POS-based entity extraction and exact-only grouping."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
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

STAGE_NAME = "telegram_entity_extraction"
STAGE_VERSION = "1"
AUTO_MERGE_POLICY = "exact_only"
MAX_REVIEW_CANDIDATES = 5000

SINGLE_POS = {"NOUN", "PROPN"}
TWO_TOKEN_PATTERNS = {("NOUN", "NOUN"), ("ADJ", "NOUN")}
STOP_LEMMAS = {
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
LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
PUNCT_RE = re.compile(r"(^[^\wА-Яа-яЁё]+|[^\wА-Яа-яЁё]+$)", re.UNICODE)
SPACE_RE = re.compile(r"\s+")
CSV_FIELDS = [
    "group_id",
    "candidate_1",
    "candidate_2",
    "similarity_score",
    "method",
    "pos_pattern",
    "example_context",
    "action_status",
]

CYRILLIC_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


@dataclass(frozen=True)
class TelegramEntityExtractionResult:
    raw_export_run_id: str
    output_dir: Path
    entities_parquet_path: Path
    entity_groups_path: Path
    resolution_candidates_path: Path
    summary_path: Path
    metrics: dict[str, Any]


class TelegramEntityExtractionService:
    """Extract entity candidates from normalized POS signals without domain rules."""

    def __init__(
        self,
        session: Session,
        *,
        enriched_root: Path | str = "./data/enriched",
    ) -> None:
        self.session = session
        self.enriched_root = Path(enriched_root)

    def write_entities(self, raw_export_run_id: str) -> TelegramEntityExtractionResult:
        run = self._require_run(raw_export_run_id)
        features_path = _features_path_from_metadata(run)
        rows = pq.read_table(features_path).to_pylist()

        output_dir = (
            self.enriched_root
            / "telegram_entities"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        entities_parquet_path = output_dir / "entities.parquet"
        entity_groups_path = output_dir / "entity_groups.json"
        resolution_candidates_path = output_dir / "entity_resolution_candidates.csv"
        summary_path = output_dir / "entity_extraction_summary.json"

        mentions = [
            mention
            for row in rows
            for mention in _candidate_mentions(row)
        ]
        entity_rows = _aggregate_entities(mentions)
        groups_payload = _groups_payload(entity_rows)
        review_candidates = _resolution_candidates(groups_payload["groups"])
        metrics = _metrics(rows, entity_rows, groups_payload["groups"], review_candidates)
        generated_at = utc_now().isoformat()

        _write_entities_parquet(entities_parquet_path, entity_rows)
        _write_json(entity_groups_path, groups_payload)
        _write_resolution_csv(resolution_candidates_path, review_candidates)
        summary = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": generated_at,
            "input": {
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "features_parquet_path": str(features_path),
            },
            "outputs": {
                "entities_parquet_path": str(entities_parquet_path),
                "entity_groups_path": str(entity_groups_path),
                "resolution_candidates_path": str(resolution_candidates_path),
                "summary_path": str(summary_path),
            },
            "policy": {
                "auto_merge_policy": AUTO_MERGE_POLICY,
                "auto_merge_confidence": "high",
                "review_required_for": ["medium", "low"],
            },
            "metrics": metrics,
            "sample_entities": [
                {
                    "normalized_text": row["normalized_text"],
                    "pos_pattern": json.loads(row["pos_pattern_json"]),
                    "mention_count": row["mention_count"],
                    "group_confidence": row["group_confidence"],
                }
                for row in entity_rows[:50]
            ],
        }
        _write_json(summary_path, summary)

        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="entity_extraction",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": generated_at,
                "entities_parquet_path": str(entities_parquet_path),
                "entity_groups_path": str(entity_groups_path),
                "resolution_candidates_path": str(resolution_candidates_path),
                "summary_path": str(summary_path),
                "entity_rows": metrics["entity_rows"],
                "group_count": metrics["group_count"],
                "review_candidate_rows": metrics["review_candidate_rows"],
                "auto_merge_policy": AUTO_MERGE_POLICY,
            },
        )
        self.session.commit()
        return TelegramEntityExtractionResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            entities_parquet_path=entities_parquet_path,
            entity_groups_path=entity_groups_path,
            resolution_candidates_path=resolution_candidates_path,
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
            raise ValueError("entity extraction requires a succeeded raw export run")
        return dict(row)


def _candidate_mentions(row: dict[str, Any]) -> list[dict[str, Any]]:
    tokens = _json_list(row.get("tokens_json"))
    lemmas = _json_list(row.get("lemmas_json"))
    pos_tags = _json_list(row.get("pos_tags_json"))
    if not (len(tokens) == len(lemmas) == len(pos_tags)):
        return []

    mentions: list[dict[str, Any]] = []
    for index, pos in enumerate(pos_tags):
        if pos in SINGLE_POS:
            mentions.extend(_build_mention(row, tokens, lemmas, pos_tags, index, index + 1))

        if index + 1 < len(pos_tags) and tuple(pos_tags[index : index + 2]) in TWO_TOKEN_PATTERNS:
            mentions.extend(_build_mention(row, tokens, lemmas, pos_tags, index, index + 2))

        if pos == "PROPN":
            end = index + 1
            while end < len(pos_tags) and pos_tags[end] == "PROPN":
                end += 1
            if end - index > 1:
                mentions.extend(_build_mention(row, tokens, lemmas, pos_tags, index, end))
    return mentions


def _build_mention(
    row: dict[str, Any],
    tokens: list[str],
    lemmas: list[str],
    pos_tags: list[str],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    lemma_items = [_normalize_term_item(lemma) for lemma in lemmas[start:end]]
    token_items = [_normalize_term_item(token) for token in tokens[start:end]]
    normalized_text = _normalize_phrase(" ".join(lemma_items))
    canonical_text = _normalize_phrase(" ".join(token_items))
    pos_pattern = pos_tags[start:end]
    if not _is_valid_entity(normalized_text):
        return []
    return [
        {
            "normalized_text": normalized_text,
            "canonical_text": canonical_text or normalized_text,
            "pos_pattern": pos_pattern,
            "source_ref": _source_ref(row),
            "example_context": _truncate(str(row.get("clean_text") or row.get("raw_text") or ""), 260),
            "entity_type": str(row.get("entity_type") or ""),
            "telegram_message_id": int(row.get("telegram_message_id") or 0),
        }
    ]


def _aggregate_entities(mentions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for mention in mentions:
        buckets[
            (
                str(mention["normalized_text"]),
                _json_string(mention["pos_pattern"]),
            )
        ].append(mention)

    rows: list[dict[str, Any]] = []
    for (normalized_text, pos_pattern_json), bucket in sorted(buckets.items()):
        pos_pattern = json.loads(pos_pattern_json)
        source_refs = sorted({str(item["source_ref"]) for item in bucket if item["source_ref"]})
        examples = _unique_limited(str(item["example_context"]) for item in bucket)
        entity_types = Counter(str(item["entity_type"]) for item in bucket if item["entity_type"])
        canonical_counter = Counter(str(item["canonical_text"]) for item in bucket)
        canonical_text = canonical_counter.most_common(1)[0][0]
        group_id = _stable_id("entity-group", normalized_text)
        rows.append(
            {
                "entity_id": _stable_id("entity", normalized_text, pos_pattern_json),
                "group_id": group_id,
                "canonical_text": canonical_text,
                "normalized_text": normalized_text,
                "lemma_text": normalized_text,
                "pos_pattern_json": _json_string(pos_pattern),
                "mention_count": len(bucket),
                "source_count": len(source_refs),
                "source_refs_json": _json_string(source_refs),
                "example_contexts_json": _json_string(examples),
                "entity_type_counts_json": _json_string(dict(sorted(entity_types.items()))),
                "group_confidence": "high",
                "group_method": "exact",
            }
        )
    return rows


def _groups_payload(entity_rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entity_rows:
        grouped[str(row["group_id"])].append(row)

    groups: list[dict[str, Any]] = []
    for group_id, rows in sorted(grouped.items()):
        source_refs = sorted(
            {
                source_ref
                for row in rows
                for source_ref in _json_list(row["source_refs_json"])
            }
        )
        examples = _unique_limited(
            example
            for row in rows
            for example in _json_list(row["example_contexts_json"])
        )
        pos_patterns = [json.loads(row["pos_pattern_json"]) for row in rows]
        canonical_counter = Counter(str(row["canonical_text"]) for row in rows)
        normalized_text = str(rows[0]["normalized_text"])
        groups.append(
            {
                "group_id": group_id,
                "normalized_text": normalized_text,
                "canonical_text": canonical_counter.most_common(1)[0][0],
                "confidence": "high",
                "method": "exact",
                "auto_merge_allowed": True,
                "entity_ids": [str(row["entity_id"]) for row in rows],
                "mention_count": sum(int(row["mention_count"]) for row in rows),
                "source_refs": source_refs,
                "examples": examples,
                "pos_patterns": pos_patterns,
            }
        )

    return {
        "stage": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "auto_merge_policy": AUTO_MERGE_POLICY,
        "groups": groups,
    }


def _resolution_candidates(groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    groups_by_translit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups_by_prefix_length: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        normalized = str(group["normalized_text"])
        groups_by_translit[_translit(normalized)].append(group)
        prefix = _fuzzy_prefix(normalized)
        if prefix:
            groups_by_prefix_length[(prefix, len(normalized))].append(group)

    for bucket in groups_by_translit.values():
        _append_candidate_pairs(candidates, seen_pairs, bucket, method_hint="translit")
        if len(candidates) >= MAX_REVIEW_CANDIDATES:
            return candidates[:MAX_REVIEW_CANDIDATES]

    for left in groups:
        normalized = str(left["normalized_text"])
        prefix = _fuzzy_prefix(normalized)
        if not prefix:
            continue
        for length in range(len(normalized) - 2, len(normalized) + 3):
            if length <= 0:
                continue
            bucket = groups_by_prefix_length.get((prefix, length), [])
            _append_left_candidate_pairs(candidates, seen_pairs, left, bucket)
            if len(candidates) >= MAX_REVIEW_CANDIDATES:
                return candidates[:MAX_REVIEW_CANDIDATES]
    return candidates


def _append_left_candidate_pairs(
    candidates: list[dict[str, str]],
    seen_pairs: set[tuple[str, str]],
    left: dict[str, Any],
    bucket: list[dict[str, Any]],
) -> None:
    for right in bucket:
        if left["group_id"] == right["group_id"]:
            continue
        pair = tuple(sorted([str(left["group_id"]), str(right["group_id"])]))
        if pair in seen_pairs:
            continue
        method, score = _candidate_similarity(
            str(left["normalized_text"]),
            str(right["normalized_text"]),
        )
        if method is None:
            continue
        seen_pairs.add(pair)
        candidates.append(_review_candidate_row(left, right, method=method, score=score))
        if len(candidates) >= MAX_REVIEW_CANDIDATES:
            return


def _append_candidate_pairs(
    candidates: list[dict[str, str]],
    seen_pairs: set[tuple[str, str]],
    groups: list[dict[str, Any]],
    *,
    method_hint: str | None = None,
) -> None:
    for index, left in enumerate(groups):
        for right in groups[index + 1 :]:
            pair = tuple(sorted([str(left["group_id"]), str(right["group_id"])]))
            if pair in seen_pairs:
                continue
            method, score = _candidate_similarity(
                str(left["normalized_text"]),
                str(right["normalized_text"]),
                method_hint=method_hint,
            )
            if method is None:
                continue
            seen_pairs.add(pair)
            candidates.append(_review_candidate_row(left, right, method=method, score=score))
            if len(candidates) >= MAX_REVIEW_CANDIDATES:
                return


def _review_candidate_row(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    method: str,
    score: float,
) -> dict[str, str]:
    return {
        "group_id": f"{left['group_id']}::{right['group_id']}",
        "candidate_1": str(left["normalized_text"]),
        "candidate_2": str(right["normalized_text"]),
        "similarity_score": f"{score:.3f}",
        "method": method,
        "pos_pattern": _json_string(
            {
                "candidate_1": left["pos_patterns"],
                "candidate_2": right["pos_patterns"],
            }
        ),
        "example_context": _truncate(
            " | ".join(
                [
                    *(str(item) for item in left.get("examples", [])[:1]),
                    *(str(item) for item in right.get("examples", [])[:1]),
                ]
            ),
            500,
        ),
        "action_status": "pending_review",
    }


def _candidate_similarity(
    left: str,
    right: str,
    *,
    method_hint: str | None = None,
) -> tuple[str | None, float]:
    if left == right:
        return None, 1.0
    if _translit(left) == _translit(right):
        return "translit", 1.0
    if method_hint == "translit":
        return None, 0.0
    if abs(len(left) - len(right)) > 2:
        return None, 0.0
    if _fuzzy_prefix(left) != _fuzzy_prefix(right):
        return None, 0.0
    distance = _damerau_levenshtein(left, right)
    if distance <= 2:
        return "fuzzy", 1.0 - (distance / max(len(left), len(right), 1))
    return None, 0.0


def _metrics(
    feature_rows: list[dict[str, Any]],
    entity_rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    review_candidates: list[dict[str, str]],
) -> dict[str, Any]:
    patterns = Counter(
        " ".join(json.loads(str(row["pos_pattern_json"])))
        for row in entity_rows
    )
    return {
        "feature_rows": len(feature_rows),
        "entity_rows": len(entity_rows),
        "group_count": len(groups),
        "review_candidate_rows": len(review_candidates),
        "auto_merged_group_count": len(groups),
        "pos_pattern_counts": dict(sorted(patterns.items())),
    }


def _features_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    feature_enrichment = metadata.get("feature_enrichment")
    if not isinstance(feature_enrichment, dict):
        raise ValueError("entity extraction requires Stage 3 feature_enrichment metadata")
    path_value = feature_enrichment.get("features_parquet_path")
    if not path_value:
        raise ValueError("entity extraction requires feature_enrichment.features_parquet_path")
    return _resolve_path(path_value)


def _write_entities_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
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


def _write_resolution_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _source_ref(row: dict[str, Any]) -> str:
    message_url = str(row.get("message_url") or "")
    if message_url:
        return message_url
    source_url = str(row.get("source_url") or "")
    if source_url:
        return source_url
    return f"telegram_message:{row.get('telegram_message_id') or 0}"


def _is_valid_entity(value: str) -> bool:
    if not value or not LETTER_RE.search(value):
        return False
    parts = value.split()
    if all(part in STOP_LEMMAS for part in parts):
        return False
    return len(value.replace(" ", "")) >= 3


def _normalize_phrase(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip().casefold()


def _normalize_term_item(value: str) -> str:
    return PUNCT_RE.sub("", str(value or "")).casefold()


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


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("\u241f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _unique_limited(values: Any, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _translit(value: str) -> str:
    return "".join(CYRILLIC_TRANSLIT.get(char, char) for char in value.casefold())


def _fuzzy_prefix(value: str) -> str:
    compact = value.replace(" ", "")
    if len(compact) < 4:
        return ""
    return compact[:2]


def _damerau_levenshtein(left: str, right: str) -> int:
    previous_previous: list[int] | None = None
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            cost = min(insert_cost, delete_cost, replace_cost)
            if (
                previous_previous is not None
                and left_index > 1
                and right_index > 1
                and left_char == right[right_index - 2]
                and left[left_index - 2] == right_char
            ):
                cost = min(cost, previous_previous[right_index - 2] + 1)
            current.append(int(cost))
        previous_previous, previous = previous, current
    return previous[-1]


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
