from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.telegram_ingestion.live_service import WatchTelegramSources
from app.application.telegram_ingestion.ports import TelegramHistoryClient
from app.domain.telegram_ingestion import TelegramFetchedMessage, TelegramIncomingMessage
from app.domain.telegram_ingestion import TelegramIngestionResult, TelegramIngestionSettings
from app.domain.telegram_ingestion import TelegramSourceChat
from app.domain.telegram_ingestion import TelegramSourceSubscription, TelegramUserbotAccount
from app.domain.telegram_ingestion import TelegramUserbotFloodWait


class InMemorySourceStateRepository:
    def __init__(self, settings: TelegramIngestionSettings) -> None:
        self.settings = settings
        self.state_updates: list[dict[str, object]] = []
        self.cooldown_updates: list[dict[str, object]] = []

    async def get_settings(self) -> TelegramIngestionSettings:
        return self.settings

    async def save_settings(
        self,
        settings: TelegramIngestionSettings,
    ) -> TelegramIngestionSettings:
        self.settings = settings
        return settings

    async def update_source_chat_state(
        self,
        *,
        chat_id: UUID,
        status: str,
        telegram_chat_id: str | None = None,
        last_message_id: int | None = None,
        last_error: str | None = None,
    ) -> None:
        self.state_updates.append(
            {
                "chat_id": chat_id,
                "status": status,
                "telegram_chat_id": telegram_chat_id,
                "last_message_id": last_message_id,
                "last_error": last_error,
            }
        )

    async def update_userbot_account_cooldown(
        self,
        *,
        account_id: UUID,
        cooldown_until: datetime | None,
        last_error: str | None,
    ) -> None:
        self.cooldown_updates.append(
            {
                "account_id": account_id,
                "cooldown_until": cooldown_until,
                "last_error": last_error,
            }
        )


class FakeIngester:
    def __init__(self) -> None:
        self.messages: list[TelegramIncomingMessage] = []

    async def execute(self, message: TelegramIncomingMessage) -> TelegramIngestionResult:
        self.messages.append(message)
        return TelegramIngestionResult(status="created", message=None, enrichment_job_id=None)


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class FakeLiveClient:
    def __init__(self) -> None:
        self.latest_by_ref: dict[str, tuple[str | None, int | None]] = {}
        self.recovery_by_ref: dict[str, list[TelegramFetchedMessage]] = {}
        self.recovery_batches_by_ref: dict[str, list[list[TelegramFetchedMessage]]] = {}
        self.live_messages: list[tuple[UUID, TelegramFetchedMessage]] = []
        self.flood_wait_by_ref: dict[str, int] = {}
        self.fetch_calls: list[dict[str, object]] = []
        self.watched_sources: list[object] = []
        self.reload_after_seconds: float | None = None

    async def __aenter__(self) -> FakeLiveClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def resolve_source(self, input_ref: str) -> str | None:
        if input_ref in self.flood_wait_by_ref:
            raise TelegramUserbotFloodWait(self.flood_wait_by_ref[input_ref])
        return self.latest_by_ref.get(input_ref, (None, None))[0]

    async def get_latest_message_id(self, input_ref: str) -> tuple[str | None, int | None]:
        if input_ref in self.flood_wait_by_ref:
            raise TelegramUserbotFloodWait(self.flood_wait_by_ref[input_ref])
        return self.latest_by_ref[input_ref]

    async def fetch_messages_after(
        self,
        input_ref: str,
        *,
        after_message_id: int,
        limit: int,
    ) -> list[TelegramFetchedMessage]:
        self.fetch_calls.append(
            {
                "input_ref": input_ref,
                "after_message_id": after_message_id,
                "limit": limit,
            }
        )
        if input_ref in self.recovery_batches_by_ref:
            return self.recovery_batches_by_ref[input_ref].pop(0)
        return self.recovery_by_ref.get(input_ref, [])

    async def watch_sources(
        self,
        sources: Sequence[TelegramSourceSubscription],
        handler: Callable[[UUID, TelegramFetchedMessage], Awaitable[None]],
        *,
        reload_after_seconds: float | None = None,
    ) -> None:
        self.watched_sources = list(sources)
        self.reload_after_seconds = reload_after_seconds
        for source_chat_id, message in self.live_messages:
            await handler(source_chat_id, message)


class FakeLiveClientFactory:
    def __init__(self, client: FakeLiveClient) -> None:
        self.client = client
        self.create_calls = 0

    def create(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
    ) -> TelegramHistoryClient:
        self.create_calls += 1
        return self.client


