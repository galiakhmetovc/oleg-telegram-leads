"""HTML page routes for the web workspace."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from pur_leads.services.web_auth import AuthError, WebAuthService
from pur_leads.web.dependencies import get_auth_service

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return _page(
        page="login",
        title="PUR Leads",
        main="""
        <main class="material-auth-shell">
          <section class="material-auth-panel">
            <div class="material-brand-lockup">
              <span class="brand-mark">PUR</span>
              <span class="muted">Leads</span>
            </div>
            <div class="material-auth-copy">
              <h1 class="md-typescale-headline-large">Вход оператора</h1>
              <p class="muted">Единый рабочий кабинет для лидов, источников и каталога.</p>
            </div>
            <form id="local-login-form" class="material-auth-form" autocomplete="on">
              <md-outlined-text-field name="username" label="Логин" autocomplete="username" required>
              </md-outlined-text-field>
              <md-outlined-text-field name="password" label="Пароль" type="password"
                autocomplete="current-password" required>
              </md-outlined-text-field>
              <md-filled-button type="submit">Войти</md-filled-button>
              <p id="login-status" class="status-line" role="status"></p>
            </form>
            <form id="change-password-form" class="material-auth-form is-hidden" autocomplete="off">
              <div class="material-auth-copy">
                <h2 class="md-typescale-title-large">Сменить пароль</h2>
                <p class="muted">Встроенный администратор должен заменить одноразовый пароль перед работой.</p>
              </div>
              <md-outlined-text-field name="new_password" label="Новый пароль" type="password"
                autocomplete="new-password" required minlength="8">
              </md-outlined-text-field>
              <md-filled-button type="submit">Сохранить пароль</md-filled-button>
              <p id="change-password-status" class="status-line" role="status"></p>
            </form>
            <div id="telegram-login-hook" class="telegram-hook"></div>
          </section>
        </main>
        """,
    )


@router.get("/", response_class=HTMLResponse)
def inbox_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="leads-inbox",
            title="Входящие лиды",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Входящие лиды</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="inbox-layout">
                <aside class="queue-pane" aria-label="Очередь лидов">
                  <form id="lead-filters" class="filter-grid">
                    <select name="status" aria-label="Статус">
                      <option value="">Все статусы</option>
                      <option value="new">Новый</option>
                      <option value="in_work">В работе</option>
                      <option value="maybe">Возможно</option>
                      <option value="snoozed">Отложен</option>
                    </select>
                    <label><input type="checkbox" name="auto_pending"> Автодобавлено</label>
                    <label><input type="checkbox" name="operator_issues"> Нужен оператор</label>
                    <label><input type="checkbox" name="retro"> Ретро</label>
                    <input name="min_confidence" type="number" min="0" max="1" step="0.05"
                      placeholder="Мин. уверенность" aria-label="Минимальная уверенность">
                  </form>
                  <div id="lead-queue" class="queue-list" aria-live="polite"></div>
                  <div class="queue-pagination">
                    <span id="lead-pagination" class="muted">0 / 0</span>
                    <button id="lead-load-more" type="button" hidden>Показать еще</button>
                  </div>
                </aside>
                <section id="lead-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Выберите лид</div>
                </section>
                <aside class="side-pane" aria-label="Оперативные сигналы">
                  <dl class="signal-list">
                    <div><dt data-field="auto_pending">Автодобавлено</dt><dd id="signal-auto">0</dd></div>
                    <div><dt data-field="retro">Ретро</dt><dd id="signal-retro">0</dd></div>
                    <div><dt data-field="maybe">Возможно</dt><dd id="signal-maybe">0</dd></div>
                  </dl>
                  <div id="action-status" class="status-line"></div>
                </aside>
              </section>
            </main>
            """,
        )
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/users", status_code=303)


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/resources", status_code=303)


