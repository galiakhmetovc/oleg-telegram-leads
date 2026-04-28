"""Catalog extraction and candidate persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.catalog import (
    artifacts_table,
    catalog_candidate_facts_table,
    catalog_candidates_table,
    catalog_evidence_table,
    extracted_facts_table,
    extraction_runs_table,
    parsed_chunks_table,
    sources_table,
)


@dataclass(frozen=True)
class ExtractionRunRecord:
    id: str
    run_type: str
    model: str | None
    prompt_version: str | None
    catalog_version_id: str | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    error: str | None
    stats_json: Any
    source_scope_json: Any
    extractor_version: str
    candidate_count: int
    fact_count: int
    created_catalog_entity_count: int
    token_usage_json: Any


@dataclass(frozen=True)
class ExtractedFactRecord:
    id: str
    extraction_run_id: str
    source_id: str | None
    chunk_id: str | None
    fact_type: str
    canonical_name: str
    value_json: Any
    confidence: float
    status: str
    created_at: datetime


@dataclass(frozen=True)
class CatalogCandidateRecord:
    id: str
    candidate_type: str
    proposed_action: str
    canonical_name: str
    normalized_value_json: Any
    source_count: int
    evidence_count: int
    confidence: float
    status: str
    target_entity_type: str | None
    target_entity_id: str | None
    merge_target_candidate_id: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    created_by: str
    created_at: datetime
    updated_at: datetime


class CatalogCandidateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_extraction_run(self, **values) -> ExtractionRunRecord:  # type: ignore[no-untyped-def]
        run_id = new_id()
        self.session.execute(insert(extraction_runs_table).values(id=run_id, **values))
        return self.get_extraction_run(run_id)  # type: ignore[return-value]

    def get_extraction_run(self, run_id: str) -> ExtractionRunRecord | None:
        row = (
            self.session.execute(
                select(extraction_runs_table).where(extraction_runs_table.c.id == run_id)
            )
            .mappings()
            .first()
        )
        return ExtractionRunRecord(**dict(row)) if row is not None else None

    def update_extraction_run(self, run_id: str, **values) -> ExtractionRunRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(extraction_runs_table)
            .where(extraction_runs_table.c.id == run_id)
            .values(**values)
        )
        run = self.get_extraction_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def create_fact(self, **values) -> ExtractedFactRecord:  # type: ignore[no-untyped-def]
        fact_id = new_id()
        self.session.execute(insert(extracted_facts_table).values(id=fact_id, **values))
        return self.get_fact(fact_id)  # type: ignore[return-value]

    def get_fact(self, fact_id: str) -> ExtractedFactRecord | None:
        row = (
            self.session.execute(
                select(extracted_facts_table).where(extracted_facts_table.c.id == fact_id)
            )
            .mappings()
            .first()
        )
        return ExtractedFactRecord(**dict(row)) if row is not None else None

    def find_candidate(
        self,
        *,
        candidate_type: str,
        canonical_name: str,
        proposed_action: str,
    ) -> CatalogCandidateRecord | None:
        row = (
            self.session.execute(
                select(catalog_candidates_table).where(
                    catalog_candidates_table.c.candidate_type == candidate_type,
                    catalog_candidates_table.c.canonical_name == canonical_name,
                    catalog_candidates_table.c.proposed_action == proposed_action,
                )
            )
            .mappings()
            .first()
        )
        return CatalogCandidateRecord(**dict(row)) if row is not None else None

    def create_candidate(self, **values) -> CatalogCandidateRecord:  # type: ignore[no-untyped-def]
        candidate_id = new_id()
        self.session.execute(insert(catalog_candidates_table).values(id=candidate_id, **values))
        return self.get_candidate(candidate_id)  # type: ignore[return-value]

    def update_candidate(self, candidate_id: str, **values) -> CatalogCandidateRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(catalog_candidates_table)
            .where(catalog_candidates_table.c.id == candidate_id)
            .values(**values)
        )
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return candidate

    def get_candidate(self, candidate_id: str) -> CatalogCandidateRecord | None:
        row = (
            self.session.execute(
                select(catalog_candidates_table).where(
                    catalog_candidates_table.c.id == candidate_id
                )
            )
            .mappings()
            .first()
        )
        return CatalogCandidateRecord(**dict(row)) if row is not None else None

    def list_candidates(
        self,
        *,
        status: str | None = None,
        candidate_type: str | None = None,
        limit: int = 100,
    ) -> list[CatalogCandidateRecord]:
        query = select(catalog_candidates_table)
        if status:
            query = query.where(catalog_candidates_table.c.status == status)
        if candidate_type:
            query = query.where(catalog_candidates_table.c.candidate_type == candidate_type)
        rows = (
            self.session.execute(
                query.order_by(catalog_candidates_table.c.updated_at.desc()).limit(limit)
            )
            .mappings()
            .all()
        )
        return [CatalogCandidateRecord(**dict(row)) for row in rows]

    def list_candidate_evidence_details(self, candidate_id: str) -> list[dict[str, Any]]:
        artifact_id = func.coalesce(
            catalog_evidence_table.c.artifact_id,
            parsed_chunks_table.c.artifact_id,
        )
        rows = (
            self.session.execute(
                select(
                    catalog_evidence_table.c.id.label("evidence_id"),
                    catalog_evidence_table.c.source_id.label("evidence_source_id"),
                    catalog_evidence_table.c.artifact_id.label("evidence_artifact_id"),
                    catalog_evidence_table.c.chunk_id.label("evidence_chunk_id"),
                    catalog_evidence_table.c.quote.label("quote"),
                    catalog_evidence_table.c.page_number.label("page_number"),
                    catalog_evidence_table.c.location_json.label("location_json"),
                    catalog_evidence_table.c.extractor_version.label("extractor_version"),
                    catalog_evidence_table.c.evidence_type.label("evidence_type"),
                    catalog_evidence_table.c.confidence.label("evidence_confidence"),
                    catalog_evidence_table.c.created_by.label("evidence_created_by"),
                    catalog_evidence_table.c.created_at.label("evidence_created_at"),
                    sources_table.c.id.label("source_id"),
                    sources_table.c.source_type.label("source_type"),
                    sources_table.c.origin.label("source_origin"),
                    sources_table.c.external_id.label("source_external_id"),
                    sources_table.c.url.label("source_url"),
                    sources_table.c.title.label("source_title"),
                    sources_table.c.published_at.label("source_published_at"),
                    sources_table.c.raw_text.label("source_raw_text"),
                    parsed_chunks_table.c.id.label("chunk_id"),
                    parsed_chunks_table.c.chunk_index.label("chunk_index"),
                    parsed_chunks_table.c.text.label("chunk_text"),
                    parsed_chunks_table.c.parser_name.label("chunk_parser_name"),
                    parsed_chunks_table.c.parser_version.label("chunk_parser_version"),
                    artifacts_table.c.id.label("artifact_id"),
                    artifacts_table.c.file_name.label("artifact_file_name"),
                    artifacts_table.c.mime_type.label("artifact_mime_type"),
                    artifacts_table.c.file_size.label("artifact_file_size"),
                    artifacts_table.c.download_status.label("artifact_download_status"),
                )
                .select_from(
                    catalog_evidence_table.outerjoin(
                        sources_table,
                        catalog_evidence_table.c.source_id == sources_table.c.id,
                    )
                    .outerjoin(
                        parsed_chunks_table,
                        catalog_evidence_table.c.chunk_id == parsed_chunks_table.c.id,
                    )
                    .outerjoin(artifacts_table, artifact_id == artifacts_table.c.id)
                )
                .where(
                    catalog_evidence_table.c.entity_type == "catalog_candidate",
                    catalog_evidence_table.c.entity_id == candidate_id,
                )
                .order_by(catalog_evidence_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def ensure_candidate_fact_link(
        self,
        *,
        candidate_id: str,
        fact_id: str,
        created_at: datetime,
    ) -> bool:
        existing_id = self.session.execute(
            select(catalog_candidate_facts_table.c.id).where(
                catalog_candidate_facts_table.c.catalog_candidate_id == candidate_id,
                catalog_candidate_facts_table.c.extracted_fact_id == fact_id,
            )
        ).scalar_one_or_none()
        if existing_id is not None:
            return False
        self.session.execute(
            insert(catalog_candidate_facts_table).values(
                id=new_id(),
                catalog_candidate_id=candidate_id,
                extracted_fact_id=fact_id,
                created_at=created_at,
            )
        )
        return True

    def create_evidence(self, **values) -> str:  # type: ignore[no-untyped-def]
        existing_id = self.session.execute(
            select(catalog_evidence_table.c.id).where(
                catalog_evidence_table.c.entity_type == values["entity_type"],
                catalog_evidence_table.c.entity_id == values["entity_id"],
                catalog_evidence_table.c.source_id.is_(values["source_id"])
                if values["source_id"] is None
                else catalog_evidence_table.c.source_id == values["source_id"],
                catalog_evidence_table.c.artifact_id.is_(values["artifact_id"])
                if values["artifact_id"] is None
                else catalog_evidence_table.c.artifact_id == values["artifact_id"],
                catalog_evidence_table.c.chunk_id.is_(values["chunk_id"])
                if values["chunk_id"] is None
                else catalog_evidence_table.c.chunk_id == values["chunk_id"],
                catalog_evidence_table.c.evidence_type == values["evidence_type"],
            )
        ).scalar_one_or_none()
        if existing_id is not None:
            return existing_id
        evidence_id = new_id()
        self.session.execute(insert(catalog_evidence_table).values(id=evidence_id, **values))
        return evidence_id
