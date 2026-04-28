"""Tests for AI Analyzer — pure unit tests without Telegram/Docker."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ai_analyzer import AIAnalyzer, _load_system_prompt


# ── Test Data ─────────────────────────────────────────────

TEST_MESSAGE_INTERCOM = {
    "id": 716254,
    "sender_name": "TestUser",
    "text": (
        "Добрый вечер! Поделитесь, какие домофоны ставите в проекты? "
        "Нужен минималистичный, черный, небольшой экран. "
        "Ориентация лучше вертикальная, если так бывает. "
        "Какие функции у них могут быть? На что обратить внимание?"
    ),
}

TEST_MESSAGE_CAMERAS = {
    "id": 716255,
    "sender_name": "CamUser",
    "text": "Подскажите, какие ip-камеры лучше поставить на дачу? Бюджет до 30к, нужно 4 штуки с ночной видимостью.",
}

TEST_MESSAGE_NOT_LEAD = {
    "id": 716256,
    "sender_name": "ExpertUser",
    "text": "Я обычно ставлю Dahua, хорошая аналитика. Для дома отлично подходит NVR5216.",
}

TEST_MESSAGE_OFFTOPIC = {
    "id": 716257,
    "sender_name": "InteriorUser",
    "text": "Какой цвет стен лучше выбрать для спальни в скандинавском стиле?",
}

TEST_MESSAGE_SMART_HOME = {
    "id": 716258,
    "sender_name": "SmartUser",
    "text": "Привет! Кто-нибудь делал умный дом на Tuya? Хочу автоматизировать свет и жалюзи, не знаю с чего начать.",
}


# ── Tests: System Prompt ──────────────────────────────────

def test_system_prompt_loaded():
    """System prompt must be loaded from prompts.md and not empty."""
    prompt = _load_system_prompt()
    assert prompt, "System prompt is empty — prompts.md not found or empty"
    assert len(prompt) > 100, f"System prompt too short: {len(prompt)} chars"
    assert "лид" in prompt.lower() or "lead" in prompt.lower(), "Prompt must mention leads"
    print(f"✅ System prompt loaded: {len(prompt)} chars")


def test_system_prompt_has_few_shot_examples():
    """Prompt should contain few-shot examples after our update."""
    prompt = _load_system_prompt()
    assert "ПРИМЕР" in prompt or "пример" in prompt, "Prompt must have examples"
    # Should have both positive (lead) and negative (not lead) examples
    assert "ЛИД" in prompt.upper(), "Prompt must mark lead examples clearly"
    print("✅ Prompt has few-shot examples")


def test_system_prompt_no_hardcoded_ids():
    """Prompt should NOT contain hardcoded message IDs like 716255."""
    prompt = _load_system_prompt()
    # After fix, there should be no hardcoded IDs, only [ID] placeholders
    # We allow IDs only in example blocks that use generic placeholders
    # Check for the specific bad pattern
    assert '"id": 716255' not in prompt, "Prompt must not have hardcoded IDs from specific chats"
    print("✅ No hardcoded message IDs in prompt")


# ── Tests: Message Formatting ─────────────────────────────

def test_format_chunk():
    """_format_chunk should produce readable message format."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_INTERCOM, TEST_MESSAGE_CAMERAS]
    result = analyzer._format_chunk(chunk)
    assert "[716254]" in result
    assert "@TestUser" in result
    assert "домофоны" in result
    print(f"✅ Format chunk works:\n{result[:200]}...")


# ── Tests: JSON Extraction ────────────────────────────────

def test_extract_json_clean():
    """Should parse clean JSON."""
    analyzer = AIAnalyzer()
    text = '{"leads": [{"id": 716254, "reason": "Ищет домофон"}]}'
    result = analyzer._extract_json(text)
    assert result is not None
    assert result["leads"][0]["id"] == 716254
    print("✅ Clean JSON extraction works")


def test_extract_json_with_markdown():
    """Should extract JSON from ```json ... ``` block."""
    analyzer = AIAnalyzer()
    text = 'Вот результат:\n```json\n{"leads": [{"id": 716254, "reason": "test"}]}\n```'
    result = analyzer._extract_json(text)
    assert result is not None
    assert len(result["leads"]) == 1
    print("✅ Markdown JSON extraction works")


def test_extract_json_with_thinking():
    """Should extract JSON even when thinking/wrapping text is present."""
    analyzer = AIAnalyzer()
    text = (
        "Анализирую сообщения...\n\n"
        "Сообщение [716254] содержит запрос о домофонах — это лид.\n\n"
        '{"leads": [{"id": 716254, "reason": "Запрашивает рекомендации по домофонам"}]}'
    )
    result = analyzer._extract_json(text)
    assert result is not None
    assert len(result["leads"]) == 1
    print("✅ JSON extraction with surrounding text works")


