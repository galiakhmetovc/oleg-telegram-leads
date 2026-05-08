from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidatePage
from app.domain.analytics import AnalyticsRun
from app.infrastructure.persistence.tables import analytics_aggregates, analytics_candidates
from app.infrastructure.persistence.tables import analytics_runs


class PostgresAnalyticsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_runs(self) -> list[AnalyticsRun]:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(analytics_runs).order_by(
                    analytics_runs.c.finished_at.desc().nullslast(),
                    analytics_runs.c.imported_at.desc(),
                )
            )
            return [_run_from_row(row) for row in result.mappings()]

    async def get_run(self, run_id: UUID) -> AnalyticsRun | None:
        async with self._session_factory() as session:
            result = await session.execute(sa.select(analytics_runs).where(analytics_runs.c.id == run_id))
            row = result.mappings().first()
            return _run_from_row(row) if row is not None else None

    async def list_aggregates(self, run_id: UUID) -> list[AnalyticsAggregate]:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(analytics_aggregates)
                .where(analytics_aggregates.c.run_id == run_id)
                .order_by(analytics_aggregates.c.kind.asc(), analytics_aggregates.c.count.desc())
            )
            return [_aggregate_from_row(row) for row in result.mappings()]

    async def list_candidates(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
        score_min: int | None,
        temperature: str | None,
        signal: str | None,
        reason: str | None,
        solution_area: str | None,
        customer_segment: str | None,
        lane: str | None,
        q: str | None,
    ) -> AnalyticsCandidatePage:
        predicates = [analytics_candidates.c.run_id == run_id]
        if score_min is not None:
            predicates.append(analytics_candidates.c.score >= score_min)
        if temperature:
            predicates.append(analytics_candidates.c.temperature == temperature)
        if signal:
            predicates.append(sa.literal(signal) == sa.any_(analytics_candidates.c.signal_types))
        if reason:
            predicates.append(sa.literal(reason) == sa.any_(analytics_candidates.c.reason_keys))
        if solution_area:
            predicates.append(sa.literal(solution_area) == sa.any_(analytics_candidates.c.solution_area_types))
        if customer_segment:
            predicates.append(sa.literal(customer_segment) == sa.any_(analytics_candidates.c.customer_segment_types))
        if lane:
            predicates.append(analytics_candidates.c.review_lane == lane)
        if q:
            predicates.append(analytics_candidates.c.text.ilike(f"%{q}%"))

        async with self._session_factory() as session:
            total = await session.scalar(
                sa.select(sa.func.count()).select_from(analytics_candidates).where(*predicates)
            )
            result = await session.execute(
                sa.select(analytics_candidates)
                .where(*predicates)
                .order_by(analytics_candidates.c.score.desc(), analytics_candidates.c.message_id.asc())
                .limit(limit)
                .offset(offset)
            )
            return AnalyticsCandidatePage(
                total=int(total or 0),
                items=[_candidate_from_row(row) for row in result.mappings()],
            )

    async def replace_import(
        self,
        run: AnalyticsRun,
        candidates: Sequence[AnalyticsCandidate],
        aggregates: Sequence[AnalyticsAggregate],
    ) -> AnalyticsRun:
        async with self._session_factory() as session:
            result = await session.execute(sa.select(analytics_runs.c.id).where(analytics_runs.c.name == run.name))
            existing_run_id = result.scalar_one_or_none()
            run_id = existing_run_id or run.id

            if existing_run_id is not None:
                await session.execute(
                    analytics_candidates.delete().where(analytics_candidates.c.run_id == existing_run_id)
                )
                await session.execute(
                    analytics_aggregates.delete().where(analytics_aggregates.c.run_id == existing_run_id)
                )

            run_payload = _run_to_values(run, run_id)
            await session.execute(
                insert(analytics_runs)
                .values(run_payload)
                .on_conflict_do_update(
                    index_elements=[analytics_runs.c.name],
                    set_={
                        key: value
                        for key, value in run_payload.items()
                        if key not in {"id", "name"}
                    },
                )
            )

            for candidate_chunk in _chunks(candidates, 500):
                await session.execute(
                    analytics_candidates.insert(),
                    [_candidate_to_values(candidate, run_id) for candidate in candidate_chunk],
                )
            for aggregate_chunk in _chunks(aggregates, 500):
                await session.execute(
                    analytics_aggregates.insert(),
                    [_aggregate_to_values(aggregate, run_id) for aggregate in aggregate_chunk],
                )

            await session.commit()

        imported = await self.get_run(run_id)
        if imported is None:
            raise RuntimeError("imported analytics run is not readable")
        return imported


