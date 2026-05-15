from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.application.lead_handling.ports import LeadBotSender, LeadHandlingRepository
from app.application.lead_handling.ports import MessageReviewWriter
from app.domain.lead_handling import LeadHandling, LeadHandlingActor, LeadHandlingSummary

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


@dataclass(frozen=True)
class PrivateBotMessage:
    chat_id: str
    actor: LeadHandlingActor
    text: str


@dataclass(frozen=True)
class PrivateBotCallback:
    action: str
    source_message_id: UUID | None
    status: str | None
    callback_query_id: str
    chat_id: str
    message_id: int
    actor: LeadHandlingActor


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


class HandleLeadBotPrivateMessage:
    def __init__(
        self,
        *,
        handling_repository: LeadHandlingRepository,
        sender: LeadBotSender,
        bot_token: str,
        bot_id: str = "main_bot",
    ) -> None:
        self._handling_repository = handling_repository
        self._sender = sender
        self._bot_token = bot_token
        self._bot_id = bot_id

    async def execute_message(self, message: PrivateBotMessage) -> None:
        session = await self._handling_repository.get_session_state(
            bot_id=self._bot_id,
            telegram_user_id=message.actor.telegram_user_id,
        )
        if session is not None and session.state == "awaiting_comment":
            await self._handle_comment_text(message, session.payload)
            return
        if message.text.strip() in {"/start", "start"}:
            await self._send_main_menu(message.chat_id)
            return
        if message.text.strip().lower() == "мои лиды":
            await self._send_my_leads(message.chat_id, message.actor)
            return
        await self._send_main_menu(message.chat_id)

    async def execute_callback(self, callback: PrivateBotCallback) -> None:
        if callback.action == "my_leads":
            await self._answer_private_callback(callback)
            await self._send_my_leads(callback.chat_id, callback.actor)
            return
        if callback.action == "open" and callback.source_message_id is not None:
            await self._open_private_card(callback)
            return
        if callback.action == "status" and callback.source_message_id is not None and callback.status:
            await self._change_private_status(callback)
            return
        if callback.action == "comment" and callback.source_message_id is not None:
            await self._start_private_comment(callback)
            return
        await self._answer_private_callback(callback, text="Команда пока недоступна", show_alert=True)

    async def _open_private_card(self, callback: PrivateBotCallback) -> None:
        if callback.source_message_id is None:
            await self._answer_private_callback(callback, text="Лид не найден", show_alert=True)
            return
        handling = await self._handling_repository.get_by_source_message_id(callback.source_message_id)
        if handling is None or handling.owner_telegram_user_id != callback.actor.telegram_user_id:
            await self._answer_private_callback(
                callback,
                text="Этот лид закреплен за другим оператором",
                show_alert=True,
            )
            return
        await self._answer_private_callback(callback)
        await self._safe_send_private_message(
            chat_id=callback.chat_id,
            text=_render_private_lead_card(handling),
            reply_markup=_private_lead_card_keyboard(
                handling.source_message_id,
                telegram_message_url=handling.telegram_message_url,
            ),
            actor=callback.actor,
            source_message_id=handling.source_message_id,
            event_type="callback_failed",
        )

    async def _change_private_status(self, callback: PrivateBotCallback) -> None:
        handling = await self._owned_handling_for_callback(callback)
        if handling is None:
            return
        if callback.status not in {"contacted", "waiting", "closed"}:
            await self._answer_private_callback(callback, text="Неизвестный статус", show_alert=True)
            return
        result = await self._handling_repository.change_status(
            source_message_id=handling.source_message_id,
            status=callback.status,  # type: ignore[arg-type]
            actor=callback.actor,
        )
        await self._answer_private_callback(callback, text="Статус обновлен")
        await self._safe_edit_group_card_after_private_action(
            handling=result.handling,
            actor=callback.actor,
            callback_query_id=callback.callback_query_id,
        )

    async def _start_private_comment(self, callback: PrivateBotCallback) -> None:
        handling = await self._owned_handling_for_callback(callback)
        if handling is None:
            return
        await self._handling_repository.set_session_state(
            bot_id=self._bot_id,
            telegram_user_id=callback.actor.telegram_user_id,
            state="awaiting_comment",
            payload={"source_message_id": str(handling.source_message_id)},
        )
        await self._answer_private_callback(callback, text="Отправьте комментарий сообщением")
        await self._safe_send_private_message(
            chat_id=callback.chat_id,
            text="Отправьте комментарий по этому лиду следующим сообщением.",
            reply_markup=None,
            actor=callback.actor,
            source_message_id=handling.source_message_id,
            event_type="callback_failed",
        )

    async def _handle_comment_text(
        self,
        message: PrivateBotMessage,
        payload: dict[str, object],
    ) -> None:
        source_message_id = _source_message_id_from_payload(payload)
        if source_message_id is None:
            await self._handling_repository.clear_session_state(
                bot_id=self._bot_id,
                telegram_user_id=message.actor.telegram_user_id,
            )
            await self._safe_send_private_message(
                chat_id=message.chat_id,
                text="Не удалось найти лид для комментария.",
                reply_markup=_main_menu_keyboard(),
                actor=message.actor,
                source_message_id=None,
                event_type="message_failed",
            )
            return
        handling = await self._handling_repository.get_by_source_message_id(source_message_id)
        if handling is None or handling.owner_telegram_user_id != message.actor.telegram_user_id:
            await self._safe_send_private_message(
                chat_id=message.chat_id,
                text="Этот лид закреплен за другим оператором",
                reply_markup=_main_menu_keyboard(),
                actor=message.actor,
                source_message_id=source_message_id,
                event_type="message_failed",
            )
            return
        result = await self._handling_repository.add_comment(
            source_message_id=source_message_id,
            comment=message.text.strip(),
            actor=message.actor,
        )
        await self._handling_repository.clear_session_state(
            bot_id=self._bot_id,
            telegram_user_id=message.actor.telegram_user_id,
        )
        await self._safe_send_private_message(
            chat_id=message.chat_id,
            text="Комментарий сохранен.",
            reply_markup=_main_menu_keyboard(),
            actor=message.actor,
            source_message_id=source_message_id,
            event_type="message_failed",
        )
        await self._safe_edit_group_card_after_private_action(
            handling=result.handling,
            actor=message.actor,
            callback_query_id=None,
        )

    async def _send_my_leads(self, chat_id: str, actor: LeadHandlingActor) -> None:
        leads = await self._handling_repository.list_for_owner(
            telegram_user_id=actor.telegram_user_id,
            limit=20,
        )
        await self._safe_send_private_message(
            chat_id=chat_id,
            text=_render_my_leads(leads),
            reply_markup=_my_leads_keyboard(leads),
            actor=actor,
            source_message_id=leads[0].source_message_id if leads else None,
            event_type="message_failed",
        )

    async def _send_main_menu(self, chat_id: str) -> None:
        await self._sender.send_text(
            bot_token=self._bot_token,
            chat_id=chat_id,
            text="Мои лиды",
            reply_markup=_main_menu_keyboard(),
        )

    async def _answer_private_callback(
        self,
        callback: PrivateBotCallback,
        *,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        try:
            await self._sender.answer_callback_query(
                bot_token=self._bot_token,
                callback_query_id=callback.callback_query_id,
                text=text,
                show_alert=show_alert,
            )
        except Exception:
            logger.exception("Failed to answer private lead bot callback")

    async def _safe_send_private_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None,
        actor: LeadHandlingActor,
        source_message_id: UUID | None,
        event_type: str,
    ) -> None:
        try:
            await self._sender.send_text(
                bot_token=self._bot_token,
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            if source_message_id is not None:
                await self._handling_repository.record_event(
                    source_message_id=source_message_id,
                    event_type=event_type,
                    actor=actor,
                    payload={
                        "operation": "send_private_message",
                        "chat_id": chat_id,
                        "error": str(exc) or type(exc).__name__,
                    },
                )
            logger.exception("Failed to send private lead bot message")

    async def _owned_handling_for_callback(self, callback: PrivateBotCallback) -> LeadHandling | None:
        if callback.source_message_id is None:
            await self._answer_private_callback(callback, text="Лид не найден", show_alert=True)
            return None
        handling = await self._handling_repository.get_by_source_message_id(callback.source_message_id)
        if handling is None or handling.owner_telegram_user_id != callback.actor.telegram_user_id:
            await self._answer_private_callback(
                callback,
                text="Этот лид закреплен за другим оператором",
                show_alert=True,
            )
            return None
        return handling

    async def _safe_edit_group_card_after_private_action(
        self,
        *,
        handling: LeadHandling,
        actor: LeadHandlingActor,
        callback_query_id: str | None,
    ) -> None:
        if handling.sales_chat_id is None or handling.sales_chat_message_id is None:
            return
        try:
            await self._sender.edit_text(
                bot_token=self._bot_token,
                chat_id=handling.sales_chat_id,
                message_id=handling.sales_chat_message_id,
                text=_render_group_card_after_private_action(handling),
                reply_markup=_group_lead_card_keyboard(handling.source_message_id),
            )
        except Exception as exc:
            await self._handling_repository.record_event(
                source_message_id=handling.source_message_id,
                event_type="callback_failed",
                actor=actor,
                payload={
                    "operation": "edit_group_card",
                    "chat_id": handling.sales_chat_id,
                    "message_id": handling.sales_chat_message_id,
                    "callback_query_id": callback_query_id,
                    "error": str(exc) or type(exc).__name__,
                },
            )
            logger.exception("Failed to edit group card after private lead action")


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


def _main_menu_keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "Мои лиды", "callback_data": "lh:my_leads"}]]}


