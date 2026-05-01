import json
from pathlib import Path

from fastapi.testclient import TestClient

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.services.web_auth import WebAuthService
from pur_leads.db.session import create_session_factory
from pur_leads.web.app import create_app


def test_login_page_and_static_assets_are_served(tmp_path):
    client = _client(tmp_path)

    login_response = client.get("/login")
    css_response = client.get("/static/app.css")
    js_response = client.get("/static/app.js")
    material_response = client.get("/static/vendor/material-web.js")

    assert login_response.status_code == 200
    assert 'data-page="login"' in login_response.text
    assert 'id="local-login-form"' in login_response.text
    assert 'id="change-password-form"' in login_response.text
    assert 'class="material-auth-shell"' in login_response.text
    assert '<md-outlined-text-field name="username"' in login_response.text
    assert '<md-outlined-text-field name="password"' in login_response.text
    assert '<md-filled-button type="submit">Войти</md-filled-button>' in login_response.text
    assert (
        '<md-filled-button type="submit">Сохранить пароль</md-filled-button>' in login_response.text
    )
    assert "Вход оператора" in login_response.text
    assert "Сменить пароль" in login_response.text
    assert "/static/app.css" in login_response.text
    assert "/static/app.js" in login_response.text
    assert '<link rel="icon" href="data:,">' in login_response.text
    assert "Noto+Sans" in login_response.text
    assert "Roboto" not in login_response.text
    assert "Material+Symbols+Outlined" in login_response.text
    assert "icon_names=add,article,check_circle,close,database,description,folder" in login_response.text
    assert "forum,model_training" in login_response.text
    assert 'type="module" src="/static/vendor/material-web.js"' in login_response.text
    assert css_response.status_code == 200
    assert "grid-template-columns" in css_response.text
    assert "--md-ref-typeface-brand: var(--ui-font);" in css_response.text
    assert "width: min(440px, 100%);" in css_response.text
    assert js_response.status_code == 200
    assert material_response.status_code == 200
    assert "customElements" in material_response.text
    package = json.loads(Path("package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["@material/web"] == "2.4.1"
    assert "bootstrap" not in package.get("dependencies", {})
    assert "auto_pending" in js_response.text
    assert "crm_candidate_count" in js_response.text
    assert "classifier_version_id" in js_response.text
    assert "response.status === 401" in js_response.text
    assert "response.status === 403" in js_response.text
    assert "state.items.some" in js_response.text
    assert "message_url" in js_response.text
    assert "primary_sender_name" in js_response.text
    assert "work_outcome" in js_response.text
    assert "primary_task_id" in js_response.text
    assert "pagination.has_more" in js_response.text
    assert "must_change_password" in js_response.text
    assert "/api/auth/change-password" in js_response.text


def test_workspace_admin_sections_are_protected_and_render_shells(tmp_path):
    client = _client(tmp_path)

    workspace_denied = client.get("/", follow_redirects=False)
    crm_denied = client.get("/crm", follow_redirects=False)
    sources_denied = client.get("/sources", follow_redirects=False)
    resources_denied = client.get("/resources", follow_redirects=False)
    users_denied = client.get("/users", follow_redirects=False)
    settings_denied = client.get("/settings", follow_redirects=False)
    ai_registry_denied = client.get("/ai-registry", follow_redirects=False)
    task_executors_denied = client.get("/task-executors", follow_redirects=False)
    task_types_denied = client.get("/task-types", follow_redirects=False)
    catalog_denied = client.get("/catalog", follow_redirects=False)
    today_denied = client.get("/today", follow_redirects=False)
    artifacts_denied = client.get("/artifacts", follow_redirects=False)
    operations_denied = client.get("/operations", follow_redirects=False)
    quality_denied = client.get("/quality", follow_redirects=False)
    _login(client)
    workspace_response = client.get("/")
    crm_response = client.get("/crm")
    sources_response = client.get("/sources")
    resources_response = client.get("/resources")
    users_response = client.get("/users")
    settings_response = client.get("/settings")
    ai_registry_response = client.get("/ai-registry")
    task_executors_response = client.get("/task-executors")
    task_types_response = client.get("/task-types")
    admin_redirect = client.get("/admin", follow_redirects=False)
    onboarding_redirect = client.get("/onboarding", follow_redirects=False)
    catalog_response = client.get("/catalog")
    today_response = client.get("/today")
    artifacts_response = client.get("/artifacts")
    operations_response = client.get("/operations")
    quality_response = client.get("/quality")
    js_response = client.get("/static/app.js")

    assert workspace_denied.status_code == 303
    assert workspace_denied.headers["location"] == "/login"
    assert crm_denied.status_code == 303
    assert crm_denied.headers["location"] == "/login"
    assert sources_denied.status_code == 303
    assert sources_denied.headers["location"] == "/login"
    assert resources_denied.status_code == 303
    assert resources_denied.headers["location"] == "/login"
    assert users_denied.status_code == 303
    assert users_denied.headers["location"] == "/login"
    assert settings_denied.status_code == 303
    assert settings_denied.headers["location"] == "/login"
    assert ai_registry_denied.status_code == 303
    assert ai_registry_denied.headers["location"] == "/login"
    assert task_executors_denied.status_code == 303
    assert task_executors_denied.headers["location"] == "/login"
    assert task_types_denied.status_code == 303
    assert task_types_denied.headers["location"] == "/login"
    assert catalog_denied.status_code == 303
    assert catalog_denied.headers["location"] == "/login"
    assert today_denied.status_code == 303
    assert today_denied.headers["location"] == "/login"
    assert artifacts_denied.status_code == 303
    assert artifacts_denied.headers["location"] == "/login"
    assert operations_denied.status_code == 303
    assert operations_denied.headers["location"] == "/login"
    assert quality_denied.status_code == 303
    assert quality_denied.headers["location"] == "/login"
    assert workspace_response.status_code == 200
    assert 'data-page="leads-inbox"' in workspace_response.text
    assert '<a href="/today">Сегодня</a>' in workspace_response.text
    assert '<a href="/sources">Источники</a>' in workspace_response.text
    assert '<a href="/resources">Ресурсы</a>' in workspace_response.text
    assert '<a href="/catalog">Каталог</a>' in workspace_response.text
    assert '<a href="/crm">CRM</a>' in workspace_response.text
    assert '<a href="/users">Пользователи</a>' in workspace_response.text
    assert '<a href="/settings">Настройки</a>' in workspace_response.text
    assert '<a href="/ai-registry">AI-реестр</a>' in workspace_response.text
    assert '<a href="/task-executors">Исполнители задач</a>' in workspace_response.text
    assert '<a href="/task-types">Задачи</a>' in workspace_response.text
    assert '<a href="/quality">Качество</a>' in workspace_response.text
    assert '<a href="/artifacts">Артефакты</a>' in workspace_response.text
    assert '<a href="/operations">Операции</a>' in workspace_response.text
    assert '<a href="/onboarding">Онбординг</a>' not in workspace_response.text
    assert '<a href="/admin">Админка</a>' not in workspace_response.text
    assert 'id="lead-queue"' in workspace_response.text
    assert 'id="lead-load-more"' in workspace_response.text
    assert 'id="lead-detail"' in workspace_response.text
    assert 'data-field="auto_pending"' in workspace_response.text
    assert 'data-field="retro"' in workspace_response.text
    assert 'data-field="maybe"' in workspace_response.text
    assert admin_redirect.status_code == 303
    assert admin_redirect.headers["location"] == "/users"
    assert onboarding_redirect.status_code == 303
    assert onboarding_redirect.headers["location"] == "/resources"
    assert resources_response.status_code == 200
    assert 'data-page="resources"' in resources_response.text
    assert "Ресурсы системы" in resources_response.text
    assert 'id="onboarding-add-resource"' in resources_response.text
    assert 'id="onboarding-resource-dialog"' in resources_response.text
    assert 'id="onboarding-resource-list"' in resources_response.text
    assert "Онбординг" not in resources_response.text
    assert "Юзербот через файл сессии" not in resources_response.text
    assert "onboarding-material-shell" not in resources_response.text
    assert '<md-outlined-text-field name="token"' in resources_response.text
    assert (
        '<md-filled-button id="onboarding-group-discover" type="button" disabled>'
        in resources_response.text
    )
    assert 'id="onboarding-group-hint"' in resources_response.text
    assert '<md-checkbox name="make_default" checked' in resources_response.text
    assert 'id="onboarding-session-form"' not in resources_response.text
    assert 'id="onboarding-llm-model-form"' not in resources_response.text
    assert "https://web.telegram.org/k/" in resources_response.text
    assert "https://my.telegram.org/auth?to=apps" in resources_response.text
    assert users_response.status_code == 200
    assert 'data-page="users"' in users_response.text
    assert 'id="telegram-admin-form"' in users_response.text
    assert 'id="admin-users"' in users_response.text
    assert "Добавить администратора" in users_response.text
    assert settings_response.status_code == 200
    assert 'data-page="settings"' in settings_response.text
    assert 'id="setting-form"' in settings_response.text
    assert 'id="settings-list"' in settings_response.text
    assert "Как настройка влияет на работу" in settings_response.text
    assert ai_registry_response.status_code == 200
    assert 'data-page="ai-registry"' in ai_registry_response.text
    assert 'id="ai-registry-bootstrap"' in ai_registry_response.text
    assert 'id="ai-models"' in ai_registry_response.text
    assert 'id="ai-profile-form"' in ai_registry_response.text
    assert 'id="ai-model-profiles"' in ai_registry_response.text
    assert "Контекстное окно" in ai_registry_response.text
    assert "Профили моделей" in ai_registry_response.text
    assert task_executors_response.status_code == 200
    assert 'data-page="task-executors"' in task_executors_response.text
    assert 'id="ai-route-form"' in task_executors_response.text
    assert 'id="ai-routes"' in task_executors_response.text
    assert 'select name="profile_id"' in task_executors_response.text
    assert 'select name="model_id"' not in task_executors_response.text
    assert "Исполнители задач" in task_executors_response.text
    assert "Связка: тип задачи + ресурс + профиль модели" in task_executors_response.text
    assert task_types_response.status_code == 200
    assert 'data-page="task-types"' in task_types_response.text
    assert 'id="task-type-list"' in task_types_response.text
    assert "poll_monitored_source" in task_types_response.text
    assert crm_response.status_code == 200
    assert 'data-page="crm"' in crm_response.text
    assert '<a href="/today">Сегодня</a>' in crm_response.text
    assert '<a href="/sources">Источники</a>' in crm_response.text
    assert '<a href="/catalog">Каталог</a>' in crm_response.text
    assert '<a href="/quality">Качество</a>' in crm_response.text
    assert 'id="crm-client-list"' in crm_response.text
    assert 'id="crm-client-form"' in crm_response.text
    assert sources_response.status_code == 200
    assert 'data-page="sources"' in sources_response.text
    assert 'id="source-list"' in sources_response.text
    assert 'id="source-form"' in sources_response.text
    assert 'name="start_recent_days"' in sources_response.text
    assert 'id="source-detail"' in sources_response.text
    assert catalog_response.status_code == 200
    assert 'data-page="catalog"' in catalog_response.text
    assert 'id="catalog-item-form"' in catalog_response.text
    assert 'id="catalog-item-list"' in catalog_response.text
    assert 'id="catalog-item-detail"' in catalog_response.text
    assert 'id="catalog-snapshot-rebuild"' in catalog_response.text
    assert "Ручной каталог" in catalog_response.text
    assert "Канонические сущности, термины, признаки и условия." in catalog_response.text
    assert '<option value="item">Сущности</option>' in catalog_response.text
    assert "Что это за сущность, когда она релевантна и как ее распознавать" in (
        catalog_response.text
    )
    assert "Каноническое имя: коротко, конкретно и без лишних слов." in catalog_response.text
    assert "Тип определяет роль сущности в базе знаний и влияет на будущие промпты." in (
        catalog_response.text
    )
    assert "Сырой текст, ссылка или пример сохраняются как источник для обучения и аудита." in (
        catalog_response.text
    )
    assert "Автоизвлечение запускает AI-разбор только после сохранения сырого источника." in (
        catalog_response.text
    )
    assert "Пример: Камеры Dahua" in catalog_response.text
    assert "Порядок работы: источник → кандидат → подтверждение → снапшот → совпадение в чате." in (
        catalog_response.text
    )
    assert "Ключевые слова дают fuzzy match, признаки запроса повышают уверенность, исключающие признаки снижают ее." in (
        catalog_response.text
    )
    assert "Что продаем" not in catalog_response.text
    assert "Канонические товары, услуги, термины и офферы." not in catalog_response.text
    assert "AI-кандидаты" in catalog_response.text
    assert "Сырой ингест" in catalog_response.text
    assert 'id="catalog-raw-summary"' in catalog_response.text
    assert 'id="catalog-raw-message-list"' in catalog_response.text
    assert 'id="catalog-raw-message-detail"' in catalog_response.text
    assert 'id="catalog-candidate-list"' in catalog_response.text
    assert 'id="catalog-candidate-detail"' in catalog_response.text
    assert 'id="catalog-filters"' in catalog_response.text
    assert 'id="catalog-edit-form"' in catalog_response.text
    assert 'id="catalog-name-input"' in catalog_response.text
    assert 'id="catalog-value-json"' in catalog_response.text
    assert '<option value="maybe_example">Пример maybe</option>' in catalog_response.text
    assert today_response.status_code == 200
    assert 'data-page="today"' in today_response.text
    assert 'id="today-summary"' in today_response.text
    assert 'id="today-leads"' in today_response.text
    assert 'id="today-tasks"' in today_response.text
    assert 'id="today-task-form"' in today_response.text
    assert 'id="today-contact-reasons"' in today_response.text
    assert 'id="today-support-cases"' in today_response.text
    assert 'id="today-catalog-candidates"' in today_response.text
    assert 'id="today-operational-issues"' in today_response.text
    assert artifacts_response.status_code == 200
    assert 'data-page="artifacts"' in artifacts_response.text
    assert 'id="artifact-summary"' in artifacts_response.text
    assert 'id="artifact-filters"' in artifacts_response.text
    assert 'id="artifact-list"' in artifacts_response.text
    assert 'id="artifact-detail"' in artifacts_response.text
    assert operations_response.status_code == 200
    assert 'data-page="operations"' in operations_response.text
    assert 'id="operations-summary"' in operations_response.text
    assert 'id="operations-jobs"' in operations_response.text
    assert 'id="operations-detail"' in operations_response.text
    assert 'id="operations-events"' in operations_response.text
    assert 'id="operations-notifications"' in operations_response.text
    assert 'id="operations-extraction-runs"' in operations_response.text
    assert 'id="operations-access-checks"' in operations_response.text
    assert 'id="operations-backups"' in operations_response.text
    assert 'id="operations-restores"' in operations_response.text
    assert 'id="operations-backup-create"' in operations_response.text
    assert 'id="operations-audit"' in operations_response.text
    assert quality_response.status_code == 200
    assert 'data-page="quality"' in quality_response.text
    assert 'id="quality-summary"' in quality_response.text
    assert 'id="quality-datasets"' in quality_response.text
    assert 'id="quality-runs"' in quality_response.text
    assert 'id="quality-failed-results"' in quality_response.text
    assert "/api/crm/clients" in js_response.text
    assert "/crm/convert" in js_response.text
    assert "/api/sources" in js_response.text
    assert "/api/onboarding/resources" in js_response.text
    assert "setOnboardingGroupDiscoverEnabled" in js_response.text
    assert "/api/onboarding/bot-token" in js_response.text
    assert "/api/onboarding/userbots/session-file" not in js_response.text
    assert "/api/onboarding/llm-provider" in js_response.text
    assert "/api/onboarding/llm-default-model" not in js_response.text
    assert "populateOnboardingLlmModels" not in js_response.text
    assert "/api/onboarding/userbots/interactive/start" in js_response.text
    assert "/api/onboarding/userbots/interactive/complete" in js_response.text
    assert "/api/catalog/candidates" in js_response.text
    assert "/api/catalog/items" in js_response.text
    assert "/api/catalog/raw-ingest" in js_response.text
    assert "/api/catalog/snapshots/rebuild" in js_response.text
    assert "loadCatalogRawIngest" in js_response.text
    assert "submitCatalogItem" in js_response.text
    assert "Условия и действия" in js_response.text
    assert "Статус определяет, участвует ли сущность в текущем источнике истины." in (
        js_response.text
    )
    assert "Вес: насколько сильно термин влияет на fuzzy match и будущие правила." in (
        js_response.text
    )
    assert "JSON-данные должны оставаться валидным JSON." in js_response.text
    assert "Параметры: срок, цена, доступность, ограничение или другое уточнение." in (
        js_response.text
    )
    assert "Офферов нет" not in js_response.text
    assert "Цена/условия" not in js_response.text
    assert "оценочный кейс" in js_response.text
    assert "/api/operations/summary" in js_response.text
    assert "/api/artifacts" in js_response.text
    assert "/api/quality/summary" in js_response.text
    assert "/api/operations/extraction-runs" in js_response.text
    assert "/api/operations/backups" in js_response.text
    assert "/api/today" in js_response.text
    assert "limit: String(state.limit)" in js_response.text
    assert "offset: String(state.offset)" in js_response.text
    assert "loadCatalogCandidateDetail" in js_response.text
    assert "initOperations" in js_response.text
    assert "initArtifacts" in js_response.text
    assert "initQuality" in js_response.text
    assert "initToday" in js_response.text
    assert "initResources" in js_response.text
    assert "initTaskExecutors" in js_response.text
    assert "initTaskTypes" in js_response.text
    assert 'window.location.assign("/")' in js_response.text
    assert 'method: "PATCH"' in js_response.text
    assert "/api/admin/userbots" in js_response.text
    assert "/api/admin/ai-registry/bootstrap-defaults" in js_response.text
    assert "/api/admin/ai-models/" in js_response.text
    assert "/api/admin/ai-model-profiles/" in js_response.text
    assert 'profile_id: data.get("profile_id")' in js_response.text
    assert 'account_id: data.get("account_id")' in js_response.text


def _client(tmp_path) -> TestClient:
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        WebAuthService(session, telegram_bot_token="telegram-token").ensure_bootstrap_admin(
            username="admin",
            password="initial-secret",
        )
    return TestClient(
        create_app(
            database_path=db_path,
            bootstrap_admin_password="initial-secret",
            bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
            telegram_bot_token="telegram-token",
        )
    )


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200
