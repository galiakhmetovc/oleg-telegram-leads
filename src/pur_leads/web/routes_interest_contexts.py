"""Interest context web/API routes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.core.tracing import current_trace_json
from pur_leads.models.telegram_sources import telegram_raw_export_runs_table
from pur_leads.services.audit import AuditService
from pur_leads.services.interest_contexts import (
    INTEREST_CONTEXT_SOURCE_PURPOSE,
    InterestContextDetail,
    InterestContextService,
)
from pur_leads.services.telegram_desktop_import import (
    DESKTOP_IMPORT_EXPORT_FORMAT,
    TelegramDesktopArchiveImportService,
)
from pur_leads.services.tracing import TraceService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session
from pur_leads.web.routes_onboarding import _safe_upload_filename, _store_uploaded_file

router = APIRouter(prefix="/api/interest-contexts", tags=["interest-contexts"])


class InterestContextCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class InterestContextTelegramSourceRequest(BaseModel):
    input_ref: str = Field(min_length=1)
    range_mode: str = "source_start"
    recent_days: int | None = None
    message_id: int | None = None
    since_date: str | None = None
    batch_size: int = 1000
    max_messages: int | None = None
    media_enabled: bool = False
    media_types: list[str] = ["document"]
    max_media_size_bytes: int | None = None
    check_access: bool = False
    enqueue_raw_export: bool = True


@router.get("")
def list_interest_contexts(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    return {"items": [jsonable_encoder(asdict(row)) for row in service.list_contexts()]}


@router.post("")
def create_interest_context(
    payload: InterestContextCreateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        context = InterestContextService(session).create_context(
            name=payload.name,
            description=payload.description,
            actor=_actor(validated),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"context": jsonable_encoder(asdict(context))}


@router.get("/{context_id}")
def get_interest_context_detail(
    context_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = InterestContextService(session).get_detail(context_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interest context not found") from exc
    return _detail_payload(detail)


@router.post("/{context_id}/telegram-source")
def add_telegram_source_to_interest_context(
    context_id: str,
    payload: InterestContextTelegramSourceRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    try:
        source, access_job, raw_export_job = service.create_telegram_seed_source(
            context_id,
            input_ref=payload.input_ref,
            actor=_actor(validated),
            start_mode=_source_start_mode(payload),
            start_recent_days=payload.recent_days if payload.range_mode == "recent_days" else None,
            check_access=payload.check_access,
            enqueue_raw_export=payload.enqueue_raw_export,
            range_config={
                "mode": payload.range_mode,
                "recent_days": payload.recent_days,
                "message_id": payload.message_id,
                "since_date": payload.since_date,
                "batch_size": payload.batch_size,
                "max_messages": payload.max_messages,
            },
            media_config={
                "enabled": payload.media_enabled,
                "types": payload.media_types,
                "max_file_size_bytes": payload.max_media_size_bytes,
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interest context not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(
        {
            "source": asdict(source),
            "access_job": asdict(access_job) if access_job else None,
            "raw_export_job": asdict(raw_export_job) if raw_export_job else None,
        }
    )


@router.post("/{context_id}/telegram-archive")
async def upload_telegram_archive_to_interest_context(
    request: Request,
    context_id: str,
    file: UploadFile = File(...),
    display_name: str | None = Form(None),
    sync_source_messages: bool = Form(False),
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    try:
        context = service.repository.get(context_id)
        if context is None:
            raise KeyError(context_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interest context not found") from exc

    safe_name = _safe_upload_filename(file.filename or "telegram-export.zip")
    if not safe_name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Нужен zip-архив Telegram Desktop")

    upload_started_at = utc_now()
    stored_path, size_bytes, sha256 = await _store_uploaded_file(
        file,
        root=Path(request.app.state.raw_export_storage_path),
        safe_name=safe_name,
    )
    if not zipfile.is_zipfile(stored_path):
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Файл не похож на zip-архив Telegram Desktop")

    actor = _actor(validated)
    trace = current_trace_json()
    input_ref = display_name.strip() if display_name and display_name.strip() else None
    upload_metadata = {
        "original_filename": safe_name,
        "content_type": file.content_type,
        "stored_archive_path": str(stored_path),
        "size_bytes": size_bytes,
        "sha256": sha256,
        "uploaded_at": upload_started_at.isoformat(),
        "uploaded_by": actor,
    }
    if trace:
        upload_metadata["trace_id"] = trace["trace_id"]
        upload_metadata["web_session_id"] = trace.get("web_session_id")
        upload_metadata["user_id"] = trace.get("user_id")

    try:
        result = TelegramDesktopArchiveImportService(
            session,
            raw_root=request.app.state.raw_export_storage_path,
        ).import_archive(
            stored_path,
            input_ref=input_ref,
            purpose=INTEREST_CONTEXT_SOURCE_PURPOSE,
            interest_context_id=context_id,
            added_by=actor,
            sync_source_messages=sync_source_messages,
            import_metadata={
                "trace": trace,
                "upload": upload_metadata,
                "interest_context": {
                    "id": context.id,
                    "name": context.name,
                    "source_role": INTEREST_CONTEXT_SOURCE_PURPOSE,
                },
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service.repository.update(context.id, updated_at=utc_now())
    session.commit()
    TraceService(session).record_child_span(
        span_name="interest_context.import.telegram_desktop_archive",
        status="ok",
        started_at=upload_started_at,
        resource_type="interest_context",
        resource_id=context.id,
        attributes_json={
            "monitored_source_id": result.source.id,
            "raw_export_run_id": result.raw_export.run_id,
            "message_count": result.message_count,
            "attachment_count": result.attachment_count,
            "stored_archive_path": str(stored_path),
            "sha256": sha256,
        },
    )
    AuditService(session).record_change(
        actor=actor,
        action="interest_context.telegram_archive_uploaded",
        entity_type="interest_context",
        entity_id=context.id,
        old_value_json=None,
        new_value_json={
            "monitored_source_id": result.source.id,
            "raw_export_run_id": result.raw_export.run_id,
            "message_count": result.message_count,
            "attachment_count": result.attachment_count,
            "stored_archive_path": str(stored_path),
        },
    )
    raw_run = (
        session.execute(
            select(telegram_raw_export_runs_table).where(
                telegram_raw_export_runs_table.c.id == result.raw_export.run_id
            )
        )
        .mappings()
        .one()
    )
    return jsonable_encoder(
        {
            "source": asdict(result.source),
            "raw_export_run": {
                **dict(raw_run),
                "export_format": DESKTOP_IMPORT_EXPORT_FORMAT,
            },
            "result": result.as_jsonable(),
            "trace": trace,
        }
    )


@router.post("/{context_id}/draft")
def build_interest_context_draft(
    context_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = InterestContextService(session).get_detail(context_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interest context not found") from exc
    raw_runs = [
        source.latest_raw_export_run
        for source in detail.sources
        if source.latest_raw_export_run
        and source.latest_raw_export_run.get("status") == "succeeded"
    ]
    return {
        "status": "manual_next_step",
        "message": (
            "Сырые данные собраны. Следующий ручной шаг: открыть артефакты, "
            "проверить raw/parquet и запустить подготовку знаний."
        ),
        "ready_raw_export_runs": len(raw_runs),
    }


def _source_start_mode(payload: InterestContextTelegramSourceRequest) -> str | None:
    if payload.range_mode == "from_beginning":
        return "from_beginning"
    if payload.range_mode == "recent_days":
        return "recent_days"
    return None


def _detail_payload(detail: InterestContextDetail) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "context": asdict(detail.context),
            "sources": [
                {
                    **asdict(source.source),
                    "latest_raw_export_run": source.latest_raw_export_run,
                }
                for source in detail.sources
            ],
        }
    )


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id
