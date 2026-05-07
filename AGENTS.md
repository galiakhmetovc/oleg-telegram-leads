# Project Working Rules

Этот файл - обязательный регламент работы над PUR Leads v2. Если правило в чате
расходится с этим файлом, сначала обновляем этот файл или явно фиксируем исключение.

## Source Of Truth

- Важные правила и решения не остаются только в чате.
- Перед началом работы читать: `README.md`, `state/current.md`, `docs/architecture.md`,
  `docs/decisions.md`, затем этот файл.
- Текущее состояние проекта поддерживать в `state/current.md`.
- Долгоживущие архитектурные, продуктовые и процессные решения фиксировать в
  `docs/decisions.md`.

## Scope

- V1 является историческим справочником.
- Старый код можно читать для понимания предметной области, данных и прежних решений.
- Нельзя переносить v1-модули или архитектуру в v2 "как есть" без отдельного
  решения.
- Активная разработка v2 идет в ветке `v2-from-scratch` или feature-ветках от нее.
- `main` остается историческим v1, пока не принято явное решение иначе.

## Stack

- Database: PostgreSQL.
- Backend: Python, FastAPI, SQLAlchemy, Alembic, uv.
- Frontend: React, Vite, TypeScript, MUI как React-реализация Material Design.
- Local orchestration: Docker Compose.

## Docker

- Сейчас весь проект работает в dev-режиме.
- Dockerfile'ы в dev-режиме устанавливают только runtime/dependency слой.
- Исходный код backend/frontend не запекается в Docker images.
- Исходный код подключается в контейнеры через bind volumes.
- Production images с baked source, nginx, secrets management и hardening проектируются
  отдельно, когда появится production-срез.

## Architecture

- Сразу закладываем взрослую архитектуру, без временного монолита из роутов,
  ORM-моделей и бизнес-логики.
- Основной стиль: Hexagonal Architecture / Ports and Adapters.
- Соблюдать dependency rule: `api` и `infrastructure` зависят от `application`,
  `application` зависит от `domain`; `domain` не зависит от FastAPI, SQLAlchemy,
  Telegram, LLM API, файловой системы или UI.
- Бизнес-операции оформлять как use cases/application services, а не размазывать
  по FastAPI routes, React components или SQLAlchemy models.
- Persistence скрывать за repository ports. Транзакционные границы делать явными
  через Unit of Work там, где есть несколько операций записи или важная консистентность.
- API schemas, domain objects, DB models и frontend types не смешивать без причины.
- Внешние реализации подключать через Dependency Injection/composition root.
- Доменные правила и use cases должны тестироваться без поднятия FastAPI/Postgres,
  когда это практически возможно.
- Важные use cases должны иметь понятные logs/events/trace points с самого начала.
- YAGNI обязателен: не строим лишние механизмы заранее, но границы между слоями
  делаем сразу.

## Design Practices

Применять явно:

- GRASP: Information Expert, Creator, Controller, Low Coupling, High Cohesion,
  Polymorphism, Pure Fabrication, Indirection, Protected Variations.
- SOLID: Single Responsibility, Open/Closed, Liskov Substitution, Interface
  Segregation, Dependency Inversion.
- DDD tactical patterns where useful: entities, value objects, domain services,
  repositories as ports, bounded contexts/modules.
- Ports and Adapters для интеграций: Telegram, LLM/NLP providers, filesystem,
  database, background jobs, external APIs.
- Testability by design: сначала ясная граница поведения, потом реализация.

## Data

- `artifacts/` - локальные временные выгрузки, логи, traces, evidence.
- `datasets/` - небольшие версионируемые выборки для разработки, evals и регрессий,
  если решено их коммитить.
- Production lead exports можно коммитить, если они нужны для разработки/eval/
  регрессий.
- Перед коммитом production-derived данных явно проверять, что добавляется: не
  тащить случайные большие дампы, секреты, токены или нерелевантные персональные
  данные.
- Если данные чувствительные, отдельно решаем: оставить как есть, обезличить или
  не коммитить.

## NLP And LLM

- NLP/LLM решения строить как воспроизводимый pipeline.
- Для каждого classifier/judge/prompt/model фиксировать: входные данные,
  нормализацию, модель или prompt, версию, результат, метрики/eval и типичные
  ошибки.
- Любой классификатор или judge должен иметь набор примеров и способ сравнить
  качество до/после.
- Не добавлять LLM provider, NLP framework, vector database или отдельный сервис
  без обсуждения причины и альтернатив.

## Frontend

- Делаем рабочий операторский интерфейс, не landing page.
- Базовый UI-подход: Google Material Design через MUI.
- Приоритет: таблицы, фильтры, списки, формы, статусы, review-flow, понятные
  empty/loading/error states.
- Интерфейс должен быть плотным, спокойным и прикладным.
- Не делать marketing hero, декоративные карточки, визуальный шум и красоту ради
  красоты.
- UI-тексты по умолчанию на русском.
- Код, имена файлов, API-поля, классы, функции, миграции и технические
  идентификаторы - на английском.

## Dependencies

- Добавлять зависимости только под конкретную задачу.
- Backend зависимости добавлять через `uv add`; frontend зависимости через
  `npm install`.
- Lock-файлы не редактировать вручную.
- Перед добавлением новой БД, очереди, NLP-фреймворка, LLM-провайдера или
  UI-библиотеки сначала проговорить причину и альтернативы.

## Configuration

- Не зашивать в код доменные правила, списки сигналов, словари, пороги, веса,
  включенные этапы pipeline, UI-представления доменных типов и provider-specific
  настройки.
- Такие вещи должны жить в конфигурации, файлах правил, базе данных или другом
  явном externalized source of truth.
- Код должен реализовывать механизмы: загрузку конфигурации, валидацию, выполнение
  pipeline, применение правил и отображение результата.
- Редактируемые настройки продукта и NLP/domain rules храним в PostgreSQL как
  ревизии. YAML/файлы допустимы только как bootstrap defaults или импортируемые
  артефакты, но не как активное редактируемое хранилище.
- Операторская модель rule matching: только точные фразы и лемматические фразы.
  В UI/API не вводить внутренние Yargy-предикаты вроде `caseless`; legacy
  документы можно канонизировать при загрузке, но новые настройки должны
  сохраняться в понятной оператору форме.
- Если значение временно остается в коде, оно должно быть явно помечено как
  bootstrap default и вынесено перед развитием соответствующего поведения.

## Verification

- Все, что влияет на поведение системы, считается бизнес-логикой.
- Проверка должна соответствовать риску: unit, integration, API, UI smoke,
  manual verification или другой воспроизводимый способ.
- Не писать тесты ради тестов, но изменение поведения должно быть проверяемым.
- Текущий базовый набор проверок:
  - backend: `uv run ruff check .`, `uv run mypy .`, `uv run pytest`
  - frontend: `npm test`, `npm run build`
  - infra: `docker compose config`
  - runtime smoke, если трогали Docker/API: `docker compose up --build` и `/health`

## Git

- Коммитить после законченного проверенного шага.
- Не коммитить мусорные промежуточные состояния.
- Не перетирать пользовательские изменения.
- Перед коммитом смотреть `git status` и осознанно выбирать файлы.

## Definition Of Done

Задача считается сделанной, когда:

- код и документы обновлены;
- поведение проверено подходящим способом;
- `state/current.md` обновлен, если поменялось состояние проекта;
- важное решение добавлено в `docs/decisions.md`;
- пользовательские изменения не перетерты;
- финальный ответ содержит, что изменилось и чем проверено.
