from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.telegram_ingestion import TelegramIngestionSettings, TelegramIncomingMessage
from app.domain.telegram_ingestion import TelegramSourceChat, TelegramSourceMessage
from app.domain.telegram_ingestion import TelegramUserbotAccount
from app.infrastructure.persistence.tables import enrichment_task_outbox
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages
from app.infrastructure.persistence.tables import telegram_userbot_accounts


class PostgresTelegramIngestionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_settings(self) -> TelegramIngestionSettings:
        async with self._session_factory() as session:
            account_rows = (
                await session.execute(sa.select(telegram_userbot_accounts).order_by(
                    telegram_userbot_accounts.c.name.asc(),
                    telegram_userbot_accounts.c.id.asc(),
                ))
            ).mappings().all()
            chat_rows = (
                await session.execute(sa.select(telegram_source_chats).order_by(
                    telegram_source_chats.c.title.asc(),
                    telegram_source_chats.c.id.asc(),
                ))
            ).mappings().all()
        return TelegramIngestionSettings(
            accounts=[_account_from_row(row) for row in account_rows],
            chats=[_chat_from_row(row) for row in chat_rows],
        )

    async def save_settings(
        self,
        settings: TelegramIngestionSettings,
    ) -> TelegramIngestionSettings:
        now = datetime.now(UTC)
        account_ids = [account.id for account in settings.accounts]
        chat_ids = [chat.id for chat in settings.chats]
        async with self._session_factory() as session:
            await _delete_missing(session, telegram_source_chats, chat_ids)
            await _delete_missing(session, telegram_userbot_accounts, account_ids)
            for account in settings.accounts:
                await session.execute(_upsert_account(account, now))
            for chat in settings.chats:
                await session.execute(_upsert_chat(chat, now))
            await session.commit()
        return await self.get_settings()

    async def get_source_message(
        self,
        *,
        source_chat_id: UUID,
        telegram_message_id: int,
    ) -> TelegramSourceMessage | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(telegram_source_messages)
                .where(telegram_source_messages.c.source_chat_id == source_chat_id)
                .where(telegram_source_messages.c.telegram_message_id == telegram_message_id)
            )
            row = result.mappings().first()
        return _source_message_from_row(row) if row is not None else None

    async def get_source_message_context_by_job(self, enrichment_job_id: UUID) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(
                    telegram_source_messages.c.id.label("source_message_id"),
                    telegram_source_messages.c.telegram_message_id,
                    telegram_source_chats.c.input_ref,
                    telegram_source_chats.c.telegram_chat_id,
                )
                .select_from(
                    telegram_source_messages.join(
                        telegram_source_chats,
                        telegram_source_messages.c.source_chat_id == telegram_source_chats.c.id,
                    )
                )
                .where(telegram_source_messages.c.enrichment_job_id == enrichment_job_id)
            )
            row = result.mappings().first()
        return dict(row) if row is not None else None

    async def save_source_message(
        self,
        message: TelegramIncomingMessage,
        *,
        text: str,
        enrichment_job_id: UUID,
    ) -> TelegramSourceMessage:
        now = datetime.now(UTC)
        message_id = uuid4()
        values = {
            "id": message_id,
            "account_id": message.account_id,
            "source_chat_id": message.source_chat_id,
            "telegram_message_id": message.telegram_message_id,
            "message_date": message.message_date,
            "sender_id": message.sender_id,
            "sender_username": message.sender_username,
            "text": text,
            "raw_payload": message.raw_payload,
            "enrichment_job_id": enrichment_job_id,
            "created_at": now,
        }
        statement = (
            insert(telegram_source_messages)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    telegram_source_messages.c.source_chat_id,
                    telegram_source_messages.c.telegram_message_id,
                ]
            )
            .returning(telegram_source_messages)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().first()
            if row is not None:
                await session.execute(
                    enrichment_task_outbox.update()
                    .where(enrichment_task_outbox.c.job_id == enrichment_job_id)
                    .where(enrichment_task_outbox.c.status != "published")
                    .values(status="pending", claimed_at=None, updated_at=now)
                )
                await session.execute(
                    telegram_source_chats.update()
                    .where(telegram_source_chats.c.id == message.source_chat_id)
                    .values(
                        last_message_id=_monotonic_last_message_id(message.telegram_message_id),
                        updated_at=now,
                    )
                )
                await session.commit()
                return _source_message_from_row(row)
            await session.commit()

        existing = await self.get_source_message(
            source_chat_id=message.source_chat_id,
            telegram_message_id=message.telegram_message_id,
        )
        if existing is None:
            raise RuntimeError("telegram source message insert conflict was not readable")
        return existing

    async def update_source_chat_state(
        self,
        *,
        chat_id: UUID,
        status: str,
        telegram_chat_id: str | None = None,
        last_message_id: int | None = None,
        last_error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "last_error": last_error,
            "updated_at": datetime.now(UTC),
        }
        if telegram_chat_id is not None:
            values["telegram_chat_id"] = telegram_chat_id
        if last_message_id is not None:
            values["last_message_id"] = _monotonic_last_message_id(last_message_id)
        async with self._session_factory() as session:
            await session.execute(
                telegram_source_chats.update()
                .where(telegram_source_chats.c.id == chat_id)
                .values(**values)
            )
            await session.commit()

    async def update_userbot_account_cooldown(
        self,
        *,
        account_id: UUID,
        cooldown_until: datetime | None,
        last_error: str | None,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                telegram_userbot_accounts.update()
                .where(telegram_userbot_accounts.c.id == account_id)
                .values(
                    cooldown_until=cooldown_until,
                    last_error=last_error,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()


async def _delete_missing(
    session: AsyncSession,
    table: sa.Table,
    ids: list[UUID],
) -> None:
    if ids:
        await session.execute(table.delete().where(table.c.id.not_in(ids)))
    else:
        await session.execute(table.delete())


def _upsert_account(account: TelegramUserbotAccount, now: datetime) -> Any:
    values = _account_to_row(account, now)
    return (
        insert(telegram_userbot_accounts)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[telegram_userbot_accounts.c.id],
            set_={
                "name": values["name"],
                "phone": values["phone"],
                "api_id": values["api_id"],
                "api_hash": values["api_hash"],
                "session_string": values["session_string"],
                "phone_code_hash": values["phone_code_hash"],
                "enabled": values["enabled"],
                "status": values["status"],
                "last_error": values["last_error"],
                "telegram_user_id": values["telegram_user_id"],
                "telegram_username": values["telegram_username"],
                "cooldown_until": values["cooldown_until"],
                "updated_at": now,
            },
        )
    )


def _upsert_chat(chat: TelegramSourceChat, now: datetime) -> Any:
    values = _chat_to_row(chat, now)
    return (
        insert(telegram_source_chats)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[telegram_source_chats.c.id],
            set_={
                "account_id": values["account_id"],
                "title": values["title"],
                "input_ref": values["input_ref"],
                "telegram_chat_id": values["telegram_chat_id"],
                "enabled": values["enabled"],
                "status": values["status"],
                "last_message_id": values["last_message_id"],
                "last_error": values["last_error"],
                "updated_at": now,
            },
        )
    )


