"""Pipeline — оркестратор модулей Telegram Leads Finder.

Два Telegram-клиента:
- userbot (Telethon, сессия krab-tg-session.session) — ТОЛЬКО чтение чатов + поиск чатов
- bot (Bot API) — управляющая группа: отправка уведомлений + event handler для команд

Режимы:
  python pipeline.py              — daemon (слушает группу + запускает циклы)
  python pipeline.py --once       — один цикл и выход
  python pipeline.py --daemon     — явный daemon

"""

import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import re
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

from src import config
from src.fetcher import Fetcher
from src.keyword_scanner import KeywordScanner
from src.ai_analyzer import AIAnalyzer
from src.notifier import Notifier

import json as _json

# ── Logging setup ────────────────────────────────────
_log_level = getattr(logging, os.getenv("LOG_LEVEL", "DEBUG"), logging.DEBUG)
_log_dir = Path(os.getenv("LOG_DIR", str(Path(__file__).resolve().parent.parent / "artifacts" / "logs")))
_log_dir.mkdir(parents=True, exist_ok=True)

_log_file = _log_dir / "leads-finder.log"
_file_handler = logging.handlers.RotatingFileHandler(
    str(_log_file), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_file_handler.setLevel(logging.DEBUG)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), _file_handler],
)
logger = logging.getLogger("pipeline")
logger.info("Logging: level=%s, file=%s", _log_level, _log_file)

# ── Graceful shutdown ────────────────────────────────────
_shutdown = False


def _signal_handler(sig, frame):
    global _shutdown
    logger.info("Получен сигнал %s, завершаем...", sig)
    _shutdown = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ── Антон — для @mention при найденных лидах ────────────
ANTON_TELEGRAM_ID = 352122033  # @AntonBezkrovnyy

# ── Regex для парсинга Telegram-ссылок ──────────────────
TG_LINK_RE = re.compile(
    r'(?:https?://)?t\.me/([^/]+)/(\d+)',
    re.IGNORECASE,
)

# ── Команды управляющей группы ──────────────────────────
HELP_TEXT = """🤖 **Leads Finder — Команды**

/status — статус системы
/run — запустить проверку вручную
/list — список мониторимых чатов
/reset <chat_id> — сбросить чекпоинт чата
/remove <chat_id> — удалить чат из мониторинга
/leads — последние найденные лиды
/help — эта справка

📦 **Добавление чатов:**
1. Перешлите сообщение из чата — он будет добавлен в мониторинг
2. Или отправьте ссылку на сообщение (t.me/chat/123)

💡 **Обучение AI:**
Перешлите сообщение из уже мониторимого чата — оно сохранится как пример лида.

"""

MONTHS_RU = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _format_date_ru(dt: datetime) -> str:
    return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year} года, {dt.hour:02d}:{dt.minute:02d}"


