from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.lead_handling import LeadBotSession, LeadClaimResult, LeadHandling
from app.domain.lead_handling import LeadHandlingActionResult, LeadHandlingActor
from app.domain.lead_handling import LeadHandlingEvent, LeadHandlingEventType
from app.domain.lead_handling import LeadHandlingStatus, LeadHandlingSummary
from app.infrastructure.persistence.tables import lead_bot_sessions, lead_handling_events
from app.infrastructure.persistence.tables import lead_handlings


class PostgresLeadHandlingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(
        self,
        *,
        source_message_id: UUID,
        sales_chat_id: str,
        sales_chat_message_id: int,
        actor: LeadHandlingActor,
        notification_outbox_id: UUID | None = None,
    ) -> LeadClaimResult:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            await _ensure_handling(
                session,
                source_message_id=source_message_id,
                notification_outbox_id=notification_outbox_id,
                sales_chat_id=sales_chat_id,
                sales_chat_message_id=sales_chat_message_id,
                now=now,
            )
            row = await _locked_handling_row(session, source_message_id)
            already_claimed = bool(
                row["owner_telegram_user_id"] is not None
                and row["owner_telegram_user_id"] != actor.telegram_user_id
            )
            if already_claimed:
                handling = _handling_from_row(row)
                event = await _append_event(
                    session,
                    handling=handling,
                    event_type="callback_failed",
                    actor=actor,
                    payload={
                        "reason": "already_claimed",
                        "owner_telegram_user_id": handling.owner_telegram_user_id,
                    },
                    created_at=now,
                )
            else:
                result = await session.execute(
                    lead_handlings.update()
                    .where(lead_handlings.c.id == row["id"])
                    .values(
                        notification_outbox_id=notification_outbox_id
                        if notification_outbox_id is not None
                        else row["notification_outbox_id"],
                        sales_chat_id=sales_chat_id,
                        sales_chat_message_id=sales_chat_message_id,
                        status="claimed",
                        owner_telegram_user_id=actor.telegram_user_id,
                        owner_telegram_username=actor.telegram_username,
                        owner_display_name=actor.display_name,
                        claimed_at=row["claimed_at"] or now,
                        closed_at=None,
                        updated_at=now,
                    )
                    .returning(lead_handlings)
                )
                handling = _handling_from_row(result.mappings().one())
                event = await _append_event(
                    session,
                    handling=handling,
                    event_type="claimed",
                    actor=actor,
                    payload={
                        "sales_chat_id": sales_chat_id,
                        "sales_chat_message_id": sales_chat_message_id,
                    },
                    created_at=now,
                )
            await session.commit()
        return LeadClaimResult(handling=handling, event=event, already_claimed=already_claimed)

    async def mark_not_lead(
        self,
        *,
        source_message_id: UUID,
        sales_chat_id: str | None,
        sales_chat_message_id: int | None,
        actor: LeadHandlingActor,
        notification_outbox_id: UUID | None = None,
    ) -> LeadHandlingActionResult:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            await _ensure_handling(
                session,
                source_message_id=source_message_id,
                notification_outbox_id=notification_outbox_id,
                sales_chat_id=sales_chat_id,
                sales_chat_message_id=sales_chat_message_id,
                now=now,
            )
            row = await _locked_handling_row(session, source_message_id)
            result = await session.execute(
                lead_handlings.update()
                .where(lead_handlings.c.id == row["id"])
                .values(
                    notification_outbox_id=notification_outbox_id
                    if notification_outbox_id is not None
                    else row["notification_outbox_id"],
                    sales_chat_id=sales_chat_id or row["sales_chat_id"],
                    sales_chat_message_id=sales_chat_message_id or row["sales_chat_message_id"],
                    status="not_lead",
                    closed_at=now,
                    updated_at=now,
                )
                .returning(lead_handlings)
            )
            handling = _handling_from_row(result.mappings().one())
            event = await _append_event(
                session,
                handling=handling,
                event_type="marked_not_lead",
                actor=actor,
                payload={
                    "sales_chat_id": sales_chat_id,
                    "sales_chat_message_id": sales_chat_message_id,
                },
                created_at=now,
            )
            await session.commit()
        return LeadHandlingActionResult(handling=handling, event=event)

    async def change_status(
        self,
        *,
        source_message_id: UUID,
        status: LeadHandlingStatus,
        actor: LeadHandlingActor,
    ) -> LeadHandlingActionResult:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            row = await _locked_handling_row(session, source_message_id)
            closed_at = now if status in {"closed", "not_lead"} else None
            result = await session.execute(
                lead_handlings.update()
                .where(lead_handlings.c.id == row["id"])
                .values(status=status, closed_at=closed_at, updated_at=now)
                .returning(lead_handlings)
            )
            handling = _handling_from_row(result.mappings().one())
            event = await _append_event(
                session,
                handling=handling,
                event_type="status_changed",
                actor=actor,
                payload={"status": status},
                created_at=now,
            )
            await session.commit()
        return LeadHandlingActionResult(handling=handling, event=event)

    async def add_comment(
        self,
        *,
        source_message_id: UUID,
        comment: str,
        actor: LeadHandlingActor,
    ) -> LeadHandlingActionResult:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            row = await _locked_handling_row(session, source_message_id)
            result = await session.execute(
                lead_handlings.update()
                .where(lead_handlings.c.id == row["id"])
                .values(last_comment=comment, updated_at=now)
                .returning(lead_handlings)
            )
            handling = _handling_from_row(result.mappings().one())
            event = await _append_event(
                session,
                handling=handling,
                event_type="comment_added",
                actor=actor,
                payload={"comment": comment},
                created_at=now,
            )
            await session.commit()
        return LeadHandlingActionResult(handling=handling, event=event)

    async def list_for_owner(
        self,
        *,
        telegram_user_id: str,
        limit: int,
    ) -> list[LeadHandlingSummary]:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(lead_handlings)
                .where(lead_handlings.c.owner_telegram_user_id == telegram_user_id)
                .where(lead_handlings.c.status != "not_lead")
                .order_by(lead_handlings.c.updated_at.desc(), lead_handlings.c.id.desc())
                .limit(limit)
            )
            rows = result.mappings().all()
        return [_summary_from_row(row) for row in rows]

    async def get_by_source_message_id(self, source_message_id: UUID) -> LeadHandling | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(lead_handlings).where(lead_handlings.c.source_message_id == source_message_id)
            )
            row = result.mappings().first()
        return _handling_from_row(row) if row is not None else None

    async def set_session_state(
        self,
        *,
        bot_id: str,
        telegram_user_id: str,
        state: str,
        payload: dict[str, object],
    ) -> LeadBotSession:
        now = datetime.now(UTC)
        statement = (
            insert(lead_bot_sessions)
            .values(
                bot_id=bot_id,
                telegram_user_id=telegram_user_id,
                state=state,
                payload=payload,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[lead_bot_sessions.c.bot_id, lead_bot_sessions.c.telegram_user_id],
                set_={
                    "state": state,
                    "payload": payload,
                    "updated_at": now,
                },
            )
            .returning(lead_bot_sessions)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().one()
            await session.commit()
        return _session_from_row(row)

    async def get_session_state(self, *, bot_id: str, telegram_user_id: str) -> LeadBotSession | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(lead_bot_sessions)
                .where(lead_bot_sessions.c.bot_id == bot_id)
                .where(lead_bot_sessions.c.telegram_user_id == telegram_user_id)
            )
            row = result.mappings().first()
        return _session_from_row(row) if row is not None else None

    async def clear_session_state(self, *, bot_id: str, telegram_user_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                lead_bot_sessions.delete()
                .where(lead_bot_sessions.c.bot_id == bot_id)
                .where(lead_bot_sessions.c.telegram_user_id == telegram_user_id)
            )
            await session.commit()


