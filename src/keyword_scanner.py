"""Keyword Scanner — нечёткий поиск по ключевым словам с учётом опечаток и транслитерации."""
import logging
from rapidfuzz import fuzz, process

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
        from transliterate import translit, get_available_language_codes
        # ru -> en
        result = translit(text, "ru", reversed=True)
        _translit_cache[text] = result
        return result
    except Exception:
        return text


def _normalize(text: str) -> str:
    """Нормализация текста: нижний регистр."""
    return text.lower().strip()


def _extract_keywords_from_md(keywords_path: str) -> dict[str, list[str]]:
    """Парсинг keywords.md для дополнительных ключевых слов."""
    additional: dict[str, list[str]] = {}
    try:
        with open(keywords_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return additional
    
    current_category = None
    in_code_block = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        
        if not in_code_block:
            continue
        
        if not stripped or stripped.startswith("#"):
            continue
        
        # Это ключевое слово внутри блока кода
        if current_category:
            additional.setdefault(current_category, []).append(stripped)
    
    # Нужно сопоставить блоки кода с категориями — упрощённая версия:
    # Если файл keywords.md структурирован правильно, читаем блоки кода под заголовками
    additional = {}
    current_cat = None
    in_block = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("## ") and not stripped.startswith("## Как") and not stripped.startswith("## Принципы"):
            # Новая категория
            cat_name = stripped.lstrip("# ").lstrip("0123456789. ").strip()
            # Маппинг заголовков на ключи категорий
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
            current_cat = cat_map.get(cat_name)
            continue
        
        if stripped.startswith("```"):
            in_block = not in_block
            if in_block and current_cat:
                additional.setdefault(current_cat, [])
            continue
        
        if in_block and current_cat and stripped:
            # Пропускаем пустые строки и комментарии
            if stripped and not stripped.startswith("#"):
                additional.setdefault(current_cat, []).append(stripped)
    
    return additional


class KeywordScanner:
    def __init__(self):
        # Объединяем ключевые слова из config и из keywords.md
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
        
        # Логируем статистику
        total = sum(len(kws) for kws in self.categories.values())
        logger.info(f"KeywordScanner: {len(self.categories)} категорий, {total} ключевых слов")

    def scan(self, messages: list[dict]) -> list[dict]:
        """Найти сообщения, содержащие ключевые слова."""
        results = []
        
        for msg in messages:
            text_lower = _normalize(msg["text"])
            matches = self._match_categories(text_lower)
            
            if matches:
                results.append({
                    "message": msg,
                    "categories": matches,
                    "source": "keyword",
                })
        
        logger.info(f"Keyword-матчи: {len(results)} из {len(messages)} сообщений")
        return results

    def _match_categories(self, text: str) -> list[dict]:
        """Найти все совпадения по категориям."""
        matches = []
        text_translit = _transliterate(text)
        
        # Разбиваем текст на слова для поиска подстрок
        words = text.split()
        words_translit = text_translit.split()
        
        for category, keywords in self.categories.items():
            for keyword in keywords:
                kw_lower = keyword.lower()
                
                # Ищем среди слов сообщения
                best_score = 0
                
                for word in words:
                    # Прямое совпадение / нечёткое совпадение
                    score = fuzz.partial_ratio(kw_lower, word)
                    best_score = max(best_score, score)
                
                # Проверяем транслитерированный вариант
                kw_translit = _transliterate(kw_lower)
                if kw_translit != kw_lower:
                    for word in words_translit:
                        score = fuzz.partial_ratio(kw_translit, word)
                        best_score = max(best_score, score)
                
                # Также проверяем, не содержится ли ключевое слово целиком в тексте
                if kw_lower in text:
                    best_score = 100
                
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
