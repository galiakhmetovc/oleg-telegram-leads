from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


LeadHandlingStatus = Literal["new", "claimed", "contacted", "waiting", "closed", "not_lead"]
LeadHandlingEventType = Literal[
    "created",
    "claimed",
    "marked_not_lead",
    "status_changed",
    "comment_added",
    "group_message_edited",
    "callback_failed",
    "message_failed",
]


@dataclass(frozen=True)
class LeadHandlingActor:
    telegram_user_id: str
    telegram_username: str | None
    display_name: str | None


@dataclass(frozen=True)
class LeadHandling:
    id: UUID
    source_message_id: UUID
    notification_outbox_id: UUID | None
    sales_chat_id: str | None
    sales_chat_message_id: int | None
    status: LeadHandlingStatus
    owner_telegram_user_id: str | None
    owner_telegram_username: str | None
    owner_display_name: str | None
    last_comment: str | None
    claimed_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class LeadHandlingEvent:
    id: UUID
    lead_handling_id: UUID
    source_message_id: UUID
    actor_telegram_user_id: str | None
    actor_telegram_username: str | None
    actor_display_name: str | None
    event_type: LeadHandlingEventType
    payload: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class LeadClaimResult:
    handling: LeadHandling
    event: LeadHandlingEvent
    already_claimed: bool


@dataclass(frozen=True)
class LeadHandlingActionResult:
    handling: LeadHandling
    event: LeadHandlingEvent


@dataclass(frozen=True)
class LeadHandlingSummary:
    id: UUID
    source_message_id: UUID
    status: LeadHandlingStatus
    owner_telegram_user_id: str | None
    owner_display_name: str | None
    last_comment: str | None
    sales_chat_id: str | None
    sales_chat_message_id: int | None
    updated_at: datetime


@dataclass(frozen=True)
class LeadBotSession:
    bot_id: str
    telegram_user_id: str
    state: str
    payload: dict[str, object]
    updated_at: datetime
