"""HTML page routes for the web workspace."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from pur_leads.services.interest_contexts import InterestContextService
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
                autocomplete="new-password" required minlength="12" maxlength="128"
                supporting-text="12-128 символов, без пробелов по краям, не должен содержать логин">
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
    if not InterestContextService(auth_service.session).has_active_or_draft_context():
        return RedirectResponse("/interest-contexts", status_code=303)
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
                  <a href="/interest-contexts">Интересы</a>
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


@router.get("/help", response_class=HTMLResponse)
def help_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        _page(
            page="help",
            title="Помощь",
            main="""
            <main class="workspace resources-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Помощь</h1>
                </div>
                <nav>
                  <a href="/">Лиды</a>
                  <a href="/interest-contexts">Интересы</a>
                  <a href="/resources">Ресурсы</a>
                  <a href="/artifacts">Артефакты</a>
                  <a href="/operations">Операции</a>
                  <a href="/help">Помощь</a>
                  <button id="logout-button" type="button">Выйти</button>
                </nav>
              </header>
              <section class="help-layout">
                <aside class="help-nav" aria-label="Разделы справки">
                  <a href="#purpose">Что делает продукт</a>
                  <a href="#terms">Терминология</a>
                  <a href="#pipeline">Этапы и связи</a>
                  <a href="#numbers">Как читать цифры</a>
                  <a href="#data">Данные и артефакты</a>
                  <a href="#settings">Настройки шагов</a>
                  <a href="#intent">Слои намерений</a>
                  <a href="#feedback">Обратная связь</a>
                  <a href="#evidence">Объяснимость</a>
                  <a href="#operations">Операции</a>
                </aside>
                <article class="help-content">
                  <section id="purpose" class="help-section">
                    <h2>Что делает продукт</h2>
                    <p>
                      PUR Leads помогает сначала собрать и проверить знания о том, что интересно пользователю,
                      а потом искать в других данных сообщения, где эти интересы проявляются. Продукт не должен
                      быть черным ящиком: у каждого результата есть источник, этап, правила, score, evidence и
                      ссылка назад к исходному сообщению или файлу.
                    </p>
                    <p>
                      Ключевая идея: сначала строится <strong>ядро интересов</strong>, затем по нему выполняется
                      <strong>широкий тематический поиск</strong>, затем более узкий <strong>слой намерений</strong>,
                      затем ручная разметка и AI-фильтр уточняют результат.
                    </p>
                  </section>

                  <section id="terms" class="help-section">
                    <h2>Терминология</h2>
                    <dl class="help-dl">
                      <div><dt>Контекст интересов</dt><dd>Рабочая область для одного пользователя, направления или проверки гипотезы. Внутри контекста хранятся источники, бриф, ядро, запуски анализа и feedback.</dd></div>
                      <div><dt>Источник интересов</dt><dd>Данные, по которым система понимает, что важно пользователю: Telegram-канал, архив чата, документ, ручной текст, переписка с клиентом или сотрудником.</dd></div>
                      <div><dt>Источник анализа</dt><dd>Данные, в которых мы ищем проявления уже собранного ядра: например, отдельный чат дизайнеров, выгруженный ZIP-архив или позже подключенный Telegram-чат.</dd></div>
                      <div><dt>Архив</dt><dd>Файл, который загрузил пользователь. Для демо это ZIP из Telegram Desktop. Архив сам по себе еще не результат анализа.</dd></div>
                      <div><dt>Raw export run</dt><dd>Один технический запуск разбора архива или Telegram-источника. Он сохраняет максимум сырых данных: сообщения, metadata, вложения, пути файлов и счетчики.</dd></div>
                      <div><dt>Raw data</dt><dd>Исходные сообщения и metadata как они пришли из Telegram export или Telethon. На этом этапе AI не используется и смысл не интерпретируется.</dd></div>
                      <div><dt>Prepared data</dt><dd>Подготовленные данные: clean text, tokens, lemmas, POS tags, token map, FTS-документы, Chroma-документы, признаки, n-граммы и сущности.</dd></div>
                      <div><dt>Ядро интересов</dt><dd>Проверенный список тем, продуктов, услуг, сценариев, терминов, синонимов и отрицательных сигналов. Это не чат и не файл, а рабочая база знаний для поиска.</dd></div>
                      <div><dt>Кандидат ядра</dt><dd>Черновой элемент, найденный правилами или LLM. Его можно принять, отклонить, объединить или отредактировать.</dd></div>
                      <div><dt>Элемент ядра</dt><dd>Одобренный кандидат. Именно элементы ядра используются в анализе других чатов.</dd></div>
                      <div><dt>Широкий тематический слой</dt><dd>Первый слой поиска по рабочему ядру. В коде и старых id может называться <code>broad</code>. Его задача - собрать все сообщения по теме, даже с лишним шумом.</dd></div>
                      <div><dt>Широкое совпадение</dt><dd>Сообщение, которое похоже на один из элементов ядра по словам, леммам, синонимам или локальной семантике. Это еще не лид.</dd></div>
                      <div><dt>Слой намерений</dt><dd>Второй, настраиваемый фильтр поверх широкого тематического слоя. Он ищет не просто тему, а намерение: спросить, купить, заказать, найти исполнителя, уточнить цену, попросить помощи.</dd></div>
                      <div><dt>Сообщение намерения</dt><dd>Сообщение, прошедшее широкий тематический слой и слой намерений. Это кандидат для дальнейшего просмотра, но еще не окончательный лид.</dd></div>
                      <div><dt>Feedback / разметка</dt><dd>Решение оператора по сообщению: верно или неверно, плюс комментарий. Эта разметка не меняет старый список сама по себе, а используется для создания нового фильтра.</dd></div>
                      <div><dt>AI-валидация</dt><dd>Запрос к LLM, который смотрит ручную разметку и предлагает изменения: исключающие леммы, фразы, semantic-negative examples, контекстные правила или изменение порогов.</dd></div>
                      <div><dt>AI-фильтр</dt><dd>Новый слой намерений, созданный из одобренных AI-рекомендаций и ручной разметки. Он применяется заново и создает новый список сообщений намерений.</dd></div>
                      <div><dt>Semantic-negative</dt><dd>Семантическое исключение: сообщение похоже по смыслу на примеры, отмеченные как неверные. Оно убирает не только exact-id, но и похожий шум.</dd></div>
                      <div><dt>Positive boost</dt><dd>Усиление сообщений, похожих на примеры, отмеченные как верные. Оно не создает сообщение из воздуха, а повышает score уже найденных кандидатов и защищает правильные примеры от агрессивного удаления.</dd></div>
                      <div><dt>Запуск</dt><dd>Фиксированный результат одного действия: raw export run, preparation job, broad analysis run, intent run, validation run. Запуски нужны, чтобы сравнивать версии.</dd></div>
                      <div><dt>Evidence</dt><dd>Объяснение результата: какие правила сработали, какой элемент ядра совпал, какой score получился, какие тексты использовались, откуда исходное сообщение.</dd></div>
                    </dl>
                  </section>

                  <section id="pipeline" class="help-section">
                    <h2>Этапы и как они связаны</h2>
                    <ol class="help-steps">
                      <li><strong>1. Создание контекста</strong><span>Пользователь создает рабочий контекст, например “ПУР”. Все источники, ядро и запуски дальше должны явно ссылаться на этот контекст.</span></li>
                      <li><strong>2. Загрузка источника интересов</strong><span>Пользователь загружает архив Telegram-канала, документ или ручной текст. На демо используется архив Telegram Desktop. Telegram-ссылки временно убраны из основного демо-сценария.</span></li>
                      <li><strong>3. Raw ingest</strong><span>Система разбирает архив и сохраняет raw export run: JSON/JSONL/parquet, вложения, metadata, ссылки, счетчики сообщений и файлов. AI здесь не используется.</span></li>
                      <li><strong>4. Проверка raw</strong><span>Пользователь проверяет, какой файл или чат был разобран, сколько сообщений и вложений найдено, какие артефакты лежат на диске и какие пути записаны в metadata.</span></li>
                      <li><strong>5. Подготовка данных</strong><span>Система строит prepared data. Stage 2 делает clean text, tokens, lemmas, POS tags и token map. Затем данные попадают в PostgreSQL для FTS, в Chroma для семантического поиска, а также в таблицы признаков, n-грамм и сущностей.</span></li>
                      <li><strong>6. Бриф интересов</strong><span>Бриф можно написать руками или сформировать из источников через LLM. Он объясняет системе, кто пользователь, чем он занимается, что считать интересом и что считать границей домена.</span></li>
                      <li><strong>7. Черновая сборка ядра</strong><span>Правила и локальные признаки формируют кандидатов ядра из prepared data. Это делается до LLM, чтобы можно было видеть, что система нашла сама.</span></li>
                      <li><strong>8. LLM-улучшение кандидатов</strong><span>Кандидаты отправляются в LLM чанками. Модель предлагает нормализованные названия, категории, синонимы, сигналы и причины. Пользователь принимает или отклоняет рекомендации постранично.</span></li>
                      <li><strong>9. Рабочее ядро</strong><span>Одобренные кандидаты становятся элементами ядра. Только они дальше используются для анализа других источников.</span></li>
                      <li><strong>10. Загрузка источника анализа</strong><span>Пользователь загружает отдельный архив чата или другой источник, где надо искать проявления интересов. Этот источник также проходит raw ingest и подготовку данных.</span></li>
                      <li><strong>11. Широкий тематический анализ</strong><span>Система сравнивает подготовленные сообщения источника анализа с рабочим ядром. Результат - широкий тематический запуск: много тематических совпадений, включая шум.</span></li>
                      <li><strong>12. Слой намерений</strong><span>Поверх широкого тематического запуска применяется настраиваемый слой намерений. Он ищет признаки запроса, покупки, помощи, цены или исполнителя и отсекает очевидный шум.</span></li>
                      <li><strong>13. Разметка сообщений намерений</strong><span>Оператор помечает часть сообщений как “Верно” или “Неверно” и оставляет комментарий. Это обучающий сигнал для следующего фильтра.</span></li>
                      <li><strong>14. AI-валидация и рекомендации</strong><span>LLM получает ручную разметку, правила слоя, evidence и примеры сообщений. Она предлагает, что добавить в исключения или усиление.</span></li>
                      <li><strong>15. Применение AI-фильтра</strong><span>Одобренные рекомендации создают новый слой. Его надо применить заново к тому же широкому тематическому запуску. Старый список не переписывается: создается новый intent run для сравнения.</span></li>
                    </ol>
                  </section>

                  <section id="numbers" class="help-section">
                    <h2>Как читать цифры</h2>
                    <p>
                      В интерфейсе есть несколько счетчиков, и они отвечают на разные вопросы. Нельзя сравнивать
                      их как одно и то же число.
                    </p>
                    <dl class="help-dl">
                      <div><dt>3000 входных совпадений</dt><dd>Столько строк пришло из широкого тематического слоя. Это максимум кандидатов, которые слой намерений получил на вход.</dd></div>
                      <div><dt>856 намерений</dt><dd>Столько сообщений прошло текущий слой намерений или AI-фильтр и осталось в новом списке.</dd></div>
                      <div><dt>Очищено 2144</dt><dd>Это разница от широкого тематического входа: 3000 минус 856. Сюда входят все причины отсева: отсутствие include/context, score ниже порога, исключающие правила, ручные exact-id и semantic-negative.</dd></div>
                      <div><dt>1274 -> 856</dt><dd>Это другой вопрос: сколько убрал новый фильтр по сравнению с предыдущим списком сообщений намерений. В текущем примере дополнительно убрано 418 сообщений.</dd></div>
                      <div><dt>Ручные -11</dt><dd>11 сообщений были помечены оператором как неверные и удалены точно по source/telegram id. Это контрольный минимум: они обязаны исчезнуть.</dd></div>
                      <div><dt>Semantic -910</dt><dd>910 широких кандидатов были похожи по смыслу на отрицательные примеры и отсеяны semantic-negative правилом. Это число считается внутри полного прохода от 3000, а не только от старого списка 1274.</dd></div>
                      <div><dt>Усилено 760</dt><dd>760 оставшихся сообщений получили positive boost, потому что похожи на примеры, отмеченные как верные. Это не означает, что все 760 вручную подтверждены.</dd></div>
                    </dl>
                    <p>
                      Правильная формула для чтения демо: <strong>все сообщения</strong> -> <strong>широкие
                      тематические совпадения</strong> -> <strong>сообщения намерений</strong> -> <strong>новый
                      список после feedback/AI-фильтра</strong>.
                    </p>
                  </section>

                  <section id="data" class="help-section">
                    <h2>Данные и артефакты</h2>
                    <dl class="help-dl">
                      <div><dt>Raw files</dt><dd>Исходные JSON/JSONL/parquet и вложения из Telegram. Их задача - сохранить максимум того, что было в архиве или канале.</dd></div>
                      <div><dt>messages.parquet</dt><dd>Каноническая таблица сообщений после raw ingest. Используется для повторной подготовки без повторной загрузки Telegram.</dd></div>
                      <div><dt>texts.parquet</dt><dd>Stage 2: raw_text, clean_text, tokens, lemmas, POS tags, token map. Это основа для объяснимого поиска по словам и леммам.</dd></div>
                      <div><dt>PostgreSQL prepared documents</dt><dd>Рабочая таблица для просмотра, FTS-поиска и связи сообщений с источниками. Здесь данные доступны интерфейсу.</dd></div>
                      <div><dt>Chroma index</dt><dd>Семантический индекс для поиска похожих по смыслу сообщений. Он дополняет FTS, но не заменяет нормализацию и леммы.</dd></div>
                      <div><dt>Features</dt><dd>Признаки сообщения: язык, есть ли вопрос, есть ли URL, похоже ли на решение, техническая плотность, признаки автора и другие сигналы.</dd></div>
                      <div><dt>N-граммы</dt><dd>Частотные слова и фразы. Они помогают увидеть шум, стоп-слова и повторяющиеся темы, но требуют очистки и фильтров.</dd></div>
                      <div><dt>POS-сущности</dt><dd>Кандидаты сущностей из NOUN/PROPN/ADJ-паттернов. Используются для ядра, глоссария и будущего entity review.</dd></div>
                      <div><dt>Draft candidates</dt><dd>Черновые элементы ядра, собранные из подготовленных данных до утверждения.</dd></div>
                      <div><dt>LLM recommendations</dt><dd>Проверяемые предложения модели. Они ничего не меняют, пока пользователь их не одобрит.</dd></div>
                      <div><dt>Core items</dt><dd>Утвержденные элементы рабочего ядра, которые участвуют в анализе источников.</dd></div>
                      <div><dt>Thematic analysis run</dt><dd>Широкий тематический запуск по рабочему ядру. Старое техническое имя - broad analysis run.</dd></div>
                      <div><dt>Intent run</dt><dd>Применение конкретного слоя намерений к конкретному широкому тематическому запуску.</dd></div>
                    </dl>
                  </section>

                  <section id="settings" class="help-section">
                    <h2>Настройки шагов</h2>
                    <div class="help-table-wrap">
                      <table class="help-table">
                        <thead><tr><th>Поле</th><th>Где</th><th>Что значит</th><th>Как влияет</th></tr></thead>
                        <tbody>
                          <tr><td>Название архива</td><td>Архив источника / Архив чата</td><td>Человеческое имя загрузки.</td><td>Помогает отличать запуски и артефакты.</td></tr>
                          <tr><td>Добавить сообщения в рабочую базу</td><td>Архив источника</td><td>Синхронизирует сообщения из raw/parquet в таблицу для поиска.</td><td>Если выключить, архив сохранится, но следующие этапы не увидят сообщения как рабочий источник.</td></tr>
                          <tr><td>Лимит кандидатов</td><td>Сборка ядра</td><td>Сколько верхних rule-based кандидатов взять из ранжированного списка.</td><td>Меньше лимит - быстрее ревью, больше лимит - меньше риск пропустить редкие темы.</td></tr>
                          <tr><td>URL / Token / Модель</td><td>LLM</td><td>Данные провайдера и выбранная модель.</td><td>Создает маршрут `catalog_extractor / primary`, который использует бриф и рекомендации.</td></tr>
                          <tr><td>Бриф</td><td>Бриф</td><td>Текстовое описание интересов и границ.</td><td>Передается в LLM-этапы, чтобы модель не придумывала домен заново.</td></tr>
                          <tr><td>Минимальный score</td><td>Слой намерений</td><td>Порог попадания сообщения в слой.</td><td>Выше порог - меньше, но точнее сообщений.</td></tr>
                          <tr><td>Максимум результатов</td><td>Слой намерений</td><td>Сколько совпадений сохранить.</td><td>Ограничивает длинные результаты, но не меняет raw-данные.</td></tr>
                          <tr><td>Вес широкого тематического слоя</td><td>Слой намерений</td><td>Насколько учитывать score совпадения с ядром.</td><td>Если увеличить, сильнее ценятся сообщения, хорошо совпавшие с ядром.</td></tr>
                          <tr><td>Вес одного намерения</td><td>Слой намерений</td><td>Сколько добавляет каждое включающее условие.</td><td>Если увеличить, явные фразы “нужно/заказать/подскажите” сильнее поднимают score.</td></tr>
                          <tr><td>Semantic-negative threshold</td><td>Слой намерений / AI-фильтр</td><td>Порог похожести на отрицательные примеры.</td><td>Ниже порог - агрессивнее чистка, выше порог - меньше риск удалить полезное.</td></tr>
                          <tr><td>Positive boost</td><td>AI-фильтр</td><td>Добавка к score для сообщений, похожих на верные примеры.</td><td>Помогает сохранить и поднять сообщения, похожие на то, что оператор уже подтвердил.</td></tr>
                        </tbody>
                      </table>
                    </div>
                  </section>

                  <section id="intent" class="help-section">
                    <h2>Как работает слой намерений</h2>
                    <p>
                      Слой намерений применяется только поверх широкого тематического анализа. Сначала сообщение должно
                      совпасть с рабочим ядром, затем слой проверяет включающие, контекстные и исключающие правила.
                      Если есть Stage 2 нормализация, правила смотрят не только raw-текст, но и clean text
                      вместе с леммами. Поэтому “домофоны” может совпасть с правилом “домофон”.
                    </p>
                    <dl class="help-dl">
                      <div><dt>Включающие условия</dt><dd>Фразы намерения: “нужно”, “подскажите”, “где заказать”, “сколько стоит”. Они отвечают на вопрос “человек что-то хочет сделать?”.</dd></div>
                      <div><dt>Контекстные условия</dt><dd>Домен: камеры, домофоны, освещение, реле, щит, датчики. Они отвечают на вопрос “это относится к нашей области?”.</dd></div>
                      <div><dt>Исключающие леммы</dt><dd>Отдельные нормализованные слова, которые должны убрать сообщение. Работают по леммам, а не по raw-регуляркам.</dd></div>
                      <div><dt>Исключающие фразы</dt><dd>Фразы после нормализации, например “аренда рабочего места”. Лучше regex, потому что они объяснимее и устойчивее к падежам.</dd></div>
                      <div><dt>Semantic-negative examples</dt><dd>Короткие примеры нерелевантного смысла. Система считает семантическую похожесть и убирает похожие сообщения, если они не похожи на positive examples сильнее.</dd></div>
                      <div><dt>Advanced regex</dt><dd>Резервный инструмент для сложных случаев. Его надо использовать осторожно, потому что regex хуже объясняется оператору.</dd></div>
                      <div><dt>Исключить элементы ядра</dt><dd>Убирает слишком широкие элементы: “консультирование”, “клиенты”, “смета”.</dd></div>
                      <div><dt>Require include/context</dt><dd>Если включено, совпадение с этим типом правила обязательно.</dd></div>
                      <div><dt>Score</dt><dd>Складывается из веса широкого тематического совпадения, сработавших условий намерения, контекстных условий и positive boost.</dd></div>
                    </dl>
                  </section>

                  <section id="feedback" class="help-section">
                    <h2>Что делает обратная связь</h2>
                    <p>
                      Кнопки “Верно” и “Неверно” не переписывают старый результат. Они создают обучающие примеры
                      для следующего фильтра. Поэтому после разметки нужен отдельный шаг: AI-валидация, одобрение
                      рекомендаций и применение AI-фильтра.
                    </p>
                    <dl class="help-dl">
                      <div><dt>Неверно</dt><dd>Сообщение становится exact negative example. Новый AI-фильтр обязан убрать его по id и может убрать похожие сообщения через semantic-negative.</dd></div>
                      <div><dt>Верно</dt><dd>Сообщение становится positive example. Новый AI-фильтр должен сохранить его и может усилить похожие сообщения через positive boost.</dd></div>
                      <div><dt>Комментарий</dt><dd>Поясняет, почему оператор принял решение. Его надо использовать в LLM-валидации и аудите.</dd></div>
                      <div><dt>AI-рекомендация</dt><dd>Предложение модели изменить фильтр. Пока оно не одобрено, результат анализа не меняется.</dd></div>
                      <div><dt>Применение AI-фильтра</dt><dd>Создает новый intent run. Старый список остается для сравнения: можно увидеть, что именно изменилось.</dd></div>
                    </dl>
                  </section>

                  <section id="evidence" class="help-section">
                    <h2>Объяснимость и трассировка</h2>
                    <p>
                      Для демо важно идти от результата назад к источнику. У сообщений широкого тематического слоя
                      и слоя намерений показывается evidence: какое ядро совпало, какой текст совпал, какие условия
                      сработали, какие части score были добавлены, использовались ли леммы Stage 2, был ли
                      semantic-negative или positive boost.
                    </p>
                    <dl class="help-dl">
                      <div><dt>score</dt><dd>Итоговая локальная оценка совпадения.</dd></div>
                      <div><dt>thematic score</dt><dd>Насколько сообщение совпало с рабочим ядром. В старых JSON-полях может называться broad score.</dd></div>
                      <div><dt>include/context hits</dt><dd>Какие правила слоя намерений сработали.</dd></div>
                      <div><dt>prepared text</dt><dd>Показывает, использовались ли clean text и lemmas.</dd></div>
                      <div><dt>semantic scores</dt><dd>Показывают похожесть на negative и positive examples. Нужны, чтобы понять, почему сообщение удалилось или получило boost.</dd></div>
                      <div><dt>telegram message id</dt><dd>ID исходного сообщения, по которому можно восстановить ссылку и источник.</dd></div>
                    </dl>
                  </section>

                  <section id="operations" class="help-section">
                    <h2>Операции и безопасность демо</h2>
                    <ul class="help-list">
                      <li>Все длинные списки должны смотреться постранично, обычно по 10 строк.</li>
                      <li>Raw-данные не удаляются при повторной подготовке: этапы должны переиспользовать выгрузку.</li>
                      <li>LLM не должен запускаться на raw-ингесте автоматически: сначала raw/parquet, потом подготовка, потом явный LLM-этап.</li>
                      <li>Если страница ничего не показывает, проверьте выбранный контекст в левой колонке.</li>
                        <li>Если нет сообщений намерений, сначала проверьте широкий тематический запуск анализа, затем примените слой намерений.</li>
                      <li>Артефакты и операции нужны для аудита: что было загружено, какие файлы созданы, какие job выполнялись.</li>
                    </ul>
                  </section>
                </article>
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
    return RedirectResponse("/resources", status_code=303)


