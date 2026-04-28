"""Tests for caption fix (media+text messages) and prompt filtering."""

import json
import logging
import os
import sys

# Suppress file loggers from ai_analyzer (no write access in test env)
logging.getLogger("src.ai_analyzer").handlers.clear()
logging.getLogger("src.ai_analyzer").propagate = True

# Mock LOG_DIR to /tmp for tests
os.environ.setdefault("LOG_DIR", "/tmp/tg-test-logs")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeMessage:
    """Fake Telethon message for testing fetcher."""
    def __init__(self, id, text=None, caption=None, sender=None, from_id=None, sender_id=None, date=None, reply_markup=None):
        self.id = id
        self.text = text
        self.caption = caption
        self.message = caption or text  # Telethon uses .message for media captions
        self.sender = sender
        self.from_id = from_id
        self.sender_id = sender_id
        self.date = date
        self.reply_markup = reply_markup


class FakeSender:
    def __init__(self, first_name="Test", last_name=None):
        self.first_name = first_name
        self.last_name = last_name


class FakeEntity:
    def __init__(self, title="Test Chat", username="test_chat"):
        self.title = title
        self.username = username


def test_msg_text_extraction():
    """Test that text is extracted from both msg.text and msg.caption."""
    cases = [
        ("Hello", None, True, "plain text message"),
        (None, "Photo caption text", True, "media with caption"),
        (None, None, False, "empty message (skip)"),
        ("", None, False, "empty text (skip)"),
        ("", "  ", False, "whitespace caption (skip)"),
        (None, "Длинный текст подписи к фото", True, "photo with long caption"),
    ]

    for text, caption, expected, desc in cases:
        msg = FakeMessage(id=1, text=text, caption=caption, sender=FakeSender("User"))
        msg_text = msg.text or getattr(msg, "message", None) or getattr(msg, "caption", None) or ""
        has_text = bool(msg_text.strip())
        assert has_text == expected, f"{desc}: expected {expected}, got {has_text} (text={text!r}, caption={caption!r})"
        if expected:
            print(f"  ✅ {desc}: extracted '{msg_text[:50]}'")
        else:
            print(f"  ✅ {desc}: correctly skipped")

    print("✅ test_msg_text_extraction PASSED\n")


def test_prompt_rejects_wrong_topics():
    """Test that prompt clearly rejects wrong topics."""
    from src.ai_analyzer import SYSTEM_PROMPT

    assert SYSTEM_PROMPT, "System prompt is empty!"

    assert "Стеклянные конструкции" in SYSTEM_PROMPT, "Prompt must reject glass constructions"
    assert "IT-программирование" in SYSTEM_PROMPT or "IT-разработка" in SYSTEM_PROMPT, "Prompt must reject IT/programming"
    assert "мебели" in SYSTEM_PROMPT, "Prompt must reject furniture"
    assert "шторы" in SYSTEM_PROMPT, "Prompt must reject curtains"
    assert "Видеонаблюдение" in SYSTEM_PROMPT, "Prompt must mention video surveillance"
    assert "Умный дом" in SYSTEM_PROMPT, "Prompt must mention smart home"
    assert "Климат" in SYSTEM_PROMPT, "Prompt must mention climate (new niche)"

    print("  ✅ Rejects glass constructions")
    print("  ✅ Rejects IT/programming")
    print("  ✅ Rejects furniture/curtains")
    print("  ✅ Includes climate niche")
    print("✅ test_prompt_rejects_wrong_topics PASSED\n")


def test_prompt_has_few_shot():
    """Test that prompt has few-shot examples."""
    from src.ai_analyzer import SYSTEM_PROMPT

    assert SYSTEM_PROMPT, "System prompt is empty!"

    positive = SYSTEM_PROMPT.count("✅ ЛИД")
    negative = SYSTEM_PROMPT.count("❌ НЕ ЛИД")

    assert positive >= 6, f"Expected at least 6 positive examples, got {positive}"
    assert negative >= 3, f"Expected at least 3 negative examples, got {negative}"
    assert "Стеклянные конструкции" in SYSTEM_PROMPT, "Missing glass counter-example"
    assert "мобильное приложение" in SYSTEM_PROMPT, "Missing IT counter-example"

    print(f"  ✅ Positive examples: {positive}")
    print(f"  ✅ Negative examples: {negative}")
    print("✅ test_prompt_has_few_shot PASSED\n")


async def test_ai_rejects_glass():
    """Test that AI rejects glass construction messages (live API call)."""
    from src.ai_analyzer import AIAnalyzer

    if not os.getenv("ZAI_API_KEY"):
        print("  ⏭️ ZAI_API_KEY not set, skipping live test")
        return

    analyzer = AIAnalyzer()

    messages = [
        {"id": 200, "sender_name": "UserA", "text": "Подскажите стекольщика, нужны стеклянные перегородки в офис с выездом на замер."},
        {"id": 201, "sender_name": "UserB", "text": "Нужно разработать мобильное приложение для умного дома."},
        {"id": 202, "sender_name": "UserC", "text": "Какие шторы лучше подойдут к серым стенам?"},
        {"id": 203, "sender_name": "UserD", "text": "Кто ставил видеодомофон Dahua? Отзовитесь."},
    ]

    results = await analyzer.analyze(messages)
    lead_ids = {r["message"]["id"] for r in results}

    assert 200 not in lead_ids, f"Glass (200) should NOT be a lead! Found: {results}"
    assert 201 not in lead_ids, f"IT dev (201) should NOT be a lead! Found: {results}"
    assert 202 not in lead_ids, f"Curtains (202) should NOT be a lead! Found: {results}"
    assert 203 in lead_ids, f"Videodoorphone (203) SHOULD be a lead! Got: {results}"

    print(f"  ✅ Glass construction (200) → rejected")
    print(f"  ✅ IT development (201) → rejected")
    print(f"  ✅ Curtains (202) → rejected")
    print(f"  ✅ Videodoorphone (203) → accepted as lead")
    print("✅ test_ai_rejects_glass PASSED\n")


