from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.telegram_ingestion.use_cases import IngestTelegramMessage
from app.application.telegram_ingestion.use_cases import UpdateTelegramIngestionSettings
from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentStatus
from app.domain.telegram_ingestion import TelegramIncomingMessage, TelegramIngestionSettings
from app.domain.telegram_ingestion import TelegramSourceChat, TelegramSourceMessage
from app.domain.telegram_ingestion import TelegramUserbotAccount


class InMemoryTelegramIngestionRepository:
    def __init__(self) -> None:
        self.messages: list[TelegramSourceMessage] = []
        self.events: list[str] = []

    async def get_source_message(
        self,
        *,
        source_chat_id: UUID,
        telegram_message_id: int,
    ) -> TelegramSourceMessage | None:
        return next(
            (
                message
                for message in self.messages
                if message.source_chat_id == source_chat_id
                and message.telegram_message_id == telegram_message_id
            ),
            None,
        )

    async def save_source_message(
        self,
        message: TelegramIncomingMessage,
        *,
        text: str,
        enrichment_job_id: UUID,
    ) -> TelegramSourceMessage:
        saved = TelegramSourceMessage(
            id=uuid4(),
            account_id=message.account_id,
            source_chat_id=message.source_chat_id,
            telegram_message_id=message.telegram_message_id,
            message_date=message.message_date,
            sender_id=message.sender_id,
            sender_username=message.sender_username,
            text=text,
            raw_payload=message.raw_payload,
            enrichment_job_id=enrichment_job_id,
            created_at=datetime(2026, 5, 8, tzinfo=UTC),
        )
        self.events.append(f"save_source_message:{message.telegram_message_id}")
        self.messages.append(saved)
        return saved


class ConflictingTelegramIngestionRepository(InMemoryTelegramIngestionRepository):
    def __init__(self, existing: TelegramSourceMessage) -> None:
        super().__init__()
        self.messages = [existing]

    async def get_source_message(
        self,
        *,
        source_chat_id: UUID,
        telegram_message_id: int,
    ) -> TelegramSourceMessage | None:
        if self.messages:
            return None
        return await super().get_source_message(
            source_chat_id=source_chat_id,
            telegram_message_id=telegram_message_id,
        )

    async def save_source_message(
        self,
        message: TelegramIncomingMessage,
        *,
        text: str,
        enrichment_job_id: UUID,
    ) -> TelegramSourceMessage:
        self.events.append(f"save_conflict:{message.telegram_message_id}")
        return self.messages[0]


class InMemoryTelegramSettingsRepository:
    def __init__(self, settings: TelegramIngestionSettings) -> None:
        self.settings = settings

    async def get_settings(self) -> TelegramIngestionSettings:
        return self.settings

    async def save_settings(self, settings: TelegramIngestionSettings) -> TelegramIngestionSettings:
        self.settings = settings
        return settings


class FakeEnrichmentJobCreator:
    def __init__(self) -> None:
        self.created_texts: list[str] = []
        self.created_ids: list[UUID] = []
        self.published_ids: list[UUID] = []
        self.discarded_ids: list[UUID] = []
        self.events: list[str] = []

    async def create(self, input_text: str) -> EnrichmentJobSnapshot:
        job_id = uuid4()
        self.created_texts.append(input_text)
        self.created_ids.append(job_id)
        self.events.append(f"create_job:{input_text}")
        return EnrichmentJobSnapshot(
            id=job_id,
            input_text=input_text,
            status=EnrichmentStatus.QUEUED,
            progress_percent=0,
            current_stage=None,
            stage_index=0,
            stage_count=0,
            stage_progress_percent=0,
            message="Задача поставлена в очередь",
            result=None,
            error=None,
            created_at=datetime(2026, 5, 8, tzinfo=UTC),
            started_at=None,
            finished_at=None,
        )

    async def publish(self, job_id: UUID) -> None:
        self.published_ids.append(job_id)
        self.events.append(f"publish_job:{job_id}")

    async def discard_unpublished(self, job_id: UUID) -> None:
        self.discarded_ids.append(job_id)
        self.events.append(f"discard_job:{job_id}")

    async def execute(self, input_text: str) -> EnrichmentJobSnapshot:
        job = await self.create(input_text)
        await self.publish(job.id)
        return job

