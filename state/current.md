# Текущее состояние

**Дата:** 2026-06-28
**Стадия:** 🟢 работает в Docker, restart=always

## ✅ Сделано

- Все 6 модулей написаны и работают
- Два Telegram-клиента (userbot + bot) с отдельными сессиями
- Daemon-режим: listener в управляющей группе + scheduler (15 мин)
- Команды: /status, /run, /list, /reset, /remove, /recheck, /leads, /help
- Добавление чатов по ссылке `t.me/chat/123` и пересылке
- Keyword scanner: ~380 слов, 9 категорий, rapidfuzz
- AI analyzer: glm-4.5, few-shot промпт, thinking mode off
- Только AI-подтверждённые лиды в уведомлениях
- Direct fetch для целевых сообщений (обход удалённых сообщений)
- Caption extraction для media-сообщений
- RotatingFileHandler логирование (leads-finder.log, ai-analyzer.log)
- Docker deploy + reset_and_rebuild.sh
- Тесты: unit + live (AI API)
- Документация: 22 ADR, architecture, config, keywords, prompts

## ⚠️ Известные проблемы

1. **AI иногда возвращает `id=None`** — модель не всегда проставляет ID из списка. Нужно усилить промпт.
2. **Obsidian сохранение отключено** — sync/async conflict в `_save_to_obsidian()`. Модуль готов к включению после фикса.
3. **Keyword scanner даёт ложные срабатывания** — «фотографы», «наличники дверей» и т.д. Keyword-only не отправляются, но логируются.

## 🔧 Текущая конфигурация

| Параметр | Значение |
|----------|----------|
| Модель | glm-4.5 |
| API | z.ai (`https://api.z.ai/api/coding/paas/v4`) |
| Thinking mode | отключён |
| Batch size | 15 сообщений |
| Batch char limit | 5 000 символов |
| Poll interval | 15 мин (900 сек) |
| Fetch limit | 500 сообщений |
| Логирование | DEBUG, RotatingFileHandler |

## 📋 Бэклог

- [ ] Усилить промпт: обязательное поле `id` в JSON-ответе
- [ ] Включить Obsidian сохранение (фикс sync/async)
- [ ] Очистить keyword scanner от ложных срабатываний
- [ ] Расширить список мониторимых чатов
- [ ] Метрики и аналитика по лидам
- [ ] Тюнинг AI-промптов по накопленным примерам
