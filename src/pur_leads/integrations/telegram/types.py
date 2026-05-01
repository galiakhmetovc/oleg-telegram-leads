"""Telegram DTOs used by ingestion workers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ResolvedTelegramSource:
    input_ref: str
    source_kind: str
    telegram_id: str | None
    username: str | None
    title: str | None


@dataclass(frozen=True)
class SourceAccessResult:
    status: str
    can_read_messages: bool
    can_read_history: bool
    resolved_source: ResolvedTelegramSource | None = None
    last_message_id: int | None = None
    flood_wait_seconds: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class TelegramMessage:
    monitored_source_ref: str
    telegram_message_id: int
    message_date: datetime
    sender_id: str | None
    sender_display: str | None
    text: str | None
    caption: str | None
    has_media: bool
    media_metadata_json: dict[str, Any] | None
    reply_to_message_id: int | None
    thread_id: str | None
    forward_metadata_json: dict[str, Any] | None
    raw_metadata_json: dict[str, Any]


@dataclass(frozen=True)
class TelegramDocumentDownload:
    status: str
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    local_path: str | None
    skip_reason: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class TelegramMediaDownload:
    status: str
    media_type: str | None
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    local_path: str | None
    skip_reason: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class MessageContext:
    target_message_id: int
    reply_messages: list[TelegramMessage]
    neighbor_before: list[TelegramMessage]
    neighbor_after: list[TelegramMessage]
