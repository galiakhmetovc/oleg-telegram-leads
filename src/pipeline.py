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
import os
import re
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient, events

from src import config
from src.fetcher import Fetcher
from src.keyword_scanner import KeywordScanner
from src.ai_analyzer import AIAnalyzer
from src.notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline")

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
                access = await fetcher.check_chat_access(chat_id, chat_title)
                if not access.get("ok") and access.get("captcha"):
                    skipped_chats.append(chat_title)
                    logger.warning("Чат %s пропущен: captch'а", chat_title)

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

            # 2. Keyword scan
            keyword_results = self.scanner.scan(messages)
            logger.info("Keyword matches: %d / %d", len(keyword_results), len(messages))

            # 3. AI analyze (все сообщения — ADR-002)
            ai_results = await self.analyzer.analyze(messages)
            logger.info("AI leads: %d", len(ai_results))

            # 4. Merge keyword + AI results (dedup по message_id)
            all_leads = self._merge_results(keyword_results, ai_results)

            # 5. Dedup с историей
            new_leads = self._dedup_leads(all_leads)

            # 6. Notify + @mention
            if new_leads:
                await self.notifier.notify(new_leads, mention_anton=True)
                await self._save_leads(new_leads)
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

            # 7. Save to Obsidian
            self._save_to_obsidian(messages, keyword_results, new_leads)

            return f"Сообщений: {len(messages)} | Keyword: {len(keyword_results)} | AI: {len(ai_results)} | Новых лидов: {len(new_leads)}"

        except Exception as e:
            logger.error("Ошибка цикла: %s", e, exc_info=True)
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
        chats = config.load_chats()
        checkpoints = config.load_checkpoints()
        if not chats:
            await self.bot.send_message(chat_id, "📭 Список чатов пуст. Перешлите сообщение или отправьте ссылку.")
            return

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

    async def cmd_reset(self, chat_id: int, chat_ref: str):
        """Сбросить чекпоинт чата."""
        chat_id_int = await self._resolve_chat_id(chat_ref, chat_id)
        if chat_id_int is None:
            return

        checkpoints = config.load_checkpoints()
        key = str(chat_id_int)
        if key in checkpoints:
            del checkpoints[key]
            config.save_checkpoints(checkpoints)
            await self.bot.send_message(chat_id, f"🔄 Чекпоинт сброшен для чата `{chat_id_int}`\nСледующий цикл начнёт с текущего момента.", parse_mode="markdown")
        else:
            await self.bot.send_message(chat_id, f"ℹ️ У чата `{chat_id_int}` нет чекпоинта (или он уже сброшен).", parse_mode="markdown")

    async def cmd_remove(self, chat_id: int, chat_ref: str):
        """Удалить чат из мониторинга."""
        chat_id_int = await self._resolve_chat_id(chat_ref, chat_id)
        if chat_id_int is None:
            return

        chats = config.load_chats()
        original_len = len(chats)
        chats = [c for c in chats if c.get("id") != chat_id_int]
        if len(chats) < original_len:
            config.save_chats(chats)
            checkpoints = config.load_checkpoints()
            key = str(chat_id_int)
            if key in checkpoints:
                del checkpoints[key]
                config.save_checkpoints(checkpoints)
            await self.bot.send_message(chat_id, f"🗑 Чат `{chat_id_int}` удалён из мониторинга.", parse_mode="markdown")
        else:
            await self.bot.send_message(chat_id, f"⚠️ Чат `{chat_id_int}` не найден в списке.", parse_mode="markdown")

    async def cmd_leads(self, chat_id: int):
        """Последние найденные лиды."""
        leads = self._load_leads()
        if not leads:
            await self.bot.send_message(chat_id, "📋 Лидов пока нет.")
            return

        last_leads = leads[-10:]
        lines = [f"📋 **Последние {len(last_leads)} лидов (из {len(leads)}):**\n"]
        for i, lead in enumerate(last_leads, 1):
            msg = lead.get("message", {})
            lines.append(f"**{i}.** [{msg.get('chat_title', '?')}]")
            lines.append(f"💬 _{(msg.get('text', '') or '')[:100]}_")
            if msg.get("link"):
                lines.append(f"🔗 {msg['link']}")
            if lead.get("reason"):
                lines.append(f"🤖 {lead['reason']}")
            lines.append("")

        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="markdown")

    async def cmd_run(self, chat_id: int):
        """Запустить цикл вручную."""
        await self.bot.send_message(chat_id, "▶ Запускаю проверку...")
        try:
            result = await self.run_once()
            await self.bot.send_message(chat_id, f"✅ Готово:\n{result}")
        except Exception as e:
            await self.bot.send_message(chat_id, f"❌ Ошибка: {e}")

    # ── Обработка пересылок и ссылок ─────────────────────
    async def handle_forward(self, event: events.NewMessage.Event):
        """Обрабатывает пересланные сообщения.

        Сценарий 1: Чат НЕ в мониторинге → добавить чат, чекпоинт = ID пересланного сообщения
        Сценарий 2: Чат УЖЕ в мониторинге → сохранить как пример лида
        """
        if not event.forward:
            return

        fwd = event.forward

        # Шаг 1: Извлечь chat_id из пересылки
        chat_id = self._extract_chat_id_from_forward(fwd)

        # Шаг 2: Если не удалось — fallback через userbot
        if not chat_id:
            chat_id = await self._find_chat_via_userbot(fwd)

        if not chat_id:
            await self.bot.send_message(
                event.chat_id,
                "⚠️ Не удалось определить исходный чат.\n\n"
                "Попробуйте:\n"
                "• Переслать сообщение вручную (не через бота)\n"
                "• Отправить ссылку: `t.me/chat_name/123`"
            )
            return

        # Шаг 3: Определяем сценарий
        chats = config.load_chats()
        existing = next((c for c in chats if c.get("id") == chat_id), None)

        if existing:
            await self._save_lead_example(event, fwd, chat_id, existing)
        else:
            await self._add_chat_from_forward(event, fwd, chat_id)

    async def handle_link(self, event: events.NewMessage.Event, link: str):
        """Обрабатывает ссылку t.me/chat/123.

        Шаг 1: Мгновенный отклик — «принял, валидирую»
        Шаг 2: Если чат уже в мониторинге — «пример лида получен, обновляю БД»
        Шаг 3: Если новый чат — «присоединяюсь» → captch'а или «поставлен на мониторинг»
        """
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
            # Сначала получим текст сообщения из чата
            try:
                msgs = await self.userbot.get_messages(chat_id, ids=message_id)
                fwd_text = msgs.text if msgs and msgs.text else ""
            except Exception:
                fwd_text = ""
            await self._save_lead_example_with_text(event, chat_id, existing, fwd_text, message_id)
            return

        # Шаг 4: Проверяем доступ (captch'а, бан)
        fetcher = Fetcher(self.userbot)
        access = await fetcher.check_chat_access(chat_id, chat_title)

        if not access.get("ok"):
            # Ошибка доступа (captcha / not_joined / banned / etc)
            reason = access.get("reason", "unknown")
            chats = config.load_chats()
            # Не дублируем, если уже в списке
            if not any(c.get("id") == chat_id for c in chats):
                new_chat = {
                    "id": chat_id,
                    "title": chat_title,
                    "username": username,
                    "added": datetime.now().isoformat(),
                    "status": "captcha" if reason == "captcha" else "blocked",
                }
                chats.append(new_chat)
                config.save_chats(chats)

            checkpoints = config.load_checkpoints()
            checkpoints[str(chat_id)] = message_id
            config.save_checkpoints(checkpoints)

            await self.bot.send_message(
                event.chat_id,
                access.get("message", "⚠️ Проблема с доступом к чату."),
                parse_mode="markdown",
            )
            logger.warning("Чат %s добавлен с проблемой: %s", chat_title, reason)
            return

        # Шаг 5: Всё ОК — ставим на мониторинг
        now = datetime.now()
        new_chat = {
            "id": chat_id,
            "title": chat_title,
            "username": username,
            "added": now.isoformat(),
            "status": "active",
        }
        chats.append(new_chat)
        config.save_chats(chats)

        checkpoints = config.load_checkpoints()
        checkpoints[str(chat_id)] = message_id
        config.save_checkpoints(checkpoints)

        await self.bot.send_message(
            event.chat_id,
            f"✅ **Группа \"{chat_title}\" поставлена на мониторинг**\n\n"
            f"📅 {_format_date_ru(now)}\n"
            f"🔗 @{username}\n"
            f"🔑 ID: `{chat_id}`\n"
            f"📍 Чекпоинт: сообщение {message_id} (история до него пропущена)\n\n"
            f"Следующий цикл начнёт читать новые сообщения.",
            parse_mode="markdown",
        )
        logger.info("Добавлен чат %s (%s) по ссылке, чекпоинт = %d", chat_title, chat_id, message_id)

        # Мгновенный отклик
        await self.bot.send_message(
            event.chat_id,
            f"📨 Принял, сообщение валидировано.\nПытаюсь присоединиться к чату **{chat_title}**...",
            parse_mode="markdown",
        )

        # Проверяем доступ (captch'а, бан)
        access = await fetcher.check_chat_access(chat_id, chat_title)

        # Сохраняем чекпоинт = ID пересланного сообщения
        checkpoints = config.load_checkpoints()
        checkpoints[str(chat_id)] = fwd.id
        config.save_checkpoints(checkpoints)

        if not access.get("ok"):
            reason = access.get("reason", "unknown")
            chats = config.load_chats()
            if not any(c.get("id") == chat_id for c in chats):
                new_chat = {
                    "id": chat_id,
                    "title": chat_title,
                    "username": username,
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
            "username": username,
            "added": now.isoformat(),
            "status": "active",
        }
        chats.append(new_chat)
        config.save_chats(chats)

        extra = f"\n🔗 @{username}" if username else ""
        await self.bot.send_message(
            event.chat_id,
            f"✅ **Группа \"{chat_title}\" поставлена на мониторинг**\n\n"
            f"📅 {_format_date_ru(now)}\n"
            f"{extra}\n"
            f"🔑 ID: `{chat_id}`\n"
            f"📍 Чекпоинт: сообщение {fwd.id} (история до него пропущена)\n\n"
            f"Следующий цикл начнёт читать новые сообщения.",
            parse_mode="markdown",
        )
        logger.info("Добавлен чат %s (%s) по пересылке, чекпоинт = %d", chat_title, chat_id, fwd.id)
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
            async for dialog in self.userbot.iter_dialogs(limit=200):
                entity = dialog.entity
                title = getattr(entity, "title", "") or ""
                username = getattr(entity, "username", "") or ""

                if (search_name.lower() in title.lower() or
                    search_name.lower() in username.lower() or
                    title.lower() in search_name.lower()):

                    from telethon.tl.types import Channel, Chat
                    if isinstance(entity, (Channel, Chat)):
                        if isinstance(entity, Channel):
                            chat_id = int(f"-100{entity.id}")
                        else:
                            chat_id = -entity.id
                        logger.info("Найден чат '%s' (ID: %s) по имени '%s'", title, chat_id, search_name)
                        return chat_id
        except Exception as e:
            logger.warning("Ошибка поиска чата через userbot: %s", e)
        await self._save_lead_example_with_text(event, chat_id, existing, fwd_text, message_id, sender_name)

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

    def _dedup_leads(self, leads: list) -> list:
        """Убрать лиды, которые уже были отправлены."""
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
        return len(self._load_leads())

    async def _save_leads(self, leads: list):
        """Сохранить новые лиды в leads.json."""
        leads_file = config.DATA_DIR / "leads.json"
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
        await self.notifier.send_text(f"📊 {message}\n\n✉️ {fetched} сообщений | 🔑 {kw} keyword | 🤖 {ai} AI | 🎯 {leads} лидов | 📂 {chats_count} чатов")

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


