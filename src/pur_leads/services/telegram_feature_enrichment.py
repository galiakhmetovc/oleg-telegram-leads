"""Telegram Stage 3 feature enrichment over normalized messages and artifacts."""

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

STAGE_NAME = "telegram_feature_enrichment"
STAGE_VERSION = "1"

URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
USERNAME_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,32}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
PRICE_RE = re.compile(
    r"(?P<amount>\d[\d\s]{2,})(?:[,.]\d{1,2})?\s*(?P<currency>руб(?:\.|лей|ля|ль)?|р\.?|₽)",
    re.IGNORECASE,
)

QUESTION_MARKERS = {
    "сколько",
    "как",
    "какой",
    "какая",
    "какие",
    "где",
    "когда",
    "почему",
    "зачем",
    "можно",
    "нужно",
}
SOLUTION_MARKERS = {"установка", "настройка", "подключение", "управление", "мониторинг"}
OFFER_MARKERS = {"стоимость", "цена", "предлагаем", "комплект", "решение", "под ключ"}
FEATURE_PROFILE_STATUS = "not_configured"
FEATURE_PROFILE_ID = ""
FEATURE_PROFILE_VERSION = ""


@dataclass(frozen=True)
class TelegramFeatureEnrichmentResult:
    raw_export_run_id: str
    output_dir: Path
    features_parquet_path: Path
    summary_path: Path
    metrics: dict[str, Any]


class TelegramFeatureEnrichmentService:
    """Build deterministic per-row features before AI/catalog extraction."""

    def __init__(
        self,
        session: Session,
        *,
        processed_root: Path | str = "./data/processed",
    ) -> None:
        self.session = session
        self.processed_root = Path(processed_root)

    def write_features(self, raw_export_run_id: str) -> TelegramFeatureEnrichmentResult:
        run = self._require_run(raw_export_run_id)
        message_rows = pq.read_table(_texts_path_from_metadata(run)).to_pylist()
        artifact_path = _artifact_texts_path_from_metadata(run)
        artifact_rows = (
            pq.read_table(artifact_path).to_pylist()
            if artifact_path is not None and artifact_path.exists()
            else []
        )

        output_dir = (
            self.processed_root
            / "telegram_features"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        features_parquet_path = output_dir / "features.parquet"
        summary_path = output_dir / "feature_enrichment_summary.json"

        feature_rows = [
            _feature_row(row, entity_type="telegram_message")
            for row in message_rows
            if row.get("has_text")
        ]
        feature_rows.extend(
            _feature_row(row, entity_type="telegram_artifact")
            for row in artifact_rows
            if row.get("has_text")
        )
        _write_features_parquet(features_parquet_path, feature_rows)
        metrics = _metrics(feature_rows)
        summary = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": utc_now().isoformat(),
            "input": {
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "message_text_rows": len(message_rows),
                "artifact_text_rows": len(artifact_rows),
            },
            "outputs": {
                "features_parquet_path": str(features_parquet_path),
                "summary_path": str(summary_path),
            },
            "metrics": metrics,
            "feature_profiles": {
                "supported": True,
                "applied": False,
                "status": FEATURE_PROFILE_STATUS,
                "active_profile_id": None,
                "active_profile_version": None,
            },
            "sample_rows": [
                {
                    "entity_type": row["entity_type"],
                    "telegram_message_id": row["telegram_message_id"],
                    "artifact_kind": row["artifact_kind"],
                    "feature_profile_applied": row["feature_profile_applied"],
                    "clean_text": _truncate(str(row["clean_text"] or ""), 300),
                }
                for row in feature_rows[:50]
            ],
        }
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="feature_enrichment",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": summary["generated_at"],
                "features_parquet_path": str(features_parquet_path),
                "summary_path": str(summary_path),
                "total_rows": metrics["total_rows"],
                "rows_with_price": metrics["rows_with_price"],
                "feature_profile_status": FEATURE_PROFILE_STATUS,
                "feature_profile_id": None,
                "feature_profile_version": None,
                "feature_profiles_applied": False,
            },
        )
        self.session.commit()
        return TelegramFeatureEnrichmentResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            features_parquet_path=features_parquet_path,
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
            raise ValueError("feature enrichment requires a succeeded raw export run")
        return dict(row)


