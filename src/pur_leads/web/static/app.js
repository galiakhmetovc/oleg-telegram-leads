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
  </div>`;
  target.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => applyLeadAction(cluster.cluster_id, button.dataset.action));
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
