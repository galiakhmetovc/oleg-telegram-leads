from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.infrastructure.persistence.notification_summary_repository import (
    PostgresNotificationSummaryRepository,
)
from app.infrastructure.persistence.tables import enrichment_jobs, enrichment_results
from app.infrastructure.persistence.tables import llm_verifications, notification_outbox
from app.infrastructure.persistence.tables import notification_summary_runs
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages

TEST_PREFIX = "__notification_summary_repository_test__"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await _cleanup(connection)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await _cleanup(connection)
        await engine.dispose()


@pytest.mark.asyncio
async def test_claim_run_allows_period_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresNotificationSummaryRepository(
        session_factory,
        queue_depths=lambda: {"celery": 0, "llm": 0},
    )
    period_start = datetime(2036, 5, 15, 6, 0, tzinfo=UTC)
    period_end = datetime(2036, 5, 15, 18, 0, tzinfo=UTC)
    now = datetime(2036, 5, 15, 18, 5, tzinfo=UTC)

    first = await repository.claim_run(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        now=now,
    )
    second = await repository.claim_run(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        now=now,
    )
    await repository.mark_run_sent(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        telegram_message_id=100,
        sent_at=now,
    )

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_claim_run_retries_failed_period(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresNotificationSummaryRepository(
        session_factory,
        queue_depths=lambda: {"celery": 0, "llm": 0},
    )
    period_start = datetime(2036, 5, 16, 6, 0, tzinfo=UTC)
    period_end = datetime(2036, 5, 16, 18, 0, tzinfo=UTC)
    now = datetime(2036, 5, 16, 18, 5, tzinfo=UTC)
    assert await repository.claim_run(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        now=now,
    ) is True
    await repository.mark_run_failed(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        error="chat not found",
        failed_at=now,
    )

    retry = await repository.claim_run(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        now=now,
    )
    duplicate_retry = await repository.claim_run(
        period_kind="day",
        period_start=period_start,
        period_end=period_end,
        bot_id="summary_test_bot",
        chat_id="summary_test_chat",
        now=now,
    )

    assert retry is True
    assert duplicate_retry is False


@pytest.mark.asyncio
async def test_collect_metrics_counts_period_messages_and_leads(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresNotificationSummaryRepository(
        session_factory,
        queue_depths=lambda: {"celery": 4, "llm": 0},
    )
    period_start = datetime(2036, 5, 15, 6, 0, tzinfo=UTC)
    period_end = datetime(2036, 5, 15, 18, 0, tzinfo=UTC)
    before = await repository.collect_metrics(period_start=period_start, period_end=period_end)

    await _insert_runtime_rows(session_factory, period_start)

    after = await repository.collect_metrics(period_start=period_start, period_end=period_end)

    assert after.source_chats_enabled == before.source_chats_enabled + 3
    assert after.source_chats_by_status["resolved"] == before.source_chats_by_status.get("resolved", 0) + 2
    assert after.source_chats_by_status["missing"] == before.source_chats_by_status.get("missing", 0) + 1
    assert after.messages_received == before.messages_received + 4
    assert after.messages_processed == before.messages_processed + 2
    assert after.messages_failed == before.messages_failed + 1
    assert after.messages_waiting == before.messages_waiting + 1
    assert after.leads_by_temperature["hot"] == before.leads_by_temperature.get("hot", 0) + 1
    assert after.leads_by_temperature["warm"] == before.leads_by_temperature.get("warm", 0) + 1
    assert after.enrichment_jobs_by_status["completed"] == before.enrichment_jobs_by_status.get("completed", 0) + 2
    assert after.enrichment_jobs_by_status["failed"] == before.enrichment_jobs_by_status.get("failed", 0) + 1
    assert after.enrichment_jobs_by_status["queued"] == before.enrichment_jobs_by_status.get("queued", 0) + 1
    assert after.llm_runs_by_status["failed"] == before.llm_runs_by_status.get("failed", 0) + 1
    assert after.notification_outbox_by_status["pending"] == before.notification_outbox_by_status.get("pending", 0) + 1
    assert after.notification_outbox_by_status["failed"] == before.notification_outbox_by_status.get("failed", 0) + 1
    assert after.redis_queues == {"celery": 4, "llm": 0}


async def _insert_runtime_rows(
    session_factory: async_sessionmaker[AsyncSession],
    base_time: datetime,
) -> None:
    source_chat_ids = [uuid4(), uuid4(), uuid4(), uuid4()]
    job_ids = [uuid4(), uuid4(), uuid4(), uuid4()]
    message_ids = [uuid4(), uuid4(), uuid4(), uuid4()]
    async with session_factory() as session:
        await session.execute(
            telegram_source_chats.insert(),
            [
                _source_chat_row(source_chat_ids[0], "resolved", True, 1),
                _source_chat_row(source_chat_ids[1], "resolved", True, 2),
                _source_chat_row(source_chat_ids[2], "missing", True, 3),
                _source_chat_row(source_chat_ids[3], "error", False, 4),
            ],
        )
        await session.execute(
            enrichment_jobs.insert(),
            [
                _job_row(job_ids[0], "completed", base_time, "hot"),
                _job_row(job_ids[1], "completed", base_time, "warm"),
                _job_row(job_ids[2], "failed", base_time, "failed"),
                _job_row(job_ids[3], "queued", base_time, "queued"),
            ],
        )
        await session.execute(
            telegram_source_messages.insert(),
            [
                _message_row(message_ids[0], source_chat_ids[0], job_ids[0], base_time, 1),
                _message_row(message_ids[1], source_chat_ids[0], job_ids[1], base_time, 2),
                _message_row(message_ids[2], source_chat_ids[1], job_ids[2], base_time, 3),
                _message_row(message_ids[3], source_chat_ids[1], job_ids[3], base_time, 4),
            ],
        )
        await session.execute(
            enrichment_results.insert(),
            [
                _result_row(job_ids[0], "hot", base_time),
                _result_row(job_ids[1], "warm", base_time),
            ],
        )
        await session.execute(
            llm_verifications.insert(),
            [
                _llm_row(uuid4(), message_ids[0], job_ids[0], "completed", base_time),
                _llm_row(uuid4(), message_ids[1], job_ids[1], "failed", base_time),
            ],
        )
        await session.execute(
            notification_outbox.insert(),
            [
                _outbox_row(uuid4(), message_ids[0], job_ids[0], "pending", base_time),
                _outbox_row(uuid4(), message_ids[1], job_ids[1], "failed", base_time),
            ],
        )
        await session.commit()


def _source_chat_row(chat_id: UUID, status: str, enabled: bool, index: int) -> dict[str, object]:
    now = datetime(2036, 5, 15, tzinfo=UTC)
    return {
        "id": chat_id,
        "account_id": uuid4(),
        "title": f"{TEST_PREFIX} chat {index}",
        "input_ref": f"{TEST_PREFIX}_{index}",
        "telegram_chat_id": str(-1000 - index),
        "enabled": enabled,
        "status": status,
        "last_message_id": None,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }


def _job_row(job_id: UUID, status: str, created_at: datetime, suffix: str) -> dict[str, object]:
    return {
        "id": job_id,
        "input_text": f"{TEST_PREFIX} {suffix}",
        "status": status,
        "progress_percent": 100 if status == "completed" else 0,
        "current_stage": None,
        "stage_index": 0,
        "stage_count": 0,
        "stage_progress_percent": 0,
        "message": status,
        "error": {"message": "failed"} if status == "failed" else None,
        "created_at": created_at,
        "started_at": created_at if status != "queued" else None,
        "finished_at": created_at if status in {"completed", "failed"} else None,
        "updated_at": created_at,
        "nlp_config_revision_id": None,
        "nlp_config_revision": None,
    }


def _message_row(
    message_id: UUID,
    source_chat_id: UUID,
    job_id: UUID,
    created_at: datetime,
    telegram_message_id: int,
) -> dict[str, object]:
    return {
        "id": message_id,
        "account_id": uuid4(),
        "source_chat_id": source_chat_id,
        "telegram_message_id": telegram_message_id,
        "message_date": created_at,
        "sender_id": "sender",
        "sender_username": "sender",
        "text": f"{TEST_PREFIX} message {telegram_message_id}",
        "raw_payload": {"test_suite": "notification_summary_repository"},
        "enrichment_job_id": job_id,
        "created_at": created_at,
    }


def _result_row(job_id: UUID, temperature: str, created_at: datetime) -> dict[str, object]:
    return {
        "job_id": job_id,
        "result": {
            "lead_assessment": {
                "is_lead": True,
                "temperature": temperature,
            }
        },
        "created_at": created_at,
    }


def _llm_row(
    run_id: UUID,
    source_message_id: UUID,
    job_id: UUID,
    status: str,
    created_at: datetime,
) -> dict[str, object]:
    return {
        "id": run_id,
        "source_message_id": source_message_id,
        "enrichment_job_id": job_id,
        "model": "summary-test-model",
        "route_id": "summary_test_route",
        "prompt": None,
        "schema_version": "test",
        "status": status,
        "attempts": 0,
        "claimed_at": None,
        "context_pack": {},
        "response": {},
        "raw_response": None,
        "error": "failed" if status == "failed" else None,
        "created_at": created_at,
        "updated_at": created_at,
    }


def _outbox_row(
    item_id: UUID,
    source_message_id: UUID,
    job_id: UUID,
    status: str,
    created_at: datetime,
) -> dict[str, object]:
    return {
        "id": item_id,
        "route_id": f"{TEST_PREFIX}_route",
        "bot_id": "summary_test_bot",
        "chat_id": "summary_test_chat",
        "source_message_id": source_message_id,
        "enrichment_job_id": job_id,
        "text": f"{TEST_PREFIX} notification",
        "status": status,
        "attempts": 0,
        "last_error": "failed" if status == "failed" else None,
        "claimed_at": None,
        "created_at": created_at,
        "sent_at": None,
    }


async def _cleanup(connection: sa.ext.asyncio.AsyncConnection) -> None:
    await connection.execute(
        notification_summary_runs.delete().where(
            notification_summary_runs.c.bot_id == "summary_test_bot"
        )
    )
    await connection.execute(
        notification_outbox.delete().where(notification_outbox.c.route_id == f"{TEST_PREFIX}_route")
    )
    await connection.execute(
        enrichment_results.delete().where(
            enrichment_results.c.job_id.in_(
                sa.select(enrichment_jobs.c.id).where(enrichment_jobs.c.input_text.like(f"{TEST_PREFIX}%"))
            )
        )
    )
    await connection.execute(enrichment_jobs.delete().where(enrichment_jobs.c.input_text.like(f"{TEST_PREFIX}%")))
    await connection.execute(telegram_source_messages.delete().where(telegram_source_messages.c.text.like(f"{TEST_PREFIX}%")))
    await connection.execute(telegram_source_chats.delete().where(telegram_source_chats.c.input_ref.like(f"{TEST_PREFIX}%")))
