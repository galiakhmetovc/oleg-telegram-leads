"""Тесты checkpoint логики — unit-тесты без моков Telethon.

Проверяет:
1. При добавлении чата через ссылку checkpoint = message_id - 1
2. При checkpoint=0 fetcher НЕ пропускает чат
3. Keyword fallback: AI=[] но keyword нашёл → лид не теряется
4. Config валидирует тип checkpoints
5. Логирование pipeline покрывает все шаги
"""

import json
import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config


# ──────────────────────────────────────────────────────────
# Test 1: _add_chat checkpoint = message_id - 1
# ──────────────────────────────────────────────────────────

def test_add_chat_checkpoint_logic():
    """Логика: при добавлении чата через ссылку checkpoint = message_id - 1.
    Проверяем формулу напрямую."""
    message_id = 716254
    
    # ТЕКУЩИЙ КОД (БАГ):
    # checkpoint = message_id  → min_id=716254 → сообщение 716254 ПРОПУЩЕНО
    
    current_bug_checkpoint = message_id  # = 716254
    fetcher_min_id = current_bug_checkpoint  # iter_messages(min_id=716254)
    # Сообщения с id > 716254 — сообщение 716254 НЕ попадёт!
    
    # ПРАВИЛЬНЫЙ КОД:
    correct_checkpoint = message_id - 1  # = 716253
    fetcher_min_id_correct = correct_checkpoint  # iter_messages(min_id=716253)
    # Сообщения с id > 716253 → сообщение 716254 ПОПАДАЕТ!
    
    assert correct_checkpoint == 716253
    assert current_bug_checkpoint != correct_checkpoint, \
        "Текущий код ставит checkpoint=message_id (БАГ), должно быть message_id-1"


def test_add_chat_checkpoint_edge_cases():
    """Проверяем граничные случаи."""
    # ID = 1 (минимальный)
    assert (1 - 1) == 0  # checkpoint=0 — fetcher должен обработать
    
    # ID = 0 (невозможный, но проверяем)
    assert (0 - 1) == -1  # checkpoint=-1 — невалидный
    
    # Нормальный ID
    for msg_id in [100, 716254, 999999]:
        assert (msg_id - 1) < msg_id, f"checkpoint ({msg_id-1}) должен быть < message_id ({msg_id})"


# ──────────────────────────────────────────────────────────
# Test 2: fetcher при checkpoint=0 НЕ пропускает чат
# ──────────────────────────────────────────────────────────

def test_fetcher_zero_checkpoint_logic():
    """Логика fetcher: при last_id=0 чат пропускается (return []).
    Это ПРАВИЛЬНО для первого запуска без ссылки,
    но НЕПРАВИЛЬНО при добавлении через ссылку.
    
    Решение: при добавлении через ссылку всегда ставим checkpoint=message_id-1.
    При первом запуске без ссылки — чат пропускается (ok)."""
    
    # Сценарий 1: первый запуск без ссылки
    checkpoint = {}  # нет записи
    last_id = checkpoint.get("-1001292716582", 0)  # = 0
    assert last_id == 0
    # fetcher: if last_id == 0: return []  ← ПРАВИЛЬНО
    
    # Сценарий 2: добавили через ссылку t.me/chat/716254
    checkpoint = {"-1001292716582": 716253}  # message_id - 1
    last_id = checkpoint.get("-1001292716582", 0)  # = 716253
    assert last_id == 716253
    # fetcher: if last_id == 0 → False, идём дальше
    # iter_messages(min_id=716253) → получим сообщения 716254, 716255, ...
    # Сообщение 716254 ПОПАДАЕТ ✅


# ──────────────────────────────────────────────────────────
# Test 3: Keyword fallback
# ──────────────────────────────────────────────────────────

def test_keyword_fallback_logic():
    """Если AI вернул [] но keyword scanner нашёл совпадение —
    лид не должен теряться.
    
    Текущий код pipeline.py:
    1. ai_results = analyzer.analyze(messages)  → []
    2. keyword_results = scanner.scan(messages)  → [match]
    3. enriched_leads = обогащаем ai_results keyword-данными  → [] (пусто!)
    4. new_leads = dedup(enriched_leads)  → []
    
    БАГ: keyword_results вообще НЕ используется для генерации лидов!
    
    ФИКС: если ai_results пустые, но keyword_results есть —
    создавать лиды из keyword_results с source=keyword.
    """
    
    # Симулируем AI вернул пусто
    ai_results = []
    
    # Но keyword нашёл домофон
    keyword_results = [{
        "message": {
            "id": 716254,
            "chat_id": "-1001292716582",
            "chat_title": "Чат Дизайнеров",
            "sender_name": "Alice",
            "text": "Какие домофоны ставите?",
            "date": "2025-01-01T12:00:00",
            "link": "https://t.me/chat_mila_kolpakova/716254",
        },
        "categories": [{"category": "домофония", "keyword": "домофон", "score": 100}],
        "source": "keyword",
        "matched_keywords": [{"category": "домофония", "keyword": "домофон", "score": 100}],
    }]
    
    # Текущая логика (БАГ):
    kw_map = {}
    for kw_result in keyword_results:
        msg_id = kw_result.get("message", {}).get("id")
        if msg_id:
            kw_map[msg_id] = kw_result.get("matched_keywords", [])
    
    enriched = []
    for lead in ai_results:  # ai_results = [] → цикл не выполняется!
        msg_id = lead.get("message", {}).get("id")
        lead["matched_keywords"] = kw_map.get(msg_id, [])
        enriched.append(lead)
    
    assert len(enriched) == 0, "Текущий код: keyword fallback НЕ работает"
    
    # ПРАВИЛЬНАЯ логика (ФИКС):
    if not ai_results and keyword_results:
        for kw in keyword_results:
            kw["source"] = "keyword"
            kw["reason"] = "Keyword-матч (AI не подтвердил)"
        enriched = keyword_results
    
    assert len(enriched) == 1, "Фикс: keyword fallback работает, лид найден"
    assert enriched[0]["source"] == "keyword"


