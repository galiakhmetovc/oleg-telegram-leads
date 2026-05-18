from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast

import redis.asyncio as redis
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.notifications.summary import NotificationSummaryMetrics
from app.core.config import get_settings
from app.infrastructure.persistence.tables import enrichment_jobs, enrichment_results
from app.infrastructure.persistence.tables import llm_verifications, notification_outbox
from app.infrastructure.persistence.tables import notification_summary_runs
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages

QueueDepthsProvider = Callable[[], Awaitable[dict[str, int | None]] | dict[str, int | None]]


class PostgresNotificationSummaryRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        queue_depths: QueueDepthsProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._queue_depths = queue_depths or _redis_queue_depths

    async def claim_run(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        now: datetime,
    ) -> bool:
        statement = (
            insert(notification_summary_runs)
            .values(
                period_kind=period_kind,
                period_start=period_start,
                period_end=period_end,
                bot_id=bot_id,
                chat_id=chat_id,
                status="sending",
                attempts=1,
                telegram_message_id=None,
                last_error=None,
                created_at=now,
                updated_at=now,
                sent_at=None,
            )
            .on_conflict_do_update(
                index_elements=[
                    notification_summary_runs.c.period_kind,
                    notification_summary_runs.c.period_start,
                    notification_summary_runs.c.period_end,
                    notification_summary_runs.c.bot_id,
                    notification_summary_runs.c.chat_id,
                ],
                set_={
                    "status": "sending",
                    "attempts": notification_summary_runs.c.attempts + 1,
                    "last_error": None,
                    "updated_at": now,
                },
                where=notification_summary_runs.c.status == "failed",
            )
            .returning(sa.literal(True))
        )
        async with self._session_factory() as session:
            result = await session.scalar(statement)
            await session.commit()
        return bool(result)

    async def collect_metrics(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> NotificationSummaryMetrics:
        async with self._session_factory() as session:
            source_counts = await _counts_by_status(
                session,
                telegram_source_chats.c.status,
                telegram_source_chats,
                telegram_source_chats.c.enabled.is_(True),
            )
            source_chats_enabled = await _count_rows(
                session,
                telegram_source_chats,
                telegram_source_chats.c.enabled.is_(True),
            )
            period_messages = _period_messages(period_start=period_start, period_end=period_end)
            messages_received = await _count_from_select(session, sa.select(period_messages.c.id))
            messages_processed = await _count_from_select(
                session,
                sa.select(period_messages.c.id).select_from(
                    period_messages.join(
                        enrichment_results,
                        period_messages.c.enrichment_job_id == enrichment_results.c.job_id,
                    )
                ),
            )
            messages_failed = await _count_from_select(
                session,
                sa.select(period_messages.c.id).select_from(
                    period_messages.join(
                        enrichment_jobs,
                        period_messages.c.enrichment_job_id == enrichment_jobs.c.id,
                    )
                ).where(enrichment_jobs.c.status == "failed"),
            )
            leads_by_temperature = await _lead_counts_by_temperature(session, period_messages)
            enrichment_jobs_by_status = await _period_status_counts(
                session,
                period_messages,
                enrichment_jobs,
                enrichment_jobs.c.status,
                enrichment_jobs.c.id == period_messages.c.enrichment_job_id,
            )
            llm_runs_by_status = await _period_status_counts(
                session,
                period_messages,
                llm_verifications,
                llm_verifications.c.status,
                llm_verifications.c.source_message_id == period_messages.c.id,
            )
            notification_outbox_by_status = await _period_status_counts(
                session,
                period_messages,
                notification_outbox,
                notification_outbox.c.status,
                notification_outbox.c.source_message_id == period_messages.c.id,
            )
        messages_waiting = max(messages_received - messages_processed - messages_failed, 0)
        return NotificationSummaryMetrics(
            source_chats_enabled=source_chats_enabled,
            source_chats_by_status=source_counts,
            messages_received=messages_received,
            messages_processed=messages_processed,
            messages_waiting=messages_waiting,
            messages_failed=messages_failed,
            leads_by_temperature=leads_by_temperature,
            enrichment_jobs_by_status=enrichment_jobs_by_status,
            llm_runs_by_status=llm_runs_by_status,
            notification_outbox_by_status=notification_outbox_by_status,
            redis_queues=await self._resolve_queue_depths(),
        )

    async def mark_run_sent(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        telegram_message_id: int,
        sent_at: datetime,
    ) -> None:
        await self._update_run(
            period_kind=period_kind,
            period_start=period_start,
            period_end=period_end,
            bot_id=bot_id,
            chat_id=chat_id,
            values={
                "status": "sent",
                "telegram_message_id": telegram_message_id,
                "last_error": None,
                "sent_at": sent_at,
                "updated_at": sent_at,
            },
        )

    async def mark_run_failed(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        error: str,
        failed_at: datetime,
    ) -> None:
        await self._update_run(
            period_kind=period_kind,
            period_start=period_start,
            period_end=period_end,
            bot_id=bot_id,
            chat_id=chat_id,
            values={
                "status": "failed",
                "last_error": error,
                "updated_at": failed_at,
            },
        )

    async def _update_run(
        self,
        *,
        period_kind: str,
        period_start: datetime,
        period_end: datetime,
        bot_id: str,
        chat_id: str,
        values: dict[str, Any],
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                notification_summary_runs.update()
                .where(notification_summary_runs.c.period_kind == period_kind)
                .where(notification_summary_runs.c.period_start == period_start)
                .where(notification_summary_runs.c.period_end == period_end)
                .where(notification_summary_runs.c.bot_id == bot_id)
                .where(notification_summary_runs.c.chat_id == chat_id)
                .values(**values)
            )
            await session.commit()

    async def _resolve_queue_depths(self) -> dict[str, int | None]:
        result = self._queue_depths()
        if inspect.isawaitable(result):
            return await result
        return result


def _period_messages(*, period_start: datetime, period_end: datetime) -> sa.Subquery:
    return (
        sa.select(
            telegram_source_messages.c.id,
            telegram_source_messages.c.enrichment_job_id,
        )
        .where(telegram_source_messages.c.created_at >= period_start)
        .where(telegram_source_messages.c.created_at < period_end)
        .subquery("period_messages")
    )


async def _counts_by_status(
    session: AsyncSession,
    status_column: Any,
    table: sa.Table,
    *conditions: Any,
) -> dict[str, int]:
    result = await session.execute(
        sa.select(status_column, sa.func.count())
        .select_from(table)
        .where(*conditions)
        .group_by(status_column)
    )
    return {str(status): int(count) for status, count in result.all()}


async def _period_status_counts(
    session: AsyncSession,
    period_messages: sa.Subquery,
    table: sa.Table,
    status_column: Any,
    join_condition: Any,
) -> dict[str, int]:
    result = await session.execute(
        sa.select(status_column, sa.func.count())
        .select_from(period_messages.join(table, join_condition))
        .group_by(status_column)
    )
    return {str(status): int(count) for status, count in result.all()}


async def _lead_counts_by_temperature(
    session: AsyncSession,
    period_messages: sa.Subquery,
) -> dict[str, int]:
    temperature = enrichment_results.c.result["lead_assessment"]["temperature"].astext
    is_lead = enrichment_results.c.result["lead_assessment"]["is_lead"].astext
    result = await session.execute(
        sa.select(temperature.label("temperature"), sa.func.count())
        .select_from(
            period_messages.join(
                enrichment_results,
                period_messages.c.enrichment_job_id == enrichment_results.c.job_id,
            )
        )
        .where(is_lead == "true")
        .group_by(temperature)
    )
    return {str(status): int(count) for status, count in result.all()}


async def _count_rows(session: AsyncSession, table: sa.Table, *conditions: Any) -> int:
    result = await session.scalar(sa.select(sa.func.count()).select_from(table).where(*conditions))
    return int(result or 0)


async def _count_from_select(session: AsyncSession, statement: sa.Select[Any]) -> int:
    result = await session.scalar(sa.select(sa.func.count()).select_from(statement.subquery()))
    return int(result or 0)


async def _redis_queue_depths() -> dict[str, int | None]:
    client = redis.from_url(get_settings().redis_url)
    try:
        return {
            "celery": await _redis_queue_depth(client, "celery"),
            "llm": await _redis_queue_depth(client, "llm"),
        }
    finally:
        await client.aclose()


async def _redis_queue_depth(client: redis.Redis, queue_name: str) -> int | None:
    try:
        return int(await cast(Any, client.llen(queue_name)))
    except Exception:
        return None
