from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Protocol
from typing import cast

from app.application.lead_handling.use_cases import LeadActionCallback
from app.application.lead_handling.use_cases import HandleLeadActionCallback
from app.application.lead_handling.use_cases import HandleLeadBotPrivateMessage
from app.application.lead_handling.use_cases import PrivateBotCallback, PrivateBotMessage
from app.db.session import create_sessionmaker
from app.domain.analytics import AnalyticsReviewVerdict
from app.domain.notifications import NotificationSettings
from app.infrastructure.notifications.telegram_sender import HttpTelegramMessageSender
from app.infrastructure.persistence.analytics_repository import PostgresAnalyticsRepository
from app.infrastructure.persistence.lead_handling_repository import PostgresLeadHandlingRepository
from app.infrastructure.persistence.notification_settings_repository import (
    PostgresNotificationSettingsRepository,
)
from app.infrastructure.telegram.bot_updates import HttpTelegramBotUpdateClient
from app.infrastructure.telegram.bot_updates import TelegramBotUpdate

logger = logging.getLogger(__name__)
OFFSET_SESSION_USER_ID = "__offset__"


class TelegramBotUpdateClient(Protocol):
    async def get_updates(
        self,
        *,
        bot_token: str,
        offset: int | None,
        timeout_seconds: int,
    ) -> list[TelegramBotUpdate]: ...


class LeadBotOffsetRepository(Protocol):
    async def get_offset(self, bot_id: str) -> int | None: ...

    async def save_offset(self, bot_id: str, offset: int) -> None: ...


class GroupLeadActionHandler(Protocol):
    async def execute(self, callback: LeadActionCallback) -> object: ...


class PrivateLeadBotHandler(Protocol):
    async def execute_callback(self, callback: PrivateBotCallback) -> object: ...

    async def execute_message(self, message: PrivateBotMessage) -> object: ...


class TelegramBotWorker:
    def __init__(
        self,
        *,
        bot_id: str,
        bot_token: str,
        update_client: TelegramBotUpdateClient,
        offset_repository: LeadBotOffsetRepository,
        group_handler: GroupLeadActionHandler,
        private_handler: PrivateLeadBotHandler,
        timeout_seconds: int = 25,
    ) -> None:
        self._bot_id = bot_id
        self._bot_token = bot_token
        self._update_client = update_client
        self._offset_repository = offset_repository
        self._group_handler = group_handler
        self._private_handler = private_handler
        self._timeout_seconds = timeout_seconds

    async def run_once(self) -> int:
        offset = await self._offset_repository.get_offset(self._bot_id)
        updates = await self._update_client.get_updates(
            bot_token=self._bot_token,
            offset=offset,
            timeout_seconds=self._timeout_seconds,
        )
        max_update_id: int | None = None
        handled = 0
        for update in updates:
            max_update_id = update.update_id if max_update_id is None else max(max_update_id, update.update_id)
            if await self._dispatch_update(update):
                handled += 1
        if max_update_id is not None:
            await self._offset_repository.save_offset(self._bot_id, max_update_id + 1)
        return handled

    async def _dispatch_update(self, update: TelegramBotUpdate) -> bool:
        callback = update.callback
        if callback is not None:
            if callback.chat_type == "private":
                await self._private_handler.execute_callback(
                    PrivateBotCallback(
                        action=callback.action,
                        source_message_id=callback.source_message_id,
                        status=callback.status,
                        callback_query_id=callback.callback_query_id,
                        chat_id=callback.chat_id,
                        message_id=callback.message_id,
                        actor=callback.actor,
                    )
                )
                return True
            if callback.action in {"claim", "notlead"} and callback.source_message_id is not None:
                await self._group_handler.execute(
                    LeadActionCallback(
                        action=callback.action,  # type: ignore[arg-type]
                        source_message_id=callback.source_message_id,
                        callback_query_id=callback.callback_query_id,
                        chat_id=callback.chat_id,
                        message_id=callback.message_id,
                        actor=callback.actor,
                        current_text=callback.current_text,
                    )
                )
                return True
            return False
        if update.private_message is not None:
            await self._private_handler.execute_message(
                PrivateBotMessage(
                    chat_id=update.private_message.chat_id,
                    actor=update.private_message.actor,
                    text=update.private_message.text,
                )
            )
            return True
        return False