@router.get("/interest-contexts", response_class=HTMLResponse)
def interest_contexts_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("context"))


@router.get("/interest-contexts/source-archive", response_class=HTMLResponse)
def interest_context_source_archive_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("load_archive"))


@router.get("/interest-contexts/source-link", response_class=HTMLResponse)
def interest_context_source_link_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/interest-contexts/source-archive", status_code=303)


@router.get("/interest-contexts/check", response_class=HTMLResponse)
def interest_context_check_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("check"))


@router.get("/interest-contexts/prepare", response_class=HTMLResponse)
def interest_context_prepare_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare"))


@router.get("/interest-contexts/prepare/texts", response_class=HTMLResponse)
def interest_context_prepare_texts_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare_texts"))


@router.get("/interest-contexts/prepare/search-fts", response_class=HTMLResponse)
def interest_context_prepare_search_fts_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare_search_fts"))


@router.get("/interest-contexts/prepare/search-chroma", response_class=HTMLResponse)
def interest_context_prepare_search_chroma_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare_search_chroma"))


@router.get("/interest-contexts/prepare/features", response_class=HTMLResponse)
def interest_context_prepare_features_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare_features"))


@router.get("/interest-contexts/prepare/aggregates", response_class=HTMLResponse)
def interest_context_prepare_aggregates_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare_aggregates"))


