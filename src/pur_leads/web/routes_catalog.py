"""Catalog candidate review routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pur_leads.repositories.catalog_candidates import CatalogCandidateRecord
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/catalog")


class CandidateReviewRequest(BaseModel):
    action: str
    reason: str | None = None


class CandidateUpdateRequest(BaseModel):
    canonical_name: str | None = None
    normalized_value: dict[str, Any] | None = None
    reason: str | None = None


@router.get("/candidates")
def list_candidates(
    status: str | None = None,
    candidate_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    candidates = CatalogCandidateService(session).list_candidates(
        status=status,
        candidate_type=candidate_type,
        limit=limit,
    )
    return {"items": [_candidate_payload(candidate) for candidate in candidates]}


@router.get("/candidates/{candidate_id}")
def get_candidate_detail(
    candidate_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = CatalogCandidateService(session).get_candidate_detail(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    return _candidate_detail_payload(detail)


@router.patch("/candidates/{candidate_id}")
def update_candidate(
    candidate_id: str,
    payload: CandidateUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = CatalogCandidateService(session)
    try:
        service.update_candidate(
            candidate_id,
            actor=_actor(validated),
            canonical_name=payload.canonical_name,
            normalized_value=payload.normalized_value,
            reason=payload.reason,
        )
        detail = service.get_candidate_detail(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _candidate_detail_payload(detail)


@router.post("/candidates/{candidate_id}/review")
def review_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        result = CatalogCandidateService(session).review_candidate(
            candidate_id,
            action=payload.action,
            actor=_actor(validated),
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "candidate": _candidate_payload(result.candidate),
        "promotion": jsonable_encoder(asdict(result.promotion)) if result.promotion else None,
    }


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _candidate_payload(candidate: CatalogCandidateRecord) -> dict[str, Any]:
    payload = jsonable_encoder(asdict(candidate))
    payload["normalized_value"] = payload.pop("normalized_value_json")
    return payload


def _candidate_detail_payload(detail: Any) -> dict[str, Any]:
    return {
        "candidate": _candidate_payload(detail.candidate),
        "evidence": [_evidence_payload(row) for row in detail.evidence],
    }


def _evidence_payload(row: dict[str, Any]) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row["evidence_id"],
            "source_id": row["evidence_source_id"],
            "artifact_id": row["artifact_id"] or row["evidence_artifact_id"],
            "chunk_id": row["evidence_chunk_id"],
            "quote": row["quote"],
            "page_number": row["page_number"],
            "location": row["location_json"],
            "extractor_version": row["extractor_version"],
            "evidence_type": row["evidence_type"],
            "confidence": row["evidence_confidence"],
            "created_by": row["evidence_created_by"],
            "created_at": row["evidence_created_at"],
            "source": _source_payload(row),
            "artifact": _artifact_payload(row),
            "chunk": _chunk_payload(row),
        }
    )


def _source_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["source_id"] is None:
        return None
    return {
        "id": row["source_id"],
        "source_type": row["source_type"],
        "origin": row["source_origin"],
        "external_id": row["source_external_id"],
        "url": row["source_url"],
        "title": row["source_title"],
        "published_at": row["source_published_at"],
        "raw_text_excerpt": _excerpt(row["source_raw_text"]),
    }


def _artifact_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["artifact_id"] is None:
        return None
    return {
        "id": row["artifact_id"],
        "file_name": row["artifact_file_name"],
        "mime_type": row["artifact_mime_type"],
        "file_size": row["artifact_file_size"],
        "download_status": row["artifact_download_status"],
    }


def _chunk_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["chunk_id"] is None:
        return None
    return {
        "id": row["chunk_id"],
        "chunk_index": row["chunk_index"],
        "text": row["chunk_text"],
        "parser_name": row["chunk_parser_name"],
        "parser_version": row["chunk_parser_version"],
    }


def _excerpt(value: str | None, *, limit: int = 700) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
