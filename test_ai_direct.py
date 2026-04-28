#!/usr/bin/env python3
"""Прямой тест AI API — увидеть реальный ответ LLM"""
import httpx, json

API_KEY = "ca50bfe496fe4edb85c8b9de84aa27438a418f76fa9a32a440ab55640c3dc3c8f"
BASE_URL = "https://api.z.ai/api/coding/paas/v4"

resp = httpx.post(
    BASE_URL + "/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "glm-4.5-air",
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": "Ты анализатор лидов. Отвечай ТОЛЬКО JSON массивом [{\"id\": N, \"reason\": \"причина\"}]. Если нет лидов - верни пустой массив []"},
            {"role": "user", "content": "Сообщения:\n1. Подскажите, какие домофоны посоветуете для загородного дома?\n2. Коллеги, кто-то может посоветовать камеры для видеонаблюдения?\n3. Привет, как дела?\n4. Сколько стоит керамогранит за метр?"}
        ]
    },
    timeout=30
)

print(f"Status: {resp.status_code}")
data = resp.json()
content = data["choices"][0]["message"]["content"]
print(f"Content type: {type(content)}")
print(f"Content len: {len(content)}")
print(f"Content repr: {repr(content[:1000])}")
print(f"Content empty: {len(content.strip()) == 0}")

if content.strip():
    print("\n--- Пробуем парсить ---")
    try:
        parsed = json.loads(content)
        print(f"json.loads OK: {parsed}")
    except:
        # fallback: найти JSON массив в тексте
        idx = content.find('[')
        if idx >= 0:
            end = content.rfind(']') + 1
            sub = content[idx:end]
            print(f"Found [{...}] at {idx}:{end}: {repr(sub[:500])}")
            try:
                parsed = json.loads(sub)
                print(f"parsed OK: {parsed}")
            except Exception as e:
                print(f"parse error: {e}")
        else:
            print("No [ found in content")
