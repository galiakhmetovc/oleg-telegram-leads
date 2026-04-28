"""Telegram source onboarding routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pur_leads.repositories.scheduler import SchedulerJobRecord
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord
from pur_leads.services.telegram_sources import (
    ActivationRequiresPreview,
    CheckpointResetRequiresConfirmation,
    SourceDetail,
    TelegramSourceService,
)
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api")


class SourceCreateRequest(BaseModel):
    input_ref: str
    purpose: str = "lead_monitoring"
    check_access: bool = True


class SourcePreviewRequest(BaseModel):
    limit: int = 20


class SourceCheckpointRequest(BaseModel):
    message_id: int
    confirm: bool = False


@router.get("/sources")
def list_sources(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {
        "items": [_source_payload(row) for row in TelegramSourceService(session).list_sources()]
    }


@router.post("/sources")
def create_source(
    payload: SourceCreateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = TelegramSourceService(session)
    actor = _actor(validated)
    try:
        source = service.create_draft(
            payload.input_ref,
            purpose=payload.purpose,
            added_by=actor,
        )
        access_job = (
            service.request_access_check(source.id, actor=actor) if payload.check_access else None
        )
        created_source = service.repository.get(source.id)
        if created_source is None:
            raise KeyError("created source missing")
        source = created_source
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "source": _source_payload(source),
        "access_job": _job_payload(access_job) if access_job else None,
    }


@router.get("/sources/{source_id}")
def get_source_detail(
    source_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = TelegramSourceService(session).get_source_detail(source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    return _detail_payload(detail)


@router.post("/sources/{source_id}/check-access")
def request_access_check(
    source_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        job = TelegramSourceService(session).request_access_check(
            source_id, actor=_actor(validated)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    return {"job": _job_payload(job)}


@router.post("/sources/{source_id}/preview")
def request_preview(
    source_id: str,
    payload: SourcePreviewRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        job = TelegramSourceService(session).request_preview(
            source_id,
            actor=_actor(validated),
            limit=payload.limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except ActivationRequiresPreview as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job": _job_payload(job)}


@router.post("/sources/{source_id}/activate")
def activate_source(
    source_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        source, job = TelegramSourceService(session).activate_from_web(
            source_id,
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except ActivationRequiresPreview as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"source": _source_payload(source), "poll_job": _job_payload(job)}


@router.post("/sources/{source_id}/pause")
def pause_source(
    source_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        source = TelegramSourceService(session).pause(source_id, actor=_actor(validated))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    return {"source": _source_payload(source)}


@router.post("/sources/{source_id}/checkpoint")
def reset_checkpoint(
    source_id: str,
    payload: SourceCheckpointRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        source = TelegramSourceService(session).reset_checkpoint(
            source_id,
            message_id=payload.message_id,
            actor=_actor(validated),
            confirm=payload.confirm,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except CheckpointResetRequiresConfirmation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"source": _source_payload(source)}


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _source_payload(source: MonitoredSourceRecord) -> dict[str, Any]:
    return jsonable_encoder(asdict(source))


def _job_payload(job: SchedulerJobRecord) -> dict[str, Any]:
    return jsonable_encoder(asdict(job))


def _detail_payload(detail: SourceDetail) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "source": asdict(detail.source),
            "access_checks": [asdict(row) for row in detail.access_checks],
            "preview_messages": [asdict(row) for row in detail.preview_messages],
            "jobs": [asdict(row) for row in detail.jobs],
        }
    )
