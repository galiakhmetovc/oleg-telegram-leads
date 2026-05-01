"""Read-only visibility over catalog raw ingest data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import desc, distinct, func, or_, select
from sqlalchemy.orm import Session

from pur_leads.models.catalog import artifacts_table, parsed_chunks_table, sources_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table

CATALOG_SOURCE_PURPOSES = ("catalog_ingestion", "both")
PENDING_JOB_STATUSES = ("queued", "running")


class CatalogRawIngestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_overview(
        self,
        *,
        source_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        monitored_sources = self._catalog_sources(source_id=source_id)
        source_ids = [row["id"] for row in monitored_sources]
        source_by_id = {row["id"]: row for row in monitored_sources}
        all_raw_source_ids = self._all_raw_source_ids(source_ids)
        page_messages = self._latest_messages(source_ids, limit=limit)
        page_raw_source_ids = [
            row["raw_source_id"] for row in page_messages if row["raw_source_id"] is not None
        ]
        raw_sources_by_id = self._raw_sources_by_id(page_raw_source_ids)
        page_message_ids = [row["id"] for row in page_messages]
        jobs_by_message = self._jobs_by_message_ids(page_message_ids, pending_only=True)
        artifact_counts = self._counts_by_source_id(artifacts_table, all_raw_source_ids)
        chunk_counts = self._counts_by_source_id(parsed_chunks_table, all_raw_source_ids)
        source_stats = self._source_stats(
            source_ids=source_ids,
            raw_source_ids=all_raw_source_ids,
            artifact_counts=artifact_counts,
            chunk_counts=chunk_counts,
        )

        return {
            "summary": {
                "catalog_sources": len(monitored_sources),
                "messages": self._message_count(source_ids),
                "mirrored_sources": len(all_raw_source_ids),
                "artifacts": sum(artifact_counts.values()),
                "parsed_chunks": sum(chunk_counts.values()),
                "pending_jobs": self._pending_job_count(source_ids),
            },
            "sources": [
                self._monitored_source_payload(row, source_stats.get(row["id"], {}))
                for row in monitored_sources
            ],
            "messages": [
                self._message_payload(
                    message,
                    monitored_source=source_by_id.get(message["monitored_source_id"]),
                    raw_source=raw_sources_by_id.get(message["raw_source_id"]),
                    chunk_count=chunk_counts.get(message["raw_source_id"], 0),
                    artifact_count=artifact_counts.get(message["raw_source_id"], 0),
                    pending_jobs=jobs_by_message.get(message["id"], []),
                )
                for message in page_messages
            ],
        }

    def get_message_detail(self, source_message_id: str) -> dict[str, Any]:
        message = (
            self.session.execute(
                select(source_messages_table).where(source_messages_table.c.id == source_message_id)
            )
            .mappings()
            .first()
        )
        if message is None:
            raise KeyError(source_message_id)

        monitored_source = (
            self.session.execute(
                select(monitored_sources_table).where(
                    monitored_sources_table.c.id == message["monitored_source_id"]
                )
            )
            .mappings()
            .first()
        )
        raw_source = None
        artifacts: list[dict[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        if message["raw_source_id"] is not None:
            raw_source = (
                self.session.execute(
                    select(sources_table).where(sources_table.c.id == message["raw_source_id"])
                )
                .mappings()
                .first()
            )
            artifacts = [
                dict(row)
                for row in self.session.execute(
                    select(artifacts_table)
                    .where(artifacts_table.c.source_id == message["raw_source_id"])
                    .order_by(artifacts_table.c.created_at)
                )
                .mappings()
                .all()
            ]
            chunks = [
                dict(row)
                for row in self.session.execute(
                    select(parsed_chunks_table)
                    .where(parsed_chunks_table.c.source_id == message["raw_source_id"])
                    .order_by(parsed_chunks_table.c.chunk_index)
                )
                .mappings()
                .all()
            ]

        jobs = self._jobs_by_message_ids([source_message_id], pending_only=False).get(
            source_message_id,
            [],
        )
        raw_source_payload = dict(raw_source) if raw_source is not None else None
        if raw_source_payload is not None:
            raw_source_payload["chunk_count"] = len(chunks)
            raw_source_payload["artifact_count"] = len(artifacts)

        return {
            "message": self._message_payload(
                message,
                monitored_source=monitored_source,
                raw_source=raw_source,
                chunk_count=len(chunks),
                artifact_count=len(artifacts),
                pending_jobs=[job for job in jobs if job["status"] in PENDING_JOB_STATUSES],
            ),
            "monitored_source": dict(monitored_source) if monitored_source is not None else None,
            "raw_source": raw_source_payload,
            "artifacts": artifacts,
            "chunks": chunks,
            "jobs": jobs,
        }

    def _catalog_sources(self, *, source_id: str | None = None) -> list[dict[str, Any]]:
        query = select(monitored_sources_table).where(
            or_(
                monitored_sources_table.c.catalog_ingestion_enabled.is_(True),
                monitored_sources_table.c.source_purpose.in_(CATALOG_SOURCE_PURPOSES),
            )
        )
        if source_id is not None:
            query = query.where(monitored_sources_table.c.id == source_id)
        rows = (
            self.session.execute(
                query.order_by(desc(monitored_sources_table.c.updated_at)).limit(500)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _latest_messages(self, source_ids: list[str], *, limit: int) -> list[dict[str, Any]]:
        if not source_ids:
            return []
        rows = (
            self.session.execute(
                select(source_messages_table)
                .where(source_messages_table.c.monitored_source_id.in_(source_ids))
                .order_by(
                    desc(source_messages_table.c.message_date),
                    desc(source_messages_table.c.telegram_message_id),
                )
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _all_raw_source_ids(self, source_ids: list[str]) -> list[str]:
        if not source_ids:
            return []
        rows = (
            self.session.execute(
                select(distinct(source_messages_table.c.raw_source_id))
                .where(source_messages_table.c.monitored_source_id.in_(source_ids))
                .where(source_messages_table.c.raw_source_id.is_not(None))
            )
            .scalars()
            .all()
        )
        return [str(row) for row in rows if row is not None]

    def _raw_sources_by_id(self, source_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not source_ids:
            return {}
        rows = (
            self.session.execute(select(sources_table).where(sources_table.c.id.in_(source_ids)))
            .mappings()
            .all()
        )
        return {row["id"]: dict(row) for row in rows}

    def _counts_by_source_id(self, table: Any, source_ids: list[str]) -> dict[str, int]:
        if not source_ids:
            return {}
        rows = (
            self.session.execute(
                select(table.c.source_id, func.count())
                .where(table.c.source_id.in_(source_ids))
                .group_by(table.c.source_id)
            )
            .mappings()
            .all()
        )
        return {row["source_id"]: int(row["count"]) for row in rows}

    def _source_stats(
        self,
        *,
        source_ids: list[str],
        raw_source_ids: list[str],
        artifact_counts: dict[str, int],
        chunk_counts: dict[str, int],
    ) -> dict[str, dict[str, Any]]:
        if not source_ids:
            return {}
        stats: dict[str, dict[str, Any]] = {
            source_id: {
                "message_count": 0,
                "raw_source_count": 0,
                "artifact_count": 0,
                "chunk_count": 0,
                "pending_job_count": 0,
                "last_message_at": None,
            }
            for source_id in source_ids
        }
        raw_source_by_source: dict[str, set[str]] = defaultdict(set)
        rows = (
            self.session.execute(
                select(
                    source_messages_table.c.monitored_source_id,
                    source_messages_table.c.raw_source_id,
                    source_messages_table.c.message_date,
                ).where(source_messages_table.c.monitored_source_id.in_(source_ids))
            )
            .mappings()
            .all()
        )
        for row in rows:
            source_id = row["monitored_source_id"]
            stats[source_id]["message_count"] += 1
            if row["raw_source_id"] is not None:
                raw_source_by_source[source_id].add(row["raw_source_id"])
            last_message_at = stats[source_id]["last_message_at"]
            if last_message_at is None or row["message_date"] > last_message_at:
                stats[source_id]["last_message_at"] = row["message_date"]

        pending_rows = (
            self.session.execute(
                select(scheduler_jobs_table.c.monitored_source_id, func.count())
                .where(scheduler_jobs_table.c.monitored_source_id.in_(source_ids))
                .where(scheduler_jobs_table.c.status.in_(PENDING_JOB_STATUSES))
                .group_by(scheduler_jobs_table.c.monitored_source_id)
            )
            .mappings()
            .all()
        )
        for row in pending_rows:
            stats[row["monitored_source_id"]]["pending_job_count"] = int(row["count"])

        raw_source_set = set(raw_source_ids)
        for source_id, source_raw_ids in raw_source_by_source.items():
            kept_raw_ids = source_raw_ids & raw_source_set
            stats[source_id]["raw_source_count"] = len(kept_raw_ids)
            stats[source_id]["artifact_count"] = sum(
                artifact_counts.get(raw_source_id, 0) for raw_source_id in kept_raw_ids
            )
            stats[source_id]["chunk_count"] = sum(
                chunk_counts.get(raw_source_id, 0) for raw_source_id in kept_raw_ids
            )
        return stats

    def _message_count(self, source_ids: list[str]) -> int:
        if not source_ids:
            return 0
        return int(
            self.session.execute(
                select(func.count())
                .select_from(source_messages_table)
                .where(source_messages_table.c.monitored_source_id.in_(source_ids))
            ).scalar_one()
        )

    def _pending_job_count(self, source_ids: list[str]) -> int:
        if not source_ids:
            return 0
        return int(
            self.session.execute(
                select(func.count())
                .select_from(scheduler_jobs_table)
                .where(scheduler_jobs_table.c.monitored_source_id.in_(source_ids))
                .where(scheduler_jobs_table.c.status.in_(PENDING_JOB_STATUSES))
            ).scalar_one()
        )

    def _jobs_by_message_ids(
        self,
        message_ids: list[str],
        *,
        pending_only: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        if not message_ids:
            return {}
        query = select(scheduler_jobs_table).where(
            scheduler_jobs_table.c.source_message_id.in_(message_ids)
        )
        if pending_only:
            query = query.where(scheduler_jobs_table.c.status.in_(PENDING_JOB_STATUSES))
        rows = (
            self.session.execute(query.order_by(desc(scheduler_jobs_table.c.created_at)))
            .mappings()
            .all()
        )
        jobs_by_message: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            payload = dict(row)
            jobs_by_message[payload["source_message_id"]].append(payload)
        return jobs_by_message

    def _monitored_source_payload(
        self,
        row: dict[str, Any],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "input_ref": row["input_ref"],
            "title": row["title"],
            "username": row["username"],
            "source_kind": row["source_kind"],
            "source_purpose": row["source_purpose"],
            "status": row["status"],
            "catalog_ingestion_enabled": row["catalog_ingestion_enabled"],
            "checkpoint_message_id": row["checkpoint_message_id"],
            "last_success_at": row["last_success_at"],
            "last_error": row["last_error"],
            "message_count": int(stats.get("message_count", 0)),
            "raw_source_count": int(stats.get("raw_source_count", 0)),
            "artifact_count": int(stats.get("artifact_count", 0)),
            "chunk_count": int(stats.get("chunk_count", 0)),
            "pending_job_count": int(stats.get("pending_job_count", 0)),
            "last_message_at": stats.get("last_message_at"),
        }

    def _message_payload(
        self,
        message: dict[str, Any],
        *,
        monitored_source: dict[str, Any] | None,
        raw_source: dict[str, Any] | None,
        chunk_count: int,
        artifact_count: int,
        pending_jobs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw_source_payload = None
        if raw_source is not None:
            raw_source_payload = {
                "id": raw_source["id"],
                "source_type": raw_source["source_type"],
                "origin": raw_source["origin"],
                "external_id": raw_source["external_id"],
                "url": raw_source["url"],
                "title": raw_source["title"],
                "fetched_at": raw_source["fetched_at"],
                "chunk_count": chunk_count,
                "artifact_count": artifact_count,
            }
        return {
            "id": message["id"],
            "monitored_source_id": message["monitored_source_id"],
            "telegram_message_id": message["telegram_message_id"],
            "message_url": self._message_url(message, monitored_source, raw_source),
            "message_date": message["message_date"],
            "fetched_at": message["fetched_at"],
            "sender_id": message["sender_id"],
            "text_excerpt": _excerpt(_message_text(message), limit=220),
            "caption_excerpt": _excerpt(message["caption"], limit=160),
            "has_media": bool(message["has_media"]),
            "media_metadata": message["media_metadata_json"],
            "classification_status": message["classification_status"],
            "raw_source": raw_source_payload,
            "pending_jobs": [_job_summary(job) for job in pending_jobs],
        }

    def _message_url(
        self,
        message: dict[str, Any],
        monitored_source: dict[str, Any] | None,
        raw_source: dict[str, Any] | None,
    ) -> str | None:
        if raw_source is not None and raw_source["url"]:
            return str(raw_source["url"])
        username = monitored_source["username"] if monitored_source is not None else None
        if username:
            return f"https://t.me/{username}/{message['telegram_message_id']}"
        return None


def _message_text(message: dict[str, Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for part in (message["text"], message["caption"]):
        if not part or not part.strip():
            continue
        cleaned = " ".join(part.split())
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        parts.append(cleaned)
    normalized = " ".join(str(message.get("normalized_text") or "").split())
    combined = " ".join(parts)
    if normalized and combined.casefold() == normalized.casefold():
        return normalized
    if normalized and normalized.casefold() not in seen:
        parts.append(normalized)
    return " ".join(parts)


def _excerpt(value: str | None, *, limit: int) -> str:
    if not value:
        return ""
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "priority": job["priority"],
        "run_after_at": job["run_after_at"],
        "attempt_count": job["attempt_count"],
        "max_attempts": job["max_attempts"],
        "last_error": job["last_error"],
        "created_at": job["created_at"],
    }
