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
  const state = { items: [], selectedId: null };
  const form = document.querySelector("#lead-filters");
  form?.addEventListener("change", () => loadLeads(state));
  form?.addEventListener("input", () => loadLeads(state));
  loadLeads(state);
}

async function loadLeads(state) {
  const params = new URLSearchParams();
  const form = document.querySelector("#lead-filters");
  if (form) {
    const data = new FormData(form);
    for (const [key, value] of data.entries()) {
      if (value === "on") params.set(key, "true");
      else if (value) params.set(key, value);
    }
  }
  const payload = await api(`/api/leads?${params.toString()}`);
  state.items = payload.items || [];
  const selectedStillVisible = state.items.some((item) => item.cluster_id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.cluster_id || null;
  renderSignals(state.items);
  renderQueue(state);
  if (state.selectedId) {
    await loadDetail(state.selectedId);
  } else {
    const detail = document.querySelector("#lead-detail");
    if (detail) detail.innerHTML = `<div class="empty-state">Select a lead</div>`;
  }
}

function renderSignals(items) {
  const autoPending = items.filter((item) => item.has_auto_pending).length;
  const retro = items.filter((item) => item.is_retro).length;
  const maybe = items.filter((item) => item.is_maybe).length;
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
  try {
    const payload = await api("/api/sources", {
      method: "POST",
      body: JSON.stringify({
        input_ref: data.get("input_ref"),
        purpose: data.get("purpose"),
        check_access: data.get("check_access") === "on",
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

function catalogStatusClass(status) {
  if (status === "auto_pending" || status === "needs_review") return "is-warn";
  if (status === "rejected" || status === "muted") return "is-danger";
  return "";
}

function shortText(value, limit) {
  const normalized = text(value).trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 1).trim()}…`;
}

async function initAdmin() {
  await Promise.all([loadUsers(), loadUserbots(), loadSettings()]);
  document.querySelector("#telegram-admin-form")?.addEventListener("submit", addTelegramAdmin);
  document.querySelector("#userbot-form")?.addEventListener("submit", addUserbot);
  document.querySelector("#setting-form")?.addEventListener("submit", saveSetting);
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

function parseSettingValue(value, valueType) {
  if (valueType === "bool") return value === "true";
  if (valueType === "int") return Number.parseInt(value, 10);
  if (valueType === "float") return Number.parseFloat(value);
  if (valueType === "json") return JSON.parse(value);
  return value;
}
