"""Catalog raw source persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.catalog import (
    artifacts_table,
    manual_inputs_table,
    parsed_chunks_table,
    sources_table,
)


@dataclass(frozen=True)
class SourceRecord:
    id: str
    source_type: str
    origin: str
    external_id: str
    url: str | None
    title: str | None
    author: str | None
    published_at: datetime | None
    fetched_at: datetime | None
    raw_text: str | None
    normalized_text: str | None
    content_hash: str
    metadata_json: Any
    created_at: datetime


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    source_id: str
    artifact_type: str
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    sha256: str | None
    local_path: str | None
    download_status: str
    skip_reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class ParsedChunkRecord:
    id: str
    source_id: str
    artifact_id: str | None
    chunk_index: int
    text: str
    token_estimate: int
    parser_name: str
    parser_version: str
    created_at: datetime


@dataclass(frozen=True)
class ManualInputRecord:
    id: str
    input_type: str
    submission_channel: str
    text: str | None
    url: str | None
    chat_ref: str | None
    message_id: int | None
    submitted_by: str
    submitted_at: datetime
    processing_status: str
    metadata_json: Any


class CatalogSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_source(self, source_id: str) -> SourceRecord | None:
        row = (
            self.session.execute(select(sources_table).where(sources_table.c.id == source_id))
            .mappings()
            .first()
        )
        return SourceRecord(**dict(row)) if row is not None else None

    def find_source_by_identity(
        self, source_type: str, origin: str, external_id: str
    ) -> SourceRecord | None:
        row = (
            self.session.execute(
                select(sources_table).where(
                    sources_table.c.source_type == source_type,
                    sources_table.c.origin == origin,
                    sources_table.c.external_id == external_id,
                )
            )
            .mappings()
            .first()
        )
        return SourceRecord(**dict(row)) if row is not None else None

    def create_source(self, **values) -> SourceRecord:  # type: ignore[no-untyped-def]
        source_id = new_id()
        self.session.execute(insert(sources_table).values(id=source_id, **values))
        return self.get_source(source_id)  # type: ignore[return-value]

    def update_source(self, source_id: str, **values) -> SourceRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(sources_table).where(sources_table.c.id == source_id).values(**values)
        )
        source = self.get_source(source_id)
        if source is None:
            raise KeyError(source_id)
        return source

    def create_artifact(self, **values) -> ArtifactRecord:  # type: ignore[no-untyped-def]
        artifact_id = new_id()
        self.session.execute(insert(artifacts_table).values(id=artifact_id, **values))
        return self.get_artifact(artifact_id)  # type: ignore[return-value]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        row = (
            self.session.execute(select(artifacts_table).where(artifacts_table.c.id == artifact_id))
            .mappings()
            .first()
        )
        return ArtifactRecord(**dict(row)) if row is not None else None

    def replace_chunks(
        self,
        *,
        source_id: str,
        artifact_id: str | None,
        chunks: list[dict[str, Any]],
    ) -> list[ParsedChunkRecord]:
        query = parsed_chunks_table.c.source_id == source_id
        if artifact_id is None:
            query = query & parsed_chunks_table.c.artifact_id.is_(None)
        else:
            query = query & (parsed_chunks_table.c.artifact_id == artifact_id)
        self.session.execute(delete(parsed_chunks_table).where(query))

        chunk_ids: list[str] = []
        for chunk in chunks:
            chunk_id = new_id()
            chunk_ids.append(chunk_id)
            self.session.execute(insert(parsed_chunks_table).values(id=chunk_id, **chunk))
        return self.list_chunks_by_ids(chunk_ids)

    def list_chunks_by_ids(self, chunk_ids: list[str]) -> list[ParsedChunkRecord]:
        if not chunk_ids:
            return []
        rows = (
            self.session.execute(
                select(parsed_chunks_table)
                .where(parsed_chunks_table.c.id.in_(chunk_ids))
                .order_by(parsed_chunks_table.c.chunk_index)
            )
            .mappings()
            .all()
        )
        return [ParsedChunkRecord(**dict(row)) for row in rows]

    def create_manual_input(self, **values) -> ManualInputRecord:  # type: ignore[no-untyped-def]
        input_id = new_id()
        self.session.execute(insert(manual_inputs_table).values(id=input_id, **values))
        return self.get_manual_input(input_id)  # type: ignore[return-value]

    def update_manual_input(self, manual_input_id: str, **values) -> ManualInputRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(manual_inputs_table)
            .where(manual_inputs_table.c.id == manual_input_id)
            .values(**values)
        )
        manual_input = self.get_manual_input(manual_input_id)
        if manual_input is None:
            raise KeyError(manual_input_id)
        return manual_input

    def get_manual_input(self, manual_input_id: str) -> ManualInputRecord | None:
        row = (
            self.session.execute(
                select(manual_inputs_table).where(manual_inputs_table.c.id == manual_input_id)
            )
            .mappings()
            .first()
        )
        return ManualInputRecord(**dict(row)) if row is not None else None
