from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.notifications import NotificationOutboxItem
from app.infrastructure.persistence.runtime_retention import trim_notification_outbox
from app.infrastructure.persistence.tables import notification_outbox

CLAIM_TIMEOUT = timedelta(minutes=10)


class PostgresNotificationOutboxRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def enqueue(
        self,
        items: list[NotificationOutboxItem],
    ) -> list[NotificationOutboxItem]:
        if not items:
            return []
        async with self._session_factory() as session:
            statement = (
                insert(notification_outbox)
                .values([_item_to_row(item) for item in items])
                .on_conflict_do_nothing(
                    index_elements=[
                        notification_outbox.c.source_message_id,
                        notification_outbox.c.route_id,
                    ],
                    index_where=notification_outbox.c.source_message_id.is_not(None),
                )
                .returning(notification_outbox)
            )
            result = await session.execute(statement)
            rows = result.mappings().all()
            await session.commit()
        return [_item_from_row(row) for row in rows]

    async def list_pending(self, *, limit: int) -> list[NotificationOutboxItem]:
        now = datetime.now(UTC)
        stale_before = now - CLAIM_TIMEOUT
        async with self._session_factory() as session:
            result = await session.execute(
                sa.text(
                    """
                    with next_items as (
                        select id
                        from notification_outbox
                        where status = 'pending'
                           or (status = 'sending' and claimed_at < :stale_before)
                        order by created_at asc, id asc
                        limit :limit
                        for update skip locked
                    )
                    update notification_outbox
                    set status = 'sending',
                        claimed_at = :claimed_at
                    where id in (select id from next_items)
                    returning id,
                              route_id,
                              bot_id,
                              chat_id,
                              source_message_id,
                              enrichment_job_id,
                              text,
                              status,
                              attempts,
                              last_error,
                              created_at,
                              sent_at
                    """
                ),
                {
                    "limit": limit,
                    "claimed_at": now,
                    "stale_before": stale_before,
                },
            )
            rows = result.mappings().all()
            await session.commit()
        return [_item_from_row(row) for row in rows]

    async def mark_sent(self, ids: list[UUID], *, sent_at: datetime) -> None:
        if not ids:
            return
        async with self._session_factory() as session:
            await session.execute(
                notification_outbox.update()
                .where(notification_outbox.c.id.in_(ids))
                .values(
                    status="sent",
                    attempts=notification_outbox.c.attempts + 1,
                    last_error=None,
                    claimed_at=None,
                    sent_at=sent_at,
                )
            )
            await trim_notification_outbox(
                session,
                max_rows=get_settings().runtime_notification_outbox_retention_rows,
            )
            await session.commit()

    async def mark_failed(self, ids: list[UUID], *, error: str) -> None:
        if not ids:
            return
        async with self._session_factory() as session:
            await session.execute(
                notification_outbox.update()
                .where(notification_outbox.c.id.in_(ids))
                .values(
                    status="failed",
                    attempts=notification_outbox.c.attempts + 1,
                    last_error=error,
                    claimed_at=None,
                )
            )
            await trim_notification_outbox(
                session,
                max_rows=get_settings().runtime_notification_outbox_retention_rows,
            )
            await session.commit()


def _item_to_row(item: NotificationOutboxItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "route_id": item.route_id,
        "bot_id": item.bot_id,
        "chat_id": item.chat_id,
        "source_message_id": item.source_message_id,
        "enrichment_job_id": item.enrichment_job_id,
        "text": item.text,
        "status": item.status,
        "attempts": item.attempts,
        "last_error": item.last_error,
        "claimed_at": None,
        "created_at": item.created_at,
        "sent_at": item.sent_at,
    }


def _item_from_row(row: Any) -> NotificationOutboxItem:
    return NotificationOutboxItem(
        id=row["id"],
        route_id=row["route_id"],
        bot_id=row["bot_id"],
        chat_id=row["chat_id"],
        source_message_id=row["source_message_id"],
        enrichment_job_id=row["enrichment_job_id"],
        text=row["text"],
        status=row["status"],
        attempts=row["attempts"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
    )
