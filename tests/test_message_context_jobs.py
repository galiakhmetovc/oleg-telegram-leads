from datetime import datetime

import pytest
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramMessage,
)
from pur_leads.models.telegram_sources import (
    message_context_links_table,
    source_messages_table,
)
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.message_context import MessageContextWorker


class FakeTelegramClient:
    def __init__(self) -> None:
        self.fetch_context_calls: list[dict[str, object]] = []

    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        return ResolvedTelegramSource(
            input_ref=input_ref,
            source_kind="telegram_supergroup",
            telegram_id="-1001",
            username="purmaster",
            title="PUR",
        )

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        return SourceAccessResult(status="succeeded", can_read_messages=True, can_read_history=True)

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        return []

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        after_date: object | None = None,
        limit: int,
    ) -> list[TelegramMessage]:
        return []

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        self.fetch_context_calls.append(
            {
                "source": source,
                "message_id": message_id,
                "before": before,
                "after": after,
                "reply_depth": reply_depth,
            }
        )
        return MessageContext(
            target_message_id=message_id,
            reply_messages=[_message(source, 90), _message(source, 80)],
            neighbor_before=[_message(source, 99), _message(source, 98)],
            neighbor_after=[_message(source, 101)],
        )


@pytest.fixture
def context_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "https://t.me/purmaster", purpose="lead_monitoring", added_by="admin"
        )
        target_id = _insert_source_message(session, source.id, 100)
        session.commit()
        yield session, source, target_id


@pytest.mark.asyncio
async def test_fetch_context_stores_reply_ancestors_and_neighbor_links(context_session):
    session, source, target_id = context_session
    client = FakeTelegramClient()
    worker = MessageContextWorker(session, client)

    result = await worker.fetch_context(target_id, before=2, after=1, reply_depth=2)

    call = client.fetch_context_calls[0]
    assert call["message_id"] == 100
    assert call["before"] == 2
    assert call["after"] == 1
    assert call["reply_depth"] == 2
    assert call["source"] == ResolvedTelegramSource(
        input_ref=source.input_ref,
        source_kind=source.source_kind,
        telegram_id=source.telegram_id,
        username=source.username,
        title=source.title,
    )
    assert result.created_source_messages == 5
    assert result.created_links == 5

    messages = (
        session.execute(
            select(source_messages_table).order_by(source_messages_table.c.telegram_message_id)
        )
        .mappings()
        .all()
    )
    assert [row["telegram_message_id"] for row in messages] == [80, 90, 98, 99, 100, 101]
    assert all(row["classification_status"] == "unclassified" for row in messages)
    assert all(row["is_archived_stub"] is False for row in messages)
    assert all(row["text_archived"] is False for row in messages)
    assert all(row["caption_archived"] is False for row in messages)
    assert all(row["metadata_archived"] is False for row in messages)
    assert next(row for row in messages if row["telegram_message_id"] == 101)[
        "raw_metadata_json"
    ] == {"message_id": 101}

    links = session.execute(
        select(
            message_context_links_table.c.related_source_message_id,
            message_context_links_table.c.relation_type,
            message_context_links_table.c.distance,
            source_messages_table.c.telegram_message_id,
        )
        .join(
            source_messages_table,
            source_messages_table.c.id == message_context_links_table.c.related_source_message_id,
        )
        .order_by(
            message_context_links_table.c.relation_type, message_context_links_table.c.distance
        )
    ).all()
    assert [(row.relation_type, row.distance, row.telegram_message_id) for row in links] == [
        ("neighbor_after", 1, 101),
        ("neighbor_before", -2, 98),
        ("neighbor_before", -1, 99),
        ("reply_ancestor", 1, 90),
        ("reply_ancestor", 2, 80),
    ]


@pytest.mark.asyncio
async def test_fetch_context_is_idempotent_for_same_window(context_session):
    session, _, target_id = context_session
    worker = MessageContextWorker(session, FakeTelegramClient())

    first = await worker.fetch_context(target_id, before=2, after=1, reply_depth=2)
    second = await worker.fetch_context(target_id, before=2, after=1, reply_depth=2)

    assert first.created_source_messages == 5
    assert first.created_links == 5
    assert second.created_source_messages == 0
    assert second.created_links == 0
    assert session.execute(select(source_messages_table)).all()
    assert len(session.execute(select(source_messages_table)).all()) == 6
    assert len(session.execute(select(message_context_links_table)).all()) == 5


def _insert_source_message(session, source_id: str, message_id: int) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            raw_source_id=None,
            telegram_message_id=message_id,
            sender_id="sender-1",
            message_date=datetime(2026, 4, 28, 12, 0, message_id % 60),
            text=f"message {message_id}",
            caption=None,
            normalized_text=None,
            has_media=False,
            media_metadata_json=None,
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={"message_id": message_id},
            fetched_at=now,
            classification_status="unclassified",
            archive_pointer_id=None,
            is_archived_stub=False,
            text_archived=False,
            caption_archived=False,
            metadata_archived=False,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _message(source: ResolvedTelegramSource, message_id: int) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref=source.input_ref,
        telegram_message_id=message_id,
        message_date=datetime(2026, 4, 28, 12, 0, message_id % 60),
        sender_id=f"user-{message_id}",
        sender_display=f"User {message_id}",
        text=f"message {message_id}",
        caption=f"caption {message_id}" if message_id == 101 else None,
        has_media=message_id == 101,
        media_metadata_json={"kind": "photo"} if message_id == 101 else None,
        reply_to_message_id=message_id - 1 if message_id in {80, 90} else None,
        thread_id="thread-1",
        forward_metadata_json={"from": "channel"} if message_id == 98 else None,
        raw_metadata_json={"message_id": message_id},
    )
