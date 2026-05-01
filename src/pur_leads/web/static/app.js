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
    throw new Error(payload.detail || `Ошибка запроса: ${response.status}`);
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
  return date.toLocaleString("ru-RU");
};

const badge = (label, className = "") =>
  `<span class="badge ${className}">${escapeHtml(label)}</span>`;

const catalogHelp = (value) => `<small class="field-help">${escapeHtml(value)}</small>`;

const LABELS = {
  active: "активен",
  admin: "администратор",
  access_denied: "доступ запрещен",
  approved: "подтверждено",
  audio: "аудио",
  auto_pending: "автодобавлено",
  both: "оба сценария",
  catalog: "каталог",
  catalog_ingestion: "наполнение каталога",
  checking_access: "проверка доступа",
  completed: "завершено",
  company: "компания",
  critical: "критично",
  deprecated: "устарело",
  disabled: "отключен",
  document: "документы",
  draft: "черновик",
  ensemble: "ансамбль",
  error: "ошибка",
  expired: "истекло",
  failed: "ошибка",
  fallback: "резерв",
  from_beginning: "с самого начала",
  from_message: "с сообщения",
  from_now: "с текущего момента",
  after_message: "после сообщения",
  family: "семья",
  flood_wait: "лимит Telegram",
  high: "высокий",
  hoa_tsn: "ТСЖ / ТСН",
  in_work: "в работе",
  interested: "интересуется",
  item: "сущность",
  lead: "лид",
  lead_phrase: "признак запроса",
  lead_monitoring: "поиск лидов",
  leads: "лиды",
  language_model: "языковая модель",
  low: "низкий",
  manual: "вручную",
  manual_test: "ручной тест",
  maybe: "возможно",
  muted: "скрыто",
  negative_phrase: "исключающий признак",
  new: "новый",
  needs_review: "на проверке",
  none: "нет",
  normal: "обычный",
  not_lead: "не лид",
  open: "открыто",
  offer: "условие",
  other: "другое",
  paused: "пауза",
  pending: "ожидает",
  person: "человек",
  price: "параметр",
  product: "предмет",
  promotion: "временное условие",
  photo: "фото",
  preview_ready: "превью готово",
  primary: "основной",
  queued: "в очереди",
  recent_days: "за N дней",
  recent_limit: "последние N сообщений",
  since_checkpoint: "с последнего чекпоинта",
  since_date: "с даты",
  source_start: "как настроен источник",
  rejected: "отклонено",
  residential_complex: "жилой комплекс",
  running: "выполняется",
  service: "действие/сервис",
  service_price: "условие сервиса",
  shadow: "теневой",
  split: "разделение",
  snoozed: "отложено",
  solution: "сценарий/решение",
  succeeded: "успешно",
  suppressed: "подавлено",
  telegram: "Telegram",
  telegram_group: "Telegram-группа",
  telegram_supergroup: "Telegram-супергруппа",
  telegram_channel: "Telegram-канал",
  text: "текст",
  terms: "условия",
  unknown: "неизвестно",
  urgent: "срочно",
  verified: "проверено",
  video: "видео",
  warning: "предупреждение",
  raw_export: "сырой экспорт",
  lead_candidate_discovery: "кандидаты лидов",
  lead_candidate_llm_arbitration: "LLM-арбитраж лидов",
  telegram_lead_candidate_llm_arbitration: "LLM-арбитраж лидов",
  telegram_lead_candidate_discovery: "кандидаты лидов",
  json: "JSON",
  jsonl: "JSONL",
  parquet: "Parquet",
  sqlite: "SQLite",
  directory: "папка",
  filesystem_discovery: "найдено на диске",
  metadata_json: "metadata запуска",
  telegram_raw_export_runs: "raw export run",
};

const label = (value, fallback = "") => LABELS[value] || text(value, fallback);

const escapeHtml = (value) =>
  text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const materialFieldSelector = (name) =>
  [
    `md-outlined-text-field[name="${name}"]`,
    `md-filled-text-field[name="${name}"]`,
    `md-checkbox[name="${name}"]`,
  ].join(", ");

const formValue = (form, name, fallback = "") => {
  const field = form?.querySelector(materialFieldSelector(name)) || form?.querySelector(`[name="${name}"]`);
  if (field && "value" in field) return field.value ?? fallback;
  const value = new FormData(form).get(name);
  return value ?? fallback;
};

const formChecked = (form, name) => {
  const field = form?.querySelector(`md-checkbox[name="${name}"]`) || form?.querySelector(`[name="${name}"]`);
  if (field && "checked" in field) return Boolean(field.checked);
  return new FormData(form).get(name) === "on";
};

document.addEventListener("DOMContentLoaded", () => {
  bindLogout();
  if (page === "login") bindLogin();
  if (page === "leads-inbox") initInbox();
  if (page === "sources") initSources();
  if (page === "catalog") initCatalog();
  if (page === "crm") initCrm();
  if (page === "today") initToday();
  if (page === "operations") initOperations();
  if (page === "artifacts") initArtifacts();
  if (page === "quality") initQuality();
  if (page === "admin") initAdmin();
  if (page === "onboarding") initOnboarding();
  if (page === "resources") initResources();
  if (page === "users") initUsersPage();
  if (page === "settings") initSettingsPage();
  if (page === "ai-registry") initAiRegistryPage();
  if (page === "task-executors") initTaskExecutors();
  if (page === "task-types") initTaskTypes();
});

function bindLogin() {
  const form = document.querySelector("#local-login-form");
  const status = document.querySelector("#login-status");
  const changeForm = document.querySelector("#change-password-form");
  const changeStatus = document.querySelector("#change-password-status");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "";
    const username = formValue(form, "username");
    try {
      const payload = await api("/api/auth/local", {
        method: "POST",
        body: JSON.stringify({
          username,
          password: formValue(form, "password"),
        }),
      });
      if (payload.user?.must_change_password) {
        form.classList.add("is-hidden");
        changeForm?.classList.remove("is-hidden");
        changeForm?.querySelector('[name="new_password"]')?.focus();
        return;
      }
      await redirectAfterAuth();
    } catch (error) {
      status.textContent = error.message;
    }
  });
  changeForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    changeStatus.textContent = "";
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ new_password: formValue(changeForm, "new_password") }),
      });
      await redirectAfterAuth();
    } catch (error) {
      changeStatus.textContent = error.message;
    }
  });
}

