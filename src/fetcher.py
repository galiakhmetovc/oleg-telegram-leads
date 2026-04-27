"""Fetcher - выгрузка новых сообщений из чатов через Telethon."""
import asyncio
import logging
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
                logger.info("Первый запуск [%s]: чекпоинт = 0, пропускаем", chat.get("title", chat_key))
                return []

            entity = await self.client.get_entity(chat_id)
            chat_title = getattr(entity, "title", chat_key)

            async for msg in self.client.iter_messages(
                entity,
                min_id=last_id,
                limit=config.FETCH_LIMIT,
            ):
                if not msg.text:
                    continue

                sender_name = "Unknown"
                if msg.sender:
                    sender_name = msg.sender.first_name or ""
                    if msg.sender.last_name:
                        sender_name += f" {msg.sender.last_name}"
                elif msg.from_id:
                    try:
                        sender_entity = await self.client.get_entity(msg.from_id)
                        sender_name = sender_entity.first_name or "Unknown"
                        if sender_entity.last_name:
                            sender_name += f" {sender_entity.last_name}"
                    except Exception:
                        sender_name = f"user_{msg.sender_id}"

                if hasattr(entity, "username") and entity.username:
                    link = f"https://t.me/{entity.username}/{msg.id}"
                else:
                    link = f"chat:{chat_key}:{msg.id}"

                messages.append({
                    "id": msg.id,
                    "chat_id": chat_key,
                    "chat_title": chat_title,
                    "sender": msg.sender_id,
                    "sender_name": sender_name,
                    "text": msg.text,
                    "date": msg.date.isoformat(),
                    "link": link,
                })

            if messages:
                self.checkpoints[chat_key] = max(m["id"] for m in messages)
                logger.info("[%s]: %d новых сообщений", chat_title, len(messages))

        except Exception as e:
            logger.error("Ошибка загрузки [%s]: %s", chat.get("title", chat_key), e)

        return messages

    async def check_chat_access(self, chat_id: int, chat_title: str) -> dict:
        """Проверить доступ к чату.

        Три варианта результата:
        1. {"ok": True} - userbot состоит в чате, captch'и нет
        2. {"ok": False, "captcha": True} - userbot в чате, но есть captch'а
        3. {"ok": False, "reason": "..."} - userbot НЕ в чате (кнопка "вступить"),
           забанен, приватный, или другая ошибка
        """
        try:
            # Шаг 1: получить entity (Telethon может резолвить, даже если не в чате)
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

            # Шаг 2: проверить left=True (userbot вышел или не вступал)
            if getattr(entity, "left", False):
                return {
                    "ok": False,
                    "reason": "not_joined",
                    "message": (
                        f"🔒 Чат **{chat_title}** недоступен - "
                        f"@krab_ai_agent не состоит в чате.\n\n"
                        f"Открой чат и нажми **«Вступить»** от имени @krab_ai_agent.\n\n"
                        f"Чат добавлен в мониторинг. После вступления "
                        f"следующий цикл начнёт читать сообщения."
                    ),
                }

            # Шаг 3: попытаться прочитать сообщения (финальная проверка)
            try:
                msgs = await self.client.get_messages(entity, limit=3)
            except Exception as e:
                err_str = str(e).upper()
                if any(kw in err_str for kw in [
                    "CHANNEL_PRIVATE", "NO_ACCESS",
                    "USER_NOT_PARTICIPANT", "PEER_FOLDED",
                ]):
                    return {
                        "ok": False,
                        "reason": "not_joined",
                        "message": (
                            f"🔒 Чат **{chat_title}** недоступен - "
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

            # Шаг 4: проверка на captch'у/антибот в последних сообщениях
            # Признаки:
            #   - Любые inline-кнопки (кнопка "Я не бот")
            #   - Текст с mention от системного отправника (антибот просит ответить)
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
                            f"на сообщение.\n"
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
