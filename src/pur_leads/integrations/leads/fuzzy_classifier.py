"""Built-in catalog keyword/fuzzy lead classifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from pur_leads.models.catalog import classifier_snapshot_entries_table, classifier_versions_table
from pur_leads.services.classifier_snapshots import ClassifierSnapshotService
from pur_leads.workers.runtime import (
    LeadClassifierMatch,
    LeadClassifierResult,
    LeadMessageForClassification,
)

BUYING_INTENT_TERMS = (
    "нужен",
    "нужна",
    "нужно",
    "нужны",
    "ищу",
    "ищем",
    "подскажите",
    "посоветуйте",
    "подберите",
    "купить",
    "заказать",
    "установить",
    "поставить",
    "сколько стоит",
    "цена",
    "есть ли",
    "где купить",
    "хочу",
)

NEGATIVE_INTENT_TERMS = (
    "продаю",
    "продам",
    "реклама",
    "обзор",
    "не нужен",
    "не нужна",
    "не нужно",
    "уже купил",
    "уже купили",
)

KEYWORD_ENTRY_TYPES = {"term", "example", "candidate", "candidate_term", "item"}


@dataclass(frozen=True)
class KeywordEntry:
    snapshot_entry_id: str
    entry_type: str
    entity_type: str | None
    entity_id: str
    term: str
    weight: float
    metadata_json: dict[str, Any]


class FuzzyCatalogLeadClassifier:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def classify_message_batch(
        self,
        *,
        messages: list[LeadMessageForClassification],
        payload: dict[str, Any],
    ) -> list[LeadClassifierResult]:
        version = self._latest_version()
        if version is None or payload.get("rebuild_snapshot"):
            built_version = ClassifierSnapshotService(self.session).build_snapshot(
                created_by="system",
                model="builtin-fuzzy",
                settings_snapshot={"classifier": "builtin-fuzzy"},
                notes="Automatically built for built-in fuzzy classifier",
            )
            version_id = built_version.id
        else:
            version_id = version["id"]
        entries = self._keyword_entries(version_id)
        return [self._classify_message(message, version_id, entries) for message in messages]

    def _latest_version(self) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                select(classifier_versions_table).order_by(
                    desc(classifier_versions_table.c.version)
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _keyword_entries(self, classifier_version_id: str) -> list[KeywordEntry]:
        rows = (
            self.session.execute(
                select(classifier_snapshot_entries_table).where(
                    classifier_snapshot_entries_table.c.classifier_version_id
                    == classifier_version_id,
                    classifier_snapshot_entries_table.c.entry_type.in_(KEYWORD_ENTRY_TYPES),
                )
            )
            .mappings()
            .all()
        )
        entries = [
            KeywordEntry(
                snapshot_entry_id=row["id"],
                entry_type=row["entry_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                term=_normalize(row["normalized_value"] or row["text_value"] or ""),
                weight=float(row["weight"] or 1.0),
                metadata_json=row["metadata_json"]
                if isinstance(row["metadata_json"], dict)
                else {},
            )
            for row in rows
        ]
        return sorted(
            [entry for entry in entries if _usable_term(entry.term)],
            key=lambda entry: (len(entry.term), entry.weight),
            reverse=True,
        )

    def _classify_message(
        self,
        message: LeadMessageForClassification,
        classifier_version_id: str,
        entries: list[KeywordEntry],
    ) -> LeadClassifierResult:
        normalized_text = _normalize(message.normalized_text or message.message_text or "")
        matches = _matches(normalized_text, entries)
        has_intent = _contains_any(normalized_text, BUYING_INTENT_TERMS)
        has_negative = _contains_any(normalized_text, NEGATIVE_INTENT_TERMS)

        if matches and has_intent and not has_negative:
            decision = "lead"
            confidence = min(0.95, 0.78 + matches[0].score * 0.15)
            notify_reason = "catalog_match_with_intent"
            reason = "Matched catalog terms with buying intent"
            commercial_value_score = 0.7
        elif matches and not has_negative:
            decision = "maybe"
            confidence = min(0.82, 0.52 + matches[0].score * 0.18)
            notify_reason = "operator_review_required"
            reason = "Matched catalog terms without explicit buying intent"
            commercial_value_score = 0.35
        else:
            decision = "not_lead"
            confidence = 0.62 if has_negative else 0.5
            notify_reason = None
            reason = "No catalog demand signal found"
            commercial_value_score = 0.0

        return LeadClassifierResult(
            source_message_id=message.source_message_id,
            classifier_version_id=classifier_version_id,
            decision=decision,
            detection_mode="live",
            confidence=confidence,
            commercial_value_score=commercial_value_score,
            negative_score=0.7 if has_negative else 0.0,
            high_value_signals_json=[match.matched_text for match in matches] if matches else [],
            negative_signals_json=["negative_intent"] if has_negative else [],
            notify_reason=notify_reason,
            reason=reason,
            matches=matches[:5],
        )


def _matches(normalized_text: str, entries: list[KeywordEntry]) -> list[LeadClassifierMatch]:
    result: list[LeadClassifierMatch] = []
    seen_terms: set[str] = set()
    for entry in entries:
        if entry.term in seen_terms or not _term_matches(entry.term, normalized_text):
            continue
        seen_terms.add(entry.term)
        result.append(
            LeadClassifierMatch(
                match_type=_lead_match_type(entry),
                matched_text=entry.term,
                score=_score(entry, normalized_text),
                classifier_snapshot_entry_id=entry.snapshot_entry_id,
                catalog_item_id=entry.entity_id if entry.entity_type == "item" else None,
                catalog_term_id=entry.entity_id if entry.entity_type == "term" else None,
                catalog_offer_id=entry.entity_id if entry.entity_type == "offer" else None,
                category_id=entry.metadata_json.get("category_id"),
            )
        )
    return result


def _score(entry: KeywordEntry, normalized_text: str) -> float:
    length_component = min(len(entry.term), 40) / 100
    density_component = min(len(entry.term) / max(len(normalized_text), 1), 0.25)
    return min(0.98, 0.58 + length_component + density_component + min(entry.weight, 2.0) * 0.04)


def _lead_match_type(entry: KeywordEntry) -> str:
    if entry.entry_type == "example":
        return "manual_example"
    return "term"


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _term_matches(term: str, value: str) -> bool:
    if term in value:
        return True
    if term.endswith(("а", "я")) and len(term) > 4:
        stem = term[:-1]
        return any(f"{stem}{suffix}" in value for suffix in ("у", "ы", "е", "ой", "ою", "ами"))
    return False


def _usable_term(value: str) -> bool:
    return len(value) >= 3 and any(char.isalpha() for char in value)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
