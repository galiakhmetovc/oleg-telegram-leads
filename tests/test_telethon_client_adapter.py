from datetime import UTC, datetime
import base64
from pathlib import Path
from typing import Any

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
async def test_telethon_client_preserves_maximum_json_safe_raw_message_metadata():
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _message(
                45,
                text="raw",
                sender_id=10,
                sender_name="Sender",
                has_media=True,
                reply_to_message_id=44,
            )
        ],
    )
    fake.messages[0].binary_payload = b"\x00\x01raw"
    fake.messages[0].edit_date = datetime(2026, 4, 28, 12, 30, tzinfo=UTC)
    fake.messages[0].chat = fake.entity
    fake.messages[0].media = FakeSerializable("MessageMediaPhoto", {"photo_id": 777})
    fake.messages[0].reply_to = FakeSerializable("MessageReplyHeader", {"reply_to_msg_id": 44})
    fake.messages[0].fwd_from = FakeSerializable("MessageFwdHeader", {"from_name": "Forwarded"})
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )
    source = ResolvedTelegramSource(
        input_ref="@chat",
        source_kind="telegram_supergroup",
        telegram_id="-1002",
        username="chat",
        title="Chat",
    )

    preview = await client.fetch_preview_messages(source, limit=1)

    raw = preview[0].raw_metadata_json
    assert raw["post"] is False
    assert raw["views"] is None
    assert raw["telethon"]["message"]["id"] == 45
    assert raw["telethon"]["message"]["message"] == "raw"
    assert raw["telethon"]["message"]["binary_payload"] == {
        "__type": "bytes",
        "encoding": "base64",
        "data": base64.b64encode(b"\x00\x01raw").decode("ascii"),
    }
    assert raw["telethon"]["message"]["edit_date"] == "2026-04-28T12:30:00+00:00"
    assert raw["telethon"]["sender"]["first_name"] == "Sender"
    assert raw["telethon"]["chat"]["title"] == "Chat"
    assert raw["telethon"]["media"]["_"] == "MessageMediaPhoto"
    assert raw["telethon"]["document"] is None
    assert raw["telethon"]["reply_to"]["_"] == "MessageReplyHeader"
    assert raw["telethon"]["fwd_from"]["_"] == "MessageFwdHeader"


@pytest.mark.asyncio
async def test_telethon_client_fetches_batch_after_date_for_recent_backfill():
    after_date = datetime(2025, 10, 28, tzinfo=UTC)
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[_message(41, text="oldest in range"), _message(42, text="next")],
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

    batch = await client.fetch_message_batch(
        source,
        after_message_id=None,
        after_date=after_date,
        limit=100,
    )

    assert [message.telegram_message_id for message in batch] == [41, 42]
    assert fake.iter_calls[0] == {
        "entity": fake.entity,
        "limit": 100,
        "offset_date": after_date,
        "reverse": True,
        "wait_time": 2,
    }


@pytest.mark.asyncio
async def test_telethon_client_iterates_configured_export_range_in_batches():
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _message(41, text="first"),
            _message(42, text="second"),
            _message(43, text="third"),
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

    batches = [
        [message.telegram_message_id for message in batch]
        async for batch in client.iter_message_batches(
            source,
            after_message_id=40,
            limit=3,
            batch_size=2,
        )
    ]

    assert batches == [[41, 42], [43]]
    assert fake.iter_calls[0] == {
        "entity": fake.entity,
        "limit": 3,
        "min_id": 40,
        "reverse": True,
        "wait_time": 2,
    }