@router.get("/interest-contexts/prepare/entities", response_class=HTMLResponse)
def interest_context_prepare_entities_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("prepare_entities"))


@router.get("/interest-contexts/core", response_class=HTMLResponse)
def interest_context_core_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("core"))


@router.get("/interest-contexts/core/candidates", response_class=HTMLResponse)
def interest_context_candidates_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("candidates"))


@router.get("/interest-contexts/core/reviews", response_class=HTMLResponse)
def interest_context_reviews_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("reviews"))


@router.get("/interest-contexts/core/items", response_class=HTMLResponse)
def interest_context_core_items_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("items"))


@router.get("/interest-contexts/analyze", response_class=HTMLResponse)
def interest_context_analysis_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("analysis_upload"))


@router.get("/interest-contexts/analyze/runs", response_class=HTMLResponse)
def interest_context_analysis_runs_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("analysis_runs"))


@router.get("/interest-contexts/analyze/matches", response_class=HTMLResponse)
def interest_context_analysis_matches_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("analysis_matches"))


@router.get("/interest-contexts/llm", response_class=HTMLResponse)
def interest_context_llm_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("llm"))


@router.get("/interest-contexts/brief", response_class=HTMLResponse)
def interest_context_brief_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("brief"))


@router.get("/interest-contexts/intent-layers", response_class=HTMLResponse)
def interest_context_intent_layers_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_layers"))


@router.get("/interest-contexts/intent-runs", response_class=HTMLResponse)
def interest_context_intent_runs_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_runs"))


@router.get("/interest-contexts/intent-matches", response_class=HTMLResponse)
def interest_context_intent_matches_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_matches"))


@router.get("/interest-contexts/project-opportunities", response_class=HTMLResponse)
def interest_context_project_opportunities_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("project_opportunities"))


@router.get("/interest-contexts/intent-review", response_class=HTMLResponse)
def interest_context_intent_review_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_review"))


@router.get("/interest-contexts/intent-ai-validation", response_class=HTMLResponse)
def interest_context_intent_ai_validation_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_ai_validation"))


@router.get("/interest-contexts/intent-ai-recommendations", response_class=HTMLResponse)
def interest_context_intent_ai_recommendations_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_ai_recommendations"))


@router.get("/interest-contexts/intent-ai-filter", response_class=HTMLResponse)
def interest_context_intent_ai_filter_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_ai_filter"))


@router.get("/interest-contexts/intent-exclusions", response_class=HTMLResponse)
def interest_context_intent_exclusions_page(
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_interest_context_step_page("intent_exclusions"))


_INTEREST_CONTEXT_STEPS = (
    ("context", "/interest-contexts", "Контекст"),
    ("load_archive", "/interest-contexts/source-archive", "Архив источника"),
    ("check", "/interest-contexts/check", "Проверка raw"),
    ("prepare", "/interest-contexts/prepare", "Подготовка"),
    ("prepare_texts", "/interest-contexts/prepare/texts", "Stage 2"),
    ("prepare_search_fts", "/interest-contexts/prepare/search-fts", "FTS"),
    ("prepare_search_chroma", "/interest-contexts/prepare/search-chroma", "Chroma"),
    ("prepare_features", "/interest-contexts/prepare/features", "Stage 3"),
    ("prepare_aggregates", "/interest-contexts/prepare/aggregates", "Stage 4"),
    ("prepare_entities", "/interest-contexts/prepare/entities", "Stage 5"),
    ("llm", "/interest-contexts/llm", "LLM"),
    ("brief", "/interest-contexts/brief", "Бриф"),
    ("core", "/interest-contexts/core", "Сборка ядра"),
    ("candidates", "/interest-contexts/core/candidates", "Кандидаты"),
    ("reviews", "/interest-contexts/core/reviews", "Рекомендации"),
    ("items", "/interest-contexts/core/items", "Рабочее ядро"),
    ("analysis_upload", "/interest-contexts/analyze", "Архив чата"),
    ("analysis_runs", "/interest-contexts/analyze/runs", "Запуски анализа"),
    ("analysis_matches", "/interest-contexts/analyze/matches", "Широкие совпадения"),
    ("intent_layers", "/interest-contexts/intent-layers", "Слои намерений"),
    ("intent_runs", "/interest-contexts/intent-runs", "Запуски намерений"),
    ("intent_matches", "/interest-contexts/intent-matches", "Сообщения намерений"),
    ("project_opportunities", "/interest-contexts/project-opportunities", "Проектные возможности"),
    ("intent_review", "/interest-contexts/intent-review", "Разметка"),
    ("intent_ai_validation", "/interest-contexts/intent-ai-validation", "AI-валидация"),
    ("intent_ai_recommendations", "/interest-contexts/intent-ai-recommendations", "AI-рекомендации"),
    ("intent_ai_filter", "/interest-contexts/intent-ai-filter", "AI-фильтр"),
)