async def _ensure_handling(
    session: AsyncSession,
    *,
    source_message_id: UUID,
    notification_outbox_id: UUID | None,
    sales_chat_id: str | None,
    sales_chat_message_id: int | None,
    now: datetime,
) -> None:
    statement = (
        insert(lead_handlings)
        .values(
            id=uuid4(),
            source_message_id=source_message_id,
            notification_outbox_id=notification_outbox_id,
            sales_chat_id=sales_chat_id,
            sales_chat_message_id=sales_chat_message_id,
            status="new",
            owner_telegram_user_id=None,
            owner_telegram_username=None,
            owner_display_name=None,
            last_comment=None,
            claimed_at=None,
            closed_at=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[lead_handlings.c.source_message_id],
            set_={"updated_at": lead_handlings.c.updated_at},
        )
    )
    await session.execute(statement)


async def _locked_handling_row(session: AsyncSession, source_message_id: UUID) -> Any:
    result = await session.execute(
        sa.select(lead_handlings)
        .where(lead_handlings.c.source_message_id == source_message_id)
        .with_for_update()
    )
    return result.mappings().one()


async def _append_event(
    session: AsyncSession,
    *,
    handling: LeadHandling,
    event_type: LeadHandlingEventType,
    actor: LeadHandlingActor,
    payload: dict[str, object],
    created_at: datetime,
) -> LeadHandlingEvent:
    result = await session.execute(
        lead_handling_events.insert()
        .values(
            id=uuid4(),
            lead_handling_id=handling.id,
            source_message_id=handling.source_message_id,
            actor_telegram_user_id=actor.telegram_user_id,
            actor_telegram_username=actor.telegram_username,
            actor_display_name=actor.display_name,
            event_type=event_type,
            payload=payload,
            created_at=created_at,
        )
        .returning(lead_handling_events)
    )
    return _event_from_row(result.mappings().one())


