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
    _login(client)
    workspace_response = client.get("/")
    admin_response = client.get("/admin")
    crm_response = client.get("/crm")
    js_response = client.get("/static/app.js")

    assert workspace_denied.status_code == 303
    assert workspace_denied.headers["location"] == "/login"
    assert admin_denied.status_code == 303
    assert admin_denied.headers["location"] == "/login"
    assert crm_denied.status_code == 303
    assert crm_denied.headers["location"] == "/login"
    assert workspace_response.status_code == 200
    assert 'data-page="leads-inbox"' in workspace_response.text
    assert '<a href="/crm">CRM</a>' in workspace_response.text
    assert 'id="lead-queue"' in workspace_response.text
    assert 'id="lead-detail"' in workspace_response.text
    assert 'data-field="auto_pending"' in workspace_response.text
    assert 'data-field="retro"' in workspace_response.text
    assert 'data-field="maybe"' in workspace_response.text
    assert admin_response.status_code == 200
    assert 'data-page="admin"' in admin_response.text
    assert '<a href="/crm">CRM</a>' in admin_response.text
    assert 'id="admin-users"' in admin_response.text
    assert 'id="settings-list"' in admin_response.text
    assert crm_response.status_code == 200
    assert 'data-page="crm"' in crm_response.text
    assert 'id="crm-client-list"' in crm_response.text
    assert 'id="crm-client-form"' in crm_response.text
    assert "/api/crm/clients" in js_response.text
    assert "/crm/convert" in js_response.text


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