def _my_leads_keyboard(leads: list[LeadHandlingSummary]) -> dict[str, Any] | None:
    if not leads:
        return None
    return {
        "inline_keyboard": [
            [
                {
                    "text": _lead_button_text(lead),
                    "callback_data": f"lh:open:{lead.source_message_id}",
                }
            ]
            for lead in leads
        ]
    }


def _private_lead_card_keyboard(
    source_message_id: UUID,
    *,
    telegram_message_url: str | None = None,
) -> dict[str, Any]:
    keyboard: list[list[dict[str, str]]] = [
        [
            {"text": "Написал", "callback_data": f"lh:status:{source_message_id}:contacted"},
            {"text": "Ждет", "callback_data": f"lh:status:{source_message_id}:waiting"},
        ],
        [
            {"text": "Закрыт", "callback_data": f"lh:status:{source_message_id}:closed"},
            {"text": "Комментарий", "callback_data": f"lh:comment:{source_message_id}"},
        ],
    ]
    if telegram_message_url:
        keyboard.append([{"text": "Открыть источник", "url": telegram_message_url}])
    return {"inline_keyboard": keyboard}


def _render_my_leads(leads: list[LeadHandlingSummary]) -> str:
    if not leads:
        return "У вас пока нет взятых лидов."
    lines = ["Мои лиды:"]
    for index, lead in enumerate(leads, start=1):
        title = lead.source_chat_title or "Источник"
        preview = lead.text_preview or "Без текста"
        lines.append(f"{index}. {title}: {preview}")
    return "\n".join(lines)


