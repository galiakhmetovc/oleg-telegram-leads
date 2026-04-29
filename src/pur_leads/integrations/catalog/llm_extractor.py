"""LLM-backed PUR catalog extractor."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.integrations.ai.chat import AiChatClient, AiChatMessage
from pur_leads.models.catalog import parsed_chunks_table
from pur_leads.workers.runtime import CatalogExtractedFact

EXTRACTOR_VERSION = "pur-llm-catalog-v1"
PROMPT_VERSION = "catalog-extraction-v1"


@dataclass(frozen=True)
class ExtractionScope:
    source_id: str | None
    chunk_id: str | None
    text: str


class LlmCatalogExtractor:
    extractor_version = EXTRACTOR_VERSION
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        client: AiChatClient,
        model: str,
        session: Session | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        fallback_extractor: Any | None = None,
        fallback_on_rate_limit: bool = False,
        fallback_on_error: bool = False,
    ) -> None:
        self.client = client
        self.model = model
        self.session = session
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.fallback_extractor = fallback_extractor
        self.fallback_on_rate_limit = fallback_on_rate_limit
        self.fallback_on_error = fallback_on_error
        self.last_token_usage_json: dict[str, Any] | None = None

    async def extract_catalog_facts(
        self,
        *,
        source_id: str | None,
        chunk_id: str | None,
        payload: dict[str, Any],
    ) -> list[CatalogExtractedFact]:
        self.last_token_usage_json = None
        scope = self._load_scope(source_id=source_id, chunk_id=chunk_id, payload=payload)
        try:
            completion = await self.client.complete(
                messages=_prompt_messages(scope.text),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            if self._should_use_fallback(exc):
                return await self.fallback_extractor.extract_catalog_facts(
                    source_id=source_id,
                    chunk_id=chunk_id,
                    payload=payload,
                )
            raise
        self.last_token_usage_json = {
            **completion.usage,
            "request_id": completion.request_id,
            "model": completion.model,
        }
        payload_json = _parse_json_object(completion.content)
        return _facts_from_payload(payload_json, source_id=scope.source_id, chunk_id=scope.chunk_id)

    def _should_use_fallback(self, exc: Exception) -> bool:
        if self.fallback_extractor is None:
            return False
        if self.fallback_on_rate_limit and _is_rate_limit_error(exc):
            return True
        return self.fallback_on_error

    def _load_scope(
        self,
        *,
        source_id: str | None,
        chunk_id: str | None,
        payload: dict[str, Any],
    ) -> ExtractionScope:
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return ExtractionScope(source_id=source_id, chunk_id=chunk_id, text=text)
        if self.session is None or chunk_id is None:
            raise ValueError("LLM catalog extractor requires payload.text or session + chunk_id")
        row = (
            self.session.execute(
                select(
                    parsed_chunks_table.c.source_id,
                    parsed_chunks_table.c.id,
                    parsed_chunks_table.c.text,
                ).where(parsed_chunks_table.c.id == chunk_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(chunk_id)
        return ExtractionScope(source_id=row["source_id"], chunk_id=row["id"], text=row["text"])


def _prompt_messages(text: str) -> list[AiChatMessage]:
    system = (
        "Return strict JSON only. Extract PUR smart-home/security/equipment catalog facts. "
        "Do not invent facts that are not supported by the source text. "
        'Use this schema: {"facts":[{"fact_type":"product|service|solution|offer|'
        'lead_phrase|negative_phrase|term","canonical_name":"...","category":"slug",'
        '"terms":["..."],"attributes":[{"name":"...","value":"..."}],'
        '"offer":{"price_text":"...","currency":"RUB"},'
        '"evidence_quote":"short exact quote","confidence":0.0}]}. '
        "Use category slugs such as video_surveillance, intercom, access_control, "
        "security_alarm, networks_sks, smart_home_core, lighting_shades, power_electric, "
        "climate_heating, audio_voice, project_service."
    )
    user = f"Source text:\n{text[:12000]}"
    return [AiChatMessage(role="system", content=system), AiChatMessage(role="user", content=user)]


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM catalog extractor expected valid JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("LLM catalog extractor expected valid JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM catalog extractor expected valid JSON object")
    return parsed


def _is_rate_limit_error(exc: Exception) -> bool:
    retry_after_seconds = getattr(exc, "retry_after_seconds", None)
    if isinstance(retry_after_seconds, int | float) and retry_after_seconds > 0:
        return True
    status_code = getattr(exc, "status_code", None)
    error_code = str(getattr(exc, "error_code", "") or "")
    return status_code == 429 or error_code in {"1302", "429"}


def _facts_from_payload(
    payload: dict[str, Any],
    *,
    source_id: str | None,
    chunk_id: str | None,
) -> list[CatalogExtractedFact]:
    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list):
        raise ValueError("LLM catalog extractor JSON must contain facts array")
    facts: list[CatalogExtractedFact] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_facts:
        if not isinstance(raw, dict):
            continue
        mapped = _fact_from_raw(raw, source_id=source_id, chunk_id=chunk_id)
        if mapped is None:
            continue
        identity = (mapped.candidate_type, mapped.canonical_name.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        facts.append(mapped)
    return facts


def _fact_from_raw(
    raw: dict[str, Any],
    *,
    source_id: str | None,
    chunk_id: str | None,
) -> CatalogExtractedFact | None:
    raw_type = _string(raw.get("fact_type")).casefold()
    canonical_name = _string(raw.get("canonical_name")).strip()
    if not raw_type or not canonical_name:
        return None
    confidence = _confidence(raw.get("confidence"))
    evidence_quote = _optional_string(raw.get("evidence_quote"))
    category_slug = _optional_string(raw.get("category"))
    terms = _string_list(raw.get("terms"))
    attributes = _attributes(raw.get("attributes"))

    if raw_type in {"product", "service", "solution", "bundle"}:
        item_type = "solution" if raw_type in {"solution", "bundle"} else raw_type
        fact_type = "bundle" if raw_type in {"solution", "bundle"} else raw_type
        value = {
            "item_type": item_type,
            "category_slug": category_slug,
            "terms": terms,
            "attributes": attributes,
            "description": _optional_string(raw.get("description")),
            "extractor_version": EXTRACTOR_VERSION,
        }
        return _catalog_fact(
            fact_type=fact_type,
            candidate_type="item",
            canonical_name=canonical_name,
            value_json=_compact_dict(value),
            confidence=confidence,
            source_id=source_id,
            chunk_id=chunk_id,
            evidence_quote=evidence_quote,
        )

    if raw_type == "offer":
        offer_value = raw.get("offer")
        offer: dict[str, Any] = offer_value if isinstance(offer_value, dict) else {}
        value = {
            **offer,
            "offer_type": _optional_string(offer.get("offer_type")) or "price",
            "title": _optional_string(offer.get("title")) or canonical_name,
            "category_slug": category_slug,
            "terms": terms,
            "ttl_source": _optional_string(offer.get("ttl_source")) or "none",
            "extractor_version": EXTRACTOR_VERSION,
        }
        return _catalog_fact(
            fact_type="offer",
            candidate_type="offer",
            canonical_name=canonical_name,
            value_json=_compact_dict(value),
            confidence=confidence,
            source_id=source_id,
            chunk_id=chunk_id,
            evidence_quote=evidence_quote,
        )

    if raw_type in {"lead_phrase", "negative_phrase"}:
        polarity = "negative" if raw_type == "negative_phrase" else "positive"
        value = {
            "category_slug": category_slug,
            "terms": terms or [canonical_name],
            "term_type": raw_type,
            "polarity": polarity,
            "extractor_version": EXTRACTOR_VERSION,
        }
        return _catalog_fact(
            fact_type="lead_intent",
            candidate_type=raw_type,
            canonical_name=canonical_name,
            value_json=_compact_dict(value),
            confidence=confidence,
            source_id=source_id,
            chunk_id=chunk_id,
            evidence_quote=evidence_quote,
        )

    if raw_type == "term":
        value = {
            "term": terms[0] if terms else canonical_name,
            "terms": terms,
            "term_type": _optional_string(raw.get("term_type")) or "alias",
            "category_slug": category_slug,
            "extractor_version": EXTRACTOR_VERSION,
        }
        return _catalog_fact(
            fact_type="term",
            candidate_type="term",
            canonical_name=canonical_name,
            value_json=_compact_dict(value),
            confidence=confidence,
            source_id=source_id,
            chunk_id=chunk_id,
            evidence_quote=evidence_quote,
        )
    return None


def _catalog_fact(
    *,
    fact_type: str,
    candidate_type: str,
    canonical_name: str,
    value_json: dict[str, Any],
    confidence: float,
    source_id: str | None,
    chunk_id: str | None,
    evidence_quote: str | None,
) -> CatalogExtractedFact:
    return CatalogExtractedFact(
        fact_type=fact_type,
        canonical_name=canonical_name,
        value_json=value_json,
        confidence=confidence,
        source_id=source_id,
        chunk_id=chunk_id,
        candidate_type=candidate_type,
        evidence_quote=evidence_quote,
    )


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        stripped = " ".join(item.split())
        normalized = stripped.casefold()
        if not stripped or normalized in seen:
            continue
        result.append(stripped)
        seen.add(normalized)
    return result


def _attributes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _optional_string(item.get("name"))
        attr_value = item.get("value")
        if name is None or attr_value in (None, ""):
            continue
        result.append({"name": name, "value": attr_value})
    return result


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(max(number, 0.0), 1.0)


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item for key, item in value.items() if item is not None and item != [] and item != {}
    }
