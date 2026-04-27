"""КРАБ — подключение к Telegram через telethon. Запуск: python3 tg-connect.py"""
import asyncio
from telethon import TelegramClient
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(BASE_DIR, 'krab-tg-session')
API_ID = 538845
API_HASH = '50299bd63cc0569f338c33999d0dfe6b'

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    me = await client.get_me()
    print(f'✅ Подключён: @{me.username} ({me.first_name})')
    print(f'ID: {me.id}')

    dialogs = await client.get_dialogs(limit=20)
    print(f'\n📂 Диалоги ({len(dialogs)} показано):')
    for d in dialogs:
        name = d.name or '(без имени)'
        print(f'  [{d.id}] {name} — {d.unread_count} непрочитанных')

    await client.disconnect()

asyncio.run(main())
