from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.settings import NlpConfigRevision
from app.infrastructure.persistence.tables import nlp_config_revisions


class PostgresNlpConfigRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_active_or_seed(
        self,
        default_documents: dict[str, dict[str, Any]],
    ) -> NlpConfigRevision:
        async with self._session_factory() as session:
            active = await self._get_active_revision(session)
            if active is not None:
                return active

            revision = await self._next_revision(session)
            await self._insert_revision(
                session,
                documents=default_documents,
                revision=revision,
                source="bootstrap",
            )
            await session.commit()

        active = await self.get_active()
        if active is None:
            raise RuntimeError("active NLP config revision is not readable after seed")
        return active

    async def get_active(self) -> NlpConfigRevision | None:
        async with self._session_factory() as session:
            return await self._get_active_revision(session)

    async def replace_active(
        self,
        documents: dict[str, dict[str, Any]],
        *,
        source: str,
    ) -> NlpConfigRevision:
        async with self._session_factory() as session:
            revision = await self._next_revision(session)
            await session.execute(
                nlp_config_revisions.update()
                .where(nlp_config_revisions.c.is_active.is_(True))
                .values(is_active=False)
            )
            revision_id = await self._insert_revision(
                session,
                documents=documents,
                revision=revision,
                source=source,
            )
            await session.commit()

        active = await self.get_active()
        if active is None or active.id != revision_id:
            raise RuntimeError("active NLP config revision is not readable after update")
        return active

    async def _get_active_revision(self, session: AsyncSession) -> NlpConfigRevision | None:
        result = await session.execute(
            sa.select(nlp_config_revisions)
            .where(nlp_config_revisions.c.is_active.is_(True))
            .order_by(nlp_config_revisions.c.revision.desc())
            .limit(1)
        )
        row = result.mappings().first()
        return _revision_from_row(row) if row is not None else None

    async def _next_revision(self, session: AsyncSession) -> int:
        result = await session.execute(sa.select(sa.func.coalesce(sa.func.max(nlp_config_revisions.c.revision), 0)))
        return int(result.scalar_one()) + 1

    async def _insert_revision(
        self,
        session: AsyncSession,
        *,
        documents: dict[str, dict[str, Any]],
        revision: int,
        source: str,
    ) -> UUID:
        revision_id = uuid4()
        await session.execute(
            nlp_config_revisions.insert().values(
                id=revision_id,
                revision=revision,
                config=documents,
                is_active=True,
                source=source,
                created_at=datetime.now(UTC),
            )
        )
        return revision_id


def _revision_from_row(row: Any) -> NlpConfigRevision:
    return NlpConfigRevision(
        id=row["id"],
        revision=row["revision"],
        documents=dict(row["config"]),
        source=row["source"],
        created_at=row["created_at"],
    )