# ── Daemon ───────────────────────────────────────────────
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

    me = await bot.get_me()
    logger.info("🤖 Бот запущен: @%s", me.username)

    # Userbot client — чтение чатов + поиск чатов (постоянное подключение)
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

    # Handler для всех сообщений в группе
    @bot.on(events.NewMessage(chats=config.GROUP_CHAT_ID))
    async def group_message_handler(event):
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

        logger.info("Команда от %s: %s", event.sender_id, text)
        if text == "/help":
            await bot.send_message(event.chat_id, HELP_TEXT, parse_mode="markdown")
        elif text == "/status":
            await pipeline.cmd_status(event.chat_id)
        elif text == "/list":
            await pipeline.cmd_list(event.chat_id)
        elif text == "/leads":
            await pipeline.cmd_leads(event.chat_id)
        elif text == "/run":
            await pipeline.cmd_run(event.chat_id)
        elif text.startswith("/reset"):
            arg = text[6:].strip()
            if not arg:
                await bot.send_message(event.chat_id, "❌ Укажите chat_id: `/reset <chat_id>`\nИли используйте `/list` для просмотра.", parse_mode="markdown")
                return
            await pipeline.cmd_reset(event.chat_id, arg)
        elif text.startswith("/remove"):
            arg = text[7:].strip()
            if not arg:
                await bot.send_message(event.chat_id, "❌ Укажите chat_id: `/remove <chat_id>`\nИли используйте `/list` для просмотра.", parse_mode="markdown")
                return
            await pipeline.cmd_remove(event.chat_id, arg)

    logger.info("Слушаю управляющую группу (ID: %s)", config.GROUP_CHAT_ID)
    logger.info("Интервал циклов: %d сек", config.POLL_INTERVAL)

    await bot.send_message(
        config.GROUP_CHAT_ID,
        "🟢 **Leads Finder запущен!**\n\n"
        f"⏱ Интервал: {config.POLL_INTERVAL // 60} мин\n"
        f"🤖 Модель: {config.ZAI_MODEL}\n"
        "📋 /help — список команд\n"
        "📦 Перешлите сообщение или отправьте ссылку (t.me/chat/123) — добавлю в мониторинг"
    )

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