@router.get("/resources", response_class=HTMLResponse)
def resources_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="resources",
            title="Ресурсы",
            main="""
            <main class="workspace resources-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Ресурсы</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <md-outlined-button id="logout-button" type="button">Выйти</md-outlined-button>
                </nav>
              </header>
              <section class="admin-section-layout">
                <section class="onboarding-resource-surface">
                    <div class="section-head">
                      <div>
                        <h2>Ресурсы системы</h2>
                        <p class="muted">
                          Исполнительные аккаунты, уведомления, AI-провайдеры и пользовательские источники данных.
                        </p>
                      </div>
                      <md-filled-button id="onboarding-add-resource" type="button">
                        <md-icon slot="icon">add</md-icon>
                        Добавить ресурс
                      </md-filled-button>
                    </div>
                    <div id="onboarding-resource-list" class="resource-list" aria-live="polite"></div>
                    <p id="onboarding-resource-status" class="status-line" role="status"></p>
                </section>
                <dialog id="onboarding-resource-dialog" class="resource-dialog">
                  <div class="resource-dialog-shell">
                    <header class="resource-dialog-head">
                      <div>
                        <h2>Добавить ресурс</h2>
                        <p class="muted">Выберите тип ресурса и заполните только его настройки.</p>
                      </div>
                      <md-icon-button id="onboarding-resource-dialog-close" type="button" title="Закрыть">
                        <md-icon>close</md-icon>
                      </md-icon-button>
                    </header>
                    <label class="material-select-field">
                      Тип ресурса
                      <select id="onboarding-resource-type">
                        <option value="telegram_bot">Telegram-бот</option>
                        <option value="telegram_notification_group">Группа уведомлений</option>
                        <option value="ai_provider_account">LLM-провайдер</option>
                        <option value="telegram_userbot">Telegram-юзербот</option>
                        <option value="telegram_desktop_archive">Архив Telegram</option>
                      </select>
                    </label>
                    <section class="onboarding-panel onboarding-panel-compact resource-form"
                      data-resource-form="telegram_bot">
                      <div class="onboarding-panel-head">
                        <md-icon aria-hidden="true">smart_toy</md-icon>
                        <div>
                          <h3 class="md-typescale-title-large">Telegram-бот</h3>
                          <p class="muted">Нужен для входа через Telegram и оперативных уведомлений.</p>
                        </div>
                      </div>
                      <form id="onboarding-bot-form" class="material-form">
                        <md-outlined-text-field name="display_name" label="Название" value="PUR Leads bot">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="token" label="Токен BotFather" type="password"
                          autocomplete="off" required placeholder="123456:ABC...">
                        </md-outlined-text-field>
                        <md-filled-button type="submit">
                          <md-icon slot="icon">send</md-icon>
                          Проверить и сохранить
                        </md-filled-button>
                      </form>
                      <p id="onboarding-bot-status" class="status-line" role="status"></p>
                    </section>
                    <section class="onboarding-panel onboarding-panel-compact resource-form is-hidden"
                      data-resource-form="telegram_notification_group">
                      <div class="onboarding-panel-head">
                        <md-icon aria-hidden="true">forum</md-icon>
                        <div>
                          <h3 class="md-typescale-title-large">Группа уведомлений</h3>
                          <p class="muted">Добавьте бота в группу, отправьте любое сообщение и выберите чат.</p>
                        </div>
                      </div>
                      <label class="material-select-field">
                        Бот для проверки групп
                        <select id="onboarding-group-bot-select" name="bot_id">
                          <option value="">Сначала сохраните бота</option>
                        </select>
                      </label>
                      <div class="material-action-row">
                        <md-filled-button id="onboarding-group-discover" type="button" disabled>
                          <md-icon slot="icon">refresh</md-icon>
                          Найти доступные группы
                        </md-filled-button>
                      </div>
                      <p id="onboarding-group-hint" class="status-line">
                        Сначала сохраните и проверьте токен бота.
                      </p>
                      <div id="onboarding-group-candidates" class="table-list"></div>
                      <p id="onboarding-group-status" class="status-line" role="status"></p>
                    </section>
                    <section class="onboarding-panel onboarding-panel-compact resource-form is-hidden"
                      data-resource-form="ai_provider_account">
                      <div class="onboarding-panel-head">
                        <md-icon aria-hidden="true">model_training</md-icon>
                        <div>
                          <h3 class="md-typescale-title-large">LLM-провайдер</h3>
                          <p class="muted">Сейчас доступен Z.AI. Модели и исполнители задач настраиваются в AI-разделах.</p>
                        </div>
                      </div>
                      <form id="onboarding-llm-form" class="material-form">
                        <md-outlined-text-field name="display_name" label="Название" value="Z.AI" required>
                        </md-outlined-text-field>
                        <md-outlined-text-field name="base_url" label="Base URL"
                          value="https://api.z.ai/api/coding/paas/v4" required>
                        </md-outlined-text-field>
                        <md-outlined-text-field name="api_key" label="Z.AI API key" type="password"
                          autocomplete="off" required>
                        </md-outlined-text-field>
                        <md-filled-button type="submit">
                          <md-icon slot="icon">sync</md-icon>
                          Проверить и сохранить
                        </md-filled-button>
                      </form>
                      <p id="onboarding-llm-status" class="status-line" role="status"></p>
                    </section>
                    <section class="onboarding-panel onboarding-panel-compact resource-form is-hidden"
                      data-resource-form="telegram_userbot">
                      <div class="onboarding-panel-head">
                        <md-icon aria-hidden="true">person_add</md-icon>
                        <div>
                          <h3 class="md-typescale-title-large">Telegram-юзербот</h3>
                          <p class="muted">Интерактивный вход создает сессию на сервере.</p>
                        </div>
                      </div>
                      <div class="material-action-row onboarding-link-row">
                        <md-outlined-button href="https://my.telegram.org/auth?to=apps" target="_blank" rel="noopener">
                          <md-icon slot="icon">vpn_key</md-icon>
                          Telegram API
                        </md-outlined-button>
                        <md-outlined-button href="https://web.telegram.org/k/" target="_blank" rel="noopener">
                          <md-icon slot="icon">open_in_new</md-icon>
                          Telegram Web
                        </md-outlined-button>
                      </div>
                      <form id="onboarding-interactive-start-form" class="material-form">
                        <md-outlined-text-field name="display_name" label="Название" required
                          placeholder="Основной юзербот">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="session_name" label="Имя сессии" required
                          placeholder="main">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="phone" label="Телефон" required
                          placeholder="+79990000000">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="api_id" label="Telegram API ID" type="number"
                          min="1" step="1" required>
                        </md-outlined-text-field>
                        <md-outlined-text-field name="api_hash" label="Telegram API hash" type="password"
                          autocomplete="off" required>
                        </md-outlined-text-field>
                        <label class="material-checkbox-line">
                          <md-checkbox name="make_default" checked></md-checkbox>
                          Использовать по умолчанию
                        </label>
                        <md-filled-button type="submit">
                          <md-icon slot="icon">send</md-icon>
                          Получить код
                        </md-filled-button>
                      </form>
                      <form id="onboarding-interactive-complete-form" class="material-form is-hidden">
                        <input name="login_id" type="hidden">
                        <md-outlined-text-field name="code" label="Код Telegram" required inputmode="numeric">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="password" label="Пароль 2FA" type="password"
                          autocomplete="off">
                        </md-outlined-text-field>
                        <md-filled-button type="submit">
                          <md-icon slot="icon">check_circle</md-icon>
                          Завершить вход
                        </md-filled-button>
                      </form>
                      <p id="onboarding-interactive-status" class="status-line" role="status"></p>
                    </section>
                    <section class="onboarding-panel onboarding-panel-compact resource-form is-hidden"
                      data-resource-form="telegram_desktop_archive">
                      <div class="onboarding-panel-head">
                        <md-icon aria-hidden="true">upload_file</md-icon>
                        <div>
                          <h3 class="md-typescale-title-large">Архив Telegram</h3>
                          <p class="muted">Загрузите zip-экспорт Telegram Desktop как источник интересов или лидов.</p>
                        </div>
                      </div>
                      <form id="onboarding-telegram-archive-form" class="material-form" enctype="multipart/form-data">
                        <md-outlined-text-field name="display_name" label="Название"
                          placeholder="Чат клиентов, канал ПУР, переписка с поставщиком">
                        </md-outlined-text-field>
                        <label class="material-select-field">
                          Назначение
                          <select name="purpose">
                            <option value="lead_monitoring">Поиск лидов</option>
                            <option value="catalog_ingestion">Знания и каталог</option>
                            <option value="both">Лиды и знания</option>
                          </select>
                        </label>
                        <label class="material-file-field">
                          Zip-архив Telegram Desktop
                          <input name="file" type="file" accept=".zip,application/zip" required>
                        </label>
                        <label class="material-checkbox-line">
                          <md-checkbox name="sync_source_messages"></md-checkbox>
                          Создать канонические сообщения сразу
                        </label>
                        <div id="onboarding-telegram-archive-progress" class="upload-progress is-hidden">
                          <md-linear-progress id="onboarding-telegram-archive-progress-bar" value="0">
                          </md-linear-progress>
                          <span id="onboarding-telegram-archive-progress-label">0%</span>
                        </div>
                        <md-filled-button type="submit">
                          <md-icon slot="icon">upload_file</md-icon>
                          Загрузить источник
                        </md-filled-button>
                      </form>
                      <p id="onboarding-telegram-archive-status" class="status-line" role="status"></p>
                    </section>
                  </div>
                </dialog>
              </section>
            </main>
            """,
        )
    )