class LeadBotSessionOffsetRepository:
    def __init__(self, handling_repository: PostgresLeadHandlingRepository) -> None:
        self._handling_repository = handling_repository

    async def get_offset(self, bot_id: str) -> int | None:
        session = await self._handling_repository.get_session_state(
            bot_id=bot_id,
            telegram_user_id=OFFSET_SESSION_USER_ID,
        )
        if session is None:
            return None
        value = session.payload.get("offset")
        return int(value) if isinstance(value, int) else None

    async def save_offset(self, bot_id: str, offset: int) -> None:
        await self._handling_repository.set_session_state(
            bot_id=bot_id,
            telegram_user_id=OFFSET_SESSION_USER_ID,
            state="offset",
            payload={"offset": offset},
        )


class AnalyticsMessageReviewWriter:
    def __init__(self, repository: PostgresAnalyticsRepository) -> None:
        self._repository = repository

    async def save_review(
        self,
        *,
        message_id: str,
        verdict: str | None,
        comment: str,
        tags: list[str],
    ) -> object:
        return await self._repository.save_message_review(
            message_id=message_id,
            verdict=cast(AnalyticsReviewVerdict | None, verdict),
            comment=comment,
            tags=tags,
        )

    async def cancel_unsent_notifications_for_message(self, message_id: str, *, reason: str) -> int:
        return await self._repository.cancel_unsent_notifications_for_message(message_id, reason=reason)


async def build_workers(*, timeout_seconds: int) -> list[TelegramBotWorker]:
    session_factory = create_sessionmaker()
    settings_repository = PostgresNotificationSettingsRepository(session_factory)
    settings = await settings_repository.get_settings()
    return _workers_from_settings(
        settings=settings,
        session_factory=session_factory,
        timeout_seconds=timeout_seconds,
    )


def _workers_from_settings(
    *,
    settings: NotificationSettings,
    session_factory: object,
    timeout_seconds: int,
) -> list[TelegramBotWorker]:
    interactive_bot_ids = {
        route.bot_id
        for route in settings.routes
        if route.enabled and route.delivery_mode == "interactive"
    }
    bots = [
        bot
        for bot in settings.bots
        if bot.enabled and bot.token and bot.id in interactive_bot_ids
    ]
    workers: list[TelegramBotWorker] = []
    for bot in bots:
        handling_repository = PostgresLeadHandlingRepository(session_factory)  # type: ignore[arg-type]
        sender = HttpTelegramMessageSender()
        workers.append(
            TelegramBotWorker(
                bot_id=bot.id,
                bot_token=bot.token or "",
                update_client=HttpTelegramBotUpdateClient(),
                offset_repository=LeadBotSessionOffsetRepository(handling_repository),
                group_handler=HandleLeadActionCallback(
                    handling_repository=handling_repository,
                    review_repository=AnalyticsMessageReviewWriter(
                        PostgresAnalyticsRepository(session_factory)  # type: ignore[arg-type]
                    ),
                    sender=sender,
                    bot_token=bot.token or "",
                ),
                private_handler=HandleLeadBotPrivateMessage(
                    handling_repository=handling_repository,
                    sender=sender,
                    bot_token=bot.token or "",
                    bot_id=bot.id,
                ),
                timeout_seconds=timeout_seconds,
            )
        )
    return workers


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Poll Telegram Bot API updates for lead actions")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()
    while True:
        workers = await build_workers(timeout_seconds=args.timeout)
        if not workers:
            logger.info("Lead bot worker found no enabled interactive notification routes")
        for worker in workers:
            try:
                await worker.run_once()
            except Exception:
                logger.exception("Lead bot worker poll failed")
        await asyncio.sleep(args.interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
