from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.domain.lead_handling import LeadHandlingActor
from app.infrastructure.persistence.lead_handling_repository import PostgresLeadHandlingRepository
from app.infrastructure.persistence.tables import lead_bot_sessions, lead_handling_events
from app.infrastructure.persistence.tables import lead_handlings, telegram_source_messages


TEST_TEXT = "__lead_handling_repository_test__"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: lead_bot_sessions.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: lead_handlings.create(sync, checkfirst=True))
        await connection.run_sync(lambda sync: lead_handling_events.create(sync, checkfirst=True))
        await connection.execute(
            telegram_source_messages.delete().where(telegram_source_messages.c.text == TEST_TEXT)
        )
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                telegram_source_messages.delete().where(telegram_source_messages.c.text == TEST_TEXT)
            )
            await connection.run_sync(lambda sync: lead_bot_sessions.drop(sync, checkfirst=True))
            await connection.run_sync(lambda sync: lead_handling_events.drop(sync, checkfirst=True))
            await connection.run_sync(lambda sync: lead_handlings.drop(sync, checkfirst=True))
        await engine.dispose()


@pytest.mark.asyncio
async def test_claim_creates_handling_and_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresLeadHandlingRepository(session_factory)
    source_message_id = uuid4()
    await _insert_source_message(session_factory, source_message_id)

    result = await repository.claim(
        source_message_id=source_message_id,
        sales_chat_id="-1001",
        sales_chat_message_id=42,
        actor=_actor("100", "manager"),
    )

    assert result.handling.status == "claimed"
    assert result.handling.source_message_id == source_message_id
    assert result.handling.owner_telegram_user_id == "100"
    assert result.handling.owner_telegram_username == "manager"
    assert result.handling.sales_chat_id == "-1001"
    assert result.handling.sales_chat_message_id == 42
    assert result.already_claimed is False
    assert result.event.event_type == "claimed"
    assert result.event.payload == {"sales_chat_id": "-1001", "sales_chat_message_id": 42}


@pytest.mark.asyncio
async def test_second_claim_from_other_user_does_not_replace_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresLeadHandlingRepository(session_factory)
    source_message_id = uuid4()
    await _insert_source_message(session_factory, source_message_id)
    await repository.claim(
        source_message_id=source_message_id,
        sales_chat_id="-1001",
        sales_chat_message_id=1,
        actor=_actor("100", "first"),
    )

    result = await repository.claim(
        source_message_id=source_message_id,
        sales_chat_id="-1001",
        sales_chat_message_id=1,
        actor=_actor("200", "second"),
    )

    assert result.handling.owner_telegram_user_id == "100"
    assert result.handling.owner_telegram_username == "first"
    assert result.already_claimed is True
    assert result.event.event_type == "callback_failed"
    assert result.event.payload["reason"] == "already_claimed"


@pytest.mark.asyncio
async def test_mark_not_lead_upserts_handling_and_appends_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresLeadHandlingRepository(session_factory)
    source_message_id = uuid4()
    await _insert_source_message(session_factory, source_message_id)

    result = await repository.mark_not_lead(
        source_message_id=source_message_id,
        sales_chat_id="-1001",
        sales_chat_message_id=3,
        actor=_actor("100", "manager"),
    )

    assert result.handling.status == "not_lead"
    assert result.event.event_type == "marked_not_lead"
    assert await _event_count(session_factory, source_message_id) == 1


@pytest.mark.asyncio
async def test_comment_changes_status_and_owner_list_uses_existing_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresLeadHandlingRepository(session_factory)
    source_message_id = uuid4()
    await _insert_source_message(session_factory, source_message_id)
    await repository.claim(
        source_message_id=source_message_id,
        sales_chat_id="-1001",
        sales_chat_message_id=7,
        actor=_actor("100", "manager"),
    )

    status_result = await repository.change_status(
        source_message_id=source_message_id,
        status="waiting",
        actor=_actor("100", "manager"),
    )
    comment_result = await repository.add_comment(
        source_message_id=source_message_id,
        comment="Созвонились, ждет КП",
        actor=_actor("100", "manager"),
    )
    leads = await repository.list_for_owner(telegram_user_id="100", limit=10)

    assert status_result.handling.status == "waiting"
    assert comment_result.handling.last_comment == "Созвонились, ждет КП"
    assert [lead.source_message_id for lead in leads] == [source_message_id]
    assert leads[0].status == "waiting"
    assert leads[0].last_comment == "Созвонились, ждет КП"
    assert await _event_count(session_factory, source_message_id) == 3


@pytest.mark.asyncio
async def test_private_session_state_round_trip_and_clear(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresLeadHandlingRepository(session_factory)

    await repository.set_session_state(
        bot_id="main_bot",
        telegram_user_id="100",
        state="awaiting_comment",
        payload={"source_message_id": str(uuid4())},
    )
    session = await repository.get_session_state(bot_id="main_bot", telegram_user_id="100")
    await repository.clear_session_state(bot_id="main_bot", telegram_user_id="100")

    assert session is not None
    assert session.state == "awaiting_comment"
    assert session.payload.keys() == {"source_message_id"}
    assert await repository.get_session_state(bot_id="main_bot", telegram_user_id="100") is None


def _actor(telegram_user_id: str, username: str) -> LeadHandlingActor:
    return LeadHandlingActor(
        telegram_user_id=telegram_user_id,
        telegram_username=username,
        display_name=username.title(),
    )


async def _insert_source_message(
    session_factory: async_sessionmaker[AsyncSession],
    source_message_id: UUID,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        await session.execute(
            telegram_source_messages.insert().values(
                id=source_message_id,
                account_id=uuid4(),
                source_chat_id=uuid4(),
                telegram_message_id=1,
                message_date=now,
                sender_id="sender",
                sender_username="sender",
                text=TEST_TEXT,
                raw_payload={"test_suite": "lead_handling_repository"},
                enrichment_job_id=uuid4(),
                created_at=now,
            )
        )
        await session.commit()


async def _event_count(
    session_factory: async_sessionmaker[AsyncSession],
    source_message_id: UUID,
) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(lead_handling_events)
                .where(lead_handling_events.c.source_message_id == source_message_id)
            )
            or 0
        )
