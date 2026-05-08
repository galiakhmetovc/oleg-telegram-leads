from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.notifications import NotificationOutboxItem

TELEGRAM_SEND_MESSAGE_CHAR_LIMIT = 4096
DEFAULT_BATCH_SEPARATOR = "\n\n---\n\n"
TRUNCATION_SUFFIX = "\n...[truncated]"


@dataclass(frozen=True)
class PackedNotificationBatch:
    item_ids: list[UUID]
    bot_id: str
    chat_id: str
    text: str
    is_full: bool


def pack_notification_batches(
    items: list[NotificationOutboxItem],
    *,
    max_message_chars: int = TELEGRAM_SEND_MESSAGE_CHAR_LIMIT,
    separator: str = DEFAULT_BATCH_SEPARATOR,
) -> list[PackedNotificationBatch]:
    if max_message_chars <= 0:
        raise ValueError("max_message_chars must be positive")

    batches: list[PackedNotificationBatch] = []
    current_ids: list[UUID] = []
    current_text = ""
    current_bot_id = ""
    current_chat_id = ""

    for item in items:
        item_text = _fit_text(item.text, max_message_chars)
        addition = item_text if not current_text else f"{separator}{item_text}"
        should_flush = bool(current_text) and len(current_text) + len(addition) > max_message_chars
        if should_flush:
            batches.append(
                PackedNotificationBatch(
                    item_ids=current_ids,
                    bot_id=current_bot_id,
                    chat_id=current_chat_id,
                    text=current_text,
                    is_full=True,
                )
            )
            current_ids = []
            current_text = ""

        if not current_text:
            current_bot_id = item.bot_id
            current_chat_id = item.chat_id
            current_text = item_text
            current_ids = [item.id]
        else:
            current_text = f"{current_text}{separator}{item_text}"
            current_ids.append(item.id)

        if len(current_text) >= max_message_chars:
            batches.append(
                PackedNotificationBatch(
                    item_ids=current_ids,
                    bot_id=current_bot_id,
                    chat_id=current_chat_id,
                    text=current_text,
                    is_full=True,
                )
            )
            current_ids = []
            current_text = ""

    if current_text:
        batches.append(
            PackedNotificationBatch(
                item_ids=current_ids,
                bot_id=current_bot_id,
                chat_id=current_chat_id,
                text=current_text,
                is_full=False,
            )
        )

    return batches


def _fit_text(text: str, max_message_chars: int) -> str:
    if len(text) <= max_message_chars:
        return text
    if max_message_chars <= len(TRUNCATION_SUFFIX):
        return text[:max_message_chars]
    return f"{text[: max_message_chars - len(TRUNCATION_SUFFIX)]}{TRUNCATION_SUFFIX}"
