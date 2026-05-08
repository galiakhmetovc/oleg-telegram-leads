from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any
from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidatePage
from app.domain.analytics import AnalyticsMessageReview
from app.domain.analytics import AnalyticsReviewVerdict
from app.domain.analytics import AnalyticsRun
from app.core.config import get_settings
from app.infrastructure.persistence.tables import analytics_aggregates, analytics_candidates
from app.infrastructure.persistence.tables import analytics_runs
from app.infrastructure.persistence.tables import enrichment_jobs, enrichment_results
from app.infrastructure.persistence.tables import message_reviews
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages

LIVE_TELEGRAM_RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


class PostgresAnalyticsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_runs(self) -> list[AnalyticsRun]:
        async with self._session_factory() as session:
            live_run = await _live_run(session)
            result = await session.execute(
                sa.select(analytics_runs).order_by(
                    analytics_runs.c.finished_at.desc().nullslast(),
                    analytics_runs.c.imported_at.desc(),
                )
            )
            return [live_run, *[_run_from_row(row) for row in result.mappings()]]

    async def get_run(self, run_id: UUID) -> AnalyticsRun | None:
        if run_id == LIVE_TELEGRAM_RUN_ID:
            async with self._session_factory() as session:
                return await _live_run(session)
        async with self._session_factory() as session:
            result = await session.execute(sa.select(analytics_runs).where(analytics_runs.c.id == run_id))
            row = result.mappings().first()
            return _run_from_row(row) if row is not None else None

    async def get_live_candidate_by_message_id(self, message_id: str) -> AnalyticsCandidate | None:
        try:
            source_message_id = UUID(message_id)
        except ValueError:
            return None
        public_base_url = get_settings().public_base_url.rstrip("/")
        async with self._session_factory() as session:
            result = await session.execute(
                _live_candidate_select()
                .where(telegram_source_messages.c.id == source_message_id)
                .limit(1)
            )
            row = result.mappings().first()
        return _live_candidate_from_row(row, public_base_url) if row is not None else None

    async def get_message_review(self, message_id: str) -> AnalyticsMessageReview | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(message_reviews).where(message_reviews.c.source_message_id == UUID(message_id))
            )
            row = result.mappings().first()
        return _review_from_row(row) if row is not None else None

    async def save_message_review(
        self,
        *,
        message_id: str,
        verdict: AnalyticsReviewVerdict | None,
        comment: str,
        tags: list[str],
    ) -> AnalyticsMessageReview:
        now = datetime.now(UTC)
        values = {
            "source_message_id": UUID(message_id),
            "verdict": verdict,
            "comment": comment,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
        }
        statement = (
            insert(message_reviews)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[message_reviews.c.source_message_id],
                set_={
                    "verdict": verdict,
                    "comment": comment,
                    "tags": tags,
                    "updated_at": now,
                },
            )
            .returning(message_reviews)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().one()
            await session.commit()
        return _review_from_row(row)

    async def list_aggregates(self, run_id: UUID) -> list[AnalyticsAggregate]:
        if run_id == LIVE_TELEGRAM_RUN_ID:
            async with self._session_factory() as session:
                candidates = await _live_candidates(session)
            return _live_aggregates(candidates)
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(analytics_aggregates)
                .where(analytics_aggregates.c.run_id == run_id)
                .order_by(analytics_aggregates.c.kind.asc(), analytics_aggregates.c.count.desc())
            )
            return [_aggregate_from_row(row) for row in result.mappings()]

    async def list_candidates(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
        score_min: int | None,
        temperature: str | None,
        signal: str | None,
        reason: str | None,
        solution_area: str | None,
        customer_segment: str | None,
        lane: str | None,
        source_chat_id: str | None,
        received_from: datetime | None,
        received_to: datetime | None,
        review_status: str | None,
        verdict: AnalyticsReviewVerdict | None,
        q: str | None,
    ) -> AnalyticsCandidatePage:
        received_from = _aware_utc(received_from)
        received_to = _aware_utc(received_to)
        if run_id == LIVE_TELEGRAM_RUN_ID:
            public_base_url = get_settings().public_base_url.rstrip("/")
            async with self._session_factory() as session:
                predicates = _live_candidate_filter_predicates(
                    score_min=score_min,
                    temperature=temperature,
                    signal=signal,
                    reason=reason,
                    solution_area=solution_area,
                    customer_segment=customer_segment,
                    lane=lane,
                    source_chat_id=source_chat_id,
                    received_from=received_from,
                    received_to=received_to,
                    review_status=review_status,
                    verdict=verdict,
                    q=q,
                )
                total = int(
                    await session.scalar(
                        sa.select(sa.func.count())
                        .select_from(_live_candidate_from_clause())
                        .where(*predicates)
                    )
                    or 0
                )
                result = await session.execute(
                    _live_candidate_select()
                    .where(*predicates)
                    .order_by(
                        _live_score_expr().desc(),
                        telegram_source_messages.c.telegram_message_id.desc(),
                        telegram_source_messages.c.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            return AnalyticsCandidatePage(
                total=total,
                items=[
                    _live_candidate_from_row(row, public_base_url)
                    for row in result.mappings()
                ],
            )

        predicates = [analytics_candidates.c.run_id == run_id]
        if score_min is not None:
            predicates.append(analytics_candidates.c.score >= score_min)
        if temperature:
            predicates.append(analytics_candidates.c.temperature == temperature)
        if signal:
            predicates.append(sa.literal(signal) == sa.any_(analytics_candidates.c.signal_types))
        if reason:
            predicates.append(sa.literal(reason) == sa.any_(analytics_candidates.c.reason_keys))
        if solution_area:
            predicates.append(sa.literal(solution_area) == sa.any_(analytics_candidates.c.solution_area_types))
        if customer_segment:
            predicates.append(sa.literal(customer_segment) == sa.any_(analytics_candidates.c.customer_segment_types))
        if lane:
            predicates.append(analytics_candidates.c.review_lane == lane)
        if source_chat_id:
            predicates.append(analytics_candidates.c.source_chat_id == source_chat_id)
        if received_from is not None:
            predicates.append(analytics_candidates.c.received_at >= received_from)
        if received_to is not None:
            predicates.append(analytics_candidates.c.received_at <= received_to)
        if q:
            predicates.append(analytics_candidates.c.text.ilike(f"%{q}%"))
        if review_status == "reviewed" or verdict is not None:
            return AnalyticsCandidatePage(total=0, items=[])

        async with self._session_factory() as session:
            imported_total = await session.scalar(
                sa.select(sa.func.count()).select_from(analytics_candidates).where(*predicates)
            )
            result = await session.execute(
                sa.select(analytics_candidates)
                .where(*predicates)
                .order_by(analytics_candidates.c.score.desc(), analytics_candidates.c.message_id.asc())
                .limit(limit)
                .offset(offset)
            )
            return AnalyticsCandidatePage(
                total=int(imported_total or 0),
                items=[_candidate_from_row(row) for row in result.mappings()],
            )

    async def replace_import(
        self,
        run: AnalyticsRun,
        candidates: Sequence[AnalyticsCandidate],
        aggregates: Sequence[AnalyticsAggregate],
    ) -> AnalyticsRun:
        async with self._session_factory() as session:
            result = await session.execute(sa.select(analytics_runs.c.id).where(analytics_runs.c.name == run.name))
            existing_run_id = result.scalar_one_or_none()
            run_id = existing_run_id or run.id

            if existing_run_id is not None:
                await session.execute(
                    analytics_candidates.delete().where(analytics_candidates.c.run_id == existing_run_id)
                )
                await session.execute(
                    analytics_aggregates.delete().where(analytics_aggregates.c.run_id == existing_run_id)
                )

            run_payload = _run_to_values(run, run_id)
            await session.execute(
                insert(analytics_runs)
                .values(run_payload)
                .on_conflict_do_update(
                    index_elements=[analytics_runs.c.name],
                    set_={
                        key: value
                        for key, value in run_payload.items()
                        if key not in {"id", "name"}
                    },
                )
            )

            for candidate_chunk in _chunks(candidates, 500):
                await session.execute(
                    analytics_candidates.insert(),
                    [_candidate_to_values(candidate, run_id) for candidate in candidate_chunk],
                )
            for aggregate_chunk in _chunks(aggregates, 500):
                await session.execute(
                    analytics_aggregates.insert(),
                    [_aggregate_to_values(aggregate, run_id) for aggregate in aggregate_chunk],
                )

            await session.commit()

        imported = await self.get_run(run_id)
        if imported is None:
            raise RuntimeError("imported analytics run is not readable")
        return imported


def _chunks[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def _live_run(session: AsyncSession) -> AnalyticsRun:
    processed = int(
        await session.scalar(sa.select(sa.func.count()).select_from(telegram_source_messages)) or 0
    )
    failed = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(
                telegram_source_messages.join(
                    enrichment_jobs,
                    telegram_source_messages.c.enrichment_job_id == enrichment_jobs.c.id,
                )
            )
            .where(enrichment_jobs.c.status == "failed")
        )
        or 0
    )
    completed = int(
        await session.scalar(
            sa.select(sa.func.count()).select_from(
                telegram_source_messages.join(
                    enrichment_results,
                    telegram_source_messages.c.enrichment_job_id == enrichment_results.c.job_id,
                )
            )
        )
        or 0
    )
    leads = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(
                telegram_source_messages.join(
                    enrichment_results,
                    telegram_source_messages.c.enrichment_job_id == enrichment_results.c.job_id,
                )
            )
            .where(sa.cast(_live_assessment_expr()["is_lead"].astext, sa.Boolean).is_(True))
        )
        or 0
    )
    first_seen = await session.scalar(sa.select(sa.func.min(telegram_source_messages.c.created_at)))
    last_seen = await session.scalar(sa.select(sa.func.max(telegram_source_messages.c.created_at)))
    return AnalyticsRun(
        id=LIVE_TELEGRAM_RUN_ID,
        name="Telegram live",
        source="telegram_runtime",
        input_path="telegram_source_messages",
        run_dir="postgresql",
        processed=processed,
        skipped=max(processed - completed - failed, 0),
        failed=failed,
        leads=leads,
        started_at=first_seen,
        finished_at=last_seen,
        imported_at=datetime.now(UTC),
        summary={
            "mode": "live",
            "completed": completed,
            "source": "telegram_source_messages",
        },
    )