class Pipeline:
    """Главный оркестратор pipeline."""

    def __init__(self, bot, userbot):
        self.bot = bot
        self.userbot = userbot
        self.bot_user_id = None
        self.scanner = KeywordScanner()
        self.analyzer = AIAnalyzer()
        self.notifier = Notifier(bot)

    # ── Основной цикл ────────────────────────────────────
    async def run_once(self) -> str:
        """Один полный цикл: fetch → keyword scan → AI analyze → notify."""
        try:
            chats = config.load_chats()
            if not chats:
                await self._send_status(
                    chats_count=0, fetched=0, kw=0, ai=0, leads=0,
                    message="📭 Нет чатов для мониторинга. Перешлите сообщение из чата, чтобы добавить."
                )
                return "Нет чатов для мониторинга"

            # 1. Fetch
            fetcher = Fetcher(self.userbot)

            # 1a. Проверяем доступ ко всем чатам (captch'а, бан)
            skipped_chats = []
            for chat in chats:
                chat_id = chat.get("id")
                chat_title = chat.get("title", str(chat_id))
                try:
                    access = await fetcher.check_chat_access(chat_id, chat_title)
                    if not access.get("ok") and access.get("captcha"):
                        skipped_chats.append(chat_title)
                        logger.warning("Чат %s пропущен: captch'а", chat_title)
                except Exception as e:
                    logger.warning("Проверка доступа %s: %s", chat_title, e)

            if skipped_chats:
                await self.bot.send_message(
                    config.GROUP_CHAT_ID,
                    "⚠️ **Чаты с проблемами доступа:**\n\n" +
                    "\n".join(f"• {t}" for t in skipped_chats) +
                    "\n\nЗайдите от @krab_ai_agent и нажмите кнопку captch'и.",
                    parse_mode="markdown",
                )

            messages = await fetcher.fetch_all()

            if not messages:
                await self._send_status(
                    chats_count=len(chats), fetched=0, kw=0, ai=0, leads=0,
                    message=f"💤 Новых сообщений нет ({len(chats)} чатов проверено)"
                )
                return f"Новых сообщений нет ({len(chats)} чатов)"

            logger.info("Получено %d сообщений из %d чатов", len(messages), len(chats))
            for _m in messages[:5]:
                logger.debug("   msg id=%s from=%s text=%r", _m.get("id"), _m.get("sender_name", "?"), _m.get("text", "")[:80])

            # 2. Keyword scan
            keyword_results = self.scanner.scan(messages)
            logger.info("Keyword matches: %d / %d", len(keyword_results), len(messages))
            for _kw in keyword_results[:5]:
                logger.debug("   kw hit: msg_id=%s words=%s", _kw.get("message", {}).get("id"), _kw.get("matched_keywords"))

            # 3. AI analyze — отправляем ВСЕ сообщения (ADR-002)
            ai_results = await self.analyzer.analyze(messages)
            logger.info("AI leads: %d (model=%s)", len(ai_results), config.ZAI_MODEL)
            for _a in ai_results[:5]:
                logger.debug("   AI lead: id=%s reason=%r", _a.get("id"), _a.get("reason", "")[:100])

            # 4. Обогащаем AI-результаты keyword-данными
            kw_map = {}
            for kw_result in keyword_results:
                msg_id = kw_result.get("message", {}).get("id")
                if msg_id:
                    kw_map[msg_id] = kw_result.get("matched_keywords", [])

            enriched_leads = []
            for lead in ai_results:
                msg_id = lead.get("message", {}).get("id")
                lead["matched_keywords"] = kw_map.get(msg_id, [])
                lead["categories"] = kw_map.get(msg_id, [])
                enriched_leads.append(lead)

            # 4b. Keyword fallback: если AI пустой, но keyword нашёл — логируем, НЕ отправляем
            if not ai_results and keyword_results:
                logger.info(
                    "AI вернул 0 лидов, keyword scanner нашёл %d совпадений (не отправляем — только AI лиды)",
                    len(keyword_results),
                )

            # 5. Dedup с историей
            # 5. Dedup с историей
            # Проверяем, есть ли pending_scan_ids (recheck mode)
            pending_ids = set()
            for chat in chats:
                pids = chat.get("pending_scan_ids")
                if pids:
                    pending_ids.update(pids)
            new_leads = self._dedup_leads(enriched_leads, skip_ids=pending_ids if pending_ids else None)

            if new_leads:
                await self.notifier.notify(new_leads, mention_anton=True)
                await self._save_leads(new_leads)
                self._save_to_obsidian(messages, keyword_results, new_leads)
                logger.info("📤 Отправлено %d лидов, @Anton уведомлён", len(new_leads))
            else:
                await self._send_status(
                    chats_count=len(chats),
                    fetched=len(messages),
                    kw=len(keyword_results),
                    ai=len(ai_results),
                    leads=0,
                    message=f"✅ Проверено {len(messages)} сообщений, лидов нет"
                )
            return f"Сообщений: {len(messages)} | Keyword: {len(keyword_results)} | AI: {len(ai_results)} | Новых лидов: {len(new_leads)}"
            return f"Сообщений: {len(messages)} | Keyword: {len(keyword_results)} | AI: {len(ai_results)} | Новых лидов: {len(new_leads)}"

        except Exception as e:
            logger.error("PIPELINE CYCLE ERROR: %s", e, exc_info=True)
            await self.notifier.send_error(str(e))
            raise

    # ── Команды ──────────────────────────────────────────
    async def cmd_status(self, chat_id: int):
        """Статус системы."""
        chats = config.load_chats()
        leads_count = self._count_leads()
        checkpoints = config.load_checkpoints()

        lines = [
            "📊 **Статус Leads Finder:**\n",
            f"📂 Чатов: {len(chats)}",
            f"🎯 Лидов найдено: {leads_count}",
            f"📎 Чекпоинтов: {len(checkpoints)}",
            f"🤖 Модель: {config.ZAI_MODEL}",
            f"⏱ Интервал: {config.POLL_INTERVAL} сек",
            f"🔑 Keyword-порог: {config.KEYWORD_THRESHOLD}%",
        ]
        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="markdown")

    async def cmd_list(self, chat_id: int):
        """Список мониторимых чатов."""
        lines = [f"📂 **Мониторимые чаты ({len(chats)}):**\n"]
        for c in chats:
            cp = checkpoints.get(str(c.get("id", "?")), "нет")
            status = c.get("status", "active")
            status_emoji = "🟢" if status == "active" else "⚠️" if status == "captcha" else "⚪"
            lines.append(f"{status_emoji} **{c.get('title', '?')}**")
            lines.append(f"   ID: `{c.get('id')}` | Чекпоинт: {cp}")
            if c.get("username"):
                lines.append(f"   @{c['username']}")
            lines.append("")

        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="markdown")

    async def cmd_leads(self, chat_id: int):
        """Показать последние лиды."""
        leads = self._load_leads()
        if not leads:
            await self.bot.send_message(chat_id, "📭 Лидов пока нет.")
            return

        last_leads = leads[-10:]
        lines = [f"📋 **Последние {len(last_leads)} лидов (из {len(leads)}):**\n"]
        for i, lead in enumerate(last_leads, 1):
            lines.append(f"**{i}.** [{lead.get('chat_title', '?')}]")
            text = lead.get("text", "")
            if text:
                lines.append(f"💬 _{text[:100]}_")
            # Keyword triggers
            matched_kw = lead.get("categories", [])
            if matched_kw:
                kw_names = []
                for kw in matched_kw:
                    if isinstance(kw, dict):
                        kw_names.append(f"{kw.get('keyword', '')} ({kw.get('score', 0)}%)")
                    elif isinstance(kw, str):
                        kw_names.append(kw)
                if kw_names:
                    lines.append(f"🔑 Слова: {' , '.join(kw_names)}")
            # AI verdict
            source = lead.get("source", "")
            reason = lead.get("reason", "")
            if source == "ai":
                lines.append(f"🤖 AI: ✅ лид — {reason}" if reason else "🤖 AI: ✅ лид")
            elif source == "keyword":
                lines.append("⚠️ Keyword-матч (без AI)")
            if lead.get("link"):
                lines.append(f"🔗 {lead['link']}")
            lines.append("")
        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="markdown")

    async def cmd_recheck(self, chat_id: int, arg: str):
        """Перепроверить конкретные сообщения через AI.

        Поддерживает:
        - Один ID: /recheck 716288
        - Несколько ID через пробел: /recheck 716254 716288
        - Ссылку: /recheck https://t.me/chat/716288
        """
        # Парсим message IDs из аргумента
        msg_ids = []

        # Ссылка t.me/chat/123
        link_match = TG_LINK_RE.search(arg)
        if link_match:
            msg_ids.append(int(link_match.group(2)))
        else:
            # Пробуем распарсить как числа
            for token in arg.split():
                token = token.strip()
                # Проверяем, не ссылка ли это частичная
                sub_match = TG_LINK_RE.search(token)
                if sub_match:
                    msg_ids.append(int(sub_match.group(2)))
                else:
                    try:
                        msg_ids.append(int(token))
                    except ValueError:
                        pass

        if not msg_ids:
            await self.bot.send_message(chat_id, "❌ Не удалось распознать ID сообщений.")
            return

        # Убираем дубли
        msg_ids = list(dict.fromkeys(msg_ids))

        # Определяем чат: берем первый мониторящийся или пытаемся найти из ссылки
        chats = config.load_chats()
        if not chats:
            await self.bot.send_message(chat_id, "📭 Нет чатов для мониторинга.")
            return

        # Если была ссылка — определяем чат из username
        target_chat = None
        link_match = TG_LINK_RE.search(arg)
        if link_match:
            link_username = link_match.group(1)
            for c in chats:
                uname = (c.get("username") or "").lstrip("@").lower()
                if uname == link_username.lower():
                    target_chat = c
                    break

        if not target_chat:
            if len(chats) == 1:
                target_chat = chats[0]
            else:
                await self.bot.send_message(
                    chat_id,
                    f"❓ Укажите чат (несколько в мониторинге):\n" +
                    "\n".join(f"• {c.get('title', '?')} (id={c.get('id')})" for c in chats) +
                    f"\n\nИспользуйте: `/recheck <chat_id> <msg_ids>`",
                    parse_mode="markdown",
                )
                return

        chat_id_int = target_chat.get("id")
        chat_title = target_chat.get("title", str(chat_id_int))

        # Устанавливаем pending_scan_ids
        await self.bot.send_message(
            chat_id,
            f"🔍 Перепроверяю {len(msg_ids)} сообщений в **{chat_title}**...\n"
            f"📋 ID: {', '.join(str(i) for i in msg_ids)}",
            parse_mode="markdown",
        )
        logger.info("recheck: %d сообщений для чата %s: %s", len(msg_ids), chat_title, msg_ids)

        # Сохраняем pending_scan_ids в конфиг чата
        target_chat["pending_scan_ids"] = msg_ids
        config.save_chats(chats)

        # Сбрасываем лиды (чтобы дедуп не мешал)
        # НЕ сбрасываем checkpoint — он останется как есть

        # Запускаем один цикл
        try:
            result = await self.run_once()
            await self.bot.send_message(chat_id, f"✅ Перепроверка завершена.\n{result}")
        except Exception as e:
            logger.error("Ошибка перепроверки: %s", e, exc_info=True)
            await self.bot.send_message(chat_id, f"❌ Ошибка: {e}")
    async def cmd_leads(self, chat_id: int):
        """Показать последние лиды."""
        leads = self._load_leads()
        if not leads:
            await self.bot.send_message(chat_id, "📭 Лидов пока нет.")
            return

        last_leads = leads[-10:]
        lines = [f"📋 **Последние {len(last_leads)} лидов (из {len(leads)}):**\n"]
        for i, lead in enumerate(last_leads, 1):
            lines.append(f"**{i}.** [{lead.get('chat_title', '?')}]")
            text = lead.get("text", "")
            if text:
                lines.append(f"💬 _{text[:100]}_")
            # Keyword triggers
            matched_kw = lead.get("categories", [])
            if matched_kw:
                kw_names = []
                for kw in matched_kw:
                    if isinstance(kw, dict):
                        kw_names.append(f"{kw.get('keyword', '')} ({kw.get('score', 0)}%)")
                    elif isinstance(kw, str):
                        kw_names.append(kw)
                if kw_names:
                    lines.append(f"🔑 Слова: {' , '.join(kw_names)}")
            # AI verdict
            source = lead.get("source", "")
            reason = lead.get("reason", "")
            if source == "ai":
                lines.append(f"🤖 AI: ✅ лид — {reason}" if reason else "🤖 AI: ✅ лид")
            elif source == "keyword":
                lines.append("⚠️ Keyword-матч (без AI)")
            if lead.get("link"):
                lines.append(f"🔗 {lead['link']}")
            lines.append("")
        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="markdown")

    async def cmd_run(self, chat_id: int):
        """Запустить проверку вручную."""
        await self.bot.send_message(chat_id, "▶ Запускаю проверку...")
        try:
            result = await self.run_once()
        except Exception as e:
            logger.error("Ошибка ручного запуска: %s", e, exc_info=True)
            await self.bot.send_message(chat_id, f"❌ Ошибка: {e}")

    async def cmd_reset(self, chat_id: int, chat_ref: str):
        """Сбросить чекпоинт чата."""
        chat_id_int = await self._resolve_chat_id(chat_ref, chat_id)
        if chat_id_int is None:
            return

        checkpoints = config.load_checkpoints()
        checkpoints[str(chat_id_int)] = 0
        config.save_checkpoints(checkpoints)
        await self.bot.send_message(chat_id, f"🔄 Чекпоинт чата `{chat_id_int}` сброшен.", parse_mode="markdown")

    async def cmd_remove(self, chat_id: int, chat_ref: str):
        """Удалить чат из мониторинга."""
        chat_id_int = await self._resolve_chat_id(chat_ref, chat_id)
        if chat_id_int is None:
            return

        chats = config.load_chats()
        before = len(chats)
        chats = [c for c in chats if c.get("id") != chat_id_int]
        if len(chats) < before:
            config.save_chats(chats)
            await self.bot.send_message(chat_id, f"🗑 Чат `{chat_id_int}` удалён из мониторинга.", parse_mode="markdown")
        else:
            await self.bot.send_message(chat_id, f"⚠️ Чат `{chat_id_int}` не найден в списке.", parse_mode="markdown")
        chats = config.load_chats()
        existing = next((c for c in chats if c.get("id") == chat_id), None)

        if existing:
            # Сценарий 2: пример лида
            fwd_text = fwd.message or ""
            sender_name = fwd.from_name or "Unknown"
            await self._save_lead_example_with_text(event, chat_id, existing, fwd_text, fwd.id, sender_name)
        else:
            # Сценарий 1: добавить чат
            await self._add_chat(event, chat_id, fwd.from_name or "Unknown", None, fwd.id)

    async def handle_link(self, event: events.NewMessage.Event, link: str):
        """Обрабатывает ссылку t.me/chat/123."""
        match = TG_LINK_RE.search(link)
        if not match:
            await self.bot.send_message(event.chat_id, "⚠️ Не удалось распарсить ссылку.\nФормат: `t.me/chat_name/123`")
            return

        username = match.group(1)
        message_id = int(match.group(2))

        # Шаг 1: Мгновенный отклик
        await self.bot.send_message(
            event.chat_id,
            f"🔗 Принял, ссылка валидирована.\nПытаюсь присоединиться к чату **@{username}**...",
            parse_mode="markdown",
        )

        # Шаг 2: Резолвим chat_id через userbot
        try:
            entity = await self.userbot.get_entity(username)
            from telethon.tl.types import Channel, Chat
            if isinstance(entity, Channel):
                chat_id = int(f"-100{entity.id}")
            elif isinstance(entity, Chat):
                chat_id = -entity.id
            elif hasattr(entity, "id"):
                chat_id = entity.id
            else:
                await self.bot.send_message(event.chat_id, "⚠️ Не удалось определить ID чата по ссылке.")
                return

            chat_title = getattr(entity, "title", username) or getattr(entity, "first_name", username) or username
        except Exception as e:
            await self.bot.send_message(event.chat_id, f"⚠️ Не удалось найти чат `@{username}`: {e}")
            return

        # Шаг 3: Проверяем, уже в мониторинге?
        chats = config.load_chats()
        existing = next((c for c in chats if c.get("id") == chat_id), None)

        if existing:
            # Сценарий 2: чат уже мониторится → пример лида
            try:
                msgs = await self.userbot.get_messages(chat_id, ids=message_id)
                fwd_text = msgs.text if msgs and msgs.text else ""
            except Exception:
                fwd_text = ""
            await self._save_lead_example_with_text(event, chat_id, existing, fwd_text, message_id)
            return

        # Шаг 4: Новый чат — проверка доступа + добавление
        await self._add_chat(event, chat_id, chat_title, username, message_id)

    # ── Внутренние: добавление чата ──────────────────────
    async def _add_chat(self, event, chat_id, chat_title, username, checkpoint_msg_id):
        """Добавляет чат в мониторинг с проверкой доступа."""
        from telethon.tl.types import Channel, Chat

        # Попробуем определить username через entity
        resolved_username = username
        if not resolved_username:
            try:
                entity = await self.userbot.get_entity(chat_id)
                resolved_username = getattr(entity, "username", None)
                if resolved_username:
                    resolved_username = f"@{resolved_username}"
            except Exception:
                pass

        # Мгновенный отклик
        await self.bot.send_message(
            event.chat_id,
            f"📨 Принял, сообщение валидировано.\nПытаюсь присоединиться к чату **{chat_title}**...",
            parse_mode="markdown",
        )

        # Проверяем доступ
        fetcher = Fetcher(self.userbot)
        access = await fetcher.check_chat_access(chat_id, chat_title)

        # Сохраняем чекпоинт: message_id - 1, чтобы self.include сообщение с этим ID
        checkpoints = config.load_checkpoints()
        checkpoint_value = max(0, checkpoint_msg_id - 1) if checkpoint_msg_id else 0
        checkpoints[str(chat_id)] = checkpoint_value
        config.save_checkpoints(checkpoints)
        logger.info("Чекпоинт для %s: %d (message_id=%d, checkpoint-1)", chat_title, checkpoint_value, checkpoint_msg_id)

        if not access.get("ok"):
            reason = access.get("reason", "unknown")
            chats = config.load_chats()
            if not any(c.get("id") == chat_id for c in chats):
                new_chat = {
                    "id": chat_id,
                    "title": chat_title,
                    "username": resolved_username,
                    "added": datetime.now().isoformat(),
                    "status": "captcha" if reason == "captcha" else "blocked",
                }
                chats.append(new_chat)
                config.save_chats(chats)
            await self.bot.send_message(
                event.chat_id,
                access.get("message", "⚠️ Проблема с доступом к чату."),
                parse_mode="markdown",
            )
            logger.warning("Чат %s добавлен с проблемой: %s", chat_title, reason)
            return

        # Всё ОК — ставим на мониторинг
        now = datetime.now()
        chats = config.load_chats()
        new_chat = {
            "id": chat_id,
            "title": chat_title,
            "username": resolved_username,
            "added": now.isoformat(),
            "status": "active",
            "initial_scan_msg_id": checkpoint_msg_id if checkpoint_msg_id else None,
        }
        chats.append(new_chat)
        config.save_chats(chats)

        extra = f"\n🔗 {resolved_username}" if resolved_username else ""
        await self.bot.send_message(
            event.chat_id,
            f'✅ **Группа "{chat_title}" поставлена на мониторинг**\n\n'
            f"📅 {_format_date_ru(now)}\n"
            f"{extra}\n"
            f"🔑 ID: `{chat_id}`\n"
            f"📍 Чекпоинт: сообщение {checkpoint_msg_id} (история до него пропущена)\n\n"
            f"Следующий цикл начнёт читать новые сообщения.",
            parse_mode="markdown",
        )
        logger.info("Добавлен чат %s (%s), чекпоинт=%d (msg_id=%d)", chat_title, chat_id, checkpoint_value, checkpoint_msg_id)

    # ── Внутренние: извлечение chat_id из пересылки ──────
    def _extract_chat_id_from_forward(self, fwd) -> int | None:
        """Извлекает chat_id напрямую из объекта пересылки."""
        if fwd.chat_id:
            return fwd.chat_id

        if fwd.from_id:
            if hasattr(fwd.from_id, "channel_id") and fwd.from_id.channel_id:
                return int(f"-100{fwd.from_id.channel_id}")
            elif hasattr(fwd.from_id, "chat_id") and fwd.from_id.chat_id:
                return fwd.from_id.chat_id
            elif hasattr(fwd.from_id, "user_id") and fwd.from_id.user_id:
                return None  # Это ЛС

        return None

    async def _find_chat_via_userbot(self, fwd) -> int | None:
        """Fallback: ищет чат через userbot по from_name."""
        if not fwd.from_name:
            return None

        search_name = fwd.from_name
        logger.info("Ищем чат через userbot по имени: %s", search_name)

        try:
            from telethon.tl.types import Channel, Chat
            async for dialog in self.userbot.iter_dialogs(limit=200):
                entity = dialog.entity
                title = getattr(entity, "title", "") or ""
                username = getattr(entity, "username", "") or ""

                if (search_name.lower() in title.lower() or
                    search_name.lower() in username.lower() or
                    title.lower() in search_name.lower()):

                    if isinstance(entity, (Channel, Chat)):
                        if isinstance(entity, Channel):
                            chat_id = int(f"-100{entity.id}")
                        else:
                            chat_id = -entity.id
                        logger.info("Найден чат '%s' (ID: %s) по имени '%s'", title, chat_id, search_name)
                        return chat_id
        except Exception as e:
            logger.warning("Ошибка поиска чата через userbot: %s", e)

        return None

    # ── Внутренние: сохранение примера лида ──────────────
    async def _save_lead_example_with_text(self, event, chat_id, existing, fwd_text, message_id, sender_name="Unknown"):
        """Сохраняет пример лида в БД и отправляет подтверждение."""
        if not fwd_text:
            await self.bot.send_message(
                event.chat_id,
                "⚠️ Сообщение не содержит текста, не могу сохранить как пример лида."
            )
            return

        example = {
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_title": existing.get("title", str(chat_id)),
            "text": fwd_text,
            "sender_name": sender_name,
            "date": datetime.now().isoformat(),
            "added_by": event.sender_id,
        }
        examples_file = config.DATA_DIR / "lead_examples.json"
        examples = []
        if examples_file.exists():
            try:
                with open(examples_file, "r", encoding="utf-8") as f:
                    examples = json.load(f)
            except (json.JSONDecodeError, IOError):
                examples = []

        # Дедупликация по (chat_id, message_id)
        example_key = (chat_id, message_id)
        if not any((e.get("chat_id"), e.get("message_id")) == example_key for e in examples):
            examples.append(example)
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(examples_file, "w", encoding="utf-8") as f:
                json.dump(examples, f, ensure_ascii=False, indent=2)

            total = len(examples)
            await self.bot.send_message(
                event.chat_id,
                f"✅ **Пример для обнаружения лида получен, обновляю базу данных.**\n\n"
                f"📂 Чат: {existing.get('title', str(chat_id))}\n"
                f"💬 _{(fwd_text[:150])}{'...' if len(fwd_text) > 150 else ''}_\n\n"
                f"📊 Всего примеров в базе: {total}",
                parse_mode="markdown",
            )
            logger.info("Сохранён пример лида из чата %s (всего: %d)", chat_id, total)
        else:
            await self.bot.send_message(
                event.chat_id,
                f"ℹ️ Это сообщение уже есть в базе примеров.\n"
                f"📂 Чат: {existing.get('title', str(chat_id))}",
            )

    # ── Внутренние: resolve chat_id ──────────────────────
    async def _resolve_chat_id(self, chat_ref: str, notify_chat_id: int) -> int | None:
        """Разрешить chat_ref (ID или часть title) в int chat_id."""
        try:
            return int(chat_ref)
        except ValueError:
            chats = config.load_chats()
            found = None
            for c in chats:
                if chat_ref.lower() in c.get("title", "").lower():
                    found = c
                    break
            if not found:
                await self.bot.send_message(notify_chat_id, f"❌ Чат не найден: {chat_ref}")
                return None
            return found["id"]

    # ── Внутренние: merge, dedup, save ───────────────────
    def _merge_results(self, keyword_results: list, ai_results: list) -> list:
        """Объединить keyword и AI результаты, dedup по message_id."""
        seen_ids = set()
        all_leads = []

        for lead in ai_results:
            msg_id = lead.get("message", {}).get("id")
            if msg_id and msg_id not in seen_ids:
                seen_ids.add(msg_id)
                all_leads.append(lead)

        for lead in keyword_results:
            msg_id = lead.get("message", {}).get("id")
            if msg_id and msg_id not in seen_ids:
                seen_ids.add(msg_id)
                all_leads.append(lead)

        return all_leads

    def _dedup_leads(self, leads: list, skip_ids: set = None) -> list:
        """Убрать лиды, которые уже были отправлены.

        Args:
            leads: список найденных лидов
            skip_ids: если передан, только эти ID исключаются из dedup (recheck)
        """
        if skip_ids is not None:
            # Recheck mode: исключаем из dedup только указанные ID
            seen = self._load_seen_lead_ids() - skip_ids
            logger.info("dedup: recheck mode, исключаем из seen: %s", skip_ids)
        else:
            seen = self._load_seen_lead_ids()
        return [l for l in leads if l.get("message", {}).get("id") not in seen]

    def _load_seen_lead_ids(self) -> set:
        """Загрузить ID уже отправленных лидов."""
        leads_file = config.DATA_DIR / "leads.json"
        if leads_file.exists():
            try:
                with open(leads_file, "r", encoding="utf-8") as f:
                    return {lead.get("id") for lead in json.load(f)}
            except (json.JSONDecodeError, KeyError):
                return set()
        return set()

    def _load_leads(self) -> list:
        """Загрузить все лиды."""
        leads_file = config.DATA_DIR / "leads.json"
        if leads_file.exists():
            try:
                with open(leads_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    def _count_leads(self) -> int:
        existing = self._load_leads()
        for lead in leads:
            existing.append({
                "id": lead.get("message", {}).get("id"),
                "chat_id": lead.get("message", {}).get("chat_id"),
                "chat_title": lead.get("message", {}).get("chat_title"),
                "text": lead.get("message", {}).get("text", "")[:500],
                "sender_name": lead.get("message", {}).get("sender_name"),
                "link": lead.get("message", {}).get("link"),
                "reason": lead.get("reason", ""),
                "source": lead.get("source", ""),
                "categories": lead.get("categories", []),
                "date": datetime.now().isoformat(),
            })
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(leads_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    async def _send_status(self, chats_count: int, fetched: int, kw: int, ai: int, leads: int, message: str):
        """Отправить статусный репорт в группу."""
        await self.notifier.send_text(f"📊 {message}\n\n✉️ {fetched} сообщений | 🤖 {ai} AI-лидов | 🎯 {leads} новых | 📂 {chats_count} чатов")

    def _save_to_obsidian(self, messages: list, keyword_results: list, new_leads: list):
        """Сохраняет результаты цикла в Obsidian."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            obsidian_dir = Path(config.OBSIDIAN_DIR)
            obsidian_dir.mkdir(parents=True, exist_ok=True)
            report_path = obsidian_dir / f"{today}.md"

            timestamp = datetime.now().strftime("%H:%M")
            entry = (
                f"\n## Цикл {timestamp}\n"
                f"- Сообщений: {len(messages)}\n"
                f"- Keyword matches: {len(keyword_results)}\n"
                f"- Новых лидов: {len(new_leads)}\n"
            )
            if new_leads:
                entry += "\n### Лиды\n"
                for lead in new_leads:
                    entry += f"- **{lead.get('message', {}).get('chat_title', '?')}** — {(lead.get('message', {}).get('text', '') or '')[:100]}\n"

            if report_path.exists():
                with open(report_path, "a", encoding="utf-8") as f:
                    f.write(entry)
            else:
                header = f"# Leads Finder Report — {today}\n"
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(header + entry)

            logger.info("Отчёт сохранён: %s", report_path)
        except Exception as e:
            logger.error("Ошибка сохранения в Obsidian: %s", e)


async def daemon_mode() -> None:
    """Daemon: слушает управляющую группу + запускает циклы по расписанию."""
    global _shutdown

    # Bot client — управляющая группа
    bot = TelegramClient(
        str(config.BOT_SESSION_PATH),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH,
    )
    await bot.start(bot_token=config.BOT_TOKEN)

    # Verify bot started correctly
    me = await bot.get_me()
    if not me or not me.bot:
        logger.error("❌ Не удалось запустить бота! Проверьте BOT_TOKEN.")
        return

    logger.info("🤖 Бот запущен: @%s (id=%s)", me.username, me.id)
    bot_user_id = me.id

    # Test message sending to group
    try:
        test_msg = await bot.send_message(config.GROUP_CHAT_ID, "🧪 Проверка доступа...")
        await asyncio.sleep(1)
        await test_msg.delete()
        logger.info("✅ Бот может отправлять сообщения в группу")
    except Exception as e:
        logger.error("❌ Бот не может отправлять сообщения в группу: %s", e)
        logger.error("Проверьте: 1) Бот добавлен в группу  2) Group Privacy = Disable")
        await asyncio.sleep(5)
        return

    # Регистрируем команды бота
    await bot(SetBotCommandsRequest(
        scope=BotCommandScopeDefault(),
        lang_code="",
        commands=[
            BotCommand(command="status", description="Статус системы"),
            BotCommand(command="run", description="Запустить проверку сейчас"),
            BotCommand(command="list", description="Список чатов под мониторингом"),
            BotCommand(command="reset", description="Сбросить чекпоинт чата"),
            BotCommand(command="remove", description="Удалить чат из мониторинга"),
            BotCommand(command="remove", description="Удалить чат из мониторинга"),
            BotCommand(command="leads", description="Последние найденные лиды"),
            BotCommand(command="recheck", description="Перепроверить конкретные сообщения"),
            BotCommand(command="help", description="Справка"),
        ],
    ))
    logger.info("📋 Команды бота зарегистрированы")

    # Userbot client — чтение чатов (постоянное подключение)
    userbot = TelegramClient(
        str(config.SESSION_PATH),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH,
    )
    await userbot.connect()
    if not await userbot.is_user_authorized():
        logger.error("❌ Userbot не авторизован! Проверьте сессию.")
        await bot.send_message(config.GROUP_CHAT_ID, "❌ Userbot не авторизован. Pipeline не запущен.")
        return

    userbot_me = await userbot.get_me()
    logger.info("👤 Userbot подключён: %s (ID: %s)", userbot_me.first_name, userbot_me.id)

    pipeline = Pipeline(bot, userbot)
    pipeline.bot_user_id = bot_user_id

    # Handler для всех сообщений в группе
    @bot.on(events.NewMessage(chats=config.GROUP_CHAT_ID))
    async def group_message_handler(event):
        # Игнорируем свои собственные сообщения
        if event.sender_id == bot_user_id:
            return

        text = (event.text or "").strip()
        logger.info(
            "📨 Входящее от %s: text=%r fwd=%s",
            event.sender_id,
            text[:80] if text else None,
            event.forward is not None,
        )

        # Пересылки
        if event.forward:
            await pipeline.handle_forward(event)
            return

        # Ссылки t.me/.../123
        link_match = TG_LINK_RE.search(text)
        if link_match:
            logger.info("🔗 Ссылка обнаружена: %s", text[:80])
            try:
                await pipeline.handle_link(event, text)
            except Exception as e:
                logger.error("Ошибка обработки ссылки: %s", e, exc_info=True)
                await bot.send_message(event.chat_id, f"❌ Ошибка: {e}")
            return

        # Команды
        if not text.startswith("/"):
            return

        logger.info("🛠 Команда от %s: %s", event.sender_id, text)
        cmd = text.split("@")[0].strip().lower()

        try:
            if cmd == "/help":
                await bot.send_message(event.chat_id, HELP_TEXT, parse_mode="markdown")
            elif cmd == "/status":
                await pipeline.cmd_status(event.chat_id)
            elif cmd == "/list":
                await pipeline.cmd_list(event.chat_id)
            elif cmd == "/leads":
                await pipeline.cmd_leads(event.chat_id)
            elif cmd == "/run":
                await pipeline.cmd_run(event.chat_id)
            elif cmd.startswith("/reset"):
                arg = text[6:].strip()
                if not arg:
                    await bot.send_message(event.chat_id, "❌ Укажите chat_id: `/reset <chat_id>`\nИли используйте `/list` для просмотра.", parse_mode="markdown")
                    return
                await pipeline.cmd_reset(event.chat_id, arg)
            elif cmd.startswith("/remove"):
                arg = text[7:].strip()
                if not arg:
                    await bot.send_message(event.chat_id, "❌ Укажите chat_id: `/remove <chat_id>`\nИли используйте `/list` для просмотра.", parse_mode="markdown")
                    return
                await pipeline.cmd_remove(event.chat_id, arg)
            elif cmd.startswith("/recheck"):
                # /recheck <message_ids> — перепроверить конкретные сообщения
                # Поддерживает: один ID, несколько через пробел, или ссылку t.me/chat/123
                arg = text[9:].strip()
                if not arg:
                    await bot.send_message(event.chat_id,
                        "❌ Укажите сообщения для перепроверки:\n"
                        "• `/recheck 716288`\n"
                        "• `/recheck 716254 716288 717000`\n"
                        "• `/recheck https://t.me/chat/716288`",
                        parse_mode="markdown")
                    return
                await pipeline.cmd_recheck(event.chat_id, arg)
                await pipeline.cmd_recheck(event.chat_id, arg)
            else:
                await bot.send_message(event.chat_id, f"❓ Неизвестная команда: {cmd}\n/help — список команд")
        except Exception as e:
            logger.error("Ошибка обработки команды %s: %s", cmd, e, exc_info=True)
            try:
                await bot.send_message(event.chat_id, f"❌ Ошибка: {e}")
            except Exception:
                pass

    logger.info("Слушаю управляющую группу (ID: %s)", config.GROUP_CHAT_ID)

    async def scheduler():
        while not _shutdown:
            try:
                logger.info("▶ Запуск цикла...")
                result = await pipeline.run_once()
                logger.info("✅ %s", result)
            except Exception as e:
                logger.error("❌ Ошибка цикла: %s", e, exc_info=True)

            for _ in range(config.POLL_INTERVAL):
                if _shutdown:
                    break
                await asyncio.sleep(1)

    await asyncio.gather(
        bot.run_until_disconnected(),
        scheduler(),
    )

    await userbot.disconnect()
    await bot.disconnect()
    logger.info("Daemon остановлен.")


# ── Entry point ──────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram Leads Finder")
    parser.add_argument("--once", action="store_true", help="Один цикл и выход")
    parser.add_argument("--daemon", action="store_true", help="Daemon-режим (дефолт)")
    parser.add_argument("--interval", type=int, default=None, help="Интервал в секундах")
    args = parser.parse_args()
    if args.interval:
        config.POLL_INTERVAL = args.interval
    if args.once:
        async def run_once_mode():
            bot = TelegramClient(
                str(config.BOT_SESSION_PATH),
                config.TELEGRAM_API_ID,
                config.TELEGRAM_API_HASH,
            )
            await bot.start(bot_token=config.BOT_TOKEN)

            userbot = TelegramClient(
                str(config.SESSION_PATH),
                config.TELEGRAM_API_ID,
                config.TELEGRAM_API_HASH,
            )
            await userbot.connect()
            pipeline = Pipeline(bot, userbot)
            await pipeline.cmd_run(config.GROUP_CHAT_ID)
            await userbot.disconnect()
            await bot.disconnect()
        asyncio.run(run_once_mode())
    else:
        asyncio.run(daemon_mode())