def _interest_context_step_page(step: str) -> str:
    title_by_step = {
        "context": "Контекст интересов",
        "load_archive": "Архив источника интересов",
        "load_link": "Telegram-ссылка источника",
        "check": "Проверка raw-данных",
        "prepare": "Подготовка данных",
        "prepare_texts": "Stage 2: нормализованные тексты",
        "prepare_search_fts": "Поиск FTS",
        "prepare_search_chroma": "Поиск Chroma",
        "prepare_features": "Stage 3: признаки",
        "prepare_aggregates": "Stage 4: агрегаты",
        "prepare_entities": "Stage 5: сущности",
        "llm": "LLM-провайдер",
        "brief": "Бриф ядра интересов",
        "core": "Сборка ядра",
        "candidates": "Кандидаты ядра",
        "reviews": "LLM-рекомендации",
        "items": "Рабочее ядро",
        "analysis_upload": "Архив чата для анализа",
        "analysis_runs": "Запуски анализа",
        "analysis_matches": "Широкие совпадения",
        "intent_layers": "Слои намерений",
        "intent_runs": "Запуски намерений",
        "intent_matches": "Сообщения намерений",
        "project_opportunities": "Проектные возможности",
        "intent_review": "Разметка сообщений намерений",
        "intent_ai_validation": "AI-валидация по разметке",
        "intent_ai_recommendations": "Рекомендации AI",
        "intent_ai_filter": "Создание AI-фильтра",
        "intent_exclusions": "Применение исключений",
    }
    intro_by_step = {
        "context": "Создайте или выберите контекст. Дальше все источники, ядро, анализ и намерения привязаны к нему.",
        "load_archive": "Выберите контекст слева и загрузите ZIP-архив Telegram Desktop. На этом шаге сохраняем raw/parquet без AI.",
        "load_link": "Добавьте Telegram-канал или чат по ссылке. Система поставит raw-выгрузку в очередь.",
        "check": "Проверьте, что raw/parquet, вложения и рабочая таблица собраны корректно.",
        "prepare": "Запустите нормализацию, локальный индекс, извлечение и ранжирование кандидатов.",
        "prepare_texts": "Проверьте, что именно получилось после нормализации: raw_text, clean_text, tokens, lemmas, POS и token-map.",
        "prepare_search_fts": "Проверьте точный полнотекстовый поиск по нормализованному тексту и леммам.",
        "prepare_search_chroma": "Проверьте семантический поиск по Chroma-индексу выбранного raw-run.",
        "prepare_features": "Проверьте детерминированные признаки сообщений и текстов вложений: вопрос, ссылки, контакты, score языка.",
        "prepare_aggregates": "Проверьте агрегаты: n-граммы, частотные термины, URL, качество источника и счетчики.",
        "prepare_entities": "Проверьте извлеченные POS-сущности и результат очистки/ранжирования.",
        "llm": "Подключите провайдера и модель. Это отдельный ресурс для LLM-этапов.",
        "brief": "Сформируйте или отредактируйте объяснимый контекст для модели.",
        "core": "Сформируйте rule-based черновик ядра. Этот экран не показывает длинные списки.",
        "candidates": "Просматривайте rule-based кандидатов постранично, без длинного списка на рабочем экране.",
        "reviews": "Разбирайте рекомендации LLM постранично: одобрить, отклонить или вернуть на ревью.",
        "items": "Здесь лежат элементы ядра интересов, которые оператор уже одобрил.",
        "analysis_upload": "Загрузите отдельный ZIP-архив чата, который надо проверить по рабочему ядру.",
        "analysis_runs": "Выберите широкий тематический запуск. Это артефакт первого слоя совпадений по ядру.",
        "analysis_matches": "Постранично смотрите сообщения, совпавшие с рабочим ядром интересов.",
        "intent_layers": "Создайте или примените настраиваемый слой намерений поверх широкого тематического анализа.",
        "intent_runs": "Выберите запуск слоя намерений. Это отдельный проверяемый артефакт.",
        "intent_matches": "Постранично смотрите сообщения, прошедшие слой намерений, и объяснение почему.",
        "project_opportunities": "Для чата дизайнеров ищем проектные возможности: где ПУР может помочь оборудованием, инженерией, интеграцией или консультацией.",
        "intent_review": "Помечайте сообщения как правильные или неправильные и оставляйте комментарии для обучения следующего фильтра.",
        "intent_ai_validation": "Запускайте AI-валидацию вручную только после накопления операторской разметки.",
        "intent_ai_recommendations": "Разбирайте предложения модели: одобрить или отклонить, видя impact preview.",
        "intent_ai_filter": "Создавайте новый слой намерений только из одобренных AI-рекомендаций.",
        "intent_exclusions": "Применяйте исключения из feedback после проверки влияния на текущий запуск.",
    }
    step = step if step in title_by_step else "context"
    title = title_by_step[step]
    main = f"""
            <main class="workspace resources-workspace" data-interest-step="{step}">
              <header class="topbar scenario-topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>{title}</h1>
                </div>
                <nav class="interest-step-nav" aria-label="Сценарий ядра интересов">
                  {_interest_context_step_nav(step)}
                  <md-outlined-button id="logout-button" type="button">Выйти</md-outlined-button>
                </nav>
              </header>
              <section class="interest-context-layout">
                {_interest_context_context_panel()}
                <section class="detail-pane interest-context-detail-pane" aria-live="polite">
                  {_interest_context_detail_header(intro_by_step[step])}
                  {_interest_context_step_body(step)}
                </section>
                {_interest_context_stage_panel(step)}
              </section>
            </main>
            """
    return _page(page="interest-contexts", title=title, main=main)


def _interest_context_step_nav(active_step: str) -> str:
    return "".join(
        f'<a class="interest-step-link {"is-active" if step == active_step else ""}" '
        f'data-interest-step-link="{step}" href="{path}">{label}</a>'
        for step, path, label in _INTEREST_CONTEXT_STEPS
    )


def _interest_context_context_panel() -> str:
    return """
                <aside class="queue-pane interest-context-pane" aria-label="Контексты интересов">
                  <div class="section-head">
                    <div>
                      <h2>Контексты</h2>
                      <p class="muted">Отдельное ядро знаний о том, что пользователю интересно искать и улучшать.</p>
                    </div>
                    <md-outlined-button id="interest-context-refresh" type="button">
                      <md-icon slot="icon">refresh</md-icon>
                      Обновить
                    </md-outlined-button>
                  </div>
                  <p class="muted context-selector-note">
                    Выбранный контекст прокидывается во все следующие шаги: raw, подготовку, бриф,
                    ядро, анализ чатов и слой намерений.
                  </p>
                  <a class="button-link" href="/interest-contexts">Создать или выбрать контекст</a>
                  <div id="interest-context-list" class="queue-list" aria-live="polite"></div>
                  <p id="interest-context-status" class="status-line" role="status"></p>
                </aside>
    """


def _interest_context_detail_header(intro: str) -> str:
    return f"""
                  <header class="detail-header scenario-detail-header">
                    <div>
                      <h2 id="interest-context-detail-title">Выберите контекст</h2>
                      <p id="interest-context-detail-description" class="muted">{intro}</p>
                    </div>
                    <div class="badges" id="interest-context-detail-badges"></div>
                  </header>
    """


def _interest_context_step_body(step: str) -> str:
    bodies = {
        "context": _interest_context_create_body,
        "load_archive": _interest_context_archive_body,
        "load_link": _interest_context_link_body,
        "check": _interest_context_check_body,
        "prepare": _interest_context_prepare_body,
        "prepare_texts": _interest_context_prepare_texts_body,
        "prepare_search_fts": _interest_context_prepare_search_fts_body,
        "prepare_search_chroma": _interest_context_prepare_search_chroma_body,
        "prepare_features": _interest_context_prepare_features_body,
        "prepare_aggregates": _interest_context_prepare_aggregates_body,
        "prepare_entities": _interest_context_prepare_entities_body,
        "core": _interest_context_core_body,
        "candidates": _interest_context_candidates_body,
        "reviews": _interest_context_reviews_body,
        "items": _interest_context_items_body,
        "analysis_upload": _interest_context_analysis_upload_body,
        "analysis_runs": _interest_context_analysis_runs_body,
        "analysis_matches": _interest_context_analysis_matches_body,
        "llm": _interest_context_llm_body,
        "brief": _interest_context_brief_body,
        "intent_layers": _interest_context_intent_layers_body,
        "intent_runs": _interest_context_intent_runs_body,
        "intent_matches": _interest_context_intent_matches_body,
        "project_opportunities": _interest_context_project_opportunities_body,
        "intent_review": _interest_context_intent_review_body,
        "intent_ai_validation": _interest_context_intent_ai_validation_body,
        "intent_ai_recommendations": _interest_context_intent_ai_recommendations_body,
        "intent_ai_filter": _interest_context_intent_ai_filter_body,
        "intent_exclusions": _interest_context_intent_exclusions_body,
    }
    return bodies[step]()


