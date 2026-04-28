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
                  <a href="/sources">Sources</a>
                  <a href="/catalog">Catalog</a>
                  <a href="/crm">CRM</a>
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
                  <a href="/sources">Sources</a>
                  <a href="/catalog">Catalog</a>
                  <a href="/crm">CRM</a>
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
                    <h2>Userbots</h2>
                  </div>
                  <form id="userbot-form" class="inline-form">
                    <input name="display_name" placeholder="Userbot name" required>
                    <input name="session_name" placeholder="Session name" required>
                    <input name="session_path" placeholder="Session path" required>
                    <label class="checkbox-line">
                      <input name="make_default" type="checkbox" checked>
                      Default
                    </label>
                    <button type="submit">Add userbot</button>
                  </form>
                  <div id="userbot-accounts" class="table-list"></div>
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
                  <a href="/">Inbox</a>
                  <a href="/sources">Sources</a>
                  <a href="/catalog">Catalog</a>
                  <a href="/crm">CRM</a>
                  <a href="/admin">Admin</a>
                  <button id="logout-button" type="button">Logout</button>
                </nav>
              </header>
              <section class="crm-layout">
                <aside class="queue-pane" aria-label="Clients">
                  <div class="section-head">
                    <h2>Clients</h2>
                    <button id="crm-refresh" type="button">Refresh</button>
                  </div>
                  <div id="crm-client-list" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="crm-client-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Select a client</div>
                </section>
                <aside class="side-pane" aria-label="New client">
                  <form id="crm-client-form" class="stack">
                    <label>
                      Name
                      <input name="display_name" required>
                    </label>
                    <label>
                      Type
                      <select name="client_type">
                        <option value="unknown">Unknown</option>
                        <option value="person">Person</option>
                        <option value="family">Family</option>
                        <option value="company">Company</option>
                        <option value="cottage_settlement">Cottage settlement</option>
                        <option value="hoa_tsn">HOA / TSN</option>
                        <option value="residential_complex">Residential complex</option>
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
                      Interest
                      <textarea name="interest_text" rows="4"></textarea>
                    </label>
                    <label>
                      Notes
                      <textarea name="notes" rows="4"></textarea>
                    </label>
                    <button type="submit">Create</button>
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
            title="Sources",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Sources</h1>
                </div>
                <nav>
                  <a href="/">Inbox</a>
                  <a href="/sources">Sources</a>
                  <a href="/catalog">Catalog</a>
                  <a href="/crm">CRM</a>
                  <a href="/admin">Admin</a>
                  <button id="logout-button" type="button">Logout</button>
                </nav>
              </header>
              <section class="sources-layout">
                <aside class="queue-pane" aria-label="Telegram sources">
                  <div class="section-head">
                    <h2>Sources</h2>
                    <button id="source-refresh" type="button">Refresh</button>
                  </div>
                  <div id="source-list" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="source-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Select a source</div>
                </section>
                <aside class="side-pane" aria-label="New source">
                  <form id="source-form" class="stack">
                    <label>
                      Telegram chat or channel
                      <input name="input_ref" placeholder="@chat or https://t.me/..." required>
                    </label>
                    <label>
                      Purpose
                      <select name="purpose">
                        <option value="lead_monitoring">Lead monitoring</option>
                        <option value="catalog_ingestion">Catalog ingestion</option>
                        <option value="both">Both</option>
                      </select>
                    </label>
                    <label>
                      Start days back
                      <input name="start_recent_days" type="number" min="1" placeholder="empty = from now">
                    </label>
                    <label class="checkbox-line">
                      <input name="check_access" type="checkbox" checked>
                      Check access now
                    </label>
                    <button type="submit">Create source</button>
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
            title="Catalog",
            main="""
            <main class="workspace">
              <header class="topbar">
                <div>
                  <span class="eyebrow">PUR Leads</span>
                  <h1>Catalog</h1>
                </div>
                <nav>
                  <a href="/">Inbox</a>
                  <a href="/sources">Sources</a>
                  <a href="/catalog">Catalog</a>
                  <a href="/crm">CRM</a>
                  <a href="/admin">Admin</a>
                  <button id="logout-button" type="button">Logout</button>
                </nav>
              </header>
              <section class="catalog-layout">
                <aside class="queue-pane" aria-label="Catalog candidates">
                  <div class="section-head">
                    <h2>Candidates</h2>
                    <button id="catalog-refresh" type="button">Refresh</button>
                  </div>
                  <form id="catalog-filters" class="filter-grid">
                    <select name="status" aria-label="Status">
                      <option value="auto_pending">Auto pending</option>
                      <option value="needs_review">Needs review</option>
                      <option value="approved">Approved</option>
                      <option value="rejected">Rejected</option>
                      <option value="">All status</option>
                    </select>
                    <select name="candidate_type" aria-label="Type">
                      <option value="">All types</option>
                      <option value="item">Items</option>
                      <option value="offer">Offers</option>
                      <option value="lead_phrase">Lead phrases</option>
                      <option value="negative_phrase">Negative phrases</option>
                    </select>
                  </form>
                  <form id="manual-input-form" class="manual-input-form">
                    <h2>Manual input</h2>
                    <select name="input_type" aria-label="Manual input type">
                      <option value="catalog_note">Catalog note</option>
                      <option value="lead_example">Lead example</option>
                      <option value="non_lead_example">Non-lead example</option>
                      <option value="telegram_link">Telegram link</option>
                      <option value="manual_text">Manual text</option>
                    </select>
                    <textarea name="text" rows="4" placeholder="Text"></textarea>
                    <input name="url" type="url" placeholder="https://t.me/...">
                    <input name="evidence_note" placeholder="Evidence note">
                    <label class="checkbox-line">
                      <input name="auto_extract" type="checkbox" checked>
                      Auto extract
                    </label>
                    <button type="submit">Submit</button>
                    <p id="manual-input-status" class="status-line" role="status"></p>
                  </form>
                  <div id="catalog-candidate-list" class="queue-list" aria-live="polite"></div>
                </aside>
                <section id="catalog-candidate-detail" class="detail-pane" aria-live="polite">
                  <div class="empty-state">Select a candidate</div>
                  <form id="catalog-edit-form" class="catalog-edit-form" hidden>
                    <label>Name<input id="catalog-name-input" name="canonical_name"></label>
                    <label>Payload JSON<textarea id="catalog-value-json" name="normalized_value"></textarea></label>
                  </form>
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
