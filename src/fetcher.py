"""Fetcher - выгрузка новых сообщений из чатов через Telethon."""
import asyncio
import logging
import logging.handlers
import re
from datetime import datetime
from telethon import TelegramClient

import sys
sys.path.insert(0, "..")
from src import config

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, client: TelegramClient):
        self.client = client
        self.checkpoints = config.load_checkpoints()

    async def fetch_all(self) -> list[dict]:
        """Выгрузить новые сообщения из всех чатов."""
        all_messages = []
        chats = config.load_chats()
        
        if not chats:
            logger.warning("Список чатов пуст, нечего загружать")
            return []

        for chat in chats:
            messages = await self._fetch_chat(chat)
            all_messages.extend(messages)
        
        config.save_checkpoints(self.checkpoints)
        logger.info("Загружено %d сообщений из %d чатов", len(all_messages), len(chats))
        return all_messages

    async def _fetch_chat(self, chat: dict) -> list[dict]:
        """Выгрузить новые сообщения из одного чата."""
        chat_id = chat.get("id", chat)
        chat_key = str(chat_id)
        last_id = self.checkpoints.get(chat_key, 0)
        messages = []

        try:
            if last_id == 0:
                # Проверяем, есть ли pending_scan_ids
                pending_ids = chat.get("pending_scan_ids")
                if not pending_ids:
                    logger.info("Первый запуск [%s]: чекпоинт = 0, нет pending_scan, пропускаем", chat.get("title", chat_key))
                    return []

            entity = await self.client.get_entity(chat_id)
            chat_title = getattr(entity, "title", chat_key)

            skipped_no_text = 0
            seen_ids = set()

            # === Шаг 1: Direct fetch для pending_scan_ids ===
            pending_ids = chat.get("pending_scan_ids")
            if pending_ids:
                logger.info("[%s]: direct fetch %d pending IDs: %s", chat_title, len(pending_ids), pending_ids)
                for pid in pending_ids:
                    try:
                        target_msg = await self.client.get_messages(entity, ids=pid)
                        if target_msg and target_msg.id:
                            msg_text = target_msg.text or getattr(target_msg, "message", None) or getattr(target_msg, "caption", None) or ""
                            if msg_text.strip():
                                sender_name = self._resolve_sender(target_msg)
                                link = self._make_link(entity, target_msg.id, chat_key)

                                messages.append({
                                    "id": target_msg.id,
                                    "chat_id": chat_key,
                                    "chat_title": chat_title,
                                    "sender": target_msg.sender_id,
                                    "sender_name": sender_name,
                                    "text": msg_text,
                                    "date": target_msg.date.isoformat(),
                                    "link": link,
                                })
                                seen_ids.add(target_msg.id)
                                logger.info("[%s]: pending msg %d добавлен (%s): %s",
                                           chat_title, target_msg.id, sender_name, repr(msg_text[:60]))
                            else:
                                logger.info("[%s]: pending msg %d пропущен (нет текста)", chat_title, pid)
                        else:
                            logger.warning("[%s]: pending msg %d не найден (None)", chat_title, pid)
                    except Exception as e:
                        logger.warning("[%s]: ошибка чтения pending msg %d: %s", chat_title, pid, e)

                # Убираем pending_scan_ids после скана
                chat["pending_scan_ids"] = None
                config.save_chats(config.load_chats())
                logger.info("[%s]: pending_scan_ids очищены", chat_title)

            # === Шаг 2: Direct fetch для initial_scan_msg_id (обратная совместимость) ===
            target_msg_id = chat.get("initial_scan_msg_id")
            if target_msg_id and target_msg_id not in seen_ids:
                logger.info("[%s]: direct fetch target msg_id=%d (checkpoint=%d)", chat_title, target_msg_id, last_id)
                try:
                    target_msg = await self.client.get_messages(entity, ids=target_msg_id)
                    if target_msg and target_msg.id:
                        msg_text = target_msg.text or getattr(target_msg, "message", None) or getattr(target_msg, "caption", None) or ""
                        if msg_text.strip():
                            sender_name = self._resolve_sender(target_msg)
                            link = self._make_link(entity, target_msg.id, chat_key)

                            messages.append({
                                "id": target_msg.id,
                                "chat_id": chat_key,
                                "chat_title": chat_title,
                                "sender": target_msg.sender_id,
                                "sender_name": sender_name,
                                "text": msg_text,
                                "date": target_msg.date.isoformat(),
                                "link": link,
                            })
                            seen_ids.add(target_msg.id)
                            logger.info("[%s]: target msg %d добавлен (%s): %s",
                                       chat_title, target_msg.id, sender_name, repr(msg_text[:60]))
                        else:
                            logger.info("[%s]: target msg %d пропущен (нет текста)", chat_title, target_msg_id)
                    else:
                        logger.warning("[%s]: target msg %d не найден (None)", chat_title, target_msg_id)
                except Exception as e:
                    logger.warning("[%s]: ошибка чтения target msg %d: %s", chat_title, target_msg_id, e)

                # Убираем initial_scan_msg_id после первого скана
                chat["initial_scan_msg_id"] = None
                config.save_chats(config.load_chats())

            # === Шаг 3: Основной запрос — все сообщения после checkpoint ===
            if last_id > 0:
                async for msg in self.client.iter_messages(
                    entity,
                    min_id=last_id,
                    limit=config.FETCH_LIMIT,
                ):
                    if msg.id in seen_ids:
                        continue

                    msg_text = msg.text or getattr(msg, "message", None) or getattr(msg, "caption", None) or ""
                    if not msg_text.strip():
                        skipped_no_text += 1
                        logger.debug("  Пропущено (нет текста): id=%s media=%s", msg.id, type(msg.media).__name__ if msg.media else None)
                        continue

                    sender_name = self._resolve_sender(msg)
                    link = self._make_link(entity, msg.id, chat_key)

                    messages.append({
                        "id": msg.id,
                        "chat_id": chat_key,
                        "chat_title": chat_title,
                        "sender": msg.sender_id,
                        "sender_name": sender_name,
                        "text": msg_text,
                        "date": msg.date.isoformat(),
                        "link": link,
                    })
                    seen_ids.add(msg.id)

            if messages:
                self.checkpoints[chat_key] = max(m["id"] for m in messages)
                logger.info(
                    "[%s]: %d новых сообщений (ID %d..%d), пропущено без текста: %d",
                    chat_title, len(messages), min(m["id"] for m in messages),
                    max(m["id"] for m in messages), skipped_no_text,
                )
            else:
                logger.debug("[%s]: нет новых сообщений (min_id=%d)", chat_title, last_id)
        except Exception as e:
            logger.error("Ошибка загрузки [%s]: %s", chat.get("title", chat_key), e)

        return messages

    def _resolve_sender(self, msg) -> str:
        """Resolve sender name from a Telethon message."""
        if msg.sender:
            name = msg.sender.first_name or ""
            if msg.sender.last_name:
                name += f" {msg.sender.last_name}"
            return name or "Unknown"
        elif msg.from_id:
            return f"user_{msg.sender_id}"
        return "Unknown"

    def _make_link(self, entity, msg_id: int, chat_key: str) -> str:
        """Generate t.me link for a message."""
        if hasattr(entity, "username") and entity.username:
            return f"https://t.me/{entity.username}/{msg_id}"
        return f"chat:{chat_key}:{msg_id}"

    async def check_chat_access(self, chat_id: int, chat_title: str) -> dict:
        """Проверить доступ к чату."""
        try:
            try:
                entity = await self.client.get_entity(chat_id)
            except Exception as e:
                return {
                    "ok": False,
                    "reason": "no_entity",
                    "message": (
                        f"⚠️ Не удалось найти чат **{chat_title}**.\n\n"
                        f"Возможно, ссылка устарела или чат удалён.\n"
                        f"Чат добавлен в мониторинг - попробую позже."
                    ),
                }

            if getattr(entity, "left", False):
                return {
                    "ok": False,
                    "reason": "not_joined",
                    "message": (
                        f"🔒 Чат **{chat_title}** недоступен — "
                        f"@krab_ai_agent не состоит в чате.\n\n"
                        f"Открой чат и нажми **«Вступить»** от имени @krab_ai_agent.\n\n"
                        f"Чат добавлен в мониторинг. После вступления "
                        f"следующий цикл начнёт читать сообщения."
                    ),
                }

            try:
                msgs = await self.client.get_messages(entity, limit=3)
            except Exception as e:
                err_str = str(e).upper()
                if any(kw in err_str for kw in [
                    "CHANNEL_PRIVATE","NO_ACCESS",
                    "USER_NOT_PARTICIPANT","PEER_FOLDED",
                ]):
                    return {
                        "ok": False,
                        "reason": "not_joined",
                        "message": (
                            f"🔒 Чат **{chat_title}** недоступен — "
                            f"@krab_ai_agent не состоит в чате.\n\n"
                            f"Открой чат и нажми **«Вступить»** от имени @krab_ai_agent.\n\n"
                            f"Чат добавлен в мониторинг. После вступления "
                            f"следующий цикл начнёт читать сообщения."
                        ),
                    }
                elif "FLOOD" in err_str:
                    return {
                        "ok": False,
                        "reason": "flood",
                        "message": (
                            f"⏳ Telegram flood wait для чата **{chat_title}**.\n"
                            f"Попробую позже."
                        ),
                    }
                elif "BANNED" in err_str or "FORBIDDEN" in err_str:
                    return {
                        "ok": False,
                        "reason": "banned",
                        "message": (
                            f"🚫 @krab_ai_agent заблокирован в чате "
                            f"**{chat_title}**.\n\n"
                            f"Причина: {str(e)[:200]}"
                        ),
                    }
                else:
                    return {
                        "ok": False,
                        "reason": "error",
                        "message": (
                            f"⚠️ Ошибка доступа к **{chat_title}**: "
                            f"{str(e)[:200]}\n\n"
                            f"Чат добавлен в мониторинг - попробую позже."
                        ),
                    }

            if not msgs or not msgs[0]:
                return {"ok": True}

            for msg in msgs:
                has_buttons = (
                    msg.reply_markup
                    and hasattr(msg.reply_markup, "rows")
                    and any(row.buttons for row in msg.reply_markup.rows)
                )
                has_mention = bool(msg.text and re.search(r'@\w+', msg.text))
                is_system = (
                    msg.sender_id is None
                    or (hasattr(msg, "from_id") and msg.from_id is None)
                )

                if has_buttons:
                    return {
                        "ok": False,
                        "captcha": True,
                        "message": (
                            f"⚠️ В чате **{chat_title}** обнаружена "
                            f"captch'а (антибот).\n\n"
                            f"Зайди в чат от аккаунта @krab_ai_agent "
                            f"и нажми кнопку.\n"
                            f"После этого я смогу читать сообщения.\n\n"
                            f"Чат добавлен в мониторинг, но циклы "
                            f"будут пропущены."
                        ),
                    }
                if has_mention and is_system:
                    return {
                        "ok": False,
                        "captcha": True,
                        "message": (
                            f"⚠️ В чате **{chat_title}** возможен антибот "
                            f"(просит ответить).\n\n"
                            f"Зайди в чат от @krab_ai_agent и ответь "
                            f"на сообщение.\n\n"
                            f"После этого я смогу читать сообщения.\n\n"
                            f"Чат добавлен в мониторинг, но циклы "
                            f"будут пропущены."
                        ),
                    }

            return {"ok": True}
        except Exception as e:
            return {
                "ok": False,
                "reason": "error",
                "message": (
                    f"⚠️ Ошибка при проверке **{chat_title}**: "
                    f"{str(e)[:200]}\n\n"
                    f"Чат добавлен в мониторинг - попробую позже."
                ),
            }
