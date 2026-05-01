"""Manual catalog editing behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.catalog import (
    catalog_attributes_table,
    catalog_evidence_table,
    catalog_items_table,
    catalog_offers_table,
    catalog_terms_table,
)
from pur_leads.repositories.catalog import CatalogItemRecord, CatalogRepository, CatalogTermRecord
from pur_leads.services.audit import AuditService
from pur_leads.services.catalog import CatalogService, normalize_catalog_text
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.classifier_snapshots import ClassifierSnapshotService

ARCHIVED_ITEM_STATUS = "deprecated"
ARCHIVED_OFFER_STATUS = "expired"
DEFAULT_STATUS = "approved"
MANUAL_EVIDENCE_TYPE = "manual_note"


@dataclass(frozen=True)
class CatalogOfferRecord:
    id: str
    item_id: str | None
    category_id: str | None
    offer_type: str
    title: str
    description: str | None
    price_amount: float | None
    currency: str | None
    price_text: str | None
    terms_json: Any
    status: str
    valid_from: datetime | None
    valid_to: datetime | None
    ttl_days: int | None
    ttl_source: str
    first_seen_source_id: str | None
    last_seen_source_id: str | None
    last_seen_at: datetime | None
    expired_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ManualCatalogItemDetail:
    item: CatalogItemRecord
    terms: list[CatalogTermRecord]
    offers: list[CatalogOfferRecord]
    attributes: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


class CatalogEditorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogRepository(session)
        self.audit = AuditService(session)

    def list_items(self, *, status: str | None = None, limit: int = 100) -> list[CatalogItemRecord]:
        query = select(catalog_items_table)
        if status:
            query = query.where(catalog_items_table.c.status == status)
        rows = (
            self.session.execute(
                query.order_by(catalog_items_table.c.updated_at.desc()).limit(limit)
            )
            .mappings()
            .all()
        )
        return [CatalogItemRecord(**dict(row)) for row in rows]

    def get_item_detail(self, item_id: str) -> ManualCatalogItemDetail:
        item = self.repository.get_item(item_id)
        if item is None:
            raise KeyError(item_id)
        return ManualCatalogItemDetail(
            item=item,
            terms=self._list_terms(item_id),
            offers=self._list_offers(item_id),
            attributes=self._list_attributes(item_id),
            evidence=self._list_evidence("item", item_id),
        )

    def create_item(
        self,
        *,
        actor: str,
        name: str,
        item_type: str,
        category_slug: str | None = None,
        description: str | None = None,
        terms: list[dict[str, Any]] | None = None,
        offers: list[dict[str, Any]] | None = None,
        attributes: list[dict[str, Any]] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> CatalogItemRecord:
        now = utc_now()
        cleaned_name = _required_text(name, "name")
        category_id = self._category_id(category_slug)
        item = self.repository.create_item(
            category_id=category_id,
            item_type=_required_text(item_type, "item_type"),
            name=cleaned_name,
            canonical_name=cleaned_name,
            description=_optional_text(description),
            status=DEFAULT_STATUS,
            confidence=1.0,
            first_seen_source_id=None,
            first_seen_at=now,
            last_seen_at=now,
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        for term in terms or []:
            self.add_term(
                item.id,
                actor=actor,
                term=str(term.get("term") or ""),
                term_type=str(term.get("term_type") or "alias"),
                weight=float(term.get("weight") or 1.0),
                language=str(term.get("language") or "ru"),
            )
        for offer in offers or []:
            self.add_offer(
                item.id,
                actor=actor,
                title=str(offer.get("title") or cleaned_name),
                offer_type=str(offer.get("offer_type") or "price"),
                description=_optional_text(offer.get("description")),
                price_amount=_optional_float(offer.get("price_amount")),
                currency=_optional_text(offer.get("currency")),
                price_text=_optional_text(offer.get("price_text")),
                terms_json=offer.get("terms_json"),
                ttl_days=_optional_int(offer.get("ttl_days")),
                ttl_source=str(offer.get("ttl_source") or "manual"),
            )
        for attribute in attributes or []:
            self.add_attribute(
                item.id,
                name=str(attribute.get("name") or attribute.get("attribute_name") or ""),
                value=str(attribute.get("value") or attribute.get("attribute_value") or ""),
                value_type=str(attribute.get("value_type") or "text"),
                unit=_optional_text(attribute.get("unit")),
            )
        if evidence:
            self.attach_evidence(
                entity_type="item",
                entity_id=item.id,
                actor=actor,
                evidence=evidence,
            )
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.item_create",
            entity_type="catalog_item",
            entity_id=item.id,
            old_value_json=None,
            new_value_json={"name": item.name, "item_type": item.item_type},
        )
        self.session.commit()
        return self.repository.get_item(item.id)  # type: ignore[return-value]

    def update_item(
        self,
        item_id: str,
        *,
        actor: str,
        name: str | None = None,
        item_type: str | None = None,
        category_slug: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> CatalogItemRecord:
        before = self.repository.get_item(item_id)
        if before is None:
            raise KeyError(item_id)
        values: dict[str, Any] = {"updated_at": utc_now()}
        if name is not None:
            cleaned = _required_text(name, "name")
            values["name"] = cleaned
            values["canonical_name"] = cleaned
        if item_type is not None:
            values["item_type"] = _required_text(item_type, "item_type")
        if category_slug is not None:
            values["category_id"] = self._category_id(category_slug)
        if description is not None:
            values["description"] = _optional_text(description)
        if status is not None:
            values["status"] = _required_text(status, "status")
        item = self.repository.update_item(item_id, **values)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.item_update",
            entity_type="catalog_item",
            entity_id=item_id,
            old_value_json={"name": before.name, "status": before.status},
            new_value_json={"name": item.name, "status": item.status},
        )
        self.session.commit()
        return item

    def archive_item(self, item_id: str, *, actor: str, reason: str | None = None) -> CatalogItemRecord:
        item = self.update_item(item_id, actor=actor, status=ARCHIVED_ITEM_STATUS)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.item_archive",
            entity_type="catalog_item",
            entity_id=item_id,
            old_value_json=None,
            new_value_json={"status": ARCHIVED_ITEM_STATUS, "reason": reason},
        )
        self.session.commit()
        return item

    def add_term(
        self,
        item_id: str | None,
        *,
        actor: str,
        term: str,
        term_type: str = "alias",
        category_slug: str | None = None,
        language: str = "ru",
        weight: float = 1.0,
    ) -> CatalogTermRecord:
        if item_id is not None and self.repository.get_item(item_id) is None:
            raise KeyError(item_id)
        now = utc_now()
        term_text = _required_text(term, "term")
        category_id = self._category_id(category_slug)
        record = self.repository.create_term(
            item_id=item_id,
            category_id=category_id,
            term=term_text,
            normalized_term=normalize_catalog_text(term_text),
            term_type=_required_text(term_type, "term_type"),
            language=language or "ru",
            status=DEFAULT_STATUS,
            weight=float(weight),
            created_by=actor,
            first_seen_source_id=None,
            created_at=now,
            updated_at=now,
        )
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.term_create",
            entity_type="catalog_term",
            entity_id=record.id,
            old_value_json=None,
            new_value_json={"term": record.term, "term_type": record.term_type},
        )
        self.session.commit()
        return record

    def update_term(
        self,
        term_id: str,
        *,
        actor: str,
        term: str | None = None,
        term_type: str | None = None,
        status: str | None = None,
        weight: float | None = None,
    ) -> CatalogTermRecord:
        before = self.repository.get_term(term_id)
        if before is None:
            raise KeyError(term_id)
        values: dict[str, Any] = {"updated_at": utc_now()}
        if term is not None:
            term_text = _required_text(term, "term")
            values["term"] = term_text
            values["normalized_term"] = normalize_catalog_text(term_text)
        if term_type is not None:
            values["term_type"] = _required_text(term_type, "term_type")
        if status is not None:
            values["status"] = _required_text(status, "status")
        if weight is not None:
            values["weight"] = float(weight)
        self.session.execute(
            update(catalog_terms_table).where(catalog_terms_table.c.id == term_id).values(**values)
        )
        after = self.repository.get_term(term_id)
        if after is None:
            raise KeyError(term_id)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.term_update",
            entity_type="catalog_term",
            entity_id=term_id,
            old_value_json={"term": before.term, "status": before.status},
            new_value_json={"term": after.term, "status": after.status},
        )
        self.session.commit()
        return after

    def archive_term(self, term_id: str, *, actor: str, reason: str | None = None) -> CatalogTermRecord:
        term = self.update_term(term_id, actor=actor, status=ARCHIVED_ITEM_STATUS)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.term_archive",
            entity_type="catalog_term",
            entity_id=term_id,
            old_value_json=None,
            new_value_json={"status": ARCHIVED_ITEM_STATUS, "reason": reason},
        )
        self.session.commit()
        return term

    def add_offer(
        self,
        item_id: str | None,
        *,
        actor: str,
        title: str,
        offer_type: str = "price",
        description: str | None = None,
        price_amount: float | None = None,
        currency: str | None = None,
        price_text: str | None = None,
        terms_json: Any = None,
        ttl_days: int | None = None,
        ttl_source: str = "manual",
        category_slug: str | None = None,
    ) -> CatalogOfferRecord:
        if item_id is not None and self.repository.get_item(item_id) is None:
            raise KeyError(item_id)
        now = utc_now()
        offer_id = new_id()
        self.session.execute(
            insert(catalog_offers_table).values(
                id=offer_id,
                item_id=item_id,
                category_id=self._category_id(category_slug),
                offer_type=offer_type or "price",
                title=_required_text(title, "title"),
                description=_optional_text(description),
                price_amount=price_amount,
                currency=currency,
                price_text=price_text,
                terms_json=terms_json,
                status=DEFAULT_STATUS,
                valid_from=None,
                valid_to=None,
                ttl_days=ttl_days,
                ttl_source=ttl_source or "manual",
                first_seen_source_id=None,
                last_seen_source_id=None,
                last_seen_at=now,
                expired_at=None,
                created_by=actor,
                created_at=now,
                updated_at=now,
            )
        )
        offer = self.get_offer(offer_id)
        if offer is None:
            raise KeyError(offer_id)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.offer_create",
            entity_type="catalog_offer",
            entity_id=offer.id,
            old_value_json=None,
            new_value_json={"title": offer.title, "price_text": offer.price_text},
        )
        self.session.commit()
        return offer

    def update_offer(
        self,
        offer_id: str,
        *,
        actor: str,
        title: str | None = None,
        price_text: str | None = None,
        status: str | None = None,
        description: str | None = None,
    ) -> CatalogOfferRecord:
        before = self.get_offer(offer_id)
        if before is None:
            raise KeyError(offer_id)
        values: dict[str, Any] = {"updated_at": utc_now()}
        if title is not None:
            values["title"] = _required_text(title, "title")
        if price_text is not None:
            values["price_text"] = _optional_text(price_text)
        if status is not None:
            values["status"] = _required_text(status, "status")
        if description is not None:
            values["description"] = _optional_text(description)
        self.session.execute(
            update(catalog_offers_table)
            .where(catalog_offers_table.c.id == offer_id)
            .values(**values)
        )
        after = self.get_offer(offer_id)
        if after is None:
            raise KeyError(offer_id)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.offer_update",
            entity_type="catalog_offer",
            entity_id=offer_id,
            old_value_json={"title": before.title, "status": before.status},
            new_value_json={"title": after.title, "status": after.status},
        )
        self.session.commit()
        return after

    def archive_offer(self, offer_id: str, *, actor: str, reason: str | None = None) -> CatalogOfferRecord:
        offer = self.update_offer(offer_id, actor=actor, status=ARCHIVED_OFFER_STATUS)
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.offer_archive",
            entity_type="catalog_offer",
            entity_id=offer_id,
            old_value_json=None,
            new_value_json={"status": ARCHIVED_OFFER_STATUS, "reason": reason},
        )
        self.session.commit()
        return offer

    def get_offer(self, offer_id: str) -> CatalogOfferRecord | None:
        row = (
            self.session.execute(
                select(catalog_offers_table).where(catalog_offers_table.c.id == offer_id)
            )
            .mappings()
            .first()
        )
        return CatalogOfferRecord(**dict(row)) if row is not None else None

    def add_attribute(
        self,
        item_id: str,
        *,
        name: str,
        value: str,
        value_type: str = "text",
        unit: str | None = None,
    ) -> dict[str, Any]:
        if self.repository.get_item(item_id) is None:
            raise KeyError(item_id)
        now = utc_now()
        attribute_id = new_id()
        self.session.execute(
            insert(catalog_attributes_table).values(
                id=attribute_id,
                item_id=item_id,
                attribute_name=_required_text(name, "attribute_name"),
                attribute_value=_required_text(value, "attribute_value"),
                value_type=value_type or "text",
                unit=unit,
                status=DEFAULT_STATUS,
                valid_from=None,
                valid_to=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        return self._get_attribute(attribute_id)

    def attach_evidence(
        self,
        *,
        entity_type: str,
        entity_id: str,
        actor: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now()
        source_id = _optional_text(evidence.get("source_id"))
        chunk_id = _optional_text(evidence.get("chunk_id"))
        if source_id is None and (evidence.get("source_text") or evidence.get("source_url")):
            source_text = _optional_text(evidence.get("source_text"))
            source_url = _optional_text(evidence.get("source_url"))
            external_id = source_url or _short_hash(source_text or str(evidence))
            source = CatalogSourceService(self.session).upsert_source(
                source_type="manual_text" if source_text else "manual_link",
                origin="manual",
                external_id=external_id,
                raw_text=source_text,
                url=source_url,
                metadata_json={"created_from": "catalog_editor"},
            )
            source_id = source.id
            if source_text:
                chunk = CatalogSourceService(self.session).replace_parsed_chunks(
                    source.id,
                    chunks=[source_text],
                    parser_name="manual-evidence",
                    parser_version="1",
                )[0]
                chunk_id = chunk.id
        evidence_id = new_id()
        self.session.execute(
            insert(catalog_evidence_table).values(
                id=evidence_id,
                entity_type=entity_type,
                entity_id=entity_id,
                source_id=source_id,
                artifact_id=_optional_text(evidence.get("artifact_id")),
                chunk_id=chunk_id,
                quote=_optional_text(evidence.get("quote")),
                page_number=_optional_int(evidence.get("page_number")),
                location_json=evidence.get("location_json"),
                extractor_version=None,
                evidence_type=_optional_text(evidence.get("evidence_type")) or MANUAL_EVIDENCE_TYPE,
                confidence=_optional_float(evidence.get("confidence")),
                created_by=actor,
                created_at=now,
            )
        )
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.evidence_attach",
            entity_type=entity_type,
            entity_id=entity_id,
            old_value_json=None,
            new_value_json={"evidence_id": evidence_id},
        )
        self.session.commit()
        return self._get_evidence(evidence_id)

    def rebuild_classifier_snapshot(self, *, actor: str, reason: str | None = None):
        snapshot = ClassifierSnapshotService(self.session).build_snapshot(
            created_by=actor,
            model="builtin-fuzzy",
            settings_snapshot={"trigger": "manual_catalog_editor", "reason": reason},
            notes="Manually rebuilt after catalog editor changes",
        )
        self.audit.record_change(
            actor=actor,
            action="catalog_editor.snapshot_rebuild",
            entity_type="classifier_version",
            entity_id=snapshot.id,
            old_value_json=None,
            new_value_json={"version": snapshot.version, "reason": reason},
        )
        self.session.commit()
        return snapshot

    def _category_id(self, category_slug: str | None) -> str | None:
        slug = _optional_text(category_slug)
        if slug is None:
            return None
        category = self.repository.find_category_by_slug(slug)
        if category is None:
            CatalogService(self.session).seed_initial_categories()
            category = self.repository.find_category_by_slug(slug)
        if category is None:
            now = utc_now()
            category = self.repository.create_category(
                parent_id=None,
                slug=slug,
                name=slug.replace("_", " ").title(),
                description=None,
                status=DEFAULT_STATUS,
                sort_order=1000,
                created_at=now,
                updated_at=now,
            )
            self.session.commit()
        return category.id

    def _list_terms(self, item_id: str) -> list[CatalogTermRecord]:
        rows = (
            self.session.execute(
                select(catalog_terms_table)
                .where(catalog_terms_table.c.item_id == item_id)
                .order_by(catalog_terms_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [CatalogTermRecord(**dict(row)) for row in rows]

    def _list_offers(self, item_id: str) -> list[CatalogOfferRecord]:
        rows = (
            self.session.execute(
                select(catalog_offers_table)
                .where(catalog_offers_table.c.item_id == item_id)
                .order_by(catalog_offers_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [CatalogOfferRecord(**dict(row)) for row in rows]

    def _list_attributes(self, item_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.session.execute(
                select(catalog_attributes_table)
                .where(catalog_attributes_table.c.item_id == item_id)
                .order_by(catalog_attributes_table.c.created_at)
            )
            .mappings()
            .all()
        ]

    def _list_evidence(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.session.execute(
                select(catalog_evidence_table)
                .where(
                    catalog_evidence_table.c.entity_type == entity_type,
                    catalog_evidence_table.c.entity_id == entity_id,
                )
                .order_by(catalog_evidence_table.c.created_at)
            )
            .mappings()
            .all()
        ]

    def _get_attribute(self, attribute_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(catalog_attributes_table).where(
                    catalog_attributes_table.c.id == attribute_id
                )
            )
            .mappings()
            .one()
        )
        return dict(row)

    def _get_evidence(self, evidence_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(catalog_evidence_table).where(catalog_evidence_table.c.id == evidence_id)
            )
            .mappings()
            .one()
        )
        return dict(row)


def _required_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    return cleaned


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