def _monotonic_last_message_id(incoming_message_id: int) -> Any:
    return sa.func.greatest(
        sa.func.coalesce(telegram_source_chats.c.last_message_id, incoming_message_id),
        incoming_message_id,
    )


def _account_to_row(account: TelegramUserbotAccount, now: datetime) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "phone": account.phone,
        "api_id": account.api_id,
        "api_hash": account.api_hash,
        "session_string": account.session_string,
        "phone_code_hash": account.phone_code_hash,
        "enabled": account.enabled,
        "status": account.status,
        "last_error": account.last_error,
        "telegram_user_id": account.telegram_user_id,
        "telegram_username": account.telegram_username,
        "cooldown_until": account.cooldown_until,
        "created_at": account.created_at or now,
        "updated_at": now,
    }


def _chat_to_row(chat: TelegramSourceChat, now: datetime) -> dict[str, Any]:
    return {
        "id": chat.id,
        "account_id": chat.account_id,
        "title": chat.title,
        "input_ref": chat.input_ref,
        "telegram_chat_id": chat.telegram_chat_id,
        "enabled": chat.enabled,
        "status": chat.status,
        "last_message_id": chat.last_message_id,
        "last_error": chat.last_error,
        "created_at": chat.created_at or now,
        "updated_at": now,
    }


def _account_from_row(row: Any) -> TelegramUserbotAccount:
    return TelegramUserbotAccount(
        id=row["id"],
        name=row["name"],
        phone=row["phone"],
        api_id=row["api_id"],
        api_hash=row["api_hash"],
        session_string=row["session_string"],
        phone_code_hash=row["phone_code_hash"],
        enabled=row["enabled"],
        status=row["status"],
        last_error=row["last_error"],
        telegram_user_id=row["telegram_user_id"],
        telegram_username=row["telegram_username"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        cooldown_until=row["cooldown_until"],
    )


def _chat_from_row(row: Any) -> TelegramSourceChat:
    return TelegramSourceChat(
        id=row["id"],
        account_id=row["account_id"],
        title=row["title"],
        input_ref=row["input_ref"],
        telegram_chat_id=row["telegram_chat_id"],
        enabled=row["enabled"],
        status=row["status"],
        last_message_id=row["last_message_id"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_message_from_row(row: Any) -> TelegramSourceMessage:
    return TelegramSourceMessage(
        id=row["id"],
        account_id=row["account_id"],
        source_chat_id=row["source_chat_id"],
        telegram_message_id=row["telegram_message_id"],
        message_date=row["message_date"],
        sender_id=row["sender_id"],
        sender_username=row["sender_username"],
        text=row["text"],
        raw_payload=row["raw_payload"],
        enrichment_job_id=row["enrichment_job_id"],
        created_at=row["created_at"],
    )
