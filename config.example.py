"""Конфигурация Telegram Leads Finder.

Скопируйте этот файл в src/config.py и заполните реальные значения.
Секреты лучше задать через .env файл (см. .env.example).
"""
import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
OBSIDIAN_DIR = BASE_DIR / "vault" / "05-Journal" / "oleg-telegram-leads"

load_dotenv(BASE_DIR / ".env")

# ── Telegram (userbot — только чтение чатов) ────────────
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", ""))       # Обязательный!
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")         # Обязательный!
SESSION_PATH = BASE_DIR / "krab-tg-session"

# ── Telegram (bot — управляющая группа, уведомления) ────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")                         # Обязательный!
BOT_SESSION_PATH = BASE_DIR / "bot-session"

# ── Управляющая группа ───────────────────────────────────
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", ""))            # Обязательный!
GROUP_INVITE_LINK = ""  # Заполните после создания группы

# ── Антон — для @mention при найденных лидах ─────────────
ANTON_TELEGRAM_ID = 0  # Заполните реальным ID

# ── z.ai (AI Analyzer) ──────────────────────────────────
ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
ZAI_BASE_URL = "https://api.zai.chat/v1"
ZAI_MODEL = os.getenv("ZAI_MODEL", "glm-4.5-air")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.1"))

# ── Pipeline параметры ──────────────────────────────────
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "900"))         # 15 минут
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "100"))             # сообщений за запрос
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "30"))                # сообщений в чанк AI
BATCH_CHAR_LIMIT = int(os.getenv("BATCH_CHAR_LIMIT", "15000"))
KEYWORD_THRESHOLD = float(os.getenv("KEYWORD_THRESHOLD", "75")) # % совпадения
MAX_LEADS_PER_MESSAGE = int(os.getenv("MAX_LEADS_PER_MESSAGE", "10"))

# ── Пути к данным ───────────────────────────────────────
KEYWORDS_PATH = BASE_DIR / "docs" / "keywords.md"
PROMPT_PATH = BASE_DIR / "docs" / "prompts.md"