def _live_candidate_select() -> Any:
    return sa.select(
        telegram_source_messages.c.id.label("source_message_id"),
        telegram_source_messages.c.source_chat_id,
        telegram_source_messages.c.telegram_message_id,
        telegram_source_messages.c.created_at.label("received_at"),
        telegram_source_messages.c.text,
        telegram_source_messages.c.enrichment_job_id,
        telegram_source_chats.c.title.label("source_chat_title"),
        telegram_source_chats.c.input_ref,
        telegram_source_chats.c.telegram_chat_id,
        enrichment_results.c.result.label("enrichment_result"),
        message_reviews.c.source_message_id.label("review_source_message_id"),
        message_reviews.c.verdict.label("review_verdict"),
        message_reviews.c.comment.label("review_comment"),
        message_reviews.c.tags.label("review_tags"),
        message_reviews.c.created_at.label("review_created_at"),
        message_reviews.c.updated_at.label("review_updated_at"),
    ).select_from(_live_candidate_from_clause())


def _live_candidate_from_clause() -> Any:
    return (
        telegram_source_messages.join(
            telegram_source_chats,
            telegram_source_messages.c.source_chat_id == telegram_source_chats.c.id,
        )
        .join(
            enrichment_results,
            telegram_source_messages.c.enrichment_job_id == enrichment_results.c.job_id,
        )
        .outerjoin(
            message_reviews,
            telegram_source_messages.c.id == message_reviews.c.source_message_id,
        )
    )


