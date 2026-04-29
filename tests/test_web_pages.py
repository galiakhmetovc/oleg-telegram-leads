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


def test_workspace_and_admin_pages_are_protected_and_render_shells(tmp_path):
    client = _client(tmp_path)

    workspace_denied = client.get("/", follow_redirects=False)
    admin_denied = client.get("/admin", follow_redirects=False)
    crm_denied = client.get("/crm", follow_redirects=False)
    sources_denied = client.get("/sources", follow_redirects=False)
    catalog_denied = client.get("/catalog", follow_redirects=False)
    operations_denied = client.get("/operations", follow_redirects=False)
    _login(client)
    workspace_response = client.get("/")
    admin_response = client.get("/admin")
    crm_response = client.get("/crm")
    sources_response = client.get("/sources")
    catalog_response = client.get("/catalog")
    operations_response = client.get("/operations")
    js_response = client.get("/static/app.js")

    assert workspace_denied.status_code == 303
    assert workspace_denied.headers["location"] == "/login"
    assert admin_denied.status_code == 303
    assert admin_denied.headers["location"] == "/login"
    assert crm_denied.status_code == 303
    assert crm_denied.headers["location"] == "/login"
    assert sources_denied.status_code == 303
    assert sources_denied.headers["location"] == "/login"
    assert catalog_denied.status_code == 303
    assert catalog_denied.headers["location"] == "/login"
    assert operations_denied.status_code == 303
    assert operations_denied.headers["location"] == "/login"
    assert workspace_response.status_code == 200
    assert 'data-page="leads-inbox"' in workspace_response.text
    assert '<a href="/sources">Sources</a>' in workspace_response.text
    assert '<a href="/catalog">Catalog</a>' in workspace_response.text
    assert '<a href="/crm">CRM</a>' in workspace_response.text
    assert '<a href="/operations">Operations</a>' in workspace_response.text
    assert 'id="lead-queue"' in workspace_response.text
    assert 'id="lead-detail"' in workspace_response.text
    assert 'data-field="auto_pending"' in workspace_response.text
    assert 'data-field="retro"' in workspace_response.text
    assert 'data-field="maybe"' in workspace_response.text
    assert admin_response.status_code == 200
    assert 'data-page="admin"' in admin_response.text
    assert '<a href="/sources">Sources</a>' in admin_response.text
    assert '<a href="/catalog">Catalog</a>' in admin_response.text
    assert '<a href="/crm">CRM</a>' in admin_response.text
    assert 'id="admin-users"' in admin_response.text
    assert 'id="userbot-form"' in admin_response.text
    assert 'id="userbot-accounts"' in admin_response.text
    assert 'id="settings-list"' in admin_response.text
    assert crm_response.status_code == 200
    assert 'data-page="crm"' in crm_response.text
    assert '<a href="/sources">Sources</a>' in crm_response.text
    assert '<a href="/catalog">Catalog</a>' in crm_response.text
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
    assert 'id="catalog-candidate-list"' in catalog_response.text
    assert 'id="catalog-candidate-detail"' in catalog_response.text
    assert 'id="catalog-filters"' in catalog_response.text
    assert 'id="catalog-edit-form"' in catalog_response.text
    assert 'id="catalog-name-input"' in catalog_response.text
    assert 'id="catalog-value-json"' in catalog_response.text
    assert operations_response.status_code == 200
    assert 'data-page="operations"' in operations_response.text
    assert 'id="operations-summary"' in operations_response.text
    assert 'id="operations-jobs"' in operations_response.text
    assert 'id="operations-detail"' in operations_response.text
    assert 'id="operations-events"' in operations_response.text
    assert 'id="operations-notifications"' in operations_response.text
    assert 'id="operations-audit"' in operations_response.text
    assert "/api/crm/clients" in js_response.text
    assert "/crm/convert" in js_response.text
    assert "/api/sources" in js_response.text
    assert "/api/catalog/candidates" in js_response.text
    assert "/api/operations/summary" in js_response.text
    assert "loadCatalogCandidateDetail" in js_response.text
    assert "initOperations" in js_response.text
    assert 'method: "PATCH"' in js_response.text
    assert "/api/admin/userbots" in js_response.text


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
    return TestClient(create_app(database_path=db_path, telegram_bot_token="telegram-token"))


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/local",
        json={"username": "admin", "password": "initial-secret"},
    )
    assert response.status_code == 200
