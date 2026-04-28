# Telegram Leads Finder

Автоматизированная система выявления потенциальных клиентов в открытых Telegram-группах для ниши **умные дома / автоматизация / видеонаблюдение / домофония / котлы / сигнализация**.

## Зачем

Олег — эксперт по умным домам и автоматизации. Люди ежедневно спрашивают в чатах про камеры, термостаты, умные розетки, видеодомофоны, котлы и т.д. Система автоматически:

1. **Выгружает** новые сообщения из целевых чатов (Telethon userbot)
2. **Сканирует** по ключевым словам (rapidfuzz, ~380 слов, 9 категорий)
3. **Анализирует** семантику через LLM (z.ai, glm-4.5) — находит запросы, где человек выбирает/ищет оборудование
4. **Уведомляет** Антона в управляющую группу с @mention и ссылкой на сообщение

## Текущий статус

**Стадия:** 🟢 работает в Docker (restart: always), AI-интеграция настроена

**Что сделано:**
- ✅ 6 модулей в `src/` (config, fetcher, keyword_scanner, ai_analyzer, notifier, pipeline)
- ✅ Два Telegram-клиента: userbot `@krab_ai_agent` (чтение) + bot `@ext_team_f_bot` (группа)
- ✅ Daemon-режим: listener в группе + циклический опрос чатов каждые 15 мин
- ✅ Bot commands: /help, /status, /run, /list, /reset, /remove, /recheck, /leads
- ✅ Добавление чатов по ссылке `t.me/chat/123` и пересылке
- ✅ Keyword scanner: ~380 ключевых слов, 9 категорий, rapidfuzz
- ✅ AI analyzer: glm-4.5, few-shot промпт, thinking mode off
- ✅ Только AI-подтверждённые лиды (keyword-only не отправляются)
- ✅ Direct fetch для целевых сообщений (обход удалённых сообщений в Telegram)
- ✅ Caption extraction (media + текст)
- ✅ @mention Антона при найденных лидах
- ✅ Статус-репорт каждый цикл
- ✅ RotatingFileHandler логирование (leads-finder.log, ai-analyzer.log)
- ✅ Docker deploy + reset_and_rebuild.sh
- ✅ Тесты: unit + live (AI API)
- ✅ Документация: 22 ADR, architecture, config, keywords, prompts

## Как работает

```
pipeline.py --daemon
    │
    ├─► Bot event handler (управляющая группа)
    │       ├─ /status, /run, /list, /reset, /remove, /recheck, /leads, /help
    │       └─ ссылки / пересылки — добавление чатов
    │
    └─► Scheduler loop (каждые 15 мин)
            └─► run_once()
                ├─► fetcher.py          → новые сообщения из чатов
                │                          (direct fetch + iter_messages)
                ├─► keyword_scanner.py  → нечёткий поиск по ключевым словам
                │                          (только логирование, не отправляет)
                ├─► ai_analyzer.py      → семантический анализ через z.ai
                │                          (glm-4.5, thinking off, few-shot)
                ├─► merge + dedup       → объединение результатов
                ├─► notifier.py         → @mention Антона + уведомления
                └─► Obsidian            → запись результатов (отключена)
```

## Управление через Telegram

### Команды

| Команда | Описание |
|---------|----------|
| `/status` | Статус системы |
| `/run` | Запустить проверку вручную |
| `/list` | Список мониторимых чатов |
| `/reset <chat_id>` | Сбросить чекпоинт чата |
| `/remove <chat_id>` | Удалить чат из мониторинга |
| `/recheck <id...>` | Перепроверить сообщения через AI |
| `/leads` | Последние найденные лиды |
| `/help` | Справка |

### Добавление чатов

| Действие | Результат |
|----------|-----------|
| Ссылка `t.me/chat/123` | Добавить чат, checkpoint = 123-1, initial_scan = 123 |
| Пересылка из нового чата | Добавить чат, checkpoint = ID сообщения |
| Пересылка из мониторимого чата | Сохранить как пример лида |

