"""Quality and evaluation visibility routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pur_leads.models.evaluation import (
    decision_records_table,
    evaluation_cases_table,
    evaluation_datasets_table,
    evaluation_results_table,
    evaluation_runs_table,
    quality_metric_snapshots_table,
)
from pur_leads.services.audit import mask_secret_values
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/quality")


@router.get("/summary")
def quality_summary(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    failed_results_query = (
        select(evaluation_results_table)
        .where(evaluation_results_table.c.passed.is_(False))
        .order_by(evaluation_results_table.c.created_at.desc())
        .limit(10)
    )
    failed_runs_query = (
        select(evaluation_runs_table)
        .where(evaluation_runs_table.c.status == "failed")
        .order_by(evaluation_runs_table.c.started_at.desc())
        .limit(10)
    )
    return {
        "decisions": {
            "total": _table_count(session, decision_records_table),
            "by_type": _count_by(session, decision_records_table, "decision_type"),
            "by_status": _count_by(session, decision_records_table, "status"),
        },
        "datasets": {
            "total": _table_count(session, evaluation_datasets_table),
            "by_type": _count_by(session, evaluation_datasets_table, "dataset_type"),
            "by_status": _count_by(session, evaluation_datasets_table, "status"),
        },
        "cases": {
            "total": _table_count(session, evaluation_cases_table),
            "by_label_source": _count_by(session, evaluation_cases_table, "label_source"),
            "by_expected_decision": _count_by(
                session,
                evaluation_cases_table,
                "expected_decision",
            ),
        },
        "runs": {
            "total": _table_count(session, evaluation_runs_table),
            "by_status": _count_by(session, evaluation_runs_table, "status"),
            "by_type": _count_by(session, evaluation_runs_table, "run_type"),
            "recent_failed": _rows(session, failed_runs_query),
        },
        "results": {
            "total": _table_count(session, evaluation_results_table),
            "passed": _result_count(session, passed=True),
            "failed": _result_count(session, passed=False),
            "failure_types": _count_by(session, evaluation_results_table, "failure_type"),
            "recent_failed": _rows(session, failed_results_query),
        },
        "snapshots": {
            "total": _table_count(session, quality_metric_snapshots_table),
            "by_scope": _count_by(session, quality_metric_snapshots_table, "scope"),
            "latest": _rows(
                session,
                select(quality_metric_snapshots_table)
                .order_by(quality_metric_snapshots_table.c.created_at.desc())
                .limit(10),
            ),
        },
    }


@router.get("/decisions")
def list_decisions(
    decision_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    source_message_id: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(decision_records_table)
    if decision_type:
        query = query.where(decision_records_table.c.decision_type == decision_type)
    if entity_type:
        query = query.where(decision_records_table.c.entity_type == entity_type)
    if entity_id:
        query = query.where(decision_records_table.c.entity_id == entity_id)
    if source_message_id:
        query = query.where(decision_records_table.c.source_message_id == source_message_id)
    query = query.order_by(decision_records_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/datasets")
def list_datasets(
    dataset_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(evaluation_datasets_table)
    if dataset_type:
        query = query.where(evaluation_datasets_table.c.dataset_type == dataset_type)
    if status:
        query = query.where(evaluation_datasets_table.c.status == status)
    query = query.order_by(evaluation_datasets_table.c.updated_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/cases")
def list_cases(
    dataset_id: str | None = None,
    label_source: str | None = None,
    expected_decision: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(evaluation_cases_table)
    if dataset_id:
        query = query.where(evaluation_cases_table.c.evaluation_dataset_id == dataset_id)
    if label_source:
        query = query.where(evaluation_cases_table.c.label_source == label_source)
    if expected_decision:
        query = query.where(evaluation_cases_table.c.expected_decision == expected_decision)
    query = query.order_by(evaluation_cases_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/runs")
def list_runs(
    dataset_id: str | None = None,
    status: str | None = None,
    run_type: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(evaluation_runs_table)
    if dataset_id:
        query = query.where(evaluation_runs_table.c.evaluation_dataset_id == dataset_id)
    if status:
        query = query.where(evaluation_runs_table.c.status == status)
    if run_type:
        query = query.where(evaluation_runs_table.c.run_type == run_type)
    query = query.order_by(evaluation_runs_table.c.started_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


@router.get("/results")
def list_results(
    run_id: str | None = None,
    passed: bool | None = None,
    failure_type: str | None = None,
    limit: int = 100,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(evaluation_results_table)
    if run_id:
        query = query.where(evaluation_results_table.c.evaluation_run_id == run_id)
    if passed is not None:
        query = query.where(evaluation_results_table.c.passed == passed)
    if failure_type:
        query = query.where(evaluation_results_table.c.failure_type == failure_type)
    query = query.order_by(evaluation_results_table.c.created_at.desc()).limit(_limit(limit))
    return {"items": _rows(session, query)}


def _table_count(session: Session, table) -> int:  # type: ignore[no-untyped-def]
    return int(session.execute(select(func.count()).select_from(table)).scalar_one())


def _result_count(session: Session, *, passed: bool) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(evaluation_results_table)
            .where(evaluation_results_table.c.passed == passed)
        ).scalar_one()
    )


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