def _chunks[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _run_to_values(run: AnalyticsRun, run_id: UUID) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": run.name,
        "source": run.source,
        "input_path": run.input_path,
        "run_dir": run.run_dir,
        "processed": run.processed,
        "skipped": run.skipped,
        "failed": run.failed,
        "leads": run.leads,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "imported_at": run.imported_at,
        "summary": run.summary,
    }


def _candidate_to_values(candidate: AnalyticsCandidate, run_id: UUID) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "run_id": run_id,
        "message_id": candidate.message_id,
        "text": candidate.text,
        "score": candidate.score,
        "temperature": candidate.temperature,
        "review_lane": candidate.review_lane,
        "solution_areas": candidate.solution_areas,
        "customer_segments": candidate.customer_segments,
        "intent_signals": candidate.intent_signals,
        "noise_signals": candidate.noise_signals,
        "reasons": candidate.reasons,
        "domain_signals": candidate.domain_signals,
        "facts": candidate.facts,
        "signal_types": _unique_texts(item.get("type") for item in candidate.domain_signals),
        "fact_types": _unique_texts(item.get("type") for item in candidate.facts),
        "reason_keys": _unique_texts(item.get("key") for item in candidate.reasons),
        "solution_area_types": _unique_texts(item.get("type") for item in candidate.solution_areas),
        "customer_segment_types": _unique_texts(item.get("type") for item in candidate.customer_segments),
    }


def _aggregate_to_values(aggregate: AnalyticsAggregate, run_id: UUID) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "run_id": run_id,
        "kind": aggregate.kind,
        "key": aggregate.key,
        "label": aggregate.label,
        "count": aggregate.count,
        "payload": aggregate.payload,
    }


def _unique_texts(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text and text not in unique:
            unique.append(text)
    return unique


def _run_from_row(row: Any) -> AnalyticsRun:
    return AnalyticsRun(
        id=row["id"],
        name=str(row["name"]),
        source=str(row["source"]),
        input_path=str(row["input_path"]),
        run_dir=str(row["run_dir"]),
        processed=int(row["processed"]),
        skipped=int(row["skipped"]),
        failed=int(row["failed"]),
        leads=int(row["leads"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        imported_at=row["imported_at"] or datetime.now(UTC),
        summary=dict(row["summary"] or {}),
    )


def _aggregate_from_row(row: Any) -> AnalyticsAggregate:
    return AnalyticsAggregate(
        kind=str(row["kind"]),
        key=str(row["key"]),
        label=str(row["label"]),
        count=int(row["count"]),
        payload=dict(row["payload"] or {}),
    )


def _candidate_from_row(row: Any) -> AnalyticsCandidate:
    return AnalyticsCandidate(
        run_id=row["run_id"],
        message_id=str(row["message_id"]),
        text=str(row["text"]),
        score=int(row["score"]),
        temperature=str(row["temperature"]),
        review_lane=str(row["review_lane"]),
        solution_areas=list(row["solution_areas"] or []),
        customer_segments=list(row["customer_segments"] or []),
        intent_signals=list(row["intent_signals"] or []),
        noise_signals=list(row["noise_signals"] or []),
        reasons=list(row["reasons"] or []),
        domain_signals=list(row["domain_signals"] or []),
        facts=list(row["facts"] or []),
    )
