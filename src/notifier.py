"""Notifier — отправка результатов в управляющую группу через бота."""

import logging
import logging.handlers
from datetime import datetime
from telethon import TelegramClient

import sys
sys.path.insert(0, "..")
from src import config

logger = logging.getLogger(__name__)

ANTON_TELEGRAM_ID = 352122033  # @AntonBezkrovnyy


class Notifier:
    """Отправляет уведомления о лидах в управляющую группу через бота."""

    def __init__(self, bot_client: TelegramClient):
        self.bot_client = bot_client
        self.group_id = config.GROUP_CHAT_ID
        self.max_leads = getattr(config, "MAX_LEADS_PER_MESSAGE", 10)

    async def notify(self, leads: list[dict], mention_anton: bool = False) -> int:
        """Отправить уведомления о лидах в управляющую группу.

        Args:
            leads: Список найденных лидов
            mention_anton: Если True, @mention Антона в первом сообщении
        """
        if not leads:
            return 0

        sent = 0
        batches = [leads[i:i + self.max_leads] for i in range(0, len(leads), self.max_leads)]

        for i, batch in enumerate(batches):
            text = self._format_message(batch, is_first=(i == 0), mention_anton=mention_anton)
            try:
                await self.bot_client.send_message(self.group_id, text)
                sent += len(batch)
                logger.info("Отправлено %d лидов в группу через бота", len(batch))
            except Exception as e:
                logger.error("Ошибка отправки уведомления через бота: %s", e)

        return sent

    def _format_message(self, leads: list[dict], is_first: bool = False, mention_anton: bool = False) -> str:
        """Форматировать сообщение о лидах с подробной информацией о триггерах."""
        lines = []
        if is_first and mention_anton:
            lines.append(f"tg://user?id={ANTON_TELEGRAM_ID} 🔍 **Найдены потенциальные клиенты ({datetime.now().strftime('%H:%M %d.%m')}):**\n")
        elif is_first:
            lines.append(f"🔍 **Найдены потенциальные клиенты ({datetime.now().strftime('%H:%M %d.%m')}):**\n")

        for lead in leads:
            msg = lead.get("message", {})
            chat_title = msg.get("chat_title", "?")
            text = (msg.get("text", "") or "")[:200]
            sender = msg.get("sender_name", "?")
            link = msg.get("link", "")
            reason = lead.get("reason", "")
            categories = lead.get("categories", [])
            matched_keywords = lead.get("matched_keywords", [])
            source = lead.get("source", "")

            lines.append(f"**📂 {chat_title}** | 👤 {sender}")

            # --- Keyword triggers ---
            if matched_keywords:
                kw_list = []
                for kw in matched_keywords:
                    if isinstance(kw, dict):
                        kw_str = kw.get("keyword", "")
                        score = kw.get("score", 0)
                        kw_list.append(f"{kw_str} ({score}%)")
                    elif isinstance(kw, str):
                        kw_list.append(kw)
                    else:
                        kw_list.append(str(kw))
                lines.append(f"🔑 Слова: {' , '.join(kw_list)}")

            # --- Message text ---
            if text:
                lines.append(f"💬 _{text}_")

            # --- AI verdict ---
            if source == "ai":
                if reason:
                    lines.append(f"🤖 AI: ✅ лид — {reason}")
                else:
                    lines.append(f"🤖 AI: ✅ лид")
            elif source == "keyword":
                lines.append(f"⚠️ Keyword-матч (без AI-подтверждения)")

            # --- Link ---
            if link:
                lines.append(f"🔗 {link}")
            lines.append("")

        return "\n".join(lines)

    async def send_text(self, text: str):
        """Отправить произвольный текст в группу."""
        try:
            await self.bot_client.send_message(self.group_id, text)
        except Exception as e:
            logger.error("Ошибка отправки текста в группу: %s", e)

    async def send_error(self, error: str):
        """Отправить сообщение об ошибке в группу."""
        try:
            await self.bot_client.send_message(
                self.group_id,
                f"❌ **Ошибка:** {error[:500]}"
            )
        except Exception as e:
            logger.error("Ошибка отправки ошибки в группу: %s", e)