@pytest.mark.asyncio
async def test_live_watch_bootstraps_unresolved_source_without_importing_history() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, last_message_id=None)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.latest_by_ref[chat.input_ref] = ("telegram-chat-1", 500)

    summary = await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
    ).execute()

    assert summary.accounts == 1
    assert summary.chats == 1
    assert ingester.messages == []
    assert client.fetch_calls == []
    assert repository.state_updates == [
        {
            "chat_id": chat.id,
            "status": "resolved",
            "telegram_chat_id": "telegram-chat-1",
            "last_message_id": None,
            "last_error": None,
        }
    ]
    assert len(client.watched_sources) == 1


@pytest.mark.asyncio
async def test_live_watch_passes_settings_reload_interval_to_live_client() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()

    await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        settings_reload_interval_seconds=45,
    ).execute()

    assert client.reload_after_seconds == 45


@pytest.mark.asyncio
async def test_live_watch_subscribes_resolved_source_without_history_recovery() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.recovery_by_ref[chat.input_ref] = [
        _fetched_message(telegram_chat_id="telegram-chat-1", message_id=501, text="Should not be recovered")
    ]
    client.live_messages = [
        (chat.id, _fetched_message(telegram_chat_id="telegram-chat-1", message_id=502, text="Live lead"))
    ]

    summary = await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
    ).execute()

    assert summary.accounts == 1
    assert summary.chats == 1
    assert client.fetch_calls == []
    assert [message.telegram_message_id for message in ingester.messages] == [502]
    assert len(client.watched_sources) == 1


@pytest.mark.asyncio
async def test_live_watch_does_not_recover_prepared_sources_on_settings_reload() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.recovery_by_ref[chat.input_ref] = [
        _fetched_message(telegram_chat_id="telegram-chat-1", message_id=501, text="Recovery lead")
    ]
    watcher = WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
    )

    first = await watcher.execute()
    second = await watcher.execute()

    assert first.messages_created == 0
    assert second.messages_created == 0
    assert client.fetch_calls == []
    assert ingester.messages == []
    assert len(client.watched_sources) == 1


@pytest.mark.asyncio
async def test_live_watch_skips_account_while_cooldown_is_active() -> None:
    account = _authorized_account(cooldown_until=datetime.now(UTC) + timedelta(hours=1))
    chat = _source_chat(account.id, last_message_id=None)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    factory = FakeLiveClientFactory(client)

    summary = await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=factory,
    ).execute()

    assert summary.accounts == 0
    assert summary.chats == 0
    assert factory.create_calls == 0
    assert ingester.messages == []
    assert repository.state_updates == []
    assert repository.cooldown_updates == []


@pytest.mark.asyncio
async def test_live_watch_clears_source_error_after_empty_recovery_success() -> None:
    account = _authorized_account()
    chat = _source_chat(
        account.id,
        telegram_chat_id="telegram-chat-1",
        last_message_id=500,
        last_error="Telegram FloodWait: 120s",
    )
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()

    await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
    ).execute()

    assert repository.state_updates == [
        {
            "chat_id": chat.id,
            "status": "resolved",
            "telegram_chat_id": "telegram-chat-1",
            "last_message_id": None,
            "last_error": None,
        }
    ]
    assert ingester.messages == []
    assert len(client.watched_sources) == 1


@pytest.mark.asyncio
async def test_live_watch_persists_account_cooldown_on_flood_wait() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, last_message_id=None)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.flood_wait_by_ref[chat.input_ref] = 120

    before = datetime.now(UTC)
    with pytest.raises(TelegramUserbotFloodWait):
        await WatchTelegramSources(
            repository=repository,
            ingester=ingester,
            history_client_factory=FakeLiveClientFactory(client),
        ).execute()

    assert repository.cooldown_updates[0]["account_id"] == account.id
    assert repository.cooldown_updates[0]["last_error"] == "Telegram FloodWait: 120s"
    assert isinstance(repository.cooldown_updates[0]["cooldown_until"], datetime)
    assert repository.cooldown_updates[0]["cooldown_until"] >= before + timedelta(seconds=119)
    assert repository.state_updates == [
        {
            "chat_id": chat.id,
            "status": "draft",
            "telegram_chat_id": None,
            "last_message_id": None,
            "last_error": "Telegram FloodWait: 120s",
        }
    ]
    assert ingester.messages == []


@pytest.mark.asyncio
async def test_live_watch_throttles_recovery_after_expired_cooldown() -> None:
    account = _authorized_account(cooldown_until=datetime.now(UTC) - timedelta(seconds=1))
    first_chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    second_chat = _source_chat(account.id, telegram_chat_id="telegram-chat-2", last_message_id=700)
    repository = InMemorySourceStateRepository(
        TelegramIngestionSettings(accounts=[account], chats=[first_chat, second_chat])
    )
    ingester = FakeIngester()
    client = FakeLiveClient()
    sleep = RecordingSleep()

    summary = await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
        cooldown_recovery_limit=5,
        cooldown_recovery_delay_seconds=1.5,
        sleep=sleep,
    ).execute()

    assert summary.accounts == 1
    assert summary.chats == 2
    assert repository.cooldown_updates == [
        {
            "account_id": account.id,
            "cooldown_until": None,
            "last_error": None,
        }
    ]
    assert client.fetch_calls == []
    assert sleep.calls == []
    assert len(client.watched_sources) == 2


