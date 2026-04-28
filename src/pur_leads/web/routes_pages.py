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
            <h1>Operator access</h1>
            <form id="local-login-form" class="stack" autocomplete="on">
              <label>
                Username
                <input name="username" type="text" autocomplete="username" required>
              </label>
              <label>
                Password
                <input name="password" type="password" autocomplete="current-password" required>
              </label>
              <button type="submit">Sign in</button>
              <p id="login-status" class="status-line" role="status"></p>
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
            title="Leads Inbox",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Leads Inbox</h1>
                </div>
                <nav>
                  <a href="/">Inbox</a>
                  <a href="/admin">Admin</a>
                  <button id="logout-button" type="button">Logout</button>
                </nav>
              </header>
              <section class="inbox-layout">
                <aside class="queue-pane" aria-label="Lead queue">
                  <form id="lead-filters" class="filter-grid">
                    <select name="status" aria-label="Status">
                      <option value="">All status</option>
                      <option value="new">New</option>
                      <option value="in_work">In work</option>
                      <option value="maybe">Maybe</option>
                      <option value="snoozed">Snoozed</option>
                    </select>
                    <label><input type="checkbox" name="auto_pending"> Auto pending</label>
                    <label><input type="checkbox" name="operator_issues"> Operator issues</label>
                    <label><input type="checkbox" name="retro"> Retro</label>
                    <input name="min_confidence" type="number" min="0" max="1" step="0.05"
                      placeholder="Min confidence" aria-label="Minimum confidence">
                  </form>
                  <div id="lead-queue" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="lead-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Select a lead</div>
                </section>
                <aside class="side-pane" aria-label="Operational signals">
                  <dl class="signal-list">
                    <div><dt data-field="auto_pending">Auto pending</dt><dd id="signal-auto">0</dd></div>
                    <div><dt data-field="retro">Retro</dt><dd id="signal-retro">0</dd></div>
                    <div><dt data-field="maybe">Maybe</dt><dd id="signal-maybe">0</dd></div>
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
            title="Admin",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Admin</h1>
                </div>
                <nav>
                  <a href="/">Inbox</a>
                  <a href="/admin">Admin</a>
                  <button id="logout-button" type="button">Logout</button>
                </nav>
              </header>
              <section class="admin-layout">
                <section>
                  <div class="section-head">
                    <h2>Admin users</h2>
                  </div>
                  <form id="telegram-admin-form" class="inline-form">
                    <input name="telegram_user_id" placeholder="Telegram ID" required>
                    <input name="telegram_username" placeholder="Username">
                    <input name="display_name" placeholder="Display name">
                    <button type="submit">Add</button>
                  </form>
                  <div id="admin-users" class="table-list"></div>
                </section>
                <section>
                  <div class="section-head">
                    <h2>Settings</h2>
                  </div>
                  <form id="setting-form" class="inline-form">
                    <input name="key" placeholder="Key" required>
                    <input name="value" placeholder="JSON value" required>
                    <select name="value_type">
                      <option value="bool">bool</option>
                      <option value="int">int</option>
                      <option value="float">float</option>
                      <option value="string">string</option>
                      <option value="json">json</option>
                    </select>
                    <button type="submit">Save</button>
                  </form>
                  <div id="settings-list" class="table-list"></div>
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
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="{page}">
  {main}
  <script src="/static/app.js" defer></script>
</body>
</html>"""