@pytest.mark.asyncio
async def test_telethon_client_downloads_media_with_type_and_size_policy(tmp_path):
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _document_message(
                54,
                file_name="catalog.pdf",
                mime_type="application/pdf",
                size=99,
            )
        ],
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )
    source = ResolvedTelegramSource(
        input_ref="@chat",
        source_kind="telegram_supergroup",
        telegram_id="-1002",
        username="chat",
        title="Chat",
    )

    too_large = await client.download_message_media(
        source,
        message_id=54,
        destination_dir=tmp_path / "too-large",
        allowed_media_types=["document"],
        max_file_size_bytes=10,
    )
    downloaded = await client.download_message_media(
        source,
        message_id=54,
        destination_dir=tmp_path / "ok",
        allowed_media_types=["document"],
        max_file_size_bytes=100,
    )

    assert too_large.status == "skipped"
    assert too_large.skip_reason == "file_too_large"
    assert downloaded.status == "downloaded"
    assert downloaded.media_type == "document"
    assert downloaded.local_path == str(tmp_path / "ok" / "catalog.pdf")


@pytest.mark.asyncio
async def test_telethon_client_marks_and_downloads_document_media(tmp_path):
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _document_message(
                51,
                file_name="catalog.pdf",
                mime_type="application/pdf",
                size=7,
            )
        ],
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )
    source = ResolvedTelegramSource(
        input_ref="@chat",
        source_kind="telegram_supergroup",
        telegram_id="-1002",
        username="chat",
        title="Chat",
    )

    preview = await client.fetch_preview_messages(source, limit=1)
    downloaded = await client.download_message_document(
        source,
        message_id=51,
        destination_dir=tmp_path,
    )

    assert preview[0].media_metadata_json == {
        "type": "object",
        "document": {
            "file_name": "catalog.pdf",
            "mime_type": "application/pdf",
            "file_size": 7,
            "downloadable": True,
            "skip_reason": None,
        },
    }
    assert downloaded.status == "downloaded"
    assert downloaded.file_name == "catalog.pdf"
    assert downloaded.mime_type == "application/pdf"
    assert downloaded.file_size == 7
    assert downloaded.local_path == str(tmp_path / "catalog.pdf")
    assert (tmp_path / "catalog.pdf").read_bytes() == b"catalog"


@pytest.mark.asyncio
async def test_telethon_client_skips_video_documents(tmp_path):
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _document_message(
                52,
                file_name="clip.mp4",
                mime_type="video/mp4",
                size=10,
                video=True,
            )
        ],
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )
    source = ResolvedTelegramSource(
        input_ref="@chat",
        source_kind="telegram_supergroup",
        telegram_id="-1002",
        username="chat",
        title="Chat",
    )

    preview = await client.fetch_preview_messages(source, limit=1)
    downloaded = await client.download_message_document(
        source,
        message_id=52,
        destination_dir=tmp_path,
    )

    assert preview[0].media_metadata_json == {
        "type": "object",
        "document": {
            "file_name": "clip.mp4",
            "mime_type": "video/mp4",
            "file_size": 10,
            "downloadable": False,
            "skip_reason": "video",
        },
    }
    assert downloaded.status == "skipped"
    assert downloaded.skip_reason == "video"
    assert downloaded.local_path is None


@pytest.mark.asyncio
async def test_telethon_client_skips_audio_documents(tmp_path):
    fake = FakeTelethonClient(
        entity=FakeEntity(id=-1002, username="chat", title="Chat", megagroup=True),
        messages=[
            _document_message(
                53,
                file_name="voice.m4a",
                mime_type="audio/mp4",
                size=10,
                audio=True,
            )
        ],
    )
    client = TelethonTelegramClient(
        session_path="/secure/userbot.session",
        api_id=123,
        api_hash="hash",
        client_factory=lambda *args, **kwargs: fake,
    )
    source = ResolvedTelegramSource(
        input_ref="@chat",
        source_kind="telegram_supergroup",
        telegram_id="-1002",
        username="chat",
        title="Chat",
    )

    preview = await client.fetch_preview_messages(source, limit=1)
    downloaded = await client.download_message_document(
        source,
        message_id=53,
        destination_dir=tmp_path,
    )

    assert preview[0].media_metadata_json == {
        "type": "object",
        "document": {
            "file_name": "voice.m4a",
            "mime_type": "audio/mp4",
            "file_size": 10,
            "downloadable": False,
            "skip_reason": "audio",
        },
    }
    assert downloaded.status == "skipped"
    assert downloaded.skip_reason == "audio"
    assert downloaded.local_path is None


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