@router.get("/artifacts", response_class=HTMLResponse)
def artifacts_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="artifacts",
            title="Артефакты",
            main="""
            <main class="workspace resources-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Артефакты</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <md-outlined-button id="logout-button" type="button">Выйти</md-outlined-button>
                </nav>
              </header>
              <section class="admin-section-layout artifacts-shell">
                <section class="onboarding-resource-surface">
                  <div class="section-head">
                    <div>
                      <h2>Артефакты пайплайна</h2>
                      <p class="muted">
                        Файлы из raw export и metadata этапов: JSON, JSONL, Parquet, SQLite,
                        Chroma и LLM trace.
                      </p>
                    </div>
                    <md-filled-button id="artifacts-refresh" type="button">
                      <md-icon slot="icon">refresh</md-icon>
                      Обновить
                    </md-filled-button>
                  </div>
                  <section id="artifact-summary" class="operations-summary" aria-live="polite">
                    <div class="empty-state">Загружаются артефакты</div>
                  </section>
                  <form id="artifact-filters" class="inline-form artifact-filters">
                    <input name="q" placeholder="Поиск по пути, этапу или источнику">
                    <select name="stage" aria-label="Этап">
                      <option value="">Все этапы</option>
                    </select>
                    <select name="kind" aria-label="Тип файла">
                      <option value="">Все типы</option>
                    </select>
                    <select name="exists" aria-label="Наличие">
                      <option value="">Все</option>
                      <option value="true">Существует</option>
                      <option value="false">Нет файла</option>
                    </select>
                  </form>
                  <div class="artifacts-layout">
                    <div id="artifact-list" class="resource-list" aria-live="polite"></div>
                    <section id="artifact-detail" class="detail-pane" aria-live="polite">
                      <div class="empty-state">Выберите артефакт</div>
                    </section>
                  </div>
                  <p id="artifact-status" class="status-line" role="status"></p>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="users",
            title="Пользователи",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Пользователи</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="admin-section-layout">
                <section>
                  <div class="section-head">
                    <div>
                      <h2>Администраторы</h2>
                      <p class="muted">Пока используется одна роль: администратор.</p>
                    </div>
                  </div>
                  <form id="telegram-admin-form" class="inline-form">
                    <input name="telegram_user_id" placeholder="Telegram ID" required>
                    <input name="telegram_username" placeholder="Имя пользователя">
                    <input name="display_name" placeholder="Отображаемое имя">
                    <button type="submit">Добавить администратора</button>
                  </form>
                  <div id="admin-users" class="table-list"></div>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="settings",
            title="Настройки",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Настройки</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="admin-section-layout">
                <section>
                  <div class="section-head">
                    <div>
                      <h2>Настройки</h2>
                      <p class="muted">Как настройка влияет на работу видно в каждой строке.</p>
                    </div>
                  </div>
                  <form id="setting-form" class="inline-form settings-form">
                    <input name="key" placeholder="Ключ" required>
                    <input name="value" placeholder="Значение JSON" required>
                    <select name="value_type">
                      <option value="bool">bool</option>
                      <option value="int">int</option>
                      <option value="float">float</option>
                      <option value="string">string</option>
                      <option value="json">json</option>
                    </select>
                    <button type="submit">Сохранить</button>
                  </form>
                  <div id="settings-list" class="table-list"></div>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/ai-registry", response_class=HTMLResponse)
def ai_registry_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="ai-registry",
            title="AI-реестр",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>AI-реестр</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="admin-section-layout">
                <section>
                  <div class="section-head">
                    <div>
                      <h2>Модели</h2>
                      <p class="muted">Контекстное окно, max output, capabilities и лимиты параллельности.</p>
                    </div>
                    <div class="row-actions">
                      <button id="ai-registry-bootstrap" type="button">Загрузить Z.AI defaults</button>
                      <button id="ai-registry-refresh" type="button">Обновить</button>
                    </div>
                  </div>
                  <div id="ai-models" class="table-list"></div>
                  <div class="section-head ai-profile-head">
                    <div>
                      <h2>Профили моделей</h2>
                      <p class="muted">Профиль хранит конкретные параметры запуска модели: лимиты токенов, temperature, thinking и structured output.</p>
                    </div>
                  </div>
                  <form id="ai-profile-form" class="inline-form ai-profile-form">
                    <select name="model_id" required></select>
                    <input name="profile_key" placeholder="profile key" required>
                    <input name="display_name" placeholder="Название профиля" required>
                    <input name="max_input_tokens" type="number" min="1" step="1" placeholder="Max input">
                    <input name="max_output_tokens" type="number" min="1" step="1" placeholder="Max output">
                    <input name="temperature" type="number" min="0" max="2" step="0.1" placeholder="Temperature">
                    <select name="thinking_mode">
                      <option value="off">Thinking off</option>
                      <option value="on">Thinking on</option>
                    </select>
                    <label class="checkbox-line">
                      <input name="structured_output_required" type="checkbox" checked>
                      Structured output
                    </label>
                    <button type="submit">Сохранить профиль</button>
                  </form>
                  <div id="ai-model-profiles" class="table-list"></div>
                  <div id="ai-registry-status" class="status-line"></div>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/task-executors", response_class=HTMLResponse)
def task_executors_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="task-executors",
            title="Исполнители задач",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Исполнители задач</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="admin-section-layout">
                <section>
                  <div class="section-head">
                    <div>
                      <h2>Связки исполнения</h2>
                      <p class="muted">Связка: тип задачи + ресурс + профиль модели. Для одной задачи можно включить несколько исполнителей.</p>
                    </div>
                    <button id="ai-registry-refresh" type="button">Обновить</button>
                  </div>
                  <form id="ai-route-form" class="inline-form executor-form">
                    <select name="agent_key" required></select>
                    <select name="profile_id" required></select>
                    <select name="account_id" required></select>
                    <select name="route_role" required>
                      <option value="primary">Основной</option>
                      <option value="fallback">Резерв</option>
                      <option value="shadow">Теневой</option>
                      <option value="ensemble">Ансамбль</option>
                      <option value="split">Разделение</option>
                      <option value="manual_test">Ручной тест</option>
                    </select>
                    <input name="priority" type="number" min="0" step="1" value="50" aria-label="Приоритет">
                    <label class="checkbox-line">
                      <input name="enabled" type="checkbox" checked>
                      Включен
                    </label>
                    <button type="submit">Сохранить исполнителя</button>
                  </form>
                  <div id="ai-routes" class="table-list"></div>
                  <div id="ai-registry-status" class="status-line"></div>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/task-types", response_class=HTMLResponse)
def task_types_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="task-types",
            title="Задачи",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Задачи</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="admin-section-layout">
                <section>
                  <div class="section-head">
                    <div>
                      <h2>Реестр типов задач</h2>
                      <p class="muted">poll_monitored_source и другие типы описывают требования к ресурсам и правила параллельности.</p>
                    </div>
                    <button id="task-types-refresh" type="button">Обновить</button>
                  </div>
                  <div id="task-type-list" class="table-list"></div>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/crm", response_class=HTMLResponse)
def crm_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="crm",
            title="CRM",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>CRM</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="crm-layout">
                <aside class="queue-pane" aria-label="Клиенты">
                  <div class="section-head">
                    <h2>Клиенты</h2>
                    <button id="crm-refresh" type="button">Обновить</button>
                  </div>
                  <div id="crm-client-list" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="crm-client-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Выберите клиента</div>
                </section>
                <aside class="side-pane" aria-label="Новый клиент">
                  <form id="crm-client-form" class="stack">
                    <label>
                      Имя
                      <input name="display_name" required>
                    </label>
                    <label>
                      Тип
                      <select name="client_type">
                        <option value="unknown">Неизвестно</option>
                        <option value="person">Человек</option>
                        <option value="family">Семья</option>
                        <option value="company">Компания</option>
                        <option value="cottage_settlement">Коттеджный поселок</option>
                        <option value="hoa_tsn">ТСЖ / ТСН</option>
                        <option value="residential_complex">Жилой комплекс</option>
                      </select>
                    </label>
                    <label>
                      Telegram ID
                      <input name="telegram_user_id">
                    </label>
                    <label>
                      Telegram username
                      <input name="telegram_username">
                    </label>
                    <label>
                      Интерес
                      <textarea name="interest_text" rows="4"></textarea>
                    </label>
                    <label>
                      Заметки
                      <textarea name="notes" rows="4"></textarea>
                    </label>
                    <button type="submit">Создать</button>
                    <p id="crm-status" class="status-line" role="status"></p>
                  </form>
                </aside>
              </section>
            </main>
            """,
        )
    )


