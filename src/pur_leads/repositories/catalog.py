"""Operational catalog persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_evidence_table,
    catalog_items_table,
    catalog_terms_table,
    catalog_versions_table,
)


@dataclass(frozen=True)
class CatalogCategoryRecord:
    id: str
    parent_id: str | None
    slug: str
    name: str
    description: str | None
    status: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CatalogItemRecord:
    id: str
    category_id: str | None
    item_type: str
    name: str
    canonical_name: str
    description: str | None
    status: str
    confidence: float | None
    first_seen_source_id: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CatalogTermRecord:
    id: str
    item_id: str | None
    category_id: str | None
    term: str
    normalized_term: str
    term_type: str
    language: str
    status: str
    weight: float
    created_by: str
    first_seen_source_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CatalogVersionRecord:
    id: str
    version: int
    catalog_hash: str
    candidate_hash: str | None
    item_count: int
    term_count: int
    offer_count: int
    included_statuses_json: Any
    created_by: str
    created_at: datetime
    notes: str | None


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_category_by_slug(self, slug: str) -> CatalogCategoryRecord | None:
        row = (
            self.session.execute(
                select(catalog_categories_table).where(catalog_categories_table.c.slug == slug)
            )
            .mappings()
            .first()
        )
        return CatalogCategoryRecord(**dict(row)) if row is not None else None

    def create_category(self, **values) -> CatalogCategoryRecord:  # type: ignore[no-untyped-def]
        category_id = new_id()
        self.session.execute(insert(catalog_categories_table).values(id=category_id, **values))
        return self.find_category_by_slug(values["slug"])  # type: ignore[return-value]

    def find_item_by_canonical_name(self, canonical_name: str) -> CatalogItemRecord | None:
        row = (
            self.session.execute(
                select(catalog_items_table).where(
                    catalog_items_table.c.canonical_name == canonical_name
                )
            )
            .mappings()
            .first()
        )
        return CatalogItemRecord(**dict(row)) if row is not None else None

    def create_item(self, **values) -> CatalogItemRecord:  # type: ignore[no-untyped-def]
        item_id = new_id()
        self.session.execute(insert(catalog_items_table).values(id=item_id, **values))
        return self.get_item(item_id)  # type: ignore[return-value]

    def update_item(self, item_id: str, **values) -> CatalogItemRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(catalog_items_table).where(catalog_items_table.c.id == item_id).values(**values)
        )
        item = self.get_item(item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def get_item(self, item_id: str) -> CatalogItemRecord | None:
        row = (
            self.session.execute(
                select(catalog_items_table).where(catalog_items_table.c.id == item_id)
            )
            .mappings()
            .first()
        )
        return CatalogItemRecord(**dict(row)) if row is not None else None

    def find_term(
        self,
        *,
        item_id: str | None,
        category_id: str | None,
        normalized_term: str,
        term_type: str,
    ) -> CatalogTermRecord | None:
        conditions = [
            catalog_terms_table.c.normalized_term == normalized_term,
            catalog_terms_table.c.term_type == term_type,
        ]
        conditions.append(
            catalog_terms_table.c.item_id.is_(None)
            if item_id is None
            else catalog_terms_table.c.item_id == item_id
        )
        conditions.append(
            catalog_terms_table.c.category_id.is_(None)
            if category_id is None
            else catalog_terms_table.c.category_id == category_id
        )
        row = (
            self.session.execute(select(catalog_terms_table).where(*conditions)).mappings().first()
        )
        return CatalogTermRecord(**dict(row)) if row is not None else None

    def create_term(self, **values) -> CatalogTermRecord:  # type: ignore[no-untyped-def]
        term_id = new_id()
        self.session.execute(insert(catalog_terms_table).values(id=term_id, **values))
        return self.get_term(term_id)  # type: ignore[return-value]

    def get_term(self, term_id: str) -> CatalogTermRecord | None:
        row = (
            self.session.execute(
                select(catalog_terms_table).where(catalog_terms_table.c.id == term_id)
            )
            .mappings()
            .first()
        )
        return CatalogTermRecord(**dict(row)) if row is not None else None

    def create_evidence(self, **values) -> str:  # type: ignore[no-untyped-def]
        evidence_id = new_id()
        self.session.execute(insert(catalog_evidence_table).values(id=evidence_id, **values))
        return evidence_id

    def list_evidence_for_entities(self, entities: list[tuple[str, str]]) -> list[dict[str, Any]]:
        if not entities:
            return []
        rows: list[dict[str, Any]] = []
        for entity_type, entity_id in entities:
            rows.extend(
                dict(row)
                for row in self.session.execute(
                    select(catalog_evidence_table).where(
                        catalog_evidence_table.c.entity_type == entity_type,
                        catalog_evidence_table.c.entity_id == entity_id,
                    )
                )
                .mappings()
                .all()
            )
        return rows

    def next_catalog_version_number(self) -> int:
        current = self.session.execute(select(func.max(catalog_versions_table.c.version))).scalar()
        return int(current or 0) + 1

    def create_catalog_version(self, **values) -> CatalogVersionRecord:  # type: ignore[no-untyped-def]
        version_id = new_id()
        self.session.execute(insert(catalog_versions_table).values(id=version_id, **values))
        row = (
            self.session.execute(
                select(catalog_versions_table).where(catalog_versions_table.c.id == version_id)
            )
            .mappings()
            .one()
        )
        return CatalogVersionRecord(**dict(row))