@pytest.mark.asyncio
async def test_live_watch_drains_cooldown_recovery_in_small_batches() -> None:
    account = _authorized_account(cooldown_until=datetime.now(UTC) - timedelta(seconds=1))
    chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.recovery_batches_by_ref[chat.input_ref] = [
        [
            _fetched_message(telegram_chat_id="telegram-chat-1", message_id=501, text="Recovery lead 501"),
            _fetched_message(telegram_chat_id="telegram-chat-1", message_id=502, text="Recovery lead 502"),
        ],
        [
            _fetched_message(telegram_chat_id="telegram-chat-1", message_id=503, text="Recovery lead 503"),
        ],
    ]
    sleep = RecordingSleep()

    await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
        cooldown_recovery_limit=2,
        cooldown_recovery_delay_seconds=1.5,
        sleep=sleep,
    ).execute()

    assert client.fetch_calls == []
    assert ingester.messages == []
    assert sleep.calls == []


@pytest.mark.asyncio
async def test_live_watch_recovers_once_then_processes_live_messages() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.recovery_by_ref[chat.input_ref] = [
        _fetched_message(telegram_chat_id="telegram-chat-1", message_id=501, text="Recovery lead")
    ]
    client.live_messages = [
        (chat.id, _fetched_message(telegram_chat_id="telegram-chat-1", message_id=502, text="Live lead"))
    ]

    summary = await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
    ).execute()

    assert summary.accounts == 1
    assert summary.chats == 1
    assert client.fetch_calls == []
    assert [message.telegram_message_id for message in ingester.messages] == [502]
    assert repository.state_updates[-2:] == [
        {
            "chat_id": chat.id,
            "status": "resolved",
            "telegram_chat_id": "telegram-chat-1",
            "last_message_id": 502,
            "last_error": None,
        },
    ]


@pytest.mark.asyncio
async def test_live_watch_does_not_move_cursor_backwards_for_out_of_order_messages() -> None:
    account = _authorized_account()
    chat = _source_chat(account.id, telegram_chat_id="telegram-chat-1", last_message_id=500)
    repository = InMemorySourceStateRepository(TelegramIngestionSettings(accounts=[account], chats=[chat]))
    ingester = FakeIngester()
    client = FakeLiveClient()
    client.live_messages = [
        (chat.id, _fetched_message(telegram_chat_id="telegram-chat-1", message_id=502, text="Live lead 502")),
        (chat.id, _fetched_message(telegram_chat_id="telegram-chat-1", message_id=501, text="Live lead 501")),
    ]

    await WatchTelegramSources(
        repository=repository,
        ingester=ingester,
        history_client_factory=FakeLiveClientFactory(client),
        recovery_limit=100,
    ).execute()

    assert [message.telegram_message_id for message in ingester.messages] == [502, 501]
    assert repository.state_updates[-2:] == [
        {
            "chat_id": chat.id,
            "status": "resolved",
            "telegram_chat_id": "telegram-chat-1",
            "last_message_id": 502,
            "last_error": None,
        },
        {
            "chat_id": chat.id,
            "status": "resolved",
            "telegram_chat_id": "telegram-chat-1",
            "last_message_id": 502,
            "last_error": None,
        },
    ]


def _authorized_account(cooldown_until: datetime | None = None) -> TelegramUserbotAccount:
    return TelegramUserbotAccount(
        id=uuid4(),
        name="main",
        phone="+79990000000",
        api_id=12345,
        api_hash="hash",
        session_string="session",
        phone_code_hash=None,
        enabled=True,
        status="authorized",
        last_error=None,
        telegram_user_id="42",
        telegram_username="operator",
        created_at=datetime(2026, 5, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, tzinfo=UTC),
        cooldown_until=cooldown_until,
    )


def _source_chat(
    account_id: UUID,
    *,
    telegram_chat_id: str | None = None,
    last_message_id: int | None,
    last_error: str | None = None,
) -> TelegramSourceChat:
    return TelegramSourceChat(
        id=uuid4(),
        account_id=account_id,
        title="Designers",
        input_ref="@designers",
        telegram_chat_id=telegram_chat_id,
        enabled=True,
        status="resolved" if last_message_id is not None else "draft",
        last_message_id=last_message_id,
        last_error=last_error,
        created_at=datetime(2026, 5, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, tzinfo=UTC),
    )


def _fetched_message(*, telegram_chat_id: str, message_id: int, text: str) -> TelegramFetchedMessage:
    return TelegramFetchedMessage(
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=message_id,
        message_date=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        sender_id="100",
        sender_username="designer",
        text=text,
        raw_payload={"message_id": message_id},
    )