async function redirectAfterAuth() {
  window.location.assign("/");
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
    if (detail) detail.innerHTML = `<div class="empty-state">Выберите лид</div>`;
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
    target.innerHTML = `<div class="empty-state">Лидов нет</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((item) => {
      const active = item.cluster_id === state.selectedId ? "is-active" : "";
      const markers = [
        item.has_auto_pending ? badge("автодобавлено", "is-warn") : "",
        item.has_auto_merge_pending ? badge("объединение", "is-warn") : "",
        item.is_retro ? badge("ретро") : "",
        item.is_maybe ? badge("возможно") : "",
      ].join("");
      return `<button class="queue-item ${active}" type="button" data-id="${item.cluster_id}">
        <strong>${escapeHtml(item.primary_message?.text || label(item.status))}</strong>
        <span class="muted">${escapeHtml(item.category?.name || "Без категории")}</span>
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
        <h2>${escapeHtml(cluster.primary_message?.text || label(cluster.status, "Лид"))}</h2>
        <p class="muted">${escapeHtml(senderName)}</p>
      </div>
      <div class="badges">
        ${badge(label(cluster.status || "new"))}
        ${badge(label(cluster.work_outcome || "none"))}
        ${cluster.has_auto_pending ? badge("автодобавлено", "is-warn") : ""}
        ${cluster.is_retro ? badge("ретро") : ""}
        ${cluster.is_maybe ? badge("возможно") : ""}
      </div>
    </header>
    <section class="detail-section">
      <h3>Источник</h3>
      <div class="detail-meta">
        ${badge(`источник ${cluster.source_id || "н/д"}`)}
        ${badge(`сообщение ${cluster.primary_message?.telegram_message_id || "н/д"}`)}
        ${badge(`classifier_version_id ${classifierVersionId}`)}
        ${badge(`crm_candidate_count ${crmCandidateCount}`)}
        ${badge(`primary_task_id ${cluster.primary_task_id || "н/д"}`)}
        ${badge(`объединение ${cluster.merge_reason || cluster.merge_strategy || "нет"}`)}
      </div>
      ${
        messageUrl
          ? `<a href="${escapeHtml(messageUrl)}" target="_blank" rel="noreferrer">Открыть сообщение</a>`
          : ""
      }
    </section>
    <section class="detail-section">
      <h3>Совпадения</h3>
      <div class="table-list">
        ${matches.map(renderMatch).join("") || '<div class="empty-state">Совпадений нет</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Хронология</h3>
      <div class="timeline">
        ${(detail.timeline || []).map(renderTimelineEntry).join("") || '<div class="empty-state">Событий нет</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Обратная связь</h3>
      <div class="table-list">
        ${feedback.map(renderFeedback).join("") || '<div class="empty-state">Обратной связи нет</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Действия</h3>
      <div class="detail-meta">
        <button type="button" data-action="take_into_work">Взять в работу</button>
        <button type="button" data-action="maybe">Возможно</button>
        <button type="button" data-action="not_lead">Не лид</button>
      </div>
    </section>
    <section class="detail-section">
      <h3>Перенос в CRM</h3>
      <form id="lead-crm-convert-form" class="inline-form">
        <input name="display_name" value="${escapeHtml(senderName || "Новый клиент")}" required>
        <input name="interest_text" value="${escapeHtml(cluster.primary_message?.text || "")}" required>
        <input name="task_title" value="Связаться с клиентом" required>
        <button type="submit">Перенести</button>
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
    status.textContent = "Сохранено";
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
    if (status) status.textContent = "Перенесено в CRM";
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
    if (detail) detail.innerHTML = `<div class="empty-state">Клиентов нет</div>`;
  }
}

function renderCrmList(state) {
  const target = document.querySelector("#crm-client-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">Клиентов нет</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((client) => {
      const active = client.id === state.selectedId ? "is-active" : "";
      return `<button class="queue-item ${active}" type="button" data-id="${client.id}">
        <strong>${escapeHtml(client.display_name)}</strong>
        <span class="muted">${escapeHtml(label(client.client_type))} / ${escapeHtml(label(client.status))}</span>
        <span class="queue-meta">${badge(label(client.source_type))}${badge(time(client.updated_at) || "новый")}</span>
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
        <h2>${escapeHtml(client.display_name || "Клиент")}</h2>
        <p class="muted">${escapeHtml(label(client.client_type || "unknown"))}</p>
      </div>
      <div class="badges">
        ${badge(label(client.status || "active"))}
        ${badge(label(client.source_type || "manual"))}
      </div>
    </header>
    ${crmSection("Контакты", profile.contacts, renderCrmContact)}
    ${crmSection("Объекты", profile.objects, renderCrmObject)}
    ${crmSection("Интересы", profile.interests, renderCrmInterest)}
    ${crmSection("Оборудование", profile.assets, renderCrmAsset)}
    ${crmSection("Поводы связаться", profile.contact_reasons, renderCrmReason)}
    ${crmSection("Касания", profile.touchpoints, renderCrmTouchpoint)}
  </div>`;
}

function crmSection(title, rows, renderer) {
  return `<section class="detail-section">
    <h3>${escapeHtml(title)}</h3>
    <div class="table-list">
      ${(rows || []).map(renderer).join("") || '<div class="empty-state">Нет данных</div>'}
    </div>
  </section>`;
}

function renderCrmContact(contact) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(contact.contact_name || contact.telegram_username || contact.telegram_user_id || "Контакт")}</strong>
      <p class="muted">${escapeHtml(label(contact.preferred_channel || "unknown"))}</p>
    </div>
    <span>${contact.is_primary ? "основной" : ""}</span>
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
    if (status) status.textContent = "Создано";
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
    if (detail) detail.innerHTML = `<div class="empty-state">Источников нет</div>`;
  }
}

function renderSourceList(state) {
  const target = document.querySelector("#source-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">Источников нет</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((source) => {
      const active = source.id === state.selectedId ? "is-active" : "";
      const sourceTitle = source.title || source.username || source.input_ref;
      const statusClass = sourceStatusClass(source.status);
      return `<button class="queue-item ${active}" type="button" data-id="${source.id}">
        <strong>${escapeHtml(sourceTitle)}</strong>
        <span class="muted">${escapeHtml(label(source.source_kind))} / ${escapeHtml(label(source.source_purpose))}</span>
        <span class="queue-meta">
          ${badge(label(source.status), statusClass)}
          ${source.lead_detection_enabled ? badge("лиды") : ""}
          ${source.catalog_ingestion_enabled ? badge("каталог") : ""}
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
  const access = detail.access_summary || {};
  const labelText = source.title || source.username || source.input_ref || "Источник";
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(labelText)}</h2>
        <p class="muted">${escapeHtml(source.input_ref || "")}</p>
      </div>
      <div class="badges">
        ${badge(label(source.status || "draft"), sourceStatusClass(source.status))}
        ${badge(label(source.source_kind || "telegram"))}
        ${badge(label(source.priority || "normal"))}
        ${access.label ? badge(access.label, accessSeverityClass(access.severity)) : ""}
      </div>
    </header>
    ${renderAccessSummary(access)}
    <section class="detail-section">
      <h3>Конфигурация</h3>
      <div class="detail-meta">
        ${badge(`назначение ${label(source.source_purpose || "н/д")}`)}
        ${badge(`старт ${label(source.start_mode || "from_now")}`)}
        ${badge(`опрос ${source.poll_interval_seconds || 0}s`)}
        ${badge(`чекпоинт ${source.checkpoint_message_id || "нет"}`)}
        ${badge(`превью ${source.preview_message_count || 0}`)}
        ${source.lead_detection_enabled ? badge("поиск лидов") : ""}
        ${source.catalog_ingestion_enabled ? badge("каталог") : ""}
      </div>
      <p class="muted">следующий опрос: ${escapeHtml(time(source.next_poll_at) || "не запланирован")}</p>
      ${
        source.last_error
          ? `<p class="muted">последняя ошибка: ${escapeHtml(source.last_error)}</p>`
          : ""
      }
    </section>
    <section class="detail-section">
      <h3>Действия</h3>
      <div class="source-action-bar">
        <button type="button" data-source-action="check-access">Проверить доступ</button>
        <button type="button" data-source-action="preview">Получить превью</button>
        <button type="button" data-source-action="activate">Активировать</button>
        <button type="button" data-source-action="pause">Пауза</button>
      </div>
      <form id="source-checkpoint-form" class="checkpoint-form">
        <input name="message_id" type="number" min="1" placeholder="ID сообщения чекпоинта" required>
        <button type="submit">Сбросить чекпоинт</button>
      </form>
    </section>
    ${renderRawExportForm(source)}
    ${sourceSection("Превью сообщений", detail.preview_messages, renderPreviewMessage)}
    ${sourceSection("Проверки доступа", detail.access_checks, renderAccessCheck)}
    ${sourceSection("Задачи", detail.jobs, renderSourceJob)}
  </div>`;
  target.querySelectorAll("[data-source-action]").forEach((button) => {
    button.addEventListener("click", () =>
      sourceAction(source.id, button.dataset.sourceAction, state)
    );
  });
  target.querySelector("#source-checkpoint-form")?.addEventListener("submit", (event) =>
    resetSourceCheckpoint(event, source.id, state)
  );
  target.querySelector("#source-raw-export-form")?.addEventListener("submit", (event) =>
    requestRawExport(event, source.id, state)
  );
}

function renderRawExportForm(source) {
  return `<section class="detail-section">
    <h3>Raw-выгрузка Telegram</h3>
    <p class="muted">Скачивает сообщения один раз в JSON/JSONL/parquet и создает canonical rows без AI-обработки.</p>
    <form id="source-raw-export-form" class="raw-export-form">
      <div class="catalog-form-grid">
        <label>Диапазон
          <select name="range_mode">
            ${[
              "source_start",
              "since_checkpoint",
              "recent_days",
              "since_date",
              "from_message",
              "after_message",
              "from_beginning",
              "from_now",
            ]
              .map(
                (mode) =>
                  `<option value="${mode}" ${
                    mode === "source_start" ? "selected" : ""
                  }>${escapeHtml(label(mode))}</option>`
              )
              .join("")}
          </select>
          ${catalogHelp("source_start берет старт из настройки источника; since_checkpoint безопасно пропускает запуск, если чекпоинта нет.")}
        </label>
        <label>Дней назад
          <input name="recent_days" type="number" min="1" value="${
            source.start_recent_days || 180
          }">
          ${catalogHelp("Используется только для диапазона 'за N дней'.")}
        </label>
        <label>ID сообщения
          <input name="message_id" type="number" min="1" placeholder="например 716254">
          ${catalogHelp("Используется для 'с сообщения' и 'после сообщения'.")}
        </label>
        <label>Дата начала
          <input name="since_date" type="datetime-local">
          ${catalogHelp("Используется только для диапазона 'с даты'.")}
        </label>
        <label>Размер пачки
          <input name="batch_size" type="number" min="1" max="5000" value="1000">
          ${catalogHelp("Сколько сообщений читать за одну пачку Telethon.")}
        </label>
        <label>Максимум сообщений
          <input name="max_messages" type="number" min="1" placeholder="без лимита">
          ${catalogHelp("Пусто означает читать весь выбранный диапазон.")}
        </label>
      </div>
      <div class="source-action-bar raw-export-media">
        <label><input name="media_enabled" type="checkbox"> скачивать медиа</label>
        ${["document", "photo", "video", "audio", "other"]
          .map(
            (type) =>
              `<label><input name="media_types" type="checkbox" value="${type}" ${
                type === "document" ? "checked" : ""
              }> ${escapeHtml(label(type))}</label>`
          )
          .join("")}
        <label>Лимит файла, байт
          <input class="compact-input" name="max_media_size_bytes" type="number" min="1" placeholder="нет">
        </label>
      </div>
      <button type="submit">Поставить raw-выгрузку в очередь</button>
    </form>
  </section>`;
}

function sourceSection(title, rows, renderer) {
  return `<section class="detail-section">
    <h3>${escapeHtml(title)}</h3>
    <div class="table-list">
      ${(rows || []).map(renderer).join("") || '<div class="empty-state">Нет данных</div>'}
    </div>
  </section>`;
}

function renderAccessSummary(access) {
  if (!access || !access.mode) {
    return "";
  }
  const severityClass = accessSeverityClass(access.severity);
  const joinText =
    access.requires_join === true
      ? "вступление требуется"
      : access.requires_join === false
        ? "вступление не требуется"
        : "участие не определено";
  return `<section class="detail-section access-summary ${severityClass}">
    <div>
      <h3>Режим доступа</h3>
      <strong>${escapeHtml(access.label || "Доступ не проверен")}</strong>
      <p class="muted">${escapeHtml(access.description || "")}</p>
    </div>
    <div class="detail-meta">
      ${badge(joinText, severityClass)}
      ${badge(access.can_read_messages ? "сообщения читаются" : "сообщения не читаются", severityClass)}
      ${badge(access.can_read_history ? "история читается" : "история не читается", severityClass)}
      ${access.checked_at ? badge(`проверено ${time(access.checked_at)}`) : ""}
    </div>
  </section>`;
}

function renderPreviewMessage(message) {
  const body = message.text || message.caption || "";
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(body || "Медиа-сообщение")}</strong>
      <p class="muted">${escapeHtml(message.sender_display || "")}</p>
    </div>
    <span>${escapeHtml(message.telegram_message_id)}</span>
  </div>`;
}

function renderAccessCheck(check) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(label(check.status))}</strong>
      <p class="muted">${escapeHtml(check.access_label || check.resolved_title || check.error || check.check_type)}</p>
      ${
        check.access_description
          ? `<p class="muted">${escapeHtml(check.access_description)}</p>`
          : ""
      }
    </div>
    <span>${escapeHtml(time(check.checked_at))}</span>
  </div>`;
}

function accessSeverityClass(severity) {
  if (severity === "ok") return "";
  if (severity === "warning") return "is-warn";
  if (severity === "error") return "is-danger";
  return "";
}

function renderSourceJob(job) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(job.job_type)}</strong>
      <p class="muted">${escapeHtml(job.idempotency_key || job.scope_id || "")}</p>
    </div>
    <span>${escapeHtml(job.status ? label(job.status) : time(job.created_at))}</span>
  </div>`;
}

async function createSource(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#source-status");
  const data = new FormData(form);
  const startMode = data.get("start_mode") || "from_now";
  const startRecentDays = Number.parseInt(data.get("start_recent_days"), 10);
  try {
    const payload = await api("/api/sources", {
      method: "POST",
      body: JSON.stringify({
        input_ref: data.get("input_ref"),
        purpose: data.get("purpose"),
        check_access: data.get("check_access") === "on",
        start_mode: startMode,
        start_recent_days:
          startMode === "recent_days" && !Number.isNaN(startRecentDays) ? startRecentDays : null,
      }),
    });
    form.reset();
    form.querySelector('[name="check_access"]').checked = true;
    if (status) status.textContent = "Создано";
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
    if (status) status.textContent = "Сохранено";
    await loadSources(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function requestRawExport(event, sourceId, state) {
  event.preventDefault();
  const status = document.querySelector("#source-status");
  const data = new FormData(event.currentTarget);
  const numberOrNull = (name) => {
    const value = Number.parseInt(data.get(name), 10);
    return Number.isNaN(value) ? null : value;
  };
  const mediaTypes = data.getAll("media_types");
  try {
    await api(`/api/sources/${sourceId}/raw-export`, {
      method: "POST",
      body: JSON.stringify({
        range_mode: data.get("range_mode") || "source_start",
        recent_days: numberOrNull("recent_days"),
        message_id: numberOrNull("message_id"),
        since_date: data.get("since_date") || null,
        batch_size: numberOrNull("batch_size") || 1000,
        max_messages: numberOrNull("max_messages"),
        media_enabled: data.get("media_enabled") === "on",
        media_types: mediaTypes.length ? mediaTypes : ["document"],
        max_media_size_bytes: numberOrNull("max_media_size_bytes"),
        canonicalize: true,
      }),
    });
    if (status) status.textContent = "Raw-выгрузка поставлена в очередь";
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
    if (status) status.textContent = "Чекпоинт сброшен";
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
  const itemState = { items: [], selectedId: null, detail: null, search: "" };
  const candidateState = { items: [], selectedId: null, detail: null };
  const rawState = { items: [], selectedId: null, detail: null, payload: null };
  const createDialog = document.querySelector("#catalog-item-dialog");
  document.querySelector("#catalog-item-form")?.addEventListener("submit", (event) =>
    submitCatalogItem(event, itemState)
  );
  document.querySelector("#catalog-item-dialog-open")?.addEventListener("click", () => {
    createDialog?.showModal();
    createDialog?.querySelector('[name="name"]')?.focus();
  });
  document.querySelector("#catalog-item-dialog-close")?.addEventListener("click", () =>
    createDialog?.close()
  );
  createDialog?.addEventListener("click", (event) => {
    if (event.target === createDialog) createDialog.close();
  });
  document.querySelector("#catalog-item-search")?.addEventListener("input", (event) => {
    itemState.search = event.currentTarget.value || "";
    renderCatalogItemList(itemState);
  });
  document.querySelector("#catalog-snapshot-rebuild")?.addEventListener("click", () =>
    rebuildCatalogSnapshot(itemState)
  );
  document.querySelector("#catalog-refresh")?.addEventListener("click", () =>
    loadCatalogCandidates(candidateState)
  );
  document.querySelector("#catalog-raw-refresh")?.addEventListener("click", () =>
    loadCatalogRawIngest(rawState)
  );
  document.querySelector("#catalog-filters")?.addEventListener("change", () =>
    loadCatalogCandidates(candidateState)
  );
  document.querySelector("#manual-input-form")?.addEventListener("submit", (event) =>
    submitManualInput(event, candidateState)
  );
  loadCatalogItems(itemState);
  loadCatalogRawIngest(rawState);
  loadCatalogCandidates(candidateState);
}

async function loadCatalogItems(state) {
  const payload = await api("/api/catalog/items?limit=200");
  state.items = payload.items || [];
  const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
  state.detail = null;
  renderCatalogItemList(state);
  if (state.selectedId) {
    await loadCatalogItemDetail(state, state.selectedId);
  } else {
    renderCatalogItemDetail(state);
  }
}

async function loadCatalogItemDetail(state, itemId) {
  const target = document.querySelector("#catalog-item-detail");
  if (target) target.innerHTML = `<div class="empty-state">Загружается сущность каталога</div>`;
  const payload = await api(`/api/catalog/items/${itemId}`);
  if (state.selectedId !== itemId) return;
  state.detail = payload;
  const index = state.items.findIndex((item) => item.id === payload.item.id);
  if (index >= 0) state.items[index] = payload.item;
  renderCatalogItemList(state);
  renderCatalogItemDetail(state);
}

function renderCatalogItemList(state) {
  const target = document.querySelector("#catalog-item-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">Каталог пока пуст</div>`;
    return;
  }
  const query = text(state.search).trim().toLowerCase();
  const visibleItems = query
    ? state.items.filter((item) =>
        [item.name, item.canonical_name, item.item_type, item.status]
          .map((value) => text(value).toLowerCase())
          .some((value) => value.includes(query))
      )
    : state.items;
  if (!visibleItems.length) {
    target.innerHTML = `<div class="empty-state">Ничего не найдено</div>`;
    return;
  }
  target.innerHTML = visibleItems
    .map((item) => {
      const active = item.id === state.selectedId ? "is-active" : "";
      return `<button class="queue-item ${active}" type="button" data-id="${item.id}">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="muted">${escapeHtml(label(item.item_type))}</span>
        <span class="queue-meta">
          ${badge(label(item.status), catalogStatusClass(item.status))}
          ${badge(Math.round((item.confidence || 0) * 100) + "%")}
        </span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.id;
      state.detail = null;
      renderCatalogItemList(state);
      loadCatalogItemDetail(state, state.selectedId);
    });
  });
}

function renderCatalogItemDetail(state) {
  const target = document.querySelector("#catalog-item-detail");
  if (!target) return;
  const detail = state.detail;
  if (!detail?.item) {
    target.innerHTML = `<div class="empty-state">Выберите сущность каталога или добавьте новую</div>`;
    return;
  }
  const item = detail.item;
  const terms = detail.terms || [];
  const offers = detail.offers || [];
  const evidence = detail.evidence || [];
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(item.name)}</h2>
        <p class="muted">${escapeHtml(item.id)}</p>
      </div>
      <div class="badges">
        ${badge(label(item.status), catalogStatusClass(item.status))}
        ${badge(label(item.item_type))}
      </div>
    </header>
    <section class="detail-section">
      <h3>Редактирование</h3>
      <form id="catalog-item-edit-form" class="catalog-edit-form">
        <div class="catalog-form-grid">
          <label>Название
            <input name="name" value="${escapeHtml(item.name)}" required>
            ${catalogHelp("Каноническое имя: коротко, конкретно и без лишних слов. Оно будет видно оператору и попадет в снапшот распознавания.")}
          </label>
          <label>Тип
            <select name="item_type">
              ${["product", "service", "bundle", "solution", "brand", "model"]
                .map(
                  (type) =>
                    `<option value="${type}" ${item.item_type === type ? "selected" : ""}>${escapeHtml(
                      label(type)
                    )}</option>`
                )
                .join("")}
            </select>
            ${catalogHelp("Тип определяет роль сущности в базе знаний: предмет, действие, сценарий, бренд или модель.")}
          </label>
          <label>Статус
            <select name="status">
              ${["approved", "needs_review", "auto_pending", "muted", "deprecated", "expired"]
                .map(
                  (status) =>
                    `<option value="${status}" ${item.status === status ? "selected" : ""}>${escapeHtml(
                      label(status)
                    )}</option>`
                )
                .join("")}
            </select>
            ${catalogHelp("Статус определяет, участвует ли сущность в текущем источнике истины. approved и auto_pending активны, deprecated лучше не использовать для новых совпадений.")}
          </label>
        </div>
        <label>Описание
          <textarea name="description" rows="4">${escapeHtml(item.description || "")}</textarea>
          ${catalogHelp("Описание объясняет смысл сущности, границы применимости, исключения и важные нюансы для оператора и AI.")}
        </label>
        <div class="source-action-bar">
          <button type="submit">Сохранить</button>
          <button type="button" data-catalog-item-archive="${escapeHtml(item.id)}">Архивировать</button>
        </div>
      </form>
    </section>
    <section class="detail-section">
      <h3>Термины</h3>
      <form id="catalog-term-form" class="inline-form">
        <label>Термин
          <input name="term" placeholder="Термин" required>
          ${catalogHelp("Слово, модель, синоним, бренд или фраза, которая связывает сообщение с этой сущностью.")}
        </label>
        <label>Тип термина
          <select name="term_type">
            <option value="keyword">Ключевое слово</option>
            <option value="alias">Синоним</option>
            <option value="lead_phrase">Признак запроса</option>
            <option value="negative_phrase">Исключающий признак</option>
            <option value="brand">Бренд</option>
            <option value="model">Модель</option>
            <option value="problem_phrase">Проблема</option>
          </select>
          ${catalogHelp("Тип помогает отличить нейтральные ключевые слова от признаков запроса и исключающих признаков.")}
        </label>
        <label>Вес
          <input name="weight" type="number" min="0" max="5" step="0.1" value="1">
          ${catalogHelp("Вес: насколько сильно термин влияет на fuzzy match и будущие правила. 1 — обычный сигнал, больше 1 — сильнее.")}
        </label>
        <button type="submit">Добавить</button>
      </form>
      <div class="table-list">${renderCatalogTerms(terms)}</div>
    </section>
    <section class="detail-section">
      <h3>Условия и действия</h3>
      <form id="catalog-offer-form" class="inline-form">
        <label>Название
          <input name="title" placeholder="Название" required>
          ${catalogHelp("Короткое название условия, действия, ограничения или параметра, связанного с сущностью.")}
        </label>
        <label>Параметры
          <input name="price_text" placeholder="Параметры">
          ${catalogHelp("Параметры: срок, цена, доступность, ограничение или другое уточнение. Поле не обязано быть ценой.")}
        </label>
        <label>Тип
          <select name="offer_type">
            <option value="price">Параметр</option>
            <option value="service_price">Сервисное условие</option>
            <option value="bundle_price">Условие набора</option>
            <option value="promotion">Временное условие</option>
            <option value="terms">Условия</option>
          </select>
          ${catalogHelp("Тип показывает, это постоянный параметр, сервисное действие, временное условие или правило применения.")}
        </label>
        <button type="submit">Добавить</button>
      </form>
      <div class="table-list">${renderCatalogOffers(offers)}</div>
    </section>
    <section class="detail-section">
      <h3>Источники</h3>
      ${renderManualCatalogEvidence(evidence)}
    </section>
    <p id="catalog-item-detail-status" class="status-line" role="status"></p>
  </div>`;
  target.querySelector("#catalog-item-edit-form")?.addEventListener("submit", (event) =>
    saveCatalogItemEdit(event, item.id, state)
  );
  target.querySelector("#catalog-term-form")?.addEventListener("submit", (event) =>
    addCatalogTerm(event, item.id, state)
  );
  target.querySelector("#catalog-offer-form")?.addEventListener("submit", (event) =>
    addCatalogOffer(event, item.id, state)
  );
  target.querySelector("[data-catalog-item-archive]")?.addEventListener("click", () =>
    archiveCatalogItem(item.id, state)
  );
  target.querySelectorAll("[data-catalog-term-archive]").forEach((button) => {
    button.addEventListener("click", () => archiveCatalogTerm(button.dataset.catalogTermArchive, state));
  });
  target.querySelectorAll("[data-catalog-offer-archive]").forEach((button) => {
    button.addEventListener("click", () => archiveCatalogOffer(button.dataset.catalogOfferArchive, state));
  });
}

function renderCatalogTerms(terms) {
  if (!terms.length) return `<div class="empty-state">Терминов нет</div>`;
  return terms
    .map(
      (term) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(term.term)}</strong>
          <p class="muted">${escapeHtml(label(term.term_type))} · вес ${escapeHtml(term.weight)}</p>
        </div>
        <div class="source-action-bar">
          ${badge(label(term.status), catalogStatusClass(term.status))}
          <button type="button" data-catalog-term-archive="${escapeHtml(term.id)}">Архив</button>
        </div>
      </div>`
    )
    .join("");
}

function renderCatalogOffers(offers) {
  if (!offers.length) return `<div class="empty-state">Условий нет</div>`;
  return offers
    .map(
      (offer) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(offer.title)}</strong>
          <p class="muted">${escapeHtml([label(offer.offer_type), offer.price_text].filter(Boolean).join(" · "))}</p>
        </div>
        <div class="source-action-bar">
          ${badge(label(offer.status), catalogStatusClass(offer.status))}
          <button type="button" data-catalog-offer-archive="${escapeHtml(offer.id)}">Архив</button>
        </div>
      </div>`
    )
    .join("");
}

function renderManualCatalogEvidence(evidence) {
  if (!evidence.length) return `<div class="empty-state">Источников нет</div>`;
  return `<div class="evidence-list">${evidence
    .map(
      (item) => `<article class="evidence-item">
        <div class="evidence-source">
          <strong>${escapeHtml(label(item.evidence_type))}</strong>
          ${item.confidence ? badge(Math.round(item.confidence * 100) + "%") : ""}
        </div>
        ${item.quote ? `<blockquote>${escapeHtml(item.quote)}</blockquote>` : ""}
        ${item.source_id ? `<p class="muted">source_id ${escapeHtml(item.source_id)}</p>` : ""}
      </article>`
    )
    .join("")}</div>`;
}

async function submitCatalogItem(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#catalog-item-status");
  const data = new FormData(form);
  const name = text(data.get("name")).trim();
  const terms = [
    ...catalogTermLines(data.get("terms"), "keyword"),
    ...catalogTermLines(data.get("lead_phrases"), "lead_phrase"),
    ...catalogTermLines(data.get("negative_phrases"), "negative_phrase"),
  ];
  const offerTitle = text(data.get("offer_title")).trim();
  const offerPriceText = text(data.get("offer_price_text")).trim();
  const evidenceQuote = text(data.get("evidence_quote")).trim();
  const body = {
    name,
    item_type: data.get("item_type") || "product",
    category_slug: text(data.get("category_slug")).trim() || null,
    description: text(data.get("description")).trim() || null,
    terms,
    offers:
      offerTitle || offerPriceText
        ? [{ title: offerTitle || name, price_text: offerPriceText || null, offer_type: "price" }]
        : [],
    evidence: evidenceQuote
      ? { quote: evidenceQuote, source_text: evidenceQuote, evidence_type: "manual_note" }
      : null,
  };
  try {
    const payload = await api("/api/catalog/items", {
      method: "POST",
      body: JSON.stringify(body),
    });
    form.reset();
    document.querySelector("#catalog-item-dialog")?.close();
    state.selectedId = payload.item.id;
    if (status) status.textContent = "Позиция добавлена";
    await loadCatalogItems(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function catalogTermLines(value, termType) {
  return text(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((term) => ({ term, term_type: termType }));
}

async function saveCatalogItemEdit(event, itemId, state) {
  event.preventDefault();
  const status = document.querySelector("#catalog-item-detail-status");
  const data = new FormData(event.currentTarget);
  try {
    const payload = await api(`/api/catalog/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: data.get("name"),
        item_type: data.get("item_type"),
        description: data.get("description") || null,
        status: data.get("status"),
      }),
    });
    state.detail = payload;
    if (status) status.textContent = "Сохранено";
    await loadCatalogItems(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function addCatalogTerm(event, itemId, state) {
  event.preventDefault();
  const status = document.querySelector("#catalog-item-detail-status");
  const data = new FormData(event.currentTarget);
  try {
    await api(`/api/catalog/items/${itemId}/terms`, {
      method: "POST",
      body: JSON.stringify({
        term: data.get("term"),
        term_type: data.get("term_type"),
        weight: Number(data.get("weight") || 1),
      }),
    });
    state.selectedId = itemId;
    await loadCatalogItemDetail(state, itemId);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function addCatalogOffer(event, itemId, state) {
  event.preventDefault();
  const status = document.querySelector("#catalog-item-detail-status");
  const data = new FormData(event.currentTarget);
  try {
    await api(`/api/catalog/items/${itemId}/offers`, {
      method: "POST",
      body: JSON.stringify({
        title: data.get("title"),
        price_text: data.get("price_text") || null,
        offer_type: data.get("offer_type") || "price",
      }),
    });
    state.selectedId = itemId;
    await loadCatalogItemDetail(state, itemId);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function archiveCatalogItem(itemId, state) {
  const status = document.querySelector("#catalog-item-detail-status");
  try {
    await api(`/api/catalog/items/${itemId}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: "manual archive" }),
    });
    await loadCatalogItems(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function archiveCatalogTerm(termId, state) {
  const status = document.querySelector("#catalog-item-detail-status");
  try {
    await api(`/api/catalog/terms/${termId}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: "manual archive" }),
    });
    await loadCatalogItemDetail(state, state.selectedId);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function archiveCatalogOffer(offerId, state) {
  const status = document.querySelector("#catalog-item-detail-status");
  try {
    await api(`/api/catalog/offers/${offerId}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: "manual archive" }),
    });
    await loadCatalogItemDetail(state, state.selectedId);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function rebuildCatalogSnapshot(state) {
  const status = document.querySelector("#catalog-item-status");
  try {
    const payload = await api("/api/catalog/snapshots/rebuild", {
      method: "POST",
      body: JSON.stringify({ reason: "manual catalog editor" }),
    });
    if (status) status.textContent = `Снапшот v${payload.classifier_snapshot.version} собран`;
    await loadCatalogItems(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadCatalogRawIngest(state) {
  const target = document.querySelector("#catalog-raw-message-list");
  if (target) target.innerHTML = `<div class="empty-state">Загружается сырой ингест</div>`;
  const payload = await api("/api/catalog/raw-ingest?limit=50");
  state.payload = payload;
  state.items = payload.messages || [];
  const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
  state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
  state.detail = null;
  renderCatalogRawSummary(payload);
  renderCatalogRawMessages(state);
  if (state.selectedId) {
    await loadCatalogRawMessageDetail(state, state.selectedId);
  } else {
    renderCatalogRawMessageDetail(state);
  }
}

function renderCatalogRawSummary(payload) {
  const target = document.querySelector("#catalog-raw-summary");
  if (!target) return;
  const summary = payload?.summary || {};
  target.innerHTML = `<div class="ops-metric-row catalog-raw-metrics">
    ${renderOpsMetric("Источники", summary.catalog_sources || 0, "каналы каталога")}
    ${renderOpsMetric("Сообщения", summary.messages || 0, "получено из Telegram")}
    ${renderOpsMetric("Raw sources", summary.mirrored_sources || 0, "зеркало источников")}
    ${renderOpsMetric("Документы", summary.artifacts || 0, "скачанные файлы")}
    ${renderOpsMetric("Фрагменты", summary.parsed_chunks || 0, "готово к AI")}
    ${renderOpsMetric("Задачи", summary.pending_jobs || 0, "в очереди", summary.pending_jobs ? "is-warn" : "")}
  </div>`;
}

function renderCatalogRawMessages(state) {
  const target = document.querySelector("#catalog-raw-message-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">Сообщений каталога пока нет</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((item) => {
      const active = item.id === state.selectedId ? "is-active" : "";
      const raw = item.raw_source || {};
      const badges = [
        item.has_media ? badge("медиа") : "",
        raw.chunk_count ? badge(`фрагментов ${raw.chunk_count}`) : "",
        raw.artifact_count ? badge(`документов ${raw.artifact_count}`) : "",
        item.pending_jobs?.length ? badge(`задач ${item.pending_jobs.length}`, "is-warn") : "",
      ]
        .filter(Boolean)
        .join("");
      return `<button class="table-row catalog-raw-message ${active}" type="button" data-raw-message-id="${escapeHtml(item.id)}">
        <div>
          <strong>${escapeHtml(shortText(item.text_excerpt || "Сообщение без текста", 180))}</strong>
          <p class="muted">${escapeHtml([raw.origin, raw.external_id || item.telegram_message_id, time(item.message_date)].filter(Boolean).join(" / "))}</p>
          <div class="queue-meta">${badges}</div>
        </div>
        <span>${escapeHtml(item.telegram_message_id)}</span>
      </button>`;
    })
    .join("");
  target.querySelectorAll("[data-raw-message-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.rawMessageId;
      state.detail = null;
      renderCatalogRawMessages(state);
      loadCatalogRawMessageDetail(state, state.selectedId);
    });
  });
}

async function loadCatalogRawMessageDetail(state, messageId) {
  const target = document.querySelector("#catalog-raw-message-detail");
  if (target) target.innerHTML = `<div class="empty-state">Загружается сообщение</div>`;
  const payload = await api(`/api/catalog/raw-ingest/messages/${messageId}`);
  if (state.selectedId !== messageId) return;
  state.detail = payload;
  renderCatalogRawMessageDetail(state);
}

function renderCatalogRawMessageDetail(state) {
  const target = document.querySelector("#catalog-raw-message-detail");
  if (!target) return;
  const detail = state.detail;
  if (!detail?.message) {
    target.innerHTML = `<div class="empty-state">Выберите сообщение</div>`;
    return;
  }
  const message = detail.message;
  const rawSource = detail.raw_source || {};
  const artifacts = detail.artifacts || [];
  const chunks = detail.chunks || [];
  const jobs = detail.jobs || [];
  target.innerHTML = `<div class="catalog-raw-detail">
    <header class="detail-header">
      <div>
        <h3>Сообщение ${escapeHtml(message.telegram_message_id)}</h3>
        <p class="muted">${escapeHtml(time(message.message_date))}</p>
      </div>
      <div class="badges">
        ${message.has_media ? badge("медиа") : ""}
        ${badge(label(message.classification_status || "unknown"))}
      </div>
    </header>
    <div class="source-action-bar">
      ${message.message_url ? `<a href="${escapeHtml(message.message_url)}" target="_blank" rel="noreferrer">Открыть в Telegram</a>` : ""}
      ${rawSource.id ? badge(`source ${rawSource.external_id || rawSource.id}`) : ""}
    </div>
    <section>
      <h4>Raw text</h4>
      <pre class="json-block catalog-raw-text">${escapeHtml(rawSource.raw_text || message.text_excerpt || "")}</pre>
    </section>
    <section>
      <h4>Фрагменты</h4>
      ${renderCatalogRawChunks(chunks)}
    </section>
    <section>
      <h4>Документы</h4>
      ${renderCatalogRawArtifacts(artifacts)}
    </section>
    <section>
      <h4>Задачи</h4>
      ${renderCatalogRawJobs(jobs)}
    </section>
  </div>`;
}

function renderCatalogRawChunks(chunks) {
  if (!chunks.length) return `<div class="empty-state">Фрагментов нет</div>`;
  return `<div class="table-list">${chunks
    .map(
      (chunk) => `<div class="table-row">
        <div>
          <strong>Фрагмент ${escapeHtml(chunk.chunk_index)}</strong>
          <p class="muted">${escapeHtml([chunk.parser_name, chunk.parser_version, `токенов ${chunk.token_estimate}`].filter(Boolean).join(" / "))}</p>
          <pre class="json-block catalog-raw-chunk">${escapeHtml(chunk.text || "")}</pre>
        </div>
      </div>`
    )
    .join("")}</div>`;
}

function renderCatalogRawArtifacts(artifacts) {
  if (!artifacts.length) return `<div class="empty-state">Документов нет</div>`;
  return `<div class="table-list">${artifacts
    .map(
      (artifact) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(artifact.file_name || artifact.artifact_type)}</strong>
          <p class="muted">${escapeHtml([artifact.mime_type, formatBytes(artifact.file_size), artifact.local_path].filter(Boolean).join(" / "))}</p>
        </div>
        <span>${badge(label(artifact.download_status || "unknown"), operationsStatusClass(artifact.download_status))}</span>
      </div>`
    )
    .join("")}</div>`;
}

function renderCatalogRawJobs(jobs) {
  if (!jobs.length) return `<div class="empty-state">Задач нет</div>`;
  return `<div class="table-list">${jobs
    .map(
      (job) => `<div class="table-row">
        <div>
          <strong>${escapeHtml(job.job_type)}</strong>
          <p class="muted">${escapeHtml(job.last_error || time(job.run_after_at) || job.id)}</p>
        </div>
        <span>${badge(label(job.status || "unknown"), operationsStatusClass(job.status))}</span>
      </div>`
    )
    .join("")}</div>`;
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
  if (target) target.innerHTML = `<div class="empty-state">Загружается кандидат</div>`;
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
    target.innerHTML = `<div class="empty-state">Кандидатов нет</div>`;
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
          ${badge(label(item.status), catalogStatusClass(item.status))}
          ${badge(Math.round((item.confidence || 0) * 100) + "%")}
          ${item.evidence_count ? badge(`доказательств ${item.evidence_count}`) : ""}
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
    target.innerHTML = `<div class="empty-state">Выберите кандидата</div>`;
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
        ${badge(label(item.status), catalogStatusClass(item.status))}
        ${badge(label(item.candidate_type))}
        ${badge(label(item.proposed_action))}
      </div>
    </header>
    <section class="detail-section">
      <h3>Значение</h3>
      <div class="detail-meta">
        ${value.category_slug ? badge(value.category_slug) : ""}
        ${value.item_type ? badge(value.item_type) : ""}
        ${value.price_text ? badge(value.price_text, "is-warn") : ""}
        ${badge(`уверенность ${Math.round((item.confidence || 0) * 100)}%`)}
      </div>
      ${
        value.description
          ? `<p>${escapeHtml(value.description)}</p>`
          : ""
      }
    </section>
    <section class="detail-section">
      <h3>Термины</h3>
      <div class="detail-meta">
        ${terms.map((term) => badge(term)).join("") || '<span class="muted">Терминов нет</span>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>Редактирование</h3>
      <form id="catalog-edit-form" class="catalog-edit-form">
        <label>Название
          <input id="catalog-name-input" name="canonical_name" value="${escapeHtml(item.canonical_name)}">
          ${catalogHelp("Название кандидата после AI-разбора. Исправьте его до канонического вида перед подтверждением.")}
        </label>
        <label>JSON-данные
          <textarea id="catalog-value-json" name="normalized_value" rows="12">${escapeHtml(
            JSON.stringify(value, null, 2)
          )}</textarea>
          ${catalogHelp("JSON-данные должны оставаться валидным JSON. Здесь лежит нормализованное значение кандидата: тип, категория, термины, описание и параметры.")}
        </label>
        <label>Причина
          <input name="reason" placeholder="Необязательная заметка">
          ${catalogHelp("Заметка попадет в аудит и поможет понять, почему кандидат был изменен, подтвержден или отклонен.")}
        </label>
        <div class="source-action-bar">
          <button type="submit">Сохранить изменения</button>
        </div>
      </form>
    </section>
    <section class="detail-section">
      <h3>Доказательства</h3>
      ${renderCatalogEvidence(evidence)}
    </section>
    <section class="detail-section">
      <h3>Проверка</h3>
      <div class="source-action-bar">
        <button type="button" data-catalog-action="approve">Подтвердить</button>
        <button type="button" data-catalog-action="needs_review">На проверку</button>
        <button type="button" data-catalog-action="reject">Отклонить</button>
        <button type="button" data-catalog-action="mute">Скрыть</button>
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
  if (!evidence.length) return `<div class="empty-state">Доказательств нет</div>`;
  return `<div class="evidence-list">${evidence
    .map((item) => {
      const sourceLabel = [item.source?.origin, item.source?.external_id].filter(Boolean).join(" / ");
      const artifactLabel = item.artifact?.file_name || item.artifact?.mime_type || "";
      const chunkText = item.chunk?.text || item.source?.raw_text_excerpt || "";
      return `<article class="evidence-item">
        <div class="evidence-source">
          <strong>${escapeHtml(sourceLabel || "Источник")}</strong>
          ${artifactLabel ? badge(artifactLabel) : ""}
          ${item.chunk ? badge(`фрагмент ${item.chunk.chunk_index}`) : ""}
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
    document.querySelector("#catalog-status").textContent = "Сохранено";
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
    if (status) status.textContent = "Сохранено";
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
    form.querySelector('input[name="auto_extract"]').checked = false;
    if (status) {
      const queued = payload.queued_jobs?.length || 0;
      const snapshot = payload.classifier_snapshot ? `снапшот v${payload.classifier_snapshot.version}` : "";
      const evaluationCase = payload.evaluation_case ? "оценочный кейс" : "";
      status.textContent = ["Сохранено", queued ? `задач в очереди: ${queued}` : "", snapshot, evaluationCase]
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
  const workerCapacity = summary.capacity?.worker_capacity || {};
  const capacityTotals = summary.capacity?.totals || {};
  const bottleneck = (summary.capacity?.bottlenecks || [])[0];
  target.innerHTML = `<div class="ops-metric-row">
    ${renderOpsMetric(
      "Воркеры",
      workerCapacity.configured_worker_concurrency || 0,
      `рекомендовано ${workerCapacity.recommended_worker_concurrency || 0}`,
      bottleneck?.kind === "worker_concurrency" ? "is-warn" : ""
    )}
    ${renderOpsMetric(
      "AI слоты",
      capacityTotals.ai_model_available_slots || 0,
      `${capacityTotals.ai_model_effective_slots || 0} всего`
    )}
    ${renderOpsMetric(
      "Юзерботы",
      capacityTotals.telegram_userbot_effective_slots || 0,
      "чтение Telegram"
    )}
    ${renderOpsMetric(
      "Боты",
      capacityTotals.telegram_bot_effective_slots || 0,
      "уведомления"
    )}
    ${renderOpsMetric("Задачи", summary.jobs?.total || 0, `${queuedJobs} в очереди / ${runningJobs} выполняется`)}
    ${renderOpsMetric("Ошибки задач", failedJobs, "нужна проверка оператора", failedJobs ? "is-danger" : "")}
    ${renderOpsMetric("Запуски", summary.runs?.total || 0, "попытки воркеров")}
    ${renderOpsMetric("Ошибки", errorEvents, "операционные события", errorEvents ? "is-danger" : "")}
    ${renderOpsMetric("Уведомления", summary.notifications?.total || 0, `${suppressedNotifications} подавлено`)}
    ${renderOpsMetric("Извлечение", summary.extraction_runs?.total || 0, `${failedExtractions} ошибок`, failedExtractions ? "is-danger" : "")}
    ${renderOpsMetric("Доступ", summary.access_checks?.total || 0, `${accessIssues} проблем`, accessIssues ? "is-danger" : "")}
    ${renderOpsMetric("Качество", qualityCases, `${failedQualityRuns} запусков с ошибкой`, failedQualityRuns ? "is-danger" : "")}
    ${renderOpsMetric("Бэкапы", summary.backups?.total || 0, `${verifiedBackups} проверено`, failedBackups ? "is-danger" : "")}
    ${renderOpsMetric("Аудит", summary.audit?.total || 0, "зафиксированные изменения")}
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
    if (detail) detail.innerHTML = `<div class="empty-state">Задач нет</div>`;
  }
}

function renderOperationsJobs(state) {
  const target = document.querySelector("#operations-jobs");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">Задач нет</div>`;
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
          ${badge(label(job.status), operationsStatusClass(job.status))}
          ${badge(`попытки ${job.attempt_count || 0}/${job.max_attempts || 0}`)}
          ${job.last_error ? badge("ошибка", "is-danger") : ""}
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
        <h2>${escapeHtml(job.job_type || "Задача")}</h2>
        <p class="muted">${escapeHtml(job.id || "")}</p>
      </div>
      <div class="badges">
        ${badge(label(job.status || "unknown"), operationsStatusClass(job.status))}
        ${badge(label(job.priority || "normal"))}
        ${job.locked_by ? badge(`заблокировано ${job.locked_by}`, "is-warn") : ""}
      </div>
    </header>
    <section class="detail-section">
      <h3>Выполнение</h3>
      <div class="detail-meta">
        ${badge(`область ${job.scope_type || "н/д"}`)}
        ${badge(`источник ${job.monitored_source_id || "н/д"}`)}
        ${badge(`сообщение ${job.source_message_id || "н/д"}`)}
        ${badge(`попытки ${job.attempt_count || 0}/${job.max_attempts || 0}`)}
        ${badge(`запуск после ${time(job.run_after_at) || "н/д"}`)}
        ${badge(`повтор ${time(job.next_retry_at) || "нет"}`)}
      </div>
      ${
        job.last_error
          ? `<p class="muted">последняя ошибка: ${escapeHtml(job.last_error)}</p>`
          : ""
      }
    </section>
    ${operationsJsonSection("Payload", job.payload_json)}
    ${operationsJsonSection("Чекпоинт до", job.checkpoint_before_json)}
    ${operationsJsonSection("Чекпоинт после", job.checkpoint_after_json)}
    ${operationsJsonSection("Результат", job.result_summary_json)}
    <section class="detail-section">
      <h3>Запуски</h3>
      <div class="table-list">
        ${runs.map(renderOperationRun).join("") || '<div class="empty-state">Запусков нет</div>'}
      </div>
    </section>
    <section class="detail-section">
      <h3>События</h3>
      <div class="table-list">
        ${events.map(renderOperationEvent).join("") || '<div class="empty-state">Событий нет</div>'}
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

function initArtifacts() {
  const state = { items: [], selectedId: null };
  document.querySelector("#artifacts-refresh")?.addEventListener("click", () =>
    loadArtifacts(state)
  );
  document.querySelector("#artifact-filters")?.addEventListener("change", () =>
    loadArtifacts(state, { resetSelection: true })
  );
  document.querySelector("#artifact-filters")?.addEventListener("input", () =>
    loadArtifacts(state, { resetSelection: true })
  );
  loadArtifacts(state);
}

async function loadArtifacts(state, options = {}) {
  const status = document.querySelector("#artifact-status");
  if (status) status.textContent = "";
  try {
    const params = artifactFilterParams();
    const payload = await api(`/api/artifacts${params ? `?${params}` : ""}`);
    state.items = payload.items || [];
    if (options.resetSelection) state.selectedId = null;
    const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
    state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
    renderArtifactSummary(payload.summary || {});
    populateArtifactFilters(payload);
    renderArtifactList(state);
    if (state.selectedId) {
      await loadArtifactDetail(state.selectedId);
    } else {
      const detail = document.querySelector("#artifact-detail");
      if (detail) detail.innerHTML = `<div class="empty-state">Артефактов нет</div>`;
    }
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function artifactFilterParams() {
  const form = document.querySelector("#artifact-filters");
  if (!form) return "";
  const params = new URLSearchParams({ limit: "1000" });
  const data = new FormData(form);
  for (const [key, value] of data.entries()) {
    if (value) params.set(key, value);
  }
  return params.toString();
}

function populateArtifactFilters(payload) {
  const form = document.querySelector("#artifact-filters");
  if (!form) return;
  fillSelectOptions(form.querySelector('[name="stage"]'), payload.stages || [], "Все этапы");
  fillSelectOptions(form.querySelector('[name="kind"]'), payload.kinds || [], "Все типы");
}

function fillSelectOptions(select, values, emptyLabel) {
  if (!select) return;
  const selected = select.value;
  const options = [`<option value="">${escapeHtml(emptyLabel)}</option>`]
    .concat(
      values.map(
        (value) => `<option value="${escapeHtml(value)}">${escapeHtml(label(value, value))}</option>`
      )
    )
    .join("");
  select.innerHTML = options;
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
}

function renderArtifactSummary(summary) {
  const target = document.querySelector("#artifact-summary");
  if (!target) return;
  target.innerHTML = `<div class="ops-metric-row">
    ${renderOpsMetric("Запуски", summary.run_count || 0, "raw export runs")}
    ${renderOpsMetric("Артефакты", summary.artifact_count || 0, "все найденные пути")}
    ${renderOpsMetric("На диске", summary.existing_count || 0, "файлы и папки")}
    ${renderOpsMetric(
      "Нет файла",
      summary.missing_count || 0,
      "путь есть в metadata",
      summary.missing_count ? "is-danger" : ""
    )}
    ${renderOpsMetric(
      "Размер",
      formatBytes(summary.total_file_size_bytes || 0),
      "без рекурсивного подсчета папок"
    )}
  </div>`;
}

function renderArtifactList(state) {
  const target = document.querySelector("#artifact-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = `<div class="empty-state">Артефактов нет</div>`;
    return;
  }
  target.innerHTML = state.items
    .map((artifact) => {
      const active = artifact.id === state.selectedId ? "is-active" : "";
      const existsClass = artifact.exists ? "" : "is-danger";
      return `<button class="resource-row artifact-row ${active}" type="button" data-id="${artifact.id}">
        <div class="resource-kind">
          <md-icon aria-hidden="true">${artifactIcon(artifact.kind)}</md-icon>
          <span>${escapeHtml(label(artifact.kind, artifact.kind))}</span>
        </div>
        <div class="resource-primary">
          <strong>${escapeHtml(artifact.key)}</strong>
          <p class="muted">${escapeHtml(artifact.path)}</p>
        </div>
        <div>${badge(label(artifact.stage, artifact.stage))}</div>
        <div class="resource-actions">
          ${badge(artifact.exists ? "на диске" : "нет файла", existsClass)}
          ${badge(label(artifact.metadata_json?.source, artifact.metadata_json?.source || "source"))}
          ${badge(formatBytes(artifact.size_bytes || 0))}
        </div>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".artifact-row").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id;
      renderArtifactList(state);
      await loadArtifactDetail(state.selectedId);
    });
  });
}

async function loadArtifactDetail(artifactId) {
  const payload = await api(`/api/artifacts/${encodeURIComponent(artifactId)}`);
  renderArtifactDetail(payload);
}

function renderArtifactDetail(payload) {
  const target = document.querySelector("#artifact-detail");
  if (!target) return;
  const artifact = payload.artifact || {};
  const preview = payload.preview || {};
  target.innerHTML = `<div class="detail-grid">
    <header class="detail-header">
      <div>
        <h2>${escapeHtml(artifact.key || "Артефакт")}</h2>
        <p class="muted">${escapeHtml(artifact.path || "")}</p>
      </div>
      <div class="badges">
        ${badge(label(artifact.kind || "file"))}
        ${badge(label(artifact.stage || "unknown"))}
        ${badge(artifact.exists ? "на диске" : "нет файла", artifact.exists ? "" : "is-danger")}
      </div>
    </header>
    <section class="detail-section">
      <h3>Источник</h3>
      <div class="detail-meta">
        ${badge(`run ${artifact.raw_export_run_id || "н/д"}`)}
        ${badge(artifact.title || artifact.username || artifact.source_ref || "источник")}
        ${badge(`создан ${time(artifact.run_created_at) || "н/д"}`)}
        ${badge(`изменен ${time(artifact.modified_at) || "н/д"}`)}
        ${badge(label(artifact.metadata_json?.source, artifact.metadata_json?.source || "source"))}
        ${badge(formatBytes(artifact.size_bytes || 0))}
      </div>
    </section>
    ${operationsJsonSection("Metadata", artifact.metadata_json || {})}
    ${renderArtifactPreview(preview)}
  </div>`;
}

function renderArtifactPreview(preview) {
  if (!preview.available) {
    return `<section class="detail-section">
      <h3>Содержимое</h3>
      <div class="empty-state">${escapeHtml(preview.reason || "Предпросмотр недоступен")}</div>
    </section>`;
  }
  if (preview.kind === "parquet") {
    return `<section class="detail-section">
      <h3>Parquet</h3>
      <div class="detail-meta">
        ${badge(`${preview.row_count || 0} строк`)}
        ${badge(`${preview.row_group_count || 0} row groups`)}
        ${badge(`${(preview.columns || []).length} колонок`)}
      </div>
      ${renderArtifactSchema(preview.columns || [])}
      ${renderArtifactRows(preview.rows || [], (preview.columns || []).map((column) => column.name))}
      ${preview.truncated ? '<p class="muted">Показаны первые строки файла.</p>' : ""}
    </section>`;
  }
  if (preview.kind === "sqlite") {
    return `<section class="detail-section">
      <h3>SQLite</h3>
      ${renderArtifactSqliteTables(preview.tables || [])}
      ${renderArtifactRows(preview.sample?.rows || [], preview.sample?.columns || [], preview.sample?.table)}
      ${preview.truncated ? '<p class="muted">Показаны первые таблицы базы.</p>' : ""}
    </section>`;
  }
  if (preview.kind === "jsonl" && (preview.records || []).length) {
    return `<section class="detail-section">
      <h3>JSONL</h3>
      <div class="detail-meta">${badge(`${preview.records_previewed || 0} записей в предпросмотре`)}</div>
      ${renderArtifactRows(preview.records || [], Object.keys(preview.records?.[0] || {}), "Первые записи")}
      <pre class="json-block artifact-preview">${escapeHtml(preview.text || "")}</pre>
      ${preview.truncated ? '<p class="muted">Показано начало файла, полный файл больше лимита предпросмотра.</p>' : ""}
    </section>`;
  }
  return `<section class="detail-section">
    <h3>Содержимое</h3>
    <pre class="json-block artifact-preview">${escapeHtml(preview.text || "")}</pre>
    ${preview.truncated ? '<p class="muted">Показано начало файла, полный файл больше лимита предпросмотра.</p>' : ""}
  </section>`;
}

function renderArtifactSchema(columns) {
  if (!columns.length) return `<div class="empty-state">Schema не найдена</div>`;
  return `<div class="artifact-table-wrap">
    <table class="artifact-table">
      <thead><tr><th>Колонка</th><th>Тип</th></tr></thead>
      <tbody>${columns
        .map(
          (column) => `<tr>
            <td>${escapeHtml(column.name)}</td>
            <td>${escapeHtml(column.type)}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table>
  </div>`;
}

function renderArtifactSqliteTables(tables) {
  if (!tables.length) return `<div class="empty-state">Таблицы не найдены</div>`;
  return `<div class="artifact-table-wrap">
    <table class="artifact-table">
      <thead><tr><th>Таблица</th><th>Строк</th></tr></thead>
      <tbody>${tables
        .map(
          (table) => `<tr>
            <td>${escapeHtml(table.name)}</td>
            <td>${escapeHtml(text(table.row_count, "н/д"))}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table>
  </div>`;
}

function renderArtifactRows(rows, columns, title = "Первые строки") {
  if (!rows.length) return `<div class="empty-state">Строки для предпросмотра не найдены</div>`;
  const visibleColumns = columns.filter(Boolean).slice(0, 12);
  const resolvedColumns = visibleColumns.length ? visibleColumns : Object.keys(rows[0] || {}).slice(0, 12);
  return `<div>
    <h4>${escapeHtml(title)}</h4>
    <div class="artifact-table-wrap">
      <table class="artifact-table">
        <thead><tr>${resolvedColumns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
        <tbody>${rows
          .map(
            (row) => `<tr>${resolvedColumns
              .map((column) => `<td>${escapeHtml(formatArtifactCell(row[column]))}</td>`)
              .join("")}</tr>`
          )
          .join("")}</tbody>
      </table>
    </div>
  </div>`;
}

function formatArtifactCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return text(value);
}

function artifactIcon(kind) {
  const icons = {
    directory: "folder",
    json: "description",
    jsonl: "article",
    parquet: "table_chart",
    sqlite: "database",
  };
  return icons[kind] || "storage";
}

function renderOperationRun(run) {
  const duration = run.duration_ms === null || run.duration_ms === undefined ? "выполняется" : `${run.duration_ms}ms`;
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(run.worker_name || "воркер")}</strong>
      <p class="muted">${escapeHtml(time(run.started_at))} / ${escapeHtml(duration)}</p>
    </div>
    <span>${badge(label(run.status), operationsStatusClass(run.status))}</span>
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
    items.map(renderOperationEvent).join("") || '<div class="empty-state">Событий нет</div>';
}

function renderOperationEvent(event) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(event.event_type || "событие")}</strong>
      <p class="muted">${escapeHtml(shortText(event.message || "", 120))}</p>
    </div>
    <span>${badge(label(event.severity || "info"), operationsStatusClass(event.severity))}</span>
  </div>`;
}

function renderOperationsNotifications(items) {
  const target = document.querySelector("#operations-notifications");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationNotification).join("") ||
    '<div class="empty-state">Уведомлений нет</div>';
}

function renderOperationNotification(item) {
  const notificationLabel = [item.notification_type, item.notification_policy].filter(Boolean).join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(notificationLabel || "уведомление")}</strong>
      <p class="muted">${escapeHtml(item.suppressed_reason || item.error || time(item.created_at))}</p>
    </div>
    <span>${badge(label(item.status || "unknown"), operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderOperationsExtractionRuns(items) {
  const target = document.querySelector("#operations-extraction-runs");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationExtractionRun).join("") ||
    '<div class="empty-state">Запусков извлечения нет</div>';
}

function renderOperationExtractionRun(item) {
  const runLabel = [item.run_type, item.model].filter(Boolean).join(" / ");
  const usage = tokenUsageSummary(item.token_usage_json);
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(runLabel || "извлечение")}</strong>
      <p class="muted">${escapeHtml(item.error || usage || time(item.started_at))}</p>
    </div>
    <span>${badge(label(item.status || "unknown"), operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderOperationsAccessChecks(items) {
  const target = document.querySelector("#operations-access-checks");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationAccessCheck).join("") ||
    '<div class="empty-state">Проверок доступа нет</div>';
}

function renderOperationAccessCheck(item) {
  const accessLabel = [item.resolved_title, item.monitored_source_id].filter(Boolean).join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(accessLabel || "доступ к источнику")}</strong>
      <p class="muted">${escapeHtml(item.error || time(item.checked_at))}</p>
    </div>
    <span>${badge(label(item.status || "unknown"), operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderOperationsBackups(items) {
  const target = document.querySelector("#operations-backups");
  if (!target) return;
  target.innerHTML =
    items.map(renderOperationBackup).join("") || '<div class="empty-state">Бэкапов нет</div>';
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
      <strong>${escapeHtml(item.backup_type || "бэкап")}</strong>
      <p class="muted">${escapeHtml(details || item.storage_uri || "")}</p>
    </div>
    <span class="row-actions">
      ${badge(label(item.status || "unknown"), operationsStatusClass(item.status))}
      <button type="button" data-backup-id="${escapeHtml(item.id)}" data-backup-restore-check>Проверить</button>
    </span>
  </div>`;
}

function renderOperationsRestores(items) {
  const target = document.querySelector("#operations-restores");
  if (!target) return;
  target.innerHTML =
    items.map((item) => `<div class="table-row">
      <div>
        <strong>${escapeHtml(item.restore_type || "проверка восстановления")}</strong>
        <p class="muted">${escapeHtml(time(item.finished_at || item.started_at))}</p>
      </div>
      <span>${badge(label(item.validation_status || item.status || "unknown"), operationsStatusClass(item.status))}</span>
    </div>`).join("") || '<div class="empty-state">Проверок восстановления нет</div>';
}

async function createOperationBackup() {
  const button = document.querySelector("#operations-backup-create");
  if (button) button.disabled = true;
  try {
    await api("/api/operations/backups/database", { method: "POST", body: "{}" });
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
    items.map(renderOperationAudit).join("") || '<div class="empty-state">Записей аудита нет</div>';
}

function renderOperationAudit(item) {
  const entity = [item.entity_type, item.entity_id].filter(Boolean).join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.action || "изменение")}</strong>
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
    ${renderOpsMetric("Решения", summary.decisions?.total || 0, "записанные трассы")}
    ${renderOpsMetric("Наборы", summary.datasets?.total || 0, "наборы качества")}
    ${renderOpsMetric("Кейсы", summary.cases?.total || 0, "размеченные примеры")}
    ${renderOpsMetric("Запуски", totalRuns, `${failedRuns} ошибок`, failedRuns ? "is-danger" : "")}
    ${renderOpsMetric("Провалы", failedResults, "нужно разобрать", failedResults ? "is-danger" : "")}
  </div>`;
}

function renderQualityDatasets(items) {
  const target = document.querySelector("#quality-datasets");
  if (!target) return;
  if (!items.length) {
    target.innerHTML = `<div class="empty-state">Наборов нет</div>`;
    return;
  }
  target.innerHTML = items
    .map(
      (item) => `<div class="queue-item">
        <strong>${escapeHtml(item.name || item.dataset_key)}</strong>
        <span class="muted">${escapeHtml(item.dataset_key || item.id)}</span>
        <span class="queue-meta">
          ${badge(label(item.dataset_type || "dataset"))}
          ${badge(label(item.status || "unknown"), operationsStatusClass(item.status))}
        </span>
      </div>`
    )
    .join("");
}

function renderQualityRuns(items) {
  const target = document.querySelector("#quality-runs");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityRun).join("") || '<div class="empty-state">Запусков нет</div>';
}

function renderQualityRun(item) {
  const metrics = item.metrics_json || {};
  const detail = [
    item.model,
    metrics.total !== undefined ? `${metrics.passed || 0}/${metrics.total} прошло` : "",
    time(item.finished_at || item.started_at),
  ]
    .filter(Boolean)
    .join(" / ");
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.run_type || "evaluation")}</strong>
      <p class="muted">${escapeHtml(item.error || detail)}</p>
    </div>
    <span>${badge(label(item.status || "unknown"), operationsStatusClass(item.status))}</span>
  </div>`;
}

function renderQualityFailedResults(items) {
  const target = document.querySelector("#quality-failed-results");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityResult).join("") ||
    '<div class="empty-state">Проваленных кейсов нет</div>';
}

function renderQualityResult(item) {
  const detail = item.details_json?.reason || item.evaluation_case_id || item.id;
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.failure_type || "failed")}</strong>
      <p class="muted">${escapeHtml(shortText(detail || "", 120))}</p>
    </div>
    <span>${badge(label(item.actual_decision || "н/д"), "is-danger")}</span>
  </div>`;
}

function renderQualityDecisions(items) {
  const target = document.querySelector("#quality-decisions");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityDecision).join("") ||
    '<div class="empty-state">Решений нет</div>';
}

function renderQualityDecision(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.decision_type || "decision")}</strong>
      <p class="muted">${escapeHtml(shortText(item.reason || item.entity_id || "", 120))}</p>
    </div>
    <span>${badge(label(item.decision || "н/д"))}</span>
  </div>`;
}

function renderQualityCases(items) {
  const target = document.querySelector("#quality-cases");
  if (!target) return;
  target.innerHTML =
    items.map(renderQualityCase).join("") || '<div class="empty-state">Кейсов нет</div>';
}

function renderQualityCase(item) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(item.expected_decision || "expected")}</strong>
      <p class="muted">${escapeHtml(shortText(item.message_text || item.id, 120))}</p>
    </div>
    <span>${badge(label(item.label_source || "manual"))}</span>
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
  if (total) return `токены ${total}`;
  if (prompt || completion) return `токены ${prompt || 0}/${completion || 0}`;
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
    if (status) status.textContent = `Обновлено ${time(payload.generated_at)}`;
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function renderTodaySummary(payload) {
  const target = document.querySelector("#today-summary");
  if (!target) return;
  const counts = payload.counts || {};
  target.innerHTML = `<div class="ops-metric-row today-metric-row">
    ${renderOpsMetric("Новые лиды", counts.new_leads || 0, `${counts.maybe_leads || 0} возможно`)}
    ${renderOpsMetric("Задачи", counts.due_tasks || 0, `${counts.overdue_tasks || 0} просрочено`, counts.overdue_tasks ? "is-danger" : "")}
    ${renderOpsMetric("Поводы", counts.contact_reasons || 0, "клиенты для контакта")}
    ${renderOpsMetric("Поддержка", counts.support_cases || 0, "открытые кейсы", counts.support_cases ? "is-warn" : "")}
    ${renderOpsMetric("Каталог", counts.catalog_candidates || 0, "факты на проверке")}
    ${renderOpsMetric("Проблемы", counts.operational_issues || 0, "ошибки", counts.operational_issues ? "is-danger" : "")}
  </div>`;
}

function renderTodayLeads(items) {
  const target = document.querySelector("#today-leads");
  if (!target) return;
  target.innerHTML =
    items.map(renderTodayLead).join("") || '<div class="empty-state">Новых лидов нет</div>';
}

function renderTodayLead(item) {
  const confidence = Math.round((item.confidence_max || 0) * 100);
  return `<div class="table-row today-row">
    <div>
      <strong>${escapeHtml(shortText(item.message_text || item.summary || "Лид", 180))}</strong>
      <p class="muted">${escapeHtml(item.primary_sender_name || "неизвестный отправитель")}</p>
      <div class="queue-meta">
        ${badge(label(item.status || "new"), todayStatusClass(item.status))}
        ${badge(`${confidence}%`)}
        ${item.telegram_message_id ? badge(`сообщение ${item.telegram_message_id}`) : ""}
      </div>
    </div>
    <a href="/" aria-label="Открыть входящие лиды">Открыть</a>
  </div>`;
}

function renderTodayTasks(items) {
  const target = document.querySelector("#today-tasks");
  if (!target) return;
  target.innerHTML =
    items.map(renderTodayTask).join("") || '<div class="empty-state">Задач на сейчас нет</div>';
  target.querySelectorAll("[data-today-task-action]").forEach((button) => {
    button.addEventListener("click", () =>
      todayTaskAction(button.dataset.taskId, button.dataset.todayTaskAction)
    );
  });
}

function renderTodayTask(task) {
  return `<div class="table-row today-row">
    <div>
      <strong>${escapeHtml(task.title || "Задача")}</strong>
      <p class="muted">${escapeHtml(task.description || time(task.due_at) || "")}</p>
      <div class="queue-meta">
        ${badge(label(task.status || "open"), todayStatusClass(task.status))}
        ${badge(label(task.priority || "normal"), todayPriorityClass(task.priority))}
        ${task.due_at ? badge(time(task.due_at), todayDueClass(task.due_at)) : ""}
      </div>
    </div>
    <div class="row-actions">
      <button type="button" data-task-id="${escapeHtml(task.id)}" data-today-task-action="complete">Готово</button>
      <button type="button" data-task-id="${escapeHtml(task.id)}" data-today-task-action="snooze">Отложить</button>
    </div>
  </div>`;
}

function renderTodayContactReasons(items) {
  const target = document.querySelector("#today-contact-reasons");
  if (!target) return;
  target.innerHTML =
    items.map(renderTodayContactReason).join("") ||
    '<div class="empty-state">Поводов связаться нет</div>';
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
      <strong>${escapeHtml(item.title || "Повод связаться")}</strong>
      <p class="muted">${escapeHtml(client.display_name || item.reason_text || "")}</p>
      <div class="queue-meta">
        ${badge(label(item.status || "new"), todayStatusClass(item.status))}
        ${badge(label(item.priority || "normal"), todayPriorityClass(item.priority))}
        ${item.due_at ? badge(time(item.due_at), todayDueClass(item.due_at)) : ""}
      </div>
    </div>
    <div class="row-actions">
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="accept">Принять</button>
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="done">Готово</button>
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="snooze">Отложить</button>
      <button type="button" data-reason-id="${escapeHtml(item.id)}" data-today-contact-action="dismiss">Скрыть</button>
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
          <strong>${escapeHtml(item.title || "Кейс поддержки")}</strong>
          <p class="muted">${escapeHtml(client.display_name || item.issue_text || "")}</p>
        </div>
        <span>${badge(label(item.priority || item.status || "open"), todayPriorityClass(item.priority))}</span>
      </div>`;
    }).join("") || '<div class="empty-state">Кейсов поддержки нет</div>';
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
          <strong>${escapeHtml(item.canonical_name || "Кандидат каталога")}</strong>
          <p class="muted">${escapeHtml(subtitle || item.proposed_action || "")}</p>
        </div>
        <span>${badge(label(item.status || "pending"), catalogStatusClass(item.status))}</span>
      </div>`;
    }).join("") || '<div class="empty-state">Кандидатов каталога нет</div>';
}

function renderTodayOperationalIssues(items) {
  const target = document.querySelector("#today-operational-issues");
  if (!target) return;
  target.innerHTML =
    items.map((item) => `<div class="table-row">
      <div>
        <strong>${escapeHtml(item.event_type || "событие")}</strong>
        <p class="muted">${escapeHtml(shortText(item.message || "", 120))}</p>
      </div>
      <span>${badge(label(item.severity || "error"), operationsStatusClass(item.severity))}</span>
    </div>`).join("") || '<div class="empty-state">Операционных проблем нет</div>';
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
    if (status) status.textContent = "Задача создана";
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
let onboardingAiRegistry = null;

async function initAdmin() {
  await Promise.all([loadUsers(), loadUserbots(), loadSettings(), loadAiRegistry()]);
  document.querySelector("#telegram-admin-form")?.addEventListener("submit", addTelegramAdmin);
  document.querySelector("#userbot-form")?.addEventListener("submit", addUserbot);
  document.querySelector("#setting-form")?.addEventListener("submit", saveSetting);
  document.querySelector("#ai-registry-bootstrap")?.addEventListener("click", bootstrapAiRegistry);
  document.querySelector("#ai-registry-refresh")?.addEventListener("click", loadAiRegistry);
  document.querySelector("#ai-route-form")?.addEventListener("submit", saveAiRoute);
}

async function initUsersPage() {
  await loadUsers();
  document.querySelector("#telegram-admin-form")?.addEventListener("submit", addTelegramAdmin);
}

async function initSettingsPage() {
  await loadSettings();
  document.querySelector("#setting-form")?.addEventListener("submit", saveSetting);
}

async function initAiRegistryPage() {
  await loadAiRegistry();
  document.querySelector("#ai-registry-bootstrap")?.addEventListener("click", bootstrapAiRegistry);
  document.querySelector("#ai-registry-refresh")?.addEventListener("click", loadAiRegistry);
  document.querySelector("#ai-profile-form")?.addEventListener("submit", saveAiProfile);
}

async function initTaskExecutors() {
  await loadAiRegistry();
  document.querySelector("#ai-registry-refresh")?.addEventListener("click", loadAiRegistry);
  document.querySelector("#ai-route-form")?.addEventListener("submit", saveAiRoute);
}

async function initTaskTypes() {
  document.querySelector("#task-types-refresh")?.addEventListener("click", loadTaskTypes);
  await loadTaskTypes();
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
          <p class="muted">${escapeHtml(label(user.auth_type))} / ${escapeHtml(label(user.status))}</p>
        </div>
        <span>${escapeHtml(label(user.role))}</span>
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
          <p class="muted">${escapeHtml(account.session_name)} / ${escapeHtml(label(account.status))}</p>
        </div>
        <span>${escapeHtml(account.priority)}</span>
      </div>`
      )
      .join("") || '<div class="empty-state">Юзерботов нет</div>';
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
          <p class="muted">${escapeHtml(setting.group || "Система")} / ${escapeHtml(setting.value_type)}${setting.is_default ? " / значение по умолчанию" : ""}</p>
          <p class="muted">${escapeHtml(setting.description || "")}</p>
          <p class="muted">${escapeHtml(setting.impact || "")}</p>
        </div>
        <div class="row-actions">
          <span>${escapeHtml(JSON.stringify(setting.value))}</span>
          ${setting.is_default ? "" : `<button type="button" data-delete-setting="${escapeHtml(setting.key)}">Удалить</button>`}
        </div>
      </div>`
    )
    .join("");
  target.querySelectorAll("[data-delete-setting]").forEach((button) => {
    button.addEventListener("click", deleteSetting);
  });
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
      reason: "обновление из веб-админки",
    }),
  });
  event.currentTarget.reset();
  await loadSettings();
}

async function deleteSetting(event) {
  const key = event.currentTarget.dataset.deleteSetting;
  await api(`/api/settings/${encodeURIComponent(key)}`, { method: "DELETE" });
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

async function bootstrapAiRegistry() {
  const status = document.querySelector("#ai-registry-status");
  if (status) status.textContent = "Загружаются значения по умолчанию...";
  try {
    adminAiRegistry = await api("/api/admin/ai-registry/bootstrap-defaults", {
      method: "POST",
      body: JSON.stringify({}),
    });
    renderAiRegistry(adminAiRegistry);
    if (status) status.textContent = "Значения по умолчанию загружены";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function renderAiRegistry(registry) {
  renderAiRouteForm(registry);
  renderAiProfileForm(registry);
  renderAiModels(registry.models || []);
  renderAiProfiles(registry.profiles || []);
  renderAiRoutes(registry.routes || []);
}

function renderAiRouteForm(registry) {
  const form = document.querySelector("#ai-route-form");
  if (!form) return;
  const agentSelect = form.querySelector('[name="agent_key"]');
  const profileSelect = form.querySelector('[name="profile_id"]');
  const accountSelect = form.querySelector('[name="account_id"]');
  if (agentSelect) {
    agentSelect.innerHTML = (registry.agents || [])
      .map((agent) => `<option value="${escapeHtml(agent.agent_key)}">${escapeHtml(agent.agent_key)}</option>`)
      .join("");
  }
  if (profileSelect) {
    profileSelect.innerHTML = (registry.profiles || [])
      .map(
        (profile) =>
          `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.model)} / ${escapeHtml(
            profile.display_name
          )}</option>`
      )
      .join("");
  }
  if (profileSelect && accountSelect) {
    populateAiRouteAccountSelect(registry);
    profileSelect.onchange = () => populateAiRouteAccountSelect(registry);
  }
}

function populateAiRouteAccountSelect(registry) {
  const form = document.querySelector("#ai-route-form");
  const profileSelect = form?.querySelector('[name="profile_id"]');
  const accountSelect = form?.querySelector('[name="account_id"]');
  if (!profileSelect || !accountSelect) return;
  const profile = (registry.profiles || []).find((item) => item.id === profileSelect.value);
  const accounts = (registry.accounts || []).filter(
    (account) => account.enabled !== false && (!profile || account.ai_provider_id === profile.ai_provider_id)
  );
  if (!accounts.length) {
    accountSelect.innerHTML = '<option value="">Нет активных аккаунтов провайдера</option>';
    return;
  }
  const current = accountSelect.value;
  accountSelect.innerHTML = accounts
    .map(
      (account) =>
        `<option value="${escapeHtml(account.id)}">${escapeHtml(
          account.display_name || account.base_url || account.id
        )}</option>`
    )
    .join("");
  accountSelect.value = accounts.some((account) => account.id === current) ? current : accounts[0].id;
}

function renderAiProfileForm(registry) {
  const form = document.querySelector("#ai-profile-form");
  if (!form) return;
  const modelSelect = form.querySelector('[name="model_id"]');
  if (!modelSelect) return;
  modelSelect.innerHTML = (registry.models || [])
    .map(
      (model) =>
        `<option value="${escapeHtml(model.id)}">${escapeHtml(model.provider_model_name)} / ${escapeHtml(
          label(model.model_type)
        )}</option>`
    )
    .join("");
}

function renderAiModels(models) {
  const target = document.querySelector("#ai-models");
  if (!target) return;
  target.innerHTML =
    models
      .map((model) => {
        const limit = model.limit || {};
        return `<form class="table-row ai-limit-form" data-limit-id="${escapeHtml(limit.id || "")}" data-model-id="${escapeHtml(model.id)}">
          <div>
            <input name="display_name" value="${escapeHtml(model.display_name || model.provider_model_name)}" aria-label="Название модели">
            <p class="muted">${escapeHtml(model.provider_model_name)} / ${escapeHtml(label(model.model_type))} / ${escapeHtml(label(model.status))}</p>
          </div>
          <div class="row-actions">
            <input class="compact-input" name="context_window_tokens" type="number" min="1" step="1"
              value="${escapeHtml(model.context_window_tokens || "")}" placeholder="context" aria-label="Контекстное окно">
            <input class="compact-input" name="model_max_output_tokens" type="number" min="1" step="1"
              value="${escapeHtml(model.max_output_tokens || "")}" placeholder="output" aria-label="Max output модели">
            <input class="compact-input" name="raw_limit" type="number" min="1" step="1"
              value="${escapeHtml(limit.raw_limit || 1)}" aria-label="Сырой лимит параллельности">
            <input class="compact-input" name="utilization_ratio" type="number" min="0.1" max="1"
              step="0.05" value="${escapeHtml(limit.utilization_ratio || 0.8)}"
              aria-label="Коэффициент использования">
            <span class="badge">эфф. ${escapeHtml(limit.effective_limit || 1)}</span>
            <button type="submit">Сохранить</button>
          </div>
        </form>`;
      })
      .join("") || '<div class="empty-state">Моделей нет</div>';
  target.querySelectorAll(".ai-limit-form").forEach((form) => {
    form.addEventListener("submit", saveAiLimit);
  });
}

function renderAiProfiles(profiles) {
  const target = document.querySelector("#ai-model-profiles");
  if (!target) return;
  target.innerHTML =
    profiles
      .map(
        (profile) => `<form class="table-row ai-profile-row" data-profile-id="${escapeHtml(profile.id)}">
          <div>
            <strong>${escapeHtml(profile.display_name)}</strong>
            <p class="muted">${escapeHtml(profile.model)} / ${escapeHtml(profile.profile_key)} / ${escapeHtml(label(profile.status))}</p>
          </div>
          <div class="row-actions">
            <input class="compact-input" name="max_input_tokens" type="number" min="1" step="1"
              value="${escapeHtml(profile.max_input_tokens || "")}" placeholder="input" aria-label="Max input">
            <input class="compact-input" name="max_output_tokens" type="number" min="1" step="1"
              value="${escapeHtml(profile.max_output_tokens || "")}" placeholder="output" aria-label="Max output">
            <input class="compact-input" name="temperature" type="number" min="0" max="2" step="0.1"
              value="${escapeHtml(profile.temperature ?? "")}" placeholder="temp" aria-label="Temperature">
            <select name="thinking_mode" aria-label="Thinking mode">
              <option value="off" ${profile.thinking_mode === "off" ? "selected" : ""}>off</option>
              <option value="on" ${profile.thinking_mode === "on" ? "selected" : ""}>on</option>
            </select>
            <label class="checkbox-line">
              <input name="structured_output_required" type="checkbox" ${profile.structured_output_required ? "checked" : ""}>
              JSON
            </label>
            <button type="submit">Сохранить</button>
          </div>
        </form>`
      )
      .join("") || '<div class="empty-state">Профилей моделей нет</div>';
  target.querySelectorAll(".ai-profile-row").forEach((form) => {
    form.addEventListener("submit", updateAiProfile);
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
          <strong>${escapeHtml(route.agent_key)} / ${escapeHtml(label(route.route_role))}</strong>
          <p class="muted">${escapeHtml(route.provider_account || "аккаунт")} / ${escapeHtml(route.model)} / ${escapeHtml(route.model_profile || "профиль")} / приоритет ${escapeHtml(route.priority)}</p>
        </div>
        <div class="row-actions">
          ${badge(route.enabled ? "включен" : "отключен", route.enabled ? "" : "is-warn")}
          <button type="button" data-route-id="${escapeHtml(route.id)}" data-enabled="${
            route.enabled ? "false" : "true"
          }">${route.enabled ? "Отключить" : "Включить"}</button>
        </div>
      </div>`
      )
      .join("") || '<div class="empty-state">Исполнителей задач нет</div>';
  target.querySelectorAll("[data-route-id]").forEach((button) => {
    button.addEventListener("click", toggleAiRoute);
  });
}

async function saveAiLimit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#ai-registry-status");
  const limitId = form.dataset.limitId;
  const modelId = form.dataset.modelId;
  if (!limitId || !modelId) return;
  const data = new FormData(form);
  try {
    await api(`/api/admin/ai-models/${encodeURIComponent(modelId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        display_name: data.get("display_name"),
        context_window_tokens: data.get("context_window_tokens")
          ? Number.parseInt(data.get("context_window_tokens"), 10)
          : null,
        max_output_tokens: data.get("model_max_output_tokens")
          ? Number.parseInt(data.get("model_max_output_tokens"), 10)
          : null,
        status: "active",
      }),
    });
    await api(`/api/admin/ai-model-limits/${encodeURIComponent(limitId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        raw_limit: Number.parseInt(data.get("raw_limit"), 10),
        utilization_ratio: Number.parseFloat(data.get("utilization_ratio")),
      }),
    });
    if (status) status.textContent = "Модель и лимит сохранены";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function saveAiProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#ai-registry-status");
  const data = new FormData(form);
  const modelId = data.get("model_id");
  try {
    await api(`/api/admin/ai-models/${encodeURIComponent(modelId)}/profiles`, {
      method: "POST",
      body: JSON.stringify(aiProfilePayload(data, true)),
    });
    form.reset();
    if (status) status.textContent = "Профиль модели сохранен";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function updateAiProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#ai-registry-status");
  const data = new FormData(form);
  try {
    await api(`/api/admin/ai-model-profiles/${encodeURIComponent(form.dataset.profileId)}`, {
      method: "PATCH",
      body: JSON.stringify(aiProfilePayload(data, false)),
    });
    if (status) status.textContent = "Профиль модели обновлен";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function aiProfilePayload(data, includeIdentity) {
  const payload = {
    max_input_tokens: data.get("max_input_tokens") ? Number.parseInt(data.get("max_input_tokens"), 10) : null,
    max_output_tokens: data.get("max_output_tokens") ? Number.parseInt(data.get("max_output_tokens"), 10) : null,
    temperature: data.get("temperature") ? Number.parseFloat(data.get("temperature")) : null,
    thinking_mode: data.get("thinking_mode") || "off",
    structured_output_required: data.get("structured_output_required") === "on",
    status: "active",
  };
  if (includeIdentity) {
    payload.profile_key = data.get("profile_key");
    payload.display_name = data.get("display_name");
  }
  return payload;
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
        profile_id: data.get("profile_id"),
        account_id: data.get("account_id"),
        route_role: data.get("route_role"),
        priority: Number.parseInt(data.get("priority"), 10),
        enabled: data.get("enabled") === "on",
      }),
    });
    if (status) status.textContent = "Исполнитель задачи сохранен";
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
    if (status) status.textContent = "Маршрут обновлен";
    await loadAiRegistry();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadTaskTypes() {
  const target = document.querySelector("#task-type-list");
  if (!target) return;
  try {
    const payload = await api("/api/admin/task-types");
    target.innerHTML =
      (payload.items || [])
        .map(
          (task) => `<div class="table-row">
          <div>
            <strong>${escapeHtml(task.task_type)}</strong>
            <p class="muted">${escapeHtml(task.display_name)} / ${escapeHtml(task.workload_class)} / ${escapeHtml(task.status)}</p>
            <p class="muted">${escapeHtml(task.parallelism_rule)}</p>
            <p class="muted">${escapeHtml((task.required_capabilities || []).join(", "))}</p>
          </div>
          <span>${escapeHtml((task.config_keys || []).join(", ") || "без настроек")}</span>
        </div>`
        )
        .join("") || '<div class="empty-state">Типов задач нет</div>';
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function initOnboarding() {
  document.querySelector("#onboarding-refresh")?.addEventListener("click", loadOnboardingStatus);
  document.querySelector("#onboarding-add-resource")?.addEventListener("click", openOnboardingResourceDialog);
  document
    .querySelector("#onboarding-resource-dialog-close")
    ?.addEventListener("click", closeOnboardingResourceDialog);
  document
    .querySelector("#onboarding-resource-type")
    ?.addEventListener("change", updateOnboardingResourceForm);
  document.querySelector("#onboarding-bot-form")?.addEventListener("submit", saveOnboardingBot);
  document
    .querySelector("#onboarding-group-bot-select")
    ?.addEventListener("change", () => {
      updateOnboardingGroupDiscoverEnabled();
      loadOnboardingGroups();
    });
  document
    .querySelector("#onboarding-group-discover")
    ?.addEventListener("click", discoverOnboardingGroups);
  document
    .querySelector("#onboarding-llm-form")
    ?.addEventListener("submit", saveOnboardingLlmProvider);
  document
    .querySelector("#onboarding-interactive-start-form")
    ?.addEventListener("submit", startInteractiveUserbotLogin);
  document
    .querySelector("#onboarding-interactive-complete-form")
    ?.addEventListener("submit", completeInteractiveUserbotLogin);
  loadOnboardingStatus();
  loadOnboardingResources();
  loadOnboardingBots();
  updateOnboardingResourceForm();
}

function initResources() {
  initOnboarding();
}

function openOnboardingResourceDialog(event) {
  const dialog = document.querySelector("#onboarding-resource-dialog");
  if (!dialog) return;
  const resourceType = event?.currentTarget?.dataset?.resourceType;
  const select = document.querySelector("#onboarding-resource-type");
  if (resourceType && select) select.value = resourceType;
  updateOnboardingResourceForm();
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function closeOnboardingResourceDialog() {
  const dialog = document.querySelector("#onboarding-resource-dialog");
  if (!dialog) return;
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }
}

function updateOnboardingResourceForm() {
  const selectedType = document.querySelector("#onboarding-resource-type")?.value || "telegram_bot";
  document.querySelectorAll("[data-resource-form]").forEach((section) => {
    section.classList.toggle("is-hidden", section.dataset.resourceForm !== selectedType);
  });
  if (selectedType === "telegram_notification_group") {
    loadOnboardingBots();
  }
}

async function loadOnboardingResources() {
  const target = document.querySelector("#onboarding-resource-list");
  if (!target) return;
  try {
    const payload = await api("/api/onboarding/resources");
    renderOnboardingResources(payload.items || []);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderOnboardingResources(resources) {
  const target = document.querySelector("#onboarding-resource-list");
  if (!target) return;
  if (!resources.length) {
    target.innerHTML = '<div class="empty-state">Ресурсы еще не добавлены</div>';
    return;
  }
  target.innerHTML = resources
    .map((resource) => {
      const icon = onboardingResourceIcon(resource.resource_type);
      const statusClass = resource.status === "active" ? "" : "is-warn";
      return `<div class="resource-row">
        <div class="resource-kind">
          <md-icon aria-hidden="true">${icon}</md-icon>
          <span>${escapeHtml(resource.type_label || resource.resource_type)}</span>
        </div>
        <div class="resource-primary">
          <strong>${escapeHtml(resource.display_name || resource.id)}</strong>
          <p class="muted">${escapeHtml(resource.detail || "")}</p>
        </div>
        <div>${badge(label(resource.status, resource.status), statusClass)}</div>
        <div class="resource-actions">
          <md-outlined-button type="button" data-edit-resource-type="${escapeHtml(resource.resource_type)}">
            Редактировать
          </md-outlined-button>
          <md-outlined-button type="button"
            data-delete-resource="${escapeHtml(resource.id)}"
            data-resource-type="${escapeHtml(resource.resource_type)}">
            Удалить
          </md-outlined-button>
        </div>
      </div>`;
    })
    .join("");
  target.querySelectorAll("[data-edit-resource-type]").forEach((button) => {
    button.addEventListener("click", openOnboardingResourceDialog);
  });
  target.querySelectorAll("[data-delete-resource]").forEach((button) => {
    button.addEventListener("click", deleteOnboardingResource);
  });
}

function onboardingResourceIcon(resourceType) {
  const icons = {
    telegram_bot: "smart_toy",
    telegram_notification_group: "forum",
    telegram_userbot: "person",
    ai_provider_account: "model_training",
  };
  return icons[resourceType] || "settings";
}

async function deleteOnboardingResource(event) {
  const button = event.currentTarget;
  const status = document.querySelector("#onboarding-resource-status");
  const resourceType = button.dataset.resourceType;
  const resourceId = button.dataset.deleteResource;
  const paths = {
    telegram_bot: `/api/onboarding/bots/${encodeURIComponent(resourceId)}`,
    telegram_notification_group: `/api/onboarding/notification-groups/${encodeURIComponent(resourceId)}`,
    ai_provider_account: `/api/onboarding/llm-providers/${encodeURIComponent(resourceId)}`,
    telegram_userbot: `/api/onboarding/userbots/${encodeURIComponent(resourceId)}`,
  };
  const path = paths[resourceType];
  if (!path) return;
  try {
    await api(path, { method: "DELETE" });
    if (status) status.textContent = "Ресурс удален";
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function refreshOnboardingResourceState() {
  await Promise.all([loadOnboardingResources(), loadOnboardingStatus(), loadOnboardingBots()]);
}

function setOnboardingGroupDiscoverEnabled(enabled) {
  updateOnboardingGroupDiscoverEnabled(enabled);
}

function updateOnboardingGroupDiscoverEnabled(forceEnabled = null) {
  const button = document.querySelector("#onboarding-group-discover");
  const hint = document.querySelector("#onboarding-group-hint");
  const selectedBotId = document.querySelector("#onboarding-group-bot-select")?.value || "";
  const enabled = forceEnabled === null ? Boolean(selectedBotId) : Boolean(forceEnabled && selectedBotId);
  if (button) button.disabled = !enabled;
  if (hint) {
    hint.textContent = enabled
      ? "Бот выбран. Можно найти все группы, куда он добавлен."
      : "Сначала сохраните бота и выберите его здесь.";
  }
}

async function loadOnboardingStatus() {
  const target = document.querySelector("#onboarding-status");
  const progress = document.querySelector("#onboarding-progress");
  if (!target) return;
  try {
    const payload = await api("/api/onboarding/status");
    const steps = Object.entries(payload.steps || {});
    const doneCount = steps.filter(([, step]) => step.done).length;
    if (progress) progress.value = steps.length ? doneCount / steps.length : 0;
    setOnboardingGroupDiscoverEnabled(Boolean(payload.steps?.bot_token?.done));
    target.innerHTML = steps
      .map(([key, step]) => {
        const icon = step.done ? "check_circle" : "radio_button_unchecked";
        const state = step.done ? "is-done" : "";
        return `<md-list-item class="onboarding-step ${state}" data-step="${escapeHtml(key)}">
          <md-icon slot="start" aria-hidden="true">${icon}</md-icon>
          <span>${escapeHtml(step.label || key)}</span>
        </md-list-item>`;
      })
      .join("");
  } catch (error) {
    setOnboardingGroupDiscoverEnabled(false);
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

async function saveOnboardingBot(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#onboarding-bot-status");
  try {
    const payload = await api("/api/onboarding/bot-token", {
      method: "POST",
      body: JSON.stringify({
        token: formValue(form, "token"),
        display_name: formValue(form, "display_name") || "Telegram bot",
      }),
    });
    if (status) status.textContent = `Бот @${payload.bot?.telegram_username || "telegram"} сохранен`;
    form.reset();
    closeOnboardingResourceDialog();
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadOnboardingBots() {
  const target = document.querySelector("#onboarding-bot-list");
  try {
    const payload = await api("/api/onboarding/bots");
    const bots = payload.items || [];
    renderOnboardingBots(bots);
    populateOnboardingGroupBotSelect(bots);
    updateOnboardingGroupDiscoverEnabled();
  } catch (error) {
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderOnboardingBots(bots) {
  const target = document.querySelector("#onboarding-bot-list");
  if (!target) return;
  if (!bots.length) {
    target.innerHTML = '<div class="empty-state">Сохраненных ботов пока нет</div>';
    return;
  }
  target.innerHTML = bots
    .map(
      (bot) => `<div class="onboarding-mini-row">
        <div>
          <strong>${escapeHtml(bot.display_name || bot.telegram_username || "Telegram bot")}</strong>
          <p class="muted">${escapeHtml(bot.telegram_username ? `@${bot.telegram_username}` : "username не получен")}</p>
        </div>
        <md-outlined-button type="button" data-delete-bot="${escapeHtml(bot.id)}">Удалить</md-outlined-button>
      </div>`
    )
    .join("");
  target.querySelectorAll("[data-delete-bot]").forEach((button) => {
    button.addEventListener("click", deleteOnboardingBot);
  });
}

function populateOnboardingGroupBotSelect(bots) {
  const select = document.querySelector("#onboarding-group-bot-select");
  if (!select) return;
  const current = select.value;
  if (!bots.length) {
    select.innerHTML = '<option value="">Сначала сохраните бота</option>';
    return;
  }
  select.innerHTML = bots
    .map(
      (bot) =>
        `<option value="${escapeHtml(bot.id)}">${escapeHtml(bot.display_name || bot.telegram_username || "Telegram bot")}</option>`
    )
    .join("");
  select.value = bots.some((bot) => bot.id === current) ? current : bots[0].id;
}

async function deleteOnboardingBot(event) {
  const status = document.querySelector("#onboarding-bot-status");
  try {
    await api(`/api/onboarding/bots/${encodeURIComponent(event.currentTarget.dataset.deleteBot)}`, {
      method: "DELETE",
    });
    if (status) status.textContent = "Бот удален";
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function discoverOnboardingGroups() {
  const button = document.querySelector("#onboarding-group-discover");
  const target = document.querySelector("#onboarding-group-candidates");
  const status = document.querySelector("#onboarding-group-status");
  const botId = document.querySelector("#onboarding-group-bot-select")?.value || "";
  if (status) status.textContent = "";
  if (button?.disabled) {
    if (status) status.textContent = "Сначала выберите бота.";
    return;
  }
  try {
    const payload = await api(`/api/onboarding/notification-groups/discover?bot_id=${encodeURIComponent(botId)}`);
    const candidates = payload.candidates || [];
    if (!candidates.length) {
      target.innerHTML = '<div class="empty-state">Группы не найдены</div>';
      return;
    }
    target.innerHTML = candidates
      .map(
        (candidate) => `<div class="table-row onboarding-group-row">
          <div>
            <strong>${escapeHtml(candidate.title)}</strong>
            <p class="muted">${escapeHtml(candidate.chat_type)} ${escapeHtml(candidate.chat_id)}</p>
          </div>
          <md-filled-button type="button"
            data-chat-id="${escapeHtml(candidate.chat_id)}"
            data-title="${escapeHtml(candidate.title)}"
            data-chat-type="${escapeHtml(candidate.chat_type)}"
            data-thread-id="${escapeHtml(candidate.message_thread_id ?? "")}">
            Выбрать
          </md-filled-button>
        </div>`
      )
      .join("");
    target.querySelectorAll("[data-chat-id]").forEach((button) => {
      button.addEventListener("click", saveOnboardingGroup);
    });
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function saveOnboardingGroup(event) {
  const button = event.currentTarget;
  const status = document.querySelector("#onboarding-group-status");
  const threadId = button.dataset.threadId;
  const botId = document.querySelector("#onboarding-group-bot-select")?.value || "";
  try {
    await api("/api/onboarding/notification-group", {
      method: "POST",
      body: JSON.stringify({
        bot_id: botId,
        chat_id: button.dataset.chatId,
        title: button.dataset.title,
        chat_type: button.dataset.chatType || null,
        message_thread_id: threadId ? Number.parseInt(threadId, 10) : null,
        send_test: true,
      }),
    });
    if (status) status.textContent = "Группа уведомлений сохранена, тестовое сообщение отправлено";
    closeOnboardingResourceDialog();
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadOnboardingGroups() {
  const target = document.querySelector("#onboarding-group-list");
  try {
    const payload = await api("/api/onboarding/notification-groups");
    renderOnboardingGroups(payload.items || []);
  } catch (error) {
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderOnboardingGroups(groups) {
  const target = document.querySelector("#onboarding-group-list");
  if (!target) return;
  if (!groups.length) {
    target.innerHTML = '<div class="empty-state">Сохраненных групп уведомлений пока нет</div>';
    return;
  }
  target.innerHTML = groups
    .map(
      (group) => `<div class="onboarding-mini-row">
        <div>
          <strong>${escapeHtml(group.title || group.chat_id)}</strong>
          <p class="muted">${escapeHtml(group.bot_name || "бот")} / ${escapeHtml(group.chat_id)}${group.message_thread_id ? ` / topic ${escapeHtml(group.message_thread_id)}` : ""}</p>
        </div>
        <md-outlined-button type="button" data-delete-group="${escapeHtml(group.id)}">Удалить</md-outlined-button>
      </div>`
    )
    .join("");
  target.querySelectorAll("[data-delete-group]").forEach((button) => {
    button.addEventListener("click", deleteOnboardingGroup);
  });
}

async function deleteOnboardingGroup(event) {
  const status = document.querySelector("#onboarding-group-status");
  try {
    await api(`/api/onboarding/notification-groups/${encodeURIComponent(event.currentTarget.dataset.deleteGroup)}`, {
      method: "DELETE",
    });
    if (status) status.textContent = "Группа уведомлений удалена";
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function saveOnboardingLlmProvider(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#onboarding-llm-status");
  try {
    if (status) status.textContent = "Сохраняю ключ и загружаю модели...";
    onboardingAiRegistry = await api("/api/onboarding/llm-provider", {
      method: "POST",
      body: JSON.stringify({
        base_url: formValue(form, "base_url"),
        api_key: formValue(form, "api_key"),
        display_name: formValue(form, "display_name") || "Z.AI",
      }),
    });
    const modelCount = (onboardingAiRegistry.models || []).length;
    if (status) status.textContent = `LLM-провайдер сохранен. Моделей в метакаталоге: ${modelCount}`;
    const apiKeyField = form.querySelector('[name="api_key"]');
    if (apiKeyField && "value" in apiKeyField) apiKeyField.value = "";
    closeOnboardingResourceDialog();
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadOnboardingLlmRegistry() {
  try {
    onboardingAiRegistry = await api("/api/admin/ai-registry");
    renderOnboardingLlmProviders(onboardingAiRegistry.accounts || [], onboardingAiRegistry.routes || []);
  } catch {
    renderOnboardingLlmProviders([], []);
  }
}

function renderOnboardingLlmProviders(accounts, routes) {
  const target = document.querySelector("#onboarding-llm-provider-list");
  if (!target) return;
  const activeAccounts = (accounts || []).filter((account) => account.enabled !== false);
  if (!activeAccounts.length) {
    target.innerHTML = '<div class="empty-state">Сохраненных LLM-провайдеров пока нет</div>';
    return;
  }
  const routeLines = readableAiRoutes(routes || []);
  target.innerHTML = activeAccounts
    .map(
      (account) => `<div class="onboarding-mini-row">
        <div>
          <strong>${escapeHtml(account.display_name || account.provider_account || "LLM provider")}</strong>
          <p class="muted">${escapeHtml(account.base_url || "")}</p>
          ${routeLines.map((line) => `<p class="muted">${escapeHtml(line)}</p>`).join("") || '<p class="muted">routes не выбраны</p>'}
        </div>
        <md-outlined-button type="button" data-delete-llm="${escapeHtml(account.id)}">Удалить</md-outlined-button>
      </div>`
    )
    .join("");
  target.querySelectorAll("[data-delete-llm]").forEach((button) => {
    button.addEventListener("click", deleteOnboardingLlmProvider);
  });
}

function readableAiRoutes(routes) {
  const labels = {
    "catalog_extractor.primary": "Основной анализ каталога",
    "catalog_extractor.fallback": "Резервный анализ каталога",
    "lead_detector.shadow": "Проверка лидов в фоне",
    "ocr_extractor.primary": "OCR документов",
  };
  return routes
    .filter((route) => route.enabled !== false)
    .map((route) => {
      const routeKey = `${route.agent_key}.${route.route_role}`;
      const label = labels[routeKey] || routeKey;
      return `${label}: ${routeKey} = ${route.model || "модель не выбрана"}`;
    });
}

async function deleteOnboardingLlmProvider(event) {
  const status = document.querySelector("#onboarding-llm-status");
  try {
    await api(`/api/onboarding/llm-providers/${encodeURIComponent(event.currentTarget.dataset.deleteLlm)}`, {
      method: "DELETE",
    });
    if (status) status.textContent = "LLM-провайдер отключен";
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadOnboardingUserbots() {
  const target = document.querySelector("#onboarding-userbot-list");
  if (!target) return;
  try {
    const payload = await api("/api/onboarding/userbots");
    renderOnboardingUserbots(payload.items || [], payload.credentials || {});
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderOnboardingUserbots(userbots, credentials) {
  const target = document.querySelector("#onboarding-userbot-list");
  if (!target) return;
  if (!userbots.length) {
    const credentialText = credentials.telegram_api_id
      ? `Telegram API ID ${credentials.telegram_api_id} сохранен, API hash ${credentials.api_hash_configured ? "сохранен в секретах" : "не сохранен"}.`
      : "Сохраненных юзерботов пока нет.";
    target.innerHTML = `<div class="empty-state">${escapeHtml(credentialText)}</div>`;
    return;
  }
  target.innerHTML = userbots
    .map(
      (userbot) => `<div class="onboarding-mini-row">
        <div>
          <strong>${escapeHtml(userbot.display_name || userbot.session_name || "Юзербот")}</strong>
          <p class="muted">${escapeHtml(userbot.telegram_username ? `@${userbot.telegram_username}` : userbot.session_name || "")}</p>
          <p class="muted">Telegram API ID ${escapeHtml(credentials.telegram_api_id || "не указан")}; API hash ${credentials.api_hash_configured ? "сохранен в секретах" : "не сохранен"}</p>
        </div>
        <md-outlined-button type="button" data-delete-userbot="${escapeHtml(userbot.id)}">Удалить</md-outlined-button>
      </div>`
    )
    .join("");
  target.querySelectorAll("[data-delete-userbot]").forEach((button) => {
    button.addEventListener("click", deleteOnboardingUserbot);
  });
}

async function deleteOnboardingUserbot(event) {
  const status = document.querySelector("#onboarding-interactive-status");
  try {
    await api(`/api/onboarding/userbots/${encodeURIComponent(event.currentTarget.dataset.deleteUserbot)}`, {
      method: "DELETE",
    });
    if (status) status.textContent = "Юзербот удален";
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function startInteractiveUserbotLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#onboarding-interactive-status");
  const completeForm = document.querySelector("#onboarding-interactive-complete-form");
  try {
    const payload = await api("/api/onboarding/userbots/interactive/start", {
      method: "POST",
      body: JSON.stringify({
        display_name: formValue(form, "display_name"),
        session_name: formValue(form, "session_name"),
        phone: formValue(form, "phone"),
        api_id: Number.parseInt(formValue(form, "api_id"), 10),
        api_hash: formValue(form, "api_hash"),
        make_default: formChecked(form, "make_default"),
      }),
    });
    completeForm?.classList.remove("is-hidden");
    completeForm.querySelector('[name="login_id"]').value = payload.login_id;
    completeForm.querySelector('[name="code"]')?.focus();
    if (status) status.textContent = "Код отправлен в Telegram";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function completeInteractiveUserbotLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#onboarding-interactive-status");
  try {
    await api("/api/onboarding/userbots/interactive/complete", {
      method: "POST",
      body: JSON.stringify({
        login_id: formValue(form, "login_id"),
        code: formValue(form, "code"),
        password: formValue(form, "password") || null,
      }),
    });
    if (status) status.textContent = "Интерактивный вход завершен";
    form.reset();
    form.classList.add("is-hidden");
    closeOnboardingResourceDialog();
    await refreshOnboardingResourceState();
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