def test_extract_json_empty():
    """Should return None for non-JSON text."""
    analyzer = AIAnalyzer()
    text = "Я не могу помочь с этим запросом."
    result = analyzer._extract_json(text)
    assert result is None
    print("✅ Non-JSON returns None")


def test_extract_json_empty_leads():
    """Should parse {'leads': []} correctly."""
    analyzer = AIAnalyzer()
    text = '{"leads": []}'
    result = analyzer._extract_json(text)
    assert result is not None
    assert result["leads"] == []
    print("✅ Empty leads parsed correctly")


# ── Tests: Lead Parsing ───────────────────────────────────

def test_parse_leads_valid():
    """Should parse valid leads with correct message data."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_INTERCOM]
    data = {"leads": [{"id": 716254, "reason": "Ищет домофон для проекта"}]}
    results = analyzer._parse_leads(data, chunk)
    assert len(results) == 1
    assert results[0]["message"]["id"] == 716254
    assert results[0]["reason"] == "Ищет домофон для проекта"
    assert results[0]["source"] == "ai"
    print("✅ Lead parsing works")


def test_parse_leads_wrong_id():
    """Should skip leads with IDs not in chunk."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_INTERCOM]
    data = {"leads": [{"id": 999999, "reason": "test"}]}
    results = analyzer._parse_leads(data, chunk)
    assert len(results) == 0
    print("✅ Wrong IDs filtered out")


def test_parse_leads_no_leads_field():
    """Should handle missing 'leads' field gracefully."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_INTERCOM]
    data = {"something": "else"}
    results = analyzer._parse_leads(data, chunk)
    assert results == []
    print("✅ Missing 'leads' field handled")


# ── Tests: Payload ────────────────────────────────────────

def test_build_payload_has_thinking_disabled():
    """Payload should include thinking disabled for JSON tasks."""
    analyzer = AIAnalyzer()
    messages = [{"role": "user", "content": "test"}]
    payload = analyzer._build_payload(messages)
    expected_model = os.environ.get("ZAI_MODEL", "glm-5.1")
    assert payload["model"] == expected_model, f"Expected model {expected_model}, got {payload['model']}"
    assert payload["temperature"] == 0.1
    assert payload["stream"] is False
    # After fix: thinking should be disabled
    if "thinking" in payload:
        assert payload["thinking"].get("type") == "disabled", \
            f"Thinking should be disabled, got: {payload['thinking']}"
    print("✅ Payload structure correct")


def test_build_messages_has_format_instruction():
    """User message should contain format instruction."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_INTERCOM]
    messages = analyzer._build_messages(chunk)
    assert len(messages) >= 1  # at least user message
    user_msg = messages[-1]
    assert "leads" in user_msg["content"].lower()
    assert '"leads"' in user_msg["content"]
    print("✅ Format instruction present in user message")


# ── Tests: Chunking ───────────────────────────────────────

def test_chunk_messages_respects_batch_size():
    """Should split messages into chunks by batch size."""
    analyzer = AIAnalyzer()
    messages = [{"id": i, "text": f"msg {i}", "sender_name": "u"} for i in range(35)]
    chunks = analyzer._chunk_messages(messages)
    assert len(chunks) == 3  # 15 + 15 + 5
    assert all(len(c) <= 15 for c in chunks)
    print(f"✅ Chunking: 35 messages → {len(chunks)} chunks")


def test_chunk_messages_respects_char_limit():
    """Should split by char limit."""
    analyzer = AIAnalyzer()
    # Create messages where each is 600 chars
    messages = [{"id": i, "text": "x" * 600, "sender_name": "u"} for i in range(10)]
    chunks = analyzer._chunk_messages(messages)
    # 5000 / 600 ≈ 8 messages per chunk
    assert len(chunks) >= 2
    print(f"✅ Char limit chunking: 10 × 600chars → {len(chunks)} chunks")


# ── Tests: Live API ──────────────────────────────────────

async def test_live_api_intercom():
    """Live test: AI must detect intercom message as lead."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_INTERCOM]
    
    print("\n🧪 Live API test: intercom message")
    print(f"   Message: {TEST_MESSAGE_INTERCOM['text'][:80]}...")
    
    results = await analyzer.analyze(chunk)
    
    if results:
        print(f"   ✅ AI detected {len(results)} lead(s)")
        for r in results:
            print(f"   → ID={r['message']['id']}, reason={r['reason']}")
    else:
        print("   ❌ AI returned NO leads — this is a bug!")
    
    assert len(results) >= 1, f"AI must detect intercom as lead, got {len(results)}"
    assert results[0]["message"]["id"] == 716254


async def test_live_api_cameras():
    """Live test: AI must detect camera question as lead."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_CAMERAS]
    
    print("\n🧪 Live API test: camera message")
    results = await analyzer.analyze(chunk)
    
    if results:
        print(f"   ✅ AI detected {len(results)} lead(s)")
    else:
        print("   ❌ AI returned NO leads")
    
    assert len(results) >= 1, "AI must detect camera question as lead"


