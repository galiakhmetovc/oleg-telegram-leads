"""Deterministic bootstrap extractor for PUR catalog chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.models.catalog import parsed_chunks_table
from pur_leads.workers.runtime import CatalogExtractedFact

EXTRACTOR_VERSION = "pur-heuristic-1"

SERVICE_ENTRY_RE = re.compile(r"(?ms)^\s*(?P<code>\d+\.\d+)\s+(?P<body>.*?)(?=^\s*\d+\.\d+\s+|\Z)")
SOLUTION_RE = re.compile(
    r"(?is)\bУровень\s+(?P<level>\d+)\s*[–-]\s*(?P<name>[А-ЯA-ZЁ][^\n\r]{2,80})"
)
PRICE_RE = re.compile(
    r"(?is)Итоговая\s+стоимость\s+решения\s+под\s+ключ\s+от\s+"
    r"(?P<amount>\d[\d\s]*)\s*руб"
)

TECHNICAL_START_RE = re.compile(
    r"^(Установка|Настройка|Доступ|Поддержка|Контроль|Устранение|Достаточно|"
    r"Открытие|Организация|Принцип работы|Возможности|Стоимость решения)\b",
    re.IGNORECASE,
)
INLINE_TECHNICAL_RE = re.compile(
    r"\b(Установка|Настройка|Доступ|Поддержка|Контроль|Устранение|Достаточно)\b"
)

CATEGORY_BY_SECTION = {
    "1": "lighting_shades",
    "2": "power_electric",
    "3": "climate_heating",
    "4": "audio_voice",
    "5": "video_surveillance",
    "6": "networks_sks",
    "7": "project_service",
}


@dataclass(frozen=True)
class ChunkScope:
    source_id: str
    chunk_id: str
    text: str


class HeuristicCatalogExtractor:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def extract_catalog_facts(
        self,
        *,
        source_id: str | None,
        chunk_id: str | None,
        payload: dict[str, Any],
    ) -> list[CatalogExtractedFact]:
        scope = self._load_scope(source_id=source_id, chunk_id=chunk_id, payload=payload)
        facts = [
            *_extract_numbered_services(scope),
            *_extract_access_solution(scope),
        ]
        return _dedupe_facts(facts)

    def _load_scope(
        self,
        *,
        source_id: str | None,
        chunk_id: str | None,
        payload: dict[str, Any],
    ) -> ChunkScope:
        text = payload.get("text")
        if isinstance(text, str) and source_id is not None and chunk_id is not None:
            return ChunkScope(source_id=source_id, chunk_id=chunk_id, text=text)
        if chunk_id is None:
            raise ValueError("heuristic extractor requires chunk_id or payload.text")
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
        return ChunkScope(source_id=row["source_id"], chunk_id=row["id"], text=row["text"])


def _extract_numbered_services(scope: ChunkScope) -> list[CatalogExtractedFact]:
    facts: list[CatalogExtractedFact] = []
    for match in SERVICE_ENTRY_RE.finditer(scope.text):
        code = match.group("code")
        body = match.group("body")
        title = _service_title(body)
        if title is None:
            continue
        facts.append(
            CatalogExtractedFact(
                fact_type="service",
                canonical_name=title,
                value_json={
                    "item_type": "service",
                    "category_slug": _category_slug(code, title),
                    "terms": _terms_for_title(title),
                    "source_code": code,
                    "description": _description(body),
                    "extractor_version": EXTRACTOR_VERSION,
                },
                confidence=0.78,
                source_id=scope.source_id,
                chunk_id=scope.chunk_id,
                candidate_type="item",
                evidence_quote=_quote(code, body),
            )
        )
    return facts


def _extract_access_solution(scope: ChunkScope) -> list[CatalogExtractedFact]:
    if "въезд" not in scope.text.casefold() and "проезд" not in scope.text.casefold():
        return []
    solution = SOLUTION_RE.search(scope.text)
    if solution is None:
        return []

    level = solution.group("level")
    level_name = _normalize_space(solution.group("name"))
    canonical = f"Автоматизация въездной группы: Уровень {level} - {level_name}"
    facts = [
        CatalogExtractedFact(
            fact_type="bundle",
            canonical_name=canonical,
            value_json={
                "item_type": "solution",
                "category_slug": "access_control",
                "terms": [
                    canonical,
                    f"уровень {level} {level_name}".casefold(),
                    "автоматизация въездной группы",
                    "въездная группа",
                    "скуд",
                ],
                "description": _description(scope.text),
                "extractor_version": EXTRACTOR_VERSION,
            },
            confidence=0.82,
            source_id=scope.source_id,
            chunk_id=scope.chunk_id,
            candidate_type="item",
            evidence_quote=_quote("", scope.text),
        )
    ]
    price = PRICE_RE.search(scope.text)
    if price is not None:
        amount = _normalize_price_amount(price.group("amount"))
        facts.append(
            CatalogExtractedFact(
                fact_type="offer",
                canonical_name=f"{canonical} - стоимость",
                value_json={
                    "offer_type": "price",
                    "title": f"{canonical} - стоимость",
                    "price_text": f"от {amount} руб",
                    "price_amount": int(amount.replace(" ", "")),
                    "currency": "RUB",
                    "related_item_name": canonical,
                    "ttl_source": "unknown",
                    "extractor_version": EXTRACTOR_VERSION,
                },
                confidence=0.74,
                source_id=scope.source_id,
                chunk_id=scope.chunk_id,
                candidate_type="offer",
                evidence_quote=price.group(0),
            )
        )
    return facts


def _service_title(body: str) -> str | None:
    lines = [_normalize_space(line) for line in body.splitlines()]
    lines = [line for line in lines if line]
    title_parts: list[str] = []
    for line in lines:
        inline = INLINE_TECHNICAL_RE.search(line)
        if inline is not None and (title_parts or inline.start() > 0):
            prefix = line[: inline.start()].strip()
            if prefix:
                title_parts.append(prefix)
            break
        if title_parts and TECHNICAL_START_RE.search(line):
            break
        title_parts.append(line)
        if len(" ".join(title_parts)) > 120:
            break
    title = _normalize_space(" ".join(title_parts))
    if not title or len(title) < 4:
        return None
    if title.casefold().startswith(("#", "что делаем")):
        return None
    return title[:180]


def _category_slug(code: str, title: str) -> str:
    normalized = title.casefold()
    if "домофон" in normalized:
        return "intercom"
    if "видеонаблю" in normalized or "камер" in normalized:
        return "video_surveillance"
    if "замок" in normalized or "доступ" in normalized or "скуд" in normalized:
        return "access_control"
    if "охран" in normalized or "задым" in normalized or "утеч" in normalized:
        return "security_alarm"
    return CATEGORY_BY_SECTION.get(code.split(".", 1)[0], "smart_home_core")


def _terms_for_title(title: str) -> list[str]:
    terms = [title]
    normalized = title.casefold()
    if "освещ" in normalized:
        terms.extend(["освещение", "управление освещением"])
    if "димм" in normalized:
        terms.append("диммер")
    if "видеонаблю" in normalized:
        terms.extend(["видеонаблюдение", "камеры наблюдения"])
    if "домофон" in normalized:
        terms.append("умный домофон")
    if "штор" in normalized or "жалюзи" in normalized:
        terms.extend(["умные шторы", "управление шторами"])
    return _dedupe_strings(terms)


def _description(value: str) -> str:
    return _normalize_space(value)[:700]


def _quote(code: str, body: str) -> str:
    prefix = f"{code} " if code else ""
    return (prefix + _normalize_space(body))[:600]


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def _normalize_price_amount(value: str) -> str:
    digits = "".join(char for char in value if char.isdigit())
    groups: list[str] = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    return " ".join(reversed(groups))


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_space(value)
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def _dedupe_facts(facts: list[CatalogExtractedFact]) -> list[CatalogExtractedFact]:
    result: list[CatalogExtractedFact] = []
    seen: set[tuple[str, str]] = set()
    for fact in facts:
        key = (fact.candidate_type, fact.canonical_name.casefold())
        if key in seen:
            continue
        result.append(fact)
        seen.add(key)
    return result
