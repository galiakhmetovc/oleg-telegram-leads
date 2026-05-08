from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.notifications.use_cases import FlushNotificationOutbox
from app.application.notifications.use_cases import QueueNotificationsForEnrichment
from app.application.notifications.routing import NotificationMessageContext
from app.domain.enrichment import EnrichmentMetrics, LeadAssessment, LeadCategory, LeadReason, LeadReviewLane
from app.domain.enrichment import TextEnrichmentResult
from app.domain.notifications import NotificationOutboxItem, NotificationRoute
from app.domain.notifications import NotificationRouteConditions, NotificationSettings
from app.domain.notifications import TelegramBot, TelegramChat, TelegramSendResult


class InMemoryNotificationSettingsRepository:
    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    async def get_settings(self) -> NotificationSettings:
        return self.settings

    async def save_settings(self, settings: NotificationSettings) -> NotificationSettings:
        self.settings = settings
        return settings


class InMemoryNotificationOutboxRepository:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.items: list[NotificationOutboxItem] = []
        self.sent_ids: list[UUID] = []
        self.failed_ids: list[UUID] = []

    async def enqueue(self, items: list[NotificationOutboxItem]) -> list[NotificationOutboxItem]:
        inserted: list[NotificationOutboxItem] = []
        existing_keys = {
            (item.source_message_id, item.route_id)
            for item in self.items
            if item.source_message_id is not None
        }
        for item in items:
            if item.source_message_id is not None:
                key = (item.source_message_id, item.route_id)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
            self.items.append(item)
            inserted.append(item)
        return inserted

    async def list_pending(self, *, limit: int) -> list[NotificationOutboxItem]:
        return [
            item
            for item in sorted(self.items, key=lambda value: value.created_at)
            if item.status == "pending"
        ][:limit]

    async def mark_sent(self, ids: list[UUID], *, sent_at: datetime) -> None:
        self.sent_ids.extend(ids)
        self.items = [
            item.mark_sent(sent_at) if item.id in set(ids) else item
            for item in self.items
        ]

    async def mark_failed(self, ids: list[UUID], *, error: str) -> None:
        self.failed_ids.extend(ids)
        self.items = [
            item.mark_failed(error) if item.id in set(ids) else item
            for item in self.items
        ]


class RecordingTelegramMessageSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def get_bot_username(self, *, bot_token: str) -> str:
        return "pur_bot"

    async def send_text(self, *, bot_token: str, chat_id: str, text: str) -> TelegramSendResult:
        self.sent.append((bot_token, chat_id, text))
        return TelegramSendResult(message_id=len(self.sent), chat_id=chat_id)


@pytest.mark.asyncio
async def test_enrichment_notification_routing_enqueues_outbox_items_without_sending() -> None:
    now = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
    settings = _notification_settings()
    outbox = InMemoryNotificationOutboxRepository(now)

    queued = await QueueNotificationsForEnrichment(
        settings_repository=InMemoryNotificationSettingsRepository(settings),
        outbox_repository=outbox,
        now=lambda: now,
    ).execute(_lead_result())

    assert len(queued) == 1
    assert queued[0].route_id == "hot"
    assert queued[0].bot_id == "main_bot"
    assert queued[0].chat_id == "sales_chat"
    assert queued[0].status == "pending"
    assert "Лид ПУР" in queued[0].text
    assert "Оценка: 95 (hot)" in queued[0].text
    assert "Очередь: Прямой лид ПУР" in queued[0].text
    assert "Зоны решения: Умный дом" in queued[0].text
    assert "Сегменты: Активный запрос" in queued[0].text
    assert "Почему сработало:" in queued[0].text
    assert "+12 Поиск подрядчика: посоветуйте" in queued[0].text
    assert "Текст:" in queued[0].text
    assert outbox.items == queued


@pytest.mark.asyncio
async def test_telegram_notification_queue_is_idempotent_per_source_message_and_route() -> None:
    now = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
    source_message_id = uuid4()
    enrichment_job_id = uuid4()
    outbox = InMemoryNotificationOutboxRepository(now)
    use_case = QueueNotificationsForEnrichment(
        settings_repository=InMemoryNotificationSettingsRepository(_notification_settings()),
        outbox_repository=outbox,
        now=lambda: now,
    )
    context = NotificationMessageContext(
        source_message_id=source_message_id,
        enrichment_job_id=enrichment_job_id,
        telegram_message_url="https://t.me/channel/10",
        app_message_url="https://example.test/#/analytics/message/source",
    )

    first = await use_case.execute(_lead_result(), context)
    second = await use_case.execute(_lead_result(), context)

    assert len(first) == 1
    assert second == []
    assert len(outbox.items) == 1
    assert outbox.items[0].source_message_id == source_message_id
    assert outbox.items[0].enrichment_job_id == enrichment_job_id