def _interest_context_create_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Создание контекста</h3>
                        <p class="muted">
                          Контекст - это отдельное ядро интересов пользователя. К нему привязываются источники,
                          подготовленные данные, LLM-бриф, утвержденное ядро и все последующие анализы.
                        </p>
                      </div>
                    </div>
                    <form id="interest-context-create-form" class="material-form single-column-form">
                      <md-outlined-text-field name="name" label="Название" required
                        placeholder="Например, ПУР умный дом">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="description" label="Описание" type="textarea"
                        placeholder="Какие интересы, задачи и источники сюда входят">
                      </md-outlined-text-field>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">add</md-icon>
                        Создать контекст
                      </md-filled-button>
                    </form>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/source-archive">Загрузить архив источника</a>
                    </div>
                    <p class="muted">
                      При загрузке архива будет использован контекст, выбранный в левой колонке. Если контекстов несколько,
                      сначала выберите нужный, затем переходите к архиву.
                    </p>
                  </section>
    """


def _interest_context_link_body() -> str:
    return """
                  <section class="detail-section">
                    <h3>Telegram-ссылка</h3>
                    <p class="muted">
                      Один источник по ссылке или @username. Результат этого шага - source и raw export job.
                    </p>
                    <form id="interest-context-telegram-source-form" class="material-form interest-source-form">
                      <md-outlined-text-field name="input_ref" label="Ссылка или @username" required
                        placeholder="https://t.me/purmaster">
                      </md-outlined-text-field>
                      <label class="material-select-field">
                        Диапазон
                        <select name="range_mode">
                          <option value="from_beginning">С самого начала</option>
                          <option value="recent_days">За N дней</option>
                          <option value="since_date">С даты</option>
                          <option value="from_message">С сообщения</option>
                          <option value="after_message">После сообщения</option>
                          <option value="since_checkpoint">С последнего чекпоинта</option>
                          <option value="from_now">С текущего момента</option>
                        </select>
                      </label>
                      <md-outlined-text-field name="recent_days" label="Дней назад" type="number" value="180">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="message_id" label="ID сообщения" type="number">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="since_date" label="Дата начала" type="datetime-local">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="batch_size" label="Размер пачки" type="number" value="1000">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="max_messages" label="Максимум сообщений" type="number">
                      </md-outlined-text-field>
                      <label class="material-checkbox-line">
                        <input name="media_enabled" type="checkbox">
                        Скачать вложения
                      </label>
                      <label class="material-checkbox-line">
                        <input name="media_types" type="checkbox" value="document" checked>
                        Документы
                      </label>
                      <md-outlined-text-field name="max_media_size_bytes" label="Лимит файла, байт" type="number">
                      </md-outlined-text-field>
                      <label class="material-checkbox-line">
                        <input name="check_access" type="checkbox">
                        Проверить доступ
                      </label>
                      <label class="material-checkbox-line">
                        <input name="enqueue_raw_export" type="checkbox" checked>
                        Поставить raw-выгрузку в очередь
                      </label>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">send</md-icon>
                        Добавить источник
                      </md-filled-button>
                    </form>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/check">Проверить raw-данные</a>
                    </div>
                    <p class="muted">Когда raw-выгрузка завершится, проверьте parquet, вложения и примеры сообщений.</p>
                  </section>
    """


def _interest_context_archive_body() -> str:
    return """
                  <section class="detail-section">
                    <h3>Архив Telegram Desktop</h3>
                    <p class="muted">
                      Один ZIP-архив источника интересов. Он будет привязан к выбранному контексту слева.
                      Результат шага - raw/parquet и, при включенной галочке, рабочие сообщения для следующих этапов.
                    </p>
                    <div class="explain-box">
                      <strong>Что будет создано</strong>
                      <ul>
                        <li>Raw-run: проверяемый запуск импорта конкретного архива.</li>
                        <li>messages.jsonl и messages.parquet: один раз сохраненная выгрузка сообщений без AI.</li>
                        <li>attachments.jsonl: список вложений и ссылки на файлы, если они были в архиве.</li>
                        <li>Рабочая таблица сообщений: включается галочкой ниже, нужна для проверки, подготовки и анализа.</li>
                      </ul>
                    </div>
                    <form id="interest-context-telegram-archive-form" class="material-form interest-source-form">
                      <md-outlined-text-field name="display_name" label="Название архива"
                        placeholder="Экспорт Telegram">
                      </md-outlined-text-field>
                      <label class="material-file-field">
                        ZIP-архив
                        <input name="file" type="file" accept=".zip,application/zip" required>
                      </label>
                      <label class="material-checkbox-line">
                        <input name="sync_source_messages" type="checkbox" checked>
                        Добавить сообщения в рабочую базу для поиска и анализа
                      </label>
                      <p class="muted form-help">
                        Оставьте включенным, чтобы после загрузки видеть сообщения в проверке данных
                        и использовать их на следующих этапах. Если выключить, архив сохранится только
                        как файл-источник.
                      </p>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">upload_file</md-icon>
                        Загрузить архив
                      </md-filled-button>
                    </form>
                    <div id="interest-context-upload-progress" class="upload-progress is-hidden">
                      <md-linear-progress id="interest-context-upload-progress-bar" value="0"></md-linear-progress>
                      <span id="interest-context-upload-progress-label">0%</span>
                    </div>
                    <p id="interest-context-upload-status" class="status-line" role="status"></p>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/check">Проверить raw-данные</a>
                    </div>
                    <p class="muted">После загрузки проверьте, сколько сообщений и вложений попало в raw/parquet.</p>
                  </section>
    """


def _interest_context_check_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Raw/parquet и рабочая таблица</h3>
                        <p class="muted">
                          Проверяем количество сообщений, вложений, raw-запуски, наличие файлов и короткие примеры.
                          Полный список сообщений здесь намеренно не показываем.
                        </p>
                      </div>
                      <md-filled-tonal-button id="interest-context-open-raw-review" type="button">
                        <md-icon slot="icon">table_chart</md-icon>
                        Обновить проверку
                      </md-filled-tonal-button>
                    </div>
                    <div class="explain-box">
                      <strong>Как читать этот экран</strong>
                      <ul>
                        <li>Raw/parquet файлы относятся к конкретному raw-run и показывают, что физически лежит на диске.</li>
                        <li>Примеры сообщений относятся либо к рабочей таблице, либо к messages.jsonl, если рабочая таблица пуста.</li>
                        <li>Если есть "Нет файла", значит путь записан в metadata, но файла на диске сейчас нет.</li>
                      </ul>
                    </div>
                    <div id="interest-context-raw-review" class="raw-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Источники</h3>
                      <a class="interest-next-link" href="/interest-contexts/prepare">Дальше: подготовка данных</a>
                    </div>
                    <div id="interest-context-source-list" class="resource-list" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Подготовка данных</h3>
                        <p class="muted">
                          Последовательно запускает Stage 2-5: PostgreSQL prepared documents, FTS, Chroma, признаки, агрегаты, сущности и ранжирование.
                        </p>
                      </div>
                      <md-filled-button id="interest-context-prepare-data" type="button">
                        <md-icon slot="icon">model_training</md-icon>
                        Подготовить данные
                      </md-filled-button>
                    </div>
                    <div class="explain-box">
                      <strong>Что именно делает подготовка</strong>
                      <ul>
                        <li>Stage 2: сохраняет raw_text, строит clean_text, tokens, lemmas, POS-теги и token-map.</li>
                        <li>Индекс: кладет подготовленный текст в PostgreSQL FTS и Chroma-совместимый слой local_hashing_v1.</li>
                        <li>Stage 3: добавляет признаки в PostgreSQL: вопрос, решение, ссылки, цены, контакты, технический score.</li>
                        <li>Stage 4: сохраняет агрегаты в PostgreSQL: n-граммы, URL, источники и качество данных.</li>
                        <li>Stage 5: сохраняет сущности и ранжирование в PostgreSQL для дальнейшей сборки ядра.</li>
                      </ul>
                    </div>
                    <div id="interest-context-prepare-progress" class="prepare-progress-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Результаты подготовки</h3>
                      <a class="interest-next-link" href="/interest-contexts/prepare/texts">Открыть Stage 2</a>
                    </div>
                    <div class="table-list">
                      <a class="table-row linked-row" href="/interest-contexts/prepare/texts">
                        <div>
                          <strong>Stage 2: нормализованные тексты</strong>
                          <p class="muted">raw_text, clean_text, tokens, lemmas, POS и token-map из PostgreSQL.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/prepare/search-fts">
                        <div>
                          <strong>FTS поиск</strong>
                          <p class="muted">Полнотекстовый поиск по PostgreSQL prepared documents.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/prepare/search-chroma">
                        <div>
                          <strong>Chroma поиск</strong>
                          <p class="muted">Семантический поиск по Chroma-индексу raw-run.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/prepare/features">
                        <div>
                          <strong>Stage 3: признаки</strong>
                          <p class="muted">Вопросы, ссылки, контакты, цены, технический score из PostgreSQL.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/prepare/aggregates">
                        <div>
                          <strong>Stage 4: агрегаты</strong>
                          <p class="muted">N-граммы, URL, качество источника и счетчики из PostgreSQL.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/prepare/entities">
                        <div>
                          <strong>Stage 5: сущности</strong>
                          <p class="muted">POS-кандидаты, очистка, ранжирование и причины score из PostgreSQL.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                    </div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Источники для подготовки</h3>
                      <a class="interest-next-link" href="/interest-contexts/core">Дальше: формирование ядра</a>
                    </div>
                    <div id="interest-context-source-list" class="resource-list" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_texts_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Stage 2: нормализованные тексты</h3>
                        <p class="muted">Один артефакт: подготовленные документы в PostgreSQL. Показываем 10 строк на страницу.</p>
                      </div>
                      <md-outlined-button id="interest-context-prep-texts-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Что здесь проверять</strong>
                      <ul>
                        <li>raw_text - исходный текст сообщения или текстового чанка документа.</li>
                        <li>clean_text - очищенный текст для поиска, без изменения смысла.</li>
                        <li>tokens, lemmas, POS и token-map - то, чем дальше пользуются поиск, признаки и сущности.</li>
                      </ul>
                    </div>
                    <div id="interest-context-prep-run-selector" data-prep-run-metadata-key="text_normalization"></div>
                    <div id="interest-context-prep-texts" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_search_fts_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>FTS поиск</h3>
                        <p class="muted">Ищет по PostgreSQL `telegram_prepared_documents`: clean_text + lemmas_text.</p>
                      </div>
                    </div>
                    <div id="interest-context-prep-run-selector" data-prep-run-metadata-key="fts_index"></div>
                    <form id="interest-context-prep-fts-form" class="material-form interest-source-form">
                      <md-outlined-text-field name="q" label="Запрос" required
                        placeholder="домофон камера dahua">
                      </md-outlined-text-field>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">search</md-icon>
                        Искать в FTS
                      </md-filled-button>
                    </form>
                    <p class="muted form-help">FTS нужен для объяснимого поиска по словам и леммам. Он не заменяет Chroma, а дополняет ее.</p>
                    <div id="interest-context-prep-fts-results" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_search_chroma_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Chroma поиск</h3>
                        <p class="muted">Ищет семантически по Chroma-индексу выбранного raw-run.</p>
                      </div>
                    </div>
                    <div id="interest-context-prep-run-selector" data-prep-run-metadata-key="chroma_index"></div>
                    <form id="interest-context-prep-chroma-form" class="material-form interest-source-form">
                      <md-outlined-text-field name="q" label="Запрос" required
                        placeholder="человек ищет домофон или камеру">
                      </md-outlined-text-field>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">hub</md-icon>
                        Искать в Chroma
                      </md-filled-button>
                    </form>
                    <p class="muted form-help">Chroma нужен для похожих по смыслу сообщений, когда точных слов может не быть.</p>
                    <div id="interest-context-prep-chroma-results" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_features_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Stage 3: признаки</h3>
                        <p class="muted">Постранично показывает признаки из `telegram_prepared_documents.feature_json`.</p>
                      </div>
                      <md-outlined-button id="interest-context-prep-features-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Что добавляет Stage 3</strong>
                      <ul>
                        <li>question/solution/offer flags - быстрые признаки типа сообщения.</li>
                        <li>urls, prices, phones, usernames - структурные сигналы, которые можно искать и проверять.</li>
                        <li>technical_language_score - доля NOUN/PROPN, полезно для отбора терминов.</li>
                      </ul>
                    </div>
                    <div id="interest-context-prep-run-selector" data-prep-run-metadata-key="feature_enrichment"></div>
                    <div id="interest-context-prep-features" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_aggregates_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Stage 4: агрегаты</h3>
                        <p class="muted">Один экран для summary, n-грамм, URL и качества источника из PostgreSQL stage outputs.</p>
                      </div>
                      <md-outlined-button id="interest-context-prep-aggregates-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Что смотреть в агрегатах</strong>
                      <ul>
                        <li>N-граммы строятся из лемм Stage 2, частые служебные слова скрываются.</li>
                        <li>Список ниже постраничный: можно смотреть все леммы, биграммы и триграммы, а не только top-10.</li>
                        <li>URL и качество источника показывают, из чего реально собраны данные.</li>
                      </ul>
                    </div>
                    <div id="interest-context-prep-run-selector" data-prep-run-metadata-key="aggregated_stats"></div>
                    <div id="interest-context-prep-aggregates" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_prepare_entities_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Stage 5: сущности и ранжирование</h3>
                        <p class="muted">Показывает POS-сущности и rule-based ranking из `telegram_entity_candidates`.</p>
                      </div>
                      <md-outlined-button id="interest-context-prep-entities-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div id="interest-context-prep-run-selector" data-prep-run-metadata-key="entity_ranking"></div>
                    <div id="interest-context-prep-entities" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_core_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Rule-based сборка ядра</h3>
                        <p class="muted">
                          Одно действие: собрать черновик кандидатов из подготовленных данных. LLM здесь не используется.
                        </p>
                      </div>
                      <div class="button-row">
                        <md-outlined-text-field id="interest-context-draft-max-items" label="Лимит кандидатов"
                          type="number" value="1000" min="10" step="10">
                        </md-outlined-text-field>
                        <md-filled-button id="interest-context-build-draft" type="button">
                          <md-icon slot="icon">hub</md-icon>
                          Сформировать ядро
                        </md-filled-button>
                      </div>
                    </div>
                    <div class="explain-box">
                      <strong>Как собирается ядро</strong>
                      <ul>
                        <li>Вход: результаты подготовки Stage 5 - очищенные и ранжированные сущности из сообщений и документов.</li>
                        <li>Правила: POS-паттерны NOUN/PROPN/ADJ+NOUN, частотность, evidence из источников, штрафы за шум.</li>
                        <li>Лимит 1000 - верхняя граница кандидатов из ранжированного списка, чтобы не тащить весь шум. Сейчас его можно поменять перед запуском.</li>
                        <li>Результат: черновые кандидаты. После approve они становятся рабочим ядром и влияют на анализ чатов.</li>
                      </ul>
                    </div>
                    <div id="interest-context-draft-review" class="draft-review-panel" data-summary-only="true" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Дальше по ядру</h3>
                      <a class="interest-next-link" href="/interest-contexts/core/candidates">Открыть кандидатов</a>
                    </div>
                    <div class="table-list">
                      <a class="table-row linked-row" href="/interest-contexts/core/candidates">
                        <div>
                          <strong>Кандидаты ядра</strong>
                          <p class="muted">Rule-based кандидаты с пагинацией по 10 строк.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/core/reviews">
                        <div>
                          <strong>LLM-рекомендации</strong>
                          <p class="muted">Отдельный экран для запуска и ревью LLM-улучшения.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/core/items">
                        <div>
                          <strong>Рабочее ядро</strong>
                          <p class="muted">Утвержденные элементы после approve.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                      <a class="table-row linked-row" href="/interest-contexts/analyze">
                        <div>
                          <strong>Анализ чата</strong>
                          <p class="muted">Загрузка отдельного Telegram-архива и проверка по рабочему ядру.</p>
                        </div>
                        <span>Открыть</span>
                      </a>
                    </div>
                  </section>
    """


