from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


TelegramIngestionStatus = Literal["created", "duplicate", "skipped_empty_text"]
TelegramUserbotStatus = Literal["draft", "code_sent", "authorized", "error"]
TelegramSourceChatStatus = Literal["draft", "resolved", "error"]


@dataclass(frozen=True)
class TelegramUserbotAccount:
    id: UUID
    name: str
    phone: str
    api_id: int
    api_hash: str | None
    session_string: str | None
    phone_code_hash: str | None
    enabled: bool
    status: TelegramUserbotStatus
    last_error: str | None
    telegram_user_id: str | None
    telegram_username: str | None
    created_at: datetime | None
    updated_at: datetime | None
    cooldown_until: datetime | None = None

    @property
    def has_api_hash(self) -> bool:
        return bool(self.api_hash)

    @property
    def has_session(self) -> bool:
        return bool(self.session_string)


@dataclass(frozen=True)
class TelegramSourceChat:
    id: UUID
    account_id: UUID
    title: str
    input_ref: str
    telegram_chat_id: str | None
    enabled: bool
    status: TelegramSourceChatStatus
    last_message_id: int | None
    last_error: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class TelegramIngestionSettings:
    accounts: list[TelegramUserbotAccount]
    chats: list[TelegramSourceChat]


@dataclass(frozen=True)
class UserbotCodeSent:
    phone_code_hash: str
    session_string: str | None


@dataclass(frozen=True)
class UserbotAuthorization:
    telegram_user_id: str | None
    telegram_username: str | None
    session_string: str


class TelegramUserbotFloodWait(RuntimeError):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"Telegram FloodWait: {seconds}s")
        self.seconds = seconds


@dataclass(frozen=True)
class TelegramIncomingMessage:
    account_id: UUID
    source_chat_id: UUID
    telegram_message_id: int
    message_date: datetime | None
    sender_id: str | None
    sender_username: str | None
    text: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class TelegramFetchedMessage:
    telegram_chat_id: str | None
    telegram_message_id: int
    message_date: datetime | None
    sender_id: str | None
    sender_username: str | None
    text: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class TelegramSourceSubscription:
    source_chat_id: UUID
    input_ref: str
    telegram_chat_id: str | None


@dataclass(frozen=True)
class TelegramSourceMessage:
    id: UUID
    account_id: UUID
    source_chat_id: UUID
    telegram_message_id: int
    message_date: datetime | None
    sender_id: str | None
    sender_username: str | None
    text: str
    raw_payload: dict[str, Any]
    enrichment_job_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class TelegramIngestionResult:
    status: TelegramIngestionStatus
    message: TelegramSourceMessage | None
    enrichment_job_id: UUID | None
