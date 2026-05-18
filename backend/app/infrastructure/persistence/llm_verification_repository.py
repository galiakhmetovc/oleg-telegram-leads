from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enrichment import TextEnrichmentResult
from app.domain.llm_verification import LlmVerificationRun, SourceMessageForLlmVerification
from app.infrastructure.persistence.tables import enrichment_results, llm_verifications
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages

LLM_CLAIM_TIMEOUT = timedelta(minutes=20)


class PostgresLlmVerificationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_source_message(self, source_message_id: UUID) -> SourceMessageForLlmVerification | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(
                    telegram_source_messages.c.id.label("source_message_id"),
                    telegram_source_messages.c.source_chat_id,
                    telegram_source_messages.c.telegram_message_id,
                    telegram_source_messages.c.text,
                    telegram_source_messages.c.enrichment_job_id,
                    telegram_source_chats.c.title.label("source_chat_title"),
                    enrichment_results.c.result.label("enrichment_result"),
                )
                .select_from(
                    telegram_source_messages.join(
                        telegram_source_chats,
                        telegram_source_messages.c.source_chat_id == telegram_source_chats.c.id,
                    ).join(
                        enrichment_results,
                        telegram_source_messages.c.enrichment_job_id == enrichment_results.c.job_id,
                    )
                )
                .where(telegram_source_messages.c.id == source_message_id)
            )
            row = result.mappings().first()
        return _source_from_row(row) if row is not None else None

    async def get_source_message_by_enrichment_job_id(self, enrichment_job_id: UUID) -> SourceMessageForLlmVerification | None:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(
                    telegram_source_messages.c.id.label("source_message_id"),
                    telegram_source_messages.c.source_chat_id,
                    telegram_source_messages.c.telegram_message_id,
                    telegram_source_messages.c.text,
                    telegram_source_messages.c.enrichment_job_id,
                    telegram_source_chats.c.title.label("source_chat_title"),
                    enrichment_results.c.result.label("enrichment_result"),
                )
                .select_from(
                    telegram_source_messages.join(
                        telegram_source_chats,
                        telegram_source_messages.c.source_chat_id == telegram_source_chats.c.id,
                    ).join(
                        enrichment_results,
                        telegram_source_messages.c.enrichment_job_id == enrichment_results.c.job_id,
                    )
                )
                .where(telegram_source_messages.c.enrichment_job_id == enrichment_job_id)
            )
            row = result.mappings().first()
        return _source_from_row(row) if row is not None else None

    async def save_run(self, run: LlmVerificationRun) -> LlmVerificationRun:
        async with self._session_factory() as session:
            await session.execute(
                llm_verifications.insert().values(
                    id=run.id,
                    source_message_id=run.source_message_id,
                    enrichment_job_id=run.enrichment_job_id,
                    model=run.model,
                    route_id=run.route_id,
                    prompt=run.prompt,
                    schema_version=run.schema_version,
                    status=run.status,
                    attempts=run.attempts,
                    claimed_at=run.claimed_at,
                    context_pack=run.context_pack,
                    response=run.response,
                    raw_response=run.raw_response,
                    error=run.error,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                )
            )
            await session.commit()
        return run

    async def get_run(self, run_id: UUID) -> LlmVerificationRun | None:
        async with self._session_factory() as session:
            result = await session.execute(sa.select(llm_verifications).where(llm_verifications.c.id == run_id))
            row = result.mappings().first()
        return _run_from_row(row) if row is not None else None

    async def claim_run(self, run_id: UUID) -> LlmVerificationRun | None:
        now = datetime.now(UTC)
        stale_before = now - LLM_CLAIM_TIMEOUT
        async with self._session_factory() as session:
            result = await session.execute(
                llm_verifications.update()
                .where(llm_verifications.c.id == run_id)
                .where(
                    (llm_verifications.c.status == "queued")
                    | (
                        (llm_verifications.c.status == "running")
                        & (llm_verifications.c.claimed_at < stale_before)
                    )
                )
                .values(
                    status="running",
                    attempts=llm_verifications.c.attempts + 1,
                    claimed_at=now,
                    updated_at=now,
                )
                .returning(llm_verifications)
            )
            row = result.mappings().first()
            await session.commit()
        return _run_from_row(row) if row is not None else None

    async def complete_run(
        self,
        run_id: UUID,
        *,
        response: dict[str, object],
        raw_response: str,
        completed_at: datetime,
    ) -> LlmVerificationRun | None:
        async with self._session_factory() as session:
            result = await session.execute(
                llm_verifications.update()
                .where(llm_verifications.c.id == run_id)
                .values(
                    status="completed",
                    response=response,
                    raw_response=raw_response,
                    error=None,
                    claimed_at=None,
                    updated_at=completed_at,
                )
                .returning(llm_verifications)
            )
            row = result.mappings().first()
            await session.commit()
        return _run_from_row(row) if row is not None else None

    async def fail_run(
        self,
        run_id: UUID,
        *,
        error: str,
        raw_response: str | None,
        failed_at: datetime,
    ) -> LlmVerificationRun | None:
        async with self._session_factory() as session:
            result = await session.execute(
                llm_verifications.update()
                .where(llm_verifications.c.id == run_id)
                .values(
                    status="failed",
                    response=None,
                    raw_response=raw_response,
                    error=error,
                    claimed_at=None,
                    updated_at=failed_at,
                )
                .returning(llm_verifications)
            )
            row = result.mappings().first()
            await session.commit()
        return _run_from_row(row) if row is not None else None

    async def list_runs(self, source_message_id: UUID) -> list[LlmVerificationRun]:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(llm_verifications)
                .where(llm_verifications.c.source_message_id == source_message_id)
                .order_by(llm_verifications.c.created_at.desc())
            )
            rows = result.mappings().all()
        return [_run_from_row(row) for row in rows]

    async def list_all_runs(self, *, limit: int, offset: int) -> tuple[int, list[LlmVerificationRun]]:
        async with self._session_factory() as session:
            total_result = await session.execute(sa.select(sa.func.count()).select_from(llm_verifications))
            result = await session.execute(
                sa.select(llm_verifications)
                .order_by(llm_verifications.c.created_at.desc(), llm_verifications.c.id.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.mappings().all()
        return int(total_result.scalar_one()), [_run_from_row(row) for row in rows]

    async def route_run_exists(self, *, source_message_id: UUID, route_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(sa.func.count())
                .select_from(llm_verifications)
                .where(llm_verifications.c.source_message_id == source_message_id)
                .where(llm_verifications.c.route_id == route_id)
                .where(llm_verifications.c.status.in_(["queued", "running", "completed"]))
            )
        return int(result.scalar_one()) > 0


def _source_from_row(row: Any) -> SourceMessageForLlmVerification:
    return SourceMessageForLlmVerification(
        source_message_id=row["source_message_id"],
        source_chat_id=row["source_chat_id"],
        source_chat_title=row["source_chat_title"],
        telegram_message_id=row["telegram_message_id"],
        text=row["text"],
        enrichment_job_id=row["enrichment_job_id"],
        enrichment_result=TextEnrichmentResult.from_dict(row["enrichment_result"]),
    )


def _run_from_row(row: Any) -> LlmVerificationRun:
    return LlmVerificationRun(
        id=row["id"],
        source_message_id=row["source_message_id"],
        enrichment_job_id=row["enrichment_job_id"],
        model=row["model"],
        route_id=row.get("route_id"),
        prompt=row.get("prompt"),
        schema_version=row["schema_version"],
        status=row["status"],
        attempts=row.get("attempts") or 0,
        claimed_at=row.get("claimed_at"),
        context_pack=row["context_pack"],
        response=row["response"],
        raw_response=row["raw_response"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
