"""AI Analyzer — семантический анализ сообщений через z.ai (glm-4.5-air)."""
import json
import logging
import re
import httpx

import sys
sys.path.insert(0, "..")
from src import config

logger = logging.getLogger(__name__)

# Системный промпт — загружается из prompts.md или используется дефолтный
SYSTEM_PROMPT = ""


def _load_system_prompt() -> str:
    """Загрузить системный промпт из prompts.md."""
    global SYSTEM_PROMPT
    if SYSTEM_PROMPT:
        return SYSTEM_PROMPT
    
    try:
        with open(config.PROMPT_PATH, "r") as f:
            content = f.read()
        
        # Извлекаем промпт из блока ```text ... ```
        match = re.search(r"```text\s*\n(.*?)```", content, re.DOTALL)
        if match:
            SYSTEM_PROMPT = match.group(1).strip()
        else:
            # Фоллбэк: берём всё после "## Системный промпт"
            match = re.search(r"## Системный промпт.*?\n```", content, re.DOTALL)
            if match:
                SYSTEM_PROMPT = match.group(0)
                SYSTEM_PROMPT = re.sub(r"```text\s*\n?", "", SYSTEM_PROMPT)
                SYSTEM_PROMPT = SYSTEM_PROMPT.rstrip("`").strip()
    
    except FileNotFoundError:
        logger.warning("Файл %s не найден, используется дефолтный промпт", config.PROMPT_PATH)
    
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = """Ты — аналитик лидов для эксперта по умным домам. Найди сообщения, где человек:
1. Запрашивает совет по оборудованию
2. Задаёт вопрос об установке/монтаже
3. Не может определиться с выбором
4. Ищет исполнителя
5. Планирует покупку
6. Жалуется на проблему с оборудованием

Верни ТОЛЬКО JSON-массив: [{"id": 123, "reason": "причина"}]
Если ничего не найдено — верни []"""
    
    return SYSTEM_PROMPT


FALLBACK_PROMPT = """Проанализируй сообщения и верни JSON-массив с ID тех сообщений, где человек ищет помощь по темам: камеры, видеонаблюдение, домофон, умный дом, автоматизация, сигнализация, котлы, теплый пол, отопление.

Формат: [{"id": 123, "reason": "причина"}]
Если ничего не найдено — верни []

Сообщения:
{chunk}"""


class AIAnalyzer:
    def __init__(self):
        self.api_key = config.ZAI_API_KEY
        self.base_url = config.ZAI_BASE_URL
        self.model = config.ZAI_MODEL
        self.batch_size = config.BATCH_SIZE
        self.batch_char_limit = config.BATCH_CHAR_LIMIT
        self.temperature = config.AI_TEMPERATURE
        self.system_prompt = _load_system_prompt()

    async def analyze(self, messages: list[dict]) -> list[dict]:
        """Проанализировать сообщения через LLM."""
        if not messages:
            return []
        
        if not self.api_key:
            logger.warning("ZAI_API_KEY не задан, AI-анализ пропущен")
            return []
        
        chunks = self._chunk_messages(messages)
        results = []
        
        for i, chunk in enumerate(chunks):
            try:
                response = await self._call_llm(chunk)
                results.extend(response)
                logger.info("AI-чанк %d/%d: %d совпадений", i + 1, len(chunks), len(response))
            except Exception as e:
                logger.error("AI-анализ чанка %d не удался: %s", i + 1, e)
                # Пробуем fallback
                try:
                    response = await self._call_llm_fallback(chunk)
                    results.extend(response)
                    logger.info("Fallback чанк %d: %d совпадений", i + 1, len(response))
                except Exception as e2:
                    logger.error("Fallback чанк %d тоже не удался: %s", i + 1, e2)
        
        logger.info("AI-всего: %d совпадений из %d сообщений", len(results), len(messages))
        return results

    def _chunk_messages(self, messages: list[dict]) -> list[list[dict]]:
        """Разбить сообщения на чанки."""
        chunks = []
        current_chunk = []
        current_chars = 0
        
        for msg in messages:
            msg_chars = len(msg.get("text", ""))
            
            if current_chunk and (
                len(current_chunk) >= self.batch_size or
                current_chars + msg_chars > self.batch_char_limit
            ):
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
            
            current_chunk.append(msg)
            current_chars += msg_chars
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def _format_chunk(self, chunk: list[dict]) -> str:
        """Форматировать чанк для LLM."""
        lines = []
        for msg in chunk:
            lines.append(f"[{msg['id']}] @{msg['sender_name']}: {msg['text']}")
        return "\n".join(lines)

    async def _call_llm(self, chunk: list[dict]) -> list[dict]:
        """Отправить чанк в LLM и распарсить ответ."""
        user_content = self._format_chunk(chunk)
        
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                },
            )
        
        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text[:500]}")
        return self._parse_response(response.json(), chunk)

    async def _call_llm_fallback(self, chunk: list[dict]) -> list[dict]:
        """Повторный запрос с упрощённым промптом."""
        user_content = self._format_chunk(chunk)
        
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.0,
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "user", "content": FALLBACK_PROMPT.format(chunk=user_content)},
                    ],
                },
            )
        
        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text[:500]}")
        return self._parse_response(response.json(), chunk)

    def _parse_response(self, llm_response: dict, chunk: list[dict]) -> list[dict]:
        """Распарсить JSON-ответ LLM."""
        try:
            content = llm_response["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            logger.error("Невалидный формат ответа LLM")
            return []
        
        # Извлекаем JSON из текста (LLM может обернуть в markdown)
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if not json_match:
            logger.warning("Не найден JSON в ответе: %s", content[:200])
            return []
        
        try:
            matches = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.error("Ошибка парсинга JSON: %s", e)
            return []
        
        if not isinstance(matches, list):
            logger.error("Ответ LLM не является массивом")
            return []
        
        # Фильтруем: оставляем только те, у которых message_id есть в чанке
        chunk_ids = {m["id"] for m in chunk}
        results = []
        
        for match in matches:
            if not isinstance(match, dict):
                continue
            msg_id = match.get("id")
            if msg_id not in chunk_ids:
                continue
            msg = next(m for m in chunk if m["id"] == msg_id)
            results.append({
                "message": msg,
                "reason": match.get("reason", ""),
                "source": "ai",
            })
        
        return results
