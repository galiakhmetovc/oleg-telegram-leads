"""Analyze uploaded chats against the approved interest core."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
from typing import Any

from sqlalchemy import desc, func, insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.interest_context_drafts import (
    interest_core_analysis_matches_table,
    interest_core_analysis_runs_table,
    interest_core_items_table,
)
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.audit import AuditService

MAX_MATCHES_PER_MESSAGE = 5


@dataclass(frozen=True)
class InterestCoreAnalysisRunRecord:
    id: str
    context_id: str
    monitored_source_id: str
    raw_export_run_id: str
    status: str
    source_title: str | None
    message_count: int
    core_item_count: int
    matched_message_count: int
    match_count: int
    summary_json: Any
    created_by: str
    started_at: Any
    finished_at: Any
    created_at: Any
    updated_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterestCoreAnalysisMatchRecord:
    id: str
    run_id: str
    context_id: str
    source_message_id: str
    interest_core_item_id: str
    telegram_message_id: int
    message_date: Any
    sender_id: str | None
    message_text: str | None
    canonical_name: str | None
    category: str | None
    matched_text: str | None
    match_kind: str
    score: float
    evidence_json: Any
    created_at: Any

    def as_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _CoreTerm:
    text: str
    normalized: str
    tokens: tuple[str, ...]
    kind: str
    base_score: float


@dataclass(frozen=True)
class _CoreMatcher:
    id: str
    canonical_name: str
    category: str | None
    terms: tuple[_CoreTerm, ...]
    noise_terms: tuple[_CoreTerm, ...]


class InterestCoreChatAnalysisService:
    """Run local, auditable matching of chat messages against active core items."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def analyze_raw_export(
        self,
        *,
        context_id: str,
        monitored_source_id: str,
        raw_export_run_id: str,
        actor: str,
        source_title: str | None = None,
    ) -> dict[str, Any]:
        core_items = self._active_core_items(context_id)
        if not core_items:
            raise ValueError("Сначала сформируйте и примите рабочее ядро")
        messages = self._source_messages(
            monitored_source_id=monitored_source_id,
            raw_export_run_id=raw_export_run_id,
        )
        now = utc_now()
        run_id = new_id()
        self.session.execute(
            insert(interest_core_analysis_runs_table).values(
                id=run_id,
                context_id=context_id,
                monitored_source_id=monitored_source_id,
                raw_export_run_id=raw_export_run_id,
                status="running",
                source_title=source_title,
                message_count=len(messages),
                core_item_count=len(core_items),
                matched_message_count=0,
                match_count=0,
                summary_json=None,
                created_by=actor,
                started_at=now,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()

        try:
            match_rows = self._build_matches(
                run_id=run_id,
                context_id=context_id,
                core_items=core_items,
                messages=messages,
                created_at=now,
            )
            if match_rows:
                self.session.execute(insert(interest_core_analysis_matches_table), match_rows)
            summary = _analysis_summary(match_rows)
            finished_at = utc_now()
            self.session.execute(
                update(interest_core_analysis_runs_table)
                .where(interest_core_analysis_runs_table.c.id == run_id)
                .values(
                    status="succeeded",
                    matched_message_count=summary["matched_message_count"],
                    match_count=len(match_rows),
                    summary_json=summary,
                    finished_at=finished_at,
                    updated_at=finished_at,
                )
            )
            self.session.commit()
        except Exception as exc:
            failed_at = utc_now()
            self.session.execute(
                update(interest_core_analysis_runs_table)
                .where(interest_core_analysis_runs_table.c.id == run_id)
                .values(
                    status="failed",
                    summary_json={"error": str(exc) or exc.__class__.__name__},
                    finished_at=failed_at,
                    updated_at=failed_at,
                )
            )
            self.session.commit()
            raise

        run = self._run(run_id)
        self.audit.record_change(
            actor=actor,
            action="interest_core_analysis.run",
            entity_type="interest_context",
            entity_id=context_id,
            old_value_json=None,
            new_value_json={
                "run_id": run_id,
                "monitored_source_id": monitored_source_id,
                "raw_export_run_id": raw_export_run_id,
                "message_count": len(messages),
                "core_item_count": len(core_items),
                "matched_message_count": summary["matched_message_count"],
                "match_count": len(match_rows),
            },
        )
        return {
            "run": run.as_jsonable() if run else None,
            "summary": summary,
            "top_matches": [
                row.as_jsonable()
                for row in self.list_matches(
                    context_id=context_id,
                    run_id=run_id,
                    limit=10,
                    offset=0,
                )["items"]
            ],
        }

    def latest_payload(
        self,
        context_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_core_analysis_runs_table)
                .where(interest_core_analysis_runs_table.c.context_id == context_id)
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_core_analysis_runs_table)
                .where(interest_core_analysis_runs_table.c.context_id == context_id)
                .order_by(desc(interest_core_analysis_runs_table.c.created_at))
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        return {
            "summary": _runs_summary([dict(row) for row in rows], total),
            "items": [_run_record(row).as_jsonable() for row in rows],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def list_matches(
        self,
        *,
        context_id: str,
        run_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        run = self._run(run_id)
        if run is None or run.context_id != context_id:
            raise KeyError(run_id)
        safe_limit = max(1, min(100, int(limit)))
        safe_offset = max(0, int(offset))
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(interest_core_analysis_matches_table)
                .where(interest_core_analysis_matches_table.c.context_id == context_id)
                .where(interest_core_analysis_matches_table.c.run_id == run_id)
            ).scalar_one()
            or 0
        )
        rows = (
            self.session.execute(
                select(interest_core_analysis_matches_table)
                .where(interest_core_analysis_matches_table.c.context_id == context_id)
                .where(interest_core_analysis_matches_table.c.run_id == run_id)
                .order_by(
                    desc(interest_core_analysis_matches_table.c.score),
                    desc(interest_core_analysis_matches_table.c.message_date),
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .mappings()
            .all()
        )
        return {
            "run": run.as_jsonable(),
            "items": [_match_record(row) for row in rows],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }

    def _active_core_items(self, context_id: str) -> list[_CoreMatcher]:
        rows = (
            self.session.execute(
                select(interest_core_items_table)
                .where(interest_core_items_table.c.context_id == context_id)
                .where(interest_core_items_table.c.status == "active")
                .order_by(interest_core_items_table.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        return [_matcher_from_row(row) for row in rows]

    def _source_messages(
        self,
        *,
        monitored_source_id: str,
        raw_export_run_id: str,
    ) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.session.execute(
                select(source_messages_table)
                .where(source_messages_table.c.monitored_source_id == monitored_source_id)
                .where(source_messages_table.c.archive_pointer_id == raw_export_run_id)
                .order_by(source_messages_table.c.message_date, source_messages_table.c.telegram_message_id)
            )
            .mappings()
            .all()
        ]

    def _build_matches(
        self,
        *,
        run_id: str,
        context_id: str,
        core_items: list[_CoreMatcher],
        messages: list[dict[str, Any]],
        created_at: Any,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for message in messages:
            text = _message_text(message)
            normalized = _normalize(text)
            if not normalized:
                continue
            message_tokens = set(_tokens(normalized))
            candidates: list[dict[str, Any]] = []
            for item in core_items:
                match = _best_match(item, normalized, message_tokens)
                if match is None:
                    continue
                candidates.append(
                    {
                        "id": new_id(),
                        "run_id": run_id,
                        "context_id": context_id,
                        "source_message_id": message["id"],
                        "interest_core_item_id": item.id,
                        "telegram_message_id": message["telegram_message_id"],
                        "message_date": message["message_date"],
                        "sender_id": message["sender_id"],
                        "message_text": _truncate(text, 2000),
                        "canonical_name": item.canonical_name,
                        "category": item.category,
                        "matched_text": _truncate(match["matched_text"], 500),
                        "match_kind": match["match_kind"],
                        "score": match["score"],
                        "evidence_json": match["evidence_json"],
                        "created_at": created_at,
                    }
                )
            rows.extend(
                sorted(candidates, key=lambda row: row["score"], reverse=True)[
                    :MAX_MATCHES_PER_MESSAGE
                ]
            )
        return rows

    def _run(self, run_id: str) -> InterestCoreAnalysisRunRecord | None:
        row = (
            self.session.execute(
                select(interest_core_analysis_runs_table).where(
                    interest_core_analysis_runs_table.c.id == run_id
                )
            )
            .mappings()
            .first()
        )
        return _run_record(row) if row is not None else None


def _matcher_from_row(row: Any) -> _CoreMatcher:
    canonical_name = str(row["canonical_name"] or "").strip()
    terms: list[_CoreTerm] = []
    terms.extend(_terms_from_values([canonical_name], "canonical", 0.65))
    terms.extend(_terms_from_values(_json_list(row["synonyms_json"]), "synonym", 0.72))
    terms.extend(_terms_from_values(_json_list(row["lead_signals_json"]), "lead_signal", 0.86))
    noise_terms = _terms_from_values(_json_list(row["noise_patterns_json"]), "canonical", 0.0)
    deduped: dict[tuple[str, str], _CoreTerm] = {}
    for term in terms:
        deduped.setdefault((term.normalized, term.kind), term)
    return _CoreMatcher(
        id=str(row["id"]),
        canonical_name=canonical_name,
        category=row["category"],
        terms=tuple(deduped.values()),
        noise_terms=tuple(noise_terms),
    )


def _terms_from_values(values: list[Any], kind: str, base_score: float) -> list[_CoreTerm]:
    terms: list[_CoreTerm] = []
    for value in values:
        text = str(value or "").strip()
        normalized = _normalize(text)
        tokens = tuple(_tokens(normalized))
        if not normalized or (len(normalized) < 4 and not tokens):
            continue
        terms.append(
            _CoreTerm(
                text=text,
                normalized=normalized,
                tokens=tokens,
                kind=kind,
                base_score=base_score,
            )
        )
    return terms


def _best_match(
    item: _CoreMatcher,
    normalized_text: str,
    message_tokens: set[str],
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    noise_hits = [
        term.text for term in item.noise_terms if _term_hits(term, normalized_text, message_tokens)
    ]
    for term in item.terms:
        hit = _term_hit(term, normalized_text, message_tokens)
        if hit is None:
            continue
        score = max(0.1, min(0.98, hit["score"] - min(0.35, 0.12 * len(noise_hits))))
        candidate = {
            "matched_text": term.text,
            "match_kind": term.kind if hit["kind"] != "token_overlap" else "token_overlap",
            "score": round(score, 4),
            "evidence_json": {
                "core_item_id": item.id,
                "canonical_name": item.canonical_name,
                "term": term.text,
                "term_kind": term.kind,
                "hit_kind": hit["kind"],
                "matched_tokens": hit["matched_tokens"],
                "noise_hits": noise_hits[:5],
                "algorithm": "local_interest_core_match_v1",
            },
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def _term_hits(term: _CoreTerm, normalized_text: str, message_tokens: set[str]) -> bool:
    return _term_hit(term, normalized_text, message_tokens) is not None


def _term_hit(
    term: _CoreTerm,
    normalized_text: str,
    message_tokens: set[str],
) -> dict[str, Any] | None:
    if term.normalized and term.normalized in normalized_text:
        return {
            "kind": "phrase",
            "score": term.base_score + 0.1,
            "matched_tokens": list(term.tokens),
        }
    if not term.tokens:
        return None
    matched_tokens = [token for token in term.tokens if token in message_tokens]
    if not matched_tokens:
        return None
    coverage = len(matched_tokens) / len(term.tokens)
    required = 1.0 if len(term.tokens) <= 2 else 0.75
    if coverage < required:
        return None
    return {
        "kind": "token_overlap",
        "score": term.base_score * max(0.65, coverage),
        "matched_tokens": matched_tokens,
    }


def _analysis_summary(match_rows: list[dict[str, Any]]) -> dict[str, Any]:
    message_ids = {row["source_message_id"] for row in match_rows}
    by_category = Counter(str(row["category"] or "без категории") for row in match_rows)
    by_kind = Counter(str(row["match_kind"]) for row in match_rows)
    by_core_item = Counter(str(row["canonical_name"] or row["interest_core_item_id"]) for row in match_rows)
    return {
        "matched_message_count": len(message_ids),
        "match_count": len(match_rows),
        "by_category": dict(by_category.most_common(20)),
        "by_kind": dict(by_kind.most_common()),
        "top_core_items": dict(by_core_item.most_common(20)),
        "algorithm": "local_interest_core_match_v1",
    }


def _runs_summary(rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {
        "total": total,
        "page_count": len(rows),
        "latest_match_count": int(rows[0]["match_count"] or 0) if rows else 0,
        "latest_matched_message_count": int(rows[0]["matched_message_count"] or 0) if rows else 0,
    }


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _message_text(message: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            str(message.get("text") or ""),
            str(message.get("caption") or ""),
        ]
        if part.strip()
    )


def _normalize(value: str | None) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"https?://\S+|www\.\S+", " url ", text)
    text = re.sub(r"[^-0-9a-zа-я_+#./\\]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(normalized: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[-0-9a-zа-я_+#./\\]+", normalized)
        if len(token) >= 3 and token not in _STOPWORDS
    ]


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _run_record(row: Any) -> InterestCoreAnalysisRunRecord:
    return InterestCoreAnalysisRunRecord(**dict(row))


def _match_record(row: Any) -> InterestCoreAnalysisMatchRecord:
    return InterestCoreAnalysisMatchRecord(**dict(row))


def _pagination(*, limit: int, offset: int, total: int) -> dict[str, Any]:
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + limit < total,
    }


_STOPWORDS = {
    "без",
    "был",
    "была",
    "были",
    "быть",
    "вам",
    "вас",
    "все",
    "для",
    "его",
    "еще",
    "или",
    "как",
    "мне",
    "надо",
    "нас",
    "нет",
    "они",
    "под",
    "при",
    "про",
    "раз",
    "так",
    "там",
    "тут",
    "уже",
    "что",
    "это",
    "the",
    "url",
    "and",
    "for",
    "you",
    "with",
}
