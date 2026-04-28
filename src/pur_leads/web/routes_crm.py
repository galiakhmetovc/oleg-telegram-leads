"""CRM memory routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pur_leads.repositories.crm import ClientRecord
from pur_leads.services.crm import ClientProfile, CrmService, LeadClusterConversionResult
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api")


class ClientProfileRequest(BaseModel):
    display_name: str
    client_type: str = "unknown"
    notes: str | None = None
    contacts: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    interests: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    opportunities: list[dict[str, Any]] = []
    support_cases: list[dict[str, Any]] = []
    contact_reasons: list[dict[str, Any]] = []
    touchpoints: list[dict[str, Any]] = []
    metadata_json: Any | None = None


class LeadCrmConversionRequest(BaseModel):
    client: dict[str, Any] | None = None
    contact: dict[str, Any] | None = None
    client_object: dict[str, Any] | None = None
    interest: dict[str, Any] | None = None
    task: dict[str, Any] | None = None
    link_existing_client_id: str | None = None
    used_candidate_ids: list[str] = []


@router.get("/crm/clients")
def list_clients(
    status: str | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    clients = CrmService(session).repository.list_clients(status=status)
    return {"items": [_client_payload(client) for client in clients]}


@router.post("/crm/clients")
def create_client_profile(
    payload: ClientProfileRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        profile = CrmService(session).create_client_profile(
            actor=_actor(validated),
            display_name=payload.display_name,
            client_type=payload.client_type,
            notes=payload.notes,
            contacts=payload.contacts,
            objects=payload.objects,
            interests=payload.interests,
            assets=payload.assets,
            opportunities=payload.opportunities,
            support_cases=payload.support_cases,
            contact_reasons=payload.contact_reasons,
            touchpoints=payload.touchpoints,
            metadata_json=payload.metadata_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profile_payload(profile)


@router.get("/crm/clients/{client_id}")
def get_client_profile(
    client_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        profile = CrmService(session).get_client_profile(client_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Client not found") from exc
    return _profile_payload(profile)


@router.post("/leads/{cluster_id}/crm/convert")
def convert_lead_cluster(
    cluster_id: str,
    payload: LeadCrmConversionRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        result = CrmService(session).convert_lead_cluster(
            cluster_id,
            actor=_actor(validated),
            client=payload.client,
            contact=payload.contact,
            client_object=payload.client_object,
            interest=payload.interest,
            task=payload.task,
            link_existing_client_id=payload.link_existing_client_id,
            used_candidate_ids=payload.used_candidate_ids,
            owner_user_id=validated.user.id,
            assignee_user_id=validated.user.id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lead cluster or CRM entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _conversion_payload(result)


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _client_payload(client: ClientRecord) -> dict[str, Any]:
    return jsonable_encoder(asdict(client))


def _profile_payload(profile: ClientProfile) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "client": asdict(profile.client),
            "contacts": [asdict(contact) for contact in profile.contacts],
            "objects": [asdict(client_object) for client_object in profile.objects],
            "interests": [asdict(interest) for interest in profile.interests],
            "assets": [asdict(asset) for asset in profile.assets],
            "opportunities": [asdict(opportunity) for opportunity in profile.opportunities],
            "support_cases": [asdict(support_case) for support_case in profile.support_cases],
            "contact_reasons": [asdict(reason) for reason in profile.contact_reasons],
            "touchpoints": [asdict(touchpoint) for touchpoint in profile.touchpoints],
        }
    )


def _conversion_payload(result: LeadClusterConversionResult) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "client": asdict(result.client),
            "contact": asdict(result.contact) if result.contact else None,
            "client_object": asdict(result.client_object) if result.client_object else None,
            "interest": asdict(result.interest) if result.interest else None,
            "task": asdict(result.task) if result.task else None,
            "action": asdict(result.action),
            "primary_entity_type": result.primary_entity_type,
            "primary_entity_id": result.primary_entity_id,
        }
    )
