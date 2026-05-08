from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.application.telegram_ingestion.ports import TelegramHistoryClient
from app.application.telegram_ingestion.ports import TelegramHistoryClientFactory
from app.application.telegram_ingestion.ports import TelegramMessageIngester
from app.application.telegram_ingestion.ports import TelegramSourceStateRepository
from app.domain.telegram_ingestion import TelegramFetchedMessage, TelegramIncomingMessage
from app.domain.telegram_ingestion import TelegramSourceChat, TelegramSourceSubscription
from app.domain.telegram_ingestion import TelegramUserbotAccount, TelegramUserbotFloodWait

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramPollingSummary:
    accounts: int = 0
    chats: int = 0
    messages_created: int = 0
    duplicates: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class TelegramReadyAccount:
    account: TelegramUserbotAccount
    resumed_after_cooldown: bool = False


class PollTelegramSources:
    def __init__(
        self,
        *,
        repository: TelegramSourceStateRepository,
        ingester: TelegramMessageIngester,
        history_client_factory: TelegramHistoryClientFactory,
        batch_limit: int = 100,
    ) -> None:
        self._repository = repository
        self._ingester = ingester
        self._history_client_factory = history_client_factory
        self._batch_limit = batch_limit

    async def execute(self) -> TelegramPollingSummary:
        settings = await self._repository.get_settings()
        ready_accounts = await _ready_accounts(self._repository, settings.accounts)
        accounts = [ready.account for ready in ready_accounts]
        chats_by_account = {
            account.id: [
                chat for chat in settings.chats if chat.account_id == account.id and chat.enabled
            ]
            for account in accounts
        }
        summary = TelegramPollingSummary(
            accounts=len(accounts),
            chats=sum(len(chats) for chats in chats_by_account.values()),
        )
        for account in accounts:
            async with self._history_client_factory.create(
                api_id=account.api_id,
                api_hash=account.api_hash or "",
                session_string=account.session_string or "",
            ) as client:
                for chat in chats_by_account[account.id]:
                    summary = _merge_summary(
                        summary,
                        await self._poll_chat(account, chat, client),
                    )
        return summary

    async def _poll_chat(
        self,
        account: TelegramUserbotAccount,
        chat: TelegramSourceChat,
        client: TelegramHistoryClient,
    ) -> TelegramPollingSummary:
        try:
            if chat.last_message_id is None:
                telegram_chat_id, latest_message_id = await client.get_latest_message_id(chat.input_ref)
                await self._repository.update_source_chat_state(
                    chat_id=chat.id,
                    status="resolved",
                    telegram_chat_id=telegram_chat_id,
                    last_message_id=latest_message_id,
                )
                return TelegramPollingSummary()
            messages = await client.fetch_messages_after(
                chat.input_ref,
                after_message_id=chat.last_message_id,
                limit=self._batch_limit,
            )
        except TelegramUserbotFloodWait as exc:
            await _store_account_flood_wait(self._repository, account, exc)
            await self._repository.update_source_chat_state(
                chat_id=chat.id,
                status=chat.status if chat.status in {"draft", "resolved"} else "resolved",
                last_error=str(exc),
            )
            raise
        except Exception as exc:
            await self._repository.update_source_chat_state(
                chat_id=chat.id,
                status="error",
                last_error=str(exc) or type(exc).__name__,
            )
            logger.exception("Failed to poll Telegram source chat %s", chat.id)
            return TelegramPollingSummary(skipped=1)

        created = 0
        duplicates = 0
        skipped = 0
        latest_message_id = chat.last_message_id
        telegram_chat_id = chat.telegram_chat_id
        for message in messages:
            telegram_chat_id = message.telegram_chat_id or telegram_chat_id
            result = await self._ingester.execute(
                TelegramIncomingMessage(
                    account_id=account.id,
                    source_chat_id=chat.id,
                    telegram_message_id=message.telegram_message_id,
                    message_date=message.message_date,
                    sender_id=message.sender_id,
                    sender_username=message.sender_username,
                    text=message.text,
                    raw_payload=message.raw_payload,
                )
            )
            latest_message_id = max(latest_message_id or 0, message.telegram_message_id)
            if result.status == "created":
                created += 1
            elif result.status == "duplicate":
                duplicates += 1
            else:
                skipped += 1
        if latest_message_id is not None:
            await self._repository.update_source_chat_state(
                chat_id=chat.id,
                status="resolved",
                telegram_chat_id=telegram_chat_id,
                last_message_id=latest_message_id,
            )
        return TelegramPollingSummary(
            messages_created=created,
            duplicates=duplicates,
            skipped=skipped,
        )


