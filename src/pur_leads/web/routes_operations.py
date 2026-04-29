"""Operational visibility routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pur_leads.models.audit import audit_log_table, operational_events_table
from pur_leads.models.notifications import notification_events_table
from pur_leads.models.scheduler import job_runs_table, scheduler_jobs_table
from pur_leads.services.audit import mask_secret_values
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/operations")


@router.get("/summary")
def operations_summary(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {
        "jobs": {
            "total": _table_count(session, scheduler_jobs_table),
            "by_status": _count_by(session, scheduler_jobs_table, "status"),
            "by_type": _count_by(session, scheduler_jobs_table, "job_type"),
            "recent_failed": _rows(
                session,
                select(scheduler_jobs_table)
                .where(scheduler_jobs_table.c.status == "failed")
                .order_by(scheduler_jobs_table.c.updated_at.desc())
                .limit(10),
            ),
        },
        "runs": {
            "total": _table_count(session, job_runs_table),
            "by_status": _count_by(session, job_runs_table, "status"),
        },
        "events": {
            "total": _table_count(session, operational_events_table),
            "by_severity": _count_by(session, operational_events_table, "severity"),
            "by_type": _count_by(session, operational_events_table, "event_type"),
            "recent_errors": _rows(
                session,
                select(operational_events_table)
                .where(operational_events_table.c.severity.in_(["error", "critical"]))
                .order_by(operational_events_table.c.created_at.desc())
                .limit(10),
            ),
        },
        "notifications": {
            "total": _table_count(session, notification_events_table),
            "by_status": _count_by(session, notification_events_table, "status"),
            "by_policy": _count_by(session, notification_events_table, "notification_policy"),
        },
        "audit": {
            "total": _table_count(session, audit_log_table),
            "recent": _rows(
                session,
                select(audit_log_table).order_by(audit_log_table.c.created_at.desc()).limit(10),
            ),
        },
    }


@router.get("/jobs")
def list_jobs(
    status: str | None = None,
    job_type: str | None = None,
    monitored_source_id: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(scheduler_jobs_table)
    if status:
        query = query.where(scheduler_jobs_table.c.status == status)
    if job_type:
        query = query.where(scheduler_jobs_table.c.job_type == job_type)
    if monitored_source_id:
        query = query.where(scheduler_jobs_table.c.monitored_source_id == monitored_source_id)
    query = query.order_by(scheduler_jobs_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/jobs/{job_id}")
def get_job_detail(
    job_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = (
        session.execute(select(scheduler_jobs_table).where(scheduler_jobs_table.c.id == job_id))
        .mappings()
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    runs = _rows(
        session,
        select(job_runs_table)
        .where(job_runs_table.c.scheduler_job_id == job_id)
        .order_by(job_runs_table.c.started_at.desc()),
    )
    events = _rows(
        session,
        select(operational_events_table)
        .where(
            operational_events_table.c.entity_type == "scheduler_job",
            operational_events_table.c.entity_id == job_id,
        )
        .order_by(operational_events_table.c.created_at.desc()),
    )
    return {"job": _row(job), "runs": runs, "events": events}


@router.get("/events")
def list_operational_events(
    severity: str | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(operational_events_table)
    if severity:
        query = query.where(operational_events_table.c.severity == severity)
    if event_type:
        query = query.where(operational_events_table.c.event_type == event_type)
    if entity_type:
        query = query.where(operational_events_table.c.entity_type == entity_type)
    if entity_id:
        query = query.where(operational_events_table.c.entity_id == entity_id)
    query = query.order_by(operational_events_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/audit")
def list_audit_log(
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(audit_log_table)
    if action:
        query = query.where(audit_log_table.c.action == action)
    if entity_type:
        query = query.where(audit_log_table.c.entity_type == entity_type)
    if entity_id:
        query = query.where(audit_log_table.c.entity_id == entity_id)
    query = query.order_by(audit_log_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/notifications")
def list_notification_events(
    status: str | None = None,
    notification_type: str | None = None,
    notification_policy: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(notification_events_table)
    if status:
        query = query.where(notification_events_table.c.status == status)
    if notification_type:
        query = query.where(notification_events_table.c.notification_type == notification_type)
    if notification_policy:
        query = query.where(notification_events_table.c.notification_policy == notification_policy)
    query = query.order_by(notification_events_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


def _table_count(session: Session, table) -> int:  # type: ignore[no-untyped-def]
    return int(session.execute(select(func.count()).select_from(table)).scalar_one())


def _count_by(session: Session, table, column_name: str) -> dict[str, int]:  # type: ignore[no-untyped-def]
    column = getattr(table.c, column_name)
    rows = session.execute(select(column, func.count()).group_by(column).order_by(column)).all()
    return {str(key): int(count) for key, count in rows if key is not None}


def _rows(session: Session, query) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return [_row(row) for row in session.execute(query).mappings().all()]


def _row(row) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return jsonable_encoder(mask_secret_values(dict(row)))


def _limit(value: int) -> int:
    return min(max(value, 1), 500)
