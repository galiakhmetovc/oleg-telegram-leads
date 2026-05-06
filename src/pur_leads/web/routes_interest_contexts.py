"""Interest context web/API routes."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import re
from typing import Any
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from pur_leads.core.config import load_settings
from pur_leads.core.time import utc_now
from pur_leads.core.tracing import current_trace_json
from pur_leads.models.interest_context_drafts import (
    interest_intent_analysis_runs_table,
    interest_intent_analysis_matches_table,
    interest_intent_layers_table,
    interest_intent_validation_runs_table,
)
from pur_leads.models.leads import feedback_events_table
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
from pur_leads.services.interest_intent_layers import InterestIntentLayerService
from pur_leads.services.interest_intent_validation import (
    REVIEW_ACTIONS,
    InterestIntentValidationService,
)
from pur_leads.services.ai_chat_clients import build_zai_chat_client_for_route, select_ai_route
from pur_leads.services.interest_core_briefs import (
    GENERATE_INTEREST_CORE_BRIEF_JOB,
    InterestCoreBriefService,
)
from pur_leads.services.leads import LeadService
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_messages_table,
    telegram_entity_candidates_table,
    telegram_prepared_documents_table,
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
from pur_leads.services.telegram_desktop_import import IMPORT_TELEGRAM_DESKTOP_ARCHIVE_JOB
from pur_leads.services.telegram_analysis_storage import (
    feature_rows as telegram_feature_rows,
    stage_outputs,
)
from pur_leads.services.telegram_search import TelegramSearchService
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


class InterestIntentLayerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    include_patterns: list[str] = []
    context_patterns: list[str] = []
    exclude_patterns: list[str] = []
    exclude_lemmas: list[str] = []
    exclude_phrases: list[str] = []
    semantic_negative_examples: list[str] = []
    semantic_negative_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    include_categories: list[str] = []
    exclude_categories: list[str] = []
    include_core_names: list[str] = []
    exclude_core_names: list[str] = []
    require_include_match: bool = True
    require_context_match: bool = False
    min_score: float = Field(default=0.55, ge=0.0, le=1.0)
    max_results: int = Field(default=3000, ge=1, le=20000)
    broad_score_weight: float = Field(default=0.45, ge=0.0, le=1.0)
    intent_hit_weight: float = Field(default=0.18, ge=0.0, le=1.0)


class InterestIntentLayerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    include_patterns: list[str] | None = None
    context_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    exclude_lemmas: list[str] | None = None
    exclude_phrases: list[str] | None = None
    semantic_negative_examples: list[str] | None = None
    semantic_negative_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    include_categories: list[str] | None = None
    exclude_categories: list[str] | None = None
    include_core_names: list[str] | None = None
    exclude_core_names: list[str] | None = None
    require_include_match: bool | None = None
    require_context_match: bool | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_results: int | None = Field(default=None, ge=1, le=20000)
    broad_score_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    intent_hit_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str | None = Field(default=None, pattern="^(active|disabled|archived)$")


class InterestIntentLayerRunRequest(BaseModel):
    broad_analysis_run_id: str = Field(min_length=1)


class InterestIntentExclusionApplyRequest(BaseModel):
    term: str = Field(min_length=1, max_length=200)


class InterestIntentMatchReviewRequest(BaseModel):
    decision: str = Field(pattern="^(correct|incorrect)$")
    comment: str | None = Field(default=None, max_length=2000)


class InterestIntentValidationRunRequest(BaseModel):
    agent_key: str = "catalog_extractor"
    route_role: str = "primary"
    max_reviews: int = Field(default=80, ge=1, le=500)
    review_offset: int = Field(default=0, ge=0)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class InterestIntentValidationRecommendationUpdateRequest(BaseModel):
    status: str = Field(pattern="^(pending_review|approved|rejected)$")
    note: str | None = Field(default=None, max_length=2000)


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


@router.get("/{context_id}/prepare-data/runs")
def list_interest_context_prepared_runs(
    context_id: str,
    metadata_key: str = "text_normalization",
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return {
        "metadata_key": metadata_key,
        "raw_runs": _prepared_raw_runs_payload(session, context.id, metadata_key),
    }


@router.get("/{context_id}/prepare-data/texts")
def list_interest_context_prepared_texts(
    context_id: str,
    raw_export_run_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="text_normalization", raw_export_run_id=raw_export_run_id
    )
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    base = select(telegram_prepared_documents_table).where(
        telegram_prepared_documents_table.c.raw_export_run_id == run["id"]
    )
    total = int(session.execute(select(func.count()).select_from(base.subquery())).scalar_one() or 0)
    rows = (
        session.execute(
            base.order_by(
                telegram_prepared_documents_table.c.entity_type,
                telegram_prepared_documents_table.c.telegram_message_id,
                telegram_prepared_documents_table.c.chunk_index,
            )
            .limit(safe_limit)
            .offset(safe_offset)
        )
        .mappings()
        .all()
    )
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "text_normalization"),
            "items": [_prepared_text_payload(dict(row)) for row in rows],
            "summary": _prepared_documents_summary(session, str(run["id"])),
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
        }
    )


@router.get("/{context_id}/prepare-data/features")
def list_interest_context_prepared_features(
    context_id: str,
    raw_export_run_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="feature_enrichment", raw_export_run_id=raw_export_run_id
    )
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    base = (
        select(telegram_prepared_documents_table)
        .where(telegram_prepared_documents_table.c.raw_export_run_id == run["id"])
        .where(telegram_prepared_documents_table.c.feature_json.is_not(None))
    )
    total = int(session.execute(select(func.count()).select_from(base.subquery())).scalar_one() or 0)
    rows = (
        session.execute(
            base.order_by(
                telegram_prepared_documents_table.c.entity_type,
                telegram_prepared_documents_table.c.telegram_message_id,
                telegram_prepared_documents_table.c.chunk_index,
            )
            .limit(safe_limit)
            .offset(safe_offset)
        )
        .mappings()
        .all()
    )
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "feature_enrichment"),
            "artifact": {
                "kind": "postgres_table",
                "table": "telegram_prepared_documents",
                "column": "feature_json",
            },
            "items": [_feature_payload(dict(row)) for row in rows],
            "pagination": _pagination(limit=safe_limit, offset=safe_offset, total=total),
            "columns": ["feature_json"],
        }
    )


@router.get("/{context_id}/prepare-data/aggregates")
def get_interest_context_prepared_aggregates(
    context_id: str,
    raw_export_run_id: str | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="aggregated_stats", raw_export_run_id=raw_export_run_id
    )
    outputs = stage_outputs(session, str(run["id"]), "aggregated_stats")
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "aggregated_stats"),
            "summary": _stage_payload(outputs, "summary"),
            "ngrams": _stage_payload(outputs, "ngrams"),
            "entity_candidates": _stage_payload(outputs, "entity_candidates"),
            "urls": _stage_payload(outputs, "urls"),
            "source_quality": _stage_payload(outputs, "source_quality"),
        }
    )


@router.get("/{context_id}/prepare-data/aggregates/ngrams")
def list_interest_context_prepared_ngrams(
    context_id: str,
    raw_export_run_id: str | None = None,
    kind: str = "lemmas",
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="aggregated_stats", raw_export_run_id=raw_export_run_id
    )
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    payload = _ngram_page_payload(
        session,
        str(run["id"]),
        kind=kind,
        limit=safe_limit,
        offset=safe_offset,
    )
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "aggregated_stats"),
            **payload,
        }
    )


@router.get("/{context_id}/prepare-data/entities")
def list_interest_context_prepared_entities(
    context_id: str,
    raw_export_run_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="entity_ranking", raw_export_run_id=raw_export_run_id
    )
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    extracted = _entity_rows_page(
        session,
        str(run["id"]),
        limit=safe_limit,
        offset=safe_offset,
        ranked=False,
    )
    ranked = _entity_rows_page(
        session,
        str(run["id"]),
        limit=safe_limit,
        offset=safe_offset,
        ranked=True,
    )
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "entity_ranking"),
            "ranked_artifact": {"kind": "postgres_table", "table": "telegram_entity_candidates"},
            "extracted_artifact": {"kind": "postgres_table", "table": "telegram_entity_candidates"},
            "rules": _entity_extraction_rules_payload(),
            "ranked": ranked,
            "extracted": extracted,
        }
    )


@router.get("/{context_id}/prepare-data/search/fts")
def search_interest_context_prepared_fts(
    context_id: str,
    q: str,
    raw_export_run_id: str | None = None,
    limit: int = 10,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="fts_index", raw_export_run_id=raw_export_run_id
    )
    payload = TelegramSearchService(session).query(
        str(run["id"]),
        query_text=q,
        limit=max(1, min(limit, 50)),
        include_fts=True,
        include_chroma=False,
    )
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "fts_index"),
            "search_explanation": {
                "storage": "telegram_prepared_documents.search_vector",
                "query_normalization": "pymorphy3 lemmas + PostgreSQL to_tsquery(simple, term:*)",
                "ranking": "ts_rank_cd + rarity score",
            },
            **payload,
        }
    )


@router.get("/{context_id}/prepare-data/search/chroma")
def search_interest_context_prepared_chroma(
    context_id: str,
    q: str,
    raw_export_run_id: str | None = None,
    limit: int = 10,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _prepared_raw_run(
        session, context_id, metadata_key="chroma_index", raw_export_run_id=raw_export_run_id
    )
    payload = TelegramSearchService(session).query(
        str(run["id"]),
        query_text=q,
        limit=max(1, min(limit, 50)),
        include_fts=False,
        include_chroma=True,
    )
    return jsonable_encoder(
        {
            "raw_export_run": _raw_run_payload(run),
            "raw_runs": _prepared_raw_runs_payload(session, context_id, "chroma_index"),
            "search_explanation": {
                "storage": "Chroma persistent collection for выбранный raw-run",
                "query_normalization": "raw query + pymorphy3 lemmas",
                "embedding_profile": "из metadata raw-run, обычно rubert_tiny2_v1 или local_hashing_v1",
            },
            **payload,
        }
    )


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

    import_metadata = {
        "trace": trace,
        "upload": upload_metadata,
        "interest_context": {
            "id": context.id,
            "name": context.name,
            "source_role": INTEREST_CONTEXT_SOURCE_PURPOSE,
        },
    }
    job = SchedulerService(session).enqueue(
        job_type=IMPORT_TELEGRAM_DESKTOP_ARCHIVE_JOB,
        scope_type="interest_context",
        scope_id=context.id,
        priority="normal",
        max_attempts=1,
        idempotency_key=f"telegram-desktop-archive-import:{context.id}:{sha256}",
        payload_json={
            "mode": "interest_context_source",
            "stored_archive_path": str(stored_path),
            "original_filename": safe_name,
            "content_type": file.content_type,
            "display_name": input_ref,
            "sync_source_messages": sync_source_messages,
            "requested_by": actor,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "import_metadata": import_metadata,
        },
    )
    service.repository.update(context.id, updated_at=utc_now())
    session.commit()
    TraceService(session).record_child_span(
        span_name="interest_context.queue.telegram_desktop_archive_import",
        status="ok",
        started_at=upload_started_at,
        resource_type="interest_context",
        resource_id=context.id,
        attributes_json={
            "scheduler_job_id": job.id,
            "stored_archive_path": str(stored_path),
            "sha256": sha256,
            "size_bytes": size_bytes,
        },
    )
    AuditService(session).record_change(
        actor=actor,
        action="interest_context.telegram_archive_import_queued",
        entity_type="interest_context",
        entity_id=context.id,
        old_value_json=None,
        new_value_json={
            "scheduler_job_id": job.id,
            "stored_archive_path": str(stored_path),
            "size_bytes": size_bytes,
        },
    )
    return jsonable_encoder(
        {
            "mode": "async",
            "job": _job_payload(job),
            "progress": _archive_import_progress(job),
            "upload": upload_metadata,
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

    import_metadata = {
        "trace": trace,
        "upload": upload_metadata,
        "interest_context": {
            "id": context.id,
            "name": context.name,
            "source_role": "interest_core_analysis",
        },
    }
    job = SchedulerService(session).enqueue(
        job_type=IMPORT_TELEGRAM_DESKTOP_ARCHIVE_JOB,
        scope_type="interest_context",
        scope_id=context.id,
        priority="normal",
        max_attempts=1,
        idempotency_key=f"telegram-desktop-archive-analysis:{context.id}:{sha256}",
        payload_json={
            "mode": "interest_core_analysis",
            "stored_archive_path": str(stored_path),
            "original_filename": safe_name,
            "content_type": file.content_type,
            "display_name": input_ref,
            "sync_source_messages": True,
            "requested_by": actor,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "import_metadata": import_metadata,
        },
    )
    service.repository.update(context.id, updated_at=utc_now())
    session.commit()
    TraceService(session).record_child_span(
        span_name="interest_context.queue.analysis_telegram_desktop_archive",
        status="ok",
        started_at=upload_started_at,
        resource_type="interest_context",
        resource_id=context.id,
        attributes_json={
            "scheduler_job_id": job.id,
            "stored_archive_path": str(stored_path),
            "sha256": sha256,
            "size_bytes": size_bytes,
        },
    )
    AuditService(session).record_change(
        actor=actor,
        action="interest_context.analysis_archive_import_queued",
        entity_type="interest_context",
        entity_id=context.id,
        old_value_json=None,
        new_value_json={
            "scheduler_job_id": job.id,
            "stored_archive_path": str(stored_path),
            "size_bytes": size_bytes,
        },
    )
    return jsonable_encoder(
        {
            "mode": "async",
            "job": _job_payload(job),
            "progress": _archive_import_progress(job),
            "upload": upload_metadata,
            "trace": trace,
        }
    )


@router.get("/{context_id}/telegram-archive/import-jobs/{job_id}")
def get_interest_context_telegram_archive_import_job(
    context_id: str,
    job_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    row = (
        session.execute(
            select(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == job_id)
            .where(scheduler_jobs_table.c.scope_type == "interest_context")
            .where(scheduler_jobs_table.c.scope_id == context.id)
            .where(scheduler_jobs_table.c.job_type == IMPORT_TELEGRAM_DESKTOP_ARCHIVE_JOB)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    job = dict(row)
    return jsonable_encoder({"job": job, "progress": _archive_import_progress_from_row(job)})


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


@router.get("/{context_id}/intent-layers")
def list_interest_intent_layers(
    context_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(
        InterestIntentLayerService(session).list_layers(context.id, actor=_actor(validated))
    )


@router.post("/{context_id}/intent-layers")
def create_interest_intent_layer(
    context_id: str,
    payload: InterestIntentLayerRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        layer = InterestIntentLayerService(session).create_layer(
            context_id=context.id,
            name=payload.name,
            description=payload.description,
            actor=_actor(validated),
            include_patterns=payload.include_patterns,
            context_patterns=payload.context_patterns,
            exclude_patterns=payload.exclude_patterns,
            exclude_lemmas=payload.exclude_lemmas,
            exclude_phrases=payload.exclude_phrases,
            semantic_negative_examples=payload.semantic_negative_examples,
            semantic_negative_threshold=payload.semantic_negative_threshold,
            include_categories=payload.include_categories,
            exclude_categories=payload.exclude_categories,
            include_core_names=payload.include_core_names,
            exclude_core_names=payload.exclude_core_names,
            require_include_match=payload.require_include_match,
            require_context_match=payload.require_context_match,
            min_score=payload.min_score,
            max_results=payload.max_results,
            broad_score_weight=payload.broad_score_weight,
            intent_hit_weight=payload.intent_hit_weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder({"layer": layer.as_jsonable()})


@router.patch("/{context_id}/intent-layers/{layer_id}")
def update_interest_intent_layer(
    context_id: str,
    layer_id: str,
    payload: InterestIntentLayerUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    values = payload.model_dump(exclude_unset=True)
    try:
        layer = InterestIntentLayerService(session).update_layer(
            layer_id,
            context_id=context.id,
            actor=_actor(validated),
            values=values,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent layer not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder({"layer": layer.as_jsonable()})


@router.delete("/{context_id}/intent-layers/{layer_id}")
def archive_interest_intent_layer(
    context_id: str,
    layer_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        InterestIntentLayerService(session).archive_layer(
            layer_id,
            context_id=context.id,
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent layer not found") from exc
    return {"ok": True}


@router.post("/{context_id}/intent-layers/{layer_id}/runs")
def run_interest_intent_layer(
    context_id: str,
    layer_id: str,
    payload: InterestIntentLayerRunRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        result = InterestIntentLayerService(session).run_layer(
            context_id=context.id,
            layer_id=layer_id,
            broad_analysis_run_id=payload.broad_analysis_run_id,
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent layer or broad run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(result)


@router.get("/{context_id}/intent-runs")
def list_interest_intent_runs(
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
        InterestIntentLayerService(session).latest_runs_payload(
            context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.get("/{context_id}/intent-runs/{run_id}/matches")
def list_interest_intent_matches(
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
        payload = InterestIntentLayerService(session).list_matches(
            context_id=context.id,
            run_id=run_id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent run not found") from exc
    return jsonable_encoder(payload)


@router.post("/{context_id}/intent-runs/{run_id}/matches/{match_id}/review")
def review_interest_intent_match(
    context_id: str,
    run_id: str,
    match_id: str,
    payload: InterestIntentMatchReviewRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    target = _intent_match_row(session, context_id=context.id, run_id=run_id, match_id=match_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Intent match not found")
    actor = _actor(validated)
    session.execute(
        update(feedback_events_table)
        .where(feedback_events_table.c.target_type == "interest_intent_match")
        .where(feedback_events_table.c.target_id == match_id)
        .where(feedback_events_table.c.action.in_(list(REVIEW_ACTIONS.values())))
        .where(feedback_events_table.c.application_status != "ignored")
        .values(
            application_status="ignored",
            metadata_json={
                "superseded_by_review": {
                    "decision": payload.decision,
                    "actor": actor,
                    "at": utc_now().isoformat(),
                }
            },
        )
    )
    action = REVIEW_ACTIONS[payload.decision]
    feedback = LeadService(session).record_feedback(
        target_type="interest_intent_match",
        target_id=match_id,
        action=action,
        reason_code=f"operator_{payload.decision}",
        feedback_scope="classifier",
        learning_effect="positive_example" if payload.decision == "correct" else "negative_example",
        application_status="recorded",
        comment=payload.comment,
        metadata_json={
            "context_id": context.id,
            "intent_run_id": run_id,
            "intent_match_id": match_id,
            "review_decision": payload.decision,
        },
        created_by=actor,
    )
    return {"review": jsonable_encoder(feedback)}


@router.get("/{context_id}/intent-runs/{run_id}/matches/{match_id}/exclude-preview")
def preview_interest_intent_exclusion(
    context_id: str,
    run_id: str,
    match_id: str,
    term: str | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    target = _intent_match_row(session, context_id=context_id, run_id=run_id, match_id=match_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Intent match not found")
    suggestions = _intent_exclusion_suggestions(str(target["message_text"] or ""))
    preview_term = str(term or (suggestions[0] if suggestions else "")).strip()
    rows = _intent_match_rows_for_run(session, context_id=context_id, run_id=run_id)
    removed = [
        row
        for row in rows
        if preview_term and _plain_term_hits(preview_term, str(row["message_text"] or ""))
    ]
    return jsonable_encoder(
        {
            "match_id": match_id,
            "run_id": run_id,
            "suggestions": suggestions,
            "term": preview_term,
            "total_matches": len(rows),
            "removed_count": len(removed),
            "remaining_count": max(0, len(rows) - len(removed)),
            "target_removed": any(str(row["id"]) == match_id for row in removed),
            "removed_samples": [_intent_preview_payload(row) for row in removed[:10]],
            "explanation": (
                "Preview считает, сколько текущих сообщений слоя намерений исчезнет, "
                "если добавить этот plain-text/lemma exclusion в слой. Изменение не применяется."
            ),
        }
    )


@router.get("/{context_id}/intent-validation-runs")
def list_interest_intent_validation_runs(
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
        InterestIntentValidationService(session).latest_runs_payload(
            context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.post("/{context_id}/intent-runs/{run_id}/validation-runs")
async def generate_interest_intent_validation_run(
    context_id: str,
    run_id: str,
    payload: InterestIntentValidationRunRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    route = select_ai_route(session, agent_key=payload.agent_key, route_role=payload.route_role)
    if route is None:
        raise HTTPException(
            status_code=400,
            detail=f"No AI route configured for {payload.agent_key}/{payload.route_role}",
        )
    settings = load_settings()
    client = build_zai_chat_client_for_route(
        session,
        route=route,
        settings=settings,
        worker_name="web-intent-validation",
        task_type="interest_intent_validation",
        default_timeout_seconds=180.0,
    )
    try:
        result = await InterestIntentValidationService(session).generate_recommendations(
            context_id=context.id,
            source_intent_run_id=run_id,
            actor=_actor(validated),
            client=client,
            provider=route.provider,
            model=route.model,
            model_profile=route.model_profile,
            ai_provider_account_id=route.provider_account_id,
            ai_model_id=route.model_id,
            ai_model_profile_id=route.model_profile_id,
            ai_agent_route_id=route.route_id,
            temperature=payload.temperature
            if payload.temperature is not None
            else float(route.temperature or 0.0),
            max_tokens=payload.max_tokens or int(route.max_output_tokens or 4096),
            max_reviews=payload.max_reviews,
            review_offset=payload.review_offset,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(result)


@router.get("/{context_id}/intent-validation-runs/{validation_run_id}/recommendations")
def list_interest_intent_validation_recommendations(
    context_id: str,
    validation_run_id: str,
    limit: int = 10,
    offset: int = 0,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    return jsonable_encoder(
        InterestIntentValidationService(session).recommendations_payload(
            context.id,
            validation_run_id=validation_run_id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.get("/{context_id}/intent-runs/{run_id}/validation-recommendations")
def list_interest_intent_validation_recommendations_for_intent_run(
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
        payload = InterestIntentValidationService(session).recommendations_payload_for_source_run(
            context.id,
            source_intent_run_id=run_id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent run not found") from exc
    return jsonable_encoder(payload)


@router.post("/{context_id}/intent-runs/{run_id}/validation-recommendations/apply")
def apply_interest_intent_validation_recommendations_for_intent_run(
    context_id: str,
    run_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    source_intent_run = (
        session.execute(
            select(interest_intent_analysis_runs_table)
            .where(interest_intent_analysis_runs_table.c.context_id == context.id)
            .where(interest_intent_analysis_runs_table.c.id == run_id)
        )
        .mappings()
        .first()
    )
    if source_intent_run is None:
        raise HTTPException(status_code=404, detail="Source intent run not found")
    try:
        layer_result = InterestIntentValidationService(
            session
        ).create_layer_from_source_run_approved(
            run_id,
            context_id=context.id,
            actor=_actor(validated),
        )
        run_result = InterestIntentLayerService(session).run_layer(
            context_id=context.id,
            layer_id=str(layer_result["layer"]["id"]),
            broad_analysis_run_id=str(source_intent_run["broad_analysis_run_id"]),
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent run or layer not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder({"layer_result": layer_result, **run_result})


@router.patch("/{context_id}/intent-validation-recommendations/{recommendation_id}")
def update_interest_intent_validation_recommendation(
    context_id: str,
    recommendation_id: str,
    payload: InterestIntentValidationRecommendationUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        recommendation = InterestIntentValidationService(session).update_recommendation_status(
            recommendation_id,
            context_id=context.id,
            status=payload.status,
            actor=_actor(validated),
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recommendation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"recommendation": jsonable_encoder(recommendation)}


@router.post("/{context_id}/intent-validation-runs/{validation_run_id}/create-layer")
def create_interest_intent_validation_layer(
    context_id: str,
    validation_run_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    try:
        result = InterestIntentValidationService(session).create_layer_from_approved(
            validation_run_id,
            context_id=context.id,
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Validation run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(result)


@router.post("/{context_id}/intent-validation-runs/{validation_run_id}/run-created-layer")
def run_created_interest_intent_validation_layer(
    context_id: str,
    validation_run_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    validation_run = (
        session.execute(
            select(interest_intent_validation_runs_table)
            .where(interest_intent_validation_runs_table.c.context_id == context.id)
            .where(interest_intent_validation_runs_table.c.id == validation_run_id)
        )
        .mappings()
        .first()
    )
    if validation_run is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    created_layer_id = validation_run["created_layer_id"]
    if not created_layer_id:
        raise HTTPException(status_code=400, detail="Сначала создайте AI-фильтр")
    try:
        InterestIntentValidationService(session).ensure_created_layer_review_exclusions(
            validation_run_id,
            context_id=context.id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Validation run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source_intent_run = (
        session.execute(
            select(interest_intent_analysis_runs_table)
            .where(interest_intent_analysis_runs_table.c.context_id == context.id)
            .where(
                interest_intent_analysis_runs_table.c.id
                == validation_run["source_intent_run_id"]
            )
        )
        .mappings()
        .first()
    )
    if source_intent_run is None:
        raise HTTPException(status_code=404, detail="Source intent run not found")
    try:
        result = InterestIntentLayerService(session).run_layer(
            context_id=context.id,
            layer_id=str(created_layer_id),
            broad_analysis_run_id=str(source_intent_run["broad_analysis_run_id"]),
            actor=_actor(validated),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Intent layer or broad run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jsonable_encoder(result)


@router.get("/{context_id}/intent-exclusions")
def list_interest_intent_exclusions(
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
        _intent_exclusion_queue_payload(
            session,
            context_id=context.id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
    )


@router.post("/{context_id}/intent-exclusions/{feedback_id}/apply")
def apply_interest_intent_exclusion(
    context_id: str,
    feedback_id: str,
    payload: InterestIntentExclusionApplyRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    row = _intent_exclusion_feedback_row(session, context_id=context.id, feedback_id=feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback item not found")
    if row["application_status"] == "ignored":
        raise HTTPException(status_code=400, detail="Feedback item was removed from exclusions")
    term = payload.term.strip()
    layer_row = (
        session.execute(
            select(interest_intent_layers_table).where(
                interest_intent_layers_table.c.id == row["intent_layer_id"]
            )
        )
        .mappings()
        .first()
    )
    if layer_row is None:
        raise HTTPException(status_code=404, detail="Intent layer not found")
    exclude_terms = _json_list_any(layer_row["exclude_patterns_json"])
    if not any(str(item).casefold().strip() == term.casefold() for item in exclude_terms):
        exclude_terms.append(term)
    now = utc_now()
    feedback_metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
    feedback_metadata = {
        **feedback_metadata,
        "applied_exclusion": {
            "term": term,
            "intent_layer_id": row["intent_layer_id"],
            "intent_run_id": row["run_id"],
            "intent_match_id": row["target_id"],
            "applied_at": now.isoformat(),
        },
    }
    session.execute(
        update(interest_intent_layers_table)
        .where(interest_intent_layers_table.c.id == row["intent_layer_id"])
        .values(exclude_patterns_json=exclude_terms, updated_at=now)
    )
    session.execute(
        update(feedback_events_table)
        .where(feedback_events_table.c.id == feedback_id)
        .values(
            application_status="applied",
            applied_entity_type="interest_intent_layer",
            applied_entity_id=row["intent_layer_id"],
            applied_at=now,
            metadata_json=feedback_metadata,
        )
    )
    AuditService(session).record_change(
        actor=_actor(validated),
        action="interest_intent_exclusion.apply",
        entity_type="interest_intent_layer",
        entity_id=str(row["intent_layer_id"]),
        old_value_json={"exclude_patterns_json": layer_row["exclude_patterns_json"]},
        new_value_json={"added_exclusion": term, "feedback_id": feedback_id},
    )
    session.commit()
    return jsonable_encoder(
        {
            "status": "applied",
            "feedback_id": feedback_id,
            "intent_layer_id": row["intent_layer_id"],
            "term": term,
            "exclude_patterns": exclude_terms,
            "next_step": "Перезапустите слой намерений, чтобы получить новый список сообщений.",
        }
    )


@router.delete("/{context_id}/intent-exclusions/{feedback_id}")
def delete_interest_intent_exclusion(
    context_id: str,
    feedback_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    row = _intent_exclusion_feedback_row(session, context_id=context.id, feedback_id=feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback item not found")
    if row["application_status"] == "ignored":
        return {
            "status": "deleted",
            "feedback_id": feedback_id,
            "intent_match_id": row["target_id"],
        }
    if row["application_status"] == "applied" or row["applied_at"] is not None:
        raise HTTPException(
            status_code=400,
            detail="Исключение уже применено к слою. Удалять можно только непримененный feedback.",
        )
    now = utc_now()
    metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
    metadata = {
        **metadata,
        "cancelled_exclusion": {
            "cancelled_at": now.isoformat(),
            "cancelled_by": _actor(validated),
            "previous_application_status": row["application_status"],
        },
    }
    session.execute(
        update(feedback_events_table)
        .where(feedback_events_table.c.id == feedback_id)
        .values(application_status="ignored", metadata_json=metadata)
    )
    AuditService(session).record_change(
        actor=_actor(validated),
        action="interest_intent_exclusion.delete_pending",
        entity_type="interest_intent_match",
        entity_id=str(row["target_id"]),
        old_value_json={
            "feedback_id": feedback_id,
            "application_status": row["application_status"],
            "intent_layer_id": row["intent_layer_id"],
            "intent_run_id": row["run_id"],
        },
        new_value_json=None,
    )
    session.commit()
    return {
        "status": "deleted",
        "feedback_id": feedback_id,
        "intent_match_id": row["target_id"],
    }


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


_NGRAM_STOPWORDS = {
    "url",
    "а",
    "без",
    "бы",
    "быть",
    "в",
    "ваш",
    "ваша",
    "ваше",
    "ваши",
    "весь",
    "все",
    "всё",
    "вы",
    "где",
    "да",
    "для",
    "до",
    "его",
    "ее",
    "её",
    "если",
    "есть",
    "еще",
    "ещё",
    "же",
    "за",
    "и",
    "или",
    "из",
    "как",
    "который",
    "кто",
    "мы",
    "на",
    "надо",
    "наш",
    "наша",
    "наше",
    "наши",
    "не",
    "нет",
    "но",
    "ну",
    "о",
    "он",
    "она",
    "они",
    "по",
    "под",
    "при",
    "просто",
    "с",
    "со",
    "так",
    "такой",
    "там",
    "то",
    "тут",
    "у",
    "уже",
    "что",
    "чтобы",
    "это",
    "этот",
    "эта",
    "эти",
}


def _ngram_page_payload(
    session: Session,
    raw_export_run_id: str,
    *,
    kind: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    normalized_kind = str(kind or "lemmas").strip().lower()
    ngram_size = {"lemmas": 1, "bigrams": 2, "trigrams": 3}.get(normalized_kind)
    if ngram_size is None:
        raise HTTPException(status_code=400, detail="kind must be lemmas, bigrams or trigrams")
    counter: Counter[str] = Counter()
    rows = telegram_feature_rows(session, raw_export_run_id)
    for row in rows:
        lemmas = _clean_ngram_lemmas(row.get("lemmas_json") or row.get("lemmas"))
        if ngram_size == 1:
            counter.update(lemmas)
            continue
        counter.update(
            " ".join(items)
            for items in zip(*(lemmas[index:] for index in range(ngram_size)), strict=False)
            if len(set(items)) > 1
        )
    items = [{"term": term, "count": count} for term, count in counter.most_common()]
    total = len(items)
    return {
        "kind": normalized_kind,
        "items": items[offset : offset + limit],
        "summary": {
            "feature_rows": len(rows),
            "unique_terms": total,
            "stopwords_removed": sorted(_NGRAM_STOPWORDS),
            "source": "telegram_prepared_documents.feature_json",
        },
        "pagination": _pagination(limit=limit, offset=offset, total=total),
    }


def _clean_ngram_lemmas(value: Any) -> list[str]:
    result: list[str] = []
    for item in _json_list_any(value):
        lemma = str(item or "").casefold().replace("ё", "е").strip()
        if len(lemma) < 3:
            continue
        if lemma in _NGRAM_STOPWORDS:
            continue
        if not re.search(r"[a-zа-я0-9]", lemma):
            continue
        result.append(lemma)
    return result


def _entity_extraction_rules_payload() -> dict[str, Any]:
    return {
        "stage": "telegram_entity_extraction",
        "storage": "telegram_entity_candidates",
        "candidate_pos": ["NOUN", "PROPN", "ADJ"],
        "candidate_patterns": ["[NOUN]", "[PROPN]", "[NOUN NOUN]", "[ADJ NOUN]", "[PROPN+]"],
        "normalization": "lowercase + punctuation trim + lemmas from Stage 2",
        "auto_merge_policy": "exact_only",
        "auto_merge_confidence": "high",
        "human_review_required_for": ["medium", "low"],
        "noise_filtering": "short/no-letter/stop-lemma candidates are dropped before ranking",
        "editable": False,
        "edit_note": (
            "Сейчас правила показаны явно, но редактирование правил еще не применяет пересчет. "
            "Следующий шаг - вынести их в настройки Stage 5 и запускать пересборку."
        ),
    }


def _prepared_raw_run(
    session: Session,
    context_id: str,
    *,
    metadata_key: str,
    raw_export_run_id: str | None = None,
) -> dict[str, Any]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Interest context not found")
    source_ids = [
        str(row["id"])
        for row in session.execute(
            select(monitored_sources_table.c.id).where(
                monitored_sources_table.c.interest_context_id == context.id
            )
        )
        .mappings()
        .all()
    ]
    rows = _raw_runs_for_sources(session, source_ids)
    if raw_export_run_id:
        rows = [row for row in rows if str(row["id"]) == raw_export_run_id]
        if not rows:
            raise HTTPException(status_code=404, detail="Raw-run не найден в выбранном контексте")
    for row in rows:
        if row.get("status") != "succeeded":
            continue
        metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        if isinstance(metadata.get(metadata_key), dict):
            return row
    raise HTTPException(
        status_code=400,
        detail=f"Артефакт {metadata_key} еще не готов для выбранного контекста",
    )


def _prepared_raw_runs_payload(
    session: Session,
    context_id: str,
    metadata_key: str,
) -> list[dict[str, Any]]:
    context = InterestContextService(session).repository.get(context_id)
    if context is None:
        return []
    source_ids = [
        str(row["id"])
        for row in session.execute(
            select(monitored_sources_table.c.id).where(
                monitored_sources_table.c.interest_context_id == context.id
            )
        )
        .mappings()
        .all()
    ]
    payload = []
    for row in _raw_runs_for_sources(session, source_ids):
        metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        if row.get("status") == "succeeded" and isinstance(metadata.get(metadata_key), dict):
            payload.append(_raw_run_payload(row))
    return payload


def _prepared_documents_summary(session: Session, raw_export_run_id: str) -> dict[str, Any]:
    rows = (
        session.execute(
            select(
                telegram_prepared_documents_table.c.entity_type,
                func.count(telegram_prepared_documents_table.c.id).label("count"),
                func.sum(telegram_prepared_documents_table.c.token_count).label("tokens"),
            )
            .where(telegram_prepared_documents_table.c.raw_export_run_id == raw_export_run_id)
            .group_by(telegram_prepared_documents_table.c.entity_type)
        )
        .mappings()
        .all()
    )
    return {
        "total_rows": sum(int(row["count"] or 0) for row in rows),
        "total_tokens": sum(int(row["tokens"] or 0) for row in rows),
        "by_entity_type": {
            str(row["entity_type"]): {
                "rows": int(row["count"] or 0),
                "tokens": int(row["tokens"] or 0),
            }
            for row in rows
        },
        "storage": "postgresql" if session.get_bind().dialect.name == "postgresql" else "database",
    }


def _prepared_text_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "tokens": row.get("tokens_json") or [],
        "lemmas": row.get("lemmas_json") or [],
        "pos_tags": row.get("pos_tags_json") or [],
        "token_map": row.get("token_map_json") or [],
    }


def _feature_payload(row: dict[str, Any]) -> dict[str, Any]:
    feature = row.get("feature_json") if isinstance(row.get("feature_json"), dict) else {}
    expanded = dict(feature)
    for key, value in list(expanded.items()):
        if key.endswith("_json"):
            expanded[key[:-5]] = value
    return {
        **expanded,
        "prepared_document_id": row.get("id"),
        "entity_type": row.get("entity_type"),
        "telegram_message_id": row.get("telegram_message_id"),
        "artifact_kind": row.get("artifact_kind"),
        "file_name": row.get("file_name"),
        "message_url": row.get("message_url"),
        "clean_text": row.get("clean_text"),
    }


def _stage_payload(outputs: dict[str, Any], key: str) -> Any:
    output = outputs.get(key)
    if not isinstance(output, dict):
        return {}
    return output.get("payload_json") or {}


def _entity_rows_page(
    session: Session,
    raw_export_run_id: str,
    *,
    limit: int,
    offset: int,
    ranked: bool,
) -> dict[str, Any]:
    base = select(telegram_entity_candidates_table).where(
        telegram_entity_candidates_table.c.raw_export_run_id == raw_export_run_id
    )
    total = int(session.execute(select(func.count()).select_from(base.subquery())).scalar_one() or 0)
    order_by = (
        [
            telegram_entity_candidates_table.c.score.desc().nullslast(),
            telegram_entity_candidates_table.c.normalized_text,
        ]
        if ranked
        else [
            telegram_entity_candidates_table.c.normalized_text,
            telegram_entity_candidates_table.c.entity_id,
        ]
    )
    rows = (
        session.execute(base.order_by(*order_by).limit(limit).offset(offset))
        .mappings()
        .all()
    )
    return {
        "items": [_entity_payload(dict(row)) for row in rows],
        "pagination": _pagination(limit=limit, offset=offset, total=total),
        "columns": [column.name for column in telegram_entity_candidates_table.columns],
    }


def _entity_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    result = {**payload, **row}
    result["pos_pattern"] = row.get("pos_pattern_json") or []
    result["source_refs"] = row.get("source_refs_json") or []
    result["example_contexts"] = row.get("example_contexts_json") or []
    result["entity_type_counts"] = row.get("entity_type_counts_json") or {}
    result["reasons"] = row.get("reasons_json") or []
    result["penalties"] = row.get("penalties_json") or []
    return result


def _json_any(value: Any) -> Any:
    if value is None or value == "":
        return value
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return value


def _json_list_any(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str) and value.strip():
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                loaded = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            return loaded if isinstance(loaded, list) else [loaded]
        return [stripped]
    return []


def _pagination(*, limit: int, offset: int, total: int) -> dict[str, Any]:
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + limit < total,
    }


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


def _intent_match_row(
    session: Session,
    *,
    context_id: str,
    run_id: str,
    match_id: str,
) -> dict[str, Any] | None:
    rows = _intent_match_rows_for_run(session, context_id=context_id, run_id=run_id, match_id=match_id)
    return rows[0] if rows else None


def _intent_exclusion_queue_payload(
    session: Session,
    *,
    context_id: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    total = int(
        session.execute(
            select(func.count())
            .select_from(feedback_events_table)
            .join(
                interest_intent_analysis_matches_table,
                interest_intent_analysis_matches_table.c.id == feedback_events_table.c.target_id,
            )
            .where(feedback_events_table.c.target_type == "interest_intent_match")
            .where(feedback_events_table.c.action == "not_lead")
            .where(feedback_events_table.c.application_status != "ignored")
            .where(interest_intent_analysis_matches_table.c.context_id == context_id)
        ).scalar_one()
        or 0
    )
    rows = (
        session.execute(
            _intent_exclusion_feedback_select()
            .where(feedback_events_table.c.target_type == "interest_intent_match")
            .where(feedback_events_table.c.action == "not_lead")
            .where(feedback_events_table.c.application_status != "ignored")
            .where(interest_intent_analysis_matches_table.c.context_id == context_id)
            .order_by(desc(feedback_events_table.c.created_at))
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    items = [
        _intent_exclusion_feedback_payload(session, dict(row), context_id=context_id) for row in rows
    ]
    return {
        "items": items,
        "summary": {
            "total": total,
            "pending": sum(1 for item in items if item["feedback"]["application_status"] != "applied"),
            "applied": sum(1 for item in items if item["feedback"]["application_status"] == "applied"),
        },
        "pagination": _pagination(limit=limit, offset=offset, total=total),
    }


def _intent_exclusion_feedback_row(
    session: Session,
    *,
    context_id: str,
    feedback_id: str,
) -> dict[str, Any] | None:
    row = (
        session.execute(
            _intent_exclusion_feedback_select()
            .where(feedback_events_table.c.id == feedback_id)
            .where(feedback_events_table.c.target_type == "interest_intent_match")
            .where(interest_intent_analysis_matches_table.c.context_id == context_id)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _intent_exclusion_feedback_select() -> Any:
    return (
        select(
            feedback_events_table.c.id.label("feedback_id"),
            feedback_events_table.c.target_id,
            feedback_events_table.c.action,
            feedback_events_table.c.reason_code,
            feedback_events_table.c.feedback_scope,
            feedback_events_table.c.learning_effect,
            feedback_events_table.c.application_status,
            feedback_events_table.c.applied_entity_type,
            feedback_events_table.c.applied_entity_id,
            feedback_events_table.c.applied_at,
            feedback_events_table.c.comment,
            feedback_events_table.c.created_by,
            feedback_events_table.c.created_at.label("feedback_created_at"),
            feedback_events_table.c.metadata_json,
            interest_intent_analysis_matches_table.c.id.label("match_id"),
            interest_intent_analysis_matches_table.c.run_id,
            interest_intent_analysis_matches_table.c.context_id,
            interest_intent_analysis_matches_table.c.intent_layer_id,
            interest_intent_analysis_matches_table.c.telegram_message_id,
            interest_intent_analysis_matches_table.c.message_date,
            interest_intent_analysis_matches_table.c.sender_id,
            interest_intent_analysis_matches_table.c.message_text,
            interest_intent_analysis_matches_table.c.canonical_name,
            interest_intent_analysis_matches_table.c.category,
            interest_intent_analysis_matches_table.c.score,
            interest_intent_analysis_matches_table.c.broad_score,
            interest_intent_analysis_matches_table.c.evidence_json,
            monitored_sources_table.c.username.label("_source_username"),
            monitored_sources_table.c.input_ref.label("_source_input_ref"),
            monitored_sources_table.c.telegram_id.label("_source_telegram_id"),
        )
        .join(
            interest_intent_analysis_matches_table,
            interest_intent_analysis_matches_table.c.id == feedback_events_table.c.target_id,
        )
        .join(
            source_messages_table,
            source_messages_table.c.id == interest_intent_analysis_matches_table.c.source_message_id,
            isouter=True,
        )
        .join(
            monitored_sources_table,
            monitored_sources_table.c.id == source_messages_table.c.monitored_source_id,
            isouter=True,
        )
    )


def _intent_exclusion_feedback_payload(
    session: Session,
    row: dict[str, Any],
    *,
    context_id: str,
) -> dict[str, Any]:
    suggestions = _intent_exclusion_suggestions(str(row.get("message_text") or ""))
    metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
    applied_exclusion = (
        metadata.get("applied_exclusion") if isinstance(metadata.get("applied_exclusion"), dict) else {}
    )
    term = str(applied_exclusion.get("term") or (suggestions[0] if suggestions else "")).strip()
    preview = _intent_exclusion_preview_payload(
        session,
        context_id=context_id,
        run_id=str(row["run_id"]),
        match_id=str(row["match_id"]),
        term=term,
        suggestions=suggestions,
    )
    return {
        "feedback": {
            "id": row["feedback_id"],
            "action": row["action"],
            "reason_code": row["reason_code"],
            "feedback_scope": row["feedback_scope"],
            "learning_effect": row["learning_effect"],
            "application_status": row["application_status"],
            "applied_entity_type": row["applied_entity_type"],
            "applied_entity_id": row["applied_entity_id"],
            "applied_at": row["applied_at"],
            "comment": row["comment"],
            "created_by": row["created_by"],
            "created_at": row["feedback_created_at"],
        },
        "match": _intent_preview_payload({**row, "id": row["match_id"]}),
        "run_id": row["run_id"],
        "intent_layer_id": row["intent_layer_id"],
        "category": row["category"],
        "evidence": row["evidence_json"] if isinstance(row.get("evidence_json"), dict) else {},
        "suggestions": suggestions,
        "selected_term": term,
        "preview": preview,
    }


def _intent_exclusion_preview_payload(
    session: Session,
    *,
    context_id: str,
    run_id: str,
    match_id: str,
    term: str,
    suggestions: list[str],
) -> dict[str, Any]:
    rows = _intent_match_rows_for_run(session, context_id=context_id, run_id=run_id)
    removed = [row for row in rows if term and _plain_term_hits(term, str(row["message_text"] or ""))]
    return {
        "match_id": match_id,
        "run_id": run_id,
        "suggestions": suggestions,
        "term": term,
        "total_matches": len(rows),
        "removed_count": len(removed),
        "remaining_count": max(0, len(rows) - len(removed)),
        "target_removed": any(str(row["id"]) == match_id for row in removed),
        "removed_samples": [_intent_preview_payload(row) for row in removed[:10]],
        "explanation": (
            "Preview считает, сколько текущих сообщений слоя намерений исчезнет, "
            "если добавить это исключение в слой. Изменение не применяется без кнопки."
        ),
    }


def _intent_match_rows_for_run(
    session: Session,
    *,
    context_id: str,
    run_id: str,
    match_id: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        select(
            interest_intent_analysis_matches_table,
            monitored_sources_table.c.username.label("_source_username"),
            monitored_sources_table.c.input_ref.label("_source_input_ref"),
            monitored_sources_table.c.telegram_id.label("_source_telegram_id"),
        )
        .join(
            source_messages_table,
            source_messages_table.c.id == interest_intent_analysis_matches_table.c.source_message_id,
            isouter=True,
        )
        .join(
            monitored_sources_table,
            monitored_sources_table.c.id == source_messages_table.c.monitored_source_id,
            isouter=True,
        )
        .where(interest_intent_analysis_matches_table.c.context_id == context_id)
        .where(interest_intent_analysis_matches_table.c.run_id == run_id)
        .order_by(desc(interest_intent_analysis_matches_table.c.score))
    )
    if match_id:
        query = query.where(interest_intent_analysis_matches_table.c.id == match_id)
    return [dict(row) for row in session.execute(query).mappings().all()]


def _intent_preview_payload(row: dict[str, Any]) -> dict[str, Any]:
    message_id = row.get("telegram_message_id")
    username = str(row.get("_source_username") or "").strip().lstrip("@")
    input_ref = str(row.get("_source_input_ref") or "")
    if not username and "t.me/" in input_ref:
        username = input_ref.split("t.me/", 1)[1].strip("/").split("/", 1)[0].lstrip("@")
    telegram_id = str(row.get("_source_telegram_id") or "").strip()
    message_url = None
    if username and message_id is not None:
        message_url = f"https://t.me/{username}/{message_id}"
    elif telegram_id and message_id is not None:
        internal_id = telegram_id.removeprefix("-100").lstrip("-")
        if internal_id.isdigit():
            message_url = f"https://t.me/c/{internal_id}/{message_id}"
    return {
        "id": row["id"],
        "telegram_message_id": message_id,
        "message_url": message_url,
        "canonical_name": row.get("canonical_name"),
        "score": row.get("score"),
        "message_text": row.get("message_text"),
    }


def _intent_exclusion_suggestions(text: str) -> list[str]:
    normalized = _plain_normalize(text)
    tokens = [token for token in normalized.split() if len(token) >= 4 and token not in _PREVIEW_STOPWORDS]
    phrases: list[str] = []
    for size in (3, 2):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase = " ".join(tokens[index : index + size])
            if any(marker in phrase for marker in _DESIGN_SPECIFIC_MARKERS):
                phrases.append(phrase)
    phrases.extend(token for token in tokens if token in _DESIGN_SPECIFIC_MARKERS)
    return list(dict.fromkeys(phrases))[:8]


def _plain_term_hits(term: str, text: str) -> bool:
    normalized_term = _plain_normalize(term)
    normalized_text = _plain_normalize(text)
    if not normalized_term or not normalized_text:
        return False
    return all(token in normalized_text for token in normalized_term.split())


def _plain_normalize(value: str) -> str:
    text = value.casefold().replace("ё", "е")
    text = re.sub(r"https?://\S+|www\.\S+", " url ", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_PREVIEW_STOPWORDS = {
    "добрый",
    "день",
    "коллеги",
    "пожалуйста",
    "нужно",
    "нужен",
    "нужна",
    "помогите",
    "лучше",
    "какой",
    "какая",
    "какие",
    "ваши",
    "наши",
    "буду",
}

_DESIGN_SPECIFIC_MARKERS = {
    "ниша",
    "ниши",
    "нишу",
    "скала",
    "скалы",
    "рельеф",
    "профиль",
    "дизайн",
    "дизайнер",
    "размер",
}


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


def _archive_import_progress(job: Any) -> dict[str, Any]:
    return _archive_import_progress_from_row(_job_payload(job))


def _archive_import_progress_from_row(job: dict[str, Any] | None) -> dict[str, Any]:
    if not job:
        return {
            "kind": "telegram_desktop_archive_import",
            "status": "not_started",
            "current_stage": None,
            "current_stage_label": "Не запускалось",
            "overall_percent": 0,
            "stage_percent": 0,
            "message": "Импорт архива еще не запускался",
        }
    progress = job.get("result_summary_json")
    if isinstance(progress, dict) and progress.get("kind") == "telegram_desktop_archive_import":
        return _progress_with_actual_job_status(job, progress)
    status = str(job.get("status") or "unknown")
    payload = job.get("payload_json") if isinstance(job.get("payload_json"), dict) else {}
    return {
        "kind": "telegram_desktop_archive_import",
        "status": status,
        "mode": payload.get("mode"),
        "current_stage": None,
        "current_stage_label": "В очереди" if status == "queued" else status,
        "overall_percent": 0,
        "stage_percent": 0,
        "message": "Архив загружен. Задача импорта ожидает воркер."
        if status == "queued"
        else job.get("last_error") or status,
        "stored_archive_path": payload.get("stored_archive_path"),
        "message_count": 0,
        "attachment_count": 0,
    }


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
