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

    assert login_response.status_code == 200
    assert 'data-page="login"' in login_response.text
    assert 'id="local-login-form"' in login_response.text
    assert 'id="change-password-form"' in login_response.text
    assert "Вход оператора" in login_response.text
    assert "Сменить пароль" in login_response.text
    assert "/static/app.css" in login_response.text
    assert "/static/app.js" in login_response.text
    assert css_response.status_code == 200
    assert "grid-template-columns" in css_response.text
    assert js_response.status_code == 200
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


def test_workspace_and_admin_pages_are_protected_and_render_shells(tmp_path):
    client = _client(tmp_path)

    workspace_denied = client.get("/", follow_redirects=False)
    admin_denied = client.get("/admin", follow_redirects=False)
    crm_denied = client.get("/crm", follow_redirects=False)
    sources_denied = client.get("/sources", follow_redirects=False)
    onboarding_denied = client.get("/onboarding", follow_redirects=False)
    catalog_denied = client.get("/catalog", follow_redirects=False)
    today_denied = client.get("/today", follow_redirects=False)
    operations_denied = client.get("/operations", follow_redirects=False)
    quality_denied = client.get("/quality", follow_redirects=False)
    _login(client)
    workspace_response = client.get("/")
    admin_response = client.get("/admin")
    crm_response = client.get("/crm")
    sources_response = client.get("/sources")
    onboarding_response = client.get("/onboarding")
    catalog_response = client.get("/catalog")
    today_response = client.get("/today")
    operations_response = client.get("/operations")
    quality_response = client.get("/quality")
    js_response = client.get("/static/app.js")

    assert workspace_denied.status_code == 303
    assert workspace_denied.headers["location"] == "/login"
    assert admin_denied.status_code == 303
    assert admin_denied.headers["location"] == "/login"
    assert crm_denied.status_code == 303
    assert crm_denied.headers["location"] == "/login"
    assert sources_denied.status_code == 303
    assert sources_denied.headers["location"] == "/login"
    assert onboarding_denied.status_code == 303
    assert onboarding_denied.headers["location"] == "/login"
    assert catalog_denied.status_code == 303
    assert catalog_denied.headers["location"] == "/login"
    assert today_denied.status_code == 303
    assert today_denied.headers["location"] == "/login"
    assert operations_denied.status_code == 303
    assert operations_denied.headers["location"] == "/login"
    assert quality_denied.status_code == 303
    assert quality_denied.headers["location"] == "/login"
    assert workspace_response.status_code == 200
    assert 'data-page="leads-inbox"' in workspace_response.text
    assert '<a href="/today">Сегодня</a>' in workspace_response.text
    assert '<a href="/sources">Источники</a>' in workspace_response.text
    assert '<a href="/catalog">Каталог</a>' in workspace_response.text
    assert '<a href="/crm">CRM</a>' in workspace_response.text
    assert '<a href="/quality">Качество</a>' in workspace_response.text
    assert '<a href="/operations">Операции</a>' in workspace_response.text
    assert 'id="lead-queue"' in workspace_response.text
    assert 'id="lead-load-more"' in workspace_response.text
    assert 'id="lead-detail"' in workspace_response.text
    assert 'data-field="auto_pending"' in workspace_response.text
    assert 'data-field="retro"' in workspace_response.text
    assert 'data-field="maybe"' in workspace_response.text
    assert admin_response.status_code == 200
    assert 'data-page="admin"' in admin_response.text
    assert '<a href="/today">Сегодня</a>' in admin_response.text
    assert '<a href="/sources">Источники</a>' in admin_response.text
    assert '<a href="/catalog">Каталог</a>' in admin_response.text
    assert '<a href="/crm">CRM</a>' in admin_response.text
    assert '<a href="/quality">Качество</a>' in admin_response.text
    assert 'id="admin-users"' in admin_response.text
    assert 'id="userbot-form"' in admin_response.text
    assert 'id="userbot-accounts"' in admin_response.text
    assert 'id="settings-list"' in admin_response.text
    assert 'id="ai-registry-bootstrap"' in admin_response.text
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
    assert onboarding_response.status_code == 200
    assert 'data-page="onboarding"' in onboarding_response.text
    assert "Онбординг" in onboarding_response.text
    assert "Обычный Telegram-бот" in onboarding_response.text
    assert "Группа уведомлений" in onboarding_response.text
    assert "Юзербот" in onboarding_response.text
    assert 'id="onboarding-bot-form"' in onboarding_response.text
    assert 'id="onboarding-group-discover"' in onboarding_response.text
    assert 'id="onboarding-session-form"' in onboarding_response.text
    assert 'id="onboarding-interactive-start-form"' in onboarding_response.text
    assert catalog_response.status_code == 200
    assert 'data-page="catalog"' in catalog_response.text
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
    assert "/api/onboarding/status" in js_response.text
    assert "/api/onboarding/bot-token" in js_response.text
    assert "/api/onboarding/userbots/session-file" in js_response.text
    assert "/api/onboarding/userbots/interactive/start" in js_response.text
    assert "/api/onboarding/userbots/interactive/complete" in js_response.text
    assert "/api/catalog/candidates" in js_response.text
    assert "оценочный кейс" in js_response.text
    assert "/api/operations/summary" in js_response.text
    assert "/api/quality/summary" in js_response.text
    assert "/api/operations/extraction-runs" in js_response.text
    assert "/api/operations/backups" in js_response.text
    assert "/api/today" in js_response.text
    assert "limit: String(state.limit)" in js_response.text
    assert "offset: String(state.offset)" in js_response.text
    assert "loadCatalogCandidateDetail" in js_response.text
    assert "initOperations" in js_response.text
    assert "initQuality" in js_response.text
    assert "initToday" in js_response.text
    assert 'method: "PATCH"' in js_response.text
    assert "/api/admin/userbots" in js_response.text
    assert "/api/admin/ai-registry/bootstrap-defaults" in js_response.text


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
