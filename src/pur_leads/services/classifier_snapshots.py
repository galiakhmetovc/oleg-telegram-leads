"""Classifier snapshot builder."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.catalog import (
    catalog_attributes_table,
    catalog_items_table,
    catalog_offers_table,
    catalog_terms_table,
    classifier_examples_table,
    classifier_snapshot_entries_table,
    classifier_version_artifacts_table,
    classifier_versions_table,
)

DEFAULT_INCLUDED_STATUSES = ["approved", "auto_pending"]
ACTIVE_EXAMPLE_STATUSES = ["active"]


@dataclass(frozen=True)
class ClassifierVersionRecord:
    id: str
    version: int
    catalog_version_id: str | None
    created_at: Any
    created_by: str
    included_statuses_json: Any
    catalog_hash: str
    example_hash: str
    prompt_hash: str
    keyword_index_hash: str
    settings_hash: str
    model: str | None
    model_config_hash: str | None
    notes: str | None


class ClassifierSnapshotService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build_snapshot(
        self,
        *,
        created_by: str,
        model: str | None = None,
        catalog_version_id: str | None = None,
        included_statuses: list[str] | None = None,
        settings_snapshot: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> ClassifierVersionRecord:
        statuses = included_statuses or DEFAULT_INCLUDED_STATUSES
        settings = settings_snapshot or {}
        entries = self._collect_entries(statuses)
        catalog_entries = [entry for entry in entries if entry["entry_type"] != "example"]
        example_entries = [entry for entry in entries if entry["entry_type"] == "example"]
        keyword_index = [
            {
                "term": entry["normalized_value"],
                "entity_id": entry["entity_id"],
                "weight": entry["weight"],
            }
            for entry in entries
            if entry["entry_type"] in {"term", "example"} and entry["normalized_value"]
        ]
        catalog_prompt = _catalog_prompt(entries)
        token_estimate = _estimate_tokens(catalog_prompt)
        now = utc_now()
        version_id = new_id()
        self.session.execute(
            insert(classifier_versions_table).values(
                id=version_id,
                version=self._next_version(),
                catalog_version_id=catalog_version_id,
                created_at=now,
                created_by=created_by,
                included_statuses_json=statuses,
                catalog_hash=_hash_json(catalog_entries),
                example_hash=_hash_json(example_entries),
                prompt_hash=_hash_text(catalog_prompt),
                keyword_index_hash=_hash_json(keyword_index),
                settings_hash=_hash_json(settings),
                model=model,
                model_config_hash=_hash_json(model_config or {})
                if model_config is not None
                else None,
                notes=notes,
            )
        )
        for entry in entries:
            self.session.execute(
                insert(classifier_snapshot_entries_table).values(
                    id=new_id(),
                    classifier_version_id=version_id,
                    **entry,
                    created_at=now,
                )
            )
        for artifact_type, content_text, content_json in (
            ("catalog_prompt", catalog_prompt, None),
            ("keyword_index", None, keyword_index),
            ("settings_snapshot", None, settings),
            ("token_estimate", None, {"token_estimate": token_estimate}),
        ):
            self.session.execute(
                insert(classifier_version_artifacts_table).values(
                    id=new_id(),
                    classifier_version_id=version_id,
                    artifact_type=artifact_type,
                    content_text=content_text,
                    content_json=content_json,
                    content_hash=_hash_text(content_text)
                    if content_text is not None
                    else _hash_json(content_json),
                    created_at=now,
                )
            )
        self.session.commit()
        return self._get_version(version_id)

    def _collect_entries(self, statuses: list[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        entries.extend(
            _entry(
                entry_type="item",
                entity_type="item",
                entity_id=row["id"],
                status_at_build=row["status"],
                weight=1.0,
                text_value=row["name"],
                normalized_value=row["canonical_name"].casefold(),
                metadata_json={
                    "item_type": row["item_type"],
                    "category_id": row["category_id"],
                    "description": row["description"],
                },
            )
            for row in self._rows(catalog_items_table, statuses)
        )
        entries.extend(
            _entry(
                entry_type="term",
                entity_type="term",
                entity_id=row["id"],
                status_at_build=row["status"],
                weight=row["weight"],
                text_value=row["term"],
                normalized_value=row["normalized_term"],
                metadata_json={
                    "item_id": row["item_id"],
                    "category_id": row["category_id"],
                    "term_type": row["term_type"],
                },
            )
            for row in self._rows(catalog_terms_table, statuses)
        )
        entries.extend(
            _entry(
                entry_type="attribute",
                entity_type="attribute",
                entity_id=row["id"],
                status_at_build=row["status"],
                weight=None,
                text_value=f"{row['attribute_name']}: {row['attribute_value']}",
                normalized_value=f"{row['attribute_name']}:{row['attribute_value']}".casefold(),
                metadata_json={"item_id": row["item_id"], "value_type": row["value_type"]},
            )
            for row in self._rows(catalog_attributes_table, statuses)
        )
        entries.extend(
            _entry(
                entry_type="offer",
                entity_type="offer",
                entity_id=row["id"],
                status_at_build=row["status"],
                weight=None,
                text_value=row["price_text"] or row["title"],
                normalized_value=(row["price_text"] or row["title"]).casefold(),
                metadata_json={
                    "item_id": row["item_id"],
                    "category_id": row["category_id"],
                    "offer_type": row["offer_type"],
                    "ttl_days": row["ttl_days"],
                },
            )
            for row in self._rows(catalog_offers_table, statuses)
        )
        examples = (
            self.session.execute(
                select(classifier_examples_table).where(
                    classifier_examples_table.c.status.in_(ACTIVE_EXAMPLE_STATUSES)
                )
            )
            .mappings()
            .all()
        )
        entries.extend(
            _entry(
                entry_type="example",
                entity_type="example",
                entity_id=row["id"],
                status_at_build=row["status"],
                weight=row["weight"],
                text_value=row["example_text"],
                normalized_value=row["example_text"].casefold(),
                metadata_json={
                    "example_type": row["example_type"],
                    "polarity": row["polarity"],
                    "catalog_item_id": row["catalog_item_id"],
                    "catalog_term_id": row["catalog_term_id"],
                },
            )
            for row in examples
        )
        return entries

    def _rows(self, table, statuses: list[str]) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        rows = (
            self.session.execute(select(table).where(table.c.status.in_(statuses))).mappings().all()
        )
        return [dict(row) for row in rows]

    def _next_version(self) -> int:
        current = self.session.execute(
            select(func.max(classifier_versions_table.c.version))
        ).scalar()
        return int(current or 0) + 1

    def _get_version(self, version_id: str) -> ClassifierVersionRecord:
        row = (
            self.session.execute(
                select(classifier_versions_table).where(
                    classifier_versions_table.c.id == version_id
                )
            )
            .mappings()
            .one()
        )
        return ClassifierVersionRecord(**dict(row))


def _entry(
    *,
    entry_type: str,
    entity_type: str,
    entity_id: str,
    status_at_build: str,
    weight: float | None,
    text_value: str,
    normalized_value: str,
    metadata_json: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "entry_type": entry_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "status_at_build": status_at_build,
        "weight": weight,
        "text_value": text_value,
        "normalized_value": normalized_value,
        "metadata_json": metadata_json,
    }
    payload["content_hash"] = _hash_json(payload)
    return payload


def _catalog_prompt(entries: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{entry['entry_type']}:{entry['normalized_value']}"
        for entry in sorted(entries, key=lambda item: (item["entry_type"], item["entity_id"]))
    )


def _estimate_tokens(value: str) -> int:
    return len(value.split())


def _hash_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return _hash_text(payload)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