def _interest_context_candidates_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Кандидаты ядра</h3>
                        <p class="muted">
                          Постраничное ревью rule-based кандидатов. На этой странице не запускаются LLM-запросы.
                        </p>
                      </div>
                      <div class="button-row">
                        <md-outlined-button id="interest-context-draft-items-refresh" type="button">
                          <md-icon slot="icon">refresh</md-icon>
                          Обновить
                        </md-outlined-button>
                        <a class="interest-next-link" href="/interest-contexts/core/reviews">LLM-рекомендации</a>
                      </div>
                    </div>
                    <div class="explain-box">
                      <strong>Связь с правилами</strong>
                      <ul>
                        <li>Score показывает, насколько кандидат подтвержден частотой, POS-паттерном и evidence.</li>
                        <li>Evidence - примеры сообщений или документов, из которых кандидат появился.</li>
                        <li>AI status показывает, проходил ли кандидат отдельную LLM-проверку на странице рекомендаций.</li>
                      </ul>
                    </div>
                    <div id="interest-context-draft-items-page" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_reviews_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>LLM-рекомендации</h3>
                        <p class="muted">
                          Одно действие и один артефакт: прогнать кандидатов через LLM и разбирать рекомендации постранично.
                        </p>
                      </div>
                      <div class="button-row">
                        <md-filled-tonal-button id="interest-context-enhance-draft-llm" type="button">
                          <md-icon slot="icon">auto_fix_high</md-icon>
                          Запустить LLM-рекомендации
                        </md-filled-tonal-button>
                        <md-outlined-button id="interest-context-review-items-refresh" type="button">
                          <md-icon slot="icon">refresh</md-icon>
                          Обновить
                        </md-outlined-button>
                        <a class="interest-next-link" href="/interest-contexts/core">Назад к формированию</a>
                        <a class="interest-next-link" href="/interest-contexts/core/items">Рабочее ядро</a>
                      </div>
                    </div>
                    <div id="interest-context-llm-enhance-review" class="draft-review-panel" data-summary-only="true" aria-live="polite"></div>
                    <div id="interest-context-review-items-page" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_items_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Рабочее ядро</h3>
                        <p class="muted">
                          Сюда попадают кандидаты после approve. Эти элементы дальше должны использоваться
                          для поиска интересов и лидов.
                        </p>
                      </div>
                      <div class="button-row">
                        <md-outlined-button id="interest-context-core-items-refresh" type="button">
                          <md-icon slot="icon">refresh</md-icon>
                          Обновить
                        </md-outlined-button>
                        <a class="interest-next-link" href="/interest-contexts/core/reviews">LLM-рекомендации</a>
                        <a class="interest-next-link" href="/interest-contexts/analyze">Анализ чата</a>
                      </div>
                    </div>
                    <div id="interest-context-core-items-page" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_analysis_upload_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Загрузка чата для анализа</h3>
                        <p class="muted">
                          Архив Telegram Desktop будет сохранен как raw/parquet, сообщения попадут в рабочую таблицу,
                          затем система сопоставит их с утвержденным ядром интересов. LLM на этом шаге не используется.
                        </p>
                      </div>
                    </div>
                    <form id="interest-analysis-archive-form" class="material-form interest-source-form">
                      <md-outlined-text-field name="display_name" label="Название анализа"
                        placeholder="Например, чат с лидами за апрель">
                      </md-outlined-text-field>
                      <label class="material-file-field">
                        ZIP-архив Telegram Desktop
                        <input name="file" type="file" accept=".zip,application/zip" required>
                      </label>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">analytics</md-icon>
                        Загрузить и проанализировать
                      </md-filled-button>
                    </form>
                    <div id="interest-analysis-upload-progress" class="upload-progress is-hidden">
                      <md-linear-progress id="interest-analysis-upload-progress-bar" value="0"></md-linear-progress>
                      <span id="interest-analysis-upload-progress-label">0%</span>
                    </div>
                    <p id="interest-analysis-status" class="status-line" role="status"></p>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/analyze/runs">Открыть запуски анализа</a>
                    </div>
                    <p class="muted">После загрузки откройте запуск анализа, затем отдельно смотрите найденные сообщения.</p>
                  </section>
    """


def _interest_context_analysis_runs_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Запуски анализа</h3>
                        <p class="muted">
                          Один артефакт: список широких тематических запусков анализа по рабочему ядру. Разные запуски
                          отличаются архивом чата, raw-run, версией ядра и временем запуска.
                        </p>
                      </div>
                      <md-outlined-button id="interest-analysis-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Почему запусков может быть несколько</strong>
                      <ul>
                        <li>Вы загрузили один и тот же чат повторно или другой архив чата.</li>
                        <li>Рабочее ядро изменилось после approve/reject кандидатов.</li>
                        <li>Анализ был запущен повторно для аудита или сравнения результата.</li>
                      </ul>
                    </div>
                    <div id="interest-analysis-runs" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/analyze/matches">Открыть тематические совпадения</a>
                    </div>
                    <p class="muted">По умолчанию используется последний успешный запуск анализа.</p>
                  </section>
    """


