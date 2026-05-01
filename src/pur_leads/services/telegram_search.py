"""Unified Telegram FTS + Chroma search and RAG context assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.services.telegram_chroma_index import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_PROFILE,
    TelegramChromaIndexService,
)
from pur_leads.services.telegram_fts_index import TelegramFtsIndexService
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table


class TelegramSearchService:
    """Merge exact FTS and semantic Chroma hits into source-backed RAG context."""

    def __init__(
        self,
        session: Session,
        *,
        search_root: Path | str = "./data/search",
        chroma_root: Path | str = "./data/chroma",
    ) -> None:
        self.session = session
        self.search_root = Path(search_root)
        self.chroma_root = Path(chroma_root)

    def query(
        self,
        raw_export_run_id: str,
        *,
        query_text: str,
        limit: int = 10,
        fts_limit: int | None = None,
        chroma_limit: int | None = None,
        include_chroma: bool = True,
        embedding_profile: str | None = None,
        embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ) -> dict[str, Any]:
        run = self._require_run(raw_export_run_id)
        metadata = dict(run["metadata_json"] or {})

        fts_hits = self._fts_hits(
            metadata,
            query_text=query_text,
            limit=fts_limit or limit * 3,
        )
        chroma_hits = (
            self._chroma_hits(
                metadata,
                query_text=query_text,
                limit=chroma_limit or limit * 3,
                embedding_profile=embedding_profile,
                embedding_dimensions=embedding_dimensions,
            )
            if include_chroma
            else []
        )
        results = _merge_hits(fts_hits, chroma_hits)[: max(1, limit)]
        groups = _groups_from_results(results)
        return {
            "raw_export_run_id": raw_export_run_id,
            "query_text": query_text,
            "results": results,
            "groups": groups,
            "rag_context": _rag_context(results),
            "metrics": {
                "fts_hits": len(fts_hits),
                "chroma_hits": len(chroma_hits),
                "merged_results": len(results),
                "thread_groups": len(groups),
                "message_results": sum(
                    1 for item in results if item.get("entity_type") == "telegram_message"
                ),
                "artifact_results": sum(
                    1 for item in results if item.get("entity_type") == "telegram_artifact"
                ),
            },
        }

    def _fts_hits(
        self,
        metadata: dict[str, Any],
        *,
        query_text: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        fts_index = metadata.get("fts_index")
        if not isinstance(fts_index, dict) or not fts_index.get("search_db_path"):
            return []
        return TelegramFtsIndexService(self.session, search_root=self.search_root).query(
            search_db_path=_resolve_path(fts_index["search_db_path"]),
            query_text=query_text,
            limit=limit,
        )

    def _chroma_hits(
        self,
        metadata: dict[str, Any],
        *,
        query_text: str,
        limit: int,
        embedding_profile: str | None,
        embedding_dimensions: int,
    ) -> list[dict[str, Any]]:
        chroma_index = metadata.get("chroma_index")
        if not isinstance(chroma_index, dict) or not chroma_index.get("chroma_path"):
            return []
        return TelegramChromaIndexService(self.session, chroma_root=self.chroma_root).query(
            chroma_path=_resolve_path(chroma_index["chroma_path"]),
            collection_name=str(chroma_index.get("collection_name") or DEFAULT_COLLECTION_NAME),
            query_text=query_text,
            n_results=limit,
            embedding_profile=embedding_profile
            or str(chroma_index.get("embedding_profile") or DEFAULT_EMBEDDING_PROFILE),
            embedding_dimensions=embedding_dimensions,
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
        return dict(row)


def _merge_hits(
    fts_hits: list[dict[str, Any]],
    chroma_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for hit in fts_hits:
        key = _result_key(hit)
        item = _base_from_fts(hit)
        item["sources"] = ["fts"]
        item["fts_score"] = float(hit.get("score") or 0.0)
        item["chroma_score"] = 0.0
        item["score"] = item["fts_score"]
        merged[key] = item

    for hit in chroma_hits:
        metadata = hit.get("metadata") or {}
        key = _result_key(metadata)
        distance = float(hit.get("distance") or 0.0)
        chroma_score = max(0.0, 1.0 - distance)
        if key not in merged:
            item = _base_from_chroma(hit)
            item["sources"] = ["chroma"]
            item["fts_score"] = 0.0
            item["chroma_score"] = chroma_score
            item["score"] = chroma_score * 0.7
            merged[key] = item
            continue
        item = merged[key]
        if "chroma" not in item["sources"]:
            item["sources"].append("chroma")
        item["chroma_score"] = max(float(item["chroma_score"]), chroma_score)
        item["score"] = float(item["fts_score"]) + item["chroma_score"] * 0.35

    return sorted(
        merged.values(),
        key=lambda item: (float(item["score"]), "fts" in item["sources"]),
        reverse=True,
    )


def _base_from_fts(hit: dict[str, Any]) -> dict[str, Any]:
    message_id = int(hit["telegram_message_id"])
    thread_key = str(hit.get("thread_key") or hit.get("reply_to_message_id") or message_id)
    return {
        "raw_export_run_id": hit.get("raw_export_run_id"),
        "monitored_source_id": hit.get("monitored_source_id"),
        "entity_type": str(hit.get("entity_type") or "telegram_message"),
        "telegram_message_id": message_id,
        "row_index": int(hit.get("row_index") or 0),
        "artifact_id": str(hit.get("artifact_id") or ""),
        "artifact_kind": str(hit.get("artifact_kind") or ""),
        "chunk_index": int(hit.get("chunk_index") or 0),
        "source_url": str(hit.get("source_url") or ""),
        "final_url": str(hit.get("final_url") or ""),
        "title": str(hit.get("title") or ""),
        "file_name": str(hit.get("file_name") or ""),
        "reply_to_message_id": _nullable_int(hit.get("reply_to_message_id")),
        "thread_id": str(hit.get("thread_id") or ""),
        "thread_key": thread_key,
        "date": str(hit.get("date") or ""),
        "message_url": str(hit.get("message_url") or ""),
        "clean_text": str(hit.get("clean_text") or ""),
        "token_count": int(hit.get("token_count") or 0),
    }


def _base_from_chroma(hit: dict[str, Any]) -> dict[str, Any]:
    metadata = hit.get("metadata") or {}
    message_id = int(metadata.get("telegram_message_id") or 0)
    thread_key = str(
        metadata.get("thread_key") or metadata.get("reply_to_message_id") or message_id
    )
    return {
        "raw_export_run_id": metadata.get("raw_export_run_id"),
        "monitored_source_id": metadata.get("monitored_source_id"),
        "entity_type": str(metadata.get("entity_type") or "telegram_message"),
        "telegram_message_id": message_id,
        "row_index": int(metadata.get("row_index") or 0),
        "artifact_id": str(metadata.get("artifact_id") or ""),
        "artifact_kind": str(metadata.get("artifact_kind") or ""),
        "chunk_index": int(metadata.get("chunk_index") or 0),
        "source_url": str(metadata.get("source_url") or ""),
        "final_url": str(metadata.get("final_url") or ""),
        "title": str(metadata.get("title") or ""),
        "file_name": str(metadata.get("file_name") or ""),
        "reply_to_message_id": _nullable_int(metadata.get("reply_to_message_id")),
        "thread_id": str(metadata.get("thread_id") or ""),
        "thread_key": thread_key,
        "date": str(metadata.get("date") or ""),
        "message_url": str(metadata.get("message_url") or ""),
        "clean_text": str(hit.get("document") or ""),
        "token_count": int(metadata.get("token_count") or 0),
    }


def _groups_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        groups.setdefault(str(item["thread_key"]), []).append(item)
    payload = []
    for thread_key, items in groups.items():
        sorted_items = sorted(items, key=lambda item: int(item["telegram_message_id"]))
        top = max(sorted_items, key=lambda item: float(item["score"]))
        payload.append(
            {
                "thread_key": thread_key,
                "top_score": float(top["score"]),
                "top_message_url": top["message_url"],
                "items": sorted_items,
            }
        )
    return sorted(payload, key=lambda item: float(item["top_score"]), reverse=True)


def _rag_context(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "citation": f"[{index}]",
            "entity_type": item["entity_type"],
            "telegram_message_id": item["telegram_message_id"],
            "artifact_id": item["artifact_id"],
            "artifact_kind": item["artifact_kind"],
            "source_url": item["source_url"],
            "file_name": item["file_name"],
            "message_url": item["message_url"],
            "thread_key": item["thread_key"],
            "text": item["clean_text"],
            "sources": item["sources"],
            "score": item["score"],
        }
        for index, item in enumerate(results, start=1)
    ]


def _result_key(hit: dict[str, Any]) -> str:
    entity_type = str(hit.get("entity_type") or "telegram_message")
    if entity_type == "telegram_artifact":
        return (
            f"{hit.get('monitored_source_id')}:{entity_type}:"
            f"{hit.get('artifact_id')}:{hit.get('chunk_index')}"
        )
    return f"{hit.get('monitored_source_id')}:{entity_type}:{hit.get('telegram_message_id')}"


def _nullable_int(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    return int(value)


def _resolve_path(value: Path | str | Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else Path(".") / path
