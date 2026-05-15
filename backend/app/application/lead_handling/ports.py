from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.domain.lead_handling import LeadBotSession, LeadClaimResult, LeadHandling
from app.domain.lead_handling import LeadHandlingActionResult, LeadHandlingActor
from app.domain.lead_handling import LeadHandlingEvent, LeadHandlingStatus, LeadHandlingSummary
from app.domain.notifications import TelegramSendResult


class LeadHandlingRepository(Protocol):
    async def claim(
        self,
        *,
        source_message_id: UUID,
        sales_chat_id: str,
        sales_chat_message_id: int,
        actor: LeadHandlingActor,
        notification_outbox_id: UUID | None = None,
    ) -> LeadClaimResult: ...

    async def mark_not_lead(
        self,
        *,
        source_message_id: UUID,
        sales_chat_id: str | None,
        sales_chat_message_id: int | None,
        actor: LeadHandlingActor,
        notification_outbox_id: UUID | None = None,
    ) -> LeadHandlingActionResult: ...

    async def change_status(
        self,
        *,
        source_message_id: UUID,
        status: LeadHandlingStatus,
        actor: LeadHandlingActor,
    ) -> LeadHandlingActionResult: ...

    async def add_comment(
        self,
        *,
        source_message_id: UUID,
        comment: str,
        actor: LeadHandlingActor,
    ) -> LeadHandlingActionResult: ...

    async def list_for_owner(
        self,
        *,
        telegram_user_id: str,
        limit: int,
    ) -> list[LeadHandlingSummary]: ...

    async def get_by_source_message_id(self, source_message_id: UUID) -> LeadHandling | None: ...

    async def set_session_state(
        self,
        *,
        bot_id: str,
        telegram_user_id: str,
        state: str,
        payload: dict[str, object],
    ) -> LeadBotSession: ...

    async def get_session_state(self, *, bot_id: str, telegram_user_id: str) -> LeadBotSession | None: ...

    async def clear_session_state(self, *, bot_id: str, telegram_user_id: str) -> None: ...

    async def record_event(
        self,
        *,
        source_message_id: UUID,
        event_type: str,
        actor: LeadHandlingActor,
        payload: dict[str, object],
    ) -> LeadHandlingEvent: ...


class MessageReviewWriter(Protocol):
    async def save_review(
        self,
        *,
        message_id: str,
        verdict: str | None,
        comment: str,
        tags: list[str],
    ) -> Any: ...

    async def cancel_unsent_notifications_for_message(self, message_id: str, *, reason: str) -> int: ...


class LeadBotSender(Protocol):
    async def send_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> TelegramSendResult: ...

    async def edit_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> TelegramSendResult: ...

    async def answer_callback_query(
        self,
        *,
        bot_token: str,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None: ...
