from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.application.lead_handling.ports import LeadBotSender, LeadHandlingRepository
from app.application.lead_handling.ports import MessageReviewWriter
from app.domain.lead_handling import LeadHandling, LeadHandlingActor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LeadActionCallback:
    action: Literal["claim", "notlead"]
    source_message_id: UUID
    callback_query_id: str
    chat_id: str
    message_id: int
    actor: LeadHandlingActor
    current_text: str


@dataclass(frozen=True)
class LeadActionCallbackResult:
    status: str
    handling: LeadHandling


class HandleLeadActionCallback:
    def __init__(
        self,
        *,
        handling_repository: LeadHandlingRepository,
        review_repository: MessageReviewWriter,
        sender: LeadBotSender,
        bot_token: str,
    ) -> None:
        self._handling_repository = handling_repository
        self._review_repository = review_repository
        self._sender = sender
        self._bot_token = bot_token

    async def execute(self, callback: LeadActionCallback) -> LeadActionCallbackResult:
        if callback.action == "claim":
            return await self._claim(callback)
        return await self._not_lead(callback)

    async def _claim(self, callback: LeadActionCallback) -> LeadActionCallbackResult:
        result = await self._handling_repository.claim(
            source_message_id=callback.source_message_id,
            sales_chat_id=callback.chat_id,
            sales_chat_message_id=callback.message_id,
            actor=callback.actor,
        )
        if result.already_claimed:
            await self._safe_answer_callback(
                callback,
                text=f"Уже взял {_owner_label(result.handling)}",
                show_alert=True,
            )
            return LeadActionCallbackResult(status=result.handling.status, handling=result.handling)

        await self._safe_answer_callback(callback, text="Заявка закреплена за вами")
        await self._safe_edit_group_card(
            callback,
            text=_with_status_line(callback.current_text, f"Статус: Взял {_actor_label(callback.actor)}"),
        )
        return LeadActionCallbackResult(status=result.handling.status, handling=result.handling)

    async def _not_lead(self, callback: LeadActionCallback) -> LeadActionCallbackResult:
        result = await self._handling_repository.mark_not_lead(
            source_message_id=callback.source_message_id,
            sales_chat_id=callback.chat_id,
            sales_chat_message_id=callback.message_id,
            actor=callback.actor,
        )
        await self._review_repository.save_review(
            message_id=str(callback.source_message_id),
            verdict="not_lead",
            comment="lead marked not_lead from telegram bot",
            tags=["telegram_bot"],
        )
        await self._review_repository.cancel_unsent_notifications_for_message(
            str(callback.source_message_id),
            reason="lead marked not_lead from telegram bot",
        )
        await self._safe_answer_callback(callback, text="Отмечено как не лид")
        await self._safe_edit_group_card(
            callback,
            text=_with_status_line(callback.current_text, "Статус: Не лид"),
        )
        return LeadActionCallbackResult(status=result.handling.status, handling=result.handling)

    async def _safe_answer_callback(
        self,
        callback: LeadActionCallback,
        *,
        text: str,
        show_alert: bool = False,
    ) -> None:
        try:
            await self._sender.answer_callback_query(
                bot_token=self._bot_token,
                callback_query_id=callback.callback_query_id,
                text=text,
                show_alert=show_alert,
            )
        except Exception as exc:
            await self._record_callback_failure(
                callback,
                operation="answerCallbackQuery",
                error=exc,
            )
            logger.exception("Failed to answer lead action callback")

    async def _safe_edit_group_card(self, callback: LeadActionCallback, *, text: str) -> None:
        try:
            await self._sender.edit_text(
                bot_token=self._bot_token,
                chat_id=callback.chat_id,
                message_id=callback.message_id,
                text=text,
                reply_markup=_group_lead_card_keyboard(callback.source_message_id),
            )
        except Exception as exc:
            await self._record_callback_failure(
                callback,
                operation="editMessageText",
                error=exc,
            )
            logger.exception("Failed to edit lead action group card")

    async def _record_callback_failure(
        self,
        callback: LeadActionCallback,
        *,
        operation: str,
        error: Exception,
    ) -> None:
        await self._handling_repository.record_event(
            source_message_id=callback.source_message_id,
            event_type="callback_failed",
            actor=callback.actor,
            payload={
                "operation": operation,
                "chat_id": callback.chat_id,
                "message_id": callback.message_id,
                "callback_query_id": callback.callback_query_id,
                "error": str(error) or type(error).__name__,
            },
        )


def _with_status_line(text: str, status_line: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("Статус:"):
            lines[index] = status_line
            return "\n".join(lines)
    return f"{text.rstrip()}\n\n{status_line}"


def _actor_label(actor: LeadHandlingActor) -> str:
    if actor.telegram_username:
        return f"@{actor.telegram_username}"
    return actor.display_name or actor.telegram_user_id


def _owner_label(handling: LeadHandling) -> str:
    if handling.owner_telegram_username:
        return f"@{handling.owner_telegram_username}"
    return handling.owner_display_name or handling.owner_telegram_user_id or "другой оператор"


def _group_lead_card_keyboard(source_message_id: UUID) -> dict[str, object]:
    return {
        "inline_keyboard": [
            [
                {"text": "Взял", "callback_data": f"lh:claim:{source_message_id}"},
                {"text": "Не лид", "callback_data": f"lh:notlead:{source_message_id}"},
            ]
        ]
    }