def _live_assessment_expr() -> Any:
    return enrichment_results.c.result["lead_assessment"]


def _live_score_expr() -> Any:
    return sa.cast(_live_assessment_expr()["score"].astext, sa.Integer)


def _live_candidate_filter_predicates(
    *,
    score_min: int | None,
    temperature: str | None,
    signal: str | None,
    reason: str | None,
    solution_area: str | None,
    customer_segment: str | None,
    lane: str | None,
    source_chat_id: str | None,
    received_from: datetime | None,
    received_to: datetime | None,
    review_status: str | None,
    verdict: AnalyticsReviewVerdict | None,
    q: str | None,
) -> list[Any]:
    assessment = _live_assessment_expr()
    predicates: list[Any] = []
    if score_min is not None:
        predicates.append(_live_score_expr() >= score_min)
    if temperature:
        predicates.append(assessment["temperature"].astext == temperature)
    if signal:
        predicates.append(enrichment_results.c.result["domain_signals"].contains([{"type": signal}]))
    if reason:
        predicates.append(assessment["reasons"].contains([{"key": reason}]))
    if solution_area:
        predicates.append(assessment["solution_areas"].contains([{"type": solution_area}]))
    if customer_segment:
        predicates.append(assessment["customer_segments"].contains([{"type": customer_segment}]))
    if lane:
        predicates.append(assessment["review_lane"]["key"].astext == lane)
    if source_chat_id:
        try:
            predicates.append(telegram_source_messages.c.source_chat_id == UUID(source_chat_id))
        except ValueError:
            predicates.append(sa.false())
    if received_from is not None:
        predicates.append(telegram_source_messages.c.created_at >= received_from)
    if received_to is not None:
        predicates.append(telegram_source_messages.c.created_at <= received_to)
    if review_status == "reviewed":
        predicates.append(message_reviews.c.source_message_id.is_not(None))
    if review_status == "unreviewed":
        predicates.append(message_reviews.c.source_message_id.is_(None))
    if verdict is not None:
        predicates.append(message_reviews.c.verdict == verdict)
    if q:
        predicates.append(telegram_source_messages.c.text.ilike(f"%{q}%"))
    return predicates