def _render_private_lead_card(handling: LeadHandling) -> str:
    lines = [
        f"Статус: {_status_label(handling.status)}",
        f"Источник: {handling.source_chat_title or 'не указан'}",
        "",
        handling.text_preview or "Без текста",
    ]
    if handling.telegram_message_url:
        lines.extend(["", handling.telegram_message_url])
    if handling.last_comment:
        lines.extend(["", f"Комментарий: {handling.last_comment}"])
    return "\n".join(lines)


def _render_group_card_after_private_action(handling: LeadHandling) -> str:
    lines = [
        "Лид ПУР",
        "",
        handling.text_preview or "Без текста",
        "",
        f"Статус: {_status_label(handling.status)}",
    ]
    if handling.last_comment:
        lines.extend(["", f"Комментарий: {handling.last_comment}"])
    return "\n".join(lines)


def _lead_button_text(lead: LeadHandlingSummary) -> str:
    title = lead.source_chat_title or "Лид"
    preview = lead.text_preview or ""
    text = f"{title}: {preview}".strip(": ")
    return text[:64]


def _status_label(status: str) -> str:
    return {
        "claimed": "Взял",
        "contacted": "Написал",
        "waiting": "Ждет",
        "closed": "Закрыт",
        "not_lead": "Не лид",
        "new": "Новый",
    }.get(status, status)


def _source_message_id_from_payload(payload: dict[str, object]) -> UUID | None:
    value = payload.get("source_message_id")
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
