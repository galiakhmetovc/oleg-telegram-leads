"""Review records for LLM interest-core candidate recommendations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import delete, desc, func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.interest_context_drafts import interest_core_candidate_reviews_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.services.audit import AuditService
from pur_leads.services.interest_core_candidate_enhancement import (
    ENHANCE_INTEREST_CORE_CANDIDATES_JOB,
)

REVIEW_STATUSES = {"pending_review", "approved", "rejected", "applied"}


@dataclass(frozen=True)
class InterestCoreCandidateReviewRecord:
    id: str
    context_id: str
    enhancement_job_id: str
    draft_run_id: str | None
    source_candidate_id: str | None
    recommendation_type: str
    canonical_name: str | None
    category: str | None
    decision: str
    merge_into_candidate_id: str | None
    confidence: str
    description: str | None
    synonyms_json: Any
    lead_signals_json: Any
    noise_patterns_json: Any
    evidence_refs_json: Any
    rationale: str | None
    status: str
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: Any
    applied_at: Any
    metadata_json: Any
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


class InterestCoreCandidateReviewService:
    """Persist and review LLM recommendations separately from scheduler jobs."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def latest_payload(self, context_id: str) -> dict[str, Any]:
        latest_job = self.latest_enhancement_job(context_id)
        if latest_job is not None:
            self.ensure_job_reviews(latest_job)
        rows = self.list_reviews(
            context_id,
            enhancement_job_id=str(latest_job["id"]) if latest_job is not None else None,
        )
        return {
            "latest_job": dict(latest_job) if latest_job is not None else None,
            "summary": _summary(rows),
            "items": [row.as_jsonable() for row in rows],
        }

    def latest_enhancement_job(self, context_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(scheduler_jobs_table)
                .where(scheduler_jobs_table.c.job_type == ENHANCE_INTEREST_CORE_CANDIDATES_JOB)
                .where(scheduler_jobs_table.c.scope_type == "interest_context")
                .where(scheduler_jobs_table.c.scope_id == context_id)
                .where(scheduler_jobs_table.c.status == "succeeded")
                .order_by(desc(scheduler_jobs_table.c.created_at))
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def ensure_job_reviews(self, job: dict[str, Any]) -> int:
        job_id = str(job["id"])
        count = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_core_candidate_reviews_table)
                .where(interest_core_candidate_reviews_table.c.enhancement_job_id == job_id)
            ).scalar_one()
            or 0
        )
        if count:
            return count
        result = job.get("result_summary_json")
        if not isinstance(result, dict):
            return 0
        return self.replace_from_enhancement_result(
            context_id=str(job["scope_id"]),
            enhancement_job_id=job_id,
            result_summary=result,
            actor=str((job.get("payload_json") or {}).get("requested_by") or "worker")
            if isinstance(job.get("payload_json"), dict)
            else "worker",
        )

    def replace_from_enhancement_result(
        self,
        *,
        context_id: str,
        enhancement_job_id: str,
        result_summary: dict[str, Any],
        actor: str,
    ) -> int:
        if result_summary.get("kind") != "interest_core_candidate_enhancement":
            return 0
        if result_summary.get("status") != "succeeded":
            return 0
        result = result_summary.get("result")
        if not isinstance(result, dict):
            return 0
        now = utc_now()
        self.session.execute(
            delete(interest_core_candidate_reviews_table).where(
                interest_core_candidate_reviews_table.c.enhancement_job_id
                == enhancement_job_id
            )
        )
        rows = _review_rows(
            context_id=context_id,
            enhancement_job_id=enhancement_job_id,
            draft_run_id=_optional_text(result_summary.get("draft_run_id")),
            result=result,
            result_summary=result_summary,
            now=now,
        )
        if rows:
            self.session.execute(insert(interest_core_candidate_reviews_table), rows)
        self.session.commit()
        self.audit.record_change(
            actor=actor,
            action="interest_core_candidate_reviews.replace_from_llm",
            entity_type="interest_context",
            entity_id=context_id,
            old_value_json=None,
            new_value_json={
                "enhancement_job_id": enhancement_job_id,
                "review_count": len(rows),
                "summary": _counts_from_result(result),
            },
        )
        return len(rows)

    def list_reviews(
        self,
        context_id: str,
        *,
        enhancement_job_id: str | None = None,
        limit: int = 300,
    ) -> list[InterestCoreCandidateReviewRecord]:
        query = select(interest_core_candidate_reviews_table).where(
            interest_core_candidate_reviews_table.c.context_id == context_id
        )
        if enhancement_job_id:
            query = query.where(
                interest_core_candidate_reviews_table.c.enhancement_job_id
                == enhancement_job_id
            )
        rows = (
            self.session.execute(
                query.order_by(
                    interest_core_candidate_reviews_table.c.recommendation_type,
                    interest_core_candidate_reviews_table.c.status,
                    desc(interest_core_candidate_reviews_table.c.created_at),
                ).limit(max(1, limit))
            )
            .mappings()
            .all()
        )
        return [_record(row) for row in rows]

    def set_status(
        self,
        review_id: str,
        *,
        status: str,
        actor: str,
        note: str | None = None,
        context_id: str | None = None,
    ) -> InterestCoreCandidateReviewRecord:
        if status not in REVIEW_STATUSES:
            raise ValueError("Unsupported review status")
        before = self._get(review_id)
        if before is None:
            raise KeyError(review_id)
        if context_id is not None and before.context_id != context_id:
            raise KeyError(review_id)
        now = utc_now()
        self.session.execute(
            update(interest_core_candidate_reviews_table)
            .where(interest_core_candidate_reviews_table.c.id == review_id)
            .values(
                status=status,
                review_note=note,
                reviewed_by=actor,
                reviewed_at=now,
                updated_at=now,
                applied_at=now if status == "applied" else before.applied_at,
            )
        )
        self.session.commit()
        after = self._get(review_id)
        if after is None:
            raise KeyError(review_id)
        self.audit.record_change(
            actor=actor,
            action="interest_core_candidate_reviews.set_status",
            entity_type="interest_core_candidate_review",
            entity_id=review_id,
            old_value_json={"status": before.status, "review_note": before.review_note},
            new_value_json={"status": after.status, "review_note": after.review_note},
        )
        return after

    def _get(self, review_id: str) -> InterestCoreCandidateReviewRecord | None:
        row = (
            self.session.execute(
                select(interest_core_candidate_reviews_table).where(
                    interest_core_candidate_reviews_table.c.id == review_id
                )
            )
            .mappings()
            .first()
        )
        return _record(row) if row is not None else None


