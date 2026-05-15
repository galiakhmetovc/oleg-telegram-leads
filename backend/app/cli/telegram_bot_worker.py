from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Protocol

from app.application.lead_handling.use_cases import LeadActionCallback
from app.infrastructure.telegram.bot_updates import HttpTelegramBotUpdateClient
from app.infrastructure.telegram.bot_updates import TelegramBotCallback, TelegramBotPrivateMessage
from app.infrastructure.telegram.bot_updates import TelegramBotUpdate

logger = logging.getLogger(__name__)


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
    async def execute_callback(self, callback: TelegramBotCallback) -> object: ...

    async def execute_message(self, message: TelegramBotPrivateMessage) -> object: ...


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
                await self._private_handler.execute_callback(callback)
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
            await self._private_handler.execute_message(update.private_message)
            return True
        return False


class NoopLeadBotOffsetRepository:
    async def get_offset(self, bot_id: str) -> int | None:
        return None

    async def save_offset(self, bot_id: str, offset: int) -> None:
        return None


class NoopGroupLeadActionHandler:
    async def execute(self, callback: LeadActionCallback) -> object:
        logger.info("Ignoring group lead callback because runtime handler is not configured")
        return object()


class NoopPrivateLeadBotHandler:
    async def execute_callback(self, callback: TelegramBotCallback) -> object:
        logger.info("Ignoring private lead callback because runtime handler is not configured")
        return object()

    async def execute_message(self, message: TelegramBotPrivateMessage) -> object:
        logger.info("Ignoring private lead message because runtime handler is not configured")
        return object()


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Poll Telegram Bot API updates for lead actions")
    parser.add_argument("--bot-id", default="main_bot")
    parser.add_argument("--bot-token", default="")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()
    if not args.bot_token:
        logger.info("Lead bot worker has no --bot-token; exiting")
        return
    worker = TelegramBotWorker(
        bot_id=args.bot_id,
        bot_token=args.bot_token,
        update_client=HttpTelegramBotUpdateClient(),
        offset_repository=NoopLeadBotOffsetRepository(),
        group_handler=NoopGroupLeadActionHandler(),
        private_handler=NoopPrivateLeadBotHandler(),
        timeout_seconds=args.timeout,
    )
    while True:
        await worker.run_once()
        await asyncio.sleep(args.interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