@pytest.mark.asyncio
async def test_telethon_client_closes_connected_session():
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

    await client.resolve_source("@purmaster")
    await client.aclose()

    assert fake.connect_count == 1
    assert fake.disconnect_count == 1


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
        self.disconnect_count = 0
        self.iter_calls: list[dict[str, Any]] = []

    async def connect(self) -> None:
        self.connect_count += 1

    async def disconnect(self) -> None:
        self.disconnect_count += 1

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_entity(self, input_ref):
        return self.entity

    async def download_media(self, message, file):
        destination = Path(file) / message.document.attributes[0].file_name
        destination.write_bytes(b"catalog")
        return str(destination)

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "_": "User",
            "first_name": self.first_name,
            "last_name": self.last_name,
            "username": self.username,
            "title": self.title,
        }


class FakeDocument:
    def __init__(
        self,
        *,
        file_name: str,
        mime_type: str,
        size: int,
        video: bool,
        audio: bool,
    ) -> None:
        attributes: list[Any] = [FakeDocumentAttributeFilename(file_name)]
        if video:
            attributes.append(FakeDocumentAttributeVideo())
        if audio:
            attributes.append(FakeDocumentAttributeAudio())
        self.attributes = attributes
        self.mime_type = mime_type
        self.size = size

    def to_dict(self) -> dict[str, Any]:
        return {
            "_": "Document",
            "attributes": [attribute.to_dict() for attribute in self.attributes],
            "mime_type": self.mime_type,
            "size": self.size,
        }


class FakeDocumentAttributeFilename:
    def __init__(self, file_name: str) -> None:
        self.file_name = file_name

    def to_dict(self) -> dict[str, Any]:
        return {"_": "DocumentAttributeFilename", "file_name": self.file_name}


class FakeDocumentAttributeVideo:
    def to_dict(self) -> dict[str, Any]:
        return {"_": "DocumentAttributeVideo"}


class FakeDocumentAttributeAudio:
    def to_dict(self) -> dict[str, Any]:
        return {"_": "DocumentAttributeAudio"}


class FakeSerializable:
    def __init__(self, type_name: str, values: dict[str, Any]) -> None:
        self.type_name = type_name
        self.values = values

    def to_dict(self) -> dict[str, Any]:
        return {"_": self.type_name, **self.values}


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
        document: FakeDocument | None = None,
    ) -> None:
        self.id = id
        self.date = datetime(2026, 4, 28, 12, 0, id % 60, tzinfo=UTC)
        self.message = text
        self.sender_id = sender_id
        self.sender = FakeSender(sender_name) if sender_name else None
        self.media = object() if has_media else None
        self.document = document
        self.reply_to_msg_id = reply_to_message_id
        self.reply_to = None
        self.fwd_from = None
        self.grouped_id = None
        self.post = False
        self.views = None
        self.edit_date = None
        self.binary_payload = None
        self.chat = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "_": "Message",
            "id": self.id,
            "date": self.date,
            "message": self.message,
            "sender_id": self.sender_id,
            "media": self.media,
            "reply_to": self.reply_to,
            "fwd_from": self.fwd_from,
            "grouped_id": self.grouped_id,
            "post": self.post,
            "views": self.views,
            "edit_date": self.edit_date,
            "binary_payload": self.binary_payload,
        }


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


def _document_message(
    message_id: int,
    *,
    file_name: str,
    mime_type: str,
    size: int,
    video: bool = False,
    audio: bool = False,
) -> FakeMessage:
    return FakeMessage(
        id=message_id,
        text=file_name,
        sender_id=None,
        sender_name=None,
        has_media=True,
        reply_to_message_id=None,
        document=FakeDocument(
            file_name=file_name,
            mime_type=mime_type,
            size=size,
            video=video,
            audio=audio,
        ),
    )