def _handling_from_row(row: Any) -> LeadHandling:
    return LeadHandling(
        id=row["id"],
        source_message_id=row["source_message_id"],
        notification_outbox_id=row["notification_outbox_id"],
        sales_chat_id=row["sales_chat_id"],
        sales_chat_message_id=row["sales_chat_message_id"],
        status=row["status"],
        owner_telegram_user_id=row["owner_telegram_user_id"],
        owner_telegram_username=row["owner_telegram_username"],
        owner_display_name=row["owner_display_name"],
        last_comment=row["last_comment"],
        claimed_at=row["claimed_at"],
        closed_at=row["closed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _event_from_row(row: Any) -> LeadHandlingEvent:
    return LeadHandlingEvent(
        id=row["id"],
        lead_handling_id=row["lead_handling_id"],
        source_message_id=row["source_message_id"],
        actor_telegram_user_id=row["actor_telegram_user_id"],
        actor_telegram_username=row["actor_telegram_username"],
        actor_display_name=row["actor_display_name"],
        event_type=row["event_type"],
        payload=row["payload"],
        created_at=row["created_at"],
    )


def _summary_from_row(row: Any) -> LeadHandlingSummary:
    return LeadHandlingSummary(
        id=row["id"],
        source_message_id=row["source_message_id"],
        status=row["status"],
        owner_telegram_user_id=row["owner_telegram_user_id"],
        owner_display_name=row["owner_display_name"],
        last_comment=row["last_comment"],
        sales_chat_id=row["sales_chat_id"],
        sales_chat_message_id=row["sales_chat_message_id"],
        updated_at=row["updated_at"],
    )


def _session_from_row(row: Any) -> LeadBotSession:
    return LeadBotSession(
        bot_id=row["bot_id"],
        telegram_user_id=row["telegram_user_id"],
        state=row["state"],
        payload=row["payload"],
        updated_at=row["updated_at"],
    )
