"""Keyword Scanner — точный поиск по ключевым словам с поддержкой транслитерации.

Алгоритм:
1. Многословные ключевые слова (содержат пробел/_) → fuzz.WRatio по всему тексту
2. Однословные (все длины) → поиск КАК ОТДЕЛЬНОЕ СЛОВО (word boundaries)
3. Все проверки с транслитерацией (ru↔en)
4. partial_ratio НЕ используется — он даёт слишком много ложных срабатываний
"""

import logging
import logging.handlers
import re
from rapidfuzz import fuzz

import sys
sys.path.insert(0, "..")
from src import config

logger = logging.getLogger(__name__)

# Кэш транслитерации
_translit_cache: dict[str, str] = {}


def _transliterate(text: str) -> str:
    """Транслитерация текста ru→en и en→ru."""
    if text in _translit_cache:
        return _translit_cache[text]
    
    try:
        from transliterate import translit
        result = translit(text, "ru", reversed=True)
        _translit_cache[text] = result
        return result
    except Exception:
        return text


def _normalize(text: str) -> str:
    """Нормализация текста: нижний регистр, пунктуация → пробелы."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text)


def _extract_keywords_from_md(keywords_path: str) -> dict[str, list[str]]:
    """Парсинг keywords.md для дополнительных ключевых слов."""
    additional: dict[str, list[str]] = {}
    try:
        with open(keywords_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return additional

    cat_map = {
        "Видеонаблюдение": "видеонаблюдение",
        "Домофония": "домофония",
        "Умный дом": "умный_дом",
        "Автоматизация": "автоматизация",
        "Сигнализация": "сигнализация",
        "Контроль доступа": "контроль_доступа",
        "Сети": "сети",
        "Котлы и отопление": "котлы_отопление",
        "Электрика": "электрика",
    }

    current_cat = None
    in_block = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("## ") and not stripped.startswith("## Как") and not stripped.startswith("## Принципы"):
            cat_name = stripped.lstrip("# ").lstrip("0123456789. ").strip()
            current_cat = cat_map.get(cat_name)
            continue

        if stripped.startswith("```"):
            in_block = not in_block
            if in_block and current_cat:
                additional.setdefault(current_cat, [])
            continue

        if in_block and current_cat and stripped:
            if stripped and not stripped.startswith("#"):
                additional.setdefault(current_cat, []).append(stripped)

    return additional


def _word_match(keyword: str, text_words: list[str]) -> bool:
    """Проверяет, есть ли ключевое слово как отдельное слово в тексте.
    
    Работает для слов с дефисами: 'умный-дом' найдёт 'умный-дом'
    Работает для корневых совпадений с минимальной длиной 4+ символов.
    """
    kw_len = len(keyword)
    
    # 1. Точное совпадение слова
    if keyword in text_words:
        return True
    
    # 2. Для слов 4+ символов: проверяем, начинается ли любое слово текста с keyword
    #    (например, 'видеонаблюдение' найдёт 'видеонаблюдение', 'видеонаблюдением' и т.д.)
    if kw_len >= 4:
        for word in text_words:
            if word == keyword:
                return True
            if word.startswith(keyword) and len(word) - kw_len <= 3:
                return True
            if keyword.startswith(word) and kw_len - len(word) <= 3:
                return True
    
    return False


class KeywordScanner:
    def __init__(self):
        self.categories: dict[str, list[str]] = {}
        
        # Из config.py
        for cat, keywords in config.CATEGORIES.items():
            self.categories[cat] = list(keywords)
        
        # Из keywords.md (дополнительные)
        try:
            additional = _extract_keywords_from_md(config.KEYWORDS_PATH)
            for cat, keywords in additional.items():
                if cat in self.categories:
                    existing = set(kw.lower() for kw in self.categories[cat])
                    for kw in keywords:
                        kw_lower = kw.lower().strip()
                        if kw_lower and kw_lower not in existing:
                            self.categories[cat].append(kw_lower)
                            existing.add(kw_lower)
                else:
                    self.categories[cat] = [kw.lower().strip() for kw in keywords if kw.strip()]
        except Exception as e:
            logger.warning(f"Не удалось загрузить keywords.md: {e}")
        
        self.threshold = config.KEYWORD_THRESHOLD

        # Предобрабатываем ключевые слова: разделяем на многословные и однословные
        self._preprocessed: dict[str, list[dict]] = {}
        for cat, keywords in self.categories.items():
            preprocessed = []
            for kw in keywords:
                kw_lower = kw.lower().strip()
                if not kw_lower:
                    continue
                # Нормализуем: убираем подчёркивания
                kw_normalized = kw_lower.replace("_", " ")
                # Многословное? (содержит пробел)
                is_multword = " " in kw_normalized
                # Длина без пробелов
                clean_len = len(kw_normalized.replace(" ", ""))
                preprocessed.append({
                    "keyword": kw_normalized,
                    "is_multword": is_multword,
                    "clean_len": clean_len,
                })
            self._preprocessed[cat] = preprocessed

        total = sum(len(kws) for kws in self.categories.values())
        logger.info(f"KeywordScanner: {len(self.categories)} категорий, {total} ключевых слов")

    def scan(self, messages: list[dict]) -> list[dict]:
        """Найти сообщения, содержащие ключевые слова."""
        results = []
        
        for msg in messages:
            text = msg["text"]
            if not text or not text.strip():
                continue
            
            text_norm = _normalize(text)
            matches = self._match_categories(text_norm)

            if matches:
                results.append({
                    "message": msg,
                    "categories": matches,
                    "source": "keyword",
                    "matched_keywords": matches,
                })
        return results

    def _match_categories(self, text: str) -> list[dict]:
        """Найти все совпадения по категориям.

        Стратегия:
        - Многословные ключевые слова → fuzz.WRatio по всему тексту (порог 84)
        - Однословные → поиск КАК ОТДЕЛЬНОЕ СЛОВО (word boundaries)
        - НИКОГДА не используем partial_ratio — слишком много ложных срабатываний
        """
        matches = []
        words = text.split()
        text_translit = _transliterate(text)
        words_translit = text_translit.split()

        for category, preprocessed in self._preprocessed.items():
            for kw_info in preprocessed:
                keyword = kw_info["keyword"]
                is_multword = kw_info["is_multword"]

                best_score = 0

                if is_multword:
                    # Многословное: сначала точная подстрока, потом все слова в тексте
                    kw_normalized = keyword.replace("_", " ")
                    
                    # Быстрая проверка: точная подстрока
                    if kw_normalized in text:
                        best_score = 100
                    else:
                        # Строгая проверка: все слова ключа должны быть в тексте
                        kw_words = kw_normalized.split()
                        if all(any(w in tw for tw in words) for w in kw_words):
                            # Все слова найдены — но это может быть совпадение в разных местах
                            # Проверяем: хотя бы 2+ слова должны стоять рядом
                            text_lower = text
                            found_adjacent = False
                            for i in range(len(kw_words)):
                                for j in range(i + 1, len(kw_words)):
                                    # Ищем два слова рядом (до 3 слов между ними)
                                    w1 = kw_words[i]
                                    w2 = kw_words[j]
                                    # Строгое слово (ровно совпадает), не подстрока
                                    w1_positions = [idx for idx, w in enumerate(words) if w == w1]
                                    w2_positions = [idx for idx, w in enumerate(words) if w2 in w]
                                    for p1 in w1_positions:
                                        for p2 in w2_positions:
                                            if abs(p1 - p2) <= 3:
                                                found_adjacent = True
                                                break
                                        if found_adjacent:
                                            break
                                    if found_adjacent:
                                        break
                                if found_adjacent:
                                    break
                            
                            if found_adjacent:
                                best_score = 100
                            else:
                                # Все слова есть, но разбросаны — низкий скор
                                best_score = 70  # Ниже порога (75), не пройдёт
                else:
                    # Однословное: ТОЛЬКО отдельное слово (word boundaries)
                    # Никакого partial_ratio!
                    
                    # 1. Проверяем в оригинальном тексте
                    if _word_match(keyword, words):
                        best_score = 100
                    
                    # 2. Проверяем транслитерацию
                    if best_score == 0:
                        kw_translit = _transliterate(keyword)
                        if kw_translit != keyword:
                            if _word_match(kw_translit, words_translit):
                                best_score = 95

                if best_score >= self.threshold:
                    matches.append({
                        "category": category,
                        "keyword": keyword,
                        "score": best_score,
                    })

        # Сортируем по score, убираем дубликаты категорий
        seen_cats = set()
        unique = []
        for m in sorted(matches, key=lambda x: x["score"], reverse=True):
            if m["category"] not in seen_cats:
                seen_cats.add(m["category"])
                unique.append(m)
        
        return unique
