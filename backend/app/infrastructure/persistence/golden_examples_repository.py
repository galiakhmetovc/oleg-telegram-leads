from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.golden_examples import GoldenExample
from app.infrastructure.persistence.tables import enrichment_jobs, golden_examples
from app.infrastructure.persistence.tables import message_reviews
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages


class PostgresGoldenExamplesRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_examples(self, *, limit: int, offset: int) -> tuple[int, list[GoldenExample]]:
        async with self._session_factory() as session:
            total = int(await session.scalar(sa.select(sa.func.count()).select_from(golden_examples)) or 0)
            result = await session.execute(
                sa.select(golden_examples)
                .order_by(golden_examples.c.created_at.desc(), golden_examples.c.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return total, [_golden_example_from_row(row) for row in result.mappings()]

    async def create_example(
        self,
        *,
        text: str,
        title: str | None,
        expected_verdict: str | None,
        comment: str,
    ) -> GoldenExample:
        now = datetime.now(UTC)
        example_title = title.strip() if title else ""
        values = {
            "id": uuid4(),
            "title": example_title or _default_title(text),
            "text": text.strip(),
            "expected_verdict": expected_verdict,
            "comment": comment,
            "source_message_id": None,
            "source_chat_title": None,
            "telegram_message_id": None,
            "telegram_message_url": None,
            "last_enrichment_job_id": None,
            "created_at": now,
            "updated_at": now,
        }
        async with self._session_factory() as session:
            result = await session.execute(
                golden_examples.insert().values(**values).returning(golden_examples)
            )
            row = result.mappings().one()
            await session.commit()
            return _golden_example_from_row(row)

    async def get_example(self, example_id: UUID) -> GoldenExample | None:
        async with self._session_factory() as session:
            return await _get_example(session, example_id)

    async def delete_example(self, example_id: UUID) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                golden_examples.delete()
                .where(golden_examples.c.id == example_id)
                .returning(golden_examples.c.id)
            )
            deleted_id = result.scalar_one_or_none()
            await session.commit()
            return deleted_id is not None

    async def get_by_source_message_id(self, source_message_id: UUID) -> GoldenExample | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(golden_examples).where(golden_examples.c.source_message_id == source_message_id)
            )
            row = result.mappings().first()
            return _golden_example_from_row(row) if row is not None else None

    async def create_from_source_message(self, source_message_id: UUID) -> GoldenExample | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            existing = await _get_by_source_message_id(session, source_message_id)
            if existing is not None:
                return existing

            source = await _get_source_message(session, source_message_id)
            if source is None:
                return None

            telegram_message_id = int(source["telegram_message_id"])
            source_chat_title = str(source["source_chat_title"] or "")
            telegram_message_url = _telegram_message_url(
                input_ref=str(source["input_ref"] or ""),
                telegram_chat_id=source["telegram_chat_id"],
                telegram_message_id=telegram_message_id,
            )
            values = {
                "id": uuid4(),
                "title": f"{source_chat_title or 'Telegram'} #{telegram_message_id}",
                "text": str(source["text"]),
                "expected_verdict": source["review_verdict"],
                "comment": str(source["review_comment"] or ""),
                "source_message_id": source_message_id,
                "source_chat_title": source_chat_title or None,
                "telegram_message_id": telegram_message_id,
                "telegram_message_url": telegram_message_url,
                "last_enrichment_job_id": source["enrichment_job_id"],
                "created_at": now,
                "updated_at": now,
            }
            statement = (
                insert(golden_examples)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[golden_examples.c.source_message_id])
                .returning(golden_examples)
            )
            result = await session.execute(statement)
            row = result.mappings().first()
            if row is None:
                existing = await _get_by_source_message_id(session, source_message_id)
                await session.commit()
                return existing
            await session.commit()
            return _golden_example_from_row(row)

    async def set_last_enrichment_job(self, *, example_id: UUID, job_id: UUID) -> GoldenExample | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.execute(
                golden_examples.update()
                .where(golden_examples.c.id == example_id)
                .values(last_enrichment_job_id=job_id, updated_at=now)
                .returning(golden_examples)
            )
            row = result.mappings().first()
            await session.commit()
            return _golden_example_from_row(row) if row is not None else None


async def _get_example(session: AsyncSession, example_id: UUID) -> GoldenExample | None:
    result = await session.execute(sa.select(golden_examples).where(golden_examples.c.id == example_id))
    row = result.mappings().first()
    return _golden_example_from_row(row) if row is not None else None


async def _get_by_source_message_id(session: AsyncSession, source_message_id: UUID) -> GoldenExample | None:
    result = await session.execute(
        sa.select(golden_examples).where(golden_examples.c.source_message_id == source_message_id)
    )
    row = result.mappings().first()
    return _golden_example_from_row(row) if row is not None else None


async def _get_source_message(session: AsyncSession, source_message_id: UUID) -> Any | None:
    result = await session.execute(
        sa.select(
            telegram_source_messages.c.id,
            telegram_source_messages.c.text,
            telegram_source_messages.c.telegram_message_id,
            telegram_source_messages.c.enrichment_job_id,
            telegram_source_chats.c.title.label("source_chat_title"),
            telegram_source_chats.c.input_ref,
            telegram_source_chats.c.telegram_chat_id,
            message_reviews.c.verdict.label("review_verdict"),
            message_reviews.c.comment.label("review_comment"),
        )
        .select_from(
            telegram_source_messages.join(
                telegram_source_chats,
                telegram_source_chats.c.id == telegram_source_messages.c.source_chat_id,
            )
            .outerjoin(
                message_reviews,
                message_reviews.c.source_message_id == telegram_source_messages.c.id,
            )
            .outerjoin(
                enrichment_jobs,
                enrichment_jobs.c.id == telegram_source_messages.c.enrichment_job_id,
            )
        )
        .where(telegram_source_messages.c.id == source_message_id)
    )
    return result.mappings().first()


def _golden_example_from_row(row: Any) -> GoldenExample:
    return GoldenExample(
        id=row["id"],
        title=str(row["title"]),
        text=str(row["text"]),
        expected_verdict=row["expected_verdict"],
        comment=str(row["comment"] or ""),
        source_message_id=row["source_message_id"],
        source_chat_title=row["source_chat_title"],
        telegram_message_id=row["telegram_message_id"],
        telegram_message_url=row["telegram_message_url"],
        last_enrichment_job_id=row["last_enrichment_job_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _default_title(text: str) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= 80:
        return compact or "Golden example"
    return f"{compact[:77].rstrip()}..."


def _telegram_message_url(
    *,
    input_ref: str,
    telegram_chat_id: str | None,
    telegram_message_id: int,
) -> str | None:
    normalized = input_ref.strip().rstrip("/")
    if normalized.startswith("@") and len(normalized) > 1:
        return f"https://t.me/{normalized[1:]}/{telegram_message_id}"
    if normalized.startswith("https://t.me/") and "/+" not in normalized:
        return f"{normalized}/{telegram_message_id}"
    if telegram_chat_id and telegram_chat_id.startswith("-100"):
        return f"https://t.me/c/{telegram_chat_id[4:]}/{telegram_message_id}"
    return None
