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

async function initAdmin() {
  await Promise.all([loadUsers(), loadSettings()]);
  document.querySelector("#telegram-admin-form")?.addEventListener("submit", addTelegramAdmin);
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
