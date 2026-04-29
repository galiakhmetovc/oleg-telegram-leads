const page = document.body.dataset.page;

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "content-type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      window.location.assign("/login");
    }
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return response.json();
};

const text = (value, fallback = "") => {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
};

const time = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  return date.toLocaleString();
};

const badge = (label, className = "") =>
  `<span class="badge ${className}">${escapeHtml(label)}</span>`;

const escapeHtml = (value) =>
  text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

document.addEventListener("DOMContentLoaded", () => {
  bindLogout();
  if (page === "login") bindLogin();
  if (page === "leads-inbox") initInbox();
  if (page === "sources") initSources();
  if (page === "catalog") initCatalog();
  if (page === "crm") initCrm();
  if (page === "today") initToday();
  if (page === "operations") initOperations();
  if (page === "quality") initQuality();
  if (page === "admin") initAdmin();
});

function bindLogin() {
  const form = document.querySelector("#local-login-form");
  const status = document.querySelector("#login-status");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "";
    const data = new FormData(form);
    try {
      await api("/api/auth/local", {
        method: "POST",
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      window.location.assign("/");
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

function bindLogout() {
  document.querySelector("#logout-button")?.addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => null);
    window.location.assign("/login");
  });
}

function initInbox() {
  const state = { items: [], selectedId: null, limit: 50, offset: 0, pagination: null, loading: false };
  const form = document.querySelector("#lead-filters");
  const reset = () => loadLeads(state, { reset: true });
  form?.addEventListener("change", reset);
  form?.addEventListener("input", reset);
  document.querySelector("#lead-load-more")?.addEventListener("click", () => {
    if (!state.pagination?.has_more || state.loading) return;
    state.offset = state.items.length;
    loadLeads(state, { append: true });
  });
  loadLeads(state);
}

async function loadLeads(state, options = {}) {
  if (options.reset) state.offset = 0;
  state.loading = true;
  renderPagination(state);
  const params = new URLSearchParams({
    limit: String(state.limit),
    offset: String(state.offset),
  });
  const form = document.querySelector("#lead-filters");
  if (form) {
    const data = new FormData(form);
    for (const [key, value] of data.entries()) {
      if (value === "on") params.set(key, "true");
      else if (value) params.set(key, value);
    }
  }
  let payload;
  try {
    payload = await api(`/api/leads?${params.toString()}`);
  } finally {
    state.loading = false;
  }
  const incoming = payload.items || [];
  state.items = options.append ? [...state.items, ...incoming] : incoming;
  state.pagination = payload.pagination || {
    limit: state.limit,
    offset: state.offset,
    total: state.items.length,
    has_more: false,
  };
  const selectedStillVisible = state.items.some((item) => item.cluster_id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.cluster_id || null;
  renderSignals(state.items, payload.summary);
  renderQueue(state);
  renderPagination(state);
  if (state.selectedId) {
    await loadDetail(state.selectedId);
  } else {
    const detail = document.querySelector("#lead-detail");
    if (detail) detail.innerHTML = `<div class="empty-state">Select a lead</div>`;
  }
}

function renderSignals(items, summary = {}) {
  const autoPending = summary.auto_pending ?? items.filter((item) => item.has_auto_pending).length;
  const retro = summary.retro ?? items.filter((item) => item.is_retro).length;
  const maybe = summary.maybe ?? items.filter((item) => item.is_maybe).length;
  document.querySelector("#signal-auto").textContent = autoPending;
  document.querySelector("#signal-retro").textContent = retro;
  document.querySelector("#signal-maybe").textContent = maybe;
}

function renderQueue(state) {
  const target = document.querySelector("#lead-queue");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">No leads</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((item) => {
      const active = item.cluster_id === state.selectedId ? "is-active" : "";
      const markers = [
        item.has_auto_pending ? badge("auto_pending", "is-warn") : "",
        item.has_auto_merge_pending ? badge("merge", "is-warn") : "",
        item.is_retro ? badge("retro") : "",
        item.is_maybe ? badge("maybe") : "",
      ].join("");
      return `<button class="queue-item ${active}" type="button" data-id="${item.cluster_id}">
        <strong>${escapeHtml(item.primary_message?.text || item.status)}</strong>
        <span class="muted">${escapeHtml(item.category?.name || "Uncategorized")}</span>
        <span class="queue-meta">${markers}${badge(Math.round((item.confidence || 0) * 100) + "%")}</span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id;
      renderQueue(state);
      await loadDetail(state.selectedId);
    });
  });
}

function renderPagination(state) {
  const pagination = state.pagination || { total: 0, has_more: false };
  const meta = document.querySelector("#lead-pagination");
  const button = document.querySelector("#lead-load-more");
  if (meta) {
    meta.textContent = `${Math.min(state.items.length, pagination.total)} / ${pagination.total}`;
  }
  if (button) {
    button.hidden = !pagination.has_more;
    button.disabled = state.loading;
  }
}

async function loadDetail(clusterId) {
  const detail = await api(`/api/leads/${clusterId}`);
  renderDetail(detail);
}

function renderDetail(detail) {
  const target = document.querySelector("#lead-detail");
  if (!target) return;
  const cluster = detail.cluster || {};
  const events = detail.events || [];
  const matches = detail.matches || [];
  const feedback = detail.feedback || [];
  const firstEvent = events[0] || {};
  const classifierVersionId = firstEvent.classifier_version_id || "n/a";
  const crmCandidateCount = cluster.crm_candidate_count ?? 0;
  const senderName = cluster.primary_sender_name || firstEvent.sender_name || cluster.primary_message?.sender_id || "";
  const messageUrl = firstEvent.message_url || "";
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(cluster.primary_message?.text || cluster.status || "Lead")}</h2>
        <p class="muted">${escapeHtml(senderName)}</p>
      </div>
      <div class="badges">
        ${badge(cluster.status || "new")}
        ${badge(cluster.work_outcome || "none")}
        ${cluster.has_auto_pending ? badge("auto_pending", "is-warn") : ""}
        ${cluster.is_retro ? badge("retro") : ""}
        ${cluster.is_maybe ? badge("maybe") : ""}
      </div>
    </header>
    <section class="detail-section">
      <h3>Source</h3>
      <div class="detail-meta">
        ${badge(`source ${cluster.source_id || "n/a"}`)}
        ${badge(`message ${cluster.primary_message?.telegram_message_id || "n/a"}`)}
        ${badge(`classifier_version_id ${classifierVersionId}`)}
        ${badge(`crm_candidate_count ${crmCandidateCount}`)}
        ${badge(`primary_task_id ${cluster.primary_task_id || "n/a"}`)}
        ${badge(`merge ${cluster.merge_reason || cluster.merge_strategy || "none"}`)}
      </div>
      ${
        messageUrl
          ? `<a href="${escapeHtml(messageUrl)}" target="_blank" rel="noreferrer">Open message</a>`
          : ""
      }
    </section>
    <section class="detail-section">
      <h3>Matches</h3>
      <div class="table-list">
        ${matches.map(renderMatch).join("") || '<div class="empty-state">No matches</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Timeline</h3>
      <div class="timeline">
        ${(detail.timeline || []).map(renderTimelineEntry).join("") || '<div class="empty-state">No events</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Feedback</h3>
      <div class="table-list">
        ${feedback.map(renderFeedback).join("") || '<div class="empty-state">No feedback</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Actions</h3>
      <div class="detail-meta">
        <button type="button" data-action="take_into_work">Take into work</button>
        <button type="button" data-action="maybe">Maybe</button>
        <button type="button" data-action="not_lead">Not lead</button>
      </div>
    </section>
    <section class="detail-section">
      <h3>CRM conversion</h3>
      <form id="lead-crm-convert-form" class="inline-form">
        <input name="display_name" value="${escapeHtml(senderName || "New client")}" required>
        <input name="interest_text" value="${escapeHtml(cluster.primary_message?.text || "")}" required>
        <input name="task_title" value="Contact client" required>
        <button type="submit">Convert</button>
      </form>
    </section>
  </div>`;
  target.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => applyLeadAction(cluster.cluster_id, button.dataset.action));
  });
  target.querySelector("#lead-crm-convert-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    convertLeadToCrm(cluster.cluster_id, {
      client: {
        display_name: data.get("display_name"),
        client_type: "unknown",
      },
      contact: {
        telegram_user_id: firstEvent.sender_id || cluster.primary_sender_id || null,
      },
      interest: {
        interest_text: data.get("interest_text"),
      },
      task: {
        title: data.get("task_title"),
      },
    });
  });
}

