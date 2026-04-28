"""Diagnose: get actual message 718233 text from running container."""
import json
import os
import subprocess
import sys
from pathlib import Path

script = '''
python3 << 'PYEOF'
import asyncio
from telethon.sync import TelegramClient
from dotenv import load_dotenv
import os

load_dotenv("/app/.env")

async def main():
    from pathlib import Path
    base = Path("/app")
    session = base / "krab-tg-session"
    
    client = TelegramClient(str(session), os.getenv("TELEGRAM_API_ID"), os.getenv("TELEGRAM_API_HASH"))
    await client.connect()
    me = await client.get_me()
    print(f"me={me}")
    
    if me:
        entity = await client.get_entity(-1001292716582)
        print(f"Chat: {entity.title} (ID: {entity.id})")
        msgs = await client.get_messages(entity, ids=[718233, 718234, 716254])
        for msg in msgs:
            print(f"  ID={msg.id} | text={repr(msg.text)} | caption={repr(msg.caption)} | media={msg.media}")
    else:
        print("NOT AUTHORIZED - session invalid")
    
    await client.disconnect()

asyncio.run(main())
PYEOF
'''

result = subprocess.run(
    ["docker", "exec", "-i", "leads-finder", "sh", "-c", script],
    capture_output=True, text=True,
    cwd="/var/lib/teamd/workspaces/agents/default/projects/oleg-telegram-leads"
)

print("STDOUT:", result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:1000])
