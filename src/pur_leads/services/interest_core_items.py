"""Approved working interest-core items."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import desc, func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.interest_context_drafts import (
    interest_core_candidate_reviews_table,
    interest_core_items_table,
)
from pur_leads.services.audit import AuditService


@dataclass(frozen=True)
class InterestCoreItemRecord:
    id: str
    context_id: str
    source_review_id: str | None
    source_candidate_id: str | None
    item_type: str
    canonical_name: str
    category: str | None
    description: str | None
    confidence: str
    status: str
    synonyms_json: Any
    lead_signals_json: Any
    noise_patterns_json: Any
    evidence_refs_json: Any
    metadata_json: Any
    created_by: str
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


class InterestCoreItemService:
    """Maintain the approved, operator-visible interest core."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def latest_payload(
        self,
        context_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        total = self.item_count(context_id)
        rows = self.list_items(context_id, limit=limit, offset=offset)
        return {
            "summary": {"total": total, "page_count": len(rows)},
            "items": [row.as_jsonable() for row in rows],
            "pagination": _pagination(limit=limit, offset=offset, total=total),
        }

    def list_items(
        self,
        context_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[InterestCoreItemRecord]:
        rows = (
            self.session.execute(
                select(interest_core_items_table)
                .where(interest_core_items_table.c.context_id == context_id)
                .where(interest_core_items_table.c.status == "active")
                .order_by(desc(interest_core_items_table.c.updated_at))
                .limit(max(1, limit))
                .offset(max(0, offset))
            )
            .mappings()
            .all()
        )
        return [_record(row) for row in rows]

    def item_count(self, context_id: str) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(interest_core_items_table)
                .where(interest_core_items_table.c.context_id == context_id)
                .where(interest_core_items_table.c.status == "active")
            ).scalar_one()
            or 0
        )

    def apply_review(self, review_id: str, *, actor: str) -> InterestCoreItemRecord:
        review = (
            self.session.execute(
                select(interest_core_candidate_reviews_table).where(
                    interest_core_candidate_reviews_table.c.id == review_id
                )
            )
            .mappings()
            .first()
        )
        if review is None:
            raise KeyError(review_id)
        title = str(review["canonical_name"] or review["source_candidate_id"] or "").strip()
        if not title:
            raise ValueError("Review has no canonical name")
        existing = self._find_existing_item(
            context_id=str(review["context_id"]),
            canonical_name=title,
        )
        now = utc_now()
        values = {
            "source_review_id": review_id,
            "source_candidate_id": review["source_candidate_id"],
            "item_type": "interest",
            "canonical_name": title[:300],
            "category": review["category"],
            "description": review["description"] or review["rationale"],
            "confidence": review["confidence"] or "medium",
            "status": "active",
            "synonyms_json": review["synonyms_json"] or [],
            "lead_signals_json": review["lead_signals_json"] or [],
            "noise_patterns_json": review["noise_patterns_json"] or [],
            "evidence_refs_json": review["evidence_refs_json"] or [],
            "metadata_json": {
                "source": "llm_candidate_review",
                "review_decision": review["decision"],
                "review_recommendation_type": review["recommendation_type"],
                "review_metadata": review["metadata_json"],
            },
            "updated_at": now,
        }
        if existing is None:
            item_id = new_id()
            self.session.execute(
                insert(interest_core_items_table).values(
                    id=item_id,
                    context_id=review["context_id"],
                    created_by=actor,
                    created_at=now,
                    **values,
                )
            )
        else:
            item_id = existing.id
            self.session.execute(
                update(interest_core_items_table)
                .where(interest_core_items_table.c.id == item_id)
                .values(**values)
            )
        self.session.commit()
        item = self._get(item_id)
        if item is None:
            raise KeyError(item_id)
        self.audit.record_change(
            actor=actor,
            action="interest_core_items.apply_review",
            entity_type="interest_core_item",
            entity_id=item.id,
            old_value_json=None if existing is None else existing.as_jsonable(),
            new_value_json=item.as_jsonable(),
        )
        return item

    def _find_existing_item(
        self,
        *,
        context_id: str,
        canonical_name: str,
    ) -> InterestCoreItemRecord | None:
        row = (
            self.session.execute(
                select(interest_core_items_table)
                .where(interest_core_items_table.c.context_id == context_id)
                .where(interest_core_items_table.c.status == "active")
                .where(func.lower(interest_core_items_table.c.canonical_name) == canonical_name.lower())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return _record(row) if row is not None else None

    def _get(self, item_id: str) -> InterestCoreItemRecord | None:
        row = (
            self.session.execute(
                select(interest_core_items_table).where(interest_core_items_table.c.id == item_id)
            )
            .mappings()
            .first()
        )
        return _record(row) if row is not None else None


def _record(row: Any) -> InterestCoreItemRecord:
    return InterestCoreItemRecord(**dict(row))


def _pagination(*, limit: int, offset: int, total: int) -> dict[str, Any]:
    safe_limit = max(1, int(limit))
    safe_offset = max(0, int(offset))
    safe_total = max(0, int(total))
    return {
        "limit": safe_limit,
        "offset": safe_offset,
        "total": safe_total,
        "has_more": safe_offset + safe_limit < safe_total,
    }
