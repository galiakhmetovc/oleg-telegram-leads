# CONFIG.md — Конфигурация

Конфигурация проекта хранится в файле `src/config.py`. Секретные данные (API ключи) также можно задать через `.env` (в корне проекта).

## Порядок загрузки

1. `python-dotenv` загружает `.env` (если существует)
2. Переменные окружения (env) **переопределяют** значения в config.py

## Параметры

### Telegram (userbot — только чтение чатов)

| Параметр | Env var | Дефолт | Описание |
|----------|---------|--------|----------|
| `TELEGRAM_API_ID` | `TELEGRAM_API_ID` | `538845` | API ID Telegram |
| `TELEGRAM_API_HASH` | `TELEGRAM_API_HASH` | `50299bd...` | API Hash Telegram |
| `SESSION_PATH` | — | `BASE_DIR/krab-tg-session` | Путь к файлу сессии userbot |

### Telegram (bot — управляющая группа)

| Параметр | Env var | Дефолт | Описание |
|----------|---------|--------|----------|
| `BOT_TOKEN` | `BOT_TOKEN` | (пусто) | **Обязательный.** Токен бота от @BotFather |
| `BOT_SESSION_PATH` | — | `BASE_DIR/bot-session` | Путь к файлу сессии бота |

### Управляющая группа

| Параметр | Env var | Дефолт | Описание |
|----------|---------|--------|----------|
| `GROUP_CHAT_ID` | `GROUP_CHAT_ID` | `-1003996729093` | ID управляющей группы |
| `GROUP_INVITE_LINK` | — | `https://t.me/+YMCQ2MhiWY5iNzMy` | Ссылка-приглашение |

### z.ai (AI Analyzer)

| Параметр | Env var | Дефолт | Описание |
|----------|---------|--------|----------|
| `ZAI_API_KEY` | `ZAI_API_KEY` | (из TEAMD_PROVIDER_API_KEY) | API ключ z.ai |
| `ZAI_BASE_URL` | — | `https://api.zai.chat/v1` | z.ai endpoint |
| `ZAI_MODEL` | `ZAI_MODEL` | `glm-4.5-air` | Модель для анализа |

### Pipeline

| Параметр | Env var | Дефолт | Описание |
|----------|---------|--------|----------|
| `POLL_INTERVAL` | `POLL_INTERVAL` | `900` | Интервал циклов (сек) |
| `FETCH_LIMIT` | `FETCH_LIMIT` | `100` | Сообщений за запрос к чату |
| `BATCH_SIZE` | `BATCH_SIZE` | `30` | Сообщений в чанк для AI |
| `BATCH_CHAR_LIMIT` | `BATCH_CHAR_LIMIT` | `15000` | Символов в чанк для AI |
| `KEYWORD_THRESHOLD` | `KEYWORD_THRESHOLD` | `75` | Порог совпадения ключевых слов (%) |
| `MAX_LEADS_PER_MESSAGE` | `MAX_LEADS_PER_MESSAGE` | `10` | Максимум лидов в одном сообщении |

### Пути

| Параметр | Описание |
|----------|----------|
| `BASE_DIR` | Корень проекта (`src/config.py/../..`) |
| `DATA_DIR` | `BASE_DIR/data` — checkpoints, leads, chats |
| `ARTIFACTS_DIR` | `BASE_DIR/artifacts` — логи |
| `OBSIDIAN_DIR` | `BASE_DIR/vault/05-Journal/oleg-telegram-leads` |

## .env (пример)

```
BOT_TOKEN=8715577770:AAEoLWaNj0c82IaGkZXVPrUqYO58tdWiNyI
GROUP_CHAT_ID=-1003996729093
ZAI_API_KEY=sk-...
ZAI_MODEL=glm-4.5-air
```