@router.get("/sources", response_class=HTMLResponse)
def sources_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="sources",
            title="Источники",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Источники</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="sources-layout">
                <aside class="queue-pane" aria-label="Telegram-источники">
                  <div class="section-head">
                    <h2>Источники</h2>
                    <button id="source-refresh" type="button">Обновить</button>
                  </div>
                  <div id="source-list" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="source-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Выберите источник</div>
                </section>
                <aside class="side-pane" aria-label="Новый источник">
                  <form id="source-form" class="stack">
                    <label>
                      Telegram-чат или канал
                      <input name="input_ref" placeholder="@chat или https://t.me/..." required>
                    </label>
                    <label>
                      Назначение
                      <select name="purpose">
                        <option value="lead_monitoring">Поиск лидов</option>
                        <option value="catalog_ingestion">Наполнение каталога</option>
                        <option value="both">Оба сценария</option>
                      </select>
                    </label>
                    <label>
                      Исторический старт
                      <select name="start_mode">
                        <option value="from_now">С текущего момента</option>
                        <option value="recent_days">За последние N дней</option>
                        <option value="from_beginning">С самого начала</option>
                      </select>
                    </label>
                    <label>
                      Дней назад
                      <input name="start_recent_days" type="number" min="1" placeholder="только для режима За последние N дней">
                    </label>
                    <label class="checkbox-line">
                      <input name="check_access" type="checkbox" checked>
                      Проверить доступ сейчас
                    </label>
                    <button type="submit">Создать источник</button>
                    <p id="source-status" class="status-line" role="status"></p>
                  </form>
                </aside>
              </section>
            </main>
            """,
        )
    )


@router.get("/catalog", response_class=HTMLResponse)
def catalog_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="catalog",
            title="Каталог",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Каталог</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="catalog-layout catalog-editor-layout">
                <aside class="queue-pane" aria-label="Ручной каталог">
                  <div class="section-head">
                    <div>
                      <h2>Ручной каталог</h2>
                      <p class="muted">Канонические сущности, термины, признаки и условия.</p>
                    </div>
                    <div class="catalog-toolbar">
                      <button id="catalog-item-dialog-open" type="button">
                        <md-icon>add</md-icon>
                        Добавить
                      </button>
                      <button id="catalog-snapshot-rebuild" class="secondary-button" type="button">
                        <md-icon>refresh</md-icon>
                        Снапшот
                      </button>
                    </div>
                  </div>
                  <label class="catalog-search">
                    Поиск
                    <input id="catalog-item-search" type="search" placeholder="Название, модель, категория">
                    <small class="field-help">Фильтрует только видимый список сущностей. На источник истины и правила распознавания не влияет.</small>
                  </label>
                  <p id="catalog-item-status" class="status-line" role="status"></p>
                  <div id="catalog-item-list" class="queue-list" aria-live="polite"></div>
                  <details class="catalog-raw-source">
                    <summary>Сырой источник</summary>
                    <form id="manual-input-form" class="manual-input-form">
                      <p class="muted">Сохраняет необработанный пример. AI-разбор запускается только если включить автоизвлечение.</p>
                      <label>Тип источника
                        <select name="input_type" aria-label="Тип ручного ввода">
                          <option value="catalog_note">Заметка каталога</option>
                          <option value="lead_example">Пример лида</option>
                          <option value="non_lead_example">Пример не-лида</option>
                          <option value="maybe_example">Пример maybe</option>
                          <option value="telegram_link">Ссылка Telegram</option>
                          <option value="manual_text">Ручной текст</option>
                        </select>
                        <small class="field-help">Выбирает, как система будет трактовать материал: как факт каталога, пример решения по лиду или ссылку на сообщение.</small>
                      </label>
                      <label>Текст
                        <textarea name="text" rows="4" placeholder="Текст"></textarea>
                        <small class="field-help">Сырой текст, ссылка или пример сохраняются как источник для обучения и аудита. Пишите как есть, без попытки сразу привести к JSON.</small>
                      </label>
                      <label>URL
                        <input name="url" type="url" placeholder="https://t.me/...">
                        <small class="field-help">Ссылка на Telegram-сообщение, Telegraph или другой источник. Если это Telegram-ссылка, система выделит чат и номер сообщения.</small>
                      </label>
                      <label>Комментарий
                        <input name="evidence_note" placeholder="Комментарий к источнику">
                        <small class="field-help">Коротко объясните, почему источник важен: например, кто дал пример, что в нем нужно учесть или почему это не лид.</small>
                      </label>
                      <label class="checkbox-line">
                        <input name="auto_extract" type="checkbox">
                        Автоизвлечение
                      </label>
                      <small class="field-help">Автоизвлечение запускает AI-разбор только после сохранения сырого источника. Для спорных материалов лучше оставить выключенным и разобрать вручную.</small>
                      <button type="submit">Сохранить источник</button>
                      <p id="manual-input-status" class="status-line" role="status"></p>
                    </form>
                  </details>
                </aside>
                <section class="detail-pane catalog-detail-stack">
                  <section id="catalog-item-detail" class="detail-section" aria-live="polite">
                    <div class="empty-state">Выберите позицию каталога или добавьте новую</div>
                  </section>
                  <section class="detail-section catalog-raw-ingest-section">
                    <div class="section-head">
                      <div>
                        <h2>Сырой ингест</h2>
                        <p class="muted">Что уже получено из источников каталога до AI-разбора.</p>
                      </div>
                      <button id="catalog-raw-refresh" type="button">Обновить</button>
                    </div>
                    <div id="catalog-raw-summary" aria-live="polite">
                      <div class="empty-state">Загружается сырой ингест</div>
                    </div>
                    <div class="catalog-raw-ingest-grid">
                      <section>
                        <h3>Сообщения</h3>
                        <div id="catalog-raw-message-list" class="table-list" aria-live="polite"></div>
                      </section>
                      <section>
                        <h3>Деталь</h3>
                        <div id="catalog-raw-message-detail" aria-live="polite">
                          <div class="empty-state">Выберите сообщение</div>
                        </div>
                      </section>
                    </div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h2>AI-кандидаты</h2>
                        <p class="muted">Предложения из LLM не меняют каталог без подтверждения.</p>
                      </div>
                      <button id="catalog-refresh" type="button">Обновить</button>
                    </div>
                    <form id="catalog-filters" class="filter-grid">
                      <select name="status" aria-label="Статус">
                        <option value="auto_pending">Автодобавлено</option>
                        <option value="needs_review">На проверке</option>
                        <option value="approved">Подтверждено</option>
                        <option value="rejected">Отклонено</option>
                        <option value="">Все статусы</option>
                      </select>
                      <select name="candidate_type" aria-label="Тип">
                        <option value="">Все типы</option>
                        <option value="item">Сущности</option>
                        <option value="offer">Условия</option>
                        <option value="lead_phrase">Признаки запроса</option>
                        <option value="negative_phrase">Исключающие признаки</option>
                      </select>
                    </form>
                    <div id="catalog-candidate-list" class="queue-list" aria-live="polite"></div>
                    <section id="catalog-candidate-detail" aria-live="polite">
                      <div class="empty-state">Выберите AI-кандидата</div>
                      <form id="catalog-edit-form" class="catalog-edit-form" hidden>
                        <label>Название<input id="catalog-name-input" name="canonical_name"></label>
                        <label>JSON-данные<textarea id="catalog-value-json" name="normalized_value"></textarea></label>
                      </form>
                    </section>
                  </section>
                </section>
              </section>
              <dialog id="catalog-item-dialog" class="resource-dialog catalog-item-dialog">
                <div class="resource-dialog-shell">
                  <header class="resource-dialog-head">
                    <div>
                      <h2>Добавить сущность каталога</h2>
                      <p class="muted">Создает каноническое знание. AI-кандидаты должны приходить сюда только после проверки.</p>
                    </div>
                    <button id="catalog-item-dialog-close" class="secondary-button icon-button" type="button" title="Закрыть">
                      <md-icon>close</md-icon>
                    </button>
                  </header>
                  <details class="catalog-example" open>
                    <summary>Пример: Камеры Dahua</summary>
                    <p>Порядок работы: источник → кандидат → подтверждение → снапшот → совпадение в чате.</p>
                    <dl>
                      <div><dt>Название</dt><dd>Камеры Dahua — оператор видит это имя в карточке совпадения.</dd></div>
                      <div><dt>Тип</dt><dd>Предмет — система понимает, что это объект знания, а не действие или исключение.</dd></div>
                      <div><dt>Категория</dt><dd>video_surveillance — группирует камеры, монтаж и связанные запросы.</dd></div>
                      <div><dt>Ключевые слова</dt><dd>dahua, hero a1, wi-fi камера — дают fuzzy match по словам и моделям.</dd></div>
                      <div><dt>Признаки запроса</dt><dd>нужна камера на дачу, смотреть с телефона — повышают уверенность, что нужна помощь.</dd></div>
                      <div><dt>Исключающие признаки</dt><dd>продам камеру, просто обзор — снижают уверенность или убирают ложный лид.</dd></div>
                      <div><dt>Условия/действия</dt><dd>Подбор камеры; параметры: бюджет, наличие, монтаж — помогают оператору понять следующий шаг.</dd></div>
                    </dl>
                    <p>Ключевые слова дают fuzzy match, признаки запроса повышают уверенность, исключающие признаки снижают ее.</p>
                  </details>
                  <form id="catalog-item-form" class="catalog-edit-form catalog-create-form">
                    <div class="catalog-form-grid">
                      <label>Название
                        <input name="name" required placeholder="Например: Камеры Dahua, гарантия, монтаж, проблема доступа">
                        <small class="field-help">Каноническое имя: коротко, конкретно и без лишних слов. Оно будет видно оператору и попадет в снапшот распознавания.</small>
                      </label>
                      <label>Тип
                        <select name="item_type">
                          <option value="product">Предмет</option>
                          <option value="service">Действие/сервис</option>
                          <option value="bundle">Набор</option>
                          <option value="solution">Сценарий/решение</option>
                          <option value="brand">Бренд</option>
                          <option value="model">Модель</option>
                        </select>
                        <small class="field-help">Тип определяет роль сущности в базе знаний и влияет на будущие промпты. Если сомневаетесь, выбирайте сценарий/решение.</small>
                      </label>
                      <label>Категория
                        <input name="category_slug" placeholder="video_surveillance">
                        <small class="field-help">Стабильный slug группы знаний: латиница, цифры и подчеркивания. Помогает объединять похожие сущности и строить отчеты.</small>
                      </label>
                      <label>Условие/действие
                        <input name="offer_title" placeholder="Подбор, консультация, ограничение">
                        <small class="field-help">Необязательное уточнение: что можно сделать, предложить, проверить или ограничить для этой сущности.</small>
                      </label>
                      <label>Параметры
                        <input name="offer_price_text" placeholder="срок, стоимость, доступность, исключение">
                        <small class="field-help">Параметры: срок, цена, доступность, ограничение или другое уточнение. Поле не обязано быть ценой.</small>
                      </label>
                    </div>
                    <label>Описание
                      <textarea name="description" rows="3" placeholder="Что это за сущность, когда она релевантна и как ее распознавать"></textarea>
                      <small class="field-help">Опишите смысл для оператора и AI: какие запросы сюда относятся, какие не относятся, какие нюансы важны.</small>
                    </label>
                    <div class="catalog-form-grid catalog-form-grid-three">
                      <label>Ключевые слова
                        <textarea name="terms" rows="5" placeholder="Один термин на строку"></textarea>
                        <small class="field-help">Слова, модели, бренды, синонимы и разговорные названия. Они помогают fuzzy match найти связь даже без AI.</small>
                      </label>
                      <label>Признаки запроса
                        <textarea name="lead_phrases" rows="5" placeholder="Один признак на строку"></textarea>
                        <small class="field-help">Фразы, по которым видно намерение, проблему или потребность. Пишите естественным языком, как люди говорят в чатах.</small>
                      </label>
                      <label>Исключающие признаки
                        <textarea name="negative_phrases" rows="5" placeholder="Один признак на строку"></textarea>
                        <small class="field-help">Фразы, которые должны снижать уверенность: обсуждение без намерения, чужая реклама, несовместимый сценарий или явно не наш случай.</small>
                      </label>
                    </div>
                    <label>Источник/заметка
                      <textarea name="evidence_quote" rows="3" placeholder="Почему это есть в каталоге"></textarea>
                      <small class="field-help">Доказательство для аудита: ссылка, цитата, пояснение Олега или причина ручного добавления.</small>
                    </label>
                    <div class="source-action-bar">
                      <button type="submit">Добавить в каталог</button>
                    </div>
                  </form>
                </div>
              </dialog>
            </main>
            """,
        )
    )