async def _live_candidates(session: AsyncSession) -> list[AnalyticsCandidate]:
    public_base_url = get_settings().public_base_url.rstrip("/")
    result = await session.execute(_live_candidate_select())
    return [_live_candidate_from_row(row, public_base_url) for row in result.mappings()]


def _live_candidate_from_row(row: Any, public_base_url: str) -> AnalyticsCandidate:
    result = dict(row["enrichment_result"] or {})
    assessment = dict(result.get("lead_assessment") or {})
    review_lane = dict(assessment.get("review_lane") or {})
    source_message_id = str(row["source_message_id"])
    telegram_message_id = int(row["telegram_message_id"])
    telegram_message_url = _telegram_message_url(
        input_ref=str(row["input_ref"] or ""),
        telegram_chat_id=row["telegram_chat_id"],
        telegram_message_id=telegram_message_id,
    )
    app_message_url = f"{public_base_url}/#/analytics/message/{source_message_id}"
    return AnalyticsCandidate(
        run_id=LIVE_TELEGRAM_RUN_ID,
        message_id=source_message_id,
        text=str(row["text"]),
        score=int(assessment.get("score") or 0),
        temperature=str(assessment.get("temperature") or "none"),
        review_lane=str(review_lane.get("key") or "none"),
        solution_areas=list(assessment.get("solution_areas") or []),
        customer_segments=list(assessment.get("customer_segments") or []),
        intent_signals=list(assessment.get("intent_signals") or []),
        noise_signals=list(assessment.get("noise_signals") or []),
        reasons=list(assessment.get("reasons") or []),
        domain_signals=list(result.get("domain_signals") or []),
        facts=list(result.get("facts") or []),
        is_lead=bool(assessment.get("is_lead")),
        received_at=row["received_at"],
        source_chat_id=str(row["source_chat_id"]),
        source_chat_title=str(row["source_chat_title"] or ""),
        telegram_chat_id=str(row["telegram_chat_id"] or "") or None,
        telegram_message_id=telegram_message_id,
        telegram_message_url=telegram_message_url,
        app_message_url=app_message_url,
        testing_url=f"{public_base_url}/#/testing?message_id={source_message_id}",
        enrichment_job_id=str(row["enrichment_job_id"]),
        review=_review_from_live_row(row),
    )


def _telegram_message_url(
    *,
    input_ref: str,
    telegram_chat_id: str | None,
    telegram_message_id: int,
) -> str | None:
    normalized = input_ref.strip().rstrip("/")
    if normalized.startswith("@") and len(normalized) > 1:
        return f"https://t.me/{normalized[1:]}/{telegram_message_id}"
    if normalized.startswith("https://t.me/") and "/+" not in normalized:
        return f"{normalized}/{telegram_message_id}"
    if telegram_chat_id and telegram_chat_id.startswith("-100"):
        return f"https://t.me/c/{telegram_chat_id[4:]}/{telegram_message_id}"
    return None


