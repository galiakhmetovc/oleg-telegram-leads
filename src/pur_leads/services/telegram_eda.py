"""Telegram raw export EDA and data-quality summary."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table

STAGE_NAME = "telegram_eda"
STAGE_VERSION = "1"

URL_RE = re.compile(r"(?:https?://|t\.me/|telegram\.me/)[^\s<>()\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


@dataclass(frozen=True)
class TelegramEdaSummary:
    raw_export_run_id: str
    report_path: Path
    recommended_decision: str
    metrics: dict[str, Any]
    warnings: list[dict[str, str]]


class TelegramEdaService:
    """Build Stage 1 sanity-gate reports for Telegram raw export runs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def write_summary(self, raw_export_run_id: str) -> TelegramEdaSummary:
        run = self._require_run(raw_export_run_id)
        messages_path = Path(str(run["messages_parquet_path"]))
        if not messages_path.is_absolute():
            messages_path = Path(".") / messages_path
        generated_at = utc_now()
        metrics, anomalies = _analyze_parquet(messages_path, generated_at)
        warnings = _warnings(metrics, anomalies)
        decision = _recommended_decision(metrics, warnings)
        report_path = Path(str(run["output_dir"])) / "reports" / "eda_summary.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "generated_at": generated_at.isoformat(),
            "input": {
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": run["monitored_source_id"],
                "source_ref": run["source_ref"],
                "source_kind": run["source_kind"],
                "username": run["username"],
                "messages_parquet_path": str(messages_path),
            },
            "metrics": metrics,
            "anomalies": anomalies,
            "warnings": warnings,
            "recommended_decision": decision,
            "human_decision": {
                "status": "pending",
                "allowed_values": ["go", "go_with_warnings", "pause_source", "no_go"],
            },
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        metadata = dict(run["metadata_json"] or {})
        metadata["eda"] = {
            "stage": STAGE_NAME,
            "stage_version": STAGE_VERSION,
            "report_path": str(report_path),
            "generated_at": generated_at.isoformat(),
            "recommended_decision": decision,
            "warning_codes": [warning["code"] for warning in warnings],
            "total_messages": metrics["total_messages"],
        }
        self.session.execute(
            update(telegram_raw_export_runs_table)
            .where(telegram_raw_export_runs_table.c.id == raw_export_run_id)
            .values(metadata_json=metadata)
        )
        self.session.commit()
        return TelegramEdaSummary(
            raw_export_run_id=raw_export_run_id,
            report_path=report_path,
            recommended_decision=decision,
            metrics=metrics,
            warnings=warnings,
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
            raise ValueError("EDA requires a succeeded raw export run")
        return dict(row)


def _analyze_rows(
    rows: list[dict[str, Any]],
    generated_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    accumulator = _EdaAccumulator(generated_at)
    for row in rows:
        accumulator.add(row)
    return accumulator.finish()


def _analyze_parquet(
    messages_path: Path,
    generated_at: datetime,
    *,
    batch_size: int = 5000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    accumulator = _EdaAccumulator(generated_at)
    parquet_file = pq.ParquetFile(messages_path)
    for batch in parquet_file.iter_batches(batch_size=batch_size):
        for row in batch.to_pylist():
            accumulator.add(row)
    return accumulator.finish()


class _EdaAccumulator:
    def __init__(self, generated_at: datetime) -> None:
        self.generated_at = generated_at
        self.total = 0
        self.id_counts: Counter[int] = Counter()
        self.authors: set[str] = set()
        self.valid_date_min: datetime | None = None
        self.valid_date_max: datetime | None = None
        self.invalid_dates_count = 0
        self.has_text_count = 0
        self.has_url_count = 0
        self.has_reactions_count = 0
        self.pii_count = 0
        self.media_count = 0
        self.document_count = 0
        self.reply_count = 0
        self.service_count = 0
        self.future_dates_count = 0
        self.future_date_message_ids: list[int | None] = []
        self.message_type_distribution: Counter[str] = Counter()
        self.media_type_distribution: Counter[str] = Counter()

    def add(self, row: dict[str, Any]) -> None:
        self.total += 1
        message_id = _optional_message_id(row.get("telegram_message_id"))
        if message_id is not None:
            self.id_counts[message_id] += 1
        author = row.get("sender_id") or row.get("sender_display")
        if author:
            self.authors.add(str(author))
        date_value = _parse_datetime(row.get("date"))
        if date_value is None:
            self.invalid_dates_count += 1
        else:
            self.valid_date_min = (
                date_value
                if self.valid_date_min is None
                else min(self.valid_date_min, date_value)
            )
            self.valid_date_max = (
                date_value
                if self.valid_date_max is None
                else max(self.valid_date_max, date_value)
            )
            if date_value > self.generated_at:
                self.future_dates_count += 1
                if len(self.future_date_message_ids) < 100:
                    self.future_date_message_ids.append(message_id)
        text = _combined_text(row)
        raw_message = _loads_json(row.get("raw_message_json"))
        if text.strip():
            self.has_text_count += 1
        if URL_RE.search(text):
            self.has_url_count += 1
        if _has_reactions(raw_message):
            self.has_reactions_count += 1
        if _has_pii(text):
            self.pii_count += 1
        if row.get("media_type"):
            self.media_count += 1
            self.media_type_distribution[str(row["media_type"])] += 1
        if _is_document_message(row):
            self.document_count += 1
        if row.get("reply_to_message_id") is not None:
            self.reply_count += 1
        if _is_service_message(raw_message):
            self.service_count += 1
        self.message_type_distribution[_message_type(row, raw_message)] += 1

    def finish(self) -> tuple[dict[str, Any], dict[str, Any]]:
        duplicate_ids = sorted(
            message_id for message_id, count in self.id_counts.items() if count > 1
        )
        duplicate_count = sum(count - 1 for count in self.id_counts.values() if count > 1)
        metrics = {
            "total_messages": self.total,
            "unique_authors": len(self.authors),
            "date_min": self.valid_date_min.isoformat() if self.valid_date_min else None,
            "date_max": self.valid_date_max.isoformat() if self.valid_date_max else None,
            "has_text_ratio": _ratio(self.has_text_count, self.total),
            "has_url_ratio": _ratio(self.has_url_count, self.total),
            "has_reactions_ratio": _ratio(self.has_reactions_count, self.total),
            "pii_ratio": _ratio(self.pii_count, self.total),
            "media_ratio": _ratio(self.media_count, self.total),
            "document_ratio": _ratio(self.document_count, self.total),
            "reply_ratio": _ratio(self.reply_count, self.total),
            "service_message_ratio": _ratio(self.service_count, self.total),
            "message_type_distribution": dict(sorted(self.message_type_distribution.items())),
            "media_type_distribution": dict(sorted(self.media_type_distribution.items())),
        }
        anomalies = {
            "duplicate_message_count": duplicate_count,
            "duplicate_message_ids": duplicate_ids[:100],
            "future_dates_count": self.future_dates_count,
            "future_date_message_ids": self.future_date_message_ids,
            "invalid_dates_count": self.invalid_dates_count,
        }
        return metrics, anomalies


def _warnings(metrics: dict[str, Any], anomalies: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if metrics["total_messages"] == 0:
        warnings.append(
            {
                "code": "empty_export",
                "severity": "error",
                "message": "Raw export contains no messages.",
            }
        )
    if metrics["has_text_ratio"] < 0.1:
        warnings.append(
            {
                "code": "low_text_density",
                "severity": "warning",
                "message": "has_text_ratio < 0.1: low knowledge density.",
            }
        )
    if metrics["unique_authors"] == 1:
        warnings.append(
            {
                "code": "single_author_not_dialogue",
                "severity": "warning",
                "message": "unique_authors == 1: source is not a dialogue; this is expected for catalog channels.",
            }
        )
    if anomalies["duplicate_message_count"] > 0:
        warnings.append(
            {
                "code": "duplicate_message_ids",
                "severity": "warning",
                "message": "Duplicate Telegram message IDs found in the raw export.",
            }
        )
    if anomalies["future_dates_count"] > 0:
        warnings.append(
            {
                "code": "future_dates",
                "severity": "warning",
                "message": "Messages with dates in the future were found.",
            }
        )
    if anomalies["invalid_dates_count"] > 0:
        warnings.append(
            {
                "code": "invalid_dates",
                "severity": "warning",
                "message": "Messages with invalid dates were found.",
            }
        )
    if metrics["pii_ratio"] > 0:
        warnings.append(
            {
                "code": "pii_detected",
                "severity": "warning",
                "message": "Potential phone numbers or emails were found in message text.",
            }
        )
    return warnings


def _recommended_decision(metrics: dict[str, Any], warnings: list[dict[str, str]]) -> str:
    if metrics["total_messages"] == 0:
        return "no_go"
    if any(warning["severity"] == "error" for warning in warnings):
        return "no_go"
    if warnings:
        return "go_with_warnings"
    return "go"


def _combined_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(value)
        for value in (row.get("text_plain"), row.get("caption"))
        if value is not None and str(value).strip()
    )


def _has_pii(value: str) -> bool:
    return bool(EMAIL_RE.search(value) or PHONE_RE.search(value))


def _has_reactions(raw_message: dict[str, Any]) -> bool:
    desktop_reactions = (raw_message.get("raw_tdesktop_json") or {}).get("reactions")
    if desktop_reactions:
        return True
    reactions = (raw_message.get("raw_telethon_json") or {}).get("telethon", {}).get("reactions")
    if not isinstance(reactions, dict):
        return False
    return any(bool(reactions.get(key)) for key in ("results", "recent_reactions", "top_reactors"))


def _is_service_message(raw_message: dict[str, Any]) -> bool:
    desktop_type = (raw_message.get("raw_tdesktop_json") or {}).get("type")
    if desktop_type is not None and desktop_type != "message":
        return True
    action = (raw_message.get("raw_telethon_json") or {}).get("telethon", {}).get("action")
    return action is not None


def _message_type(row: dict[str, Any], raw_message: dict[str, Any]) -> str:
    if _is_service_message(raw_message):
        return "service"
    if row.get("media_type"):
        return "media"
    if _combined_text(row).strip():
        return "text"
    return "other"


def _is_document_message(row: dict[str, Any]) -> bool:
    media_type = str(row.get("media_type") or "")
    mime_type = str(row.get("mime_type") or "")
    return media_type == "document" or bool(mime_type and not mime_type.startswith("image/"))


def _ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return count / total


def _optional_message_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
