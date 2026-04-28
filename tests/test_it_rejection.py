"""Diagnose: get message 718233 text and test AI classification."""
import json
import os
import sys
import asyncio
import httpx
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.getenv("ZAI_API_KEY")
BASE_URL = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4").rstrip("/")

async def get_message():
    """Get message text from container via exec."""
    # We can't use telethon from host (no module), 
    # so we use the container's python
    pass

def test_ai():
    # First, let's see what text was sent to AI for chunk containing 718233
    # From logs, the chunk_ids include 718233, but we don't see the text
    # Let's check if message 718233 has text or was skipped by fetcher
    
    with open("docs/prompts.md") as f:
        system_prompt = f.read().strip()
    
    # Simulate: message 718233 text is likely a URL link "А вот это про ИТ https://t.me/chat_mila_kolpakova/718233"
    # which is what user sent us. The actual content of 718233 in chat is different.
    
    # Test 1: URL-only message (user's message)
    test1 = [
        {"id": 718233, "sender_name": "User1", "text": "А вот это про ИТ https://t.me/chat_mila_kolpakova/718233"},
    ]
    
    # Test 2: IT development message
    test2 = [
        {"id": 718233, "sender_name": "User1", "text": "А вот это про ИТ"},
        {"id": 718234, "sender_name": "User2", "text": "Кто-нибудь знает хорошего программиста для разработки приложения? Нужен умный дом."},
    ]
    
    # Test 3: Smart home + IT mix
    test3 = [
        {"id": 718233, "sender_name": "User1", "text": "А вот это про ИТ"},
        {"id": 718234, "sender_name": "User2", "text": "Подскажите, какие камеры лучше поставить на дачу?"},
    ]
    
    tests = [
        ("URL-only IT message", test1, 0),
        ("IT programming request", test2, 0),
        ("IT + camera request mixed", test3, 1),
    ]
    
    all_pass = True
    for name, messages, expected_leads in tests:
        lines = [f"[{m['id']}] @{m['sender_name']}: {m['text']}" for m in messages]
        chunk_text = "\n".join(lines)
        user_content = chunk_text + '\n\nВерни JSON-объект {"leads": [{"id": число, "reason": "краткая причина"}]}. Если лидов нет — {"leads": []}.'
        
        payload = {
            "model": "glm-4.5",
            "temperature": 0.1,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        
        print(f"\n=== Test: {name} ===")
        print(f"Messages: {[m['text'][:60] for m in messages]}")
        print(f"Expected leads: {expected_leads}")
        
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
            timeout=60.0,
        )
        
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"AI response: {content}")
        
        parsed = json.loads(content)
        leads = parsed.get("leads", [])
        actual = len(leads)
        
        if actual == expected_leads:
            print(f"✅ PASS: {actual} leads")
        else:
            print(f"❌ FAIL: expected {expected_leads}, got {actual}")
            for lead in leads:
                print(f"  - id={lead.get('id')}, reason={lead.get('reason')}")
            all_pass = False
    
    # Now let's also try to get actual message text from the running container
    print("\n\n=== Getting actual message 718233 from container ===")
    
    return all_pass

if __name__ == "__main__":
    ok = test_ai()
    if not ok:
        sys.exit(1)