@router.get("/today", response_class=HTMLResponse)
def today_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="today",
            title="Сегодня",
            main="""
            <main class="workspace today-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Сегодня</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="today-shell">
                <section id="today-summary" class="today-summary" aria-live="polite">
                  <div class="empty-state">Загружается работа на день</div>
                </section>
                <section class="today-layout">
                  <section class="detail-pane today-main" aria-label="Очереди работы на день">
                    <section class="today-section">
                      <div class="section-head">
                        <h2>Лиды</h2>
                        <button id="today-refresh" type="button">Обновить</button>
                      </div>
                      <div id="today-leads" class="table-list" aria-live="polite"></div>
                    </section>
                    <section class="today-section">
                      <div class="section-head">
                        <h2>Задачи</h2>
                      </div>
                      <form id="today-task-form" class="inline-form">
                        <input name="title" placeholder="Название задачи" required>
                        <input name="description" placeholder="Описание">
                        <select name="priority" aria-label="Приоритет">
                          <option value="normal">Обычный</option>
                          <option value="high">Высокий</option>
                          <option value="low">Низкий</option>
                        </select>
                        <input name="due_at" type="datetime-local" aria-label="Срок">
                        <button type="submit">Создать</button>
                      </form>
                      <p id="today-status" class="status-line" role="status"></p>
                      <div id="today-tasks" class="table-list" aria-live="polite"></div>
                    </section>
                    <section class="today-section">
                      <div class="section-head">
                        <h2>Поводы связаться</h2>
                      </div>
                      <div id="today-contact-reasons" class="table-list" aria-live="polite"></div>
                    </section>
                  </section>
                  <aside class="side-pane today-side" aria-label="Контекст">
                    <section class="today-section">
                      <h2>Поддержка</h2>
                      <div id="today-support-cases" class="table-list" aria-live="polite"></div>
                    </section>
                    <section class="today-section">
                      <h2>Проверка каталога</h2>
                      <div id="today-catalog-candidates" class="table-list" aria-live="polite"></div>
                    </section>
                    <section class="today-section">
                      <h2>Операционные проблемы</h2>
                      <div id="today-operational-issues" class="table-list" aria-live="polite"></div>
                    </section>
                  </aside>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/operations", response_class=HTMLResponse)
def operations_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="operations",
            title="Операции",
            main="""
            <main class="workspace operations-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Операции</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="operations-shell">
                <section id="operations-summary" class="operations-summary" aria-live="polite">
                  <div class="empty-state">Загружается состояние системы</div>
                </section>
                <section class="operations-layout">
                  <aside class="queue-pane" aria-label="Задачи планировщика">
                    <div class="section-head">
                      <h2>Задачи</h2>
                      <button id="operations-refresh" type="button">Обновить</button>
                    </div>
                    <form id="operations-job-filters" class="filter-grid">
                      <select name="status" aria-label="Статус задачи">
                        <option value="">Все задачи</option>
                        <option value="queued">В очереди</option>
                        <option value="running">Выполняется</option>
                        <option value="failed">Ошибка</option>
                        <option value="succeeded">Успешно</option>
                      </select>
                      <input name="job_type" placeholder="Тип задачи" aria-label="Тип задачи">
                      <input name="monitored_source_id" placeholder="ID источника" aria-label="ID источника">
                    </form>
                    <div id="operations-jobs" class="queue-list" aria-live="polite"></div>
                  </aside>
                  <section id="operations-detail" class="detail-pane" aria-live="polite">
                    <div class="empty-state">Выберите задачу</div>
                  </section>
                  <aside class="side-pane operations-signals" aria-label="Операционные сигналы">
                    <section>
                      <h2>События</h2>
                      <div id="operations-events" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <h2>Уведомления</h2>
                      <div id="operations-notifications" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <h2>Запуски извлечения</h2>
                      <div id="operations-extraction-runs" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <h2>Проверки доступа</h2>
                      <div id="operations-access-checks" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <div class="section-head">
                        <h2>Бэкапы</h2>
                        <button id="operations-backup-create" type="button">Сделать бэкап</button>
                      </div>
                      <div id="operations-backups" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <h2>Проверки восстановления</h2>
                      <div id="operations-restores" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <h2>Аудит</h2>
                      <div id="operations-audit" class="table-list" aria-live="polite"></div>
                    </section>
                  </aside>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/quality", response_class=HTMLResponse)
