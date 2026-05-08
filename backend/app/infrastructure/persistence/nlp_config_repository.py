from __future__ import annotations

from copy import deepcopy
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
                merged_documents = merge_missing_default_documents(default_documents, active.documents)
                if merged_documents == active.documents:
                    return active

                revision = await self._next_revision(session)
                await session.execute(
                    nlp_config_revisions.update()
                    .where(nlp_config_revisions.c.is_active.is_(True))
                    .values(is_active=False)
                )
                await self._insert_revision(
                    session,
                    documents=merged_documents,
                    revision=revision,
                    source="bootstrap_merge",
                )
                await session.commit()
                active = await self._get_active_revision(session)
                if active is None:
                    raise RuntimeError("active NLP config revision is not readable after merge")
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


def merge_missing_default_documents(
    default_documents: dict[str, dict[str, Any]],
    active_documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = deepcopy(active_documents)
    for document_name, default_document in default_documents.items():
        if document_name not in merged:
            merged[document_name] = deepcopy(default_document)

    if "pipeline" in default_documents and "pipeline" in merged:
        merged["pipeline"] = _merge_pipeline_stages(
            default_documents["pipeline"],
            merged["pipeline"],
        )

    if "lead_scoring" in default_documents and "lead_scoring" in merged:
        merged["lead_scoring"] = _merge_lead_scoring_sections(
            default_documents["lead_scoring"],
            merged["lead_scoring"],
        )

    return merged


def _merge_pipeline_stages(
    default_pipeline: dict[str, Any],
    active_pipeline: dict[str, Any],
) -> dict[str, Any]:
    merged_pipeline = deepcopy(active_pipeline)
    active_stages = merged_pipeline.get("stages", [])
    default_stages = default_pipeline.get("stages", [])
    if not isinstance(active_stages, list) or not isinstance(default_stages, list):
        return merged_pipeline

    active_stage_names = {
        str(stage.get("name"))
        for stage in active_stages
        if isinstance(stage, dict) and stage.get("name") is not None
    }
    for stage in default_stages:
        if not isinstance(stage, dict):
            continue
        stage_name = stage.get("name")
        if stage_name is not None and str(stage_name) not in active_stage_names:
            active_stages.append(deepcopy(stage))
            active_stage_names.add(str(stage_name))
    merged_pipeline["stages"] = active_stages
    return merged_pipeline


def _merge_lead_scoring_sections(
    default_document: dict[str, Any],
    active_document: dict[str, Any],
) -> dict[str, Any]:
    merged_document = deepcopy(active_document)
    default_scoring = default_document.get("lead_scoring", {})
    active_scoring = merged_document.get("lead_scoring", {})
    if not isinstance(default_scoring, dict) or not isinstance(active_scoring, dict):
        return merged_document

    for key, value in default_scoring.items():
        if key not in active_scoring:
            active_scoring[key] = deepcopy(value)
    merged_document["lead_scoring"] = active_scoring
    return merged_document
