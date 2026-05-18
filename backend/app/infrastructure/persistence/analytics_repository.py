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

from app.application.evaluation.review_eval import ReviewEvalRow, review_eval_row_from_mapping
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidateLlmSummary
from app.domain.analytics import AnalyticsCandidatePage
from app.domain.analytics import AnalyticsMessageReview
from app.domain.analytics import AnalyticsReviewVerdict
from app.domain.analytics import AnalyticsRun
from app.core.config import get_settings
from app.infrastructure.persistence.tables import analytics_aggregates, analytics_candidates
from app.infrastructure.persistence.tables import analytics_runs
from app.infrastructure.persistence.tables import enrichment_jobs, enrichment_results
from app.infrastructure.persistence.tables import llm_verifications
from app.infrastructure.persistence.tables import message_reviews
from app.infrastructure.persistence.tables import notification_outbox
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

    async def cancel_unsent_notifications_for_message(self, message_id: str, *, reason: str) -> int:
        source_message_id = UUID(message_id)
        async with self._session_factory() as session:
            result = await session.execute(
                notification_outbox.update()
                .where(notification_outbox.c.source_message_id == source_message_id)
                .where(notification_outbox.c.status.in_(["pending", "sending"]))
                .values(
                    status="cancelled",
                    last_error=reason,
                    claimed_at=None,
                )
            )
            await session.commit()
        return int(cast(Any, result).rowcount or 0)

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

    async def list_review_eval_rows(self, *, limit: int | None = None) -> list[ReviewEvalRow]:
        statement = (
            sa.select(
                message_reviews.c.source_message_id,
                message_reviews.c.verdict,
                telegram_source_messages.c.telegram_message_id,
                telegram_source_messages.c.text,
                telegram_source_chats.c.title.label("source_chat_title"),
                enrichment_results.c.result,
            )
            .select_from(
                message_reviews.join(
                    telegram_source_messages,
                    telegram_source_messages.c.id == message_reviews.c.source_message_id,
                )
                .outerjoin(
                    telegram_source_chats,
                    telegram_source_chats.c.id == telegram_source_messages.c.source_chat_id,
                )
                .outerjoin(
                    enrichment_results,
                    enrichment_results.c.job_id == telegram_source_messages.c.enrichment_job_id,
                )
            )
            .order_by(message_reviews.c.updated_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)

        async with self._session_factory() as session:
            result = await session.execute(statement)
            return [review_eval_row_from_mapping(row._mapping) for row in result]

    async def list_candidates(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
        score_min: int | None,
        score_max: int | None,
        temperature: str | None,
        signal: str | None,
        reason: str | None,
        solution_area: str | None,
        customer_segment: str | None,
        lane: str | None,
        message_id: str | None,
        source_chat: str | None,
        source_chat_id: str | None,
        source_input_ref: str | None,
        source_chat_status: str | None,
        telegram_message_id: int | None,
        telegram_chat_id: str | None,
        sender: str | None,
        source_account_id: str | None,
        received_from: datetime | None,
        received_to: datetime | None,
        review_status: str | None,
        verdict: AnalyticsReviewVerdict | None,
        source_type: str | None,
        llm_processed: bool | None,
        llm_status: str | None,
        llm_verdict: str | None,
        llm_recommendation: str | None,
        llm_model: str | None,
        llm_route: str | None,
        llm_agrees_with_rules: bool | None,
        llm_has_error: bool | None,
        llm_confidence_min: float | None,
        llm_confidence_max: float | None,
        llm_attempts_min: int | None,
        llm_attempts_max: int | None,
        enrichment_status: str | None,
        sort_by: str | None,
        sort_direction: str | None,
        q: str | None,
        grid_filters: Sequence[dict[str, str]] | None = None,
    ) -> AnalyticsCandidatePage:
        received_from = _aware_utc(received_from)
        received_to = _aware_utc(received_to)
        if run_id == LIVE_TELEGRAM_RUN_ID:
            public_base_url = get_settings().public_base_url.rstrip("/")
            async with self._session_factory() as session:
                latest_llm = _latest_llm_subquery()
                from_clause = _live_candidate_from_clause(latest_llm=latest_llm)
                predicates = _live_candidate_filter_predicates(
                    score_min=score_min,
                    score_max=score_max,
                    temperature=temperature,
                    signal=signal,
                    reason=reason,
                    solution_area=solution_area,
                    customer_segment=customer_segment,
                    lane=lane,
                    message_id=message_id,
                    source_chat=source_chat,
                    source_chat_id=source_chat_id,
                    source_input_ref=source_input_ref,
                    source_chat_status=source_chat_status,
                    telegram_message_id=telegram_message_id,
                    telegram_chat_id=telegram_chat_id,
                    sender=sender,
                    source_account_id=source_account_id,
                    received_from=received_from,
                    received_to=received_to,
                    review_status=review_status,
                    verdict=verdict,
                    source_type=source_type,
                    llm_processed=llm_processed,
                    llm_status=llm_status,
                    llm_verdict=llm_verdict,
                    llm_recommendation=llm_recommendation,
                    llm_model=llm_model,
                    llm_route=llm_route,
                    llm_agrees_with_rules=llm_agrees_with_rules,
                    llm_has_error=llm_has_error,
                    llm_confidence_min=llm_confidence_min,
                    llm_confidence_max=llm_confidence_max,
                    llm_attempts_min=llm_attempts_min,
                    llm_attempts_max=llm_attempts_max,
                    enrichment_status=enrichment_status,
                    q=q,
                    grid_filters=grid_filters,
                    latest_llm=latest_llm,
                )
                total = int(
                    await session.scalar(
                        sa.select(sa.func.count())
                        .select_from(from_clause)
                        .where(*predicates)
                    )
                    or 0
                )
                result = await session.execute(
                    _live_candidate_select(from_clause=from_clause, latest_llm=latest_llm)
                    .where(*predicates)
                    .order_by(*_live_candidate_order_by(sort_by, sort_direction, latest_llm=latest_llm))
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

        if source_type is not None and source_type != "telegram":
            return AnalyticsCandidatePage(total=0, items=[])
        if _has_positive_llm_filter(
            llm_processed=llm_processed,
            llm_status=llm_status,
            llm_verdict=llm_verdict,
            llm_recommendation=llm_recommendation,
            llm_model=llm_model,
            llm_route=llm_route,
            llm_agrees_with_rules=llm_agrees_with_rules,
            llm_has_error=llm_has_error,
        ) or _has_live_only_candidate_filter(
            sender=sender,
            source_input_ref=source_input_ref,
            source_chat_status=source_chat_status,
            telegram_chat_id=telegram_chat_id,
            source_account_id=source_account_id,
            llm_confidence_min=llm_confidence_min,
            llm_confidence_max=llm_confidence_max,
            llm_attempts_min=llm_attempts_min,
            llm_attempts_max=llm_attempts_max,
            enrichment_status=enrichment_status,
        ):
            return AnalyticsCandidatePage(total=0, items=[])

        predicates = [analytics_candidates.c.run_id == run_id]
        if score_min is not None:
            predicates.append(analytics_candidates.c.score >= score_min)
        if score_max is not None:
            predicates.append(analytics_candidates.c.score <= score_max)
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
        if source_chat:
            source_chat_pattern = f"%{source_chat.strip()}%"
            predicates.append(
                sa.or_(
                    analytics_candidates.c.source_chat_title.ilike(source_chat_pattern),
                    analytics_candidates.c.source_chat_id.ilike(source_chat_pattern),
                )
            )
        if message_id:
            predicates.append(analytics_candidates.c.message_id.ilike(f"%{message_id.strip()}%"))
        if telegram_message_id is not None:
            predicates.append(analytics_candidates.c.message_id == str(telegram_message_id))
        if received_from is not None:
            predicates.append(analytics_candidates.c.received_at >= received_from)
        if received_to is not None:
            predicates.append(analytics_candidates.c.received_at <= received_to)
        if q:
            predicates.append(analytics_candidates.c.text.ilike(f"%{q}%"))
        predicates.extend(_imported_grid_filter_predicates(grid_filters or []))
        if review_status == "reviewed" or verdict is not None:
            return AnalyticsCandidatePage(total=0, items=[])

        async with self._session_factory() as session:
            imported_total = await session.scalar(
                sa.select(sa.func.count()).select_from(analytics_candidates).where(*predicates)
            )
            result = await session.execute(
                sa.select(analytics_candidates)
                .where(*predicates)
                .order_by(*_imported_candidate_order_by(sort_by, sort_direction))
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


def _has_positive_llm_filter(
    *,
    llm_processed: bool | None,
    llm_status: str | None,
    llm_verdict: str | None,
    llm_recommendation: str | None,
    llm_model: str | None,
    llm_route: str | None,
    llm_agrees_with_rules: bool | None,
    llm_has_error: bool | None,
) -> bool:
    return (
        llm_processed is True
        or bool(llm_status)
        or bool(llm_verdict)
        or bool(llm_recommendation)
        or bool(llm_model)
        or bool(llm_route)
        or llm_agrees_with_rules is not None
        or llm_has_error is True
    )


def _has_live_only_candidate_filter(
    *,
    sender: str | None,
    source_input_ref: str | None,
    source_chat_status: str | None,
    telegram_chat_id: str | None,
    source_account_id: str | None,
    llm_confidence_min: float | None,
    llm_confidence_max: float | None,
    llm_attempts_min: int | None,
    llm_attempts_max: int | None,
    enrichment_status: str | None,
) -> bool:
    return any(
        value is not None and value != ""
        for value in (
            sender,
            source_input_ref,
            source_chat_status,
            telegram_chat_id,
            source_account_id,
            llm_confidence_min,
            llm_confidence_max,
            llm_attempts_min,
            llm_attempts_max,
            enrichment_status,
        )
    )


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
            .select_from(_live_candidate_from_clause())
            .where(_live_effective_is_lead_expr().is_(True))
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


def _live_candidate_select(*, from_clause: Any | None = None, latest_llm: Any | None = None) -> Any:
    if latest_llm is None:
        latest_llm = _latest_llm_subquery()
    if from_clause is None:
        from_clause = _live_candidate_from_clause(latest_llm=latest_llm)
    return sa.select(
        telegram_source_messages.c.id.label("source_message_id"),
        telegram_source_messages.c.account_id.label("source_account_id"),
        telegram_source_messages.c.source_chat_id,
        telegram_source_messages.c.telegram_message_id,
        telegram_source_messages.c.message_date,
        telegram_source_messages.c.sender_id,
        telegram_source_messages.c.sender_username,
        telegram_source_messages.c.created_at.label("received_at"),
        telegram_source_messages.c.text,
        telegram_source_messages.c.raw_payload,
        telegram_source_messages.c.enrichment_job_id,
        telegram_source_chats.c.title.label("source_chat_title"),
        telegram_source_chats.c.input_ref,
        telegram_source_chats.c.telegram_chat_id,
        telegram_source_chats.c.enabled.label("source_chat_enabled"),
        telegram_source_chats.c.status.label("source_chat_status"),
        telegram_source_chats.c.last_message_id.label("source_chat_last_message_id"),
        telegram_source_chats.c.last_error.label("source_chat_last_error"),
        enrichment_jobs.c.status.label("enrichment_status"),
        enrichment_jobs.c.error.label("enrichment_error"),
        enrichment_jobs.c.created_at.label("enrichment_created_at"),
        enrichment_jobs.c.started_at.label("enrichment_started_at"),
        enrichment_jobs.c.finished_at.label("enrichment_finished_at"),
        enrichment_jobs.c.updated_at.label("enrichment_updated_at"),
        enrichment_results.c.result.label("enrichment_result"),
        latest_llm.c.llm_run_id,
        latest_llm.c.llm_status,
        latest_llm.c.llm_model,
        latest_llm.c.llm_route_id,
        latest_llm.c.llm_attempts,
        latest_llm.c.llm_response,
        latest_llm.c.llm_error,
        latest_llm.c.llm_created_at,
        latest_llm.c.llm_updated_at,
        message_reviews.c.source_message_id.label("review_source_message_id"),
        message_reviews.c.verdict.label("review_verdict"),
        message_reviews.c.comment.label("review_comment"),
        message_reviews.c.tags.label("review_tags"),
        message_reviews.c.created_at.label("review_created_at"),
        message_reviews.c.updated_at.label("review_updated_at"),
    ).select_from(from_clause)


def _live_candidate_from_clause(*, latest_llm: Any | None = None) -> Any:
    from_clause = (
        telegram_source_messages.join(
            telegram_source_chats,
            telegram_source_messages.c.source_chat_id == telegram_source_chats.c.id,
        )
        .join(
            enrichment_jobs,
            telegram_source_messages.c.enrichment_job_id == enrichment_jobs.c.id,
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
    if latest_llm is not None:
        from_clause = from_clause.outerjoin(
            latest_llm,
            latest_llm.c.source_message_id == telegram_source_messages.c.id,
        )
    return from_clause


def _latest_llm_subquery() -> Any:
    ranked = (
        sa.select(
            llm_verifications.c.id.label("llm_run_id"),
            llm_verifications.c.source_message_id,
            llm_verifications.c.status.label("llm_status"),
            llm_verifications.c.model.label("llm_model"),
            llm_verifications.c.route_id.label("llm_route_id"),
            llm_verifications.c.attempts.label("llm_attempts"),
            llm_verifications.c.response.label("llm_response"),
            llm_verifications.c.error.label("llm_error"),
            llm_verifications.c.created_at.label("llm_created_at"),
            llm_verifications.c.updated_at.label("llm_updated_at"),
            sa.func.row_number()
            .over(
                partition_by=llm_verifications.c.source_message_id,
                order_by=(
                    llm_verifications.c.updated_at.desc(),
                    llm_verifications.c.created_at.desc(),
                    llm_verifications.c.id.desc(),
                ),
            )
            .label("llm_rank"),
        )
        .select_from(llm_verifications)
        .subquery("latest_llm_ranked")
    )
    return (
        sa.select(
            ranked.c.llm_run_id,
            ranked.c.source_message_id,
            ranked.c.llm_status,
            ranked.c.llm_model,
            ranked.c.llm_route_id,
            ranked.c.llm_attempts,
            ranked.c.llm_response,
            ranked.c.llm_error,
            ranked.c.llm_created_at,
            ranked.c.llm_updated_at,
        )
        .where(ranked.c.llm_rank == 1)
        .subquery("latest_llm")
    )


def _live_assessment_expr() -> Any:
    return enrichment_results.c.result["lead_assessment"]


def _live_score_expr() -> Any:
    return sa.cast(_live_assessment_expr()["score"].astext, sa.Integer)


def _live_auto_is_lead_expr() -> Any:
    return sa.cast(_live_assessment_expr()["is_lead"].astext, sa.Boolean).is_(True)


def _live_effective_is_lead_expr() -> Any:
    return sa.case(
        (message_reviews.c.verdict == "lead", sa.true()),
        (message_reviews.c.verdict.in_(["not_lead", "noise"]), sa.false()),
        else_=_live_auto_is_lead_expr(),
    )


def _live_candidate_filter_predicates(
    *,
    score_min: int | None,
    score_max: int | None,
    temperature: str | None,
    signal: str | None,
    reason: str | None,
    solution_area: str | None,
    customer_segment: str | None,
    lane: str | None,
    message_id: str | None,
    source_chat: str | None,
    source_chat_id: str | None,
    source_input_ref: str | None,
    source_chat_status: str | None,
    telegram_message_id: int | None,
    telegram_chat_id: str | None,
    sender: str | None,
    source_account_id: str | None,
    received_from: datetime | None,
    received_to: datetime | None,
    review_status: str | None,
    verdict: AnalyticsReviewVerdict | None,
    source_type: str | None,
    llm_processed: bool | None,
    llm_status: str | None,
    llm_verdict: str | None,
    llm_recommendation: str | None,
    llm_model: str | None,
    llm_route: str | None,
    llm_agrees_with_rules: bool | None,
    llm_has_error: bool | None,
    llm_confidence_min: float | None,
    llm_confidence_max: float | None,
    llm_attempts_min: int | None,
    llm_attempts_max: int | None,
    enrichment_status: str | None,
    q: str | None,
    grid_filters: Sequence[dict[str, str]] | None,
    latest_llm: Any,
) -> list[Any]:
    assessment = _live_assessment_expr()
    predicates: list[Any] = []
    if source_type is not None and source_type != "telegram":
        predicates.append(sa.false())
    if score_min is not None:
        predicates.append(_live_score_expr() >= score_min)
    if score_max is not None:
        predicates.append(_live_score_expr() <= score_max)
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
    if message_id:
        predicates.append(sa.cast(telegram_source_messages.c.id, sa.Text).ilike(f"%{message_id.strip()}%"))
    if source_chat:
        pattern = f"%{source_chat.strip()}%"
        predicates.append(
            sa.or_(
                telegram_source_chats.c.title.ilike(pattern),
                telegram_source_chats.c.input_ref.ilike(pattern),
                sa.cast(telegram_source_messages.c.source_chat_id, sa.Text).ilike(pattern),
                sa.cast(telegram_source_chats.c.telegram_chat_id, sa.Text).ilike(pattern),
            )
        )
    if source_chat_id:
        try:
            predicates.append(telegram_source_messages.c.source_chat_id == UUID(source_chat_id))
        except ValueError:
            predicates.append(sa.false())
    if source_input_ref:
        predicates.append(telegram_source_chats.c.input_ref.ilike(f"%{source_input_ref.strip()}%"))
    if source_chat_status:
        predicates.append(telegram_source_chats.c.status.ilike(f"%{source_chat_status.strip()}%"))
    if telegram_message_id is not None:
        predicates.append(telegram_source_messages.c.telegram_message_id == telegram_message_id)
    if telegram_chat_id:
        predicates.append(sa.cast(telegram_source_chats.c.telegram_chat_id, sa.Text).ilike(f"%{telegram_chat_id.strip()}%"))
    if sender:
        sender_needle = sender.strip().removeprefix("@")
        predicates.append(
            sa.or_(
                telegram_source_messages.c.sender_username.ilike(f"%{sender_needle}%"),
                sa.cast(telegram_source_messages.c.sender_id, sa.Text).ilike(f"%{sender_needle}%"),
            )
        )
    if source_account_id:
        predicates.append(sa.cast(telegram_source_messages.c.account_id, sa.Text).ilike(f"%{source_account_id.strip()}%"))
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
    if llm_processed is True:
        predicates.append(latest_llm.c.llm_run_id.is_not(None))
    if llm_processed is False:
        predicates.append(latest_llm.c.llm_run_id.is_(None))
    if llm_status:
        predicates.append(latest_llm.c.llm_status == llm_status)
    if llm_verdict:
        predicates.append(latest_llm.c.llm_response["verdict"].astext == llm_verdict)
    if llm_recommendation:
        predicates.append(latest_llm.c.llm_response["recommendation"].astext == llm_recommendation)
    if llm_model:
        predicates.append(latest_llm.c.llm_model == llm_model)
    if llm_route:
        predicates.append(latest_llm.c.llm_route_id == llm_route)
    if llm_agrees_with_rules is not None:
        predicates.append(
            sa.cast(latest_llm.c.llm_response["agrees_with_rule_engine"].astext, sa.Boolean).is_(
                llm_agrees_with_rules
            )
        )
    if llm_has_error is True:
        predicates.append(latest_llm.c.llm_error.is_not(None))
    if llm_has_error is False:
        predicates.append(latest_llm.c.llm_error.is_(None))
    if llm_confidence_min is not None:
        predicates.append(sa.cast(latest_llm.c.llm_response["confidence"].astext, sa.Float) >= llm_confidence_min)
    if llm_confidence_max is not None:
        predicates.append(sa.cast(latest_llm.c.llm_response["confidence"].astext, sa.Float) <= llm_confidence_max)
    if llm_attempts_min is not None:
        predicates.append(latest_llm.c.llm_attempts >= llm_attempts_min)
    if llm_attempts_max is not None:
        predicates.append(latest_llm.c.llm_attempts <= llm_attempts_max)
    if enrichment_status:
        predicates.append(enrichment_jobs.c.status == enrichment_status)
    if q:
        predicates.append(telegram_source_messages.c.text.ilike(f"%{q}%"))
    predicates.extend(_live_grid_filter_predicates(grid_filters or [], latest_llm=latest_llm))
    return predicates


def _live_grid_filter_predicates(filters: Sequence[dict[str, str]], *, latest_llm: Any) -> list[Any]:
    assessment = _live_assessment_expr()
    expressions: dict[str, tuple[Any, bool]] = {
        "sourceType": (sa.literal("telegram"), False),
        "sourceChat": (telegram_source_chats.c.title, False),
        "sourceChatId": (telegram_source_messages.c.source_chat_id, False),
        "sourceInputRef": (telegram_source_chats.c.input_ref, False),
        "sourceChatStatus": (telegram_source_chats.c.status, False),
        "telegramMessageId": (telegram_source_messages.c.telegram_message_id, True),
        "telegramChatId": (telegram_source_chats.c.telegram_chat_id, False),
        "sender": (
            sa.case(
                (
                    telegram_source_messages.c.sender_username.is_not(None),
                    sa.func.concat("@", telegram_source_messages.c.sender_username),
                ),
                else_=sa.cast(telegram_source_messages.c.sender_id, sa.Text),
            ),
            False,
        ),
        "messageId": (telegram_source_messages.c.id, False),
        "sourceAccountId": (telegram_source_messages.c.account_id, False),
        "score": (_live_score_expr(), True),
        "temperature": (assessment["temperature"].astext, False),
        "reviewLane": (assessment["review_lane"]["key"].astext, False),
        "reviewStatus": (
            sa.case(
                (message_reviews.c.source_message_id.is_not(None), "reviewed"),
                else_="unreviewed",
            ),
            False,
        ),
        "llmStatus": (
            sa.case(
                (latest_llm.c.llm_run_id.is_(None), "not_processed"),
                else_=sa.func.coalesce(latest_llm.c.llm_status, "processed"),
            ),
            False,
        ),
        "llmVerdict": (latest_llm.c.llm_response["verdict"].astext, False),
        "llmConfidence": (sa.cast(latest_llm.c.llm_response["confidence"].astext, sa.Float), True),
        "llmRecommendation": (latest_llm.c.llm_response["recommendation"].astext, False),
        "llmAgreement": (
            sa.case(
                (
                    sa.cast(latest_llm.c.llm_response["agrees_with_rule_engine"].astext, sa.Boolean).is_(True),
                    "true",
                ),
                (
                    sa.cast(latest_llm.c.llm_response["agrees_with_rule_engine"].astext, sa.Boolean).is_(False),
                    "false",
                ),
                else_="",
            ),
            False,
        ),
        "llmModel": (latest_llm.c.llm_model, False),
        "llmRoute": (latest_llm.c.llm_route_id, False),
        "llmAttempts": (latest_llm.c.llm_attempts, True),
        "llmError": (
            sa.case((latest_llm.c.llm_error.is_not(None), "true"), else_="false"),
            False,
        ),
        "text": (telegram_source_messages.c.text, False),
        "enrichmentStatus": (enrichment_jobs.c.status, False),
    }
    collections: dict[str, tuple[Any, str | None]] = {
        "reasons": (assessment["reasons"], "key"),
        "solutionAreas": (assessment["solution_areas"], "type"),
        "customerSegments": (assessment["customer_segments"], "type"),
        "domainSignals": (enrichment_results.c.result["domain_signals"], "type"),
        "facts": (enrichment_results.c.result["facts"], "text"),
    }
    return _grid_filter_predicates(filters, expressions=expressions, collections=collections)


def _imported_grid_filter_predicates(filters: Sequence[dict[str, str]]) -> list[Any]:
    expressions: dict[str, tuple[Any, bool]] = {
        "sourceType": (sa.literal("telegram"), False),
        "receivedAt": (analytics_candidates.c.received_at, False),
        "messageDate": (analytics_candidates.c.received_at, False),
        "sourceChat": (
            sa.func.concat_ws(" ", analytics_candidates.c.source_chat_title, analytics_candidates.c.source_chat_id),
            False,
        ),
        "sourceChatId": (analytics_candidates.c.source_chat_id, False),
        "messageId": (analytics_candidates.c.message_id, False),
        "telegramMessageId": (analytics_candidates.c.message_id, False),
        "score": (analytics_candidates.c.score, True),
        "temperature": (analytics_candidates.c.temperature, False),
        "reviewLane": (analytics_candidates.c.review_lane, False),
        "reviewStatus": (sa.literal("unreviewed"), False),
        "llmStatus": (sa.literal("not_processed"), False),
        "text": (analytics_candidates.c.text, False),
    }
    collections: dict[str, tuple[Any, str | None]] = {
        "domainSignals": (analytics_candidates.c.signal_types, None),
        "reasons": (analytics_candidates.c.reason_keys, None),
        "solutionAreas": (analytics_candidates.c.solution_area_types, None),
        "customerSegments": (analytics_candidates.c.customer_segment_types, None),
    }
    return _grid_filter_predicates(filters, expressions=expressions, collections=collections)


def _grid_filter_predicates(
    filters: Sequence[dict[str, str]],
    *,
    expressions: dict[str, tuple[Any, bool]],
    collections: dict[str, tuple[Any, str | None]],
) -> list[Any]:
    predicates: list[Any] = []
    for filter_item in filters:
        field = str(filter_item.get("field") or "").strip()
        operator = str(filter_item.get("operator") or "").strip() or "contains"
        value = str(filter_item.get("value") or "").strip()
        if not field or not value:
            continue
        collection = collections.get(field)
        if collection is not None:
            predicate = _grid_collection_filter(collection[0], collection[1], operator, value)
            if predicate is not None:
                predicates.append(predicate)
            continue
        expression = expressions.get(field)
        if expression is None:
            continue
        predicate = _grid_value_filter(expression[0], operator, value, numeric=expression[1])
        if predicate is not None:
            predicates.append(predicate)
    return predicates


def _grid_value_filter(expression: Any, operator: str, value: str, *, numeric: bool) -> Any | None:
    normalized_operator = _normalized_grid_operator(operator)
    if numeric:
        try:
            numeric_value = float(value)
        except ValueError:
            return None
        if normalized_operator == "equals":
            return expression == numeric_value
        if normalized_operator == "not_equals":
            return sa.or_(expression.is_(None), expression != numeric_value)
        if operator == ">":
            return expression > numeric_value
        if operator == ">=":
            return expression >= numeric_value
        if operator == "<":
            return expression < numeric_value
        if operator == "<=":
            return expression <= numeric_value

    text_expression = sa.func.lower(sa.func.coalesce(sa.cast(expression, sa.Text), ""))
    lowered_value = value.lower()
    if normalized_operator == "equals":
        return text_expression == lowered_value
    if normalized_operator == "not_equals":
        return text_expression != lowered_value
    if normalized_operator == "not_contains":
        return sa.not_(text_expression.ilike(_like_pattern(lowered_value), escape="\\"))
    return text_expression.ilike(_like_pattern(lowered_value), escape="\\")


def _grid_collection_filter(expression: Any, key: str | None, operator: str, value: str) -> Any | None:
    normalized_operator = _normalized_grid_operator(operator)
    if key is not None and normalized_operator in {"equals", "not_equals"}:
        predicate = expression.contains([{key: value}])
        return sa.not_(predicate) if normalized_operator == "not_equals" else predicate
    if key is None and normalized_operator in {"equals", "not_equals"}:
        predicate = sa.literal(value) == sa.any_(expression)
        return sa.not_(predicate) if normalized_operator == "not_equals" else predicate
    text_expression = sa.func.lower(sa.func.coalesce(sa.cast(expression, sa.Text), ""))
    predicate = text_expression.ilike(_like_pattern(value.lower()), escape="\\")
    return sa.not_(predicate) if normalized_operator == "not_contains" else predicate


def _normalized_grid_operator(operator: str) -> str:
    if operator in {"equals", "=", "is"}:
        return "equals"
    if operator in {"notEquals", "!=", "not"}:
        return "not_equals"
    if operator == "notContains":
        return "not_contains"
    return "contains"


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _live_candidate_order_by(sort_by: str | None, sort_direction: str | None, *, latest_llm: Any) -> list[Any]:
    expression = _live_candidate_sort_expression(sort_by, latest_llm=latest_llm)
    fallback = [
        telegram_source_messages.c.created_at.desc(),
        telegram_source_messages.c.telegram_message_id.desc(),
        telegram_source_messages.c.id.desc(),
    ]
    if expression is None:
        return fallback
    return [_ordered_expression(expression, sort_direction), *fallback]


def _imported_candidate_order_by(sort_by: str | None, sort_direction: str | None) -> list[Any]:
    expression = _imported_candidate_sort_expression(sort_by)
    fallback = [
        analytics_candidates.c.received_at.desc().nullslast(),
        analytics_candidates.c.message_id.desc(),
        analytics_candidates.c.score.desc(),
    ]
    if expression is None:
        return fallback
    return [_ordered_expression(expression, sort_direction), *fallback]


def _ordered_expression(expression: Any, sort_direction: str | None) -> Any:
    ordered = expression.asc() if sort_direction == "asc" else expression.desc()
    return ordered.nullslast()


def _live_candidate_sort_expression(sort_by: str | None, *, latest_llm: Any) -> Any | None:
    assessment = _live_assessment_expr()
    expressions: dict[str, Any] = {
        "sourceType": sa.literal("telegram"),
        "receivedAt": telegram_source_messages.c.created_at,
        "messageDate": telegram_source_messages.c.message_date,
        "sourceChat": telegram_source_chats.c.title,
        "sourceChatId": telegram_source_messages.c.source_chat_id,
        "sourceInputRef": telegram_source_chats.c.input_ref,
        "sourceChatStatus": telegram_source_chats.c.status,
        "telegramMessageId": telegram_source_messages.c.telegram_message_id,
        "telegramChatId": telegram_source_chats.c.telegram_chat_id,
        "sender": sa.func.coalesce(
            telegram_source_messages.c.sender_username,
            sa.cast(telegram_source_messages.c.sender_id, sa.Text),
        ),
        "messageId": telegram_source_messages.c.id,
        "score": _live_score_expr(),
        "temperature": assessment["temperature"].astext,
        "reviewLane": assessment["review_lane"]["key"].astext,
        "autoLead": _live_auto_is_lead_expr(),
        "effectiveLead": _live_effective_is_lead_expr(),
        "leadStatusSource": sa.case(
            (message_reviews.c.source_message_id.is_not(None), "review"),
            else_="auto",
        ),
        "reviewStatus": message_reviews.c.source_message_id.is_not(None),
        "llmStatus": latest_llm.c.llm_status,
        "llmVerdict": latest_llm.c.llm_response["verdict"].astext,
        "llmConfidence": sa.cast(latest_llm.c.llm_response["confidence"].astext, sa.Float),
        "llmRecommendation": latest_llm.c.llm_response["recommendation"].astext,
        "llmAgreement": sa.cast(latest_llm.c.llm_response["agrees_with_rule_engine"].astext, sa.Boolean),
        "llmModel": latest_llm.c.llm_model,
        "llmRoute": latest_llm.c.llm_route_id,
        "llmAttempts": latest_llm.c.llm_attempts,
        "llmUpdatedAt": latest_llm.c.llm_updated_at,
        "text": telegram_source_messages.c.text,
        "enrichmentStatus": enrichment_jobs.c.status,
        "enrichmentFinishedAt": enrichment_jobs.c.finished_at,
        "sourceAccountId": telegram_source_messages.c.account_id,
    }
    return expressions.get(sort_by or "")


def _imported_candidate_sort_expression(sort_by: str | None) -> Any | None:
    expressions: dict[str, Any] = {
        "receivedAt": analytics_candidates.c.received_at,
        "messageDate": analytics_candidates.c.received_at,
        "sourceChat": analytics_candidates.c.source_chat_title,
        "sourceChatId": analytics_candidates.c.source_chat_id,
        "messageId": analytics_candidates.c.message_id,
        "telegramMessageId": analytics_candidates.c.message_id,
        "score": analytics_candidates.c.score,
        "temperature": analytics_candidates.c.temperature,
        "reviewLane": analytics_candidates.c.review_lane,
        "text": analytics_candidates.c.text,
    }
    return expressions.get(sort_by or "")


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
        source_type="telegram",
        is_lead=bool(assessment.get("is_lead")),
        message_date=row["message_date"],
        received_at=row["received_at"],
        sender_id=str(row["sender_id"] or "") or None,
        sender_username=str(row["sender_username"] or "") or None,
        source_account_id=str(row["source_account_id"] or "") or None,
        source_chat_id=str(row["source_chat_id"]),
        source_chat_title=str(row["source_chat_title"] or ""),
        source_input_ref=str(row["input_ref"] or "") or None,
        source_chat_status=str(row["source_chat_status"] or "") or None,
        source_chat_enabled=bool(row["source_chat_enabled"]) if row["source_chat_enabled"] is not None else None,
        source_chat_last_message_id=(
            int(row["source_chat_last_message_id"]) if row["source_chat_last_message_id"] is not None else None
        ),
        source_chat_last_error=str(row["source_chat_last_error"] or "") or None,
        telegram_chat_id=str(row["telegram_chat_id"] or "") or None,
        telegram_message_id=telegram_message_id,
        telegram_message_url=telegram_message_url,
        app_message_url=app_message_url,
        testing_url=f"{public_base_url}/#/testing?message_id={source_message_id}",
        enrichment_job_id=str(row["enrichment_job_id"]),
        enrichment_status=str(row["enrichment_status"] or "") or None,
        enrichment_created_at=row["enrichment_created_at"],
        enrichment_started_at=row["enrichment_started_at"],
        enrichment_finished_at=row["enrichment_finished_at"],
        enrichment_updated_at=row["enrichment_updated_at"],
        enrichment_error=dict(row["enrichment_error"] or {}) or None,
        raw_payload=dict(row["raw_payload"] or {}),
        llm=_llm_summary_from_live_row(row),
        review=_review_from_live_row(row),
    )


def _llm_summary_from_live_row(row: Any) -> AnalyticsCandidateLlmSummary:
    run_id = row["llm_run_id"]
    if run_id is None:
        return AnalyticsCandidateLlmSummary(processed=False)
    response = dict(row["llm_response"] or {})
    return AnalyticsCandidateLlmSummary(
        processed=True,
        latest_run_id=str(run_id),
        status=str(row["llm_status"] or "") or None,
        verdict=_optional_text(response.get("verdict")),
        confidence=_optional_float(response.get("confidence")),
        recommendation=_optional_text(response.get("recommendation")),
        agrees_with_rule_engine=_optional_bool(response.get("agrees_with_rule_engine")),
        model=str(row["llm_model"] or "") or None,
        route_id=str(row["llm_route_id"] or "") or None,
        attempts=int(row["llm_attempts"]) if row["llm_attempts"] is not None else None,
        has_error=bool(row["llm_error"]),
        error=str(row["llm_error"] or "") or None,
        created_at=row["llm_created_at"],
        updated_at=row["llm_updated_at"],
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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


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
