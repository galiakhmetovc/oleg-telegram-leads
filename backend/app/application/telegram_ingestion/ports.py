from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.enrichment import EnrichmentJobSnapshot
from app.domain.telegram_ingestion import TelegramFetchedMessage, TelegramIncomingMessage
from app.domain.telegram_ingestion import TelegramIngestionResult, TelegramIngestionSettings
from app.domain.telegram_ingestion import TelegramSourceMessage, TelegramSourceSubscription
from app.domain.telegram_ingestion import UserbotAuthorization, UserbotCodeSent


class TelegramIngestionSettingsRepository(Protocol):
    async def get_settings(self) -> TelegramIngestionSettings: ...

    async def save_settings(
        self,
        settings: TelegramIngestionSettings,
    ) -> TelegramIngestionSettings: ...


class TelegramSourceStateRepository(TelegramIngestionSettingsRepository, Protocol):
    async def update_source_chat_state(
        self,
        *,
        chat_id: UUID,
        status: str,
        telegram_chat_id: str | None = None,
        last_message_id: int | None = None,
        last_error: str | None = None,
    ) -> None: ...

    async def update_userbot_account_cooldown(
        self,
        *,
        account_id: UUID,
        cooldown_until: datetime | None,
        last_error: str | None,
    ) -> None: ...


class TelegramIngestionRepository(Protocol):
    async def get_source_message(
        self,
        *,
        source_chat_id: UUID,
        telegram_message_id: int,
    ) -> TelegramSourceMessage | None: ...

    async def save_source_message(
        self,
        message: TelegramIncomingMessage,
        *,
        text: str,
        enrichment_job_id: UUID,
    ) -> TelegramSourceMessage: ...


class TelegramMessageIngester(Protocol):
    async def execute(self, message: TelegramIncomingMessage) -> TelegramIngestionResult: ...


class EnrichmentJobCreator(Protocol):
    async def create(self, input_text: str) -> EnrichmentJobSnapshot: ...

    async def publish(self, job_id: UUID) -> None: ...

    async def discard_unpublished(self, job_id: UUID) -> None: ...

    async def execute(self, input_text: str) -> EnrichmentJobSnapshot: ...


class UserbotLoginClient(Protocol):
    async def send_code(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        session_string: str | None,
    ) -> UserbotCodeSent: ...

    async def sign_in(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: str | None,
        session_string: str | None,
    ) -> UserbotAuthorization: ...


class TelegramHistoryClient(Protocol):
    async def __aenter__(self) -> TelegramHistoryClient: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    async def get_latest_message_id(self, input_ref: str) -> tuple[str | None, int | None]: ...

    async def fetch_messages_after(
        self,
        input_ref: str,
        *,
        after_message_id: int,
        limit: int,
    ) -> list[TelegramFetchedMessage]: ...

    async def watch_sources(
        self,
        sources: Sequence[TelegramSourceSubscription],
        handler: Callable[[UUID, TelegramFetchedMessage], Awaitable[None]],
    ) -> None: ...


class TelegramHistoryClientFactory(Protocol):
    def create(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
    ) -> TelegramHistoryClient: ...
