"""AI Analyzer — семантический анализ сообщений через z.ai (glm-5.1)."""

import json
import logging
import logging.handlers
import httpx
import re
import sys

sys.path.insert(0, "..")
from src import config

logger = logging.getLogger(__name__)

# File logging
import os as _os
from pathlib import Path as _Path
_ai_log_dir = _os.getenv("LOG_DIR", str(_Path(__file__).resolve().parent.parent / "artifacts" / "logs"))
_Path(_ai_log_dir).mkdir(parents=True, exist_ok=True)
_ai_fh = logging.handlers.RotatingFileHandler(
    str(_Path(_ai_log_dir) / "ai-analyzer.log"),
    maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_ai_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_ai_fh.setLevel(logging.DEBUG)
logging.getLogger(__name__).addHandler(_ai_fh)


def _load_system_prompt() -> str:
    """Загрузить системный промпт из prompts.md целиком."""
    try:
        with open(config.PROMPT_PATH, "r") as f:
            content = f.read()

        prompt = content.strip()
        logger.info("Промпт загружен из prompts.md, длина: %d символов", len(prompt))
        return prompt

    except FileNotFoundError:
        logger.warning("Файл %s не найден", config.PROMPT_PATH)
    except Exception as e:
        logger.error("Ошибка загрузки промпта: %s", e)

    return ""


# Загружаем промпт один раз при импорте
SYSTEM_PROMPT = _load_system_prompt()

if not SYSTEM_PROMPT:
    logger.warning("⚠️ Системный промпт пустой! AI будет использовать fallback-промпт.")
else:
    logger.info("✅ Системный промпт загружен (%d символов)", len(SYSTEM_PROMPT))

FALLBACK_PROMPT = """Проанализируй сообщения и верни JSON-объект с полем "leads" — массивом объектов {"id": число, "reason": "причина"} для тех сообщений, где человек ищет помощь по темам: камеры, видеонаблюдение, домофон, умный дом, автоматизация, сигнализация, котлы, теплый пол, отопление, электрика, видеодомофон, датчики, роутеры, Wi-Fi, сети, контроль доступа, охрана, турникеты, шлагбаумы.

Формат: {"leads": [{"id": 123, "reason": "причина"}]}
Если ничего не найдено — верни {"leads": []}

Сообщения:
{chunk}"""


class AIAnalyzer:
    def __init__(self):
        self.api_key = config.ZAI_API_KEY
        self.base_url = config.ZAI_BASE_URL.rstrip("/")
        self.model = config.ZAI_MODEL
        self.batch_size = config.BATCH_SIZE
        self.batch_char_limit = config.BATCH_CHAR_LIMIT
        self.temperature = config.AI_TEMPERATURE
        self.system_prompt = SYSTEM_PROMPT

    async def analyze(self, messages: list[dict]) -> list[dict]:
        """Проанализировать сообщения через LLM."""
        logger.info("analyze(): %d messages, batch=%d, char_limit=%d, model=%s",
                     len(messages), self.batch_size, self.batch_char_limit, self.model)
        if not messages:
            return []

        if not self.api_key:
            logger.warning("ZAI_API_KEY не задан, AI-анализ пропущен")
            return []

        if not self.system_prompt:
            logger.warning("Системный промпт пустой, используется fallback")

        chunks = self._chunk_messages(messages)
        results = []

        for i, chunk in enumerate(chunks):
            try:
                logger.info("Processing chunk %d/%d (%d msgs)", i + 1, len(chunks), len(chunk))
                response = await self._call_llm_with_retry(chunk)
                results.extend(response)
                logger.info("Chunk %d/%d done: %d leads", i + 1, len(chunks), len(response))
            except Exception as e:
                logger.error("AI-анализ чанка %d не удался: %s", i + 1, e)

        logger.info("analyze() DONE: %d leads from %d messages", len(results), len(messages))
        return results

    def _chunk_messages(self, messages: list[dict]) -> list[list[dict]]:
        """Разбить сообщения на чанки."""
        chunks = []
        current_chunk = []
        current_chars = 0

        for msg in messages:
            msg_chars = len(msg.get("text", ""))

            if current_chunk and (
                len(current_chunk) >= self.batch_size
                or current_chars + msg_chars > self.batch_char_limit
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

    def _extract_json(self, text: str):
        """Извлечь JSON из текста ответа LLM.

        Пытается:
        1. json.loads() — если весь текст — JSON
        2. Извлечь из ```json ... ```
        3. Найти { и } — JSON-объект
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # Шаг 1: весь текст — JSON
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Шаг 2: извлечь из markdown code block
        md_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Шаг 3: найти JSON-объект по { и }
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    def _build_messages(self, chunk: list[dict]) -> list[dict]:
        """Build messages for API."""
        logger.debug("_build_messages: %d msgs, sys_prompt_len=%d", len(chunk), len(self.system_prompt) if self.system_prompt else 0)
        """Построить массив messages для API."""
        user_content = self._format_chunk(chunk)
        user_content += '\n\nВерни JSON-объект {"leads": [{"id": число, "reason": "краткая причина"}]}. Если лидов нет — {"leads": []}.'

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_payload(self, messages: list[dict]) -> dict:
        """Построить payload для API."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": 4096,
            "messages": messages,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
    async def _post_api(self, payload: dict) -> dict:
        """Send POST to API."""
        logger.debug("_post_api: model=%s msgs=%d", payload.get("model"), len(payload.get("messages", [])))
        """Отправить запрос к API и вернуть ответ."""
        async with httpx.AsyncClient(timeout=60.0) as http:
            logger.debug("API req: url=%s model=%s temp=%s", self.base_url, self.model, self.temperature)
            response = await http.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )

        logger.debug("API resp: status=%d", response.status_code)
        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text[:1000]}")

        return response.json()

    def _get_content(self, resp_data: dict) -> str | None:
        """Extract content from API response."""
        logger.debug("_get_content: keys=%s", list(resp_data.keys())[:5])
        """Извлечь content из ответа API."""
        if "choices" not in resp_data or not resp_data["choices"]:
            return None
        return resp_data["choices"][0].get("message", {}).get("content", "")

    def _parse_leads(self, data: dict, chunk: list[dict]) -> list[dict]:
        """Extract leads from parsed JSON."""
        leads_raw = data.get("leads", [])
        logger.info("_parse_leads: raw leads count=%s, chunk_ids=%s", len(leads_raw) if isinstance(leads_raw, list) else type(leads_raw).__name__, [m["id"] for m in chunk])
        """Извлечь лиды из распарсенного JSON."""
        leads = data.get("leads", [])
        if not isinstance(leads, list):
            return []

        chunk_ids = {m["id"] for m in chunk}
        results = []

        for match in leads:
            if not isinstance(match, dict):
                continue
            msg_id = match.get("id")
            if msg_id not in chunk_ids:
                continue
            msg = next((m for m in chunk if m["id"] == msg_id), None)
            if not msg:
                continue
            results.append({
                "message": msg,
                "reason": match.get("reason", ""),
                "source": "ai",
            })

        return results

    async def _call_llm_with_retry(self, chunk: list[dict]) -> list[dict]:
        """Отправить чанк в LLM с ретраями.

        Если модель не вернула JSON — продолжаем диалог и просим исправить.
        Максимум 2 попытки.
        """
        messages = self._build_messages(chunk)
        payload = self._build_payload(messages)

        logger.info(
            "AI-запрос: модель=%s, чанк из %d сообщений, %d символов",
            self.model, len(chunk), len(self._format_chunk(chunk)),
        )

        # Попытка 1
        try:
            resp_data = await self._post_api(payload)
        except Exception as e:
            logger.error("AI-запрос не удался: %s", e)
            return []

        content = self._get_content(resp_data)
        logger.info("API response: status=200, content_len=%d", len(content) if content else 0)

        if content:
            logger.info("AI-ответ content[:200]: %s", repr(content[:200]))

        data = self._extract_json(content)
        if data is not None:
            logger.info("JSON распарсен успешно с первой попытки")
            return self._parse_leads(data, chunk)

        # Модель не вернула JSON — продолжаем диалог
        logger.warning("Модель не вернула JSON, пробуем повторно...")

        retry_msg = (
            "Ты вернул ответ не в формате JSON. "
            'Пожалуйста, верни ТОЛЬКО JSON-объект: {"leads": [{"id": число, "reason": "краткая причина"}]}. '
            'Если лидов нет — {"leads": []}. Никакого текста перед или после JSON.'
        )

        # Добавляем ответ модели и наш запрос в историю диалога
        messages.append({"role": "assistant", "content": content or "(пустой ответ)"})
        messages.append({"role": "user", "content": retry_msg})

        payload = self._build_payload(messages)

        # Попытка 2
        try:
            resp_data = await self._post_api(payload)
        except Exception as e:
            logger.error("Повторный AI-запрос не удался: %s", e)
            return []

        content = self._get_content(resp_data)
        logger.info("Повторный ответ: content_len=%d", len(content) if content else 0)

        if content:
            logger.info("Повторный ответ content[:200]: %s", repr(content[:200]))

        data = self._extract_json(content)
        if data is not None:
            logger.info("JSON распарсен успешно со второй попытки")
            return self._parse_leads(data, chunk)

        # Обе попытки провалились
        logger.error("Обе попытки получения JSON провалились. Пропускаем чанк.")
        if content:
            logger.error("Последний ответ модели: %s", content[:500])
        return []
