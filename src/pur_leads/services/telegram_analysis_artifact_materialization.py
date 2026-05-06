"""Materialize existing Telegram analysis artifacts into PostgreSQL."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.telegram_analysis_storage import (
    replace_document_features,
    replace_entity_candidates,
    replace_ranked_entity_candidates,
    replace_stage_outputs,
)
from pur_leads.services.telegram_prepared_documents import (
    replace_prepared_documents_from_batches,
)


class TelegramAnalysisArtifactMaterializationService:
    """Load already-produced parquet/json stage outputs into operational tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def materialize_all(self, *, force: bool = False) -> dict[str, Any]:
        rows = (
            self.session.execute(
                select(telegram_raw_export_runs_table)
                .where(telegram_raw_export_runs_table.c.status == "succeeded")
                .order_by(telegram_raw_export_runs_table.c.created_at)
            )
            .mappings()
            .all()
        )
        runs = [self.materialize_run(str(row["id"]), force=force) for row in rows]
        self.session.commit()
        return {
            "run_count": len(runs),
            "runs": runs,
            "totals": _totals(runs),
        }

    def materialize_run(self, raw_export_run_id: str, *, force: bool = False) -> dict[str, Any]:
        run = self._run(raw_export_run_id)
        metadata = dict(run["metadata_json"] or {})
        result: dict[str, Any] = {
            "raw_export_run_id": raw_export_run_id,
            "source_ref": run["source_ref"],
            "status": run["status"],
            "materialized": {},
            "skipped": [],
        }

        text_meta = _dict(metadata.get("text_normalization"))
        if text_meta:
            count = self._materialize_prepared_documents(
                text_meta.get("texts_parquet_path"),
                raw_export_run_id=raw_export_run_id,
                entity_type="telegram_message",
                run=run,
            )
            result["materialized"]["telegram_message_documents"] = count
            text_meta["postgres_rows"] = count
            metadata["text_normalization"] = text_meta

        artifact_meta = _dict(metadata.get("artifact_texts"))
        if artifact_meta:
            count = self._materialize_prepared_documents(
                artifact_meta.get("texts_parquet_path"),
                raw_export_run_id=raw_export_run_id,
                entity_type="telegram_artifact",
                run=run,
            )
            result["materialized"]["telegram_artifact_documents"] = count
            artifact_meta["postgres_rows"] = count
            metadata["artifact_texts"] = artifact_meta

        feature_meta = _dict(metadata.get("feature_enrichment"))
        if feature_meta:
            path = _path(feature_meta.get("features_parquet_path"))
            if path and path.exists():
                feature_rows = pq.read_table(path).to_pylist()
                count = replace_document_features(self.session, raw_export_run_id, feature_rows)
                result["materialized"]["feature_rows"] = count
                feature_meta["postgres_feature_rows"] = count
                metadata["feature_enrichment"] = feature_meta
                self._stage_output_from_paths(
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=str(run["monitored_source_id"]),
                    stage_key="feature_enrichment",
                    outputs={"summary": ("summary_json", feature_meta.get("summary_path"))},
                )
            else:
                result["skipped"].append("feature_enrichment: missing features_parquet_path")

        aggregate_meta = _dict(metadata.get("aggregated_stats"))
        if aggregate_meta:
            self._stage_output_from_paths(
                raw_export_run_id=raw_export_run_id,
                monitored_source_id=str(run["monitored_source_id"]),
                stage_key="aggregated_stats",
                outputs={
                    "summary": ("summary_json", aggregate_meta.get("summary_path")),
                    "ngrams": ("aggregate_json", aggregate_meta.get("ngrams_path")),
                    "entity_candidates": (
                        "aggregate_json",
                        aggregate_meta.get("entity_candidates_path"),
                    ),
                    "urls": ("aggregate_json", aggregate_meta.get("url_summary_path")),
                    "source_quality": ("aggregate_json", aggregate_meta.get("source_quality_path")),
                },
            )
            result["materialized"]["aggregated_outputs"] = True

        extraction_meta = _dict(metadata.get("entity_extraction"))
        if extraction_meta:
            path = _path(extraction_meta.get("entities_parquet_path"))
            if path and path.exists():
                rows = pq.read_table(path).to_pylist()
                count = replace_entity_candidates(
                    self.session,
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=str(run["monitored_source_id"]),
                    rows=rows,
                )
                result["materialized"]["entity_rows"] = count
                extraction_meta["postgres_entity_rows"] = count
                metadata["entity_extraction"] = extraction_meta
            self._stage_output_from_paths(
                raw_export_run_id=raw_export_run_id,
                monitored_source_id=str(run["monitored_source_id"]),
                stage_key="entity_extraction",
                outputs={
                    "summary": ("summary_json", extraction_meta.get("summary_path")),
                    "groups": ("entity_groups_json", extraction_meta.get("entity_groups_path")),
                    "resolution_candidates": (
                        "resolution_candidates",
                        extraction_meta.get("resolution_candidates_path"),
                    ),
                },
            )

        ranking_meta = _dict(metadata.get("entity_ranking"))
        if ranking_meta:
            path = _path(ranking_meta.get("ranked_entities_parquet_path"))
            if path and path.exists():
                rows = pq.read_table(path).to_pylist()
                count = replace_ranked_entity_candidates(
                    self.session,
                    raw_export_run_id=raw_export_run_id,
                    monitored_source_id=str(run["monitored_source_id"]),
                    rows=rows,
                )
                result["materialized"]["ranked_entity_rows"] = count
                ranking_meta["postgres_ranked_entity_rows"] = count
                metadata["entity_ranking"] = ranking_meta
            self._stage_output_from_paths(
                raw_export_run_id=raw_export_run_id,
                monitored_source_id=str(run["monitored_source_id"]),
                stage_key="entity_ranking",
                outputs={
                    "summary": ("summary_json", ranking_meta.get("summary_path")),
                    "ranked_entities": (
                        "ranked_entities_json",
                        ranking_meta.get("ranked_entities_json_path"),
                    ),
                    "noise_report": ("noise_report_json", ranking_meta.get("noise_report_path")),
                },
            )

        self.session.execute(
            telegram_raw_export_runs_table.update()
            .where(telegram_raw_export_runs_table.c.id == raw_export_run_id)
            .values(metadata_json=metadata)
        )
        if force:
            result["force"] = True
        return result

    def _run(self, raw_export_run_id: str) -> dict[str, Any]:
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
        return dict(row)

    def _materialize_prepared_documents(
        self,
        path_value: Any,
        *,
        raw_export_run_id: str,
        entity_type: str,
        run: dict[str, Any],
    ) -> int:
        path = _path(path_value)
        if path is None or not path.exists():
            return 0
        return replace_prepared_documents_from_batches(
            self.session,
            _parquet_batches_with_links(path, run),
            raw_export_run_id=raw_export_run_id,
            entity_type=entity_type,
        )

    def _stage_output_from_paths(
        self,
        *,
        raw_export_run_id: str,
        monitored_source_id: str,
        stage_key: str,
        outputs: dict[str, tuple[str, Any]],
    ) -> None:
        payloads: dict[str, dict[str, Any]] = {}
        for output_key, (output_kind, path_value) in outputs.items():
            path = _path(path_value)
            if path is None or not path.exists():
                continue
            payloads[output_key] = {
                "output_kind": output_kind,
                "payload_json": _read_payload(path),
                "artifact_path": str(path),
            }
        if payloads:
            replace_stage_outputs(
                self.session,
                raw_export_run_id=raw_export_run_id,
                monitored_source_id=monitored_source_id,
                stage_key=stage_key,
                outputs=payloads,
            )


