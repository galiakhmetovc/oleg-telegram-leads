"""Catalog extraction, candidate, and evidence behavior."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.catalog_candidates import (
    CatalogCandidateRecord,
    CatalogCandidateRepository,
    ExtractedFactRecord,
    ExtractionRunRecord,
)

LOW_CONFIDENCE_THRESHOLD = 0.6


class CatalogCandidateService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogCandidateRepository(session)

    def start_extraction_run(
        self,
        *,
        run_type: str,
        extractor_version: str,
        model: str | None = None,
        prompt_version: str | None = None,
        catalog_version_id: str | None = None,
        source_scope_json: Any = None,
    ) -> ExtractionRunRecord:
        run = self.repository.create_extraction_run(
            run_type=run_type,
            model=model,
            prompt_version=prompt_version,
            catalog_version_id=catalog_version_id,
            started_at=utc_now(),
            finished_at=None,
            status="running",
            error=None,
            stats_json=None,
            source_scope_json=source_scope_json,
            extractor_version=extractor_version,
            candidate_count=0,
            fact_count=0,
            created_catalog_entity_count=0,
            token_usage_json=None,
        )
        self.session.commit()
        return run

    def finish_extraction_run(
        self,
        run_id: str,
        *,
        status: str,
        error: str | None = None,
        stats_json: Any = None,
        token_usage_json: Any = None,
    ) -> ExtractionRunRecord:
        run = self.repository.update_extraction_run(
            run_id,
            status=status,
            error=error,
            stats_json=stats_json,
            token_usage_json=token_usage_json,
            finished_at=utc_now(),
        )
        self.session.commit()
        return run

    def create_extracted_fact(
        self,
        *,
        extraction_run_id: str,
        fact_type: str,
        canonical_name: str,
        value_json: Any,
        confidence: float,
        source_id: str | None = None,
        chunk_id: str | None = None,
    ) -> ExtractedFactRecord:
        fact = self.repository.create_fact(
            extraction_run_id=extraction_run_id,
            source_id=source_id,
            chunk_id=chunk_id,
            fact_type=fact_type,
            canonical_name=canonical_name,
            value_json=value_json,
            confidence=confidence,
            status="new",
            created_at=utc_now(),
        )
        self._increment_run_counter(extraction_run_id, fact_count=1)
        self.session.commit()
        return fact

    def create_or_update_candidate_from_fact(
        self,
        fact_id: str,
        *,
        candidate_type: str,
        proposed_action: str = "create",
        evidence_quote: str | None = None,
        created_by: str = "system",
    ) -> CatalogCandidateRecord:
        fact = self.repository.get_fact(fact_id)
        if fact is None:
            raise KeyError(fact_id)

        now = utc_now()
        existing = self.repository.find_candidate(
            candidate_type=candidate_type,
            canonical_name=fact.canonical_name,
            proposed_action=proposed_action,
        )
        if existing is None:
            candidate = self.repository.create_candidate(
                candidate_type=candidate_type,
                proposed_action=proposed_action,
                canonical_name=fact.canonical_name,
                normalized_value_json=_normalized_value(fact.value_json),
                source_count=1 if fact.source_id else 0,
                evidence_count=1,
                confidence=fact.confidence,
                status=_candidate_status(fact, candidate_type),
                target_entity_type=None,
                target_entity_id=None,
                merge_target_candidate_id=None,
                first_seen_at=now,
                last_seen_at=now,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            self._increment_run_counter(fact.extraction_run_id, candidate_count=1)
        else:
            candidate = self.repository.update_candidate(
                existing.id,
                source_count=max(existing.source_count, 1 if fact.source_id else 0),
                evidence_count=max(existing.evidence_count, 1),
                confidence=max(existing.confidence, fact.confidence),
                last_seen_at=now,
                updated_at=now,
            )

        self.repository.ensure_candidate_fact_link(
            candidate_id=candidate.id,
            fact_id=fact.id,
            created_at=now,
        )
        self._create_evidence_rows(candidate, fact, evidence_quote, created_by, now)
        self.session.commit()
        return candidate

    def _create_evidence_rows(
        self,
        candidate: CatalogCandidateRecord,
        fact: ExtractedFactRecord,
        evidence_quote: str | None,
        created_by: str,
        created_at,
    ) -> None:  # type: ignore[no-untyped-def]
        for entity_type, entity_id in (
            ("catalog_candidate", candidate.id),
            ("extracted_fact", fact.id),
        ):
            self.repository.create_evidence(
                entity_type=entity_type,
                entity_id=entity_id,
                source_id=fact.source_id,
                artifact_id=None,
                chunk_id=fact.chunk_id,
                quote=evidence_quote,
                page_number=None,
                location_json=None,
                extractor_version=None,
                evidence_type="ai_quote",
                confidence=fact.confidence,
                created_by=created_by,
                created_at=created_at,
            )

    def _increment_run_counter(
        self,
        run_id: str,
        *,
        fact_count: int = 0,
        candidate_count: int = 0,
    ) -> None:
        run = self.repository.get_extraction_run(run_id)
        if run is None:
            raise KeyError(run_id)
        self.repository.update_extraction_run(
            run_id,
            fact_count=run.fact_count + fact_count,
            candidate_count=run.candidate_count + candidate_count,
        )


def _normalized_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: value[key] for key in sorted(value)}
    return value


def _candidate_status(fact: ExtractedFactRecord, candidate_type: str) -> str:
    if fact.confidence < LOW_CONFIDENCE_THRESHOLD:
        return "needs_review"
    value = fact.value_json if isinstance(fact.value_json, dict) else {}
    if value.get("conflict") or value.get("too_broad"):
        return "needs_review"
    if candidate_type == "offer":
        if (
            value.get("valid_to")
            or value.get("ttl_days")
            or value.get("ttl_source")
            in {
                "explicit",
                "default_setting",
                "manual",
            }
        ):
            return "auto_pending"
        return "needs_review"
    return "auto_pending"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