function renderMatch(match) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(match.matched_text || match.match_type)}</strong>
      <p class="muted">${escapeHtml(match.catalog_term_text || match.catalog_item_name || match.category_name || "")}</p>
    </div>
    <span>${Math.round((match.score || 0) * 100)}%</span>
  </div>`;
}

function renderTimelineEntry(entry) {
  const label = entry.kind === "message" ? entry.message?.text : entry.event?.reason || entry.feedback?.action;
  return `<div class="timeline-entry">
    <strong>${escapeHtml(entry.kind)}</strong>
    <p>${escapeHtml(label || "")}</p>
    <p class="muted">${time(entry.at)}</p>
  </div>`;
}

function renderFeedback(row) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(row.action)}</strong>
      <p class="muted">${escapeHtml(row.feedback_scope)} / ${escapeHtml(row.learning_effect)}</p>
    </div>
    <span>${escapeHtml(row.application_status || "")}</span>
  </div>`;
}

async function applyLeadAction(clusterId, action) {
  const status = document.querySelector("#action-status");
  const payload = { action };
  if (action === "not_lead") payload.reason_code = "operator_rejected";
  try {
    await api(`/api/leads/${clusterId}/actions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    status.textContent = "Saved";
    await loadDetail(clusterId);
  } catch (error) {
    status.textContent = error.message;
  }
}

async function convertLeadToCrm(clusterId, payload) {
  const status = document.querySelector("#action-status");
  try {
    await api(`/api/leads/${clusterId}/crm/convert`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (status) status.textContent = "Converted to CRM";
    await loadDetail(clusterId);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function initCrm() {
  const state = { items: [], selectedId: null };
  document.querySelector("#crm-refresh")?.addEventListener("click", () => loadCrmClients(state));
  document.querySelector("#crm-client-form")?.addEventListener("submit", (event) =>
    createCrmClient(event, state)
  );
  loadCrmClients(state);
}

async function loadCrmClients(state) {
  const payload = await api("/api/crm/clients");
  state.items = payload.items || [];
  const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
  renderCrmList(state);
  if (state.selectedId) {
    await loadCrmDetail(state.selectedId);
  } else {
    const detail = document.querySelector("#crm-client-detail");
    if (detail) detail.innerHTML = `<div class="empty-state">No clients</div>`;
  }
}

function renderCrmList(state) {
  const target = document.querySelector("#crm-client-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">No clients</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((client) => {
      const active = client.id === state.selectedId ? "is-active" : "";
      return `<button class="queue-item ${active}" type="button" data-id="${client.id}">
        <strong>${escapeHtml(client.display_name)}</strong>
        <span class="muted">${escapeHtml(client.client_type)} / ${escapeHtml(client.status)}</span>
        <span class="queue-meta">${badge(client.source_type)}${badge(time(client.updated_at) || "new")}</span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id;
      renderCrmList(state);
      await loadCrmDetail(state.selectedId);
    });
  });
}

async function loadCrmDetail(clientId) {
  const profile = await api(`/api/crm/clients/${clientId}`);
  renderCrmDetail(profile);
}

function renderCrmDetail(profile) {
  const target = document.querySelector("#crm-client-detail");
  if (!target) return;
  const client = profile.client || {};
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(client.display_name || "Client")}</h2>
        <p class="muted">${escapeHtml(client.client_type || "unknown")}</p>
      </div>
      <div class="badges">
        ${badge(client.status || "active")}
        ${badge(client.source_type || "manual")}
      </div>
    </header>
    ${crmSection("Contacts", profile.contacts, renderCrmContact)}
    ${crmSection("Objects", profile.objects, renderCrmObject)}
    ${crmSection("Interests", profile.interests, renderCrmInterest)}
    ${crmSection("Assets", profile.assets, renderCrmAsset)}
    ${crmSection("Contact reasons", profile.contact_reasons, renderCrmReason)}
    ${crmSection("Touchpoints", profile.touchpoints, renderCrmTouchpoint)}
  </div>`;
}

function crmSection(title, rows, renderer) {
  return `<section class="detail-section">
    <h3>${escapeHtml(title)}</h3>
    <div class="table-list">
      ${(rows || []).map(renderer).join("") || '<div class="empty-state">None</div>'}
    </div>
  </section>`;
}

function renderCrmContact(contact) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(contact.contact_name || contact.telegram_username || contact.telegram_user_id || "Contact")}</strong>
      <p class="muted">${escapeHtml(contact.preferred_channel || "unknown")}</p>
    </div>
    <span>${contact.is_primary ? "primary" : ""}</span>
  </div>`;
}

function renderCrmObject(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.name)}</strong>
      <p class="muted">${escapeHtml(item.location_text || item.object_type)}</p>
    </div>
    <span>${escapeHtml(item.project_stage)}</span>
  </div>`;
}

function renderCrmInterest(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.interest_text)}</strong>
      <p class="muted">${escapeHtml(item.notes || "")}</p>
    </div>
    <span>${escapeHtml(item.interest_status)}</span>
  </div>`;
}

function renderCrmAsset(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.asset_name)}</strong>
      <p class="muted">${escapeHtml(time(item.service_due_at))}</p>
    </div>
    <span>${escapeHtml(item.asset_status)}</span>
  </div>`;
}

function renderCrmReason(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.title)}</strong>
      <p class="muted">${escapeHtml(item.reason_text)}</p>
    </div>
    <span>${escapeHtml(item.status)}</span>
  </div>`;
}

function renderCrmTouchpoint(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.summary)}</strong>
      <p class="muted">${escapeHtml(item.channel)} / ${escapeHtml(item.direction)}</p>
    </div>
    <span>${escapeHtml(time(item.created_at))}</span>
  </div>`;
}

async function createCrmClient(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#crm-status");
  const data = new FormData(form);
  const contacts = [];
  if (data.get("telegram_user_id") || data.get("telegram_username")) {
    contacts.push({
      telegram_user_id: data.get("telegram_user_id") || null,
      telegram_username: data.get("telegram_username") || null,
      preferred_channel: "telegram",
      is_primary: true,
    });
  }
  const interests = [];
  if (data.get("interest_text")) {
    interests.push({ interest_text: data.get("interest_text"), interest_status: "interested" });
  }
  try {
    const profile = await api("/api/crm/clients", {
      method: "POST",
      body: JSON.stringify({
        display_name: data.get("display_name"),
        client_type: data.get("client_type"),
        notes: data.get("notes") || null,
        contacts,
        interests,
      }),
    });
    form.reset();
    if (status) status.textContent = "Created";
    state.selectedId = profile.client.id;
    await loadCrmClients(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function initSources() {
  const state = { items: [], selectedId: null };
  document.querySelector("#source-refresh")?.addEventListener("click", () => loadSources(state));
  document.querySelector("#source-form")?.addEventListener("submit", (event) =>
    createSource(event, state)
  );
  loadSources(state);
}

async function loadSources(state) {
  const payload = await api("/api/sources");
  state.items = payload.items || [];
  const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
  renderSourceList(state);
  if (state.selectedId) {
    await loadSourceDetail(state.selectedId, state);
  } else {
    const detail = document.querySelector("#source-detail");
    if (detail) detail.innerHTML = `<div class="empty-state">No sources</div>`;
  }
}

function renderSourceList(state) {
  const target = document.querySelector("#source-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">No sources</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((source) => {
      const active = source.id === state.selectedId ? "is-active" : "";
      const label = source.title || source.username || source.input_ref;
      const statusClass = sourceStatusClass(source.status);
      return `<button class="queue-item ${active}" type="button" data-id="${source.id}">
        <strong>${escapeHtml(label)}</strong>
        <span class="muted">${escapeHtml(source.source_kind)} / ${escapeHtml(source.source_purpose)}</span>
        <span class="queue-meta">
          ${badge(source.status, statusClass)}
          ${source.lead_detection_enabled ? badge("leads") : ""}
          ${source.catalog_ingestion_enabled ? badge("catalog") : ""}
        </span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id;
      renderSourceList(state);
      await loadSourceDetail(state.selectedId, state);
    });
  });
}

async function loadSourceDetail(sourceId, state) {
  const detail = await api(`/api/sources/${sourceId}`);
  renderSourceDetail(detail, state);
}