def _parquet_batches_with_links(path: Path, run: dict[str, Any], batch_size: int = 5000) -> Iterable[list[dict[str, Any]]]:
    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(batch_size=batch_size):
        rows = batch.to_pylist()
        for row in rows:
            if not row.get("message_url"):
                row["message_url"] = _telegram_message_url(run, row.get("telegram_message_id"))
        yield rows


def _telegram_message_url(run: dict[str, Any], telegram_message_id: Any) -> str:
    if telegram_message_id is None:
        return ""
    message_id = str(telegram_message_id)
    username = str(run.get("username") or "").strip().lstrip("@")
    if username:
        return f"https://t.me/{username}/{message_id}"
    ref_username = _username_from_ref(run.get("source_ref"))
    if ref_username:
        return f"https://t.me/{ref_username}/{message_id}"
    telegram_id = str(run.get("telegram_id") or "").strip()
    if telegram_id:
        internal_id = telegram_id.removeprefix("-100").lstrip("-")
        if internal_id.isdigit():
            return f"https://t.me/c/{internal_id}/{message_id}"
    return ""


def _username_from_ref(value: Any) -> str:
    text = str(value or "").strip()
    if "t.me/" not in text:
        return ""
    tail = text.split("t.me/", 1)[1].strip("/")
    username = tail.split("/", 1)[0].strip().lstrip("@")
    if not username or username in {"c", "joinchat", "+"} or username.startswith("+"):
        return ""
    return username


def _read_payload(path: Path) -> Any:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8") as handle:
            return {"items": list(csv.DictReader(handle))}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _totals(runs: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for run in runs:
        materialized = run.get("materialized")
        if not isinstance(materialized, dict):
            continue
        for key, value in materialized.items():
            if isinstance(value, bool):
                totals[key] = totals.get(key, 0) + int(value)
            elif isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals
