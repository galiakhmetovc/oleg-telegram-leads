"""Interactive Telegram userbot login helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telethon import TelegramClient, errors


class UserbotLoginPasswordRequired(RuntimeError):
    pass


class TelethonUserbotLoginClient:
    async def send_code(
        self,
        *,
        session_path: Path | str,
        api_id: int,
        api_hash: str,
        phone: str,
    ) -> str:
        client = TelegramClient(str(session_path), api_id, api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return str(sent.phone_code_hash)
        finally:
            await client.disconnect()

    async def sign_in(
        self,
        *,
        session_path: Path | str,
        api_id: int,
        api_hash: str,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: str | None,
    ) -> dict[str, Any]:
        client = TelegramClient(str(session_path), api_id, api_hash)
        await client.connect()
        try:
            try:
                user = await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash,
                )
            except errors.SessionPasswordNeededError as exc:
                if not password:
                    raise UserbotLoginPasswordRequired("Telegram 2FA password is required") from exc
                user = await client.sign_in(password=password)
            return {
                "telegram_user_id": str(getattr(user, "id", "")) or None,
                "telegram_username": getattr(user, "username", None),
            }
        finally:
            await client.disconnect()
