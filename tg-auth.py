#!/usr/bin/env python3
"""Авторизация Telegram аккаунта КРАБа."""

import asyncio
from telethon import TelegramClient

SESSION = 'krab-tg-session'
API_ID = 538845
API_HASH = '50299bd63cc0569f338c33999d0dfe6b'
PHONE = '+79936163082'

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    
    me = await client.get_me()
    print(f"\n✅ Залогинен: {me.first_name} {me.last_name or ''}")
    print(f"   ID: {me.id}")
    print(f"   Phone: {me.phone}")
    print(f"   Username: @{me.username}" if me.username else "   Username: нет")
    print(f"\n   Сессия сохранена: {SESSION}.session")
    
    await client.disconnect()

asyncio.run(main())