@pytest.mark.asyncio
async def test_ingests_telegram_text_message_as_enrichment_job() -> None:
    repository = InMemoryTelegramIngestionRepository()
    job_creator = FakeEnrichmentJobCreator()
    source_chat_id = uuid4()
    use_case = IngestTelegramMessage(repository=repository, job_creator=job_creator)

    result = await use_case.execute(
        TelegramIncomingMessage(
            account_id=uuid4(),
            source_chat_id=source_chat_id,
            telegram_message_id=101,
            message_date=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
            sender_id="42",
            sender_username="designer",
            text="  Нужен умный дом  ",
            raw_payload={"chat_id": "-1001"},
        )
    )

    assert result.status == "created"
    assert job_creator.created_texts == ["Нужен умный дом"]
    assert result.message is not None
    assert result.message.text == "Нужен умный дом"
    assert result.message.enrichment_job_id == result.enrichment_job_id
    assert repository.messages == [result.message]
    assert job_creator.published_ids == [result.enrichment_job_id]


@pytest.mark.asyncio
async def test_ingestion_deduplicates_by_source_chat_and_telegram_message_id() -> None:
    repository = InMemoryTelegramIngestionRepository()
    job_creator = FakeEnrichmentJobCreator()
    source_chat_id = uuid4()
    incoming = TelegramIncomingMessage(
        account_id=uuid4(),
        source_chat_id=source_chat_id,
        telegram_message_id=102,
        message_date=datetime(2026, 5, 8, 10, 1, tzinfo=UTC),
        sender_id=None,
        sender_username=None,
        text="Посоветуйте подрядчика по видеонаблюдению",
        raw_payload={},
    )
    use_case = IngestTelegramMessage(repository=repository, job_creator=job_creator)

    first = await use_case.execute(incoming)
    second = await use_case.execute(incoming)

    assert first.status == "created"
    assert second.status == "duplicate"
    assert second.message == first.message
    assert job_creator.created_texts == ["Посоветуйте подрядчика по видеонаблюдению"]
    assert len(repository.messages) == 1