### Уведомления

- **Каждый цикл** — статус-репорт (сообщений / AI-лидов / чатов)
- **При лидах** — @mention Антона с деталями и ссылкой на сообщение

## Управляющая группа

**Название:** «🤖 Leads Finder — Управление»
**Ссылка:** https://t.me/+YMCQ2MhiWY5iNzMy
**Бот:** @ext_team_f_bot
**Userbot:** @krab_ai_agent

## Структура проекта

```
projects/oleg-telegram-leads/
├── README.md
├── docs/
│   ├── architecture.md       ← детальная архитектура
│   ├── config.md             ← параметры конфигурации
│   ├── decisions.md          ← ADR-001..022
│   ├── keywords.md           ← словари по 9 категориям
│   └── prompts.md            ← системный промпт для z.ai (few-shot)
├── src/
│   ├── config.py             ← конфигурация + load/save helpers
│   ├── fetcher.py            ← Telethon, direct fetch + iter_messages
│   ├── keyword_scanner.py    ← rapidfuzz, ~380 слов, 9 категорий
│   ├── ai_analyzer.py        ← z.ai glm-4.5, thinking off
│   ├── notifier.py           ← bot уведомления (только AI-лиды)
│   └── pipeline.py           ← daemon + scheduler + handlers
├── tests/
│   └── test_ai_analyzer.py   ← unit + live тесты
├── data/                     ← runtime: chats.json, checkpoints.json, leads.json
├── artifacts/logs/           ← логи: leads-finder.log, ai-analyzer.log
├── .env                      ← BOT_TOKEN, GROUP_CHAT_ID, ZAI_API_KEY
├── docker-compose.yml        ← Docker deploy
├── Dockerfile                ← Python 3.12-slim
├── reset_and_rebuild.sh      ← сброс данных + пересборка
└── requirements.txt          ← telethon, rapidfuzz, httpx, python-dotenv
```

## Запуск

### Docker (рекомендуется)

```bash
cd projects/oleg-telegram-leads

# Первичный запуск
docker compose up -d --build

# Сброс данных + пересборка
bash reset_and_rebuild.sh

# Логи
docker logs -f leads-finder
docker exec leads-finder cat /app/artifacts/logs/leads-finder.log | tail -100
```

### Локально

```bash
cd projects/oleg-telegram-leads
./tg-venv/bin/python3 src/pipeline.py          # daemon (дефолт, 15 мин)
./tg-venv/bin/python3 src/pipeline.py --once   # один цикл
```

### Тесты

```bash
cd projects/oleg-telegram-leads
./tg-venv/bin/python3 -m pytest tests/ -v              # unit тесты
./tg-venv/bin/python3 -m pytest tests/ -v -k "live"    # live AI тесты
```

## Технологии

| Компонент | Технология |
|-----------|------------|
| Telegram userbot | Telethon |
| Telegram bot | Telethon (Bot API) |
| Нечёткий поиск | rapidfuzz |
| Семантический анализ | z.ai (glm-4.5) |
| HTTP клиент | httpx |
| Deploy | Docker Compose |
| Результаты | Obsidian vault (отключена) |

## Niши (10 категорий)

1. **Видеонаблюдение** — камеры, NVR/DVR, аналитика
2. **Домофония** — видеодомофоны, вызывные панели
3. **Умный дом** — экосистемы, умные устройства
4. **Автоматизация** — сценарии, реле, контроллеры
5. **Сигнализация** — охранные системы, датчики
6. **Контроль доступа** — СКУД, турникеты, шлагбаумы
7. **Сети** — PoE, Wi-Fi, коммутаторы
8. **Котлы и отопление** — газовые/электрические котлы, теплый пол
9. **Электрика** — щиты, автоматы, УЗО
10. **Климат** — кондиционеры, вентиляция, увлажнители

## Лицензия

Частный проект.
