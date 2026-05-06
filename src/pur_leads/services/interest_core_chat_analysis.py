"""Analyze uploaded chats against the approved interest core."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
import re
from typing import Any

from sqlalchemy import and_, desc, func, insert, or_, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.interest_context_drafts import (
    interest_core_analysis_matches_table,
    interest_core_analysis_runs_table,
    interest_core_items_table,
)
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.audit import AuditService

MAX_MATCHES_PER_MESSAGE = 5
DEFAULT_ANALYSIS_BATCH_SIZE = 5000
MATCH_INSERT_BATCH_SIZE = 5000
ProgressCallback = Callable[[dict[str, Any]], None]


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
    message_url: str | None = None

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
        batch_size: int = DEFAULT_ANALYSIS_BATCH_SIZE,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        core_items = self._active_core_items(context_id)
        if not core_items:
            raise ValueError("Сначала сформируйте и примите рабочее ядро")
        message_count = self._source_message_count(
            monitored_source_id=monitored_source_id,
            raw_export_run_id=raw_export_run_id,
        )
        safe_batch_size = max(1, int(batch_size or DEFAULT_ANALYSIS_BATCH_SIZE))
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
                message_count=message_count,
                core_item_count=len(core_items),
                matched_message_count=0,
                match_count=0,
                summary_json={
                    "matched_message_count": 0,
                    "match_count": 0,
                    "processed_message_count": 0,
                    "message_count": message_count,
                    "batch_size": safe_batch_size,
                    "partial": True,
                    "algorithm": "local_interest_core_match_v1",
                },
                created_by=actor,
                started_at=now,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        _emit_progress(
            progress,
            run_id=run_id,
            status="running",
            processed_message_count=0,
            message_count=message_count,
            matched_message_count=0,
            match_count=0,
            batch_size=safe_batch_size,
        )

        try:
            processed_message_count = 0
            matched_message_ids: set[str] = set()
            by_category: Counter[str] = Counter()
            by_kind: Counter[str] = Counter()
            by_core_item: Counter[str] = Counter()
            match_count = 0
            for message_batch in self._source_message_batches(
                monitored_source_id=monitored_source_id,
                raw_export_run_id=raw_export_run_id,
                batch_size=safe_batch_size,
            ):
                batch_match_rows = self._build_matches(
                    run_id=run_id,
                    context_id=context_id,
                    core_items=core_items,
                    messages=message_batch,
                    created_at=now,
                )
                _insert_match_rows(self.session, batch_match_rows)
                processed_message_count += len(message_batch)
                match_count += len(batch_match_rows)
                _accumulate_summary(
                    batch_match_rows,
                    matched_message_ids=matched_message_ids,
                    by_category=by_category,
                    by_kind=by_kind,
                    by_core_item=by_core_item,
                )
                partial_summary = _analysis_summary_from_counters(
                    matched_message_ids=matched_message_ids,
                    by_category=by_category,
                    by_kind=by_kind,
                    by_core_item=by_core_item,
                    match_count=match_count,
                    processed_message_count=processed_message_count,
                    message_count=message_count,
                    batch_size=safe_batch_size,
                    partial=True,
                )
                updated_at = utc_now()
                self.session.execute(
                    update(interest_core_analysis_runs_table)
                    .where(interest_core_analysis_runs_table.c.id == run_id)
                    .values(
                        matched_message_count=partial_summary["matched_message_count"],
                        match_count=match_count,
                        summary_json=partial_summary,
                        updated_at=updated_at,
                    )
                )
                self.session.commit()
                _emit_progress(
                    progress,
                    run_id=run_id,
                    status="running",
                    processed_message_count=processed_message_count,
                    message_count=message_count,
                    matched_message_count=partial_summary["matched_message_count"],
                    match_count=match_count,
                    batch_size=safe_batch_size,
                )

            summary = _analysis_summary_from_counters(
                matched_message_ids=matched_message_ids,
                by_category=by_category,
                by_kind=by_kind,
                by_core_item=by_core_item,
                match_count=match_count,
                processed_message_count=processed_message_count,
                message_count=message_count,
                batch_size=safe_batch_size,
                partial=False,
            )
            finished_at = utc_now()
            self.session.execute(
                update(interest_core_analysis_runs_table)
                .where(interest_core_analysis_runs_table.c.id == run_id)
                .values(
                    status="succeeded",
                    matched_message_count=summary["matched_message_count"],
                    match_count=match_count,
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
                "message_count": message_count,
                "core_item_count": len(core_items),
                "matched_message_count": summary["matched_message_count"],
                "match_count": match_count,
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
                select(
                    interest_core_analysis_matches_table,
                    source_messages_table.c.raw_metadata_json.label("_source_raw_metadata_json"),
                    monitored_sources_table.c.username.label("_source_username"),
                    monitored_sources_table.c.input_ref.label("_source_input_ref"),
                    monitored_sources_table.c.telegram_id.label("_source_telegram_id"),
                )
                .join(
                    source_messages_table,
                    source_messages_table.c.id
                    == interest_core_analysis_matches_table.c.source_message_id,
                    isouter=True,
                )
                .join(
                    monitored_sources_table,
                    monitored_sources_table.c.id == source_messages_table.c.monitored_source_id,
                    isouter=True,
                )
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

    def _source_message_count(
        self,
        *,
        monitored_source_id: str,
        raw_export_run_id: str,
    ) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(source_messages_table)
                .where(source_messages_table.c.monitored_source_id == monitored_source_id)
                .where(source_messages_table.c.archive_pointer_id == raw_export_run_id)
            ).scalar_one()
            or 0
        )

    def _source_message_batches(
        self,
        *,
        monitored_source_id: str,
        raw_export_run_id: str,
        batch_size: int,
    ) -> Iterator[list[dict[str, Any]]]:
        last_message_id: int | None = None
        last_row_id: str | None = None
        while True:
            query = (
                select(source_messages_table)
                .where(source_messages_table.c.monitored_source_id == monitored_source_id)
                .where(source_messages_table.c.archive_pointer_id == raw_export_run_id)
            )
            if last_message_id is not None and last_row_id is not None:
                query = query.where(
                    or_(
                        source_messages_table.c.telegram_message_id > last_message_id,
                        and_(
                            source_messages_table.c.telegram_message_id == last_message_id,
                            source_messages_table.c.id > last_row_id,
                        ),
                    )
                )
            rows = (
                self.session.execute(
                    query.order_by(
                        source_messages_table.c.telegram_message_id,
                        source_messages_table.c.id,
                    ).limit(batch_size)
                )
                .mappings()
                .all()
            )
            if not rows:
                break
            batch = [dict(row) for row in rows]
            last = batch[-1]
            last_message_id = int(last["telegram_message_id"])
            last_row_id = str(last["id"])
            yield batch

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


def _insert_match_rows(session: Session, rows: list[dict[str, Any]]) -> None:
    for index in range(0, len(rows), MATCH_INSERT_BATCH_SIZE):
        chunk = rows[index : index + MATCH_INSERT_BATCH_SIZE]
        if chunk:
            session.execute(insert(interest_core_analysis_matches_table), chunk)


def _accumulate_summary(
    match_rows: list[dict[str, Any]],
    *,
    matched_message_ids: set[str],
    by_category: Counter[str],
    by_kind: Counter[str],
    by_core_item: Counter[str],
) -> None:
    for row in match_rows:
        matched_message_ids.add(str(row["source_message_id"]))
        by_category.update([str(row["category"] or "без категории")])
        by_kind.update([str(row["match_kind"])])
        by_core_item.update([str(row["canonical_name"] or row["interest_core_item_id"])])


def _analysis_summary_from_counters(
    *,
    matched_message_ids: set[str],
    by_category: Counter[str],
    by_kind: Counter[str],
    by_core_item: Counter[str],
    match_count: int,
    processed_message_count: int,
    message_count: int,
    batch_size: int,
    partial: bool,
) -> dict[str, Any]:
    return {
        "matched_message_count": len(matched_message_ids),
        "match_count": match_count,
        "processed_message_count": processed_message_count,
        "message_count": message_count,
        "batch_size": batch_size,
        "progress_percent": _progress_percent(processed_message_count, message_count),
        "by_category": dict(by_category.most_common(20)),
        "by_kind": dict(by_kind.most_common()),
        "top_core_items": dict(by_core_item.most_common(20)),
        "partial": partial,
        "algorithm": "local_interest_core_match_v1",
    }


def _emit_progress(
    progress: ProgressCallback | None,
    *,
    run_id: str,
    status: str,
    processed_message_count: int,
    message_count: int,
    matched_message_count: int,
    match_count: int,
    batch_size: int,
) -> None:
    if progress is None:
        return
    progress(
        {
            "run_id": run_id,
            "status": status,
            "current_stage": "analysis",
            "current_stage_label": "Анализ по ядру",
            "processed_message_count": processed_message_count,
            "message_count": message_count,
            "matched_message_count": matched_message_count,
            "match_count": match_count,
            "batch_size": batch_size,
            "stage_percent": _progress_percent(processed_message_count, message_count),
        }
    )


def _progress_percent(processed_message_count: int, message_count: int) -> int:
    if message_count <= 0:
        return 100
    return max(0, min(100, int(processed_message_count * 100 / message_count)))


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
    payload = dict(row)
    raw_metadata = payload.pop("_source_raw_metadata_json", None)
    username = payload.pop("_source_username", None)
    input_ref = payload.pop("_source_input_ref", None)
    telegram_id = payload.pop("_source_telegram_id", None)
    payload["message_url"] = _message_url(
        raw_metadata,
        username=username,
        input_ref=input_ref,
        telegram_id=telegram_id,
        telegram_message_id=payload.get("telegram_message_id"),
    )
    return InterestCoreAnalysisMatchRecord(**payload)


def _message_url(
    value: Any,
    *,
    username: Any,
    input_ref: Any,
    telegram_id: Any,
    telegram_message_id: Any,
) -> str | None:
    if not isinstance(value, dict):
        value = {}
    message_url = value.get("message_url")
    if isinstance(message_url, str) and message_url.strip() and message_url != "null":
        return message_url
    if telegram_message_id is None:
        return None
    message_id = str(telegram_message_id)
    source_username = str(username or "").strip().lstrip("@") or _username_from_ref(input_ref)
    if source_username:
        return f"https://t.me/{source_username}/{message_id}"
    source_id = str(telegram_id or "").strip()
    if source_id:
        internal_id = source_id.removeprefix("-100").lstrip("-")
        if internal_id.isdigit():
            return f"https://t.me/c/{internal_id}/{message_id}"
    return None


def _username_from_ref(value: Any) -> str:
    text = str(value or "").strip()
    if "t.me/" not in text:
        return ""
    tail = text.split("t.me/", 1)[1].strip("/")
    username = tail.split("/", 1)[0].strip().lstrip("@")
    if not username or username in {"c", "joinchat", "+"} or username.startswith("+"):
        return ""
    return username


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
