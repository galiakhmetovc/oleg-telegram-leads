# Бэклог — Telegram Leads Finder

## Очередь (по приоритету)

### Реализовано ✅
- [x] Написать `src/config.py` — загрузка и валидация конфигурации
- [x] Написать `src/fetcher.py` — Telethon userbot, чекпоинты, первый запуск
- [x] Написать `src/keyword_scanner.py` — rapidfuzz, транслитерация ru↔en
- [x] Написать `src/ai_analyzer.py` — чанкинг, z.ai API, парсинг ответов
- [x] Написать `src/notifier.py` — форматирование и отправка в управляющую группу
- [x] Написать `src/pipeline.py` — оркестратор, merge, dedup, error handling
- [x] Создать управляющую группу в Telegram
- [x] Создать бота через @BotFather (`@ext_team_f_bot`)
- [x] Добавить бота в управляющую группу
- [x] Протестировать AI (glm-4.5-air) на тестовых данных
- [x] Реализовать daemon-режим в pipeline.py (listener + scheduler, ADR-009)
- [x] Переписать на двух клиентов (userbot + bot, ADR-010)
- [x] Добавить обработку команд управляющей группы (/add, /list, /status, /run, /remove, /leads, /help)
- [x] Добавить graceful shutdown (SIGINT/SIGTERM)
- [x] Настроить Obsidian path (`05-Journal/oleg-telegram-leads/`)
- [x] Обновить всю документацию (12 ADR, architecture, config, README)

### В работе 🔄
- [ ] Протестировать daemon на реальном подключении к Telegram
- [ ] Добавить чаты для мониторинга

### Запланировано 📋
- [ ] Обработка пересылок — обратная связь от Олега (категория: лид / не лид)
- [ ] Настроить systemd service для автозапуска daemon
- [ ] Добавить мониторинг и алерты при падении daemon

## Идеи на будущее

- [ ] Web UI для просмотра найденных лидов
- [ ] Автоматический сбор статистики (сколько лидов в день, по категориям)
- [ ] Обучение LLM на false positive / false negative (через реакции в группе)
- [ ] Экспорт лидов в Google Sheets / Notion
- [ ] Queue-based архитектура для масштабирования (ADR-012)