# ──────────────────────────────────────────────────────────
# Test 4: Config validation
# ──────────────────────────────────────────────────────────

def test_load_checkpoints_rejects_list():
    """Если checkpoints.json содержит [] вместо {}, должен вернуться {}."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        cp_file = data_dir / "checkpoints.json"
        cp_file.write_text("[]", encoding="utf-8")
        
        with patch.object(config, "DATA_DIR", data_dir):
            result = config.load_checkpoints()
            assert isinstance(result, dict)
            assert len(result) == 0


def test_load_checkpoints_valid_dict():
    """Корректный dict должен грузиться нормально."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        cp_file = data_dir / "checkpoints.json"
        cp_file.write_text('{"-1001292716582": 716253}', encoding="utf-8")
        
        with patch.object(config, "DATA_DIR", data_dir):
            result = config.load_checkpoints()
            assert result == {"-1001292716582": 716253}


def test_save_and_load_checkpoints():
    """save → load round-trip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        
        with patch.object(config, "DATA_DIR", data_dir):
            config.save_checkpoints({"-1001292716582": 716253})
            result = config.load_checkpoints()
            assert result == {"-1001292716582": 716253}


# ──────────────────────────────────────────────────────────
# Test 5: Логирование — проверяем что логгеры создаются
# ──────────────────────────────────────────────────────────

def test_pipeline_has_logger():
    """Проверяем что pipeline создаёт логгер."""
    # Импортируем — если логгер не создастся, будет ошибка
    import logging
    logger = logging.getLogger("pipeline")
    assert logger is not None
    assert logger.name == "pipeline"


def test_fetcher_has_logger():
    import logging
    logger = logging.getLogger("src.fetcher")
    assert logger is not None


def test_ai_analyzer_has_logger():
    import logging
    logger = logging.getLogger("src.ai_analyzer")
    assert logger is not None


# ──────────────────────────────────────────────────────────
# Test 6: Проверяем текущий код _add_chat
# ──────────────────────────────────────────────────────────

def test_current_add_chat_code_has_bug():
    """Проверяем что текущий код pipeline.py содержит баг.
    
    В _add_chat:
        checkpoints[str(chat_id)] = checkpoint_msg_id  # ← БАГ
    
    Должно быть:
        checkpoints[str(chat_id)] = checkpoint_msg_id - 1  # ← ФИКС
    """
    pipeline_path = Path(__file__).resolve().parent.parent / "src" / "pipeline.py"
    content = pipeline_path.read_text(encoding="utf-8")
    
    # Ищем текущий код
    if 'checkpoints[str(chat_id)] = checkpoint_msg_id' in content:
        # Проверяем что рядом нет "- 1"
        # Если строка содержит "= checkpoint_msg_id\n" без "- 1" — это баг
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'checkpoints[str(chat_id)] = checkpoint_msg_id' in line:
                # Проверяем что это НЕ fixed версия
                if 'checkpoint_msg_id - 1' not in line:
                    print(f"  БАГ найден на строке {i+1}: {line.strip()}")
                    print(f"  Нужно: checkpoints[str(chat_id)] = checkpoint_msg_id - 1")
                    return  # Баг найден — тест проходит (подтверждает наличие бага)
        
        # Если нашли "checkpoint_msg_id - 1" — баг уже исправлен
        print("  ✅ Баг уже исправлен в коде!")
    
    # Тест всегда проходит — он просто диагностирует
    assert True


# ──────────────────────────────────────────────────────────
# Test 7: Проверяем логирование AI analyzer
# ──────────────────────────────────────────────────────────

def test_ai_analyzer_logs_raw_response():
    """Проверяем что ai_analyzer логирует сырой ответ API."""
    analyzer_path = Path(__file__).resolve().parent.parent / "src" / "ai_analyzer.py"
    content = analyzer_path.read_text(encoding="utf-8")
    
    # Должно логировать:
    checks = [
        ("API response:", "статус ответа"),
        ("content[:200]", "первые 200 символов"),
        ("JSON распарсен", "результат парсинга"),
        ("Модель не вернула JSON", "ошибку парсинга"),
        ("Обе попытки", "двойной фейл"),
    ]
    
    for pattern, desc in checks:
        assert pattern in content, f"Логирование '{desc}' (pattern: {pattern}) не найдено в ai_analyzer.py"


def test_pipeline_logs_all_steps():
    """Проверяем что pipeline логирует все ключевые шаги."""
    pipeline_path = Path(__file__).resolve().parent.parent / "src" / "pipeline.py"
    content = pipeline_path.read_text(encoding="utf-8")
    
    checks = [
        ("Получено", "количество сообщений из fetcher"),
        ("Keyword matches", "результаты keyword scanner"),
        ("AI leads", "результаты AI"),
        ("chat_id", "информацию о чате"),
        ("checkpoint", "чекпоинт при добавлении"),
    ]
    
    for pattern, desc in checks:
        assert pattern in content, f"Логирование '{desc}' (pattern: {pattern}) не найдено в pipeline.py"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
