"""Today overview routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pur_leads.services.today import TodayService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/today")


class TaskCreateRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "normal"
    due_at: datetime | None = None
    client_id: str | None = None
    lead_cluster_id: str | None = None
    contact_reason_id: str | None = None


class TaskSnoozeRequest(BaseModel):
    due_at: datetime


class ContactReasonSnoozeRequest(BaseModel):
    snoozed_until: datetime


@router.get("")
def today_summary(
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _ = validated
    return jsonable_encoder(TodayService(session).summary())


@router.post("/tasks")
def create_task(
    payload: TaskCreateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _validate_priority(payload.priority)
    task = TodayService(session).create_task(
        actor=_actor(validated),
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
        client_id=payload.client_id,
        lead_cluster_id=payload.lead_cluster_id,
        contact_reason_id=payload.contact_reason_id,
        owner_user_id=validated.user.id,
        assignee_user_id=validated.user.id,
    )
    return {"task": jsonable_encoder(task)}


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        task = TodayService(session).complete_task(task_id, actor=_actor(validated))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"task": jsonable_encoder(task)}


@router.post("/tasks/{task_id}/snooze")
def snooze_task(
    task_id: str,
    payload: TaskSnoozeRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        task = TodayService(session).snooze_task(
            task_id,
            actor=_actor(validated),
            due_at=payload.due_at,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"task": jsonable_encoder(task)}


@router.post("/contact-reasons/{reason_id}/accept")
def accept_contact_reason(
    reason_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        reason = TodayService(session).accept_contact_reason(reason_id, actor=_actor(validated))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Contact reason not found") from exc
    return {"contact_reason": jsonable_encoder(reason)}


@router.post("/contact-reasons/{reason_id}/done")
def complete_contact_reason(
    reason_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        reason = TodayService(session).complete_contact_reason(reason_id, actor=_actor(validated))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Contact reason not found") from exc
    return {"contact_reason": jsonable_encoder(reason)}


@router.post("/contact-reasons/{reason_id}/dismiss")
def dismiss_contact_reason(
    reason_id: str,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        reason = TodayService(session).dismiss_contact_reason(reason_id, actor=_actor(validated))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Contact reason not found") from exc
    return {"contact_reason": jsonable_encoder(reason)}


@router.post("/contact-reasons/{reason_id}/snooze")
def snooze_contact_reason(
    reason_id: str,
    payload: ContactReasonSnoozeRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        reason = TodayService(session).snooze_contact_reason(
            reason_id,
            actor=_actor(validated),
            snoozed_until=payload.snoozed_until,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Contact reason not found") from exc
    return {"contact_reason": jsonable_encoder(reason)}


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _validate_priority(value: str) -> None:
    if value not in {"low", "normal", "high"}:
        raise HTTPException(status_code=400, detail="Unsupported task priority")
