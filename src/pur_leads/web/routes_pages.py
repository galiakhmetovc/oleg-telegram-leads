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
        <main class="login-shell">
          <section class="login-panel">
            <div class="brand-line">
              <span class="brand-mark">PUR</span>
              <span class="muted">Leads</span>
            </div>
            <h1>Вход оператора</h1>
            <form id="local-login-form" class="stack" autocomplete="on">
              <label>
                Логин
                <input name="username" type="text" autocomplete="username" required>
              </label>
              <label>
                Пароль
                <input name="password" type="password" autocomplete="current-password" required>
              </label>
              <button type="submit">Войти</button>
              <p id="login-status" class="status-line" role="status"></p>
            </form>
            <form id="change-password-form" class="stack is-hidden" autocomplete="off">
              <div class="stack">
                <h2>Сменить пароль</h2>
                <p class="muted">Встроенный администратор должен заменить одноразовый пароль перед работой.</p>
              </div>
              <label>
                Новый пароль
                <input name="new_password" type="password" autocomplete="new-password" required minlength="8">
              </label>
              <button type="submit">Сохранить пароль</button>
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
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
    return HTMLResponse(
        _page(
            page="admin",
            title="Администрирование",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Администрирование</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="admin-layout">
                <section>
                  <div class="section-head">
                    <h2>Администраторы</h2>
                  </div>
                  <form id="telegram-admin-form" class="inline-form">
                    <input name="telegram_user_id" placeholder="Telegram ID" required>
                    <input name="telegram_username" placeholder="Имя пользователя">
                    <input name="display_name" placeholder="Отображаемое имя">
                    <button type="submit">Добавить</button>
                  </form>
                  <div id="admin-users" class="table-list"></div>
                </section>
                <section>
                  <div class="section-head">
                    <h2>Юзерботы</h2>
                  </div>
                  <form id="userbot-form" class="inline-form">
                    <input name="display_name" placeholder="Название юзербота" required>
                    <input name="session_name" placeholder="Имя сессии" required>
                    <input name="session_path" placeholder="Путь к сессии" required>
                    <label class="checkbox-line">
                      <input name="make_default" type="checkbox" checked>
                      По умолчанию
                    </label>
                    <button type="submit">Добавить юзербота</button>
                  </form>
                  <div id="userbot-accounts" class="table-list"></div>
                </section>
                <section>
                  <div class="section-head">
                    <h2>Настройки</h2>
                  </div>
                  <form id="setting-form" class="inline-form">
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
                <section class="ai-admin-section">
                  <div class="section-head">
                    <h2>AI-реестр</h2>
                    <div class="row-actions">
                      <button id="ai-registry-bootstrap" type="button">Загрузить значения по умолчанию</button>
                      <button id="ai-registry-refresh" type="button">Обновить</button>
                    </div>
                  </div>
                  <div class="ai-admin-grid">
                    <section>
                      <div class="section-head">
                        <h3>Модели</h3>
                      </div>
                      <div id="ai-models" class="table-list"></div>
                    </section>
                    <section>
                      <div class="section-head">
                        <h3>Маршруты</h3>
                      </div>
                      <form id="ai-route-form" class="inline-form">
                        <select name="agent_key" required></select>
                        <select name="model_id" required></select>
                        <select name="route_role" required>
                          <option value="primary">Основной</option>
                          <option value="fallback">Резерв</option>
                          <option value="shadow">Теневой</option>
                          <option value="ensemble">Ансамбль</option>
                          <option value="split">Разделение</option>
                          <option value="manual_test">Ручной тест</option>
                        </select>
                        <input name="priority" type="number" min="0" step="1" value="50" aria-label="Приоритет">
                        <input name="max_output_tokens" type="number" min="1" step="1"
                          placeholder="Макс. токены" aria-label="Максимум выходных токенов">
                        <label class="checkbox-line">
                          <input name="enabled" type="checkbox" checked>
                          Включен
                        </label>
                        <button type="submit">Сохранить маршрут</button>
                      </form>
                      <div id="ai-routes" class="table-list"></div>
                    </section>
                  </div>
                  <div id="ai-registry-status" class="status-line"></div>
                </section>
              </section>
            </main>
            """,
        )
    )


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="onboarding",
            title="Онбординг",
            main="""
            <main class="workspace onboarding-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Онбординг</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/today">Сегодня</a>
                  <a href="/sources">Источники</a>
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="onboarding-layout">
                <aside class="onboarding-rail" aria-label="Шаги подключения">
                  <div class="section-head">
                    <h2>Статус</h2>
                    <button id="onboarding-refresh" class="icon-button" type="button" title="Обновить">
                      <span class="material-symbols-outlined" aria-hidden="true">refresh</span>
                    </button>
                  </div>
                  <div id="onboarding-status" class="onboarding-steps" aria-live="polite"></div>
                  <div class="onboarding-note">
                    После смены временного пароля настройте бота, группу уведомлений и юзербота.
                    Источники для поиска лидов можно добавить позже в разделе
                    <a href="/sources">«Источники»</a>.
                  </div>
                </aside>
                <section class="onboarding-main">
                  <section class="onboarding-panel">
                    <div class="onboarding-panel-head">
                      <span class="material-symbols-outlined" aria-hidden="true">smart_toy</span>
                      <div>
                        <h2>Обычный Telegram-бот</h2>
                        <p class="muted">Нужен для входа через Telegram и оперативных уведомлений.</p>
                      </div>
                    </div>
                    <form id="onboarding-bot-form" class="material-form">
                      <label>
                        Токен BotFather
                        <input name="token" type="password" autocomplete="off" required
                          placeholder="123456:ABC...">
                      </label>
                      <label>
                        Название
                        <input name="display_name" value="PUR Leads bot">
                      </label>
                      <button type="submit">
                        <span class="material-symbols-outlined" aria-hidden="true">send</span>
                        Проверить и сохранить
                      </button>
                    </form>
                    <p id="onboarding-bot-status" class="status-line" role="status"></p>
                  </section>
                  <section class="onboarding-panel">
                    <div class="onboarding-panel-head">
                      <span class="material-symbols-outlined" aria-hidden="true">forum</span>
                      <div>
                        <h2>Группа уведомлений</h2>
                        <p class="muted">Добавьте бота в группу, отправьте любое сообщение и выберите чат здесь.</p>
                      </div>
                    </div>
                    <div class="inline-form">
                      <button id="onboarding-group-discover" type="button">
                        <span class="material-symbols-outlined" aria-hidden="true">refresh</span>
                        Найти доступные группы
                      </button>
                    </div>
                    <div id="onboarding-group-candidates" class="table-list"></div>
                    <p id="onboarding-group-status" class="status-line" role="status"></p>
                  </section>
                  <section class="onboarding-panel">
                    <div class="onboarding-panel-head">
                      <span class="material-symbols-outlined" aria-hidden="true">upload_file</span>
                      <div>
                        <h2>Юзербот через файл сессии</h2>
                        <p class="muted">Подходит, если Telethon-сессия уже создана и проверена.</p>
                      </div>
                    </div>
                    <form id="onboarding-session-form" class="material-form">
                      <label>
                        Название
                        <input name="display_name" required placeholder="Основной юзербот">
                      </label>
                      <label>
                        Имя сессии
                        <input name="session_name" required placeholder="main">
                      </label>
                      <label>
                        Файл .session
                        <input name="session_file" type="file" accept=".session" required>
                      </label>
                      <label>
                        Telegram API ID
                        <input name="api_id" type="number" min="1" step="1" required>
                      </label>
                      <label>
                        Telegram API hash
                        <input name="api_hash" type="password" autocomplete="off" required>
                      </label>
                      <label class="checkbox-line">
                        <input name="make_default" type="checkbox" checked>
                        Использовать по умолчанию
                      </label>
                      <button type="submit">
                        <span class="material-symbols-outlined" aria-hidden="true">upload_file</span>
                        Загрузить сессию
                      </button>
                    </form>
                    <p id="onboarding-session-status" class="status-line" role="status"></p>
                  </section>
                  <section class="onboarding-panel">
                    <div class="onboarding-panel-head">
                      <span class="material-symbols-outlined" aria-hidden="true">person_add</span>
                      <div>
                        <h2>Интерактивный вход юзербота</h2>
                        <p class="muted">Отправляет код Telegram на номер и создает сессию на сервере.</p>
                      </div>
                    </div>
                    <form id="onboarding-interactive-start-form" class="material-form">
                      <label>
                        Название
                        <input name="display_name" required placeholder="Основной юзербот">
                      </label>
                      <label>
                        Имя сессии
                        <input name="session_name" required placeholder="main">
                      </label>
                      <label>
                        Телефон
                        <input name="phone" required placeholder="+79990000000">
                      </label>
                      <label>
                        Telegram API ID
                        <input name="api_id" type="number" min="1" step="1" required>
                      </label>
                      <label>
                        Telegram API hash
                        <input name="api_hash" type="password" autocomplete="off" required>
                      </label>
                      <label class="checkbox-line">
                        <input name="make_default" type="checkbox" checked>
                        Использовать по умолчанию
                      </label>
                      <button type="submit">
                        <span class="material-symbols-outlined" aria-hidden="true">send</span>
                        Получить код
                      </button>
                    </form>
                    <form id="onboarding-interactive-complete-form" class="material-form is-hidden">
                      <input name="login_id" type="hidden">
                      <label>
                        Код Telegram
                        <input name="code" required inputmode="numeric">
                      </label>
                      <label>
                        Пароль 2FA
                        <input name="password" type="password" autocomplete="off">
                      </label>
                      <button type="submit">
                        <span class="material-symbols-outlined" aria-hidden="true">check_circle</span>
                        Завершить вход
                      </button>
                    </form>
                    <p id="onboarding-interactive-status" class="status-line" role="status"></p>
                  </section>
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
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
                      Дней назад
                      <input name="start_recent_days" type="number" min="1" placeholder="пусто = с текущего момента">
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="catalog-layout">
                <aside class="queue-pane" aria-label="Кандидаты каталога">
                  <div class="section-head">
                    <h2>Кандидаты</h2>
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
                      <option value="item">Товары/услуги</option>
                      <option value="offer">Предложения</option>
                      <option value="lead_phrase">Лид-фразы</option>
                      <option value="negative_phrase">Негативные фразы</option>
                    </select>
                  </form>
                  <form id="manual-input-form" class="manual-input-form">
                    <h2>Ручной ввод</h2>
                    <select name="input_type" aria-label="Тип ручного ввода">
                      <option value="catalog_note">Заметка каталога</option>
                      <option value="lead_example">Пример лида</option>
                      <option value="non_lead_example">Пример не-лида</option>
                      <option value="maybe_example">Пример maybe</option>
                      <option value="telegram_link">Ссылка Telegram</option>
                      <option value="manual_text">Ручной текст</option>
                    </select>
                    <textarea name="text" rows="4" placeholder="Текст"></textarea>
                    <input name="url" type="url" placeholder="https://t.me/...">
                    <input name="evidence_note" placeholder="Комментарий к источнику">
                    <label class="checkbox-line">
                      <input name="auto_extract" type="checkbox" checked>
                      Автоизвлечение
                    </label>
                    <button type="submit">Отправить</button>
                    <p id="manual-input-status" class="status-line" role="status"></p>
                  </form>
                  <div id="catalog-candidate-list" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="catalog-candidate-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Выберите кандидата</div>
                  <form id="catalog-edit-form" class="catalog-edit-form" hidden>
                    <label>Название<input id="catalog-name-input" name="canonical_name"></label>
                    <label>JSON-данные<textarea id="catalog-value-json" name="normalized_value"></textarea></label>
                  </form>
                </section>
              </section>
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
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
                  <a href="/catalog">Каталог</a>
                  <a href="/crm">CRM</a>
                  <a href="/quality">Качество</a>
                  <a href="/operations">Операции</a>
                  <a href="/onboarding">Онбординг</a>
                  <a href="/admin">Админка</a>
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
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined&amp;icon_names=check_circle,forum,person_add,radio_button_unchecked,refresh,send,smart_toy,upload_file&amp;display=block">
  <link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="{page}">
  {main}
  <script src="/static/app.js" defer></script>
</body>
</html>"""
