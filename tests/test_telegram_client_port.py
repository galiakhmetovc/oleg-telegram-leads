from datetime import datetime
from pathlib import Path

import pytest

from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.integrations.telegram.types import (
    MessageContext,
    TelegramDocumentDownload,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramMessage,
)


class FakeTelegramClient:
    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        return ResolvedTelegramSource(
            input_ref=input_ref,
            source_kind="telegram_channel",
            telegram_id="-1001",
            username="purmaster",
            title="PUR",
        )

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        return SourceAccessResult(
            status="succeeded",
            can_read_messages=True,
            can_read_history=True,
            resolved_source=source,
            last_message_id=42,
        )

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        return [_message(source, 42)][:limit]

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        limit: int,
    ) -> list[TelegramMessage]:
        return [_message(source, 43)][:limit]

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        return MessageContext(
            target_message_id=message_id,
            reply_messages=[],
            neighbor_before=[],
            neighbor_after=[],
        )

    async def download_message_document(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
    ) -> TelegramDocumentDownload:
        return TelegramDocumentDownload(
            status="downloaded",
            file_name="catalog.pdf",
            mime_type="application/pdf",
            file_size=12,
            local_path=str(Path(destination_dir) / "catalog.pdf"),
            skip_reason=None,
            error=None,
        )


@pytest.mark.asyncio
async def test_fake_client_satisfies_telegram_client_port():
    client: TelegramClientPort = FakeTelegramClient()

    source = await client.resolve_source("https://t.me/purmaster")
    access = await client.check_access(source)
    preview = await client.fetch_preview_messages(source, limit=1)
    batch = await client.fetch_message_batch(source, after_message_id=42, limit=1)
    context = await client.fetch_context(source, message_id=43, before=1, after=1, reply_depth=1)
    download = await client.download_message_document(
        source,
        message_id=43,
        destination_dir=Path("/tmp/catalog"),
    )

    assert source.username == "purmaster"
    assert access.status == "succeeded"
    assert preview[0].telegram_message_id == 42
    assert batch[0].telegram_message_id == 43
    assert context.target_message_id == 43
    assert download.status == "downloaded"


def _message(source: ResolvedTelegramSource, message_id: int) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref=source.input_ref,
        telegram_message_id=message_id,
        message_date=datetime(2026, 4, 28, 12, 0, 0),
        sender_id="user-1",
        sender_display="User",
        text="hello",
        caption=None,
        has_media=False,
        media_metadata_json=None,
        reply_to_message_id=None,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