def _interest_context_analysis_matches_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Широкие совпадения</h3>
                        <p class="muted">
                          Один артефакт: сообщения, которые совпали с рабочим ядром интересов. Показ по 10 строк.
                        </p>
                      </div>
                      <md-outlined-button id="interest-analysis-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Как работает широкий тематический слой</strong>
                      <ul>
                        <li>Берется каждое сообщение из выбранного запуска анализа.</li>
                        <li>Текст сопоставляется с утвержденными элементами ядра: названиями, синонимами, сигналами и шумовыми словами.</li>
                        <li>Используются нормализованный текст и леммы, поэтому формы слов вроде "домофоны" и "домофон" должны связываться.</li>
                        <li>Это еще не лид. Это широкий тематический список сообщений, которые вообще относятся к интересам.</li>
                      </ul>
                    </div>
                    <div id="interest-analysis-matches" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-layers">Настроить слой намерений</a>
                    </div>
                    <p class="muted">Слой намерений сужает широкий тематический список до сообщений с нужным типом намерения.</p>
                  </section>
    """


def _interest_context_intent_layers_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Слой намерений</h3>
                        <p class="muted">
                          Один артефакт: настраиваемое правило второго слоя. Оно сужает широкий тематический список
                          до сообщений с нужным намерением.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Что означают условия</strong>
                      <ul>
                        <li>Включающие условия - признаки намерения: "ищу", "нужно", "подскажите", "купить", "сколько стоит". Без них сообщение обычно не считается запросом.</li>
                        <li>Контекстные условия - предметная область: камеры, домофон, умный дом, электрика, реле, датчики. Они проверяются по нормализованному тексту и леммам.</li>
                        <li>Исключающие условия - шум: вакансии, резюме, объявления "продам/отдам" и похожие нерелевантные сообщения.</li>
                        <li>Исключить элементы ядра - слишком общие элементы, которые дают много ложных совпадений.</li>
                        <li>Условия ниже - стартовая настройка системы, не LLM-магия. Их можно редактировать перед сохранением слоя.</li>
                      </ul>
                    </div>
                    <form id="interest-intent-layer-form" class="material-form single-column-form">
                      <md-outlined-text-field name="name" label="Название слоя" required
                        value="Намерение: запрос помощи, покупки или заказа">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="description" label="Описание" type="textarea"
                        value="Сообщение не просто касается ядра, а содержит явный запрос, вопрос, поиск исполнителя, цены, покупки или консультации.">
                      </md-outlined-text-field>
                      <label>
                        Включающие условия, по одному на строку
                        <textarea name="include_patterns" rows="7">ищу
ищем
нужно
нужен
подскажите
посоветуйте
помогите
где купить
где заказать
купить
заказать
поставить
установить
подключить
сколько стоит
кто может</textarea>
                      </label>
                      <label>
                        Контекстные условия, по одному на строку
                        <textarea name="context_patterns" rows="7">видеонаблюдение
камера
видеокамера
умный дом
home assistant
алиса
розетка
выключатель
реле
щит
электрика
проводка
датчик
протечка
подсветка
освещение
домофон
контроль доступа
сигнализация</textarea>
                      </label>
                      <label>
                        Исключающие леммы/слова, по одному на строку
                        <textarea name="exclude_lemmas" rows="5">вакансия
резюме
продам
продаю
отдам
аренда</textarea>
                      </label>
                      <label>
                        Исключающие фразы после нормализации, по одной на строку
                        <textarea name="exclude_phrases" rows="5">аренда рабочего места
ищу дизайнера
требуется дизайнер
в команду</textarea>
                      </label>
                      <label>
                        Семантические negative examples, по одному на строку
                        <textarea name="semantic_negative_examples" rows="4">нужно определить размер ниши
как лучше подсветить декоративную скалу
подскажите профиль для дизайнерского решения</textarea>
                      </label>
                      <label>
                        Advanced regex-исключения, по одному на строку
                        <textarea name="exclude_patterns" rows="5">вакансия
резюме
в команду
требуется дизайнер
ищу дизайнера
продам
продаю
отдам
аренда рабочего места</textarea>
                      </label>
                      <label>
                        Исключить элементы ядра, по одному на строку
                        <textarea name="exclude_core_names" rows="5">консультирование
клиенты
комплексное проектирование
детали_проекта
проектирование
смета
сроки_реализации</textarea>
                      </label>
                      <div class="form-grid">
                        <md-outlined-text-field name="min_score" label="Минимальный score" type="number" value="0.55" step="0.01">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="max_results" label="Максимум результатов" type="number" value="3000">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="broad_score_weight" label="Вес тематического слоя" type="number" value="0.45" step="0.01">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="intent_hit_weight" label="Вес одного намерения" type="number" value="0.18" step="0.01">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="semantic_negative_threshold" label="Порог semantic-negative" type="number" value="0.78" step="0.01">
                        </md-outlined-text-field>
                      </div>
                      <label class="material-checkbox-line">
                        <input name="require_include_match" type="checkbox" checked>
                        Требовать совпадение с включающим условием
                      </label>
                      <label class="material-checkbox-line">
                        <input name="require_context_match" type="checkbox">
                        Требовать совпадение с контекстным условием
                      </label>
                      <div class="button-row">
                        <md-filled-button type="submit">
                          <md-icon slot="icon">add</md-icon>
                          Добавить слой
                        </md-filled-button>
                      </div>
                    </form>
                    <p id="interest-intent-status" class="status-line" role="status"></p>
                    <div id="interest-intent-layers" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-runs">Открыть запуски намерений</a>
                    </div>
                    <p class="muted">После применения слоя откройте отдельный список запусков намерений.</p>
                  </section>
    """


def _interest_context_intent_runs_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Запуски слоя намерений</h3>
                        <p class="muted">
                          Один артефакт: история применений слоя намерений к широким тематическим запускам анализа.
                          Разные запуски могут отличаться слоем, тематическим запуском и настройками условий.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Почему запусков может быть несколько</strong>
                      <ul>
                        <li>Один слой применили к разным широким тематическим запускам анализа.</li>
                        <li>Слой изменили: условия, веса, минимальный score или лимит результатов.</li>
                        <li>Запуск повторили после изменения рабочего ядра.</li>
                      </ul>
                    </div>
                    <div id="interest-intent-runs" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-matches">Открыть сообщения намерений</a>
                    </div>
                    <p class="muted">По умолчанию используется последний успешный запуск слоя намерений.</p>
                  </section>
    """


def _interest_context_intent_matches_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Сообщения слоя намерений</h3>
                        <p class="muted">
                          Один артефакт: более узкий список сообщений с объяснением include/context/score.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div id="interest-intent-matches" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-review">Открыть разметку</a>
                    </div>
                    <p class="muted">На этой странице сообщения только просматриваются. Решение “правильное/неправильное” и комментарий записываются на отдельной странице разметки.</p>
                  </section>
    """


def _interest_context_project_opportunities_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Проектные возможности</h3>
                        <p class="muted">
                          Один артефакт: список сообщений из чата дизайнеров, где ПУР может практически помочь
                          оборудованием, инженерией, интеграцией или консультацией.
                        </p>
                      </div>
                      <md-outlined-button id="interest-project-opportunities-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Чем отличается от слоя намерений</strong>
                      <ul>
                        <li>Ищем не “хочу купить”, а проектный повод для ПУР: объект, заказчик, чертежи, инженерка, оборудование или интеграция.</li>
                        <li>Score разбит на части: тема, проектный контекст, применимость ПУР, коммерческий повод и дизайнерский шум.</li>
                        <li>Декоративные ниши, профили, раковины, мебель, визуализация и софт дизайнера отсекаются как нерелевантный профиль источника.</li>
                        <li>Результат сохраняется как обычный intent run, поэтому его можно размечать и дообучать через существующий feedback.</li>
                      </ul>
                    </div>
                    <div class="button-row">
                      <md-filled-button id="interest-project-opportunities-run" type="button">
                        <md-icon slot="icon">workspaces</md-icon>
                        Найти проектные возможности
                      </md-filled-button>
                    </div>
                    <p id="interest-project-opportunities-status" class="status-line" role="status"></p>
                    <section class="draft-review-section">
                      <div class="section-head compact-section-head">
                        <h4>1. Выберите широкий тематический запуск</h4>
                        <span class="muted">обычно это запуск по архиву чата дизайнеров</span>
                      </div>
                      <div id="interest-analysis-runs" class="draft-review-panel" aria-live="polite"></div>
                    </section>
                    <section class="draft-review-section">
                      <div class="section-head compact-section-head">
                        <h4>2. Запуски проектных возможностей</h4>
                        <span class="muted">отдельные результаты специального профиля</span>
                      </div>
                      <div id="interest-project-opportunities-runs" class="draft-review-panel" aria-live="polite"></div>
                    </section>
                    <section class="draft-review-section">
                      <div class="section-head compact-section-head">
                        <h4>3. Сообщения проектных возможностей</h4>
                        <span class="muted">по 10 сообщений на странице</span>
                      </div>
                      <div id="interest-project-opportunities-matches" class="draft-review-panel" aria-live="polite"></div>
                    </section>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-review">Открыть разметку</a>
                    </div>
                    <p class="muted">Проверяйте именно этот слой: “интересно ПУР / не интересно ПУР” с причиной.</p>
                  </section>
    """


def _interest_context_intent_review_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Ручная разметка</h3>
                        <p class="muted">
                          Один артефакт: операторская оценка сообщений намерений. Каждое сообщение можно
                          пометить как правильное или неправильное и оставить комментарий.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-review-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Как использовать</strong>
                      <ul>
                        <li>Правильное - сообщение действительно похоже на интересный запрос по ядру.</li>
                        <li>Неправильное - сообщение попало в намерения, но не подходит; комментарий объясняет почему.</li>
                        <li>Разметка не меняет слой сама. Она только готовит данные для следующей AI-валидации.</li>
                      </ul>
                    </div>
                    <div id="interest-intent-review" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-ai-validation">Запустить AI-валидацию</a>
                    </div>
                    <p class="muted">AI-валидация запускается только вручную, когда разметки достаточно.</p>
                  </section>
    """


def _interest_context_intent_ai_validation_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Запуск AI-валидации</h3>
                        <p class="muted">
                          Один артефакт: LLM-запуск, который получает ядро, текущий слой намерений,
                          объяснения попаданий и ручную разметку correct/incorrect.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-validation-runs-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <form id="interest-intent-validation-form" class="material-form single-column-form">
                      <div class="form-grid">
                        <md-outlined-text-field name="max_reviews" label="Сколько размеченных сообщений отдать модели" type="number" value="80">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="max_tokens" label="Max tokens ответа" type="number" value="4096">
                        </md-outlined-text-field>
                        <md-outlined-text-field name="temperature" label="Temperature" type="number" value="0" step="0.1">
                        </md-outlined-text-field>
                      </div>
                      <div class="button-row">
                        <md-filled-button type="submit">
                          <md-icon slot="icon">psychology</md-icon>
                          Сформировать рекомендации
                        </md-filled-button>
                      </div>
                    </form>
                    <p id="interest-intent-validation-status" class="status-line" role="status"></p>
                    <div id="interest-intent-validation-runs" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-ai-recommendations">Открыть рекомендации AI</a>
                    </div>
                    <p class="muted">После запуска разберите предложения постранично и одобрите только безопасные.</p>
                  </section>
    """


def _interest_context_intent_ai_recommendations_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Рекомендации AI</h3>
                        <p class="muted">
                          Один артефакт: предложения модели с локальным preview. Они ничего не меняют,
                          пока оператор их не одобрит.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-validation-recommendations-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div id="interest-intent-validation-recommendations" class="draft-review-panel" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/intent-ai-filter">Создать AI-фильтр</a>
                    </div>
                    <p class="muted">Новый слой создается только из рекомендаций со статусом “одобрено”.</p>
                  </section>
    """


