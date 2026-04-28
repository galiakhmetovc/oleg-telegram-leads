"""Конфигурация Telegram Leads Finder.

Секреты: BOT_TOKEN, ZAI_API_KEY — через .env или переменные окружения.
"""
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
OBSIDIAN_DIR = Path(os.getenv("OBSIDIAN_DIR", str(BASE_DIR / "vault" / "05-Journal" / "oleg-telegram-leads")))

load_dotenv(BASE_DIR / ".env")

# ── Telegram (userbot — только чтение чатов) ────────────
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "538845"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "50299bd63cc0569f338c33999d0dfe6b")
SESSION_PATH = Path(os.getenv("SESSION_PATH", str(BASE_DIR / "krab-tg-session")))

# ── Telegram (bot — управляющая группа, уведомления) ────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")  # Обязательный! Через .env
BOT_SESSION_PATH = Path(os.getenv("BOT_SESSION_PATH", str(BASE_DIR / "bot-session")))

# ── Управляющая группа ───────────────────────────────────
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1003996729093"))
GROUP_INVITE_LINK = "https://t.me/+YMCQ2MhiWY5iNzMy"

# ── Антон — для @mention при найденных лидах ─────────────
ANTON_TELEGRAM_ID = 352122033  # @AntonBezkrovnyy

# ── z.ai (AI Analyzer) ──────────────────────────────────
ZAI_API_KEY = os.getenv("ZAI_API_KEY", os.getenv("TEAMD_PROVIDER_API_KEY", ""))
ZAI_BASE_URL = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
ZAI_MODEL = os.getenv("ZAI_MODEL", "glm-4.5")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.1"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR.parent / "artifacts" / "logs"))

# ── Pipeline параметры ──────────────────────────────────
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "900"))  # 15 минут
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "500"))       # сообщений за запрос (один API call)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "15"))          # сообщений в чанк AI
BATCH_CHAR_LIMIT = int(os.getenv("BATCH_CHAR_LIMIT", "5000"))
KEYWORD_THRESHOLD = float(os.getenv("KEYWORD_THRESHOLD", "75"))  # % совпадения
MAX_LEADS_PER_MESSAGE = int(os.getenv("MAX_LEADS_PER_MESSAGE", "10"))

# ── Пути к данным ───────────────────────────────────────
KEYWORDS_PATH = BASE_DIR / "docs" / "keywords.md"
PROMPT_PATH = BASE_DIR / "docs" / "prompts.md"

# ── Категории ключевых слов (базовые) ───────────────────
CATEGORIES = {
    "видеонаблюдение": ["камера", "видеонаблюдение", "видеокамера", "ip камера", "cctv",
                         "ip-камера", "камеры", "видеорегистратор", "nvr", "dvr",
                         "ptz", "аналитика", "обнаружение", "детекция"],
    "домофония": ["домофон", "видеодомофон", "вызывная панель", "intercom",
                   "межкомнатный", "переговорное"],
    "умный_дом": ["умный дом", "smart home",
                  "zigbee", "mqtt", "xiaomi", "tuya",
                  "умная розетка", "умный выключатель"],
    "автоматизация": ["автоматика", "автоматизация", "сценарий", "script",
                      "пульт", "прошивка", "firmware", "integration"],
    "сигнализация": ["сигнализация", "охранная", "тревожная кнопка"],
    "контроль_доступа": ["скуд", "турникет", "карта доступа", "biometric",
                          "биометрия", "баркод", "считыватель"],
    "сети": ["витая пара", "кабель", "роутер", "switch", "access point",
             "wi-fi", "оптоволокно", "lan", "vlan"],
    "котлы_отопление": ["котел", "отопление", "теплый пол", "бойлер",
                         "радиатор", "теплоноситель", "термостат",
                         "дымоход"],
    "электрика": ["электрика", "электромонтаж", "щиток",
                  "заземление", "монтаж"],
}


# ── Данные: чаты ────────────────────────────────────────
def load_chats() -> list[dict]:
    """Загружает список чатов из data/chats.json."""
    chats_file = DATA_DIR / "chats.json"
    if chats_file.exists():
        with open(chats_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_chats(chats: list[dict]) -> None:
    """Сохраняет список чатов в data/chats.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "chats.json", "w", encoding="utf-8") as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)


# ── Данные: чекпоинты ───────────────────────────────────
def load_checkpoints() -> dict:
    """Загружает чекпоинты из data/checkpoints.json."""
    cp_file = DATA_DIR / "checkpoints.json"
    if cp_file.exists():
        with open(cp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning("checkpoints.json содержит %s вместо dict, сбрасываю", type(data).__name__)
    return {}


def save_checkpoints(checkpoints: dict) -> None:
    """Сохраняет чекпоинты в data/checkpoints.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "checkpoints.json", "w", encoding="utf-8") as f:
        json.dump(checkpoints, f, ensure_ascii=False, indent=2)
