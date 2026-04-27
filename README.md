# Telegram Leads Finder

Автоматизированная система выявления потенциальных клиентов в открытых Telegram-группах для ниши **умные дома / автоматизация / видеонаблюдение / домофония / котлы / сигнализации**.

## Зачем

Олег — эксперт по умным домам и автоматизации. Люди ежедневно спрашивают в чатах про камеры, термостаты, умные розетки, видеодомофоны, котлы и т.д. Система автоматически:

1. **Выгружает** новые сообщения из целевых чатов (Telethon userbot)
2. **Ищет** совпадения по ключевым словам (rapidfuzz, нечёткий поиск с учётом опечаток и транслитерации)
3. **Анализирует** семантику через LLM (z.ai, glm-4.5-air) — находит запросы, где человек выбирает/ищет оборудование
4. **Уведомляет** Антона в управляющую группу в Telegram с @mention и ссылкой на сообщение

## Текущий статус

**Стадия:** готов к тестированию, daemon работает

**Что сделано:**
- ✅ Подключение к Telegram через Telethon (сессия `krab-tg-session.session`)
- ✅ Архитектура всех модулей (fetcher, keyword_scanner, ai_analyzer, notifier, pipeline)
- ✅ Код всех модулей в `src/` написан и импортируется
- ✅ Словари ключевых слов по 9 категориям (~381 слово)
- ✅ Системный промпт для z.ai LLM
- ✅ Конфигурация (`src/config.py`) с реальными значениями
- ✅ Два Telegram-клиента: userbot (чтение) + bot (группа)
- ✅ Управляющая группа создана, @AntonBezkrovnyy добавлен
- ✅ Bot commands зарегистрированы через BotFather
- ✅ Forward handler: два сценария (добавить чат / пример лида)
- ✅ Команды: /status, /run, /list, /reset, /remove, /leads, /help
- ✅ @mention Антона при найденных лидах
- ✅ Статус-репорт каждый цикл
- ✅ ADR-001..015: 15 архитектурных решений

## Как работает

```
pipeline.py daemon()
    │
    ├─► Bot event handler (управляющая группа)
    │       ├─ /status, /run, /list, /reset, /remove, /leads, /help
    │       └─ пересылки — добавление чатов / примеры лидов
    │
    └─► Scheduler loop (каждые 15 мин)
            └─► run_once()
                ├─► fetcher.py          → новые сообщения из чатов
                ├─► keyword_scanner.py  → нечёткий поиск по ключевым словам
                ├─► ai_analyzer.py      → семантический анализ через z.ai
                ├─► merge + dedup       → объединение результатов
                ├─► notifier.py         → @mention Антона + уведомления
                └─► Obsidian            → запись результатов в 05-Journal
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
| `/leads` | Последние найденные лиды |
| `/help` | Справка |

### Пересылки

| Ситуация | Действие |
|----------|----------|
| Пересылка из **нового** чата | Добавить чат в мониторинг, чекпоинт = ID сообщения |
| Пересылка из **уже мониторимого** чата | Сохранить как пример лида для обучения AI |

### Уведомления

- **Каждый цикл** — статус-репорт (сколько чатов, сообщений, лидов)
- **При найденных лидах** — @mention Антона с деталями

## Управляющая группа

**Название:** «🤖 Leads Finder — Управление»
**Ссылка:** https://t.me/+YMCQ2MhiWY5iNzMy
**Участники:** Антон (@AntonBezkrovnyy), Олег

## Канонические файлы проекта

| Файл | Роль |
|------|------|
| `README.md` | Этот файл — обзор проекта и статус |
| `state/current.md` | Текущая работа, блокеры, следующие шаги |
| `state/backlog.md` | Бэклог задач |
| `docs/architecture.md` | Детальная архитектура модулей, потоки данных |
| `docs/config.md` | Все параметры конфигурации |
| `docs/keywords.md` | Словари ключевых слов по 9 категориям |
| `docs/prompts.md` | Системный промпт для z.ai |
| `docs/decisions.md` | 15 архитектурных решений (ADR-001..015) |
| `notes/` | Дневные заметки |
| `artifacts/` | Логи, экспорты |

## Структура проекта

```
projects/oleg-telegram-leads/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── config.md
│   ├── decisions.md          ← ADR-001..015
│   ├── keywords.md
│   └── prompts.md
├── state/
│   ├── current.md
│   └── backlog.md
├── src/
│   ├── config.py             ← конфигурация, load/save chats/checkpoints
│   ├── fetcher.py            ← Telethon, чтение чатов
│   ├── keyword_scanner.py    ← rapidfuzz, ~381 слово, 9 категорий
│   ├── ai_analyzer.py        ← z.ai glm-4.5-air
│   ├── notifier.py           ← bot уведомления, @mention Антона
│   └── pipeline.py           ← daemon + scheduler + commands + forward handler
├── data/                     ← runtime: chats.json, checkpoints.json, leads.json
├── notes/
├── artifacts/
├── .env                      ← BOT_TOKEN, GROUP_CHAT_ID
├── krab-tg-session.session   ← userbot сессия
├── setup_bot.py              ← регистрация bot commands через BotFather
└── tg-venv/                  ← Python venv
```

## Запуск

```bash
cd projects/oleg-telegram-leads
./tg-venv/bin/python3 -m src.pipeline          # daemon (дефолт)
./tg-venv/bin/python3 -m src.pipeline --once   # один цикл
```

## Технологии

| Компонент | Технология |
|-----------|------------|
| Telegram userbot | Telethon |
| Telegram bot | Telethon (Bot API) |
| Нечёткий поиск | rapidfuzz |
| Семантический анализ | z.ai (glm-4.5-air) |
| HTTP клиент | httpx |
| Результаты | Obsidian vault (05-Journal/oleg-telegram-leads/) |

## Лицензия

Частный проект.
