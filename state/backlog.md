# Бэклог — Telegram Leads Finder

## Реализовано ✅

- [x] Написать `src/config.py` — загрузка и валидация конфигурации
- [x] Написать `src/fetcher.py` — Telethon userbot, чекпоинты, первый запуск
- [x] Написать `src/keyword_scanner.py` — rapidfuzz, транслитерация ru↔en, 324 ключевых слова
- [x] Написать `src/ai_analyzer.py` — чанкинг, z.ai API (glm-4.5-air), fallback-промпт
- [x] Написать `src/notifier.py` — отправка через бота, батчинг, @mention Антона
- [x] Написать `src/pipeline.py` — оркестратор, daemon, два клиента, event handlers
- [x] Создать управляющую группу «🤖 Leads Finder — Управление»
- [x] Создать бота `@ext_team_f_bot` через @BotFather
- [x] Добавить бота в группу, отключить Group Privacy Mode
- [x] Зарегистрировать bot commands (/help, /status, /list, /reset, /remove, /leads, /run)
- [x] Forward handler: сценарий 1 (новый чат), сценарий 2 (пример лида)
- [x] Link handler: парсинг ссылок `t.me/chat/123` → добавление чата
- [x] Captcha-детекция при добавлении чата + уведомление оператору
- [x] Статус-репорт каждый цикл (даже если ничего не найдено)
- [x] Graceful shutdown (SIGINT/SIGTERM)
- [x] Настроить Obsidian path (`05-Journal/oleg-telegram-leads/`)
- [x] Git: локальный репозиторий, .gitignore (без секретов)
- [x] Документация: 15 ADR, architecture, config, keywords, prompts
- [x] Отправить документацию на ревью судье → ✅ APPROVED
- [x] Протестировать daemon: запуск, подключение, команды

## В работе 🔄

- [ ] Добавить чаты для мониторинга и протестировать полный цикл
- [ ] Настроить scheduler teamD для автозапуска каждые 15 минут

## Запланировано 📋

- [ ] Обработка пересылок — обратная связь от Олега (категория: лид / не лид)
- [ ] Настроить systemd service для автозапуска daemon
- [ ] Удалённый git-репозиторий (нужен GitHub токен)

## Идеи на будущее 💡

- [ ] Web UI для просмотра найденных лидов
- [ ] Автоматическая статистика (лиды/день, по категориям)
- [ ] Обучение LLM на false positive / false negative
- [ ] Экспорт лидов в Google Sheets / Notion
- [ ] Queue-based архитектура для масштабирования (ADR-012)
