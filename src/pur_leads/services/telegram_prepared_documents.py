"""PostgreSQL-backed prepared Telegram documents for search and audit UI."""

from __future__ import annotations

import json
from hashlib import blake2b
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_prepared_documents_table


def replace_prepared_documents(
    session: Session,
    rows: list[dict[str, Any]],
    *,
    raw_export_run_id: str,
    entity_type: str,
) -> int:
    """Replace one prepared-document slice in the operational database."""

    session.execute(
        delete(telegram_prepared_documents_table)
        .where(telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id)
        .where(telegram_prepared_documents_table.c.entity_type == entity_type)
    )
    prepared = [
        _prepared_row(row, raw_export_run_id=raw_export_run_id, entity_type=entity_type)
        for row in rows
        if row.get("has_text")
    ]
    if not prepared:
        return 0
    for index in range(0, len(prepared), 1000):
        session.execute(telegram_prepared_documents_table.insert(), prepared[index : index + 1000])
    return len(prepared)


def prepared_document_count(session: Session, raw_export_run_id: str) -> int:
    return int(
        session.execute(
            select(func.count(telegram_prepared_documents_table.c.id)).where(
                telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id
            )
        ).scalar_one()
        or 0
    )


def _prepared_row(
    row: dict[str, Any],
    *,
    raw_export_run_id: str,
    entity_type: str,
) -> dict[str, Any]:
    now = utc_now()
    export_run_id = str(row.get("export_run_id") or raw_export_run_id)
    message_id = int(row.get("telegram_message_id") or 0)
    row_index = int(row.get("row_index") or 0)
    chunk_index = int(row.get("chunk_index") or 0)
    artifact_id = str(row.get("artifact_id") or "")
    artifact_kind = str(row.get("artifact_kind") or "")
    thread = _thread_fields(row)
    tokens = _json_list(row.get("tokens_json"))
    lemmas = _json_list(row.get("lemmas_json"))
    pos_tags = _json_list(row.get("pos_tags_json"))
    token_map = _json_any(row.get("token_map_json"), default=[])
    clean_text = str(row.get("clean_text") or "")
    return {
        "id": _prepared_id(
            raw_export_run_id=export_run_id,
            entity_type=entity_type,
            message_id=message_id,
            row_index=row_index,
            artifact_id=artifact_id,
            chunk_index=chunk_index,
        ),
        "raw_export_run_id": export_run_id,
        "monitored_source_id": str(row.get("monitored_source_id") or ""),
        "entity_type": entity_type,
        "telegram_message_id": message_id,
        "row_index": row_index,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "chunk_index": chunk_index,
        "source_url": str(row.get("source_url") or ""),
        "final_url": str(row.get("final_url") or ""),
        "title": str(row.get("title") or ""),
        "file_name": str(row.get("file_name") or ""),
        "reply_to_message_id": thread["reply_to_message_id"],
        "thread_id": thread["thread_id"],
        "thread_key": thread["thread_key"],
        "date": str(row.get("date") or ""),
        "message_url": str(row.get("message_url") or ""),
        "raw_text": str(row.get("raw_text") or ""),
        "clean_text": clean_text,
        "lemmas_text": " ".join(str(item) for item in lemmas),
        "normalization_lang": str(row.get("normalization_lang") or "unknown"),
        "tokens_json": tokens,
        "lemmas_json": lemmas,
        "pos_tags_json": pos_tags,
        "token_map_json": token_map,
        "token_count": int(row.get("token_count") or len(tokens)),
        "has_text": bool(clean_text.strip()),
        "normalization_status": str(row.get("normalization_status") or "normalized"),
        "normalization_error": row.get("normalization_error"),
        "payload_json": _payload(row),
        "feature_json": None,
        "created_at": now,
        "updated_at": now,
    }


def _prepared_id(
    *,
    raw_export_run_id: str,
    entity_type: str,
    message_id: int,
    row_index: int,
    artifact_id: str,
    chunk_index: int,
) -> str:
    if entity_type == "telegram_artifact":
        raw = f"{raw_export_run_id}:artifact:{message_id}:{artifact_id}:{chunk_index}"
        if len(raw) <= 160:
            return raw
        digest = blake2b(raw.encode("utf-8"), digest_size=12).hexdigest()
        return f"{raw_export_run_id}:artifact:{message_id}:{chunk_index}:{digest}"[:160]
    return f"{raw_export_run_id}:message:{message_id}:{row_index}"[:160]


def _thread_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = _json_dict(row.get("raw_message_json"))
    message_id = int(row.get("telegram_message_id") or 0)
    reply_to = raw.get("reply_to_message_id")
    thread_id = str(raw.get("thread_id") or "")
    thread_key = thread_id or (str(reply_to) if reply_to is not None else str(message_id))
    return {
        "reply_to_message_id": int(reply_to) if reply_to is not None else None,
        "thread_id": thread_id,
        "thread_key": thread_key,
    }


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key
        not in {
            "tokens_json",
            "lemmas_json",
            "pos_tags_json",
            "token_map_json",
            "raw_message_json",
        }
    }


def _json_dict(value: Any) -> dict[str, Any]:
    parsed = _json_any(value, default={})
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[str]:
    parsed = _json_any(value, default=[])
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_any(value: Any, *, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default
