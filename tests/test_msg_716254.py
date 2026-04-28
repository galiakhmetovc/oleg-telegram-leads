"""Подсчёт удалённых сообщений между 716254 и 718418."""
import asyncio
import os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv("/app/.env")


async def main():
    client = TelegramClient(
        os.environ["SESSION_PATH"],
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
    )
    await client.connect()
    await client.start()

    entity = await client.get_entity("chat_mila_kolpakova")

    # Считаем ВСЕ сообщения от 716249 до 718418
    # Используем max_id для ограничения сверху
    print("=== Считаем все сообщения от 716249 до 718418 ===")
    total_count = 0
    deleted_count = 0
    async for m in client.iter_messages(entity, min_id=716249, max_id=718419):
        total_count += 1
        if m.action and "delete" in str(m.action).lower():
            deleted_count += 1
    print(f"  Total: {total_count}")
    print(f"  Удалённых (service): {deleted_count}")
    print(f"  Реальных: {total_count - deleted_count}")

    # Диапазон ID: 718418 - 716249 = 2169
    # Реальных: 1159
    # Пропущено: 2169 - 1159 = 1010 (удалённых или Telegram-specific)
    print(f"\n  Диапазон ID: {718418 - 716249} (718418 - 716249)")
    print(f"  Пропущено: {(718418 - 716249) - total_count}")

    await client.disconnect()


asyncio.run(main())
