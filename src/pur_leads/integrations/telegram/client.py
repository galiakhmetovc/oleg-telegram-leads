"""Telegram client protocol used by workers."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramDocumentDownload,
    TelegramMediaDownload,
    TelegramMessage,
)


class TelegramClientPort(Protocol):
    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        """Resolve user input into a Telegram source identity."""

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        """Check whether the configured userbot can read the source."""

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        """Fetch a small recent preview without moving checkpoints."""

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        after_date: datetime | None = None,
        limit: int,
    ) -> list[TelegramMessage]:
        """Fetch a bounded batch for polling."""

    def iter_message_batches(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None = None,
        from_message_id: int | None = None,
        after_date: datetime | None = None,
        limit: int | None = None,
        batch_size: int = 1000,
    ) -> AsyncIterator[list[TelegramMessage]]:
        """Fetch history once in ordered chunks for reusable raw exports."""

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        """Fetch reply and neighboring context for one message."""

    async def download_message_document(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
    ) -> TelegramDocumentDownload:
        """Download document media for one message, skipping videos and non-documents."""

    async def download_message_media(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
        allowed_media_types: Sequence[str],
        max_file_size_bytes: int | None,
    ) -> TelegramMediaDownload:
        """Download one message media item according to the raw export media policy."""
