from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID


NotificationMatchMode = Literal["all", "any"]
NotificationOutboxStatus = Literal["pending", "sending", "sent", "failed"]


@dataclass(frozen=True)
class TelegramBot:
    id: str
    name: str
    enabled: bool
    token: str | None

    @property
    def has_token(self) -> bool:
        return bool(self.token)


@dataclass(frozen=True)
class TelegramChat:
    id: str
    name: str
    enabled: bool
    telegram_chat_id: str


@dataclass(frozen=True)
class NotificationRouteConditions:
    is_lead: bool | None = None
    score_min: int | None = None
    score_max: int | None = None
    temperatures: list[str] = field(default_factory=list)
    review_lanes: list[str] = field(default_factory=list)
    solution_areas: list[str] = field(default_factory=list)
    customer_segments: list[str] = field(default_factory=list)
    domain_signals: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    noise_signals: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.is_lead is not None,
                self.score_min is not None,
                self.score_max is not None,
                self.temperatures,
                self.review_lanes,
                self.solution_areas,
                self.customer_segments,
                self.domain_signals,
                self.facts,
                self.reasons,
                self.noise_signals,
            ]
        )


@dataclass(frozen=True)
class NotificationRoute:
    id: str
    name: str
    enabled: bool
    priority: int
    bot_id: str
    chat_id: str
    match_mode: NotificationMatchMode
    conditions: NotificationRouteConditions
    message_template: str


@dataclass(frozen=True)
class NotificationSettings:
    bots: list[TelegramBot]
    chats: list[TelegramChat]
    routes: list[NotificationRoute]
    updated_at: datetime | None


@dataclass(frozen=True)
class TelegramSendResult:
    message_id: int
    chat_id: str


@dataclass(frozen=True)
class NotificationOutboxItem:
    id: UUID
    route_id: str
    bot_id: str
    chat_id: str
    source_message_id: UUID | None
    enrichment_job_id: UUID | None
    text: str
    status: NotificationOutboxStatus
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None

    def mark_sent(self, sent_at: datetime) -> NotificationOutboxItem:
        return NotificationOutboxItem(
            id=self.id,
            route_id=self.route_id,
            bot_id=self.bot_id,
            chat_id=self.chat_id,
            source_message_id=self.source_message_id,
            enrichment_job_id=self.enrichment_job_id,
            text=self.text,
            status="sent",
            attempts=self.attempts + 1,
            last_error=None,
            created_at=self.created_at,
            sent_at=sent_at,
        )

    def mark_failed(self, error: str) -> NotificationOutboxItem:
        return NotificationOutboxItem(
            id=self.id,
            route_id=self.route_id,
            bot_id=self.bot_id,
            chat_id=self.chat_id,
            source_message_id=self.source_message_id,
            enrichment_job_id=self.enrichment_job_id,
            text=self.text,
            status="failed",
            attempts=self.attempts + 1,
            last_error=error,
            created_at=self.created_at,
            sent_at=self.sent_at,
        )