async def test_live_api_expert_not_lead():
    """Live test: expert giving advice should NOT be a lead."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_NOT_LEAD]
    
    print("\n🧪 Live API test: expert (not lead)")
    results = await analyzer.analyze(chunk)
    
    if results:
        print(f"   ⚠️ AI incorrectly detected {len(results)} lead(s)")
        for r in results:
            print(f"   → {r['reason']}")
    else:
        print("   ✅ Correctly rejected expert message")
    
    assert len(results) == 0, "Expert giving advice should NOT be a lead"


async def test_live_api_offtopic():
    """Live test: interior design question should NOT be a lead."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_OFFTOPIC]
    
    print("\n🧪 Live API test: offtopic")
    results = await analyzer.analyze(chunk)
    
    if results:
        print(f"   ⚠️ AI incorrectly detected {len(results)} lead(s)")
    else:
        print("   ✅ Correctly rejected offtopic")
    
    assert len(results) == 0, "Offtopic should not be a lead"


async def test_live_api_smart_home():
    """Live test: smart home question should be a lead."""
    analyzer = AIAnalyzer()
    chunk = [TEST_MESSAGE_SMART_HOME]
    
    print("\n🧪 Live API test: smart home")
    results = await analyzer.analyze(chunk)
    
    if results:
        print(f"   ✅ AI detected {len(results)} lead(s)")
    else:
        print("   ❌ AI returned NO leads")
    
    assert len(results) >= 1, "Smart home question should be a lead"


async def test_live_api_mixed_batch():
    """Live test: mixed batch — should find leads and skip non-leads."""
    analyzer = AIAnalyzer()
    chunk = [
        TEST_MESSAGE_OFFTOPIC,      # not lead
        TEST_MESSAGE_INTERCOM,      # LEAD
        TEST_MESSAGE_NOT_LEAD,      # not lead (expert)
        TEST_MESSAGE_CAMERAS,       # LEAD
        TEST_MESSAGE_SMART_HOME,    # LEAD
    ]
    
    print("\n🧪 Live API test: mixed batch (5 messages, expect 3 leads)")
    results = await analyzer.analyze(chunk)
    
    found_ids = {r["message"]["id"] for r in results}
    expected_ids = {716254, 716255, 716258}
    
    print(f"   Found: {found_ids}")
    print(f"   Expected: {expected_ids}")
    
    if found_ids == expected_ids:
        print("   ✅ Perfect match!")
    else:
        missing = expected_ids - found_ids
        extra = found_ids - expected_ids
        if missing:
            print(f"   ❌ Missed: {missing}")
        if extra:
            print(f"   ⚠️ False positives: {extra}")
    
    assert found_ids == expected_ids, f"Expected {expected_ids}, got {found_ids}"


# ── Runner ─────────────────────────────────────────────────

def run_unit_tests():
    """Run synchronous unit tests."""
    print("=" * 60)
    print("UNIT TESTS (no API calls)")
    print("=" * 60)
    
    tests = [
        test_system_prompt_loaded,
        test_system_prompt_has_few_shot_examples,
        test_system_prompt_no_hardcoded_ids,
        test_format_chunk,
        test_extract_json_clean,
        test_extract_json_with_markdown,
        test_extract_json_with_thinking,
        test_extract_json_empty,
        test_extract_json_empty_leads,
        test_parse_leads_valid,
        test_parse_leads_wrong_id,
        test_parse_leads_no_leads_field,
        test_build_payload_has_thinking_disabled,
        test_build_messages_has_format_instruction,
        test_chunk_messages_respects_batch_size,
        test_chunk_messages_respects_char_limit,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        name = test.__name__
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"❌ {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"💥 {name}: {type(e).__name__}: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"UNIT: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


async def run_live_tests():
    """Run live API tests."""
    print("\n" + "=" * 60)
    print("LIVE API TESTS (real z.ai calls)")
    print("=" * 60)
    
    tests = [
        test_live_api_intercom,
        test_live_api_cameras,
        test_live_api_expert_not_lead,
        test_live_api_offtopic,
        test_live_api_smart_home,
        test_live_api_mixed_batch,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        name = test.__name__
        try:
            await test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"   ❌ ASSERTION: {e}")
        except Exception as e:
            failed += 1
            print(f"   💥 ERROR: {type(e).__name__}: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"LIVE: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    
    # Always run unit tests
    unit_ok = run_unit_tests()
    
    # Run live tests if --live flag
    if "--live" in sys.argv:
        live_ok = asyncio.run(run_live_tests())
        sys.exit(0 if (unit_ok and live_ok) else 1)
    else:
        print("\n💡 Run with --live to test against real z.ai API")
        sys.exit(0 if unit_ok else 1)
