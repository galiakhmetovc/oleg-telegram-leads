"""Catalog raw source and manual input behavior."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.catalog_sources import (
    ArtifactRecord,
    CatalogSourceRepository,
    ManualInputRecord,
    ParsedChunkRecord,
    SourceRecord,
)
from pur_leads.services.audit import AuditService


@dataclass(frozen=True)
class ManualInputProcessingResult:
    manual_input: ManualInputRecord
    source: SourceRecord | None


class CatalogSourceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogSourceRepository(session)
        self.audit = AuditService(session)

    def upsert_source(
        self,
        *,
        source_type: str,
        origin: str,
        external_id: str,
        raw_text: str | None = None,
        url: str | None = None,
        title: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        fetched_at: datetime | None = None,
        metadata_json: Any = None,
    ) -> SourceRecord:
        normalized_text = normalize_text(raw_text)
        content_hash = content_sha256(
            "|".join(
                [
                    source_type,
                    origin,
                    external_id,
                    normalized_text or "",
                    url or "",
                ]
            )
        )
        existing = self.repository.find_source_by_identity(source_type, origin, external_id)
        if existing is not None:
            source = self.repository.update_source(
                existing.id,
                url=url,
                title=title,
                author=author,
                published_at=published_at,
                fetched_at=fetched_at,
                raw_text=raw_text,
                normalized_text=normalized_text,
                content_hash=content_hash,
                metadata_json=metadata_json,
            )
        else:
            source = self.repository.create_source(
                source_type=source_type,
                origin=origin,
                external_id=external_id,
                url=url,
                title=title,
                author=author,
                published_at=published_at,
                fetched_at=fetched_at,
                raw_text=raw_text,
                normalized_text=normalized_text,
                content_hash=content_hash,
                metadata_json=metadata_json,
                created_at=utc_now(),
            )
        self.session.commit()
        return source

    def record_artifact(
        self,
        source_id: str,
        *,
        artifact_type: str,
        file_name: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        sha256: str | None = None,
        local_path: str | None = None,
        download_status: str,
        skip_reason: str | None = None,
    ) -> ArtifactRecord:
        artifact = self.repository.create_artifact(
            source_id=source_id,
            artifact_type=artifact_type,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            sha256=sha256,
            local_path=local_path,
            download_status=download_status,
            skip_reason=skip_reason,
            created_at=utc_now(),
        )
        self.session.commit()
        return artifact

    def replace_parsed_chunks(
        self,
        source_id: str,
        *,
        artifact_id: str | None = None,
        chunks: list[str],
        parser_name: str,
        parser_version: str,
    ) -> list[ParsedChunkRecord]:
        now = utc_now()
        records = self.repository.replace_chunks(
            source_id=source_id,
            artifact_id=artifact_id,
            chunks=[
                {
                    "source_id": source_id,
                    "artifact_id": artifact_id,
                    "chunk_index": index,
                    "text": text,
                    "token_estimate": estimate_tokens(text),
                    "parser_name": parser_name,
                    "parser_version": parser_version,
                    "created_at": now,
                }
                for index, text in enumerate(chunks)
            ],
        )
        self.session.commit()
        return records

    def submit_manual_input(
        self,
        *,
        input_type: str,
        submitted_by: str,
        submission_channel: str = "web",
        text: str | None = None,
        url: str | None = None,
        chat_ref: str | None = None,
        message_id: int | None = None,
        evidence_note: str | None = None,
        metadata_json: Any = None,
    ) -> ManualInputProcessingResult:
        metadata = dict(metadata_json or {})
        if evidence_note:
            metadata["evidence_note"] = evidence_note
        now = utc_now()
        manual_input = self.repository.create_manual_input(
            input_type=input_type,
            submission_channel=submission_channel,
            text=text,
            url=url,
            chat_ref=chat_ref,
            message_id=message_id,
            submitted_by=submitted_by,
            submitted_at=now,
            processing_status="new",
            metadata_json=metadata,
        )
        self.audit.record_change(
            actor=submitted_by,
            action="manual_input.create",
            entity_type="manual_input",
            entity_id=manual_input.id,
            old_value_json=None,
            new_value_json={"input_type": input_type, "submission_channel": submission_channel},
        )

        source = self._source_from_manual_input(manual_input, metadata)
        if source is not None:
            manual_input = self.repository.update_manual_input(
                manual_input.id,
                processing_status="processed",
            )
            self.audit.record_change(
                actor=submitted_by,
                action="manual_input.process_source",
                entity_type="manual_input",
                entity_id=manual_input.id,
                old_value_json={"processing_status": "new"},
                new_value_json={
                    "processing_status": "processed",
                    "source_id": source.id,
                    "source_type": source.source_type,
                },
            )
        self.session.commit()
        return ManualInputProcessingResult(manual_input=manual_input, source=source)

    def _source_from_manual_input(
        self,
        manual_input: ManualInputRecord,
        metadata: dict[str, Any],
    ) -> SourceRecord | None:
        if manual_input.text:
            return self.upsert_source(
                source_type="manual_text",
                origin="manual",
                external_id=manual_input.id,
                raw_text=manual_input.text,
                metadata_json=metadata,
            )
        if manual_input.url:
            origin = manual_input.chat_ref or "manual"
            external_id = (
                str(manual_input.message_id) if manual_input.message_id else manual_input.url
            )
            return self.upsert_source(
                source_type="manual_link",
                origin=origin,
                external_id=external_id,
                url=manual_input.url,
                metadata_json=metadata,
            )
        return None


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().split())
    return normalized or None


def content_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def estimate_tokens(value: str) -> int:
    return len(value.split())
