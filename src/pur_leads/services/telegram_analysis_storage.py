"""PostgreSQL storage helpers for Telegram analysis stages."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import (
    telegram_analysis_stage_outputs_table,
    telegram_entity_candidates_table,
    telegram_prepared_documents_table,
)


def prepared_document_rows(session: Session, raw_export_run_id: str) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(telegram_prepared_documents_table)
            .where(telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id)
            .where(telegram_prepared_documents_table.c.has_text.is_(True))
            .order_by(
                telegram_prepared_documents_table.c.entity_type,
                telegram_prepared_documents_table.c.telegram_message_id,
                telegram_prepared_documents_table.c.chunk_index,
            )
        )
        .mappings()
        .all()
    )
    return [_prepared_row_payload(dict(row)) for row in rows]


def feature_rows(session: Session, raw_export_run_id: str) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(telegram_prepared_documents_table)
            .where(telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id)
            .where(telegram_prepared_documents_table.c.feature_json.is_not(None))
            .order_by(
                telegram_prepared_documents_table.c.entity_type,
                telegram_prepared_documents_table.c.telegram_message_id,
                telegram_prepared_documents_table.c.chunk_index,
            )
        )
        .mappings()
        .all()
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = row["feature_json"]
        if isinstance(payload, dict):
            result.append(payload)
    return result


def replace_document_features(
    session: Session,
    raw_export_run_id: str,
    feature_rows_payload: list[dict[str, Any]],
) -> int:
    now = utc_now()
    updated = 0
    session.execute(
        update(telegram_prepared_documents_table)
        .where(telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id)
        .values(feature_json=None, updated_at=now)
    )
    for row in feature_rows_payload:
        prepared_document_id = row.get("prepared_document_id")
        if not prepared_document_id:
            continue
        result = session.execute(
            update(telegram_prepared_documents_table)
            .where(telegram_prepared_documents_table.c.id == str(prepared_document_id))
            .where(telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id)
            .values(feature_json=_json_ready(row), updated_at=now)
        )
        updated += int(result.rowcount or 0)
    return updated


def replace_stage_outputs(
    session: Session,
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    stage_key: str,
    outputs: dict[str, dict[str, Any]],
) -> int:
    now = utc_now()
    session.execute(
        delete(telegram_analysis_stage_outputs_table)
        .where(telegram_analysis_stage_outputs_table.c.raw_export_run_id == raw_export_run_id)
        .where(telegram_analysis_stage_outputs_table.c.stage_key == stage_key)
    )
    rows = []
    for output_key, output in outputs.items():
        payload = output.get("payload_json")
        rows.append(
            {
                "id": f"{raw_export_run_id}:{stage_key}:{output_key}"[:160],
                "raw_export_run_id": raw_export_run_id,
                "monitored_source_id": monitored_source_id,
                "stage_key": stage_key,
                "output_key": output_key,
                "output_kind": str(output.get("output_kind") or "json"),
                "payload_json": _json_ready(payload),
                "artifact_path": output.get("artifact_path"),
                "row_count": _row_count(payload),
                "created_at": now,
                "updated_at": now,
            }
        )
    if rows:
        session.execute(insert(telegram_analysis_stage_outputs_table), rows)
    return len(rows)


def stage_outputs(session: Session, raw_export_run_id: str, stage_key: str) -> dict[str, Any]:
    rows = (
        session.execute(
            select(telegram_analysis_stage_outputs_table)
            .where(telegram_analysis_stage_outputs_table.c.raw_export_run_id == raw_export_run_id)
            .where(telegram_analysis_stage_outputs_table.c.stage_key == stage_key)
        )
        .mappings()
        .all()
    )
    return {str(row["output_key"]): dict(row) for row in rows}


def replace_entity_candidates(
    session: Session,
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    rows: list[dict[str, Any]],
) -> int:
    now = utc_now()
    session.execute(
        delete(telegram_entity_candidates_table).where(
            telegram_entity_candidates_table.c.raw_export_run_id == raw_export_run_id
        )
    )
    prepared = [
        _entity_row(row, raw_export_run_id=raw_export_run_id, monitored_source_id=monitored_source_id, now=now)
        for row in rows
    ]
    for index in range(0, len(prepared), 1000):
        session.execute(insert(telegram_entity_candidates_table), prepared[index : index + 1000])
    return len(prepared)


def entity_candidate_rows(session: Session, raw_export_run_id: str) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(telegram_entity_candidates_table)
            .where(telegram_entity_candidates_table.c.raw_export_run_id == raw_export_run_id)
            .order_by(
                telegram_entity_candidates_table.c.normalized_text,
                telegram_entity_candidates_table.c.entity_id,
            )
        )
        .mappings()
        .all()
    )
    return [_entity_payload(dict(row)) for row in rows]


def replace_ranked_entity_candidates(
    session: Session,
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    rows: list[dict[str, Any]],
) -> int:
    now = utc_now()
    session.execute(
        delete(telegram_entity_candidates_table).where(
            telegram_entity_candidates_table.c.raw_export_run_id == raw_export_run_id
        )
    )
    prepared = [
        _entity_row(
            row,
            raw_export_run_id=raw_export_run_id,
            monitored_source_id=monitored_source_id,
            now=now,
        )
        for row in rows
    ]
    for index in range(0, len(prepared), 1000):
        session.execute(insert(telegram_entity_candidates_table), prepared[index : index + 1000])
    return len(prepared)


def ranked_entity_rows(
    session: Session,
    raw_export_run_id: str,
    *,
    statuses: set[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = select(telegram_entity_candidates_table).where(
        telegram_entity_candidates_table.c.raw_export_run_id == raw_export_run_id
    )
    if statuses:
        query = query.where(telegram_entity_candidates_table.c.ranking_status.in_(statuses))
    query = query.order_by(
        telegram_entity_candidates_table.c.score.desc().nullslast(),
        telegram_entity_candidates_table.c.normalized_text,
    )
    if limit is not None:
        query = query.limit(max(1, limit)).offset(max(0, offset))
    rows = session.execute(query).mappings().all()
    return [_entity_payload(dict(row)) for row in rows]


def _prepared_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "prepared_document_id": row["id"],
        "entity_type": row["entity_type"],
        "export_run_id": row["raw_export_run_id"],
        "monitored_source_id": row["monitored_source_id"],
        "telegram_message_id": row["telegram_message_id"],
        "row_index": row["row_index"],
        "artifact_id": row["artifact_id"],
        "artifact_kind": row["artifact_kind"],
        "chunk_index": row["chunk_index"],
        "source_url": row["source_url"],
        "final_url": row["final_url"],
        "title": row["title"],
        "file_name": row["file_name"],
        "date": row["date"],
        "message_url": row["message_url"],
        "raw_text": row["raw_text"],
        "clean_text": row["clean_text"],
        "normalization_lang": row["normalization_lang"],
        "tokens_json": row["tokens_json"] or [],
        "lemmas_json": row["lemmas_json"] or [],
        "pos_tags_json": row["pos_tags_json"] or [],
        "token_count": row["token_count"],
        "has_text": row["has_text"],
    }


def _entity_row(
    row: dict[str, Any],
    *,
    raw_export_run_id: str,
    monitored_source_id: str,
    now: Any,
) -> dict[str, Any]:
    entity_id = str(row["entity_id"])
    return {
        "id": f"{raw_export_run_id}:{entity_id}"[:160],
        "raw_export_run_id": raw_export_run_id,
        "monitored_source_id": monitored_source_id,
        "entity_id": entity_id,
        "group_id": str(row.get("group_id") or ""),
        "canonical_text": str(row.get("canonical_text") or ""),
        "normalized_text": str(row.get("normalized_text") or ""),
        "lemma_text": str(row.get("lemma_text") or row.get("normalized_text") or ""),
        "pos_pattern_json": _json_any(row.get("pos_pattern_json"), default=[]),
        "mention_count": int(row.get("mention_count") or 0),
        "source_count": int(row.get("source_count") or 0),
        "source_refs_json": _json_any(row.get("source_refs_json"), default=[]),
        "example_contexts_json": _json_any(row.get("example_contexts_json"), default=[]),
        "entity_type_counts_json": _json_any(row.get("entity_type_counts_json"), default={}),
        "group_confidence": str(row.get("group_confidence") or ""),
        "group_method": str(row.get("group_method") or ""),
        "score": row.get("score"),
        "ranking_status": row.get("ranking_status"),
        "reasons_json": _json_any(row.get("reasons_json"), default=[]),
        "penalties_json": _json_any(row.get("penalties_json"), default=[]),
        "payload_json": _json_ready(row),
        "created_at": now,
        "updated_at": now,
    }


def _entity_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "pos_pattern_json": json.dumps(row.get("pos_pattern_json") or [], ensure_ascii=False),
        "source_refs_json": json.dumps(row.get("source_refs_json") or [], ensure_ascii=False),
        "example_contexts_json": json.dumps(
            row.get("example_contexts_json") or [], ensure_ascii=False
        ),
        "entity_type_counts_json": json.dumps(
            row.get("entity_type_counts_json") or {}, ensure_ascii=False
        ),
        "reasons_json": json.dumps(row.get("reasons_json") or [], ensure_ascii=False),
        "penalties_json": json.dumps(row.get("penalties_json") or [], ensure_ascii=False),
    }


def _row_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("items", "rows", "groups"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return 1 if payload else 0


def _json_ready(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return _json_any(value, default=value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _json_any(value: Any, *, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default
