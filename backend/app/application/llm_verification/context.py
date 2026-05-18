from __future__ import annotations

from typing import Any

from app.domain.enrichment import TextEnrichmentResult
from app.domain.settings import NlpConfigRevision

CATALOG_NAMES = ("vendors", "protocols", "devices", "software")
CATALOG_LABELS = {
    "vendors": "Вендоры",
    "protocols": "Протоколы",
    "devices": "Устройства",
    "software": "ПО",
}


def build_llm_context_pack(
    *,
    message_text: str,
    enrichment_result: TextEnrichmentResult,
    active_revision: NlpConfigRevision,
) -> dict[str, Any]:
    return {
        "message": {
            "text": message_text,
        },
        "rule_engine_result": _rule_engine_result(enrichment_result),
        "available_taxonomy": _available_taxonomy(active_revision.documents),
    }


def _rule_engine_result(result: TextEnrichmentResult) -> dict[str, Any]:
    assessment = result.lead_assessment
    return {
        "verdict": _deterministic_verdict(result),
        "score": assessment.score if assessment else None,
        "temperature": assessment.temperature if assessment else None,
        "fact_labels": _unique_labels(fact.label for fact in result.facts),
        "signal_labels": _unique_labels(signal.label for signal in result.domain_signals),
        "reason_labels": _unique_labels(reason.label for reason in (assessment.reasons if assessment else [])),
        "solution_area_labels": _unique_labels(item.label for item in (assessment.solution_areas if assessment else [])),
        "customer_segment_labels": _unique_labels(item.label for item in (assessment.customer_segments if assessment else [])),
        "intent_signal_labels": _unique_labels(item.label for item in (assessment.intent_signals if assessment else [])),
        "noise_signal_labels": _unique_labels(item.label for item in (assessment.noise_signals if assessment else [])),
    }


def _deterministic_verdict(result: TextEnrichmentResult) -> str:
    if result.lead_assessment is None:
        return "uncertain"
    return "lead" if result.lead_assessment.is_lead else "not_lead"


def _available_taxonomy(documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    facts = documents.get("facts", {}).get("facts", [])
    signals = documents.get("signals", {}).get("signals", [])
    return {
        "signal_labels": _joined_labels(_label_value(item) for item in signals if isinstance(item, dict)),
        "fact_rule_labels": _joined_labels(_label_value(item) for item in facts if isinstance(item, dict)),
        "dictionary_labels": _dictionary_labels(documents),
    }


def _dictionary_labels(documents: dict[str, dict[str, Any]]) -> str:
    groups: list[str] = []
    for catalog_name in CATALOG_NAMES:
        raw_items = documents.get(catalog_name, {}).get(catalog_name, [])
        labels: list[str] = []
        for item in raw_items:
            if isinstance(item, dict):
                labels.append(_label_value(item))
        cleaned = [label for label in labels if label]
        if cleaned:
            groups.append(f"{CATALOG_LABELS[catalog_name]}: {', '.join(cleaned)}")
    return "; ".join(groups)


def _label_value(item: dict[str, Any]) -> str:
    value = item.get("label") or item.get("canonical") or item.get("type") or item.get("key")
    return "" if value is None else str(value).strip()


def _joined_labels(values: Any) -> str:
    labels = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            labels.append(text)
    return "; ".join(labels)


def _unique_labels(values: Any) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        labels.append(text)
        seen.add(text)
    return labels
