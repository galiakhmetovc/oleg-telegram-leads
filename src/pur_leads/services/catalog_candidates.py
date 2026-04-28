"""Catalog extraction, candidate, and evidence behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.repositories.catalog_candidates import (
    CatalogCandidateRecord,
    CatalogCandidateRepository,
    ExtractedFactRecord,
    ExtractionRunRecord,
)
from pur_leads.services.audit import AuditService

PROMOTABLE_CANDIDATE_TYPES = {"item", "lead_phrase", "negative_phrase"}

LOW_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class CandidateReviewResult:
    candidate: CatalogCandidateRecord
    promotion: Any | None


@dataclass(frozen=True)
class CandidateDetailResult:
    candidate: CatalogCandidateRecord
    evidence: list[dict[str, Any]]


class CatalogCandidateService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogCandidateRepository(session)
        self.audit = AuditService(session)

    def list_candidates(
        self,
        *,
        status: str | None = None,
        candidate_type: str | None = None,
        limit: int = 100,
    ) -> list[CatalogCandidateRecord]:
        return self.repository.list_candidates(
            status=status,
            candidate_type=candidate_type,
            limit=limit,
        )

    def get_candidate_detail(self, candidate_id: str) -> CandidateDetailResult:
        candidate = self.repository.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return CandidateDetailResult(
            candidate=candidate,
            evidence=self.repository.list_candidate_evidence_details(candidate_id),
        )

    def update_candidate(
        self,
        candidate_id: str,
        *,
        actor: str,
        canonical_name: str | None = None,
        normalized_value: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> CatalogCandidateRecord:
        before = self.repository.get_candidate(candidate_id)
        if before is None:
            raise KeyError(candidate_id)

        values: dict[str, Any] = {}
        if canonical_name is not None:
            normalized_name = canonical_name.strip()
            if not normalized_name:
                raise ValueError("canonical_name must not be empty")
            values["canonical_name"] = normalized_name
        if normalized_value is not None:
            values["normalized_value_json"] = _normalized_value(normalized_value)
        if not values:
            return before

        candidate = self.repository.update_candidate(
            candidate_id,
            **values,
            updated_at=utc_now(),
        )
        self.audit.record_change(
            actor=actor,
            action="catalog_candidate.update",
            entity_type="catalog_candidate",
            entity_id=candidate_id,
            old_value_json={
                "canonical_name": before.canonical_name,
                "normalized_value": before.normalized_value_json,
            },
            new_value_json={
                "canonical_name": candidate.canonical_name,
                "normalized_value": candidate.normalized_value_json,
                "reason": reason,
            },
        )
        self.session.commit()
        return candidate

    def review_candidate(
        self,
        candidate_id: str,
        *,
        action: str,
        actor: str,
        reason: str | None = None,
    ) -> CandidateReviewResult:
        before = self.repository.get_candidate(candidate_id)
        if before is None:
            raise KeyError(candidate_id)

        status = _review_status(action)
        candidate = self.repository.update_candidate(
            candidate_id,
            status=status,
            updated_at=utc_now(),
        )
        self.audit.record_change(
            actor=actor,
            action="catalog_candidate.review",
            entity_type="catalog_candidate",
            entity_id=candidate_id,
            old_value_json={"status": before.status},
            new_value_json={"status": status, "review_action": action, "reason": reason},
        )

        promotion = None
        if action == "approve" and candidate.candidate_type in PROMOTABLE_CANDIDATE_TYPES:
            from pur_leads.services.catalog import CatalogService

            promotion = CatalogService(self.session).promote_candidate(candidate.id, actor=actor)
        else:
            self.session.commit()
        reviewed = self.repository.get_candidate(candidate_id)
        if reviewed is None:
            raise KeyError(candidate_id)
        return CandidateReviewResult(candidate=reviewed, promotion=promotion)

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


def _review_status(action: str) -> str:
    statuses = {
        "approve": "approved",
        "reject": "rejected",
        "needs_review": "needs_review",
        "mute": "muted",
    }
    try:
        return statuses[action]
    except KeyError as exc:
        raise ValueError(f"Unsupported review action: {action}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