def _interest_context_intent_ai_filter_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Создание AI-фильтра</h3>
                        <p class="muted">
                          Один артефакт: новый слой намерений, собранный из одобренных AI-рекомендаций.
                          Старый слой остается как источник и не перезаписывается.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-ai-filter-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Что делать на этой странице</strong>
                      <ul>
                        <li>Если рекомендации уже одобрены, сначала нажмите “Создать AI-фильтр”.</li>
                        <li>После создания появится следующий шаг: “Применить AI-фильтр к тем же сообщениям”.</li>
                        <li>После применения откройте “Сообщения намерений” и смотрите новый запуск.</li>
                      </ul>
                    </div>
                    <div id="interest-intent-ai-filter" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_intent_exclusions_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Применение исключений</h3>
                        <p class="muted">
                          Один артефакт: очередь feedback “Не интересно”. Здесь видно, что именно предлагается
                          добавить в исключающие условия и какие сообщения это зацепит.
                        </p>
                      </div>
                      <md-outlined-button id="interest-intent-exclusions-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <div class="explain-box">
                      <strong>Как применять безопасно</strong>
                      <ul>
                        <li>Сначала оператор нажимает “Не интересно” на конкретном сообщении слоя намерений.</li>
                        <li>Эта страница показывает impact preview: исчезнет ли целевое сообщение и сколько других сообщений уйдет вместе с ним.</li>
                        <li>Кнопка “Применить исключение” меняет настройки слоя намерений, но не переписывает старый запуск.</li>
                        <li>Чтобы увидеть новый результат, после применения перезапустите слой намерений.</li>
                      </ul>
                    </div>
                    <div id="interest-intent-exclusions" class="draft-review-panel" aria-live="polite"></div>
                  </section>
    """


def _interest_context_llm_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>Подключение LLM</h3>
                        <p class="muted">
                          Сейчас подключаем Z.AI для генерации брифа и следующих LLM-этапов ядра интересов.
                          Выбранная модель станет основным исполнителем `catalog_extractor / primary`.
                        </p>
                      </div>
                      <md-outlined-button id="interest-llm-refresh" type="button">
                        <md-icon slot="icon">refresh</md-icon>
                        Обновить
                      </md-outlined-button>
                    </div>
                    <form id="interest-llm-provider-form" class="material-form interest-llm-form">
                      <md-outlined-text-field name="display_name" label="Название" value="Z.AI">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="base_url" label="URL" required
                        value="https://api.z.ai/api/coding/paas/v4">
                      </md-outlined-text-field>
                      <md-outlined-text-field name="api_key" label="Token" type="password"
                        placeholder="z.ai API token">
                      </md-outlined-text-field>
                      <label class="material-select-field">
                        Модель
                        <input name="model" list="interest-llm-model-options" value="GLM-4-Plus" required>
                        <datalist id="interest-llm-model-options"></datalist>
                      </label>
                      <p class="muted form-help">
                        Token нужен для первого подключения или замены ключа. Если провайдер уже сохранен,
                        можно оставить token пустым и поменять только модель.
                      </p>
                      <md-filled-button type="submit">
                        <md-icon slot="icon">check_circle</md-icon>
                        Сохранить LLM
                      </md-filled-button>
                    </form>
                    <p id="interest-llm-status" class="status-line" role="status"></p>
                    <div id="interest-llm-provider-list" class="resource-list" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/brief">Открыть бриф</a>
                    </div>
                    <p class="muted">После подключения LLM сформируйте или вручную заполните бриф ядра интересов.</p>
                  </section>
    """


def _interest_context_brief_body() -> str:
    return """
                  <section class="detail-section">
                    <div class="section-head">
                      <div>
                        <h3>LLM-бриф ядра интересов</h3>
                        <p class="muted">
                          Один артефакт: редактируемый контекст для моделей. Он объясняет, что считать интересом,
                          поводом связаться и шумом.
                        </p>
                      </div>
                      <md-filled-tonal-button id="interest-core-brief-generate" type="button">
                        <md-icon slot="icon">model_training</md-icon>
                        Сформировать из источников
                      </md-filled-tonal-button>
                    </div>
                    <div class="explain-box">
                      <strong>Можно редактировать</strong>
                      <ul>
                        <li>Измените текст в поле "Бриф" и нажмите "Сохранить вручную".</li>
                        <li>Активная версия брифа влияет на следующие LLM-рекомендации по кандидатам.</li>
                        <li>Старые raw/parquet, кандидаты и уже принятые элементы ядра не переписываются автоматически.</li>
                      </ul>
                    </div>
                    <form id="interest-core-brief-form" class="material-form single-column-form">
                      <md-outlined-text-field id="interest-core-brief-text" name="brief_text"
                        label="Бриф" type="textarea"
                        placeholder="Например: ПУР занимается умным домом, видеонаблюдением, щитовым оборудованием...">
                      </md-outlined-text-field>
                      <div class="button-row">
                        <md-filled-button type="submit">
                          <md-icon slot="icon">check_circle</md-icon>
                          Сохранить вручную
                        </md-filled-button>
                      </div>
                    </form>
                    <div id="interest-core-brief-progress" class="prepare-progress-panel" aria-live="polite"></div>
                    <div id="interest-core-brief-list" class="brief-list" aria-live="polite"></div>
                  </section>
                  <section class="detail-section">
                    <div class="section-head">
                      <h3>Следующий шаг</h3>
                      <a class="interest-next-link" href="/interest-contexts/core">Собрать ядро</a>
                    </div>
                    <p class="muted">Бриф используется при LLM-рекомендациях и должен быть понятен оператору.</p>
                  </section>
    """


def _interest_context_stage_panel(active_step: str) -> str:
    step_rows = "".join(
        f"""<a class="table-row linked-row {"is-active" if step == active_step else ""}" data-interest-step-link="{step}" href="{path}">
                        <div><strong>{label}</strong><p class="muted">{_interest_context_stage_hint(step)}</p></div>
                        <span>{index}</span>
                      </a>"""
        for index, (step, path, label) in enumerate(_INTEREST_CONTEXT_STEPS, start=1)
    )
    return f"""
                <aside class="side-pane operations-signals interest-stage-panel" aria-label="Сценарий">
                  <section>
                    <h2>Сценарий</h2>
                    <p class="muted">
                      Идем последовательно: контекст, источник, raw, подготовка, ядро, анализ и намерения.
                    </p>
                  </section>
                  <section>
                    <div class="table-list scenario-step-list">
                      {step_rows}
                    </div>
                  </section>
                </aside>
    """


def _interest_context_stage_hint(step: str) -> str:
    return {
        "context": "создать и выбрать",
        "load_archive": "ZIP источника интересов",
        "load_link": "канал или чат по ссылке",
        "check": "raw/parquet, вложения, примеры",
        "prepare": "нормализация, индекс, сущности",
        "prepare_texts": "raw/clean/tokens/POS",
        "prepare_search_fts": "PostgreSQL full-text",
        "prepare_search_chroma": "семантический индекс",
        "prepare_features": "детерминированные признаки",
        "prepare_aggregates": "n-граммы и счетчики",
        "prepare_entities": "POS-сущности и ranking",
        "llm": "провайдер и модель",
        "brief": "контекст для модели",
        "core": "запуск и статус ядра",
        "candidates": "rule-based список по страницам",
        "reviews": "проверка LLM-рекомендаций",
        "items": "утвержденное ядро",
        "analysis_upload": "ZIP чата для проверки",
        "analysis_runs": "запуски тематического слоя",
        "analysis_matches": "сообщения тематического слоя",
        "intent_layers": "настройка фильтра",
        "intent_runs": "запуски фильтра",
        "intent_matches": "сообщения с намерением",
        "project_opportunities": "проектная применимость",
        "intent_review": "ручная проверка",
        "intent_ai_validation": "запуск по запросу",
        "intent_ai_recommendations": "одобрение предложений",
        "intent_ai_filter": "новый слой",
        "intent_exclusions": "feedback и влияние",
    }[step]


@router.get("/interest-contexts/{context_id}/draft", response_class=HTMLResponse)
def interest_context_draft_page(
    context_id: str,
    request: Request,
    auth_service: WebAuthService = Depends(get_auth_service),
) -> Response:
    if not _has_page_session(request, auth_service):
        return RedirectResponse("/login", status_code=303)
    context = InterestContextService(auth_service.session).repository.get(context_id)
    context_title = context.name if context is not None else "Ядро интересов"
    return HTMLResponse(
        _page(
            page="interest-context-draft",
            title=f"Кандидаты - {context_title}",
            main=f"""
            <main class="workspace resources-workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Кандидаты ядра интересов</h1>
                </div>
                <nav>
                  <a href="/interest-contexts">Ядро интересов</a>
                  <md-outlined-button id="logout-button" type="button">Выйти</md-outlined-button>
                </nav>
              </header>
              <section class="draft-screen-shell">
                <header class="detail-header">
                  <div>
                    <h2>{escape(context_title)}</h2>
                    <p class="muted">
                      Все кандидаты показываются для ручного ревью. На этом этапе AI не используется.
                    </p>
                  </div>
                  <div class="button-row">
                    <md-outlined-button type="button" onclick="window.location.assign('/interest-contexts')">
                      Назад к контекстам
                    </md-outlined-button>
                    <md-filled-tonal-button id="interest-context-draft-refresh" type="button">
                      <md-icon slot="icon">refresh</md-icon>
                      Обновить
                    </md-filled-tonal-button>
                  </div>
                </header>
                <div id="interest-context-draft-screen"
                  data-context-id="{escape(context_id)}"
                  class="draft-review-panel"
                  aria-live="polite">
                  <div class="empty-state">Загружаю кандидатов...</div>
                </div>
              </section>
            </main>
            """,
        )
    )


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


ASSET_VERSION = "20260506-large-archive-jobs"


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
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined&amp;icon_names=add,archive,article,auto_fix_high,check_circle,close,database,description,folder,forum,hub,model_training,open_in_new,person,person_add,radio_button_unchecked,refresh,search,send,settings,smart_toy,storage,table_chart,upload_file,vpn_key&amp;display=block">
  <link rel="stylesheet" href="/static/app.css?v={ASSET_VERSION}">
</head>
<body data-page="{page}">
  {main}
  <script type="module" src="/static/vendor/material-web.js"></script>
  <script src="/static/app.js?v={ASSET_VERSION}" defer></script>
</body>
</html>"""
