#!/usr/bin/env python3
"""Тест AI API с реальным промптом из файла"""
import httpx, json, re, os

os.chdir("/var/lib/teamd/projects/oleg-telegram-leads")

# Загружаем .env
env = {}
for line in open(".env"):
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

API_KEY = env["ZAI_API_KEY"]
BASE_URL = env["ZAI_BASE_URL"]

# Загружаем промпт как в ai_analyzer.py
system_prompt_raw = open("docs/prompts.md").read()
match = re.search(r"```text\s*\n(.*?)```", system_prompt_raw, re.DOTALL)
if match:
    system_prompt = match.group(1).strip()
else:
    system_prompt = system_prompt_raw

print(f"API_KEY: {API_KEY[:20]}...")
print(f"BASE_URL: {BASE_URL}")
print(f"System prompt len: {len(system_prompt)}")

# Формируем чанк
chunk = [
    {"id": 1, "sender_name": "Рустем", "text": "Коллеги, кто-то может посоветовать камеры для видеонаблюдения?"},
    {"id": 2, "sender_name": "Yulia", "text": "Дорогие коллеги, идиотский вопрос — в спецификации ванны указана высота 55 см."},
    {"id": 3, "sender_name": "Алла", "text": "Коллеги, у кого можно посмотреть двери с фигурными наличниками 7 см?"}
]
lines = [f"[{m['id']}] @{m['sender_name']}: {m['text']}" for m in chunk]
user_content = "\n".join(lines)

print(f"\nUser content:\n{user_content}\n")

resp = httpx.post(
    BASE_URL + "/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "glm-4.5-air",
        "temperature": 0.1,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    },
    timeout=60
)

print(f"Status: {resp.status_code}")
data = resp.json()
msg = data["choices"][0]["message"]

content = msg.get("content", "MISSING")
reasoning = msg.get("reasoning_content", "")
finish = data["choices"][0].get("finish_reason")

print(f"finish_reason: {finish}")
print(f"content len: {len(content) if content else 0}")
print(f"content empty: {not content or len(content.strip()) == 0}")
print(f"content: {repr(content[:2000])}")
print(f"reasoning_content len: {len(reasoning)}")
print(f"reasoning first 200: {repr(reasoning[:200])}")

# Пробуем парсить
if content and content.strip():
    print("\n--- Парсинг JSON ---")
    c = content.strip()
    
    # Try 1: direct
    try:
        parsed = json.loads(c)
        print(f"Direct: {parsed}")
    except Exception as e:
        print(f"Direct failed: {e}")
    
    # Try 2: markdown
    md = re.search(r"```(?:json)?\s*\n?(.*?)```", c, re.DOTALL)
    if md:
        try:
            parsed = json.loads(md.group(1).strip())
            print(f"Markdown: {parsed}")
        except Exception as e:
            print(f"Markdown failed: {e}")
    
    # Try 3: find brackets
    start = c.find("[")
    end = c.rfind("]")
    if start >= 0 and end > start:
        sub = c[start:end+1]
        print(f"Bracket substring: {repr(sub[:500])}")
        try:
            parsed = json.loads(sub)
            print(f"Bracket: {parsed}")
        except Exception as e:
            print(f"Bracket failed: {e}")