def _live_aggregates(candidates: Sequence[AnalyticsCandidate]) -> list[AnalyticsAggregate]:
    aggregates: list[AnalyticsAggregate] = []
    aggregates.extend(_score_bucket_aggregates(candidates))
    aggregates.extend(_object_aggregates("signal", (item.domain_signals for item in candidates)))
    aggregates.extend(_object_aggregates("reason", (item.reasons for item in candidates), key_name="key"))
    aggregates.extend(_object_aggregates("solution_area", (item.solution_areas for item in candidates)))
    aggregates.extend(_object_aggregates("customer_segment", (item.customer_segments for item in candidates)))
    aggregates.extend(_source_chat_aggregates(candidates))
    aggregates.extend(_review_aggregates(candidates))
    lane_counter = Counter(candidate.review_lane for candidate in candidates)
    aggregates.extend(
        AnalyticsAggregate(kind="review_lane", key=key, label=key, count=count)
        for key, count in lane_counter.most_common()
        if key and key != "none"
    )
    return aggregates


def _score_bucket_aggregates(candidates: Sequence[AnalyticsCandidate]) -> list[AnalyticsAggregate]:
    buckets = [
        ("0-34", 0, 34),
        ("35-59", 35, 59),
        ("60-89", 60, 89),
        ("90+", 90, None),
    ]
    result: list[AnalyticsAggregate] = []
    for label, minimum, maximum in buckets:
        count = sum(
            1
            for candidate in candidates
            if candidate.score >= minimum and (maximum is None or candidate.score <= maximum)
        )
        if count:
            result.append(
                AnalyticsAggregate(
                    kind="score_bucket",
                    key=label,
                    label=label,
                    count=count,
                    payload={"min_score": minimum, "max_score": maximum},
                )
            )
    return result


def _object_aggregates(
    kind: str,
    groups: Iterable[list[dict[str, Any]]],
    *,
    key_name: str = "type",
) -> list[AnalyticsAggregate]:
    labels: dict[str, str] = {}
    counter: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for group in groups:
        seen_in_message: set[str] = set()
        for item in group:
            key = str(item.get(key_name) or "")
            if not key or key in seen_in_message:
                continue
            seen_in_message.add(key)
            counter[key] += 1
            labels[key] = str(item.get("label") or key)
            text = item.get("text") or item.get("matched_texts")
            if text and len(examples.setdefault(key, [])) < 5:
                examples[key].append(str(text))
    return [
        AnalyticsAggregate(
            kind=kind,
            key=key,
            label=labels.get(key, key),
            count=count,
            payload={"examples": examples.get(key, [])},
        )
        for key, count in counter.most_common()
    ]


def _run_to_values(run: AnalyticsRun, run_id: UUID) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": run.name,
        "source": run.source,
        "input_path": run.input_path,
        "run_dir": run.run_dir,
        "processed": run.processed,
        "skipped": run.skipped,
        "failed": run.failed,
        "leads": run.leads,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "imported_at": run.imported_at,
        "summary": run.summary,
    }


def _candidate_to_values(candidate: AnalyticsCandidate, run_id: UUID) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "run_id": run_id,
        "message_id": candidate.message_id,
        "text": candidate.text,
        "score": candidate.score,
        "temperature": candidate.temperature,
        "review_lane": candidate.review_lane,
        "solution_areas": candidate.solution_areas,
        "customer_segments": candidate.customer_segments,
        "intent_signals": candidate.intent_signals,
        "noise_signals": candidate.noise_signals,
        "reasons": candidate.reasons,
        "domain_signals": candidate.domain_signals,
        "facts": candidate.facts,
        "received_at": candidate.received_at,
        "source_chat_id": candidate.source_chat_id,
        "source_chat_title": candidate.source_chat_title,
        "signal_types": _unique_texts(item.get("type") for item in candidate.domain_signals),
        "fact_types": _unique_texts(item.get("type") for item in candidate.facts),
        "reason_keys": _unique_texts(item.get("key") for item in candidate.reasons),
        "solution_area_types": _unique_texts(item.get("type") for item in candidate.solution_areas),
        "customer_segment_types": _unique_texts(item.get("type") for item in candidate.customer_segments),
    }


def _aggregate_to_values(aggregate: AnalyticsAggregate, run_id: UUID) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "run_id": run_id,
        "kind": aggregate.kind,
        "key": aggregate.key,
        "label": aggregate.label,
        "count": aggregate.count,
        "payload": aggregate.payload,
    }


