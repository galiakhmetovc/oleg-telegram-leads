from datetime import UTC, datetime

import pytest

from pur_leads.integrations.telegram.telethon_client import (
    TelegramClientAuthorizationError,
    TelethonTelegramClient,
)
from pur_leads.integrations.telegram.types import ResolvedTelegramSource


@pytest.mark.asyncio
async def test_telethon_client_resolves_source_and_checks_access():
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1001, username="purmaster", title="PUR", broadcast=True),
        messages=[_message(42, text="latest")],
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )

    source = await client.resolve_source("@purmaster")
    access = await client.check_access(source)

    assert fake.connect_count == 1
    assert source == ResolvedTelegramSource(
        input_ref="@purmaster",
        source_kind="telegram_channel",
        telegram_id="-1001",
        username="purmaster",
        title="PUR",
    )
    assert access.status == "succeeded"
    assert access.can_read_messages is True
    assert access.last_message_id == 42


@pytest.mark.asyncio
async def test_telethon_client_fetches_preview_and_batches_after_checkpoint():
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _message(41, text="hello", sender_id=10, sender_name="Sender"),
            _message(42, text="caption", has_media=True, reply_to_message_id=40),
        ],
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        get_history_wait_seconds=2,
        client_factory=lambda *args, **kwargs: fake,
    )
    source = ResolvedTelegramSource(
        input_ref="@chat",
        source_kind="telegram_supergroup",
        telegram_id="-1002",
        username="chat",
        title="Chat",
    )

    preview = await client.fetch_preview_messages(source, limit=2)
    batch = await client.fetch_message_batch(source, after_message_id=40, limit=100)

    assert [message.telegram_message_id for message in preview] == [41, 42]
    assert preview[0].sender_id == "10"
    assert preview[0].sender_display == "Sender"
    assert preview[1].caption == "caption"
    assert preview[1].has_media is True
    assert preview[1].reply_to_message_id == 40
    assert [message.telegram_message_id for message in batch] == [41, 42]
    assert fake.iter_calls[0] == {"entity": fake.entity, "limit": 2}
    assert fake.iter_calls[1] == {
        "entity": fake.entity,
        "limit": 100,
        "min_id": 40,
        "reverse": True,
        "wait_time": 2,
    }


@pytest.mark.asyncio
async def test_telethon_client_requires_authorized_session():
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1001, username="purmaster", title="PUR", broadcast=True),
        messages=[],
        authorized=False,
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )

    with pytest.raises(TelegramClientAuthorizationError):
        await client.resolve_source("@purmaster")


class FakeTelethonClient:
    def __init__(
        self,
        *,
        entity,
        messages,
        authorized: bool = True,
    ) -> None:
        self.entity = entity
        self.messages = messages
        self.authorized = authorized
        self.connect_count = 0
        self.iter_calls = []

    async def connect(self) -> None:
        self.connect_count += 1

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_entity(self, input_ref):
        return self.entity

    async def iter_messages(self, entity, **kwargs):
        self.iter_calls.append({"entity": entity, **kwargs})
        limit = kwargs.get("limit")
        rows = self.messages if limit is None else self.messages[:limit]
        for message in rows:
            yield message


class FakeEntity:
    def __init__(
        self,
        *,
        id: int,
        username: str | None,
        title: str,
        broadcast: bool = False,
        megagroup: bool = False,
    ) -> None:
        self.id = id
        self.username = username
        self.title = title
        self.broadcast = broadcast
        self.megagroup = megagroup


class FakeSender:
    def __init__(self, display_name: str) -> None:
        self.first_name = display_name
        self.last_name = None
        self.username = None
        self.title = None


class FakeMessage:
    def __init__(
        self,
        *,
        id: int,
        text: str,
        sender_id: int | None,
        sender_name: str | None,
        has_media: bool,
        reply_to_message_id: int | None,
    ) -> None:
        self.id = id
        self.date = datetime(2026, 4, 28, 12, 0, id % 60, tzinfo=UTC)
        self.message = text
        self.sender_id = sender_id
        self.sender = FakeSender(sender_name) if sender_name else None
        self.media = object() if has_media else None
        self.reply_to_msg_id = reply_to_message_id
        self.reply_to = None
        self.fwd_from = None
        self.grouped_id = None
        self.post = False
        self.views = None


def _message(
    message_id: int,
    *,
    text: str,
    sender_id: int | None = None,
    sender_name: str | None = None,
    has_media: bool = False,
    reply_to_message_id: int | None = None,
) -> FakeMessage:
    return FakeMessage(
        id=message_id,
        text=text,
        sender_id=sender_id,
        sender_name=sender_name,
        has_media=has_media,
        reply_to_message_id=reply_to_message_id,
    )
