"""Interest context behavior."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.repositories.interest_contexts import (
    InterestContextRecord,
    InterestContextRepository,
)
from pur_leads.repositories.scheduler import SchedulerJobRecord
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord, TelegramSourceRepository
from pur_leads.services.audit import AuditService
from pur_leads.services.telegram_sources import TelegramSourceService

INTEREST_CONTEXT_SOURCE_PURPOSE = "interest_context_seed"


@dataclass(frozen=True)
class InterestContextSourceSummary:
    source: MonitoredSourceRecord
    latest_raw_export_run: dict[str, Any] | None


@dataclass(frozen=True)
class InterestContextDetail:
    context: InterestContextRecord
    sources: list[InterestContextSourceSummary]


class InterestContextService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = InterestContextRepository(session)
        self.telegram_sources = TelegramSourceRepository(session)
        self.audit = AuditService(session)

    def list_contexts(self) -> list[InterestContextRecord]:
        return self.repository.list_contexts()

    def has_active_or_draft_context(self) -> bool:
        return self.repository.count_active_or_draft() > 0

    def create_context(
        self,
        *,
        name: str,
        description: str | None,
        actor: str,
    ) -> InterestContextRecord:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("name is required")
        now = utc_now()
        context = self.repository.create(
            name=normalized_name,
            description=description.strip() if description and description.strip() else None,
            status="draft",
            created_by=actor,
            activated_at=None,
            created_at=now,
            updated_at=now,
        )
        self.audit.record_change(
            actor=actor,
            action="interest_context.create",
            entity_type="interest_context",
            entity_id=context.id,
            old_value_json=None,
            new_value_json=asdict(context),
        )
        return context

    def get_detail(self, context_id: str) -> InterestContextDetail:
        context = self._require_context(context_id)
        sources = self.telegram_sources.list_sources_for_interest_context(context.id)
        latest_runs = self._latest_raw_export_runs_by_source([source.id for source in sources])
        return InterestContextDetail(
            context=context,
            sources=[
                InterestContextSourceSummary(
                    source=source,
                    latest_raw_export_run=latest_runs.get(source.id),
                )
                for source in sources
            ],
        )

    def create_telegram_seed_source(
        self,
        context_id: str,
        *,
        input_ref: str,
        actor: str,
        start_mode: str | None,
        start_recent_days: int | None,
        check_access: bool,
        enqueue_raw_export: bool,
        range_config: dict[str, Any],
        media_config: dict[str, Any],
    ) -> tuple[MonitoredSourceRecord, SchedulerJobRecord | None, SchedulerJobRecord | None]:
        context = self._require_context(context_id)
        source_service = TelegramSourceService(self.session)
        source = source_service.create_draft(
            input_ref,
            added_by=actor,
            purpose=INTEREST_CONTEXT_SOURCE_PURPOSE,
            interest_context_id=context.id,
            start_mode=start_mode,
            start_recent_days=start_recent_days,
        )
        self.repository.update(context.id, updated_at=utc_now())
        access_job = (
            source_service.request_access_check(source.id, actor=actor) if check_access else None
        )
        raw_export_job = None
        if enqueue_raw_export:
            source, raw_export_job = source_service.request_raw_export(
                source.id,
                actor=actor,
                range_config=range_config,
                media_config=media_config,
                canonicalize=True,
            )
        else:
            self.session.commit()
        refreshed = source_service.repository.get(source.id)
        if refreshed is None:
            raise KeyError(source.id)
        return refreshed, access_job, raw_export_job

    def _require_context(self, context_id: str) -> InterestContextRecord:
        context = self.repository.get(context_id)
        if context is None:
            raise KeyError(context_id)
        return context

    def _latest_raw_export_runs_by_source(self, source_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not source_ids:
            return {}
        rows = (
            self.session.execute(
                select(telegram_raw_export_runs_table)
                .where(telegram_raw_export_runs_table.c.monitored_source_id.in_(source_ids))
                .order_by(telegram_raw_export_runs_table.c.started_at.desc())
            )
            .mappings()
            .all()
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            source_id = str(row["monitored_source_id"])
            if source_id not in latest:
                latest[source_id] = dict(row)
        return latest