def _review_rows(
    *,
    context_id: str,
    enhancement_job_id: str,
    draft_run_id: str | None,
    result: dict[str, Any],
    result_summary: dict[str, Any],
    now: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    common_metadata = {
        "brief_id": result_summary.get("brief_id"),
        "brief_version": result_summary.get("brief_version"),
        "prompt_version": result_summary.get("prompt_version"),
        "provider": result_summary.get("provider"),
        "model": result_summary.get("model"),
        "model_profile": result_summary.get("model_profile"),
        "ai_provider_account_id": result_summary.get("ai_provider_account_id"),
        "ai_model_id": result_summary.get("ai_model_id"),
        "ai_model_profile_id": result_summary.get("ai_model_profile_id"),
        "ai_agent_route_id": result_summary.get("ai_agent_route_id"),
    }
    for item in _object_list(result.get("improved_candidates")):
        rows.append(
            _base_row(
                context_id=context_id,
                enhancement_job_id=enhancement_job_id,
                draft_run_id=draft_run_id,
                recommendation_type="improved",
                source_candidate_id=_optional_text(item.get("source_candidate_id"), 80),
                canonical_name=_optional_text(item.get("canonical_name"), 300),
                category=_optional_text(item.get("category"), 160),
                decision=_enum(
                    item.get("decision"),
                    {"keep", "merge", "reject", "needs_review"},
                    "needs_review",
                ),
                confidence=_enum(item.get("confidence"), {"low", "medium", "high"}, "medium"),
                description=_optional_text(item.get("description")),
                synonyms=item.get("synonyms"),
                lead_signals=item.get("lead_signals"),
                noise_patterns=item.get("noise_patterns"),
                evidence_refs=item.get("evidence_refs"),
                rationale=_optional_text(item.get("rationale")),
                merge_into_candidate_id=_optional_text(item.get("merge_into_candidate_id"), 80),
                metadata_json={**common_metadata, "raw": item},
                now=now,
            )
        )
    for item in _object_list(result.get("new_candidates")):
        rows.append(
            _base_row(
                context_id=context_id,
                enhancement_job_id=enhancement_job_id,
                draft_run_id=draft_run_id,
                recommendation_type="new",
                source_candidate_id=None,
                canonical_name=_optional_text(item.get("canonical_name"), 300),
                category=_optional_text(item.get("category"), 160),
                decision="new",
                confidence=_enum(item.get("confidence"), {"low", "medium", "high"}, "medium"),
                description=_optional_text(item.get("description")),
                synonyms=item.get("synonyms"),
                lead_signals=item.get("lead_signals"),
                noise_patterns=item.get("noise_patterns"),
                evidence_refs=item.get("evidence_refs"),
                rationale=_optional_text(item.get("rationale")),
                merge_into_candidate_id=None,
                metadata_json={**common_metadata, "raw": item},
                now=now,
            )
        )
    for item in _object_list(result.get("rejected_candidates")):
        rows.append(
            _base_row(
                context_id=context_id,
                enhancement_job_id=enhancement_job_id,
                draft_run_id=draft_run_id,
                recommendation_type="rejected",
                source_candidate_id=_optional_text(item.get("source_candidate_id"), 80),
                canonical_name=None,
                category=None,
                decision="reject",
                confidence="medium",
                description=None,
                synonyms=[],
                lead_signals=[],
                noise_patterns=[],
                evidence_refs=[],
                rationale=_optional_text(item.get("reason")),
                merge_into_candidate_id=None,
                metadata_json={**common_metadata, "raw": item},
                now=now,
            )
        )
    return rows


def _base_row(
    *,
    context_id: str,
    enhancement_job_id: str,
    draft_run_id: str | None,
    recommendation_type: str,
    source_candidate_id: str | None,
    canonical_name: str | None,
    category: str | None,
    decision: str,
    merge_into_candidate_id: str | None,
    confidence: str,
    description: str | None,
    synonyms: Any,
    lead_signals: Any,
    noise_patterns: Any,
    evidence_refs: Any,
    rationale: str | None,
    metadata_json: dict[str, Any],
    now: Any,
) -> dict[str, Any]:
    return {
        "id": new_id(),
        "context_id": context_id,
        "enhancement_job_id": enhancement_job_id,
        "draft_run_id": draft_run_id,
        "source_candidate_id": source_candidate_id,
        "recommendation_type": recommendation_type,
        "canonical_name": canonical_name,
        "category": category,
        "decision": decision,
        "merge_into_candidate_id": merge_into_candidate_id,
        "confidence": confidence,
        "description": description,
        "synonyms_json": _string_list(synonyms),
        "lead_signals_json": _string_list(lead_signals),
        "noise_patterns_json": _string_list(noise_patterns),
        "evidence_refs_json": _string_list(evidence_refs),
        "rationale": rationale,
        "status": "pending_review",
        "review_note": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "applied_at": None,
        "metadata_json": metadata_json,
        "created_at": now,
        "updated_at": now,
    }


def _record(row: Any) -> InterestCoreCandidateReviewRecord:
    return InterestCoreCandidateReviewRecord(**dict(row))


def _summary(rows: list[InterestCoreCandidateReviewRecord]) -> dict[str, Any]:
    result = {
        "total": len(rows),
        "by_type": {},
        "by_status": {},
    }
    for row in rows:
        result["by_type"][row.recommendation_type] = (
            result["by_type"].get(row.recommendation_type, 0) + 1
        )
        result["by_status"][row.status] = result["by_status"].get(row.status, 0) + 1
    return result


def _counts_from_result(result: dict[str, Any]) -> dict[str, int]:
    return {
        "improved": len(_object_list(result.get("improved_candidates"))),
        "new": len(_object_list(result.get("new_candidates"))),
        "rejected": len(_object_list(result.get("rejected_candidates"))),
    }


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:40]


def _optional_text(value: Any, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length] if max_length else text


def _enum(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default