def _unique_texts(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text and text not in unique:
            unique.append(text)
    return unique


def _run_from_row(row: Any) -> AnalyticsRun:
    return AnalyticsRun(
        id=row["id"],
        name=str(row["name"]),
        source=str(row["source"]),
        input_path=str(row["input_path"]),
        run_dir=str(row["run_dir"]),
        processed=int(row["processed"]),
        skipped=int(row["skipped"]),
        failed=int(row["failed"]),
        leads=int(row["leads"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        imported_at=row["imported_at"] or datetime.now(UTC),
        summary=dict(row["summary"] or {}),
    )


def _aggregate_from_row(row: Any) -> AnalyticsAggregate:
    return AnalyticsAggregate(
        kind=str(row["kind"]),
        key=str(row["key"]),
        label=str(row["label"]),
        count=int(row["count"]),
        payload=dict(row["payload"] or {}),
    )


def _candidate_from_row(row: Any) -> AnalyticsCandidate:
    return AnalyticsCandidate(
        run_id=row["run_id"],
        message_id=str(row["message_id"]),
        text=str(row["text"]),
        score=int(row["score"]),
        temperature=str(row["temperature"]),
        review_lane=str(row["review_lane"]),
        solution_areas=list(row["solution_areas"] or []),
        customer_segments=list(row["customer_segments"] or []),
        intent_signals=list(row["intent_signals"] or []),
        noise_signals=list(row["noise_signals"] or []),
        reasons=list(row["reasons"] or []),
        domain_signals=list(row["domain_signals"] or []),
        facts=list(row["facts"] or []),
        received_at=row["received_at"],
        source_chat_id=row["source_chat_id"],
        source_chat_title=row["source_chat_title"],
    )


def _review_from_row(row: Any) -> AnalyticsMessageReview:
    return AnalyticsMessageReview(
        source_message_id=str(row["source_message_id"]),
        verdict=cast(AnalyticsReviewVerdict | None, row["verdict"]),
        comment=str(row["comment"] or ""),
        tags=_list_of_strings(row["tags"] or []),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _review_from_live_row(row: Any) -> AnalyticsMessageReview | None:
    source_message_id = row["review_source_message_id"]
    if source_message_id is None:
        return None
    return AnalyticsMessageReview(
        source_message_id=str(source_message_id),
        verdict=cast(AnalyticsReviewVerdict | None, row["review_verdict"]),
        comment=str(row["review_comment"] or ""),
        tags=_list_of_strings(row["review_tags"] or []),
        created_at=row["review_created_at"],
        updated_at=row["review_updated_at"],
    )


def _list_of_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if value is not None]


def _source_chat_aggregates(candidates: Sequence[AnalyticsCandidate]) -> list[AnalyticsAggregate]:
    labels: dict[str, str] = {}
    counter: Counter[str] = Counter()
    for candidate in candidates:
        if not candidate.source_chat_id:
            continue
        counter[candidate.source_chat_id] += 1
        labels[candidate.source_chat_id] = candidate.source_chat_title or candidate.source_chat_id
    return [
        AnalyticsAggregate(
            kind="source_chat",
            key=key,
            label=labels.get(key, key),
            count=count,
        )
        for key, count in counter.most_common()
    ]


def _review_aggregates(candidates: Sequence[AnalyticsCandidate]) -> list[AnalyticsAggregate]:
    status_counter: Counter[str] = Counter(
        "reviewed" if candidate.review is not None else "unreviewed"
        for candidate in candidates
    )
    verdict_counter: Counter[str] = Counter(
        str(candidate.review.verdict)
        for candidate in candidates
        if candidate.review is not None and candidate.review.verdict
    )
    status_labels = {
        "reviewed": "С ревью",
        "unreviewed": "Без ревью",
    }
    verdict_labels = {
        "lead": "Лид",
        "not_lead": "Не лид",
        "uncertain": "Сомнительно",
        "noise": "Шум",
    }
    return [
        *[
            AnalyticsAggregate(
                kind="review_status",
                key=key,
                label=status_labels.get(key, key),
                count=count,
            )
            for key, count in status_counter.most_common()
        ],
        *[
            AnalyticsAggregate(
                kind="review_verdict",
                key=key,
                label=verdict_labels.get(key, key),
                count=count,
            )
            for key, count in verdict_counter.most_common()
        ],
    ]


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
