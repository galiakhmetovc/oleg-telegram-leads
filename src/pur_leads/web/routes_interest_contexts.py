"""Interest context web/API routes."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.core.tracing import current_trace_json
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.services.interest_context_drafts import (
    BUILD_INTEREST_CONTEXT_DRAFT_JOB,
    InterestContextDraftService,
)
from pur_leads.services.interest_core_candidate_enhancement import (
    ENHANCE_INTEREST_CORE_CANDIDATES_JOB,
)
from pur_leads.services.interest_core_candidate_reviews import (
    InterestCoreCandidateReviewService,
)
from pur_leads.services.interest_core_chat_analysis import InterestCoreChatAnalysisService
from pur_leads.services.interest_core_items import InterestCoreItemService
from pur_leads.services.interest_core_briefs import (
    GENERATE_INTEREST_CORE_BRIEF_JOB,
    InterestCoreBriefService,
)
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_messages_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.audit import AuditService
from pur_leads.services.interest_context_preparation import (
    DEFAULT_PREPARE_EMBEDDING_PROFILE,
    PREPARE_INTEREST_CONTEXT_DATA_JOB,
)
from pur_leads.services.interest_contexts import (
    INTEREST_CONTEXT_SOURCE_PURPOSE,
    InterestContextDetail,
    InterestContextService,
)
from pur_leads.services.scheduler import SchedulerService
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


class InterestContextPrepareDataRequest(BaseModel):
    embedding_profile: str = DEFAULT_PREPARE_EMBEDDING_PROFILE


class InterestContextBuildDraftRequest(BaseModel):
    max_items: int = Field(default=1000, ge=1, le=5000)


class InterestCoreBriefManualRequest(BaseModel):
    brief_text: str = Field(min_length=1)
    title: str | None = None
    activate: bool = True


class InterestCoreBriefGenerateRequest(BaseModel):
    activate: bool = True
    agent_key: str = "catalog_extractor"
    route_role: str = "primary"
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class InterestCoreCandidateEnhanceRequest(BaseModel):
    max_items: int = Field(default=1000, ge=1, le=5000)
    candidate_chunk_size: int = Field(default=10, ge=1, le=50)
    parallelism: int | None = Field(default=None, ge=0, le=64)
    agent_key: str = "catalog_extractor"
    route_role: str = "primary"
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class InterestCoreCandidateReviewUpdateRequest(BaseModel):
    status: str = Field(pattern="^(pending_review|approved|rejected|applied)$")
    note: str | None = None


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


@router.get("/{context_id}/raw-review")
def get_interest_context_raw_review(
    context_id: str,
    limit: int = 50,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    context = service.repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    source_rows = (
        session.execute(
            select(monitored_sources_table)
            .where(monitored_sources_table.c.interest_context_id == context.id)
            .order_by(monitored_sources_table.c.created_at)
        )
        .mappings()
        .all()
    )
    source_ids = [str(row["id"]) for row in source_rows]
    raw_runs = _raw_runs_for_sources(session, source_ids)
    messages = _source_message_preview(session, source_ids, limit=max(1, min(limit, 200)))
    preview_source = "source_messages"
    if not messages:
        messages = _jsonl_message_preview(raw_runs, limit=max(1, min(limit, 200)))
        preview_source = "messages_jsonl"
    return jsonable_encoder(
        {
            "context": asdict(context),
            "summary": _raw_review_summary(session, source_ids, raw_runs),
            "sources": [dict(row) for row in source_rows],
            "raw_export_runs": [_raw_run_payload(row) for row in raw_runs],
            "messages": messages,
            "preview_source": preview_source,
        }
    )


@router.post("/{context_id}/prepare-data")
def prepare_interest_context_data(
    context_id: str,
    payload: InterestContextPrepareDataRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    context = service.repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    raw_runs = [
        row
        for row in _raw_runs_for_sources(
            session,
            [
                str(row["id"])
                for row in session.execute(
                    select(monitored_sources_table.c.id).where(
                        monitored_sources_table.c.interest_context_id == context.id
                    )
                )
                .mappings()
                .all()
            ],
        )
        if row.get("status") == "succeeded"
    ]
    if not raw_runs:
        raise HTTPException(status_code=400, detail="Сначала загрузите или соберите raw-данные")
    active_job = _active_prepare_job(session, context.id)
    if active_job is not None:
        return {"job": _row(active_job), "progress": _job_progress_from_row(active_job)}
    job = SchedulerService(session).enqueue(
        job_type=PREPARE_INTEREST_CONTEXT_DATA_JOB,
        scope_type="interest_context",
        scope_id=context.id,
        priority="normal",
        max_attempts=1,
        payload_json={
            "embedding_profile": payload.embedding_profile,
            "requested_by": _actor(validated),
            "raw_export_run_count": len(raw_runs),
        },
        checkpoint_before_json={
            "raw_export_run_ids": [row["id"] for row in raw_runs],
        },
    )
    return {"job": _job_payload(job), "progress": _job_progress(job)}


@router.get("/{context_id}/prepare-data/status")
def get_interest_context_prepare_data_status(
    context_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    job = _latest_prepare_job(session, context.id)
    return {
        "job": _row(job) if job else None,
        "progress": _job_progress_from_row(job) if job else _empty_prepare_progress(),
    }


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


@router.post("/{context_id}/analysis/telegram-archive")
async def upload_telegram_archive_for_interest_analysis(
    request: Request,
    context_id: str,
    file: UploadFile = File(...),
    display_name: str | None = Form(None),
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    context = service.repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    if InterestCoreItemService(session).item_count(context.id) <= 0:
        raise HTTPException(status_code=400, detail="Сначала сформируйте и примите рабочее ядро")

    safe_name = _safe_upload_filename(file.filename or "telegram-analysis.zip")
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
            interest_context_id=context.id,
            added_by=actor,
            sync_source_messages=True,
            import_metadata={
                "trace": trace,
                "upload": upload_metadata,
                "interest_context": {
                    "id": context.id,
                    "name": context.name,
                    "source_role": "interest_core_analysis",
                },
            },
        )
        analysis = InterestCoreChatAnalysisService(session).analyze_raw_export(
            context_id=context.id,
            monitored_source_id=result.source.id,
            raw_export_run_id=result.raw_export.run_id,
            actor=actor,
            source_title=result.source.title or input_ref or safe_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service.repository.update(context.id, updated_at=utc_now())
    session.commit()
    TraceService(session).record_child_span(
        span_name="interest_context.analysis.telegram_desktop_archive",
        status="ok",
        started_at=upload_started_at,
        resource_type="interest_context",
        resource_id=context.id,
        attributes_json={
            "monitored_source_id": result.source.id,
            "raw_export_run_id": result.raw_export.run_id,
            "analysis_run_id": analysis.get("run", {}).get("id") if analysis.get("run") else None,
            "message_count": result.message_count,
            "attachment_count": result.attachment_count,
            "match_count": analysis.get("summary", {}).get("match_count"),
            "stored_archive_path": str(stored_path),
            "sha256": sha256,
        },
    )
    AuditService(session).record_change(
        actor=actor,
        action="interest_context.analysis_archive_uploaded",
        entity_type="interest_context",
        entity_id=context.id,
        old_value_json=None,
        new_value_json={
            "monitored_source_id": result.source.id,
            "raw_export_run_id": result.raw_export.run_id,
            "analysis": analysis.get("summary"),
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
            "import_result": result.as_jsonable(),
            "analysis": analysis,
            "trace": trace,
        }
    )


@router.get("/{context_id}/analysis/runs")
def list_interest_core_analysis_runs(
    context_id: str,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(
        InterestCoreChatAnalysisService(session).latest_payload(
            context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.get("/{context_id}/analysis/runs/{run_id}/matches")
def list_interest_core_analysis_matches(
    context_id: str,
    run_id: str,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        payload = InterestCoreChatAnalysisService(session).list_matches(
            context_id=context.id,
            run_id=run_id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis run not found") from exc
    return jsonable_encoder(payload)


@router.post("/{context_id}/draft")
def build_interest_context_draft(
    context_id: str,
    payload: InterestContextBuildDraftRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = InterestContextService(session)
    context = service.repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    prepare_job = _latest_prepare_job(session, context.id)
    if prepare_job is None:
        raise HTTPException(status_code=400, detail="Сначала нажмите «Подготовить данные»")
    if prepare_job.get("status") in {"queued", "running"}:
        raise HTTPException(status_code=400, detail="Подготовка данных еще выполняется")
    if prepare_job.get("status") != "succeeded":
        raise HTTPException(
            status_code=400, detail="Последняя подготовка данных завершилась ошибкой"
        )
    active_job = _active_draft_job(session, context.id)
    if active_job is not None:
        return {
            "job": _row(active_job),
            "progress": _draft_progress_from_row(active_job),
            "draft": InterestContextDraftService(session).latest_payload(context.id),
        }
    job = SchedulerService(session).enqueue(
        job_type=BUILD_INTEREST_CONTEXT_DRAFT_JOB,
        scope_type="interest_context",
        scope_id=context.id,
        priority="normal",
        max_attempts=1,
        payload_json={
            "requested_by": _actor(validated),
            "max_items": payload.max_items,
            "uses_llm": False,
        },
    )
    return {
        "job": _job_payload(job),
        "progress": _draft_progress(job),
        "draft": InterestContextDraftService(session).latest_payload(context.id),
    }


@router.get("/{context_id}/draft/status")
def get_interest_context_draft_status(
    context_id: str,
    item_limit: int = 1000,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    job = _latest_draft_job(session, context.id)
    return {
        "job": _row(job) if job else None,
        "progress": _draft_progress_from_row(job) if job else _empty_draft_progress(),
        "draft": InterestContextDraftService(session).latest_payload(
            context.id,
            limit=max(0, min(item_limit, 1000)),
        ),
    }


@router.get("/{context_id}/draft/items")
def list_interest_context_draft_items(
    context_id: str,
    limit: int = 25,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(
        InterestContextDraftService(session).latest_items_payload(
            context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.post("/{context_id}/draft/enhance-llm")
def enhance_interest_context_draft_with_llm(
    context_id: str,
    payload: InterestCoreCandidateEnhanceRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    draft = InterestContextDraftService(session).latest_payload(context.id, limit=1)
    draft_run = draft.get("draft_run")
    if not draft_run:
        raise HTTPException(status_code=400, detail="Сначала сформируйте rule-based ядро")
    if draft_run.get("status") != "succeeded":
        raise HTTPException(status_code=400, detail="Последняя сборка ядра еще не готова")
    if InterestCoreBriefService(session).active_brief(context.id) is None:
        raise HTTPException(status_code=400, detail="Сначала создайте активный LLM-бриф")
    active_job = _active_candidate_enhancement_job(session, context.id)
    if active_job is not None:
        return {
            "job": _row(active_job),
            "progress": _candidate_enhancement_progress_from_row(active_job),
            "enhancement": _candidate_enhancement_payload(active_job),
            "reviews": InterestCoreCandidateReviewService(session).latest_payload(context.id),
        }
    job = SchedulerService(session).enqueue(
        job_type=ENHANCE_INTEREST_CORE_CANDIDATES_JOB,
        scope_type="interest_context",
        scope_id=context.id,
        priority="normal",
        max_attempts=2,
        payload_json={
            "requested_by": _actor(validated),
            "max_items": payload.max_items,
            "candidate_chunk_size": payload.candidate_chunk_size,
            "parallelism": payload.parallelism,
            "agent_key": payload.agent_key,
            "route_role": payload.route_role,
            "max_tokens": payload.max_tokens,
            "temperature": payload.temperature,
        },
        checkpoint_before_json={
            "draft_run_id": draft_run.get("id"),
        },
    )
    return {
        "job": _job_payload(job),
        "progress": _candidate_enhancement_progress(job),
        "enhancement": None,
        "reviews": InterestCoreCandidateReviewService(session).latest_payload(context.id),
    }


@router.get("/{context_id}/draft/enhance-llm/status")
def get_interest_context_draft_llm_enhancement_status(
    context_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    job = _latest_candidate_enhancement_job(session, context.id)
    review_payload = InterestCoreCandidateReviewService(session).latest_payload(context.id)
    return {
        "job": _row(job) if job else None,
        "progress": _candidate_enhancement_progress_from_row(job)
        if job
        else _empty_candidate_enhancement_progress(),
        "enhancement": _candidate_enhancement_payload(job) if job else None,
        "reviews": review_payload,
    }


@router.get("/{context_id}/candidate-reviews")
def list_interest_core_candidate_reviews(
    context_id: str,
    limit: int = 25,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(
        InterestCoreCandidateReviewService(session).latest_payload(
            context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.post("/{context_id}/candidate-reviews/approve-all")
def approve_all_interest_core_candidate_reviews(
    context_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        result = InterestCoreCandidateReviewService(session).approve_all_pending(
            context.id,
            actor=_actor(validated),
            note="bulk approve",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(
        {
            "result": result,
            "reviews": InterestCoreCandidateReviewService(session).latest_payload(context.id),
            "core_items": InterestCoreItemService(session).latest_payload(context.id),
        }
    )


@router.get("/{context_id}/core-items")
def list_interest_core_items(
    context_id: str,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(
        InterestCoreItemService(session).latest_payload(
            context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.patch("/{context_id}/candidate-reviews/{review_id}")
def update_interest_core_candidate_review(
    context_id: str,
    review_id: str,
    payload: InterestCoreCandidateReviewUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        review = InterestCoreCandidateReviewService(session).set_status(
            review_id,
            status=payload.status,
            actor=_actor(validated),
            note=payload.note,
            context_id=context.id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate review not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(
        {
            "review": review.as_jsonable(),
            "reviews": InterestCoreCandidateReviewService(session).latest_payload(context.id),
        }
    )


@router.get("/{context_id}/briefs")
def list_interest_core_briefs(
    context_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(InterestCoreBriefService(session).latest_payload(context.id))


@router.post("/{context_id}/briefs/manual")
def create_manual_interest_core_brief(
    context_id: str,
    payload: InterestCoreBriefManualRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if InterestContextService(session).repository.get(context_id) is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        record = InterestCoreBriefService(session).create_manual(
            context_id,
            brief_text=payload.brief_text,
            title=payload.title,
            actor=_actor(validated),
            activate=payload.activate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(
        {
            "brief": record.as_jsonable(),
            "briefs": InterestCoreBriefService(session).latest_payload(context_id),
        }
    )


@router.post("/{context_id}/briefs/generate")
def generate_interest_core_brief(
    context_id: str,
    payload: InterestCoreBriefGenerateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    prepare_job = _latest_prepare_job(session, context.id)
    if prepare_job is None:
        raise HTTPException(status_code=400, detail="Сначала нажмите «Подготовить данные»")
    if prepare_job.get("status") in {"queued", "running"}:
        raise HTTPException(status_code=400, detail="Подготовка данных еще выполняется")
    if prepare_job.get("status") != "succeeded":
        raise HTTPException(
            status_code=400, detail="Последняя подготовка данных завершилась ошибкой"
        )
    active_job = _active_core_brief_job(session, context.id)
    if active_job is not None:
        return {
            "job": _row(active_job),
            "progress": _core_brief_progress_from_row(active_job),
            "briefs": InterestCoreBriefService(session).latest_payload(context.id),
        }
    job = SchedulerService(session).enqueue(
        job_type=GENERATE_INTEREST_CORE_BRIEF_JOB,
        scope_type="interest_context",
        scope_id=context.id,
        priority="normal",
        max_attempts=2,
        payload_json={
            "requested_by": _actor(validated),
            "activate": payload.activate,
            "agent_key": payload.agent_key,
            "route_role": payload.route_role,
            "max_tokens": payload.max_tokens,
            "temperature": payload.temperature,
        },
    )
    return {
        "job": _job_payload(job),
        "progress": _core_brief_progress(job),
        "briefs": InterestCoreBriefService(session).latest_payload(context.id),
    }


@router.get("/{context_id}/briefs/generate/status")
def get_interest_core_brief_generation_status(
    context_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    job = _latest_core_brief_job(session, context.id)
    return {
        "job": _row(job) if job else None,
        "progress": _core_brief_progress_from_row(job) if job else _empty_core_brief_progress(),
        "briefs": InterestCoreBriefService(session).latest_payload(context.id),
    }


@router.post("/{context_id}/briefs/{brief_id}/activate")
def activate_interest_core_brief(
    context_id: str,
    brief_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if InterestContextService(session).repository.get(context_id) is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        record = InterestCoreBriefService(session).activate(
            context_id,
            brief_id,
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interest core brief not found") from exc
    return jsonable_encoder(
        {
            "brief": record.as_jsonable(),
            "briefs": InterestCoreBriefService(session).latest_payload(context_id),
        }
    )


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


def _raw_runs_for_sources(session: Session, source_ids: list[str]) -> list[dict[str, Any]]:
    if not source_ids:
        return []
    return [
        dict(row)
        for row in session.execute(
            select(telegram_raw_export_runs_table)
            .where(telegram_raw_export_runs_table.c.monitored_source_id.in_(source_ids))
            .order_by(desc(telegram_raw_export_runs_table.c.started_at))
        )
        .mappings()
        .all()
    ]


def _latest_prepare_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == PREPARE_INTEREST_CONTEXT_DATA_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _active_prepare_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == PREPARE_INTEREST_CONTEXT_DATA_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .where(scheduler_jobs_table.c.status.in_(["queued", "running"]))
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _latest_draft_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == BUILD_INTEREST_CONTEXT_DRAFT_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _active_draft_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == BUILD_INTEREST_CONTEXT_DRAFT_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .where(scheduler_jobs_table.c.status.in_(["queued", "running"]))
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _latest_core_brief_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == GENERATE_INTEREST_CORE_BRIEF_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _active_core_brief_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == GENERATE_INTEREST_CORE_BRIEF_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .where(scheduler_jobs_table.c.status.in_(["queued", "running"]))
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _latest_candidate_enhancement_job(session: Session, context_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == ENHANCE_INTEREST_CORE_CANDIDATES_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _active_candidate_enhancement_job(
    session: Session, context_id: str
) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.job_type == ENHANCE_INTEREST_CORE_CANDIDATES_JOB)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context_id)
            .where(scheduler_jobs_table.c.status.in_(["queued", "running"]))
            .order_by(desc(scheduler_jobs_table.c.created_at))
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _job_payload(job: Any) -> dict[str, Any]:
    return asdict(job) if hasattr(job, "__dataclass_fields__") else dict(job)


def _job_progress(job: Any) -> dict[str, Any]:
    return _job_progress_from_row(_job_payload(job))


def _job_progress_from_row(job: dict[str, Any] | None) -> dict[str, Any]:
    if not job:
        return _empty_prepare_progress()
    progress = job.get("result_summary_json")
    if isinstance(progress, dict) and progress.get("kind") == "interest_context_data_preparation":
        return progress
    if job.get("status") == "succeeded" and isinstance(progress, dict):
        return {
            "kind": "interest_context_data_preparation",
            "status": "succeeded",
            "current_stage": "done",
            "current_stage_label": "Готово",
            "overall_percent": 100,
            "stage_percent": 100,
            "message": "Данные подготовлены",
            "stage_results": progress.get("stage_results", []),
            "raw_export_run_count": progress.get("raw_export_run_count", 0),
            "total_steps": progress.get("total_steps", 0),
            "completed_steps": progress.get("completed_steps", 0),
        }
    status = str(job.get("status") or "unknown")
    return {
        "kind": "interest_context_data_preparation",
        "status": status,
        "current_stage": None,
        "current_stage_label": "В очереди" if status == "queued" else status,
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Задача ожидает воркер"
        if status == "queued"
        else job.get("last_error") or status,
        "stage_results": [],
        "raw_export_run_count": (job.get("payload_json") or {}).get("raw_export_run_count", 0)
        if isinstance(job.get("payload_json"), dict)
        else 0,
    }


def _empty_prepare_progress() -> dict[str, Any]:
    return {
        "kind": "interest_context_data_preparation",
        "status": "not_started",
        "current_stage": None,
        "current_stage_label": "Не запускалось",
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Подготовка данных еще не запускалась",
        "stage_results": [],
        "raw_export_run_count": 0,
    }


def _draft_progress(job: Any) -> dict[str, Any]:
    return _draft_progress_from_row(_job_payload(job))


def _draft_progress_from_row(job: dict[str, Any] | None) -> dict[str, Any]:
    if not job:
        return _empty_draft_progress()
    progress = job.get("result_summary_json")
    if isinstance(progress, dict) and progress.get("kind") == "interest_context_draft_build":
        return progress
    if job.get("status") == "succeeded" and isinstance(progress, dict):
        return {
            "kind": "interest_context_draft_build",
            "status": "succeeded",
            "current_stage": "done",
            "current_stage_label": "Готово",
            "overall_percent": 100,
            "stage_percent": 100,
            "message": f"Черновик собран: {progress.get('candidate_count', 0)} кандидатов",
            "stage_results": progress.get("stage_results", []),
            "raw_export_run_count": progress.get("raw_export_run_count", 0),
            "candidate_count": progress.get("candidate_count", 0),
            "total_steps": progress.get("total_steps", 0),
            "completed_steps": progress.get("completed_steps", 0),
            "draft_run_id": progress.get("draft_run_id"),
        }
    status = str(job.get("status") or "unknown")
    return {
        "kind": "interest_context_draft_build",
        "status": status,
        "current_stage": None,
        "current_stage_label": "В очереди" if status == "queued" else status,
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Задача ожидает воркер"
        if status == "queued"
        else job.get("last_error") or status,
        "stage_results": [],
        "raw_export_run_count": 0,
        "candidate_count": 0,
    }


def _empty_draft_progress() -> dict[str, Any]:
    return {
        "kind": "interest_context_draft_build",
        "status": "not_started",
        "current_stage": None,
        "current_stage_label": "Не запускалось",
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Черновик ядра еще не собирался",
        "stage_results": [],
        "raw_export_run_count": 0,
        "candidate_count": 0,
    }


def _core_brief_progress(job: Any) -> dict[str, Any]:
    return _core_brief_progress_from_row(_job_payload(job))


def _core_brief_progress_from_row(job: dict[str, Any] | None) -> dict[str, Any]:
    if not job:
        return _empty_core_brief_progress()
    progress = job.get("result_summary_json")
    if isinstance(progress, dict) and progress.get("kind") == "interest_core_brief_generation":
        return _progress_with_actual_job_status(job, progress)
    if job.get("status") == "succeeded" and isinstance(progress, dict):
        return {
            "kind": "interest_core_brief_generation",
            "status": "succeeded",
            "current_stage": "done",
            "current_stage_label": "Готово",
            "overall_percent": 100,
            "stage_percent": 100,
            "message": progress.get("message") or "Бриф сформирован",
            "brief_id": progress.get("brief_id"),
            "version": progress.get("version"),
            "model": progress.get("model"),
            "model_profile": progress.get("model_profile"),
        }
    status = str(job.get("status") or "unknown")
    return {
        "kind": "interest_core_brief_generation",
        "status": status,
        "current_stage": None,
        "current_stage_label": "В очереди" if status == "queued" else status,
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Задача ожидает воркер"
        if status == "queued"
        else job.get("last_error") or status,
        "brief_id": None,
        "version": None,
    }


def _empty_core_brief_progress() -> dict[str, Any]:
    return {
        "kind": "interest_core_brief_generation",
        "status": "not_started",
        "current_stage": None,
        "current_stage_label": "Не запускалось",
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "LLM-бриф ядра еще не формировался",
        "brief_id": None,
        "version": None,
    }


def _candidate_enhancement_progress(job: Any) -> dict[str, Any]:
    return _candidate_enhancement_progress_from_row(_job_payload(job))


def _candidate_enhancement_progress_from_row(job: dict[str, Any] | None) -> dict[str, Any]:
    if not job:
        return _empty_candidate_enhancement_progress()
    progress = job.get("result_summary_json")
    if isinstance(progress, dict) and progress.get("kind") == "interest_core_candidate_enhancement":
        return _progress_with_actual_job_status(job, progress)
    if job.get("status") == "succeeded" and isinstance(progress, dict):
        return {
            "kind": "interest_core_candidate_enhancement",
            "status": "succeeded",
            "current_stage": "done",
            "current_stage_label": "Готово",
            "overall_percent": 100,
            "stage_percent": 100,
            "message": progress.get("message") or "LLM-рекомендации готовы",
            "candidate_count": progress.get("candidate_count", 0),
            "improved_count": progress.get("improved_count", 0),
            "new_count": progress.get("new_count", 0),
            "rejected_count": progress.get("rejected_count", 0),
            "failed_chunk_count": progress.get("failed_chunk_count", 0),
            "chunk_index": progress.get("chunk_count", 0),
            "chunk_count": progress.get("chunk_count", 0),
            "completed_chunk_count": progress.get("chunk_count", 0),
            "active_parallelism": progress.get("active_parallelism"),
            "configured_parallelism": progress.get("configured_parallelism"),
            "model": progress.get("model"),
            "model_profile": progress.get("model_profile"),
        }
    status = str(job.get("status") or "unknown")
    return {
        "kind": "interest_core_candidate_enhancement",
        "status": status,
        "current_stage": None,
        "current_stage_label": "В очереди" if status == "queued" else status,
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Задача ожидает воркер"
        if status == "queued"
        else job.get("last_error") or status,
        "candidate_count": (job.get("payload_json") or {}).get("max_items", 0)
        if isinstance(job.get("payload_json"), dict)
        else 0,
        "improved_count": 0,
        "new_count": 0,
        "rejected_count": 0,
    }


def _empty_candidate_enhancement_progress() -> dict[str, Any]:
    return {
        "kind": "interest_core_candidate_enhancement",
        "status": "not_started",
        "current_stage": None,
        "current_stage_label": "Не запускалось",
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "LLM-улучшение кандидатов еще не запускалось",
        "candidate_count": 0,
        "improved_count": 0,
        "new_count": 0,
        "rejected_count": 0,
    }


def _candidate_enhancement_payload(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    progress = job.get("result_summary_json")
    if not isinstance(progress, dict):
        return None
    if progress.get("kind") != "interest_core_candidate_enhancement":
        return None
    if progress.get("status") != "succeeded":
        return None
    return progress


def _progress_with_actual_job_status(
    job: dict[str, Any],
    progress: dict[str, Any],
) -> dict[str, Any]:
    job_status = str(job.get("status") or "")
    progress_status = str(progress.get("status") or "")
    if job_status == "failed" and progress_status != "failed":
        return {
            **progress,
            "status": "failed",
            "current_stage_label": "Ошибка",
            "overall_percent": progress.get("overall_percent", 0),
            "stage_percent": progress.get("stage_percent", 0),
            "message": (
                job.get("last_error")
                or progress.get("message")
                or "Задача завершилась ошибкой"
            ),
        }
    if job_status == "succeeded" and progress_status != "succeeded":
        return {
            **progress,
            "status": "succeeded",
            "current_stage": "done",
            "current_stage_label": "Готово",
            "overall_percent": 100,
            "stage_percent": 100,
        }
    return progress


def _row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _raw_review_summary(
    session: Session,
    source_ids: list[str],
    raw_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not source_ids:
        return {
            "source_count": 0,
            "raw_export_run_count": 0,
            "raw_message_count": 0,
            "raw_attachment_count": 0,
            "source_message_count": 0,
            "date_from": None,
            "date_to": None,
            "failed_run_count": 0,
            "missing_file_count": 0,
        }
    source_message_stats = (
        session.execute(
            select(
                func.count(source_messages_table.c.id).label("message_count"),
                func.min(source_messages_table.c.message_date).label("date_from"),
                func.max(source_messages_table.c.message_date).label("date_to"),
            ).where(source_messages_table.c.monitored_source_id.in_(source_ids))
        )
        .mappings()
        .one()
    )
    files = [file for row in raw_runs for file in _raw_run_files(row)]
    return {
        "source_count": len(source_ids),
        "raw_export_run_count": len(raw_runs),
        "raw_message_count": sum(int(row.get("message_count") or 0) for row in raw_runs),
        "raw_attachment_count": sum(int(row.get("attachment_count") or 0) for row in raw_runs),
        "source_message_count": int(source_message_stats["message_count"] or 0),
        "date_from": source_message_stats["date_from"],
        "date_to": source_message_stats["date_to"],
        "failed_run_count": sum(1 for row in raw_runs if row.get("status") == "failed"),
        "missing_file_count": sum(1 for file in files if not file["exists"]),
    }


def _raw_run_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "files": _raw_run_files(row),
        "sync_source_messages": bool(
            ((row.get("metadata_json") or {}).get("desktop_import") or {}).get(
                "sync_source_messages"
            )
        ),
    }


def _raw_run_files(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _file_payload("result_json", row.get("result_json_path")),
        _file_payload("messages_jsonl", row.get("messages_jsonl_path")),
        _file_payload("attachments_jsonl", row.get("attachments_jsonl_path")),
        _file_payload("messages_parquet", row.get("messages_parquet_path")),
        _file_payload("attachments_parquet", row.get("attachments_parquet_path")),
        _file_payload("manifest", row.get("manifest_path")),
    ]


def _file_payload(kind: str, path_raw: str | None) -> dict[str, Any]:
    path = Path(path_raw) if path_raw else None
    exists = bool(path and path.exists())
    return {
        "kind": kind,
        "path": str(path) if path else None,
        "exists": exists,
        "size_bytes": path.stat().st_size if exists and path.is_file() else None,
    }


def _source_message_preview(
    session: Session,
    source_ids: list[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not source_ids:
        return []
    rows = (
        session.execute(
            select(source_messages_table)
            .where(source_messages_table.c.monitored_source_id.in_(source_ids))
            .order_by(
                desc(source_messages_table.c.message_date),
                desc(source_messages_table.c.telegram_message_id),
            )
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": row["id"],
            "source": "source_messages",
            "monitored_source_id": row["monitored_source_id"],
            "telegram_message_id": row["telegram_message_id"],
            "sender_id": row["sender_id"],
            "message_date": row["message_date"],
            "text": _message_excerpt(row["text"], row["caption"]),
            "has_media": row["has_media"],
            "reply_to_message_id": row["reply_to_message_id"],
            "classification_status": row["classification_status"],
            "archive_pointer_id": row["archive_pointer_id"],
        }
        for row in rows
    ]


def _jsonl_message_preview(raw_runs: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for run in raw_runs:
        path_raw = run.get("messages_jsonl_path")
        if not path_raw:
            continue
        path = Path(path_raw)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if len(messages) >= limit:
                    return messages
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if raw.get("type") != "message":
                    continue
                messages.append(
                    {
                        "id": f"{run['id']}:{raw.get('id')}",
                        "source": "messages_jsonl",
                        "monitored_source_id": run.get("monitored_source_id"),
                        "telegram_message_id": raw.get("id"),
                        "sender_id": raw.get("from_id"),
                        "message_date": raw.get("date"),
                        "text": _message_excerpt(
                            _telegram_text(raw.get("text")), raw.get("caption")
                        ),
                        "has_media": bool(raw.get("raw_media_json") or raw.get("media_type")),
                        "reply_to_message_id": raw.get("reply_to_message_id"),
                        "classification_status": None,
                        "archive_pointer_id": run.get("id"),
                    }
                )
    return messages


def _telegram_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts) if parts else None
    return None


def _message_excerpt(text: Any, caption: Any) -> str:
    raw = text if isinstance(text, str) and text else caption if isinstance(caption, str) else ""
    normalized = " ".join(raw.split())
    return normalized[:700]


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id
