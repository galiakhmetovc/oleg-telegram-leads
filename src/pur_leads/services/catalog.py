"""Operational catalog behavior."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.catalog import (
    catalog_candidate_facts_table,
    catalog_items_table,
    catalog_offers_table,
    catalog_terms_table,
    extracted_facts_table,
)
from pur_leads.repositories.catalog import (
    CatalogCategoryRecord,
    CatalogRepository,
    CatalogTermRecord,
    CatalogVersionRecord,
)
from pur_leads.repositories.catalog_candidates import CatalogCandidateRepository

INITIAL_CATEGORIES = [
    ("video_surveillance", "Video Surveillance"),
    ("intercom", "Intercom"),
    ("security_alarm", "Security Alarm"),
    ("access_control", "Access Control"),
    ("networks_sks", "Networks / SKS"),
    ("smart_home_core", "Smart Home Core"),
    ("lighting_shades", "Lighting And Shades"),
    ("power_electric", "Power Electric"),
    ("climate_heating", "Climate And Heating"),
    ("audio_voice", "Audio And Voice"),
    ("project_service", "Project Service"),
]
INITIAL_CATEGORY_SLUGS = [slug for slug, _ in INITIAL_CATEGORIES]
DEFAULT_INCLUDED_STATUSES = ["approved", "auto_pending"]


@dataclass(frozen=True)
class PromotionResult:
    entity_type: str
    entity_id: str


class CatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogRepository(session)
        self.candidates = CatalogCandidateRepository(session)

    def seed_initial_categories(self) -> list[CatalogCategoryRecord]:
        now = utc_now()
        categories: list[CatalogCategoryRecord] = []
        for sort_order, (slug, name) in enumerate(INITIAL_CATEGORIES):
            existing = self.repository.find_category_by_slug(slug)
            if existing is not None:
                categories.append(existing)
                continue
            categories.append(
                self.repository.create_category(
                    parent_id=None,
                    slug=slug,
                    name=name,
                    description=None,
                    status="approved",
                    sort_order=sort_order,
                    created_at=now,
                    updated_at=now,
                )
            )
        self.session.commit()
        return categories

    def promote_candidate(self, candidate_id: str, *, actor: str) -> PromotionResult:
        candidate = self.candidates.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        fact = self._primary_fact(candidate_id)
        value = fact["value_json"] if fact is not None else candidate.normalized_value_json

        if candidate.candidate_type in {"lead_phrase", "negative_phrase"}:
            term = self._create_or_get_term_from_value(
                item_id=None,
                category_id=None,
                value=value,
                fallback_term=candidate.canonical_name,
                status=candidate.status,
                actor=actor,
                first_seen_source_id=fact["source_id"] if fact is not None else None,
            )
            self._copy_evidence(
                source_entities=[("catalog_candidate", candidate.id)]
                + ([("extracted_fact", fact["id"])] if fact is not None else []),
                target_entity_type="term",
                target_entity_id=term.id,
                created_by=actor,
            )
            self.session.commit()
            return PromotionResult(entity_type="term", entity_id=term.id)

        if candidate.candidate_type == "item":
            category = self._category_from_value(value)
            item = self.repository.find_item_by_canonical_name(candidate.canonical_name)
            now = utc_now()
            if item is None:
                item = self.repository.create_item(
                    category_id=category.id if category else None,
                    item_type=value.get("item_type", "product"),
                    name=candidate.canonical_name,
                    canonical_name=candidate.canonical_name,
                    description=value.get("description"),
                    status=candidate.status,
                    confidence=candidate.confidence,
                    first_seen_source_id=fact["source_id"] if fact is not None else None,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_by=actor,
                    created_at=now,
                    updated_at=now,
                )
            else:
                item = self.repository.update_item(
                    item.id,
                    last_seen_at=now,
                    updated_at=now,
                )

            self._copy_evidence(
                source_entities=[("catalog_candidate", candidate.id)]
                + ([("extracted_fact", fact["id"])] if fact is not None else []),
                target_entity_type="item",
                target_entity_id=item.id,
                created_by=actor,
            )
            for term_value in value.get("terms", []):
                term = self._create_or_get_term_from_value(
                    item_id=item.id,
                    category_id=item.category_id,
                    value={"term": term_value, "term_type": "alias"},
                    fallback_term=term_value,
                    status=item.status,
                    actor=actor,
                    first_seen_source_id=item.first_seen_source_id,
                )
                self._copy_evidence(
                    source_entities=[("catalog_candidate", candidate.id)],
                    target_entity_type="term",
                    target_entity_id=term.id,
                    created_by=actor,
                )
            self.session.commit()
            return PromotionResult(entity_type="item", entity_id=item.id)

        raise ValueError(f"Unsupported candidate type for promotion: {candidate.candidate_type}")

    def create_catalog_version(
        self,
        *,
        created_by: str,
        included_statuses: list[str] | None = None,
        notes: str | None = None,
    ) -> CatalogVersionRecord:
        statuses = included_statuses or DEFAULT_INCLUDED_STATUSES
        payload = self._catalog_hash_payload(statuses)
        version = self.repository.create_catalog_version(
            version=self.repository.next_catalog_version_number(),
            catalog_hash=_sha256_json(payload),
            candidate_hash=None,
            item_count=len(payload["items"]),
            term_count=len(payload["terms"]),
            offer_count=len(payload["offers"]),
            included_statuses_json=statuses,
            created_by=created_by,
            created_at=utc_now(),
            notes=notes,
        )
        self.session.commit()
        return version

    def _primary_fact(self, candidate_id: str) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(extracted_facts_table)
                .join(
                    catalog_candidate_facts_table,
                    catalog_candidate_facts_table.c.extracted_fact_id == extracted_facts_table.c.id,
                )
                .where(catalog_candidate_facts_table.c.catalog_candidate_id == candidate_id)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _category_from_value(self, value: dict[str, Any]) -> CatalogCategoryRecord | None:
        slug = value.get("category_slug")
        if not slug:
            return None
        existing = self.repository.find_category_by_slug(slug)
        if existing is not None:
            return existing
        self.seed_initial_categories()
        return self.repository.find_category_by_slug(slug)

    def _create_or_get_term_from_value(
        self,
        *,
        item_id: str | None,
        category_id: str | None,
        value: dict[str, Any],
        fallback_term: str,
        status: str,
        actor: str,
        first_seen_source_id: str | None,
    ) -> CatalogTermRecord:
        term_text = value.get("term") or fallback_term
        term_type = value.get("term_type", "alias")
        normalized = normalize_catalog_text(term_text)
        existing = self.repository.find_term(
            item_id=item_id,
            category_id=category_id,
            normalized_term=normalized,
            term_type=term_type,
        )
        if existing is not None:
            return existing
        now = utc_now()
        return self.repository.create_term(
            item_id=item_id,
            category_id=category_id,
            term=term_text,
            normalized_term=normalized,
            term_type=term_type,
            language=value.get("language", "ru"),
            status=status,
            weight=float(value.get("weight", 1.0)),
            created_by=actor,
            first_seen_source_id=first_seen_source_id,
            created_at=now,
            updated_at=now,
        )

    def _copy_evidence(
        self,
        *,
        source_entities: list[tuple[str, str]],
        target_entity_type: str,
        target_entity_id: str,
        created_by: str,
    ) -> None:
        for source_evidence in self.repository.list_evidence_for_entities(source_entities):
            self.repository.create_evidence(
                entity_type=target_entity_type,
                entity_id=target_entity_id,
                source_id=source_evidence["source_id"],
                artifact_id=source_evidence["artifact_id"],
                chunk_id=source_evidence["chunk_id"],
                quote=source_evidence["quote"],
                page_number=source_evidence["page_number"],
                location_json=source_evidence["location_json"],
                extractor_version=source_evidence["extractor_version"],
                evidence_type=source_evidence["evidence_type"],
                confidence=source_evidence["confidence"],
                created_by=created_by,
                created_at=utc_now(),
            )

    def _catalog_hash_payload(self, statuses: list[str]) -> dict[str, Any]:
        items = (
            self.session.execute(
                select(catalog_items_table).where(catalog_items_table.c.status.in_(statuses))
            )
            .mappings()
            .all()
        )
        terms = (
            self.session.execute(
                select(catalog_terms_table).where(catalog_terms_table.c.status.in_(statuses))
            )
            .mappings()
            .all()
        )
        offers = (
            self.session.execute(
                select(catalog_offers_table).where(catalog_offers_table.c.status.in_(statuses))
            )
            .mappings()
            .all()
        )
        return {
            "items": _sorted_rows(items),
            "terms": _sorted_rows(terms),
            "offers": _sorted_rows(offers),
        }


def normalize_catalog_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _serializable_row(row) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    result = {}
    for key, value in dict(row).items():
        result[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return result


def _sorted_rows(rows) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    serialized = [_serializable_row(row) for row in rows]
    return sorted(serialized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