@pytest.mark.asyncio
async def test_ingestion_discards_unpublished_job_when_source_insert_loses_race() -> None:
    source_chat_id = uuid4()
    existing_job_id = uuid4()
    existing = TelegramSourceMessage(
        id=uuid4(),
        account_id=uuid4(),
        source_chat_id=source_chat_id,
        telegram_message_id=105,
        message_date=datetime(2026, 5, 8, 10, 5, tzinfo=UTC),
        sender_id=None,
        sender_username=None,
        text="Посоветуйте подрядчика по видеонаблюдению",
        raw_payload={},
        enrichment_job_id=existing_job_id,
        created_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    repository = ConflictingTelegramIngestionRepository(existing)
    job_creator = FakeEnrichmentJobCreator()
    use_case = IngestTelegramMessage(repository=repository, job_creator=job_creator)

    result = await use_case.execute(
        TelegramIncomingMessage(
            account_id=uuid4(),
            source_chat_id=source_chat_id,
            telegram_message_id=105,
            message_date=datetime(2026, 5, 8, 10, 5, tzinfo=UTC),
            sender_id=None,
            sender_username=None,
            text="Посоветуйте подрядчика по видеонаблюдению",
            raw_payload={},
        )
    )

    assert result.status == "duplicate"
    assert result.message == existing
    assert result.enrichment_job_id == existing_job_id
    assert job_creator.published_ids == []
    assert job_creator.discarded_ids == job_creator.created_ids


@pytest.mark.asyncio
async def test_ingestion_saves_source_message_before_publishing_enrichment_job() -> None:
    repository = InMemoryTelegramIngestionRepository()
    job_creator = FakeEnrichmentJobCreator()
    shared_events: list[str] = []
    repository.events = shared_events
    job_creator.events = shared_events
    use_case = IngestTelegramMessage(repository=repository, job_creator=job_creator)

    result = await use_case.execute(
        TelegramIncomingMessage(
            account_id=uuid4(),
            source_chat_id=uuid4(),
            telegram_message_id=104,
            message_date=datetime(2026, 5, 8, 10, 4, tzinfo=UTC),
            sender_id=None,
            sender_username=None,
            text="Нужна система видеонаблюдения",
            raw_payload={},
        )
    )

    assert result.status == "created"
    assert shared_events[0] == "create_job:Нужна система видеонаблюдения"
    assert shared_events[1] == "save_source_message:104"
    assert shared_events[2].startswith("publish_job:")
    assert repository.messages[0].enrichment_job_id == result.enrichment_job_id


@pytest.mark.asyncio
async def test_ingestion_skips_empty_telegram_text_without_creating_job() -> None:
    repository = InMemoryTelegramIngestionRepository()
    job_creator = FakeEnrichmentJobCreator()
    use_case = IngestTelegramMessage(repository=repository, job_creator=job_creator)

    result = await use_case.execute(
        TelegramIncomingMessage(
            account_id=uuid4(),
            source_chat_id=uuid4(),
            telegram_message_id=103,
            message_date=None,
            sender_id=None,
            sender_username=None,
            text=" \n ",
            raw_payload={},
        )
    )

    assert result.status == "skipped_empty_text"
    assert result.message is None
    assert result.enrichment_job_id is None
    assert job_creator.created_texts == []
    assert repository.messages == []


@pytest.mark.asyncio
async def test_update_telegram_ingestion_settings_preserves_runtime_cursor_and_errors() -> None:
    account_id = uuid4()
    chat_id = uuid4()
    existing_account = TelegramUserbotAccount(
        id=account_id,
        name="Main",
        phone="+79990000000",
        api_id=12345,
        api_hash="hash",
        session_string="session",
        phone_code_hash=None,
        enabled=True,
        status="authorized",
        last_error="Telegram FloodWait: 120s",
        telegram_user_id="42",
        telegram_username="operator",
        created_at=datetime(2026, 5, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    existing_chat = TelegramSourceChat(
        id=chat_id,
        account_id=account_id,
        title="Designers",
        input_ref="@designers",
        telegram_chat_id="-10042",
        enabled=True,
        status="resolved",
        last_message_id=777,
        last_error="last recover warning",
        created_at=datetime(2026, 5, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    repository = InMemoryTelegramSettingsRepository(
        TelegramIngestionSettings(accounts=[existing_account], chats=[existing_chat])
    )

    saved = await UpdateTelegramIngestionSettings(repository).execute(
        TelegramIngestionSettings(
            accounts=[
                TelegramUserbotAccount(
                    id=account_id,
                    name="Renamed",
                    phone="+79990000000",
                    api_id=12345,
                    api_hash=None,
                    session_string=None,
                    phone_code_hash=None,
                    enabled=True,
                    status="draft",
                    last_error=None,
                    telegram_user_id=None,
                    telegram_username=None,
                    created_at=None,
                    updated_at=None,
                )
            ],
            chats=[
                TelegramSourceChat(
                    id=chat_id,
                    account_id=account_id,
                    title="Designers renamed",
                    input_ref="@designers",
                    telegram_chat_id=None,
                    enabled=True,
                    status="draft",
                    last_message_id=None,
                    last_error=None,
                    created_at=None,
                    updated_at=None,
                )
            ],
        )
    )

    assert saved.accounts[0].name == "Renamed"
    assert saved.accounts[0].status == "authorized"
    assert saved.accounts[0].last_error == "Telegram FloodWait: 120s"
    assert saved.accounts[0].telegram_user_id == "42"
    assert saved.chats[0].title == "Designers renamed"
    assert saved.chats[0].telegram_chat_id == "-10042"
    assert saved.chats[0].status == "resolved"
    assert saved.chats[0].last_message_id == 777
    assert saved.chats[0].last_error == "last recover warning"
