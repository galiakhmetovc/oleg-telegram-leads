from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.cli.telegram_bot_worker import TelegramBotWorker
from app.infrastructure.telegram.bot_updates import TelegramBotUpdate


def test_parse_claim_callback_update() -> None:
    source_message_id = uuid4()

    update = TelegramBotUpdate.from_payload(
        {
            "update_id": 10,
            "callback_query": {
                "id": "cb1",
                "from": {"id": 100, "username": "manager", "first_name": "Ivan"},
                "message": {
                    "message_id": 99,
                    "chat": {"id": -1001, "type": "supergroup"},
                    "text": "Лид ПУР",
                },
                "data": f"lh:claim:{source_message_id}",
            },
        }
    )

    assert update.callback is not None
    assert update.callback.action == "claim"
    assert update.callback.source_message_id == source_message_id
    assert update.callback.actor.telegram_user_id == "100"
    assert update.callback.chat_id == "-1001"
    assert update.callback.current_text == "Лид ПУР"


@pytest.mark.asyncio
async def test_worker_dispatches_callback_and_advances_offset() -> None:
    source_message_id = uuid4()
    client = FakeBotUpdateClient(
        [
            TelegramBotUpdate.from_payload(
                _callback_payload(
                    update_id=10,
                    chat_id=-1001,
                    chat_type="supergroup",
                    data=f"lh:claim:{source_message_id}",
                )
            )
        ]
    )
    offsets = InMemoryBotOffsetRepository()
    group_handler = RecordingGroupHandler()
    worker = TelegramBotWorker(
        bot_id="main_bot",
        bot_token="token",
        update_client=client,
        offset_repository=offsets,
        group_handler=group_handler,
        private_handler=RecordingPrivateHandler(),
    )

    await worker.run_once()

    assert [callback.action for callback in group_handler.callbacks] == ["claim"]
    assert offsets.offsets["main_bot"] == 11
    assert client.requests == [("token", None, 25)]


@pytest.mark.asyncio
async def test_worker_dispatches_private_callbacks_to_private_handler() -> None:
    source_message_id = uuid4()
    client = FakeBotUpdateClient(
        [
            TelegramBotUpdate.from_payload(
                _callback_payload(update_id=20, chat_id=100, chat_type="private", data="lh:my_leads")
            ),
            TelegramBotUpdate.from_payload(
                _callback_payload(
                    update_id=21,
                    chat_id=100,
                    chat_type="private",
                    data=f"lh:open:{source_message_id}",
                )
            ),
            TelegramBotUpdate.from_payload(
                _callback_payload(
                    update_id=22,
                    chat_id=100,
                    chat_type="private",
                    data=f"lh:status:{source_message_id}:waiting",
                )
            ),
            TelegramBotUpdate.from_payload(
                _callback_payload(
                    update_id=23,
                    chat_id=100,
                    chat_type="private",
                    data=f"lh:comment:{source_message_id}",
                )
            ),
        ]
    )
    private_handler = RecordingPrivateHandler()
    worker = TelegramBotWorker(
        bot_id="main_bot",
        bot_token="token",
        update_client=client,
        offset_repository=InMemoryBotOffsetRepository(),
        group_handler=RecordingGroupHandler(),
        private_handler=private_handler,
    )

    await worker.run_once()

    assert [callback.action for callback in private_handler.callbacks] == [
        "my_leads",
        "open",
        "status",
        "comment",
    ]


@pytest.mark.asyncio
async def test_worker_dispatches_private_text_to_private_handler() -> None:
    client = FakeBotUpdateClient(
        [
            TelegramBotUpdate.from_payload(
                {
                    "update_id": 30,
                    "message": {
                        "message_id": 5,
                        "chat": {"id": 100, "type": "private"},
                        "from": {"id": 100, "username": "manager", "first_name": "Ivan"},
                        "text": "Написал, жду ответа",
                    },
                }
            )
        ]
    )
    private_handler = RecordingPrivateHandler()
    worker = TelegramBotWorker(
        bot_id="main_bot",
        bot_token="token",
        update_client=client,
        offset_repository=InMemoryBotOffsetRepository(),
        group_handler=RecordingGroupHandler(),
        private_handler=private_handler,
    )

    await worker.run_once()

    assert private_handler.messages[-1].text == "Написал, жду ответа"


class FakeBotUpdateClient:
    def __init__(self, updates: list[TelegramBotUpdate]) -> None:
        self.updates = updates
        self.requests: list[tuple[str, int | None, int]] = []

    async def get_updates(
        self,
        *,
        bot_token: str,
        offset: int | None,
        timeout_seconds: int,
    ) -> list[TelegramBotUpdate]:
        self.requests.append((bot_token, offset, timeout_seconds))
        return self.updates


class InMemoryBotOffsetRepository:
    def __init__(self) -> None:
        self.offsets: dict[str, int] = {}

    async def get_offset(self, bot_id: str) -> int | None:
        return self.offsets.get(bot_id)

    async def save_offset(self, bot_id: str, offset: int) -> None:
        self.offsets[bot_id] = offset


class RecordingGroupHandler:
    def __init__(self) -> None:
        self.callbacks: list[AnyGroupCallback] = []

    async def execute(self, callback: AnyGroupCallback) -> None:
        self.callbacks.append(callback)


class RecordingPrivateHandler:
    def __init__(self) -> None:
        self.callbacks: list[AnyPrivateCallback] = []
        self.messages: list[AnyPrivateMessage] = []

    async def execute_callback(self, callback: AnyPrivateCallback) -> None:
        self.callbacks.append(callback)

    async def execute_message(self, message: AnyPrivateMessage) -> None:
        self.messages.append(message)


@dataclass(frozen=True)
class AnyGroupCallback:
    action: str


@dataclass(frozen=True)
class AnyPrivateCallback:
    action: str


@dataclass(frozen=True)
class AnyPrivateMessage:
    text: str


def _callback_payload(
    *,
    update_id: int,
    chat_id: int,
    chat_type: str,
    data: str,
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": 100, "username": "manager", "first_name": "Ivan"},
            "message": {
                "message_id": 99,
                "chat": {"id": chat_id, "type": chat_type},
                "text": "Лид ПУР",
            },
            "data": data,
        },
    }