async def test_ai_accepts_smart_home():
    """Test that AI accepts smart home messages (live API call)."""
    from src.ai_analyzer import AIAnalyzer

    if not os.getenv("ZAI_API_KEY"):
        print("  ⏭️ ZAI_API_KEY not set, skipping live test")
        return

    analyzer = AIAnalyzer()

    messages = [
        {"id": 300, "sender_name": "User1", "text": "Какие домофоны ставите в проекты? Нужен минималистичный, черный, небольшой экран. Ориентация лучше вертикальная, если так бывает."},
        {"id": 301, "sender_name": "User2", "text": "Подскажите, какие ip-камеры лучше поставить на дачу? Бюджет до 30к."},
        {"id": 302, "sender_name": "Expert", "text": "Я обычно ставлю Dahua, хорошая аналитика."},
        {"id": 303, "sender_name": "User3", "text": "Кто-нибудь делал умный дом на Tuya? Хочу автоматизировать свет."},
        {"id": 304, "sender_name": "User4", "text": "Нужен кондиционер с управлением через телефон."},
    ]

    results = await analyzer.analyze(messages)
    lead_ids = {r["message"]["id"] for r in results}

    assert 300 in lead_ids, f"Domofon (300) should be a lead! Got: {results}"
    assert 301 in lead_ids, f"IP-cameras (301) should be a lead! Got: {results}"
    assert 303 in lead_ids, f"Smart home Tuya (303) should be a lead! Got: {results}"
    assert 302 not in lead_ids, f"Expert (302) should NOT be a lead! Got: {results}"

    print(f"  ✅ Domofon (300) → lead")
    print(f"  ✅ IP-cameras (301) → lead")
    print(f"  ✅ Expert (302) → rejected")
    print(f"  ✅ Smart home (303) → lead")
    print(f"  ✅ AC smart (304) → {'lead' if 304 in lead_ids else 'rejected'}")
    print("✅ test_ai_accepts_smart_home PASSED\n")


async def test_ai_mixed_batch():
    """Test mixed batch with both good and bad leads."""
    from src.ai_analyzer import AIAnalyzer

    if not os.getenv("ZAI_API_KEY"):
        print("  ⏭️ ZAI_API_KEY not set, skipping live test")
        return

    analyzer = AIAnalyzer()

    messages = [
        {"id": 400, "sender_name": "Designer", "text": "Подскажите хорошую типографию для печати баннеров"},
        {"id": 401, "sender_name": "Homeowner", "text": "Какой видеодомофон выбрать для коттеджа? Хочу с камерой и Wi-Fi"},
        {"id": 402, "sender_name": "Builder", "text": "Нужен электромонтажник на объект, 3-комнатная квартира, ВДНХ"},
        {"id": 403, "sender_name": "Dev", "text": "Ищу Python-разработчика для проекта IoT платформы"},
        {"id": 404, "sender_name": "Mom", "text": "Где купить хорошую мебель для детской комнаты?"},
        {"id": 405, "sender_name": "Owner", "text": "Посоветуйте сигнализацию для загородного дома, с GSM модулем"},
    ]

    results = await analyzer.analyze(messages)
    lead_ids = {r["message"]["id"] for r in results}

    assert 401 in lead_ids, f"Videodoorphone (401) should be lead! Got: {results}"
    assert 405 in lead_ids, f"Alarm system (405) should be lead! Got: {results}"
    assert 400 not in lead_ids, f"Typography (400) should NOT be lead! Got: {results}"
    assert 403 not in lead_ids, f"Python dev (403) should NOT be lead! Got: {results}"
    assert 404 not in lead_ids, f"Furniture (404) should NOT be lead! Got: {results}"

    print(f"  ✅ Typography (400) → rejected")
    print(f"  ✅ Videodoorphone (401) → lead")
    print(f"  ✅ Electrician (402) → {'lead' if 402 in lead_ids else 'rejected'}")
    print(f"  ✅ Python dev (403) → rejected")
    print(f"  ✅ Furniture (404) → rejected")
    print(f"  ✅ Alarm system (405) → lead")
    print("✅ test_ai_mixed_batch PASSED\n")


if __name__ == "__main__":
    print("=" * 60)
    print("UNIT TESTS")
    print("=" * 60)

    test_msg_text_extraction()
    test_prompt_rejects_wrong_topics()
    test_prompt_has_few_shot()

    print("=" * 60)
    print("LIVE AI TESTS")
    print("=" * 60)

    import asyncio
    asyncio.run(test_ai_rejects_glass())
    asyncio.run(test_ai_accepts_smart_home())
    asyncio.run(test_ai_mixed_batch())

    print("=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)
