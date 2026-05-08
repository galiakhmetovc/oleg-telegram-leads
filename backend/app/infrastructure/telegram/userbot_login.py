from __future__ import annotations

from typing import Any

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from app.domain.telegram_ingestion import UserbotAuthorization, UserbotCodeSent


class UserbotLoginPasswordRequired(RuntimeError):
    pass


class TelethonUserbotLoginClient:
    async def send_code(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        session_string: str | None,
    ) -> UserbotCodeSent:
        client = TelegramClient(StringSession(session_string or ""), api_id, api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return UserbotCodeSent(
                phone_code_hash=str(sent.phone_code_hash),
                session_string=_save_session(client),
            )
        finally:
            await client.disconnect()

    async def sign_in(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: str | None,
        session_string: str | None,
    ) -> UserbotAuthorization:
        client = TelegramClient(StringSession(session_string or ""), api_id, api_hash)
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
            return UserbotAuthorization(
                telegram_user_id=str(getattr(user, "id", "")) or None,
                telegram_username=getattr(user, "username", None),
                session_string=_save_session(client),
            )
        finally:
            await client.disconnect()


def _save_session(client: Any) -> str:
    return str(client.session.save())