class WatchTelegramSources:
    def __init__(
        self,
        *,
        repository: TelegramSourceStateRepository,
        ingester: TelegramMessageIngester,
        history_client_factory: TelegramHistoryClientFactory,
        recovery_limit: int = 100,
        cooldown_recovery_limit: int = 10,
        cooldown_recovery_delay_seconds: float = 15.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._repository = repository
        self._ingester = ingester
        self._history_client_factory = history_client_factory
        self._recovery_limit = recovery_limit
        self._cooldown_recovery_limit = cooldown_recovery_limit
        self._cooldown_recovery_delay_seconds = cooldown_recovery_delay_seconds
        self._sleep = sleep
        self._latest_message_ids: dict[Any, int] = {}

    async def execute(self) -> TelegramPollingSummary:
        settings = await self._repository.get_settings()
        ready_accounts = await _ready_accounts(self._repository, settings.accounts)
        accounts = [ready.account for ready in ready_accounts]
        chats_by_account = {
            account.id: [
                chat for chat in settings.chats if chat.account_id == account.id and chat.enabled
            ]
            for account in accounts
        }
        base_summary = TelegramPollingSummary(
            accounts=len(accounts),
            chats=sum(len(chats) for chats in chats_by_account.values()),
        )
        if not accounts:
            return base_summary

        account_summaries = await asyncio.gather(
            *[
                self._watch_account(ready, chats_by_account[ready.account.id])
                for ready in ready_accounts
            ]
        )
        summary = base_summary
        for account_summary in account_summaries:
            summary = _merge_summary(summary, account_summary)
        return summary

    async def _watch_account(
        self,
        ready: TelegramReadyAccount,
        chats: list[TelegramSourceChat],
    ) -> TelegramPollingSummary:
        account = ready.account
        summary = TelegramPollingSummary()
        try:
            async with self._history_client_factory.create(
                api_id=account.api_id,
                api_hash=account.api_hash or "",
                session_string=account.session_string or "",
            ) as client:
                subscriptions: list[TelegramSourceSubscription] = []
                for index, chat in enumerate(chats):
                    self._remember_latest_message_id(chat.id, chat.last_message_id)
                    delay_after_attempt = ready.resumed_after_cooldown and index < len(chats) - 1
                    try:
                        subscription, recovered = await self._prepare_source(
                            account,
                            chat,
                            client,
                            recovery_limit=self._recovery_limit_for(ready),
                            drain_recovery=ready.resumed_after_cooldown,
                        )
                    except TelegramUserbotFloodWait as exc:
                        await self._repository.update_source_chat_state(
                            chat_id=chat.id,
                            status=chat.status if chat.status in {"draft", "resolved"} else "resolved",
                            last_error=str(exc),
                        )
                        delay_after_attempt = False
                        raise
                    except Exception as exc:
                        await self._repository.update_source_chat_state(
                            chat_id=chat.id,
                            status="error",
                            last_error=str(exc) or type(exc).__name__,
                        )
                        logger.exception("Failed to prepare Telegram source chat %s", chat.id)
                        summary = _merge_summary(summary, TelegramPollingSummary(skipped=1))
                    else:
                        subscriptions.append(subscription)
                        summary = _merge_summary(summary, recovered)
                    if delay_after_attempt:
                        await self._sleep(self._cooldown_recovery_delay_seconds)
                if subscriptions:
                    await client.watch_sources(
                        subscriptions,
                        lambda source_chat_id, message: self._handle_live_message(
                            account=account,
                            source_chat_id=source_chat_id,
                            message=message,
                        ),
                    )
        except TelegramUserbotFloodWait as exc:
            await _store_account_flood_wait(self._repository, account, exc)
            raise
        return summary

    async def _prepare_source(
        self,
        account: TelegramUserbotAccount,
        chat: TelegramSourceChat,
        client: TelegramHistoryClient,
        recovery_limit: int,
        drain_recovery: bool,
    ) -> tuple[TelegramSourceSubscription, TelegramPollingSummary]:
        if chat.last_message_id is None:
            telegram_chat_id, latest_message_id = await client.get_latest_message_id(chat.input_ref)
            self._remember_latest_message_id(chat.id, latest_message_id)
            await self._repository.update_source_chat_state(
                chat_id=chat.id,
                status="resolved",
                telegram_chat_id=telegram_chat_id,
                last_message_id=latest_message_id,
            )
            return (
                TelegramSourceSubscription(
                    source_chat_id=chat.id,
                    input_ref=chat.input_ref,
                    telegram_chat_id=telegram_chat_id,
                ),
                TelegramPollingSummary(),
            )

        recovered = TelegramPollingSummary()
        telegram_chat_id = chat.telegram_chat_id
        after_message_id = chat.last_message_id
        while after_message_id is not None:
            messages = await client.fetch_messages_after(
                chat.input_ref,
                after_message_id=after_message_id,
                limit=recovery_limit,
            )
            if not messages:
                await self._repository.update_source_chat_state(
                    chat_id=chat.id,
                    status="resolved",
                    telegram_chat_id=telegram_chat_id,
                    last_error=None,
                )
                break
            for message in messages:
                telegram_chat_id = message.telegram_chat_id or telegram_chat_id
                after_message_id = max(after_message_id, message.telegram_message_id)
                recovered = _merge_summary(
                    recovered,
                    await self._ingest_and_advance(
                        account=account,
                        source_chat_id=chat.id,
                        message=message,
                    ),
                )
            if not drain_recovery or len(messages) < recovery_limit:
                break
            await self._sleep(self._cooldown_recovery_delay_seconds)
        return (
            TelegramSourceSubscription(
                source_chat_id=chat.id,
                input_ref=chat.input_ref,
                telegram_chat_id=telegram_chat_id,
            ),
            recovered,
        )

    async def _handle_live_message(
        self,
        *,
        account: TelegramUserbotAccount,
        source_chat_id: Any,
        message: TelegramFetchedMessage,
    ) -> None:
        await self._ingest_and_advance(
            account=account,
            source_chat_id=source_chat_id,
            message=message,
        )

    async def _ingest_and_advance(
        self,
        *,
        account: TelegramUserbotAccount,
        source_chat_id: Any,
        message: TelegramFetchedMessage,
    ) -> TelegramPollingSummary:
        result = await self._ingester.execute(
            TelegramIncomingMessage(
                account_id=account.id,
                source_chat_id=source_chat_id,
                telegram_message_id=message.telegram_message_id,
                message_date=message.message_date,
                sender_id=message.sender_id,
                sender_username=message.sender_username,
                text=message.text,
                raw_payload=message.raw_payload,
            )
        )
        last_message_id = self._advance_latest_message_id(
            source_chat_id,
            message.telegram_message_id,
        )
        await self._repository.update_source_chat_state(
            chat_id=source_chat_id,
            status="resolved",
            telegram_chat_id=message.telegram_chat_id,
            last_message_id=last_message_id,
        )
        status = getattr(result, "status", None)
        if status == "created":
            return TelegramPollingSummary(messages_created=1)
        if status == "duplicate":
            return TelegramPollingSummary(duplicates=1)
        return TelegramPollingSummary(skipped=1)

    def _recovery_limit_for(self, ready: TelegramReadyAccount) -> int:
        if ready.resumed_after_cooldown:
            return max(1, min(self._recovery_limit, self._cooldown_recovery_limit))
        return self._recovery_limit

    def _remember_latest_message_id(self, source_chat_id: Any, message_id: int | None) -> None:
        if message_id is None:
            return
        self._latest_message_ids[source_chat_id] = max(
            self._latest_message_ids.get(source_chat_id, 0),
            message_id,
        )

    def _advance_latest_message_id(self, source_chat_id: Any, incoming_message_id: int) -> int:
        latest_message_id = max(
            self._latest_message_ids.get(source_chat_id, 0),
            incoming_message_id,
        )
        self._latest_message_ids[source_chat_id] = latest_message_id
        return latest_message_id


def _merge_summary(
    left: TelegramPollingSummary,
    right: TelegramPollingSummary,
) -> TelegramPollingSummary:
    return TelegramPollingSummary(
        accounts=left.accounts + right.accounts,
        chats=left.chats + right.chats,
        messages_created=left.messages_created + right.messages_created,
        duplicates=left.duplicates + right.duplicates,
        skipped=left.skipped + right.skipped,
    )


async def _ready_accounts(
    repository: TelegramSourceStateRepository,
    accounts: list[TelegramUserbotAccount],
) -> list[TelegramReadyAccount]:
    ready: list[TelegramReadyAccount] = []
    now = datetime.now(UTC)
    for account in accounts:
        if not (account.enabled and account.status == "authorized" and account.session_string):
            continue
        if _cooldown_active(account.cooldown_until, now):
            continue
        resumed_after_cooldown = account.cooldown_until is not None
        if account.cooldown_until is not None:
            await repository.update_userbot_account_cooldown(
                account_id=account.id,
                cooldown_until=None,
                last_error=None,
            )
        ready.append(TelegramReadyAccount(account=account, resumed_after_cooldown=resumed_after_cooldown))
    return ready


async def _store_account_flood_wait(
    repository: TelegramSourceStateRepository,
    account: TelegramUserbotAccount,
    exc: TelegramUserbotFloodWait,
) -> None:
    await repository.update_userbot_account_cooldown(
        account_id=account.id,
        cooldown_until=_cooldown_deadline(exc),
        last_error=str(exc),
    )


def _cooldown_active(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized > now


def _cooldown_deadline(exc: TelegramUserbotFloodWait) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=max(exc.seconds, 0))