function renderSourceDetail(detail, state) {
  const target = document.querySelector("#source-detail");
  if (!target) return;
  const source = detail.source || {};
  const label = source.title || source.username || source.input_ref || "Source";
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(label)}</h2>
        <p class="muted">${escapeHtml(source.input_ref || "")}</p>
      </div>
      <div class="badges">
        ${badge(source.status || "draft", sourceStatusClass(source.status))}
        ${badge(source.source_kind || "telegram")}
        ${badge(source.priority || "normal")}
      </div>
    </header>
    <section class="detail-section">
      <h3>Configuration</h3>
      <div class="detail-meta">
        ${badge(`purpose ${source.source_purpose || "n/a"}`)}
        ${badge(`poll ${source.poll_interval_seconds || 0}s`)}
        ${badge(`checkpoint ${source.checkpoint_message_id || "none"}`)}
        ${badge(`preview ${source.preview_message_count || 0}`)}
        ${source.lead_detection_enabled ? badge("lead detection") : ""}
        ${source.catalog_ingestion_enabled ? badge("catalog ingestion") : ""}
      </div>
      <p class="muted">next poll ${escapeHtml(time(source.next_poll_at) || "not scheduled")}</p>
      ${
        source.last_error
          ? `<p class="muted">last error ${escapeHtml(source.last_error)}</p>`
          : ""
      }
    </section>
    <section class="detail-section">
      <h3>Actions</h3>
      <div class="source-action-bar">
        <button type="button" data-source-action="check-access">Check access</button>
        <button type="button" data-source-action="preview">Fetch preview</button>
        <button type="button" data-source-action="activate">Activate</button>
        <button type="button" data-source-action="pause">Pause</button>
      </div>
      <form id="source-checkpoint-form" class="checkpoint-form">
        <input name="message_id" type="number" min="1" placeholder="Checkpoint message ID" required>
        <button type="submit">Reset checkpoint</button>
      </form>
    </section>
    ${sourceSection("Preview messages", detail.preview_messages, renderPreviewMessage)}
    ${sourceSection("Access checks", detail.access_checks, renderAccessCheck)}
    ${sourceSection("Jobs", detail.jobs, renderSourceJob)}
  </div>`;
  target.querySelectorAll("[data-source-action]").forEach((button) => {
    button.addEventListener("click", () =>
      sourceAction(source.id, button.dataset.sourceAction, state)
    );
  });
  target.querySelector("#source-checkpoint-form")?.addEventListener("submit", (event) =>
    resetSourceCheckpoint(event, source.id, state)
  );
}

function sourceSection(title, rows, renderer) {
  return `<section class="detail-section">
    <h3>${escapeHtml(title)}</h3>
    <div class="table-list">
      ${(rows || []).map(renderer).join("") || '<div class="empty-state">None</div>'}
    </div>
  </section>`;
}

function renderPreviewMessage(message) {
  const body = message.text || message.caption || "";
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(body || "Media message")}</strong>
      <p class="muted">${escapeHtml(message.sender_display || "")}</p>
    </div>
    <span>${escapeHtml(message.telegram_message_id)}</span>
  </div>`;
}

function renderAccessCheck(check) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(check.status)}</strong>
      <p class="muted">${escapeHtml(check.resolved_title || check.error || check.check_type)}</p>
    </div>
    <span>${escapeHtml(time(check.checked_at))}</span>
  </div>`;
}

function renderSourceJob(job) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(job.job_type)}</strong>
      <p class="muted">${escapeHtml(job.idempotency_key || job.scope_id || "")}</p>
    </div>
    <span>${escapeHtml(job.status || time(job.created_at))}</span>
  </div>`;
}