def quality_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="quality",
            title="Качество",
            main="""
            <main class="workspace operations-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Качество</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/users">Пользователи</a>
                  <a href="/settings">Настройки</a>
                  <a href="/ai-registry">AI-реестр</a>
                  <a href="/task-executors">Исполнители задач</a>
                  <a href="/task-types">Задачи</a>
                  <a href="/quality">Качество</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="operations-shell">
                <section id="quality-summary" class="operations-summary" aria-live="polite">
                  <div class="empty-state">Загружается состояние качества</div>
                </section>
                <section class="operations-layout">
                  <aside class="queue-pane" aria-label="Наборы оценки">
                    <div class="section-head">
                      <h2>Наборы</h2>
                      <button id="quality-refresh" type="button">Обновить</button>
                    </div>
                    <div id="quality-datasets" class="queue-list" aria-live="polite"></div>
                  </aside>
                  <section class="detail-pane" aria-live="polite">
                    <div class="section-head">
                      <h2>Запуски оценки</h2>
                    </div>
                    <div id="quality-runs" class="table-list" aria-live="polite"></div>
                    <div class="section-head">
                      <h2>Проваленные кейсы</h2>
                    </div>
                    <div id="quality-failed-results" class="table-list" aria-live="polite"></div>
                  </section>
                  <aside class="side-pane operations-signals" aria-label="Сигналы качества">
                    <section>
                      <h2>Последние решения</h2>
                      <div id="quality-decisions" class="table-list" aria-live="polite"></div>
                    </section>
                    <section>
                      <h2>Кейсы</h2>
                      <div id="quality-cases" class="table-list" aria-live="polite"></div>
                    </section>
                  </aside>
                </section>
              </section>
            </main>
            """,
        )
    )


def _has_page_session(request: Request, auth_service: WebAuthService) -> bool:
    cookie_name: str = request.app.state.web_session_cookie_name
    session_token = request.cookies.get(cookie_name)
    if not session_token:
        return False
    try:
        validated = auth_service.validate_session(session_token)
    except AuthError:
        return False
    return validated.user.role == "admin"


def _page(*, page: str, title: str, main: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="icon" href="data:,">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700&amp;display=swap">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined&amp;icon_names=add,archive,article,check_circle,close,database,description,folder,forum,model_training,open_in_new,person,person_add,radio_button_unchecked,refresh,send,settings,smart_toy,storage,table_chart,upload_file,vpn_key&amp;display=block">
  <link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="{page}">
  {main}
  <script type="module" src="/static/vendor/material-web.js"></script>
  <script src="/static/app.js" defer></script>
</body>
</html>"""