def _feature_row(row: dict[str, Any], *, entity_type: str) -> dict[str, Any]:
    raw_text = str(row.get("raw_text") or "")
    clean_text = str(row.get("clean_text") or "")
    tokens = _json_list(row.get("tokens_json"))
    lemmas = _json_list(row.get("lemmas_json"))
    pos_tags = _json_list(row.get("pos_tags_json"))
    prices = _price_values(raw_text)
    urls = [_normalize_url(match.group(0)) for match in URL_RE.finditer(raw_text)]
    phones = [_normalize_phone(match.group(0)) for match in PHONE_RE.finditer(raw_text)]
    emails = [match.group(0) for match in EMAIL_RE.finditer(raw_text)]
    usernames = [match.group(0) for match in USERNAME_RE.finditer(raw_text)]
    noun_count = sum(1 for pos in pos_tags if pos in {"NOUN", "PROPN"})
    token_count = int(row.get("token_count") or len(tokens))
    artifact_id = str(row.get("artifact_id") or "")
    artifact_kind = str(row.get("artifact_kind") or "")
    chunk_index = int(row.get("chunk_index") or 0)
    message_id = int(row.get("telegram_message_id") or 0)
    feature_id = (
        f"{entity_type}:{message_id}:{artifact_id}:{chunk_index}"
        if entity_type == "telegram_artifact"
        else f"{entity_type}:{message_id}:{row.get('row_index') or 0}"
    )
    return {
        "feature_id": feature_id,
        "entity_type": entity_type,
        "export_run_id": str(row.get("export_run_id") or ""),
        "monitored_source_id": str(row.get("monitored_source_id") or ""),
        "telegram_message_id": message_id,
        "row_index": int(row.get("row_index") or 0),
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "chunk_index": chunk_index,
        "source_url": str(row.get("source_url") or ""),
        "final_url": str(row.get("final_url") or ""),
        "title": str(row.get("title") or ""),
        "file_name": str(row.get("file_name") or ""),
        "date": str(row.get("date") or ""),
        "message_url": str(row.get("message_url") or ""),
        "raw_text": raw_text,
        "clean_text": clean_text,
        "normalization_lang": str(row.get("normalization_lang") or "unknown"),
        "tokens_json": _json_string(tokens),
        "lemmas_json": _json_string(lemmas),
        "pos_tags_json": _json_string(pos_tags),
        "feature_profile_id": FEATURE_PROFILE_ID,
        "feature_profile_version": FEATURE_PROFILE_VERSION,
        "feature_profile_applied": False,
        "token_count": token_count,
        "has_text": bool(row.get("has_text")),
        "is_question_like": _is_question_like(raw_text, lemmas),
        "is_solution_like": _has_any(clean_text, SOLUTION_MARKERS),
        "is_offer_like": _has_any(clean_text, OFFER_MARKERS) or bool(prices),
        "has_price": bool(prices),
        "price_values_json": _json_string(prices),
        "has_phone": bool(phones),
        "phone_values_json": _json_string(phones),
        "has_email": bool(emails),
        "email_values_json": _json_string(emails),
        "has_url": bool(urls),
        "urls_json": _json_string(sorted(set(urls))),
        "has_telegram_username": bool(usernames),
        "telegram_usernames_json": _json_string(sorted(set(usernames))),
        "has_noun_term": noun_count > 0,
        "technical_language_score": round(noun_count / max(1, token_count), 6),
        "text_quality": _text_quality(clean_text, token_count),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    text_quality: Counter[str] = Counter()
    entity_types: Counter[str] = Counter()
    for row in rows:
        text_quality[str(row["text_quality"])] += 1
        entity_types[str(row["entity_type"])] += 1
    return {
        "total_rows": len(rows),
        "rows_with_price": sum(1 for row in rows if row["has_price"]),
        "rows_with_phone": sum(1 for row in rows if row["has_phone"]),
        "rows_with_url": sum(1 for row in rows if row["has_url"]),
        "question_like_rows": sum(1 for row in rows if row["is_question_like"]),
        "offer_like_rows": sum(1 for row in rows if row["is_offer_like"]),
        "solution_like_rows": sum(1 for row in rows if row["is_solution_like"]),
        "feature_profile_status": FEATURE_PROFILE_STATUS,
        "feature_profiles_applied": False,
        "text_quality_counts": dict(sorted(text_quality.items())),
        "entity_type_counts": dict(sorted(entity_types.items())),
    }


def _is_question_like(raw_text: str, lemmas: list[str]) -> bool:
    if "?" in raw_text:
        return True
    return bool(QUESTION_MARKERS.intersection(set(lemmas)))


def _has_any(clean_text: str, markers: set[str]) -> bool:
    return any(marker in clean_text for marker in markers)


def _price_values(raw_text: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for match in PRICE_RE.finditer(raw_text):
        amount = int(re.sub(r"\s+", "", match.group("amount")))
        values.append({"amount": amount, "currency": "RUB", "raw": match.group(0)})
    return values


def _normalize_phone(value: str) -> str:
    return re.sub(r"\D+", "", value)


def _normalize_url(value: str) -> str:
    return value.rstrip(".,;:!?)]}\"'")


def _text_quality(clean_text: str, token_count: int) -> str:
    if not clean_text.strip():
        return "empty"
    if token_count < 4:
        return "short"
    if token_count > 300:
        return "long"
    return "normal"


def _write_features_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    schema = pa.schema(
        [
            ("feature_id", pa.string()),
            ("entity_type", pa.string()),
            ("export_run_id", pa.string()),
            ("monitored_source_id", pa.string()),
            ("telegram_message_id", pa.int64()),
            ("row_index", pa.int64()),
            ("artifact_id", pa.string()),
            ("artifact_kind", pa.string()),
            ("chunk_index", pa.int64()),
            ("source_url", pa.string()),
            ("final_url", pa.string()),
            ("title", pa.string()),
            ("file_name", pa.string()),
            ("date", pa.string()),
            ("message_url", pa.string()),
            ("raw_text", pa.string()),
            ("clean_text", pa.string()),
            ("normalization_lang", pa.string()),
            ("tokens_json", pa.string()),
            ("lemmas_json", pa.string()),
            ("pos_tags_json", pa.string()),
            ("feature_profile_id", pa.string()),
            ("feature_profile_version", pa.string()),
            ("feature_profile_applied", pa.bool_()),
            ("token_count", pa.int64()),
            ("has_text", pa.bool_()),
            ("is_question_like", pa.bool_()),
            ("is_solution_like", pa.bool_()),
            ("is_offer_like", pa.bool_()),
            ("has_price", pa.bool_()),
            ("price_values_json", pa.string()),
            ("has_phone", pa.bool_()),
            ("phone_values_json", pa.string()),
            ("has_email", pa.bool_()),
            ("email_values_json", pa.string()),
            ("has_url", pa.bool_()),
            ("urls_json", pa.string()),
            ("has_telegram_username", pa.bool_()),
            ("telegram_usernames_json", pa.string()),
            ("has_noun_term", pa.bool_()),
            ("technical_language_score", pa.float64()),
            ("text_quality", pa.string()),
        ]
    )
    table = (
        pa.Table.from_pylist(rows, schema=schema)
        if rows
        else pa.Table.from_pylist([], schema=schema)
    )
    pq.write_table(table, path, compression="zstd")


def _texts_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    text_normalization = metadata.get("text_normalization")
    if not isinstance(text_normalization, dict):
        raise ValueError("feature enrichment requires Stage 2 text_normalization metadata")
    path_value = text_normalization.get("texts_parquet_path")
    if not path_value:
        raise ValueError("feature enrichment requires text_normalization.texts_parquet_path")
    return _resolve_path(path_value)


def _artifact_texts_path_from_metadata(run: dict[str, Any]) -> Path | None:
    metadata = dict(run["metadata_json"] or {})
    artifact_texts = metadata.get("artifact_texts")
    if not isinstance(artifact_texts, dict):
        return None
    path_value = artifact_texts.get("texts_parquet_path")
    return _resolve_path(path_value) if path_value else None


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