async function createSource(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#source-status");
  const data = new FormData(form);
  const startRecentDays = Number.parseInt(data.get("start_recent_days"), 10);
  try {
    const payload = await api("/api/sources", {
      method: "POST",
      body: JSON.stringify({
        input_ref: data.get("input_ref"),
        purpose: data.get("purpose"),
        check_access: data.get("check_access") === "on",
        start_recent_days: Number.isNaN(startRecentDays) ? null : startRecentDays,
      }),
    });
    form.reset();
    form.querySelector('[name="check_access"]').checked = true;
    if (status) status.textContent = "Created";
    state.selectedId = payload.source?.id || null;
    await loadSources(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function sourceAction(sourceId, action, state) {
  const status = document.querySelector("#source-status");
  const endpoints = {
    "check-access": { path: `/api/sources/${sourceId}/check-access`, body: {} },
    preview: { path: `/api/sources/${sourceId}/preview`, body: { limit: 20 } },
    activate: { path: `/api/sources/${sourceId}/activate`, body: {} },
    pause: { path: `/api/sources/${sourceId}/pause`, body: {} },
  };
  const endpoint = endpoints[action];
  if (!endpoint) return;
  try {
    await api(endpoint.path, {
      method: "POST",
      body: JSON.stringify(endpoint.body),
    });
    if (status) status.textContent = "Saved";
    await loadSources(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function resetSourceCheckpoint(event, sourceId, state) {
  event.preventDefault();
  const status = document.querySelector("#source-status");
  const data = new FormData(event.currentTarget);
  try {
    await api(`/api/sources/${sourceId}/checkpoint`, {
      method: "POST",
      body: JSON.stringify({
        message_id: Number.parseInt(data.get("message_id"), 10),
        confirm: true,
      }),
    });
    event.currentTarget.reset();
    if (status) status.textContent = "Checkpoint reset";
    await loadSources(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function sourceStatusClass(status) {
  if (status === "checking_access" || status === "preview_ready") return "is-warn";
  if (status === "access_denied" || status === "error") return "is-danger";
  return "";
}

function initCatalog() {
  const state = { items: [], selectedId: null, detail: null };
  document.querySelector("#catalog-refresh")?.addEventListener("click", () =>
    loadCatalogCandidates(state)
  );
  document.querySelector("#catalog-filters")?.addEventListener("change", () =>
    loadCatalogCandidates(state)
  );
  document.querySelector("#manual-input-form")?.addEventListener("submit", (event) =>
    submitManualInput(event, state)
  );
  loadCatalogCandidates(state);
}

async function loadCatalogCandidates(state) {
  const params = new URLSearchParams();
  const form = document.querySelector("#catalog-filters");
  if (form) {
    const data = new FormData(form);
    for (const [key, value] of data.entries()) {
      if (value) params.set(key, value);
    }
  }
  const payload = await api(`/api/catalog/candidates?${params.toString()}`);
  state.items = payload.items || [];
  const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
  state.detail = null;
  renderCatalogCandidateList(state);
  if (state.selectedId) {
    await loadCatalogCandidateDetail(state, state.selectedId);
  } else {
    renderCatalogCandidateDetail(state);
  }
}

async function loadCatalogCandidateDetail(state, candidateId) {
  const target = document.querySelector("#catalog-candidate-detail");
  if (target) target.innerHTML = `<div class="empty-state">Loading candidate</div>`;
  const payload = await api(`/api/catalog/candidates/${candidateId}`);
  if (state.selectedId !== candidateId) return;
  state.detail = payload;
  const index = state.items.findIndex((item) => item.id === payload.candidate.id);
  if (index >= 0) state.items[index] = payload.candidate;
  renderCatalogCandidateList(state);
  renderCatalogCandidateDetail(state);
}

function renderCatalogCandidateList(state) {
  const target = document.querySelector("#catalog-candidate-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">No candidates</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((item) => {
      const active = item.id === state.selectedId ? "is-active" : "";
      const value = item.normalized_value || {};
      const subtitle = [item.candidate_type, value.category_slug, value.item_type]
        .filter(Boolean)
        .join(" / ");
      return `<button class="queue-item ${active}" type="button" data-id="${item.id}">
        <strong>${escapeHtml(item.canonical_name)}</strong>
        <span class="muted">${escapeHtml(subtitle || item.proposed_action)}</span>
        <span class="queue-meta">
          ${badge(item.status, catalogStatusClass(item.status))}
          ${badge(Math.round((item.confidence || 0) * 100) + "%")}
          ${item.evidence_count ? badge(`evidence ${item.evidence_count}`) : ""}
        </span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.id;
      state.detail = null;
      renderCatalogCandidateList(state);
      loadCatalogCandidateDetail(state, state.selectedId);
    });
  });
}

function renderCatalogCandidateDetail(state) {
  const target = document.querySelector("#catalog-candidate-detail");
  if (!target) return;
  const item =
    state.detail?.candidate || state.items.find((candidate) => candidate.id === state.selectedId);
  if (!item) {
    target.innerHTML = `<div class="empty-state">Select a candidate</div>`;
    return;
  }
  const value = item.normalized_value || {};
  const terms = Array.isArray(value.terms) ? value.terms : [];
  const evidence = state.detail?.evidence || [];
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(item.canonical_name)}</h2>
        <p class="muted">${escapeHtml(item.id)}</p>
      </div>
      <div class="badges">
        ${badge(item.status, catalogStatusClass(item.status))}
        ${badge(item.candidate_type)}
        ${badge(item.proposed_action)}
      </div>
    </header>
    <section class="detail-section">
      <h3>Value</h3>
      <div class="detail-meta">
        ${value.category_slug ? badge(value.category_slug) : ""}
        ${value.item_type ? badge(value.item_type) : ""}
        ${value.price_text ? badge(value.price_text, "is-warn") : ""}
        ${badge(`confidence ${Math.round((item.confidence || 0) * 100)}%`)}
      </div>
      ${
        value.description
          ? `<p>${escapeHtml(value.description)}</p>`
          : ""
      }
    </section>
    <section class="detail-section">
      <h3>Terms</h3>
      <div class="detail-meta">
        ${terms.map((term) => badge(term)).join("") || '<span class="muted">No terms</span>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Edit</h3>
      <form id="catalog-edit-form" class="catalog-edit-form">
        <label>Name
          <input id="catalog-name-input" name="canonical_name" value="${escapeHtml(item.canonical_name)}">
        </label>
        <label>Payload JSON
          <textarea id="catalog-value-json" name="normalized_value" rows="12">${escapeHtml(
            JSON.stringify(value, null, 2)
          )}</textarea>
        </label>
        <label>Reason
          <input name="reason" placeholder="Optional note">
        </label>
        <div class="source-action-bar">
          <button type="submit">Save changes</button>
        </div>
      </form>
    </section>
    <section class="detail-section">
      <h3>Evidence</h3>
      ${renderCatalogEvidence(evidence)}
    </section>
    <section class="detail-section">
      <h3>Review</h3>
      <div class="source-action-bar">
        <button type="button" data-catalog-action="approve">Approve</button>
        <button type="button" data-catalog-action="needs_review">Needs review</button>
        <button type="button" data-catalog-action="reject">Reject</button>
        <button type="button" data-catalog-action="mute">Mute</button>
      </div>
      <p id="catalog-status" class="status-line" role="status"></p>
    </section>
  </div>`;
  target.querySelectorAll("[data-catalog-action]").forEach((button) => {
    button.addEventListener("click", () =>
      reviewCatalogCandidate(item.id, button.dataset.catalogAction, state)
    );
  });
  target.querySelector("#catalog-edit-form")?.addEventListener("submit", (event) =>
    saveCatalogCandidateEdit(event, item.id, state)
  );
}

function renderCatalogEvidence(evidence) {
  if (!evidence.length) return `<div class="empty-state">No evidence</div>`;
  return `<div class="evidence-list">${evidence
    .map((item) => {
      const sourceLabel = [item.source?.origin, item.source?.external_id].filter(Boolean).join(" / ");
      const artifactLabel = item.artifact?.file_name || item.artifact?.mime_type || "";
      const chunkText = item.chunk?.text || item.source?.raw_text_excerpt || "";
      return `<article class="evidence-item">
        <div class="evidence-source">
          <strong>${escapeHtml(sourceLabel || "Source")}</strong>
          ${artifactLabel ? badge(artifactLabel) : ""}
          ${item.chunk ? badge(`chunk ${item.chunk.chunk_index}`) : ""}
          ${item.confidence ? badge(Math.round(item.confidence * 100) + "%") : ""}
        </div>
        ${item.quote ? `<blockquote>${escapeHtml(item.quote)}</blockquote>` : ""}
        ${chunkText ? `<p>${escapeHtml(shortText(chunkText, 520))}</p>` : ""}
      </article>`;
    })
    .join("")}</div>`;
}

async function saveCatalogCandidateEdit(event, candidateId, state) {
  event.preventDefault();
  const status = document.querySelector("#catalog-status");
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    const normalizedValue = JSON.parse(data.get("normalized_value") || "{}");
    const payload = await api(`/api/catalog/candidates/${candidateId}`, {
      method: "PATCH",
      body: JSON.stringify({
        canonical_name: data.get("canonical_name"),
        normalized_value: normalizedValue,
        reason: data.get("reason"),
      }),
    });
    state.detail = payload;
    const index = state.items.findIndex((item) => item.id === payload.candidate.id);
    if (index >= 0) state.items[index] = payload.candidate;
    renderCatalogCandidateList(state);
    renderCatalogCandidateDetail(state);
    document.querySelector("#catalog-status").textContent = "Saved";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function reviewCatalogCandidate(candidateId, action, state) {
  const status = document.querySelector("#catalog-status");
  try {
    await api(`/api/catalog/candidates/${candidateId}/review`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    if (status) status.textContent = "Saved";
    await loadCatalogCandidates(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function submitManualInput(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#manual-input-status");
  const data = new FormData(form);
  const body = {
    input_type: data.get("input_type"),
    text: data.get("text") || null,
    url: data.get("url") || null,
    evidence_note: data.get("evidence_note") || null,
    auto_extract: data.get("auto_extract") === "on",
  };
  try {
    const payload = await api("/api/catalog/manual-inputs", {
      method: "POST",
      body: JSON.stringify(body),
    });
    form.reset();
    form.querySelector('input[name="auto_extract"]').checked = true;
    if (status) {
      const queued = payload.queued_jobs?.length || 0;
      const snapshot = payload.classifier_snapshot ? `snapshot v${payload.classifier_snapshot.version}` : "";
      const evaluationCase = payload.evaluation_case ? "evaluation case" : "";
      status.textContent = ["Saved", queued ? `${queued} job queued` : "", snapshot, evaluationCase]
        .filter(Boolean)
        .join(" / ");
    }
    await loadCatalogCandidates(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function catalogStatusClass(status) {
  if (status === "auto_pending" || status === "needs_review") return "is-warn";
  if (status === "rejected" || status === "muted") return "is-danger";
  return "";
}

function initOperations() {
  const state = { items: [], selectedId: null };
  document.querySelector("#operations-refresh")?.addEventListener("click", () =>
    loadOperations(state)
  );
  document.querySelector("#operations-job-filters")?.addEventListener("change", () =>
    loadOperationsJobs(state)
  );
  document.querySelector("#operations-job-filters")?.addEventListener("input", () =>
    loadOperationsJobs(state)
  );
  document.querySelector("#operations-backup-create")?.addEventListener("click", createOperationBackup);
  loadOperations(state);
}

async function loadOperations(state) {
  await Promise.all([loadOperationsSummary(), loadOperationsJobs(state), loadOperationsSignals()]);
}

async function loadOperationsSummary() {
  const summary = await api("/api/operations/summary");
  const target = document.querySelector("#operations-summary");
  if (!target) return;
  const failedJobs = summary.jobs?.by_status?.failed || 0;
  const runningJobs = summary.jobs?.by_status?.running || 0;
  const queuedJobs = summary.jobs?.by_status?.queued || 0;
  const errorEvents =
    (summary.events?.by_severity?.error || 0) + (summary.events?.by_severity?.critical || 0);
  const suppressedNotifications = summary.notifications?.by_status?.suppressed || 0;
  const failedExtractions = summary.extraction_runs?.by_status?.failed || 0;
  const accessIssues = countStatusesExcept(summary.access_checks?.by_status || {}, [
    "succeeded",
  ]);
  const failedBackups = summary.backups?.by_status?.failed || 0;
  const verifiedBackups = summary.backups?.by_status?.verified || 0;
  const failedQualityRuns = summary.quality?.runs?.by_status?.failed || 0;
  const qualityCases = summary.quality?.cases?.total || 0;
  target.innerHTML = `<div class="ops-metric-row">
    ${renderOpsMetric("Jobs", summary.jobs?.total || 0, `${queuedJobs} queued / ${runningJobs} running`)}
    ${renderOpsMetric("Failed jobs", failedJobs, "needs operator check", failedJobs ? "is-danger" : "")}
    ${renderOpsMetric("Runs", summary.runs?.total || 0, "worker attempts")}
    ${renderOpsMetric("Errors", errorEvents, "operational events", errorEvents ? "is-danger" : "")}
    ${renderOpsMetric("Notifications", summary.notifications?.total || 0, `${suppressedNotifications} suppressed`)}
    ${renderOpsMetric("Extraction", summary.extraction_runs?.total || 0, `${failedExtractions} failed`, failedExtractions ? "is-danger" : "")}
    ${renderOpsMetric("Access", summary.access_checks?.total || 0, `${accessIssues} issues`, accessIssues ? "is-danger" : "")}
    ${renderOpsMetric("Quality", qualityCases, `${failedQualityRuns} failed runs`, failedQualityRuns ? "is-danger" : "")}
    ${renderOpsMetric("Backups", summary.backups?.total || 0, `${verifiedBackups} verified`, failedBackups ? "is-danger" : "")}
    ${renderOpsMetric("Audit", summary.audit?.total || 0, "recorded changes")}
  </div>`;
}

function renderOpsMetric(label, value, hint, className = "") {
  return `<article class="ops-metric ${className}">
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(value)}</strong>
    <small>${escapeHtml(hint)}</small>
  </article>`;
}

async function loadOperationsJobs(state) {
  const params = new URLSearchParams();
  const form = document.querySelector("#operations-job-filters");
  if (form) {
    const data = new FormData(form);
    for (const [key, value] of data.entries()) {
      if (value) params.set(key, value);
    }
  }
  const query = params.toString();
  const payload = await api(`/api/operations/jobs${query ? `?${query}` : ""}`);
  state.items = payload.items || [];
  const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
  renderOperationsJobs(state);
  if (state.selectedId) {
    await loadOperationsJobDetail(state.selectedId);
  } else {
    const detail = document.querySelector("#operations-detail");
    if (detail) detail.innerHTML = `<div class="empty-state">No jobs</div>`;
  }
}

function renderOperationsJobs(state) {
  const target = document.querySelector("#operations-jobs");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">No jobs</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((job) => {
      const active = job.id === state.selectedId ? "is-active" : "";
      const subtitle = [job.scope_type, job.scope_id, job.monitored_source_id]
        .filter(Boolean)
        .join(" / ");
      return `<button class="queue-item ${active}" type="button" data-id="${job.id}">
        <strong>${escapeHtml(job.job_type)}</strong>
        <span class="muted">${escapeHtml(subtitle || job.idempotency_key || job.id)}</span>
        <span class="queue-meta">
          ${badge(job.status, operationsStatusClass(job.status))}
          ${badge(`attempts ${job.attempt_count || 0}/${job.max_attempts || 0}`)}
          ${job.last_error ? badge("error", "is-danger") : ""}
        </span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id;
      renderOperationsJobs(state);
      await loadOperationsJobDetail(state.selectedId);
    });
  });
}

async function loadOperationsJobDetail(jobId) {
  const detail = await api(`/api/operations/jobs/${jobId}`);
  renderOperationsJobDetail(detail);
}

function renderOperationsJobDetail(detail) {
  const target = document.querySelector("#operations-detail");
  if (!target) return;
  const job = detail.job || {};
  const runs = detail.runs || [];
  const events = detail.events || [];
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(job.job_type || "Job")}</h2>
        <p class="muted">${escapeHtml(job.id || "")}</p>
      </div>
      <div class="badges">
        ${badge(job.status || "unknown", operationsStatusClass(job.status))}
        ${badge(job.priority || "normal")}
        ${job.locked_by ? badge(`locked ${job.locked_by}`, "is-warn") : ""}
      </div>
    </header>
    <section class="detail-section">
      <h3>Execution</h3>
      <div class="detail-meta">
        ${badge(`scope ${job.scope_type || "n/a"}`)}
        ${badge(`source ${job.monitored_source_id || "n/a"}`)}
        ${badge(`message ${job.source_message_id || "n/a"}`)}
        ${badge(`attempts ${job.attempt_count || 0}/${job.max_attempts || 0}`)}
        ${badge(`run after ${time(job.run_after_at) || "n/a"}`)}
        ${badge(`retry ${time(job.next_retry_at) || "none"}`)}
      </div>
      ${
        job.last_error
          ? `<p class="muted">last error ${escapeHtml(job.last_error)}</p>`
          : ""
      }
    </section>
    ${operationsJsonSection("Payload", job.payload_json)}
    ${operationsJsonSection("Checkpoint before", job.checkpoint_before_json)}
    ${operationsJsonSection("Checkpoint after", job.checkpoint_after_json)}
    ${operationsJsonSection("Result", job.result_summary_json)}
    <section class="detail-section">
      <h3>Runs</h3>
      <div class="table-list">
        ${runs.map(renderOperationRun).join("") || '<div class="empty-state">No runs</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Events</h3>
      <div class="table-list">
        ${events.map(renderOperationEvent).join("") || '<div class="empty-state">No events</div>'}
      </div>
    </section>
  </div>`;
}

function operationsJsonSection(title, value) {
  if (value === null || value === undefined) return "";
  return `<section class="detail-section">
    <h3>${escapeHtml(title)}</h3>
    <pre class="json-block">${escapeHtml(JSON.stringify(value, null, 2))}</pre>
  </section>`;
}

function renderOperationRun(run) {
  const duration = run.duration_ms === null || run.duration_ms === undefined ? "running" : `${run.duration_ms}ms`;
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(run.worker_name || "worker")}</strong>
      <p class="muted">${escapeHtml(time(run.started_at))} / ${escapeHtml(duration)}</p>
    </div>
    <span>${badge(run.status, operationsStatusClass(run.status))}</span>
  </div>`;
}

async function loadOperationsSignals() {
  const [events, notifications, extractionRuns, accessChecks, backups, restores, audit] =
    await Promise.all([
      api("/api/operations/events?limit=12"),
      api("/api/operations/notifications?limit=12"),
      api("/api/operations/extraction-runs?limit=12"),
      api("/api/operations/access-checks?limit=12"),
      api("/api/operations/backups?limit=12"),
      api("/api/operations/restores?limit=12"),
      api("/api/operations/audit?limit=12"),
    ]);
  renderOperationsEvents(events.items || []);
  renderOperationsNotifications(notifications.items || []);
  renderOperationsExtractionRuns(extractionRuns.items || []);
  renderOperationsAccessChecks(accessChecks.items || []);
  renderOperationsBackups(backups.items || []);
  renderOperationsRestores(restores.items || []);
  renderOperationsAudit(audit.items || []);
}

function renderOperationsEvents(items) {
  const target = document.querySelector("#operations-events");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationEvent).join("") || '<div class="empty-state">No events</div>';
}

function renderOperationEvent(event) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(event.event_type || "event")}</strong>
      <p class="muted">${escapeHtml(shortText(event.message || "", 120))}</p>
    </div>
    <span>${badge(event.severity || "info", operationsStatusClass(event.severity))}</span>
  </div>`;
}

function renderOperationsNotifications(items) {
  const target = document.querySelector("#operations-notifications");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationNotification).join("") ||
    '<div class="empty-state">No notifications</div>';
}

function renderOperationNotification(item) {
  const label = [item.notification_type, item.notification_policy].filter(Boolean).join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(label || "notification")}</strong>
      <p class="muted">${escapeHtml(item.suppressed_reason || item.error || time(item.created_at))}</p>
    </div>
    <span>${badge(item.status || "unknown", operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderOperationsExtractionRuns(items) {
  const target = document.querySelector("#operations-extraction-runs");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationExtractionRun).join("") ||
    '<div class="empty-state">No extraction runs</div>';
}

function renderOperationExtractionRun(item) {
  const label = [item.run_type, item.model].filter(Boolean).join(" / ");
  const usage = tokenUsageSummary(item.token_usage_json);
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(label || "extraction")}</strong>
      <p class="muted">${escapeHtml(item.error || usage || time(item.started_at))}</p>
    </div>
    <span>${badge(item.status || "unknown", operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderOperationsAccessChecks(items) {
  const target = document.querySelector("#operations-access-checks");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationAccessCheck).join("") ||
    '<div class="empty-state">No access checks</div>';
}

function renderOperationAccessCheck(item) {
  const label = [item.resolved_title, item.monitored_source_id].filter(Boolean).join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(label || "source access")}</strong>
      <p class="muted">${escapeHtml(item.error || time(item.checked_at))}</p>
    </div>
    <span>${badge(item.status || "unknown", operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderOperationsBackups(items) {
  const target = document.querySelector("#operations-backups");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationBackup).join("") || '<div class="empty-state">No backups</div>';
  target.querySelectorAll("[data-backup-restore-check]").forEach((button) => {
    button.addEventListener("click", () => createOperationRestoreDryRun(button.dataset.backupId));
  });
}

function renderOperationBackup(item) {
  const details = [formatBytes(item.size_bytes), time(item.finished_at || item.started_at)]
    .filter(Boolean)
    .join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.backup_type || "backup")}</strong>
      <p class="muted">${escapeHtml(details || item.storage_uri || "")}</p>
    </div>
    <span class="row-actions">
      ${badge(item.status || "unknown", operationsStatusClass(item.status))}
      <button type="button" data-backup-id="${escapeHtml(item.id)}" data-backup-restore-check>Check</button>
    </span>
  </div>`;
}

function renderOperationsRestores(items) {
  const target = document.querySelector("#operations-restores");
  if (!target) return;
  target.innerHTML =
    items.map((item) => `<div class="table-row">
      <div>
        <strong>${escapeHtml(item.restore_type || "restore")}</strong>
        <p class="muted">${escapeHtml(time(item.finished_at || item.started_at))}</p>
      </div>
      <span>${badge(item.validation_status || item.status || "unknown", operationsStatusClass(item.status))}</span>
    </div>`).join("") || '<div class="empty-state">No restore checks</div>';
}

async function createOperationBackup() {
  const button = document.querySelector("#operations-backup-create");
  if (button) button.disabled = true;
  try {
    await api("/api/operations/backups/sqlite", { method: "POST", body: "{}" });
    await loadOperations({ items: [], selectedId: null });
  } finally {
    if (button) button.disabled = false;
  }
}

async function createOperationRestoreDryRun(backupId) {
  if (!backupId) return;
  await api(`/api/operations/backups/${backupId}/dry-run-restore`, {
    method: "POST",
    body: "{}",
  });
  await loadOperationsSignals();
  await loadOperationsSummary();
}

function renderOperationsAudit(items) {
  const target = document.querySelector("#operations-audit");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationAudit).join("") || '<div class="empty-state">No audit records</div>';
}

function renderOperationAudit(item) {
  const entity = [item.entity_type, item.entity_id].filter(Boolean).join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.action || "change")}</strong>
      <p class="muted">${escapeHtml(entity || item.actor || "")}</p>
    </div>
    <span>${escapeHtml(time(item.created_at))}</span>
  </div>`;
}

function initQuality() {
  document.querySelector("#quality-refresh")?.addEventListener("click", loadQuality);
  loadQuality();
}

async function loadQuality() {
  const [summary, datasets, runs, failedResults, decisions, cases] = await Promise.all([
    api("/api/quality/summary"),
    api("/api/quality/datasets?limit=20"),
    api("/api/quality/runs?limit=20"),
    api("/api/quality/results?passed=false&limit=20"),
    api("/api/quality/decisions?limit=20"),
    api("/api/quality/cases?limit=20"),
  ]);
  renderQualitySummary(summary);
  renderQualityDatasets(datasets.items || []);
  renderQualityRuns(runs.items || []);
  renderQualityFailedResults(failedResults.items || []);
  renderQualityDecisions(decisions.items || []);
  renderQualityCases(cases.items || []);
}

function renderQualitySummary(summary) {
  const target = document.querySelector("#quality-summary");
  if (!target) return;
  const failedResults = summary.results?.failed || 0;
  const failedRuns = summary.runs?.by_status?.failed || 0;
  const totalRuns = summary.runs?.total || 0;
  target.innerHTML = `<div class="ops-metric-row">
    ${renderOpsMetric("Decisions", summary.decisions?.total || 0, "recorded traces")}
    ${renderOpsMetric("Datasets", summary.datasets?.total || 0, "quality sets")}
    ${renderOpsMetric("Cases", summary.cases?.total || 0, "labeled examples")}
    ${renderOpsMetric("Runs", totalRuns, `${failedRuns} failed`, failedRuns ? "is-danger" : "")}
    ${renderOpsMetric("Failed cases", failedResults, "needs review", failedResults ? "is-danger" : "")}
  </div>`;
}

function renderQualityDatasets(items) {
  const target = document.querySelector("#quality-datasets");
  if (!target) return;
  if (!items.length) {
    target.innerHTML = `<div class="empty-state">No datasets</div>`;
    return;
  }
  target.innerHTML = items
    .map(
      (item) => `<div class="queue-item">
        <strong>${escapeHtml(item.name || item.dataset_key)}</strong>
        <span class="muted">${escapeHtml(item.dataset_key || item.id)}</span>
        <span class="queue-meta">
          ${badge(item.dataset_type || "dataset")}
          ${badge(item.status || "unknown", operationsStatusClass(item.status))}
        </span>
      </div>`
    )
    .join("");
}

function renderQualityRuns(items) {
  const target = document.querySelector("#quality-runs");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityRun).join("") || '<div class="empty-state">No runs</div>';
}

function renderQualityRun(item) {
  const metrics = item.metrics_json || {};
  const detail = [
    item.model,
    metrics.total !== undefined ? `${metrics.passed || 0}/${metrics.total} passed` : "",
    time(item.finished_at || item.started_at),
  ]
    .filter(Boolean)
    .join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.run_type || "evaluation")}</strong>
      <p class="muted">${escapeHtml(item.error || detail)}</p>
    </div>
    <span>${badge(item.status || "unknown", operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderQualityFailedResults(items) {
  const target = document.querySelector("#quality-failed-results");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityResult).join("") ||
    '<div class="empty-state">No failed cases</div>';
}

function renderQualityResult(item) {
  const detail = item.details_json?.reason || item.evaluation_case_id || item.id;
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.failure_type || "failed")}</strong>
      <p class="muted">${escapeHtml(shortText(detail || "", 120))}</p>
    </div>
    <span>${badge(item.actual_decision || "n/a", "is-danger")}</span>
  </div>`;
}

function renderQualityDecisions(items) {
  const target = document.querySelector("#quality-decisions");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityDecision).join("") ||
    '<div class="empty-state">No decisions</div>';
}

function renderQualityDecision(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.decision_type || "decision")}</strong>
      <p class="muted">${escapeHtml(shortText(item.reason || item.entity_id || "", 120))}</p>
    </div>
    <span>${badge(item.decision || "n/a")}</span>
  </div>`;
}

function renderQualityCases(items) {
  const target = document.querySelector("#quality-cases");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityCase).join("") || '<div class="empty-state">No cases</div>';
}

function renderQualityCase(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.expected_decision || "expected")}</strong>
      <p class="muted">${escapeHtml(shortText(item.message_text || item.id, 120))}</p>
    </div>
    <span>${badge(item.label_source || "manual")}</span>
  </div>`;
}

function operationsStatusClass(status) {
  if (status === "failed" || status === "error" || status === "critical") return "is-danger";
  if (
    status === "queued" ||
    status === "running" ||
    status === "warning" ||
    status === "flood_wait"
  ) {
    return "is-warn";
  }
  return "";
}

function countStatusesExcept(statuses, ignored) {
  return Object.entries(statuses).reduce((total, [status, count]) => {
    if (ignored.includes(status)) return total;
    return total + count;
  }, 0);
}

function tokenUsageSummary(value) {
  if (!value || typeof value !== "object") return "";
  const total = value.total_tokens || value.totalTokens;
  const prompt = value.prompt_tokens || value.promptTokens;
  const completion = value.completion_tokens || value.completionTokens;
  if (total) return `tokens ${total}`;
  if (prompt || completion) return `tokens ${prompt || 0}/${completion || 0}`;
  return "";
}

function formatBytes(value) {
  if (value === null || value === undefined) return "";
  const bytes = Number(value);
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function shortText(value, limit) {
  const normalized = text(value).trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 1).trim()}…`;
}

function initToday() {
  document.querySelector("#today-refresh")?.addEventListener("click", loadToday);
  document.querySelector("#today-task-form")?.addEventListener("submit", createTodayTask);
  loadToday();
}

async function loadToday() {
  const status = document.querySelector("#today-status");
  try {
    const payload = await api("/api/today");
    renderTodaySummary(payload);
    renderTodayLeads(payload.leads || []);
    renderTodayTasks(payload.tasks || []);
    renderTodayContactReasons(payload.contact_reasons || []);
    renderTodaySupportCases(payload.support_cases || []);
    renderTodayCatalogCandidates(payload.catalog_candidates || []);
    renderTodayOperationalIssues(payload.operational_issues || []);
    if (status) status.textContent = `Updated ${time(payload.generated_at)}`;
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function renderTodaySummary(payload) {
  const target = document.querySelector("#today-summary");
  if (!target) return;
  const counts = payload.counts || {};
  target.innerHTML = `<div class="ops-metric-row today-metric-row">
    ${renderOpsMetric("New leads", counts.new_leads || 0, `${counts.maybe_leads || 0} maybe`)}
    ${renderOpsMetric("Due tasks", counts.due_tasks || 0, `${counts.overdue_tasks || 0} overdue`, counts.overdue_tasks ? "is-danger" : "")}
    ${renderOpsMetric("Contact reasons", counts.contact_reasons || 0, "clients to contact")}
    ${renderOpsMetric("Support", counts.support_cases || 0, "open cases", counts.support_cases ? "is-warn" : "")}
    ${renderOpsMetric("Catalog", counts.catalog_candidates || 0, "pending facts")}
    ${renderOpsMetric("Issues", counts.operational_issues || 0, "errors", counts.operational_issues ? "is-danger" : "")}
  </div>`;
}

function renderTodayLeads(items) {
  const target = document.querySelector("#today-leads");
  if (!target) return;
  target.innerHTML =
    items.map(renderTodayLead).join("") || '<div class="empty-state">No new leads</div>';
}

function renderTodayLead(item) {
  const confidence = Math.round((item.confidence_max || 0) * 100);
  return `<div class="table-row today-row">
    <div>
      <strong>${escapeHtml(shortText(item.message_text || item.summary || "Lead", 180))}</strong>
      <p class="muted">${escapeHtml(item.primary_sender_name || "unknown sender")}</p>
      <div class="queue-meta">
        ${badge(item.status || "new", todayStatusClass(item.status))}
        ${badge(`${confidence}%`)}
        ${item.telegram_message_id ? badge(`message ${item.telegram_message_id}`) : ""}
      </div>
    </div>
    <a href="/" aria-label="Open lead inbox">Open</a>
  </div>`;
}

function renderTodayTasks(items) {
  const target = document.querySelector("#today-tasks");
  if (!target) return;
  target.innerHTML =
    items.map(renderTodayTask).join("") || '<div class="empty-state">No due tasks</div>';
  target.querySelectorAll("[data-today-task-action]").forEach((button) => {
    button.addEventListener("click", () =>
      todayTaskAction(button.dataset.taskId, button.dataset.todayTaskAction)
    );
  });
}

function renderTodayTask(task) {
  return `<div class="table-row today-row">
    <div>
      <strong>${escapeHtml(task.title || "Task")}</strong>
      <p class="muted">${escapeHtml(task.description || time(task.due_at) || "")}</p>
      <div class="queue-meta">
        ${badge(task.status || "open", todayStatusClass(task.status))}
        ${badge(task.priority || "normal", todayPriorityClass(task.priority))}
        ${task.due_at ? badge(time(task.due_at), todayDueClass(task.due_at)) : ""}
      </div>
    </div>
    <div class="row-actions">
      <button type="button" data-task-id="${escapeHtml(task.id)}" data-today-task-action="complete">Done</button>
      <button type="button" data-task-id="${escapeHtml(task.id)}" data-today-task-action="snooze">Snooze</button>
    </div>
  </div>`;
}

function renderTodayContactReasons(items) {
  const target = document.querySelector("#today-contact-reasons");
  if (!target) return;
  target.innerHTML =
    items.map(renderTodayContactReason).join("") ||
    '<div class="empty-state">No contact reasons</div>';
  target.querySelectorAll("[data-today-contact-action]").forEach((button) => {
    button.addEventListener("click", () =>
      todayContactReasonAction(button.dataset.reasonId, button.dataset.todayContactAction)
    );
  });
}

function renderTodayContactReason(item) {
  const client = item.client || {};
  return `<div class="table-row today-row">
    <div>
      <strong>${escapeHtml(item.title || "Contact reason")}</strong>
      <p class="muted">${escapeHtml(client.display_name || item.reason_text || "")}</p>
      <div class="queue-meta">
        ${badge(item.status || "new", todayStatusClass(item.status))}
        ${badge(item.priority || "normal", todayPriorityClass(item.priority))}
        ${item.due_at ? badge(time(item.due_at), todayDueClass(item.due_at)) : ""}
      </div>
    </div>
    <div class="row-actions">
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="accept">Accept</button>
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="done">Done</button>
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="snooze">Snooze</button>
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="dismiss">Dismiss</button>
    </div>
  </div>`;
}

function renderTodaySupportCases(items) {
  const target = document.querySelector("#today-support-cases");
  if (!target) return;
  target.innerHTML =
    items.map((item) => {
      const client = item.client || {};
      return `<div class="table-row">
        <div>
          <strong>${escapeHtml(item.title || "Support case")}</strong>
          <p class="muted">${escapeHtml(client.display_name || item.issue_text || "")}</p>
        </div>
        <span>${badge(item.priority || item.status || "open", todayPriorityClass(item.priority))}</span>
      </div>`;
    }).join("") || '<div class="empty-state">No support cases</div>';
}

function renderTodayCatalogCandidates(items) {
  const target = document.querySelector("#today-catalog-candidates");
  if (!target) return;
  target.innerHTML =
    items.map((item) => {
      const value = item.normalized_value_json || item.normalized_value || {};
      const subtitle = [item.candidate_type, value.category_slug, value.item_type]
        .filter(Boolean)
        .join(" / ");
      return `<div class="table-row">
        <div>
          <strong>${escapeHtml(item.canonical_name || "Catalog candidate")}</strong>
          <p class="muted">${escapeHtml(subtitle || item.proposed_action || "")}</p>
        </div>
        <span>${badge(item.status || "pending", catalogStatusClass(item.status))}</span>
      </div>`;
    }).join("") || '<div class="empty-state">No catalog candidates</div>';
}

function renderTodayOperationalIssues(items) {
  const target = document.querySelector("#today-operational-issues");
  if (!target) return;
  target.innerHTML =
    items.map((item) => `<div class="table-row">
      <div>
        <strong>${escapeHtml(item.event_type || "event")}</strong>
        <p class="muted">${escapeHtml(shortText(item.message || "", 120))}</p>
      </div>
      <span>${badge(item.severity || "error", operationsStatusClass(item.severity))}</span>
    </div>`).join("") || '<div class="empty-state">No operational issues</div>';
}

async function createTodayTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#today-status");
  const data = new FormData(form);
  try {
    await api("/api/today/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: data.get("title"),
        description: data.get("description") || null,
        priority: data.get("priority") || "normal",
        due_at: toIsoOrNull(data.get("due_at")),
      }),
    });
    form.reset();
    if (status) status.textContent = "Task created";
    await loadToday();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function todayTaskAction(taskId, action) {
  if (!taskId || !action) return;
  const status = document.querySelector("#today-status");
  const endpoints = {
    complete: { path: `/api/today/tasks/${taskId}/complete`, body: {} },
    snooze: { path: `/api/today/tasks/${taskId}/snooze`, body: { due_at: nextMorningIso() } },
  };
  const endpoint = endpoints[action];
  if (!endpoint) return;
  try {
    await api(endpoint.path, {
      method: "POST",
      body: JSON.stringify(endpoint.body),
    });
    await loadToday();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function todayContactReasonAction(reasonId, action) {
  if (!reasonId || !action) return;
  const status = document.querySelector("#today-status");
  const endpoints = {
    accept: { path: `/api/today/contact-reasons/${reasonId}/accept`, body: {} },
    done: { path: `/api/today/contact-reasons/${reasonId}/done`, body: {} },
    dismiss: { path: `/api/today/contact-reasons/${reasonId}/dismiss`, body: {} },
    snooze: {
      path: `/api/today/contact-reasons/${reasonId}/snooze`,
      body: { snoozed_until: nextMorningIso() },
    },
  };
  const endpoint = endpoints[action];
  if (!endpoint) return;
  try {
    await api(endpoint.path, {
      method: "POST",
      body: JSON.stringify(endpoint.body),
    });
    await loadToday();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function todayStatusClass(status) {
  if (status === "maybe" || status === "snoozed" || status === "auto_pending") return "is-warn";
  if (status === "failed" || status === "rejected" || status === "critical") return "is-danger";
  return "";
}

function todayPriorityClass(priority) {
  if (priority === "urgent") return "is-danger";
  if (priority === "high") return "is-warn";
  return "";
}

function todayDueClass(value) {
  const due = new Date(value);
  if (Number.isNaN(due.valueOf())) return "";
  return due < new Date() ? "is-danger" : "";
}

function toIsoOrNull(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date.toISOString();
}

function nextMorningIso() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(9, 0, 0, 0);
  return date.toISOString();
}

let adminAiRegistry = null;

async function initAdmin() {
  await Promise.all([loadUsers(), loadUserbots(), loadSettings(), loadAiRegistry()]);
  document.querySelector("#telegram-admin-form")?.addEventListener("submit", addTelegramAdmin);
  document.querySelector("#userbot-form")?.addEventListener("submit", addUserbot);
  document.querySelector("#setting-form")?.addEventListener("submit", saveSetting);
  document.querySelector("#ai-registry-refresh")?.addEventListener("click", loadAiRegistry);
  document.querySelector("#ai-route-form")?.addEventListener("submit", saveAiRoute);
}

async function loadUsers() {
  const payload = await api("/api/admin/users");
  const target = document.querySelector("#admin-users");
  if (!target) return;
  target.innerHTML = (payload.items || [])
    .map(
      (user) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(user.display_name || user.local_username || user.telegram_username)}</strong>
          <p class="muted">${escapeHtml(user.auth_type)} / ${escapeHtml(user.status)}</p>
        </div>
        <span>${escapeHtml(user.role)}</span>
      </div>`
    )
    .join("");
}

async function addTelegramAdmin(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  await api("/api/admin/users/telegram", {
    method: "POST",
    body: JSON.stringify(Object.fromEntries(data.entries())),
  });
  event.currentTarget.reset();
  await loadUsers();
}

async function loadUserbots() {
  const payload = await api("/api/admin/userbots");
  const target = document.querySelector("#userbot-accounts");
  if (!target) return;
  target.innerHTML =
    (payload.items || [])
      .map(
        (account) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(account.display_name)}</strong>
          <p class="muted">${escapeHtml(account.session_name)} / ${escapeHtml(account.status)}</p>
        </div>
        <span>${escapeHtml(account.priority)}</span>
      </div>`
      )
      .join("") || '<div class="empty-state">No userbots</div>';
}

async function addUserbot(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  await api("/api/admin/userbots", {
    method: "POST",
    body: JSON.stringify({
      display_name: data.get("display_name"),
      session_name: data.get("session_name"),
      session_path: data.get("session_path"),
      make_default: data.get("make_default") === "on",
    }),
  });
  form.reset();
  form.querySelector('[name="make_default"]').checked = true;
  await Promise.all([loadUserbots(), loadSettings()]);
}

async function loadSettings() {
  const payload = await api("/api/settings");
  const target = document.querySelector("#settings-list");
  if (!target) return;
  target.innerHTML = (payload.items || [])
    .map(
      (setting) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(setting.key)}</strong>
          <p class="muted">${escapeHtml(setting.value_type)}${setting.is_default ? " / default" : ""}</p>
        </div>
        <span>${escapeHtml(JSON.stringify(setting.value))}</span>
      </div>`
    )
    .join("");
}

async function saveSetting(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const key = data.get("key");
  const valueType = data.get("value_type");
  await api(`/api/settings/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify({
      value: parseSettingValue(data.get("value"), valueType),
      value_type: valueType,
      reason: "web admin update",
    }),
  });
  event.currentTarget.reset();
  await loadSettings();
}

async function loadAiRegistry() {
  const status = document.querySelector("#ai-registry-status");
  if (status) status.textContent = "";
  try {
    adminAiRegistry = await api("/api/admin/ai-registry");
    renderAiRegistry(adminAiRegistry);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function renderAiRegistry(registry) {
  renderAiRouteForm(registry);
  renderAiModels(registry.models || []);
  renderAiRoutes(registry.routes || []);
}

function renderAiRouteForm(registry) {
  const form = document.querySelector("#ai-route-form");
  if (!form) return;
  const agentSelect = form.querySelector('[name="agent_key"]');
  const modelSelect = form.querySelector('[name="model_id"]');
  if (agentSelect) {
    agentSelect.innerHTML = (registry.agents || [])
      .map((agent) => `<option value="${escapeHtml(agent.agent_key)}">${escapeHtml(agent.agent_key)}</option>`)
      .join("");
  }
  if (modelSelect) {
    modelSelect.innerHTML = (registry.models || [])
      .map(
        (model) =>
          `<option value="${escapeHtml(model.id)}">${escapeHtml(model.model_type)} / ${escapeHtml(
            model.provider_model_name
          )}</option>`
      )
      .join("");
  }
}

function renderAiModels(models) {
  const target = document.querySelector("#ai-models");
  if (!target) return;
  target.innerHTML =
    models
      .map((model) => {
        const limit = model.limit || {};
        return `<form class="table-row ai-limit-form" data-limit-id="${escapeHtml(limit.id || "")}">
          <div>
            <strong>${escapeHtml(model.provider_model_name)}</strong>
            <p class="muted">${escapeHtml(model.model_type)} / ${escapeHtml(model.status)}</p>
          </div>
          <div class="row-actions">
            <input class="compact-input" name="raw_limit" type="number" min="1" step="1"
              value="${escapeHtml(limit.raw_limit || 1)}" aria-label="Raw concurrency">
            <input class="compact-input" name="utilization_ratio" type="number" min="0.1" max="1"
              step="0.05" value="${escapeHtml(limit.utilization_ratio || 0.8)}"
              aria-label="Utilization ratio">
            <span class="badge">eff ${escapeHtml(limit.effective_limit || 1)}</span>
            <button type="submit">Save</button>
          </div>
        </form>`;
      })
      .join("") || '<div class="empty-state">No models</div>';
  target.querySelectorAll(".ai-limit-form").forEach((form) => {
    form.addEventListener("submit", saveAiLimit);
  });
}

function renderAiRoutes(routes) {
  const target = document.querySelector("#ai-routes");
  if (!target) return;
  target.innerHTML =
    routes
      .map(
        (route) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(route.agent_key)} / ${escapeHtml(route.route_role)}</strong>
          <p class="muted">${escapeHtml(route.model)} / priority ${escapeHtml(route.priority)}</p>
        </div>
        <div class="row-actions">
          ${badge(route.enabled ? "enabled" : "disabled", route.enabled ? "" : "is-warn")}
          <button type="button" data-route-id="${escapeHtml(route.id)}" data-enabled="${
            route.enabled ? "false" : "true"
          }">${route.enabled ? "Disable" : "Enable"}</button>
        </div>
      </div>`
      )
      .join("") || '<div class="empty-state">No routes</div>';
  target.querySelectorAll("[data-route-id]").forEach((button) => {
    button.addEventListener("click", toggleAiRoute);
  });
}

async function saveAiLimit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#ai-registry-status");
  const limitId = form.dataset.limitId;
  if (!limitId) return;
  const data = new FormData(form);
  try {
    await api(`/api/admin/ai-model-limits/${encodeURIComponent(limitId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        raw_limit: Number.parseInt(data.get("raw_limit"), 10),
        utilization_ratio: Number.parseFloat(data.get("utilization_ratio")),
      }),
    });
    if (status) status.textContent = "Model limit saved";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function saveAiRoute(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#ai-registry-status");
  const data = new FormData(form);
  const agentKey = data.get("agent_key");
  try {
    await api(`/api/admin/ai-agents/${encodeURIComponent(agentKey)}/routes`, {
      method: "POST",
      body: JSON.stringify({
        model_id: data.get("model_id"),
        route_role: data.get("route_role"),
        priority: Number.parseInt(data.get("priority"), 10),
        max_output_tokens: data.get("max_output_tokens")
          ? Number.parseInt(data.get("max_output_tokens"), 10)
          : null,
        enabled: data.get("enabled") === "on",
        structured_output_required: true,
      }),
    });
    if (status) status.textContent = "Route saved";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function toggleAiRoute(event) {
  const button = event.currentTarget;
  const status = document.querySelector("#ai-registry-status");
  try {
    await api(`/api/admin/ai-routes/${encodeURIComponent(button.dataset.routeId)}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: button.dataset.enabled === "true" }),
    });
    if (status) status.textContent = "Route updated";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function parseSettingValue(value, valueType) {
  if (valueType === "bool") return value === "true";
  if (valueType === "int") return Number.parseInt(value, 10);
  if (valueType === "float") return Number.parseFloat(value);
  if (valueType === "json") return JSON.parse(value);
  return value;
}
