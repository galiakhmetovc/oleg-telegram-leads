"""Generated artifact visibility routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pur_leads.services.artifact_inventory import ArtifactInventoryService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/artifacts")


@router.get("")
def list_artifacts(
    stage: str | None = None,
    kind: str | None = None,
    exists: bool | None = None,
    q: str | None = None,
    limit: int = 500,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return ArtifactInventoryService(session).list_artifacts(
        stage=stage,
        kind=kind,
        exists=exists,
        query=q,
        limit=limit,
    )


@router.get("/{artifact_id}")
def get_artifact(
    artifact_id: str,
    max_preview_chars: int = 500_000,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        return ArtifactInventoryService(session).get_artifact(
            artifact_id,
            max_preview_chars=max_preview_chars,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