@pytest.mark.asyncio
async def test_notification_dispatcher_sends_due_items_as_one_batch() -> None:
    now = datetime(2026, 5, 8, 10, 5, tzinfo=UTC)
    outbox = InMemoryNotificationOutboxRepository(now)
    outbox.items = [
        _outbox_item(text="Лид 1", created_at=now - timedelta(minutes=5, seconds=1)),
        _outbox_item(text="Лид 2", created_at=now - timedelta(minutes=1)),
    ]
    sender = RecordingTelegramMessageSender()

    sent = await FlushNotificationOutbox(
        settings_repository=InMemoryNotificationSettingsRepository(_notification_settings()),
        outbox_repository=outbox,
        sender=sender,
        max_message_chars=4096,
        flush_interval=timedelta(minutes=5),
        min_chat_send_interval_seconds=0,
    ).execute(now=now)

    assert len(sent) == 1
    assert sender.sent == [("token-secret", "-100sales", "Лид 1\n\n---\n\nЛид 2")]
    assert outbox.sent_ids == [item.id for item in outbox.items]
    assert all(item.status == "sent" for item in outbox.items)


@pytest.mark.asyncio
async def test_notification_dispatcher_sends_full_batches_before_five_minutes() -> None:
    now = datetime(2026, 5, 8, 10, 2, tzinfo=UTC)
    outbox = InMemoryNotificationOutboxRepository(now)
    outbox.items = [
        _outbox_item(text="A" * 2000, created_at=now - timedelta(minutes=1)),
        _outbox_item(text="B" * 2000, created_at=now - timedelta(minutes=1)),
        _outbox_item(text="C" * 2000, created_at=now - timedelta(minutes=1)),
    ]
    sender = RecordingTelegramMessageSender()

    sent = await FlushNotificationOutbox(
        settings_repository=InMemoryNotificationSettingsRepository(_notification_settings()),
        outbox_repository=outbox,
        sender=sender,
        max_message_chars=4096,
        flush_interval=timedelta(minutes=5),
        min_chat_send_interval_seconds=0,
    ).execute(now=now)

    assert len(sent) == 1
    assert len(sender.sent[0][2]) <= 4096
    assert sender.sent[0][2] == f"{'A' * 2000}\n\n---\n\n{'B' * 2000}"
    assert [item.status for item in outbox.items] == ["sent", "sent", "pending"]


def _notification_settings() -> NotificationSettings:
    return NotificationSettings(
        bots=[
            TelegramBot(
                id="main_bot",
                name="Main",
                enabled=True,
                token="token-secret",
            )
        ],
        chats=[
            TelegramChat(
                id="sales_chat",
                name="Sales",
                enabled=True,
                telegram_chat_id="-100sales",
            )
        ],
        routes=[
            NotificationRoute(
                id="hot",
                name="Горячие лиды",
                enabled=True,
                priority=100,
                bot_id="main_bot",
                chat_id="sales_chat",
                match_mode="all",
                conditions=NotificationRouteConditions(is_lead=True, score_min=80),
                message_template="",
            )
        ],
        updated_at=None,
    )


def _lead_result() -> TextEnrichmentResult:
    return TextEnrichmentResult(
        original_text="Посоветуйте подрядчика по умному дому",
        normalized_text="посоветуйте подрядчика по умному дому",
        sentences=[],
        tokens=[],
        entities=[],
        facts=[],
        domain_signals=[],
        syntax=[],
        metrics=EnrichmentMetrics(
            character_count=38,
            sentence_count=1,
            token_count=5,
            entity_count=0,
            fact_count=0,
            domain_signal_count=0,
        ),
        pipeline_trace=[],
        lead_assessment=LeadAssessment(
            is_lead=True,
            score=95,
            temperature="hot",
            solution_areas=[
                LeadCategory(type="smart_home", label="Умный дом", matched_types=[])
            ],
            customer_segments=[
                LeadCategory(type="active_request", label="Активный запрос", matched_types=[])
            ],
            intent_signals=[],
            noise_signals=[],
            reasons=[
                LeadReason(
                    source="signal",
                    key="provider_search",
                    label="Поиск подрядчика",
                    weight=12,
                    matched_texts=["посоветуйте"],
                )
            ],
            review_lane=LeadReviewLane(
                key="direct_pur_lead",
                label="Прямой лид ПУР",
                description=None,
                matched_group_indexes=[0],
            ),
        ),
    )


def _outbox_item(*, text: str, created_at: datetime) -> NotificationOutboxItem:
    return NotificationOutboxItem(
        id=uuid4(),
        route_id="hot",
        bot_id="main_bot",
        chat_id="sales_chat",
        source_message_id=None,
        enrichment_job_id=None,
        text=text,
        status="pending",
        attempts=0,
        last_error=None,
        created_at=created_at,
        sent_at=None,
    )
