"""Telegram Stage 4 aggregate statistics over enriched feature rows."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_run_metadata import merge_raw_export_run_metadata

STAGE_NAME = "telegram_aggregated_stats"
STAGE_VERSION = "1"


@dataclass(frozen=True)
class TelegramAggregatedStatsResult:
    raw_export_run_id: str
    output_dir: Path
    summary_path: Path
    ngrams_path: Path
    entity_candidates_path: Path
    url_summary_path: Path
    source_quality_path: Path
    metrics: dict[str, Any]


class TelegramAggregatedStatsService:
    """Build deterministic source-level stats after Stage 3 features."""

    def __init__(
        self,
        session: Session,
        *,
        enriched_root: Path | str = "./data/enriched",
    ) -> None:
        self.session = session
        self.enriched_root = Path(enriched_root)

    def write_stats(self, raw_export_run_id: str) -> TelegramAggregatedStatsResult:
        run = self._require_run(raw_export_run_id)
        features_path = _features_path_from_metadata(run)
        rows = pq.read_table(features_path).to_pylist()

        output_dir = (
            self.enriched_root
            / "telegram_stats"
            / f"source_id={run['monitored_source_id']}"
            / f"run_id={raw_export_run_id}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "aggregated_stats.json"
        ngrams_path = output_dir / "ngrams.json"
        entity_candidates_path = output_dir / "entity_candidates.json"
        url_summary_path = output_dir / "url_summary.json"
        source_quality_path = output_dir / "source_quality.json"

        metrics = _metrics(rows)
        ngrams = _ngrams_payload(rows)
        entities = _entity_candidates_payload(rows)
        urls = _url_summary_payload(rows)
        source_quality = _source_quality_payload(rows)
        generated_at = utc_now().isoformat()
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
                "summary_path": str(summary_path),
                "ngrams_path": str(ngrams_path),
                "entity_candidates_path": str(entity_candidates_path),
                "url_summary_path": str(url_summary_path),
                "source_quality_path": str(source_quality_path),
            },
            "metrics": metrics,
            "top_terms": ngrams["top_lemmas"][:20],
        }
        _write_json(summary_path, summary)
        _write_json(ngrams_path, ngrams)
        _write_json(entity_candidates_path, entities)
        _write_json(url_summary_path, urls)
        _write_json(source_quality_path, source_quality)

        merge_raw_export_run_metadata(
            self.session,
            raw_export_run_id,
            key="aggregated_stats",
            value={
                "stage": STAGE_NAME,
                "stage_version": STAGE_VERSION,
                "generated_at": generated_at,
                "summary_path": str(summary_path),
                "ngrams_path": str(ngrams_path),
                "entity_candidates_path": str(entity_candidates_path),
                "url_summary_path": str(url_summary_path),
                "source_quality_path": str(source_quality_path),
                "total_rows": metrics["total_rows"],
            },
        )
        self.session.commit()
        return TelegramAggregatedStatsResult(
            raw_export_run_id=raw_export_run_id,
            output_dir=output_dir,
            summary_path=summary_path,
            ngrams_path=ngrams_path,
            entity_candidates_path=entity_candidates_path,
            url_summary_path=url_summary_path,
            source_quality_path=source_quality_path,
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
            raise ValueError("aggregated stats requires a succeeded raw export run")
        return dict(row)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_rows": len(rows),
        "message_rows": sum(1 for row in rows if row.get("entity_type") == "telegram_message"),
        "artifact_rows": sum(1 for row in rows if row.get("entity_type") == "telegram_artifact"),
        "question_like_rows": sum(1 for row in rows if row.get("is_question_like")),
        "offer_like_rows": sum(1 for row in rows if row.get("is_offer_like")),
        "rows_with_price": sum(1 for row in rows if row.get("has_price")),
        "rows_with_phone": sum(1 for row in rows if row.get("has_phone")),
        "rows_with_url": sum(1 for row in rows if row.get("has_url")),
    }


def _ngrams_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lemmas: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    trigrams: Counter[str] = Counter()
    for row in rows:
        row_lemmas = [
            lemma
            for lemma in _json_list(row.get("lemmas_json"))
            if len(lemma) >= 3 and lemma not in {"url", "это", "как", "для"}
        ]
        lemmas.update(row_lemmas)
        bigrams.update(" ".join(pair) for pair in zip(row_lemmas, row_lemmas[1:], strict=False))
        trigrams.update(
            " ".join(items)
            for items in zip(row_lemmas, row_lemmas[1:], row_lemmas[2:], strict=False)
        )
    return {
        "top_lemmas": _counter_items(lemmas, 100),
        "top_bigrams": _counter_items(bigrams, 100),
        "top_trigrams": _counter_items(trigrams, 100),
    }


def _entity_candidates_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usernames: Counter[str] = Counter()
    for row in rows:
        usernames.update(_json_list(row.get("telegram_usernames_json")))
    return {
        "telegram_usernames": _counter_items(usernames, 100),
    }


def _url_summary_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    domains: Counter[str] = Counter()
    urls: Counter[str] = Counter()
    for row in rows:
        row_urls = set(_json_list(row.get("urls_json")))
        source_url = str(row.get("source_url") or "")
        if source_url:
            row_urls.add(source_url)
        for url in row_urls:
            urls[url] += 1
            domain = urlparse(url).netloc.casefold()
            if domain:
                domains[domain] += 1
    return {
        "domains": _counter_items(domains, 100),
        "urls": _counter_items(urls, 200),
    }


def _source_quality_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    entity_types = Counter(str(row.get("entity_type") or "") for row in rows)
    artifact_kinds = Counter(str(row.get("artifact_kind") or "") for row in rows if row.get("artifact_kind"))
    qualities = Counter(str(row.get("text_quality") or "") for row in rows)
    return {
        "entity_type_counts": dict(sorted(entity_types.items())),
        "artifact_kind_counts": dict(sorted(artifact_kinds.items())),
        "text_quality_counts": dict(sorted(qualities.items())),
        "average_technical_language_score": _average(
            float(row.get("technical_language_score") or 0.0) for row in rows
        ),
    }


def _features_path_from_metadata(run: dict[str, Any]) -> Path:
    metadata = dict(run["metadata_json"] or {})
    feature_enrichment = metadata.get("feature_enrichment")
    if not isinstance(feature_enrichment, dict):
        raise ValueError("aggregated stats requires Stage 3 feature_enrichment metadata")
    path_value = feature_enrichment.get("features_parquet_path")
    if not path_value:
        raise ValueError("aggregated stats requires feature_enrichment.features_parquet_path")
    return _resolve_path(path_value)


def _counter_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [
        {"term": term, "count": count}
        for term, count in counter.most_common(limit)
        if term
    ]


def _average(values: Any) -> float:
    materialized = list(values)
    if not materialized:
        return 0.0
    return round(sum(materialized) / len(materialized), 6)


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
