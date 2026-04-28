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
