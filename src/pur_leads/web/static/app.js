const page = document.body.dataset.page;

const api = async (path, options = {}) => {
  const headers =
    options.body instanceof FormData
      ? { ...(options.headers || {}) }
      : { "content-type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, {
    credentials: "same-origin",
    headers,
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

const uploadFormData = (path, formData, { onProgress, onProcessing } = {}) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(event.loaded / event.total);
      }
    };
    xhr.upload.onload = () => {
      onProgress?.(1);
      onProcessing?.();
    };
    xhr.onerror = () => reject(new Error("Ошибка сети при загрузке файла"));
    xhr.onload = () => {
      const payload = parseJsonResponse(xhr.responseText);
      if (xhr.status === 401 || xhr.status === 403) {
        window.location.assign("/login");
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(payload.detail || `Ошибка запроса: ${xhr.status}`));
        return;
      }
      resolve(payload);
    };
    xhr.send(formData);
  });

const parseJsonResponse = (value) => {
  try {
    return value ? JSON.parse(value) : {};
  } catch {
    return {};
  }
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
  interest_context_seed: "ядро интересов",
  item: "сущность",
  keep: "оставить",
  lead: "лид",
  lead_phrase: "признак запроса",
  lead_monitoring: "поиск лидов",
  leads: "лиды",
  lead_signal: "сигнал интереса",
  language_model: "языковая модель",
  low: "низкий",
  manual: "вручную",
  manual_test: "ручной тест",
  maybe: "возможно",
  merge: "объединить",
  muted: "скрыто",
  negative_phrase: "исключающий признак",
  new: "новый",
  needs_review: "на проверке",
  none: "нет",
  normal: "обычный",
  not_lead: "не лид",
  not_checked: "AI не проверял",
  open: "открыто",
  offer: "условие",
  other: "другое",
  paused: "пауза",
  pending: "ожидает",
  pending_review: "ожидает ревью",
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
  reject: "отклонить",
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
  term: "термин",
  theme: "тема",
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
  canonical: "название ядра",
  phrase: "фраза",
  synonym: "синоним",
  token_overlap: "пересечение токенов",
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
  bindHelpNav();
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
  if (page === "interest-contexts") initInterestContexts();
  if (page === "interest-context-draft") initInterestContextDraftScreen();
  if (page === "users") initUsersPage();
  if (page === "settings") initSettingsPage();
  if (page === "ai-registry") initAiRegistryPage();
  if (page === "task-executors") initTaskExecutors();
  if (page === "task-types") initTaskTypes();
});

function bindHelpNav() {
  document.querySelectorAll(".topbar nav").forEach((nav) => {
    if (nav.querySelector('a[href="/help"]')) return;
    const link = document.createElement("a");
    link.href = "/help";
    link.textContent = "Помощь";
    const logout = nav.querySelector("#logout-button");
    if (logout) {
      nav.insertBefore(link, logout);
    } else {
      nav.appendChild(link);
    }
  });
}

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
  document
    .querySelector("#onboarding-telegram-archive-form")
    ?.addEventListener("submit", uploadTelegramArchiveResource);
  loadOnboardingStatus();
  loadOnboardingResources();
  loadOnboardingBots();
  updateOnboardingResourceForm();
}

function initResources() {
  initOnboarding();
}

function initInterestContexts() {
  const stepRoot = document.querySelector("[data-interest-step]");
  const state = {
    items: [],
    selectedId: new URLSearchParams(window.location.search).get("context_id"),
    detail: null,
    step: stepRoot?.dataset.interestStep || "context",
    preparePollTimer: null,
    draftPollTimer: null,
    enhancePollTimer: null,
    briefPollTimer: null,
    draftItemsLimit: 10,
    draftItemsOffset: 0,
    reviewItemsLimit: 10,
    reviewItemsOffset: 0,
    coreItemsLimit: 10,
    coreItemsOffset: 0,
    analysisRunsLimit: 10,
    analysisRunsOffset: 0,
    analysisMatchesLimit: 10,
    analysisMatchesOffset: 0,
    selectedAnalysisRunId: null,
    intentRunsLimit: 10,
    intentRunsOffset: 0,
    intentMatchesLimit: 10,
    intentMatchesOffset: 0,
    selectedIntentRunId: null,
    intentExclusionsLimit: 10,
    intentExclusionsOffset: 0,
    prepTextsLimit: 10,
    prepTextsOffset: 0,
    prepFeaturesLimit: 10,
    prepFeaturesOffset: 0,
    prepEntitiesLimit: 10,
    prepEntitiesOffset: 0,
    prepNgramsLimit: 10,
    prepNgramsOffset: 0,
    prepNgramsKind: "lemmas",
    selectedPrepRawRunId: new URLSearchParams(window.location.search).get("raw_export_run_id"),
  };
  document
    .querySelector("#interest-context-refresh")
    ?.addEventListener("click", () => loadInterestContexts(state));
  document
    .querySelector("#interest-context-create-form")
    ?.addEventListener("submit", (event) => createInterestContext(event, state));
  document
    .querySelector("#interest-context-telegram-source-form")
    ?.addEventListener("submit", (event) => addInterestContextTelegramSource(event, state));
  document
    .querySelector("#interest-context-telegram-archive-form")
    ?.addEventListener("submit", (event) => uploadInterestContextTelegramArchive(event, state));
  document
    .querySelector("#interest-analysis-archive-form")
    ?.addEventListener("submit", (event) => uploadInterestAnalysisArchive(event, state));
  document
    .querySelector("#interest-analysis-refresh")
    ?.addEventListener("click", () => loadInterestAnalysisRuns(state));
  document
    .querySelector("#interest-analysis-runs")
    ?.addEventListener("click", (event) => handleInterestAnalysisRunsClick(event, state));
  document
    .querySelector("#interest-analysis-matches")
    ?.addEventListener("click", (event) => handleInterestAnalysisMatchesClick(event, state));
  document
    .querySelector("#interest-intent-layer-form")
    ?.addEventListener("submit", (event) => createInterestIntentLayer(event, state));
  document
    .querySelector("#interest-intent-refresh")
    ?.addEventListener("click", () => {
      loadInterestIntentLayers(state);
      loadInterestIntentRuns(state);
    });
  document
    .querySelector("#interest-intent-layers")
    ?.addEventListener("click", (event) => handleInterestIntentLayersClick(event, state));
  document
    .querySelector("#interest-intent-runs")
    ?.addEventListener("click", (event) => handleInterestIntentRunsClick(event, state));
  document
    .querySelector("#interest-intent-matches")
    ?.addEventListener("click", (event) => handleInterestIntentMatchesClick(event, state));
  document
    .querySelector("#interest-intent-exclusions-refresh")
    ?.addEventListener("click", () => loadInterestIntentExclusions(state));
  document
    .querySelector("#interest-intent-exclusions")
    ?.addEventListener("click", (event) => handleInterestIntentExclusionsClick(event, state));
  document
    .querySelector("#interest-context-build-draft")
    ?.addEventListener("click", () => buildInterestContextDraft(state));
  document
    .querySelector("#interest-context-enhance-draft-llm")
    ?.addEventListener("click", () => enhanceInterestContextDraftWithLlm(state));
  document
    .querySelector("#interest-context-llm-enhance-review")
    ?.addEventListener("click", (event) => {
      approveAllInterestCoreCandidateReviews(event, state);
      updateInterestCoreCandidateReviewStatus(event, state);
    });
  document
    .querySelector("#interest-context-open-raw-review")
    ?.addEventListener("click", () => loadInterestContextRawReview(state));
  document
    .querySelector("#interest-context-prepare-data")
    ?.addEventListener("click", () => startInterestContextDataPreparation(state));
  document
    .querySelector("#interest-context-prep-texts-refresh")
    ?.addEventListener("click", () => loadInterestContextPrepareTextsPage(state));
  document
    .querySelector("#interest-context-prep-texts")
    ?.addEventListener("click", (event) => changeInterestContextPrepTextsPage(event, state));
  document
    .querySelector("#interest-context-prep-fts-form")
    ?.addEventListener("submit", (event) => searchInterestContextPrepareFts(event, state));
  document
    .querySelector("#interest-context-prep-chroma-form")
    ?.addEventListener("submit", (event) => searchInterestContextPrepareChroma(event, state));
  document
    .querySelector("#interest-context-prep-features-refresh")
    ?.addEventListener("click", () => loadInterestContextPrepareFeaturesPage(state));
  document
    .querySelector("#interest-context-prep-features")
    ?.addEventListener("click", (event) => changeInterestContextPrepFeaturesPage(event, state));
  document
    .querySelector("#interest-context-prep-aggregates-refresh")
    ?.addEventListener("click", () => loadInterestContextPrepareAggregates(state));
  document
    .querySelector("#interest-context-prep-aggregates")
    ?.addEventListener("click", (event) => changeInterestContextPrepNgramsPage(event, state));
  document
    .querySelector("#interest-context-prep-aggregates")
    ?.addEventListener("change", (event) => changeInterestContextPrepNgramsKind(event, state));
  document
    .querySelector("#interest-context-prep-entities-refresh")
    ?.addEventListener("click", () => loadInterestContextPrepareEntitiesPage(state));
  document
    .querySelector("#interest-context-prep-entities")
    ?.addEventListener("click", (event) => changeInterestContextPrepEntitiesPage(event, state));
  document.addEventListener("change", (event) => handleInterestPrepRunChange(event, state));
  document
    .querySelector("#interest-core-brief-form")
    ?.addEventListener("submit", (event) => saveManualInterestCoreBrief(event, state));
  document
    .querySelector("#interest-core-brief-generate")
    ?.addEventListener("click", () => generateInterestCoreBrief(state));
  document
    .querySelector("#interest-context-draft-items-page")
    ?.addEventListener("click", (event) => changeInterestContextDraftItemsPage(event, state));
  document
    .querySelector("#interest-context-draft-items-refresh")
    ?.addEventListener("click", () => loadInterestContextDraftItemsPage(state));
  document
    .querySelector("#interest-context-review-items-page")
    ?.addEventListener("click", (event) => {
      approveAllInterestCoreCandidateReviews(event, state);
      updateInterestCoreCandidateReviewStatus(event, state);
      changeInterestContextReviewItemsPage(event, state);
    });
  document
    .querySelector("#interest-context-review-items-refresh")
    ?.addEventListener("click", () => loadInterestContextReviewItemsPage(state));
  document
    .querySelector("#interest-context-core-items-page")
    ?.addEventListener("click", (event) => changeInterestContextCoreItemsPage(event, state));
  document
    .querySelector("#interest-context-core-items-refresh")
    ?.addEventListener("click", () => loadInterestContextCoreItemsPage(state));
  document
    .querySelector("#interest-llm-provider-form")
    ?.addEventListener("submit", (event) => saveInterestLlmProvider(event));
  document
    .querySelector("#interest-llm-refresh")
    ?.addEventListener("click", () => loadInterestLlmConfig());
  setInterestContextFormsEnabled(false);
  loadInterestContexts(state);
  loadInterestLlmConfig();
}

async function loadInterestContexts(state) {
  const target = document.querySelector("#interest-context-list");
  try {
    const payload = await api("/api/interest-contexts");
    state.items = payload.items || [];
    const selectedStillVisible = state.items.some((item) => item.id === state.selectedId);
    state.selectedId = selectedStillVisible ? state.selectedId : state.items[0]?.id || null;
    updateInterestContextStepLinks(state.selectedId);
    renderInterestContextList(state);
    if (state.selectedId) {
      await loadInterestContextDetail(state.selectedId, state);
    } else {
      state.detail = null;
      renderInterestContextEmptyDetail();
    }
  } catch (error) {
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderInterestContextList(state) {
  const target = document.querySelector("#interest-context-list");
  if (!target) return;
  if (!state.items.length) {
    target.innerHTML = '<div class="empty-state">Контекстов пока нет</div>';
    return;
  }
  target.innerHTML = state.items
    .map((context) => {
      const active = context.id === state.selectedId ? "is-active" : "";
      return `<button class="queue-item ${active}" type="button" data-id="${escapeHtml(context.id)}">
        <strong>${escapeHtml(context.name)}</strong>
        <span class="muted">${escapeHtml(context.description || "без описания")}</span>
        <span class="queue-meta">${badge(label(context.status || "draft"))}${badge(time(context.updated_at) || "новый")}</span>
      </button>`;
    })
    .join("");
  target.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.id;
      setSelectedInterestContextUrl(state.selectedId);
      renderInterestContextList(state);
      await loadInterestContextDetail(state.selectedId, state);
    });
  });
}

async function loadInterestContextDetail(contextId, state) {
  stopInterestContextPreparePolling(state);
  stopInterestContextDraftPolling(state);
  stopInterestContextEnhancementPolling(state);
  stopInterestCoreBriefPolling(state);
  const detail = await api(`/api/interest-contexts/${encodeURIComponent(contextId)}`);
  state.detail = detail;
  renderInterestContextDetail(detail);
  await loadInterestContextPrepareStatus(state, { silent: true });
  if (state.step === "core") {
    await loadInterestContextDraftStatus(state, { silent: true });
    await loadInterestContextEnhancementStatus(state, { silent: true });
  }
  if (state.step === "candidates") {
    state.draftItemsOffset = 0;
    await loadInterestContextDraftItemsPage(state);
  }
  if (state.step === "reviews") {
    await loadInterestContextEnhancementStatus(state, { silent: true });
    state.reviewItemsOffset = 0;
    await loadInterestContextReviewItemsPage(state);
  }
  if (state.step === "items") {
    state.coreItemsOffset = 0;
    await loadInterestContextCoreItemsPage(state);
  }
  if (state.step === "analysis_upload") {
    state.analysisRunsOffset = 0;
    state.analysisMatchesOffset = 0;
    state.selectedAnalysisRunId = null;
  }
  if (state.step === "analysis_runs") {
    state.analysisRunsOffset = 0;
    state.analysisMatchesOffset = 0;
    state.selectedAnalysisRunId = null;
    await loadInterestAnalysisRuns(state);
  }
  if (state.step === "analysis_matches") {
    state.analysisRunsOffset = 0;
    state.analysisMatchesOffset = 0;
    state.selectedAnalysisRunId = null;
    await loadInterestAnalysisRuns(state);
    if (state.selectedAnalysisRunId) {
      await loadInterestAnalysisMatches(state, state.selectedAnalysisRunId);
    }
  }
  if (state.step === "intent_layers") {
    state.analysisRunsOffset = 0;
    state.selectedAnalysisRunId = null;
    await loadInterestAnalysisRuns(state);
    await loadInterestIntentLayers(state);
  }
  if (state.step === "intent_runs") {
    state.intentRunsOffset = 0;
    state.intentMatchesOffset = 0;
    state.selectedIntentRunId = null;
    await loadInterestIntentRuns(state);
  }
  if (state.step === "intent_matches") {
    state.intentRunsOffset = 0;
    state.intentMatchesOffset = 0;
    state.selectedIntentRunId = null;
    await loadInterestIntentRuns(state);
    if (state.selectedIntentRunId) {
      await loadInterestIntentMatches(state, state.selectedIntentRunId);
    }
  }
  if (state.step === "intent_exclusions") {
    state.intentExclusionsOffset = 0;
    await loadInterestIntentExclusions(state);
  }
  if (state.step === "brief") {
    await loadInterestCoreBriefStatus(state, { silent: true });
  }
  if (state.step === "check") {
    await loadInterestContextRawReview(state);
  }
  if (state.step === "prepare_texts") {
    state.prepTextsOffset = 0;
    await loadInterestPrepareRunSelector(state, "text_normalization");
    await loadInterestContextPrepareTextsPage(state);
  }
  if (state.step === "prepare_search_fts") {
    await loadInterestPrepareRunSelector(state, "fts_index");
  }
  if (state.step === "prepare_search_chroma") {
    await loadInterestPrepareRunSelector(state, "chroma_index");
  }
  if (state.step === "prepare_features") {
    state.prepFeaturesOffset = 0;
    await loadInterestPrepareRunSelector(state, "feature_enrichment");
    await loadInterestContextPrepareFeaturesPage(state);
  }
  if (state.step === "prepare_aggregates") {
    state.prepNgramsOffset = 0;
    await loadInterestPrepareRunSelector(state, "aggregated_stats");
    await loadInterestContextPrepareAggregates(state);
  }
  if (state.step === "prepare_entities") {
    state.prepEntitiesOffset = 0;
    await loadInterestPrepareRunSelector(state, "entity_ranking");
    await loadInterestContextPrepareEntitiesPage(state);
  }
}

function renderInterestContextEmptyDetail() {
  setInterestContextFormsEnabled(false);
  delete document.body.dataset.interestContextId;
  updateInterestContextStepLinks(null);
  const title = document.querySelector("#interest-context-detail-title");
  const description = document.querySelector("#interest-context-detail-description");
  const badges = document.querySelector("#interest-context-detail-badges");
  const sources = document.querySelector("#interest-context-source-list");
  const rawReview = document.querySelector("#interest-context-raw-review");
  const prepareProgress = document.querySelector("#interest-context-prepare-progress");
  const draftReview = document.querySelector("#interest-context-draft-review");
  const enhanceReview = document.querySelector("#interest-context-llm-enhance-review");
  const briefProgress = document.querySelector("#interest-core-brief-progress");
  const briefList = document.querySelector("#interest-core-brief-list");
  const briefText = document.querySelector("#interest-core-brief-text");
  const analysisRuns = document.querySelector("#interest-analysis-runs");
  const analysisMatches = document.querySelector("#interest-analysis-matches");
  const intentLayers = document.querySelector("#interest-intent-layers");
  const intentRuns = document.querySelector("#interest-intent-runs");
  const intentMatches = document.querySelector("#interest-intent-matches");
  const prepTexts = document.querySelector("#interest-context-prep-texts");
  const prepFts = document.querySelector("#interest-context-prep-fts-results");
  const prepChroma = document.querySelector("#interest-context-prep-chroma-results");
  const prepFeatures = document.querySelector("#interest-context-prep-features");
  const prepAggregates = document.querySelector("#interest-context-prep-aggregates");
  const prepEntities = document.querySelector("#interest-context-prep-entities");
  if (title) title.textContent = "Выберите контекст";
  if (description) {
    description.textContent = "Сначала создайте контекст, затем загрузите архив источника для этого контекста.";
  }
  if (badges) badges.innerHTML = "";
  if (sources) sources.innerHTML = '<div class="empty-state">Источников пока нет</div>';
  if (rawReview) rawReview.innerHTML = "";
  if (prepareProgress) prepareProgress.innerHTML = "";
  if (draftReview) draftReview.innerHTML = "";
  if (enhanceReview) enhanceReview.innerHTML = "";
  if (briefProgress) briefProgress.innerHTML = "";
  if (briefList) briefList.innerHTML = "";
  if (briefText) briefText.value = "";
  if (analysisRuns) analysisRuns.innerHTML = "";
  if (analysisMatches) analysisMatches.innerHTML = "";
  if (intentLayers) intentLayers.innerHTML = "";
  if (intentRuns) intentRuns.innerHTML = "";
  if (intentMatches) intentMatches.innerHTML = "";
  if (prepTexts) prepTexts.innerHTML = "";
  if (prepFts) prepFts.innerHTML = "";
  if (prepChroma) prepChroma.innerHTML = "";
  if (prepFeatures) prepFeatures.innerHTML = "";
  if (prepAggregates) prepAggregates.innerHTML = "";
  if (prepEntities) prepEntities.innerHTML = "";
}

function renderInterestContextDetail(detail) {
  const context = detail.context || {};
  if (context.id) document.body.dataset.interestContextId = context.id;
  updateInterestContextStepLinks(context.id || null);
  const title = document.querySelector("#interest-context-detail-title");
  const description = document.querySelector("#interest-context-detail-description");
  const badges = document.querySelector("#interest-context-detail-badges");
  const sources = document.querySelector("#interest-context-source-list");
  setInterestContextFormsEnabled(Boolean(context.id));
  if (title) title.textContent = context.name || "Ядро интересов";
  if (description) description.textContent = context.description || "Описание не задано";
  if (badges) {
    badges.innerHTML = `${badge(label(context.status || "draft"))}${badge(`обновлено ${time(context.updated_at) || "сейчас"}`)}`;
  }
  if (!sources) return;
  const sourceRows = detail.sources || [];
  if (!sourceRows.length) {
    sources.innerHTML = '<div class="empty-state">Загрузите архив источника для выбранного контекста</div>';
    return;
  }
  sources.innerHTML = sourceRows
    .map((source) => {
      const rawRun = source.latest_raw_export_run || null;
      const titleText = source.title || source.username || source.input_ref || source.id;
      const rawText = rawRun
        ? `${rawRun.message_count || 0} сообщений / ${rawRun.attachment_count || 0} вложений`
        : "raw-артефакты еще не созданы";
      const reviewControl =
        currentInterestStep() === "check"
          ? `<md-filled-tonal-button type="button" data-open-raw-review>Проверить данные</md-filled-tonal-button>`
          : `<a class="button-link" href="${escapeHtml(interestContextStepHref("/interest-contexts/check", context.id))}">Проверить данные</a>`;
      return `<div class="resource-row">
        <div class="resource-kind">
          <md-icon aria-hidden="true">${rawRun ? "archive" : "database"}</md-icon>
          <span>${escapeHtml(label(source.source_kind || "telegram"))}</span>
        </div>
        <div class="resource-primary">
          <strong>${escapeHtml(titleText)}</strong>
          <p class="muted">${escapeHtml(source.input_ref || "")}</p>
          <p class="muted">${escapeHtml(rawText)}</p>
        </div>
        <div>
          ${badge(label(source.status || "draft"), sourceStatusClass(source.status))}
          ${rawRun ? badge(label(rawRun.status || "unknown"), rawRun.status === "failed" ? "is-danger" : "") : ""}
        </div>
        <div class="resource-actions">
          ${reviewControl}
        </div>
      </div>`;
    })
    .join("");
  sources.querySelectorAll("[data-open-raw-review]").forEach((button) => {
    button.addEventListener("click", () =>
      loadInterestContextRawReview({ selectedId: detail.context?.id })
    );
  });
}

function currentInterestStep() {
  return document.querySelector("[data-interest-step]")?.dataset.interestStep || "context";
}

function interestContextStepHref(path, contextId) {
  if (!contextId) return path;
  const url = new URL(path, window.location.origin);
  url.searchParams.set("context_id", contextId);
  return `${url.pathname}${url.search}`;
}

function updateInterestContextStepLinks(contextId) {
  document.querySelectorAll("[data-interest-step-link], .interest-next-link, .linked-row").forEach((link) => {
    const rawHref = link.getAttribute("href") || "/interest-contexts";
    const url = new URL(rawHref, window.location.origin);
    if (contextId) {
      url.searchParams.set("context_id", contextId);
    } else {
      url.searchParams.delete("context_id");
    }
    link.setAttribute("href", `${url.pathname}${url.search}`);
  });
}

function setSelectedInterestContextUrl(contextId) {
  updateInterestContextStepLinks(contextId);
  const url = new URL(window.location.href);
  if (contextId) {
    url.searchParams.set("context_id", contextId);
  } else {
    url.searchParams.delete("context_id");
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}`);
}

async function createInterestContext(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#interest-context-status");
  try {
    const payload = await api("/api/interest-contexts", {
      method: "POST",
      body: JSON.stringify({
        name: formValue(form, "name"),
        description: formValue(form, "description") || null,
      }),
    });
    form.reset();
    state.selectedId = payload.context?.id || null;
    setSelectedInterestContextUrl(state.selectedId);
    if (status) status.textContent = "Контекст создан";
    await loadInterestContexts(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function addInterestContextTelegramSource(event, state) {
  event.preventDefault();
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  const form = event.currentTarget;
  const data = new FormData(form);
  const numberOrNull = (name) => {
    const value = Number.parseInt(data.get(name), 10);
    return Number.isNaN(value) ? null : value;
  };
  const mediaTypes = data.getAll("media_types");
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/telegram-source`,
      {
        method: "POST",
        body: JSON.stringify({
          input_ref: formValue(form, "input_ref"),
          range_mode: data.get("range_mode") || "from_beginning",
          recent_days: numberOrNull("recent_days"),
          message_id: numberOrNull("message_id"),
          since_date: formValue(form, "since_date") || null,
          batch_size: numberOrNull("batch_size") || 1000,
          max_messages: numberOrNull("max_messages"),
          media_enabled: data.get("media_enabled") === "on",
          media_types: mediaTypes.length ? mediaTypes : ["document"],
          max_media_size_bytes: numberOrNull("max_media_size_bytes"),
          check_access: data.get("check_access") === "on",
          enqueue_raw_export: data.get("enqueue_raw_export") === "on",
        }),
      }
    );
    form.reset();
    form.querySelector('[name="media_types"][value="document"]').checked = true;
    form.querySelector('[name="enqueue_raw_export"]').checked = true;
    if (status) {
      status.textContent = payload.raw_export_job
        ? "Источник добавлен, raw-выгрузка поставлена в очередь"
        : "Источник добавлен";
    }
    await loadInterestContexts(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function uploadInterestContextTelegramArchive(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#interest-context-upload-status");
  const submitButton = form.querySelector('md-filled-button[type="submit"]');
  const fileInput = form.querySelector('input[name="file"]');
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  if (!fileInput?.files?.[0]) {
    if (status) status.textContent = "Выберите zip-архив Telegram Desktop.";
    return;
  }
  const data = new FormData(form);
  data.set(
    "sync_source_messages",
    form.querySelector('[name="sync_source_messages"]')?.checked ? "true" : "false"
  );
  try {
    setInterestContextUploadProgress({ visible: true, value: 0, label: "0%" });
    if (submitButton) submitButton.disabled = true;
    if (status) status.textContent = "Загружаю архив...";
    const payload = await uploadFormData(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/telegram-archive`,
      data,
      {
        onProgress: (value) => {
          const percent = Math.round(value * 100);
          setInterestContextUploadProgress({ visible: true, value, label: `${percent}%` });
          if (status) status.textContent = `Загрузка архива: ${percent}%`;
        },
        onProcessing: () => {
          setInterestContextUploadProgress({
            visible: true,
            indeterminate: true,
            label: "обработка",
          });
          if (status) status.textContent = "Архив получен. Создаю raw/parquet артефакты...";
        },
      }
    );
    form.reset();
    if (status) {
      status.textContent = `Архив загружен. Сообщений: ${payload.result?.message_count || 0}`;
    }
    await loadInterestContexts(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  } finally {
    if (submitButton) submitButton.disabled = false;
    setInterestContextUploadProgress({ visible: false, value: 0, label: "0%" });
  }
}

function setInterestContextUploadProgress({ visible, value = 0, label = "", indeterminate = false }) {
  const container = document.querySelector("#interest-context-upload-progress");
  const progress = document.querySelector("#interest-context-upload-progress-bar");
  const labelTarget = document.querySelector("#interest-context-upload-progress-label");
  if (!container || !progress) return;
  container.classList.toggle("is-hidden", !visible);
  if (indeterminate) {
    progress.setAttribute("indeterminate", "");
    progress.removeAttribute("value");
  } else {
    progress.removeAttribute("indeterminate");
    progress.value = Math.max(0, Math.min(1, value));
    progress.setAttribute("value", String(progress.value));
  }
  if (labelTarget) labelTarget.textContent = label;
}

async function uploadInterestAnalysisArchive(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#interest-analysis-status");
  const submitButton = form.querySelector('md-filled-button[type="submit"]');
  const fileInput = form.querySelector('input[name="file"]');
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  if (!fileInput?.files?.[0]) {
    if (status) status.textContent = "Выберите zip-архив Telegram Desktop.";
    return;
  }
  const data = new FormData(form);
  try {
    setInterestAnalysisUploadProgress({ visible: true, value: 0, label: "0%" });
    if (submitButton) submitButton.disabled = true;
    if (status) status.textContent = "Загружаю архив для анализа...";
    const payload = await uploadFormData(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/analysis/telegram-archive`,
      data,
      {
        onProgress: (value) => {
          const percent = Math.round(value * 100);
          setInterestAnalysisUploadProgress({ visible: true, value, label: `${percent}%` });
          if (status) status.textContent = `Загрузка архива: ${percent}%`;
        },
        onProcessing: () => {
          setInterestAnalysisUploadProgress({
            visible: true,
            indeterminate: true,
            label: "анализ",
          });
          if (status) {
            status.textContent = "Архив получен. Создаю raw/parquet и считаю совпадения...";
          }
        },
      }
    );
    form.reset();
    const summary = payload.analysis?.summary || {};
    const runId = payload.analysis?.run?.id || null;
    state.selectedAnalysisRunId = runId;
    state.analysisRunsOffset = 0;
    state.analysisMatchesOffset = 0;
    if (status) {
      status.textContent = `Анализ готов: ${summary.match_count || 0} совпадений, ${summary.matched_message_count || 0} сообщений`;
    }
    await loadInterestContexts(state);
    await loadInterestAnalysisRuns(state);
    if (runId) await loadInterestAnalysisMatches(state, runId);
  } catch (error) {
    if (status) status.textContent = error.message;
  } finally {
    if (submitButton) submitButton.disabled = false;
    setInterestAnalysisUploadProgress({ visible: false, value: 0, label: "0%" });
  }
}

function setInterestAnalysisUploadProgress({ visible, value = 0, label = "", indeterminate = false }) {
  const container = document.querySelector("#interest-analysis-upload-progress");
  const progress = document.querySelector("#interest-analysis-upload-progress-bar");
  const labelTarget = document.querySelector("#interest-analysis-upload-progress-label");
  if (!container || !progress) return;
  container.classList.toggle("is-hidden", !visible);
  if (indeterminate) {
    progress.setAttribute("indeterminate", "");
    progress.removeAttribute("value");
  } else {
    progress.removeAttribute("indeterminate");
    progress.value = Math.max(0, Math.min(1, value));
    progress.setAttribute("value", String(progress.value));
  }
  if (labelTarget) labelTarget.textContent = label;
}

async function loadInterestAnalysisRuns(state) {
  const target = document.querySelector("#interest-analysis-runs");
  const status = document.querySelector("#interest-analysis-status");
  if (!state.selectedId) return;
  if (target) target.innerHTML = '<div class="empty-state">Загружаю запуски анализа...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.analysisRunsLimit),
      offset: String(state.analysisRunsOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/analysis/runs?${params.toString()}`
    );
    const firstRun = payload.items?.[0]?.id || null;
    const selectedStillVisible = (payload.items || []).some(
      (item) => item.id === state.selectedAnalysisRunId
    );
    state.selectedAnalysisRunId = selectedStillVisible
      ? state.selectedAnalysisRunId
      : firstRun;
    if (target) renderInterestAnalysisRuns(payload, state);
    if (state.selectedAnalysisRunId && document.querySelector("#interest-analysis-matches")) {
      await loadInterestAnalysisMatches(state, state.selectedAnalysisRunId);
    } else if (document.querySelector("#interest-analysis-matches")) {
      renderInterestAnalysisMatches(null, state);
    }
  } catch (error) {
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function handleInterestAnalysisRunsClick(event, state) {
  const pageButton = event.target.closest("[data-analysis-runs-page-action]");
  if (pageButton) {
    const action = pageButton.dataset.analysisRunsPageAction;
    if (action === "prev") {
      state.analysisRunsOffset = Math.max(0, state.analysisRunsOffset - state.analysisRunsLimit);
    }
    if (action === "next") {
      state.analysisRunsOffset += state.analysisRunsLimit;
    }
    loadInterestAnalysisRuns(state);
    return;
  }
  const runButton = event.target.closest("[data-analysis-run-id]");
  if (!runButton) return;
  state.selectedAnalysisRunId = runButton.dataset.analysisRunId;
  state.analysisMatchesOffset = 0;
  renderInterestAnalysisRunSelection(state.selectedAnalysisRunId);
  loadInterestAnalysisMatches(state, state.selectedAnalysisRunId);
}

function handleInterestAnalysisMatchesClick(event, state) {
  const pageButton = event.target.closest("[data-analysis-matches-page-action]");
  if (!pageButton || !state.selectedAnalysisRunId) return;
  const action = pageButton.dataset.analysisMatchesPageAction;
  if (action === "prev") {
    state.analysisMatchesOffset = Math.max(
      0,
      state.analysisMatchesOffset - state.analysisMatchesLimit
    );
  }
  if (action === "next") {
    state.analysisMatchesOffset += state.analysisMatchesLimit;
  }
  loadInterestAnalysisMatches(state, state.selectedAnalysisRunId);
}

function renderInterestAnalysisRuns(payload, state) {
  const target = document.querySelector("#interest-analysis-runs");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.analysisRunsLimit, offset: 0, total: 0 };
  if (!items.length) {
    target.innerHTML = '<div class="empty-state">Загрузите ZIP-архив чата, чтобы получить первый анализ по ядру.</div>';
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <p class="muted">Каждая строка - отдельный широкий запуск: конкретный raw-run чата, версия рабочего ядра на момент запуска и результат локального matching.</p>
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
        ${renderOpsMetric("Запуски", pagination.total || 0, "в этом контексте")}
        ${renderOpsMetric("Последний анализ", payload.summary?.latest_match_count || 0, "совпадений")}
        ${renderOpsMetric("Сообщения", payload.summary?.latest_matched_message_count || 0, "с совпадениями")}
      </div>
    </div>
    <div class="table-list">${items.map((item) => renderInterestAnalysisRunRow(item, state)).join("")}</div>
    ${renderPageControls(pagination, "analysis-runs")}
  </section>`;
}

function renderInterestAnalysisRunSelection(runId) {
  document.querySelectorAll("[data-analysis-run-id]").forEach((row) => {
    row.classList.toggle("is-active", row.dataset.analysisRunId === runId);
  });
}

function renderInterestAnalysisRunRow(item, state) {
  const summary = item.summary_json || {};
  const active = item.id === state.selectedAnalysisRunId ? "is-active" : "";
  const title = item.source_title || item.raw_export_run_id || item.id;
  return `<button class="table-row linked-row analysis-run-row ${active}" type="button" data-analysis-run-id="${escapeHtml(item.id)}">
    <div>
      <strong>${escapeHtml(title)}</strong>
      <p class="muted">${escapeHtml([time(item.created_at), `run ${item.id}`].filter(Boolean).join(" / "))}</p>
      <div class="badges">
        ${badge(label(item.status || "unknown"), item.status === "failed" ? "is-danger" : "")}
        ${item.raw_export_run_id ? badge(`raw ${shortId(item.raw_export_run_id)}`) : ""}
        ${badge(`${item.message_count || 0} сообщений`)}
        ${badge(`${item.core_item_count || 0} элементов ядра`)}
        ${badge(`${item.match_count || 0} совпадений`)}
        ${badge(`${item.matched_message_count || 0} сообщений найдено`)}
      </div>
      <p class="draft-evidence"><strong>Чем отличается:</strong> архив/чат ${escapeHtml(title)}, raw-run ${escapeHtml(item.raw_export_run_id || "н/д")}, алгоритм ${escapeHtml(summary.algorithm || "local_interest_core_match_v1")}.</p>
      ${renderAnalysisCounters(summary.by_category, "Категории")}
    </div>
    <span>Открыть</span>
  </button>`;
}

async function loadInterestAnalysisMatches(state, runId) {
  const target = document.querySelector("#interest-analysis-matches");
  const status = document.querySelector("#interest-analysis-status");
  if (!target || !state.selectedId || !runId) return;
  target.innerHTML = '<div class="empty-state">Загружаю найденные сообщения...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.analysisMatchesLimit),
      offset: String(state.analysisMatchesOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/analysis/runs/${encodeURIComponent(runId)}/matches?${params.toString()}`
    );
    renderInterestAnalysisMatches(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function renderInterestAnalysisMatches(payload, state) {
  const target = document.querySelector("#interest-analysis-matches");
  if (!target) return;
  if (!payload) {
    target.innerHTML = '<div class="empty-state">Запуск анализа еще не выбран.</div>';
    return;
  }
  const items = payload.items || [];
  const pagination =
    payload.pagination || { limit: state.analysisMatchesLimit, offset: 0, total: 0 };
  const run = payload.run || {};
  if (!items.length) {
    target.innerHTML = `<div class="empty-state">В запуске ${escapeHtml(run.id || "")} совпадений нет.</div>`;
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head compact-section-head">
      <h4>Сообщения из запуска ${escapeHtml(run.id || "")}</h4>
      <span class="muted">${escapeHtml(`${pagination.offset + 1}-${Math.min(pagination.offset + items.length, pagination.total)} из ${pagination.total}`)}</span>
    </div>
    <p class="muted">Широкий слой объясняет, какой элемент рабочего ядра совпал с сообщением. Это вход для следующего, более строгого слоя намерений.</p>
    <div class="table-list">${items.map(renderInterestAnalysisMatchRow).join("")}</div>
    ${renderPageControls(pagination, "analysis-matches")}
  </section>`;
}

function renderInterestAnalysisMatchRow(item) {
  const evidence = item.evidence_json || {};
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.canonical_name || "элемент ядра")}</strong>
      <p class="muted">${escapeHtml([`сообщение #${item.telegram_message_id || "н/д"}`, time(item.message_date), item.sender_id].filter(Boolean).join(" / "))}</p>
      <p>${escapeHtml(shortText(item.message_text || "без текста", 420))}</p>
      <div class="badges">
        ${item.category ? badge(item.category) : ""}
        ${badge(label(item.match_kind || "match"))}
        ${badge(`score ${formatScore(item.score)}`)}
        ${item.matched_text ? badge(`совпало: ${item.matched_text}`) : ""}
      </div>
      ${renderAnalysisEvidence(evidence)}
      ${renderTelegramMessageLink(item)}
    </div>
  </div>`;
}

function renderTelegramMessageLink(item) {
  const url = item.message_url || item.telegram_message_url || item.evidence_json?.message_url || "";
  return url
    ? `<p class="draft-evidence"><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Открыть сообщение в Telegram</a></p>`
    : "";
}

function shortId(value) {
  const text = String(value || "");
  return text.length > 8 ? text.slice(0, 8) : text;
}

function renderAnalysisEvidence(evidence) {
  const parts = [];
  if (Array.isArray(evidence.matched_tokens) && evidence.matched_tokens.length) {
    parts.push(`токены: ${evidence.matched_tokens.slice(0, 8).join(", ")}`);
  }
  if (Array.isArray(evidence.noise_hits) && evidence.noise_hits.length) {
    parts.push(`шум: ${evidence.noise_hits.slice(0, 3).join(", ")}`);
  }
  if (evidence.hit_kind) parts.push(`тип совпадения: ${label(evidence.hit_kind)}`);
  return parts.length
    ? `<p class="draft-evidence"><strong>Почему найдено:</strong> ${escapeHtml(parts.join("; "))}</p>`
    : "";
}

function renderAnalysisCounters(value, title) {
  if (!value || typeof value !== "object") return "";
  const items = Object.entries(value).slice(0, 4);
  if (!items.length) return "";
  return `<p class="draft-evidence"><strong>${escapeHtml(title)}:</strong> ${escapeHtml(items.map(([key, count]) => `${key}: ${count}`).join("; "))}</p>`;
}

const formLines = (form, name) =>
  String(formValue(form, name) || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

const formNumber = (form, name, fallback) => {
  const value = Number.parseFloat(formValue(form, name));
  return Number.isFinite(value) ? value : fallback;
};

async function createInterestIntentLayer(event, state) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#interest-intent-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  try {
    await api(`/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-layers`, {
      method: "POST",
      body: JSON.stringify({
        name: formValue(form, "name"),
        description: formValue(form, "description") || null,
        include_patterns: formLines(form, "include_patterns"),
        context_patterns: formLines(form, "context_patterns"),
        exclude_patterns: formLines(form, "exclude_patterns"),
        exclude_core_names: formLines(form, "exclude_core_names"),
        include_categories: [],
        exclude_categories: [],
        include_core_names: [],
        require_include_match: formChecked(form, "require_include_match"),
        require_context_match: formChecked(form, "require_context_match"),
        min_score: formNumber(form, "min_score", 0.55),
        max_results: Math.max(1, Math.round(formNumber(form, "max_results", 3000))),
        broad_score_weight: formNumber(form, "broad_score_weight", 0.45),
        intent_hit_weight: formNumber(form, "intent_hit_weight", 0.18),
      }),
    });
    if (status) status.textContent = "Слой намерений добавлен";
    await loadInterestIntentLayers(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadInterestIntentLayers(state) {
  const target = document.querySelector("#interest-intent-layers");
  const status = document.querySelector("#interest-intent-status");
  if (!target || !state.selectedId) return;
  target.innerHTML = '<div class="empty-state">Загружаю слои намерений...</div>';
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-layers`
    );
    renderInterestIntentLayers(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function renderInterestIntentLayers(payload, state) {
  const target = document.querySelector("#interest-intent-layers");
  if (!target) return;
  const items = payload.items || [];
  if (!items.length) {
    target.innerHTML = '<div class="empty-state">Слоев намерений пока нет.</div>';
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <p class="muted">Сохраненные слои - это настраиваемые правила второго уровня. Их можно применить к выбранному широкому запуску анализа.</p>
    <div class="table-list">${items.map((item) => renderInterestIntentLayerRow(item, state)).join("")}</div>
  </section>`;
}

function renderInterestIntentLayerRow(item, state) {
  const selectedBroad = state.selectedAnalysisRunId;
  const includeCount = Array.isArray(item.include_patterns_json)
    ? item.include_patterns_json.length
    : 0;
  const excludeCount = Array.isArray(item.exclude_patterns_json)
    ? item.exclude_patterns_json.length
    : 0;
  const contextCount = Array.isArray(item.context_patterns_json)
    ? item.context_patterns_json.length
    : 0;
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.name || "Слой намерений")}</strong>
      <p class="muted">${escapeHtml(item.description || "без описания")}</p>
      <div class="badges">
        ${badge(label(item.status || "active"))}
        ${badge(`include ${includeCount}`)}
        ${badge(`context ${contextCount}`)}
        ${badge(`exclude ${excludeCount}`)}
        ${badge(`min ${formatScore(item.min_score)}`)}
        ${badge(`limit ${item.max_results || 0}`)}
      </div>
      <p class="draft-evidence"><strong>Источник:</strong> ${escapeHtml(selectedBroad ? `выбран широкий запуск ${selectedBroad}` : "выберите широкий запуск выше")}</p>
      <p class="draft-evidence"><strong>Логика:</strong> include ищет действие/намерение, context подтверждает тематику, exclude отсекает шум, min score задает порог попадания.</p>
    </div>
    <div class="button-column">
      <md-filled-tonal-button type="button" data-intent-layer-action="run" data-intent-layer-id="${escapeHtml(item.id)}">
        <md-icon slot="icon">filter_alt</md-icon>
        Применить
      </md-filled-tonal-button>
      <md-outlined-button type="button" data-intent-layer-action="delete" data-intent-layer-id="${escapeHtml(item.id)}">
        Удалить
      </md-outlined-button>
    </div>
  </div>`;
}

async function handleInterestIntentLayersClick(event, state) {
  const button = event.target.closest("[data-intent-layer-action]");
  if (!button) return;
  const layerId = button.dataset.intentLayerId;
  const action = button.dataset.intentLayerAction;
  if (action === "run") {
    await runInterestIntentLayer(layerId, state);
  }
  if (action === "delete") {
    await deleteInterestIntentLayer(layerId, state);
  }
}

async function runInterestIntentLayer(layerId, state) {
  const status = document.querySelector("#interest-intent-status");
  if (!state.selectedId || !layerId) return;
  if (!state.selectedAnalysisRunId) {
    if (status) status.textContent = "Сначала выберите широкий запуск анализа выше";
    return;
  }
  try {
    if (status) status.textContent = "Применяю слой намерений...";
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-layers/${encodeURIComponent(layerId)}/runs`,
      {
        method: "POST",
        body: JSON.stringify({ broad_analysis_run_id: state.selectedAnalysisRunId }),
      }
    );
    const summary = payload.summary || {};
    state.selectedIntentRunId = payload.run?.id || null;
    state.intentRunsOffset = 0;
    state.intentMatchesOffset = 0;
    if (status) {
      status.textContent = `Слой намерений готов: ${summary.match_count || 0} совпадений, ${summary.matched_message_count || 0} сообщений`;
    }
    await loadInterestIntentRuns(state);
    if (state.selectedIntentRunId) await loadInterestIntentMatches(state, state.selectedIntentRunId);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function deleteInterestIntentLayer(layerId, state) {
  const status = document.querySelector("#interest-intent-status");
  if (!state.selectedId || !layerId) return;
  try {
    await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-layers/${encodeURIComponent(layerId)}`,
      { method: "DELETE" }
    );
    if (status) status.textContent = "Слой намерений удален";
    await loadInterestIntentLayers(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadInterestIntentRuns(state) {
  const target = document.querySelector("#interest-intent-runs");
  const status = document.querySelector("#interest-intent-status");
  if (!state.selectedId) return;
  if (target) target.innerHTML = '<div class="empty-state">Загружаю запуски слоя намерений...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.intentRunsLimit),
      offset: String(state.intentRunsOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-runs?${params.toString()}`
    );
    const firstRun = payload.items?.[0]?.id || null;
    const selectedStillVisible = (payload.items || []).some(
      (item) => item.id === state.selectedIntentRunId
    );
    state.selectedIntentRunId = selectedStillVisible ? state.selectedIntentRunId : firstRun;
    if (target) renderInterestIntentRuns(payload, state);
    if (state.selectedIntentRunId && document.querySelector("#interest-intent-matches")) {
      await loadInterestIntentMatches(state, state.selectedIntentRunId);
    } else if (document.querySelector("#interest-intent-matches")) {
      renderInterestIntentMatches(null, state);
    }
  } catch (error) {
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function renderInterestIntentRuns(payload, state) {
  const target = document.querySelector("#interest-intent-runs");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.intentRunsLimit, offset: 0, total: 0 };
  if (!items.length) {
    target.innerHTML = '<div class="empty-state">Примените слой намерений к широкому запуску анализа.</div>';
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <p class="muted">Каждый запуск намерений - это конкретный слой, примененный к конкретному широкому запуску. Сравнивайте layer/run id и счетчики входных совпадений.</p>
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
        ${renderOpsMetric("Запуски", pagination.total || 0, "слои намерений")}
        ${renderOpsMetric("Последний запуск", payload.summary?.latest_match_count || 0, "совпадений")}
        ${renderOpsMetric("Сообщения", payload.summary?.latest_matched_message_count || 0, "с намерением")}
      </div>
    </div>
    <div class="table-list">${items.map((item) => renderInterestIntentRunRow(item, state)).join("")}</div>
    ${renderPageControls(pagination, "intent-runs")}
  </section>`;
}

function renderInterestIntentRunRow(item, state) {
  const summary = item.summary_json || {};
  const active = item.id === state.selectedIntentRunId ? "is-active" : "";
  const title = item.source_title || item.id;
  return `<button class="table-row linked-row analysis-run-row ${active}" type="button" data-intent-run-id="${escapeHtml(item.id)}">
    <div>
      <strong>${escapeHtml(title)}</strong>
      <p class="muted">${escapeHtml([time(item.created_at), `run ${item.id}`].filter(Boolean).join(" / "))}</p>
      <div class="badges">
        ${badge(label(item.status || "unknown"), item.status === "failed" ? "is-danger" : "")}
        ${item.intent_layer_id ? badge(`layer ${shortId(item.intent_layer_id)}`) : ""}
        ${item.broad_analysis_run_id ? badge(`broad ${shortId(item.broad_analysis_run_id)}`) : ""}
        ${badge(`${item.broad_match_count || 0} входных совпадений`)}
        ${badge(`${item.match_count || 0} намерений`)}
        ${badge(`${item.matched_message_count || 0} сообщений`)}
      </div>
      <p class="draft-evidence"><strong>Чем отличается:</strong> слой ${escapeHtml(item.intent_layer_id || "н/д")} применен к широкому запуску ${escapeHtml(item.broad_analysis_run_id || "н/д")}.</p>
      ${renderAnalysisCounters(summary.by_category, "Категории")}
    </div>
    <span>Открыть</span>
  </button>`;
}

function handleInterestIntentRunsClick(event, state) {
  const pageButton = event.target.closest("[data-intent-runs-page-action]");
  if (pageButton) {
    const action = pageButton.dataset.intentRunsPageAction;
    if (action === "prev") {
      state.intentRunsOffset = Math.max(0, state.intentRunsOffset - state.intentRunsLimit);
    }
    if (action === "next") {
      state.intentRunsOffset += state.intentRunsLimit;
    }
    loadInterestIntentRuns(state);
    return;
  }
  const runButton = event.target.closest("[data-intent-run-id]");
  if (!runButton) return;
  state.selectedIntentRunId = runButton.dataset.intentRunId;
  state.intentMatchesOffset = 0;
  renderInterestIntentRunSelection(state.selectedIntentRunId);
  loadInterestIntentMatches(state, state.selectedIntentRunId);
}

function renderInterestIntentRunSelection(runId) {
  document.querySelectorAll("[data-intent-run-id]").forEach((row) => {
    row.classList.toggle("is-active", row.dataset.intentRunId === runId);
  });
}

async function loadInterestIntentMatches(state, runId) {
  const target = document.querySelector("#interest-intent-matches");
  const status = document.querySelector("#interest-intent-status");
  if (!target || !state.selectedId || !runId) return;
  target.innerHTML = '<div class="empty-state">Загружаю сообщения слоя намерений...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.intentMatchesLimit),
      offset: String(state.intentMatchesOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-runs/${encodeURIComponent(runId)}/matches?${params.toString()}`
    );
    renderInterestIntentMatches(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function renderInterestIntentMatches(payload, state) {
  const target = document.querySelector("#interest-intent-matches");
  if (!target) return;
  if (!payload) {
    target.innerHTML = '<div class="empty-state">Запуск слоя намерений еще не выбран.</div>';
    return;
  }
  const items = payload.items || [];
  const pagination =
    payload.pagination || { limit: state.intentMatchesLimit, offset: 0, total: 0 };
  const run = payload.run || {};
  if (!items.length) {
    target.innerHTML = `<div class="empty-state">В запуске ${escapeHtml(run.id || "")} намерений нет.</div>`;
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head compact-section-head">
      <h4>Сообщения из слоя ${escapeHtml(run.id || "")}</h4>
      <span class="muted">${escapeHtml(`${pagination.offset + 1}-${Math.min(pagination.offset + items.length, pagination.total)} из ${pagination.total}`)}</span>
    </div>
    <p class="muted">Здесь показаны только сообщения, которые прошли второй слой: широкий интерес плюс признаки намерения, контекст и порог score.</p>
    <div class="table-list">${items.map(renderInterestIntentMatchRow).join("")}</div>
    ${renderPageControls(pagination, "intent-matches")}
  </section>`;
}

function renderInterestIntentMatchRow(item) {
  const evidence = item.evidence_json || {};
  const scoreParts = evidence.score_parts || {};
  const includeLabels = humanIntentPatterns(evidence.include_hits || item.matched_text);
  const contextLabels = humanIntentPatterns(evidence.context_hits || []);
  const feedback = item.operator_feedback_json || null;
  const feedbackApplied = feedback?.application_status === "applied";
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.canonical_name || "элемент ядра")}</strong>
      <p class="muted">${escapeHtml([`сообщение #${item.telegram_message_id || "н/д"}`, time(item.message_date), item.sender_id].filter(Boolean).join(" / "))}</p>
      <p>${escapeHtml(shortText(item.message_text || "без текста", 520))}</p>
      <div class="badges">
        ${item.category ? badge(item.category) : ""}
        ${badge("слой намерений")}
        ${badge(`score ${formatScore(item.score)}`)}
        ${badge(`широкий ${formatScore(item.broad_score)}`)}
        ${includeLabels.length ? badge(`намерение: ${includeLabels.slice(0, 3).join(", ")}`) : ""}
        ${feedback ? badge(feedbackApplied ? "исключение применено" : "в исключениях", feedbackApplied ? "" : "is-warn") : ""}
      </div>
      <p class="draft-evidence"><strong>Почему найдено:</strong> ${escapeHtml([
        includeLabels.length ? `намерение: ${includeLabels.slice(0, 4).join(", ")}` : "",
        contextLabels.length ? `контекст: ${contextLabels.slice(0, 4).join(", ")}` : "",
        `широкий слой ${formatScore(scoreParts.broad || 0)}`,
        `намерение ${formatScore(scoreParts.intent || 0)}`,
        scoreParts.context ? `контекст ${formatScore(scoreParts.context)}` : "",
      ].filter(Boolean).join("; "))}</p>
      <p class="draft-evidence"><strong>Подготовленный текст:</strong> ${escapeHtml(preparedTextExplanation(evidence.prepared_text))}</p>
      ${renderIntentFeedbackState(feedback)}
      ${renderTelegramMessageLink(item)}
      <div class="row-actions">
        <md-outlined-button type="button" data-intent-feedback-action="preview" data-intent-match-id="${escapeHtml(item.id)}">
          Проверить исключение
        </md-outlined-button>
        <md-outlined-button type="button" data-intent-feedback-action="not-interesting" data-intent-match-id="${escapeHtml(item.id)}" ${feedback ? "disabled" : ""}>
          ${feedback ? "Уже в исключениях" : "Не интересно"}
        </md-outlined-button>
      </div>
      <div id="intent-feedback-${escapeHtml(item.id)}" class="draft-evidence" aria-live="polite"></div>
    </div>
  </div>`;
}

function renderIntentFeedbackState(feedback) {
  if (!feedback) return "";
  const status = feedback.application_status || "recorded";
  const applied = status === "applied";
  const actionText = applied
    ? "исключение уже применено к слою"
    : "feedback записан, исключение ждет явного применения";
  return `<p class="draft-evidence"><strong>Обратная связь:</strong> ${escapeHtml(actionText)}; статус ${escapeHtml(label(status))}; ${escapeHtml(time(feedback.created_at) || "")}</p>`;
}

function humanIntentPatterns(value) {
  const items = Array.isArray(value)
    ? value
    : String(value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
  return [...new Set(items.map(humanIntentPattern).filter(Boolean))];
}

function humanIntentPattern(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const normalized = text
    .replaceAll("\\b", "")
    .replaceAll("\\s+", " ")
    .replaceAll("[а-я]*", "")
    .replace(/[()]/g, "")
    .replace(/[?]/g, "")
    .replace(/\|/g, ", ")
    .replace(/\[.*?\]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const lower = normalized.toLowerCase();
  const known = [
    ["ищу", "поиск"],
    ["ищем", "поиск"],
    ["нужен", "нужно"],
    ["нужна", "нужно"],
    ["нужно", "нужно"],
    ["подскажите", "просит подсказать"],
    ["посоветуйте", "просит совет"],
    ["помогите", "просит помощь"],
    ["купить", "покупка"],
    ["заказать", "заказ"],
    ["поставить", "монтаж/установка"],
    ["установить", "монтаж/установка"],
    ["подключить", "подключение"],
    ["смонтировать", "монтаж"],
    ["стоимость", "цена/стоимость"],
    ["цена", "цена/стоимость"],
    ["сколько стоит", "цена/стоимость"],
    ["кто может", "поиск исполнителя"],
    ["видеонаблюдение", "видеонаблюдение"],
    ["камера", "камеры"],
    ["умный дом", "умный дом"],
    ["home assistant", "Home Assistant"],
    ["розетка", "электрика/автоматизация"],
    ["реле", "электрика/автоматизация"],
    ["щит", "щит/автоматы"],
    ["датчик", "датчики"],
    ["подсветк", "подсветка/освещение"],
    ["освещени", "освещение"],
    ["светильник", "освещение"],
    ["домофон", "домофон/доступ"],
    ["контроль доступа", "контроль доступа"],
    ["сигнализаци", "сигнализация"],
  ];
  const found = known.find(([needle]) => lower.includes(needle));
  return found ? found[1] : normalized;
}

function preparedTextExplanation(prepared) {
  if (!prepared || typeof prepared !== "object") return "использован raw message_text";
  const parts = [prepared.source || "unknown"];
  if (prepared.used_clean_text) parts.push("clean_text");
  if (prepared.used_lemmas) parts.push("lemmas");
  return parts.join(" / ");
}

function handleInterestIntentMatchesClick(event, state) {
  const feedbackButton = event.target.closest("[data-intent-feedback-action]");
  if (feedbackButton && state.selectedIntentRunId) {
    handleIntentMatchFeedback(feedbackButton, state);
    return;
  }
  const pageButton = event.target.closest("[data-intent-matches-page-action]");
  if (!pageButton || !state.selectedIntentRunId) return;
  const action = pageButton.dataset.intentMatchesPageAction;
  if (action === "prev") {
    state.intentMatchesOffset = Math.max(0, state.intentMatchesOffset - state.intentMatchesLimit);
  }
  if (action === "next") {
    state.intentMatchesOffset += state.intentMatchesLimit;
  }
  loadInterestIntentMatches(state, state.selectedIntentRunId);
}

async function handleIntentMatchFeedback(button, state) {
  const matchId = button.dataset.intentMatchId;
  const action = button.dataset.intentFeedbackAction;
  const panel = document.querySelector(`#intent-feedback-${CSS.escape(matchId)}`);
  if (!matchId || !panel) return;
  try {
    if (action === "not-interesting") {
      await api(`/api/feedback/intent_match/${encodeURIComponent(matchId)}`, {
        method: "POST",
        body: JSON.stringify({
          action: "not_lead",
          reason_code: "not_relevant_intent",
          feedback_scope: "classifier",
          learning_effect: "negative_example",
          application_status: "recorded",
          comment: "Оператор отметил сообщение слоя намерений как неинтересное",
          metadata_json: {
            context_id: state.selectedId,
            intent_run_id: state.selectedIntentRunId,
          },
        }),
      });
      markIntentMatchAsExcluded(button);
      panel.innerHTML = "Feedback записан. Ниже можно посмотреть безопасный preview exclusion до изменения слоя.";
      await previewIntentMatchExclusion(matchId, state, panel);
      return;
    }
    await previewIntentMatchExclusion(matchId, state, panel);
  } catch (error) {
    panel.textContent = error.message;
  }
}

function markIntentMatchAsExcluded(button) {
  button.setAttribute("disabled", "");
  button.textContent = "Уже в исключениях";
  const row = button.closest(".table-row");
  const badges = row?.querySelector(".badges");
  if (badges && !badges.querySelector("[data-intent-feedback-badge]")) {
    badges.insertAdjacentHTML(
      "beforeend",
      '<span class="badge is-warn" data-intent-feedback-badge>в исключениях</span>'
    );
  }
}

async function previewIntentMatchExclusion(matchId, state, panel) {
  panel.textContent = "Считаю влияние exclusion...";
  const payload = await api(
    `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-runs/${encodeURIComponent(state.selectedIntentRunId)}/matches/${encodeURIComponent(matchId)}/exclude-preview`
  );
  const suggestions = payload.suggestions || [];
  const samples = payload.removed_samples || [];
  const risk =
    payload.target_removed && payload.removed_count <= Math.max(3, Math.ceil((payload.total_matches || 0) * 0.05))
      ? "точечное исключение"
      : payload.target_removed
        ? "широкое исключение, проверьте примеры"
        : "кандидат не убирает выбранное сообщение";
  panel.innerHTML = `<strong>Impact preview:</strong> ${escapeHtml(payload.term || "нет предложения")}
    <br>Что изменить: добавить это выражение в исключающие условия слоя намерений.
    <br>Эффект: уберет ${escapeHtml(String(payload.removed_count || 0))} из ${escapeHtml(String(payload.total_matches || 0))}; выбранное сообщение ${payload.target_removed ? "исчезнет" : "останется"}; оценка: ${escapeHtml(risk)}.
    ${suggestions.length ? `<br>Другие кандидаты: ${escapeHtml(suggestions.join("; "))}` : ""}
    ${samples.length ? `<br>Что еще зацепит: ${samples.map((item) => item.message_url ? `<a href="${escapeHtml(item.message_url)}" target="_blank" rel="noreferrer">#${escapeHtml(String(item.telegram_message_id))}</a>` : `#${escapeHtml(String(item.telegram_message_id))}`).join(", ")}` : ""}
    <br><a href="${escapeHtml(interestContextStepHref("/interest-contexts/intent-exclusions", state.selectedId))}">Открыть страницу применения исключений</a>
    <br><span class="muted">Изменение сейчас не применяется автоматически: сначала проверяем влияние, потом переносим условие в слой.</span>`;
}

async function loadInterestIntentExclusions(state) {
  const target = document.querySelector("#interest-intent-exclusions");
  const status = document.querySelector("#interest-intent-status") || document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  target.innerHTML = '<div class="empty-state">Загружаю очередь исключений...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.intentExclusionsLimit),
      offset: String(state.intentExclusionsOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-exclusions?${params.toString()}`
    );
    renderInterestIntentExclusions(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function handleInterestIntentExclusionsClick(event, state) {
  const pageButton = event.target.closest("[data-intent-exclusions-page-action]");
  if (pageButton) {
    const action = pageButton.dataset.intentExclusionsPageAction;
    if (action === "prev") {
      state.intentExclusionsOffset = Math.max(
        0,
        state.intentExclusionsOffset - state.intentExclusionsLimit
      );
    }
    if (action === "next") {
      state.intentExclusionsOffset += state.intentExclusionsLimit;
    }
    loadInterestIntentExclusions(state);
    return;
  }
  const applyButton = event.target.closest("[data-apply-intent-exclusion]");
  if (applyButton) {
    applyInterestIntentExclusion(applyButton, state);
  }
}

function renderInterestIntentExclusions(payload, state) {
  const target = document.querySelector("#interest-intent-exclusions");
  if (!target) return;
  const items = payload.items || [];
  const pagination =
    payload.pagination || { limit: state.intentExclusionsLimit, offset: 0, total: 0 };
  const summary = payload.summary || {};
  target.innerHTML = `<section class="draft-review-section">
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
        ${renderOpsMetric("Feedback", summary.total || 0, "не интересно")}
        ${renderOpsMetric("На применении", summary.pending || 0, "ожидает решения")}
        ${renderOpsMetric("Применено", summary.applied || 0, "в слой")}
      </div>
    </div>
    ${items.length ? `<div class="table-list">${items.map(renderInterestIntentExclusionRow).join("")}</div>` : '<div class="empty-state">Feedback “Не интересно” пока нет. Откройте сообщения намерений и отметьте нерелевантные.</div>'}
    ${renderPageControls(pagination, "intent-exclusions")}
  </section>`;
}

function renderInterestIntentExclusionRow(item) {
  const feedback = item.feedback || {};
  const match = item.match || {};
  const preview = item.preview || {};
  const suggestions = item.suggestions || [];
  const applied = feedback.application_status === "applied";
  const risk =
    preview.target_removed && preview.removed_count <= Math.max(3, Math.ceil((preview.total_matches || 0) * 0.05))
      ? "точечно"
      : preview.target_removed
        ? "широко"
        : "не убирает цель";
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(match.canonical_name || "сообщение слоя намерений")}</strong>
      <p class="muted">${escapeHtml([`feedback ${shortId(feedback.id)}`, `run ${shortId(item.run_id)}`, `layer ${shortId(item.intent_layer_id)}`, time(feedback.created_at)].filter(Boolean).join(" / "))}</p>
      <p>${escapeHtml(shortText(match.message_text || "", 520))}</p>
      <div class="badges">
        ${badge(label(feedback.application_status || "recorded"), applied ? "" : "is-warn")}
        ${badge(`score ${formatScore(match.score)}`)}
        ${badge(`эффект ${risk}`)}
        ${badge(`уберет ${preview.removed_count || 0}/${preview.total_matches || 0}`)}
        ${preview.target_removed ? badge("цель исчезнет") : badge("цель останется", "is-danger")}
      </div>
      ${renderTelegramMessageLink(match)}
      <label class="material-select-line">Исключающее условие
        <input data-intent-exclusion-term="${escapeHtml(feedback.id)}" list="intent-exclusion-options-${escapeHtml(feedback.id)}" value="${escapeHtml(item.selected_term || "")}" ${applied ? "disabled" : ""}>
        <datalist id="intent-exclusion-options-${escapeHtml(feedback.id)}">
          ${suggestions.map((term) => `<option value="${escapeHtml(term)}"></option>`).join("")}
        </datalist>
      </label>
      <p class="draft-evidence"><strong>Что произойдет:</strong> ${escapeHtml(preview.explanation || "preview недоступен")}</p>
      ${preview.removed_samples?.length ? `<p class="draft-evidence"><strong>Что еще зацепит:</strong> ${preview.removed_samples.map((sample) => sample.message_url ? `<a href="${escapeHtml(sample.message_url)}" target="_blank" rel="noreferrer">#${escapeHtml(String(sample.telegram_message_id))}</a>` : `#${escapeHtml(String(sample.telegram_message_id))}`).join(", ")}</p>` : ""}
    </div>
    <div class="row-actions">
      <md-filled-tonal-button type="button" data-apply-intent-exclusion="${escapeHtml(feedback.id)}" ${applied ? "disabled" : ""}>
        Применить исключение
      </md-filled-tonal-button>
    </div>
  </div>`;
}

async function applyInterestIntentExclusion(button, state) {
  const feedbackId = button.dataset.applyIntentExclusion;
  const status = document.querySelector("#interest-context-status");
  const input = document.querySelector(`[data-intent-exclusion-term="${CSS.escape(feedbackId)}"]`);
  const term = String(input?.value || "").trim();
  if (!feedbackId || !term || !state.selectedId) return;
  button.disabled = true;
  try {
    await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/intent-exclusions/${encodeURIComponent(feedbackId)}/apply`,
      {
        method: "POST",
        body: JSON.stringify({ term }),
      }
    );
    if (status) status.textContent = "Исключение применено к слою. Перезапустите слой намерений для нового результата.";
    await loadInterestIntentExclusions(state);
  } catch (error) {
    button.disabled = false;
    if (status) status.textContent = error.message;
  }
}

async function saveManualInterestCoreBrief(event, state) {
  event.preventDefault();
  const status = document.querySelector("#interest-context-status");
  const form = event.currentTarget;
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/briefs/manual`,
      {
        method: "POST",
        body: JSON.stringify({
          brief_text: formValue(form, "brief_text"),
          activate: true,
        }),
      }
    );
    renderInterestCoreBriefs(payload.briefs);
    if (status) status.textContent = "Бриф ядра интересов сохранен";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function generateInterestCoreBrief(state) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/briefs/generate`,
      {
        method: "POST",
        body: JSON.stringify({
          activate: true,
          agent_key: "catalog_extractor",
          route_role: "primary",
        }),
      }
    );
    renderInterestCoreBriefGeneration(payload.progress, payload.job, payload.briefs);
    if (status) status.textContent = "LLM-бриф поставлен в очередь";
    scheduleInterestCoreBriefPolling(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadInterestCoreBriefStatus(state, { silent = false } = {}) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) return;
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/briefs/generate/status`
    );
    renderInterestCoreBriefGeneration(payload.progress, payload.job, payload.briefs);
    if (isActiveBriefStatus(payload.progress?.status)) {
      scheduleInterestCoreBriefPolling(state);
    } else {
      stopInterestCoreBriefPolling(state);
    }
  } catch (error) {
    if (!silent && status) status.textContent = error.message;
  }
}

async function loadInterestLlmConfig() {
  const target = document.querySelector("#interest-llm-provider-list");
  if (!target) return;
  try {
    const registry = await api("/api/admin/ai-registry");
    populateInterestLlmModelOptions(registry.models || []);
    renderInterestLlmConfig(registry);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function populateInterestLlmModelOptions(models) {
  const datalist = document.querySelector("#interest-llm-model-options");
  if (!datalist) return;
  const languageModels = (models || [])
    .filter((model) => model.model_type === "language")
    .map((model) => model.provider_model_name)
    .filter(Boolean);
  const fallback = [
    "GLM-4-Plus",
    "GLM-5.1",
    "GLM-5",
    "GLM-4.7",
    "GLM-4.5-Air",
    "GLM-4.5-Flash",
  ];
  const values = [...new Set((languageModels.length ? languageModels : fallback).sort())];
  datalist.innerHTML = values
    .map((model) => `<option value="${escapeHtml(model)}"></option>`)
    .join("");
}

function renderInterestLlmConfig(registry) {
  const target = document.querySelector("#interest-llm-provider-list");
  if (!target) return;
  const providerById = Object.fromEntries(
    (registry.providers || []).map((provider) => [provider.id, provider])
  );
  const accounts = (registry.accounts || [])
    .filter((account) => account.enabled !== false)
    .map((account) => ({
      ...account,
      provider_key: providerById[account.ai_provider_id]?.provider_key || "provider",
    }));
  const routes = (registry.routes || []).filter(
    (route) => route.enabled !== false && route.agent_key === "catalog_extractor"
  );
  if (!accounts.length && !routes.length) {
    target.innerHTML = '<div class="empty-state">LLM еще не подключен</div>';
    return;
  }
  target.innerHTML = `
    <div class="table-list">
      ${accounts.map(renderInterestLlmAccountRow).join("")}
      ${routes.map(renderInterestLlmRouteRow).join("")}
    </div>`;
}

function renderInterestLlmAccountRow(account) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(account.display_name || account.provider_account || "LLM provider")}</strong>
      <p class="muted">${escapeHtml(account.provider_key || "provider")} / ${escapeHtml(account.base_url || "")}</p>
    </div>
    <span>${badge(account.enabled === false ? "отключен" : "подключен", account.enabled === false ? "is-warn" : "")}</span>
  </div>`;
}

function renderInterestLlmRouteRow(route) {
  return `<div class="table-row">
    <div>
      <strong>${escapeHtml(route.agent_key)} / ${escapeHtml(route.route_role)}</strong>
      <p class="muted">${escapeHtml(route.provider_account || "аккаунт")} / ${escapeHtml(route.model || "модель")} / ${escapeHtml(route.model_profile || "профиль")}</p>
    </div>
    <span>${badge(`приоритет ${route.priority ?? "н/д"}`)}</span>
  </div>`;
}

async function saveInterestLlmProvider(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#interest-llm-status");
  const apiKey = String(formValue(form, "api_key") || "").trim();
  const modelName = String(formValue(form, "model") || "").trim();
  const displayName = formValue(form, "display_name") || "Z.AI";
  const baseUrl = formValue(form, "base_url") || "https://api.z.ai/api/coding/paas/v4";
  try {
    if (status) status.textContent = apiKey ? "Сохраняю LLM-провайдера..." : "Обновляю модель...";
    let registry;
    let accountId = null;
    if (apiKey) {
      registry = await api("/api/onboarding/llm-provider", {
        method: "POST",
        body: JSON.stringify({
          display_name: displayName,
          base_url: baseUrl,
          api_key: apiKey,
        }),
      });
      accountId = registry.account?.id || firstEnabledZaiAccountId(registry);
    } else {
      registry = await api("/api/admin/ai-registry");
      accountId = firstEnabledZaiAccountId(registry);
      if (!accountId) {
        throw new Error("Введите token для первого подключения LLM-провайдера.");
      }
    }
    const model = findInterestLlmModel(registry.models || [], modelName);
    if (!model) {
      throw new Error(`Провайдер сохранен, но модель "${modelName}" не найдена в Z.AI registry.`);
    }
    if (!accountId) {
      throw new Error("LLM-провайдер сохранен, но активный аккаунт Z.AI не найден.");
    }
    if (status) status.textContent = `Привязываю модель ${model.provider_model_name}...`;
    await api("/api/admin/ai-agents/catalog_extractor/routes", {
      method: "POST",
      body: JSON.stringify({
        model_id: model.id,
        account_id: accountId,
        route_role: "primary",
        priority: 5,
        enabled: true,
        max_output_tokens: 4096,
        temperature: 0.0,
        thinking_mode: "off",
        structured_output_required: Boolean(
          model.supports_structured_output || model.supports_json_mode
        ),
      }),
    });
    const apiKeyField = form.querySelector('[name="api_key"]');
    if (apiKeyField && "value" in apiKeyField) apiKeyField.value = "";
    if (status) {
      status.textContent = `LLM подключен: ${model.provider_model_name} для catalog_extractor / primary`;
    }
    await loadInterestLlmConfig();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function firstEnabledZaiAccountId(registry) {
  const providerById = Object.fromEntries(
    (registry.providers || []).map((provider) => [provider.id, provider])
  );
  const account = (registry.accounts || []).find(
    (item) =>
      item.enabled !== false && providerById[item.ai_provider_id]?.provider_key === "zai"
  );
  return account?.id || null;
}

function findInterestLlmModel(models, modelName) {
  const normalized = normalizeInterestLlmModelName(modelName);
  return (models || []).find((model) => {
    if (model.model_type !== "language") return false;
    return normalizeInterestLlmModelName(model.provider_model_name) === normalized;
  });
}

function normalizeInterestLlmModelName(value) {
  return String(value || "").trim().toLowerCase();
}

function scheduleInterestCoreBriefPolling(state) {
  if (state.briefPollTimer) return;
  state.briefPollTimer = window.setInterval(() => {
    loadInterestCoreBriefStatus(state, { silent: true });
  }, 2000);
}

function stopInterestCoreBriefPolling(state) {
  if (!state.briefPollTimer) return;
  window.clearInterval(state.briefPollTimer);
  state.briefPollTimer = null;
}

function isActiveBriefStatus(status) {
  return ["queued", "running"].includes(String(status || ""));
}

function renderInterestCoreBriefGeneration(progress, job, briefs) {
  renderInterestCoreBriefs(briefs);
  const target = document.querySelector("#interest-core-brief-progress");
  if (!target) return;
  const status = String(progress?.status || "not_started");
  if (status === "not_started") {
    target.innerHTML = "";
    return;
  }
  const overall = normalizePercent(progress?.overall_percent);
  const stage = normalizePercent(progress?.stage_percent);
  const message = progress?.message || status;
  target.innerHTML = `<section class="prepare-progress-surface ${isActiveBriefStatus(status) ? "is-active" : ""}">
    <div class="section-head">
      <div>
        <h3>Формирование LLM-брифа</h3>
        <p class="muted">${escapeHtml(message)}</p>
      </div>
      <div class="badges">
        ${badge(label(status), status === "failed" ? "is-danger" : "")}
        ${progress?.model ? badge(progress.model) : ""}
        ${job?.id ? badge(`job ${job.id}`) : ""}
      </div>
    </div>
    <div class="prepare-progress-bars">
      ${renderProgressLine("Общий прогресс", overall, progress?.version ? `версия ${progress.version}` : "задача")}
      ${renderProgressLine(progress?.current_stage_label || "LLM-бриф", stage, progress?.model_profile || "модель")}
    </div>
  </section>`;
}

function renderInterestCoreBriefs(briefs) {
  const textField = document.querySelector("#interest-core-brief-text");
  const list = document.querySelector("#interest-core-brief-list");
  const active = briefs?.active || null;
  const items = briefs?.items || [];
  if (textField) {
    textField.value = active?.brief_text || "";
  }
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<div class="empty-state">Бриф еще не задан. Введите его вручную или сформируйте из источников.</div>';
    return;
  }
  list.innerHTML = `<div class="table-list">${items
    .map((item) => {
      const isActive = item.status === "active";
      const sourceLabel = item.source === "llm_generated" ? "LLM" : "ручной";
      return `<div class="table-row brief-row">
        <div>
          <strong>Версия ${escapeHtml(String(item.version || ""))}: ${escapeHtml(item.title || "бриф")}</strong>
          <p class="muted">${escapeHtml(shortText(item.brief_text || "", 260))}</p>
          <div class="badges">
            ${badge(label(item.status || "draft"), isActive ? "" : "is-warn")}
            ${badge(sourceLabel)}
            ${item.model ? badge(item.model) : ""}
            ${item.model_profile ? badge(item.model_profile) : ""}
          </div>
        </div>
        <div class="resource-actions">
          ${
            isActive
              ? ""
              : `<md-outlined-button type="button" data-activate-brief="${escapeHtml(item.id)}">Сделать активным</md-outlined-button>`
          }
        </div>
      </div>`;
    })
    .join("")}</div>`;
  list.querySelectorAll("[data-activate-brief]").forEach((button) => {
    button.addEventListener("click", () => activateInterestCoreBrief(button.dataset.activateBrief));
  });
}

async function activateInterestCoreBrief(briefId) {
  const contextId = document.body.dataset.interestContextId;
  const status = document.querySelector("#interest-context-status");
  if (!contextId || !briefId) return;
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(contextId)}/briefs/${encodeURIComponent(briefId)}/activate`,
      { method: "POST" }
    );
    renderInterestCoreBriefs(payload.briefs);
    if (status) status.textContent = "Активная версия брифа обновлена";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function buildInterestContextDraft(state) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  try {
    const maxItemsField = document.querySelector("#interest-context-draft-max-items");
    const maxItemsValue = Number.parseInt(maxItemsField?.value || "1000", 10);
    const maxItems = Number.isFinite(maxItemsValue)
      ? Math.max(10, Math.min(10000, maxItemsValue))
      : 1000;
    const payload = await api(`/api/interest-contexts/${encodeURIComponent(state.selectedId)}/draft`, {
      method: "POST",
      body: JSON.stringify({ max_items: maxItems }),
    });
    renderInterestContextDraft(payload.progress, payload.job, payload.draft);
    if (status) status.textContent = "Сборка ядра интересов поставлена в очередь";
    scheduleInterestContextDraftPolling(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadInterestContextDraftStatus(state, { silent = false } = {}) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) return;
  try {
    const target =
      document.querySelector("#interest-context-draft-review") ||
      document.querySelector("#interest-context-draft-screen");
    const itemLimit = target?.dataset.summaryOnly === "true" ? 0 : 1000;
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/draft/status?item_limit=${itemLimit}`
    );
    renderInterestContextDraft(payload.progress, payload.job, payload.draft);
    if (isActiveDraftStatus(payload.progress?.status)) {
      scheduleInterestContextDraftPolling(state);
    } else {
      stopInterestContextDraftPolling(state);
    }
  } catch (error) {
    if (!silent && status) status.textContent = error.message;
  }
}

function scheduleInterestContextDraftPolling(state) {
  if (state.draftPollTimer) return;
  state.draftPollTimer = window.setInterval(() => {
    loadInterestContextDraftStatus(state, { silent: true });
  }, 2000);
}

function stopInterestContextDraftPolling(state) {
  if (!state.draftPollTimer) return;
  window.clearInterval(state.draftPollTimer);
  state.draftPollTimer = null;
}

function isActiveDraftStatus(status) {
  return ["queued", "running"].includes(String(status || ""));
}

async function loadInterestContextDraftItemsPage(state) {
  const target = document.querySelector("#interest-context-draft-items-page");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  try {
    const params = new URLSearchParams({
      limit: String(state.draftItemsLimit),
      offset: String(state.draftItemsOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/draft/items?${params.toString()}`
    );
    renderInterestContextDraftItemsPage(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function changeInterestContextDraftItemsPage(event, state) {
  const button = event.target.closest("[data-draft-page-action]");
  if (!button) return;
  const action = button.dataset.draftPageAction;
  if (action === "prev") {
    state.draftItemsOffset = Math.max(0, state.draftItemsOffset - state.draftItemsLimit);
  }
  if (action === "next") {
    state.draftItemsOffset += state.draftItemsLimit;
  }
  loadInterestContextDraftItemsPage(state);
}

function renderInterestContextDraftItemsPage(payload, state) {
  const target = document.querySelector("#interest-context-draft-items-page");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.draftItemsLimit, offset: 0, total: 0 };
  const draftRun = payload.draft_run || null;
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head">
      <div>
        <h3>Кандидаты для ревью</h3>
        <p class="muted">${escapeHtml(draftRun ? `Черновик ${label(draftRun.status || "draft")}` : "Черновик еще не сформирован")}</p>
      </div>
      <div class="badges">
        ${badge(`${pagination.total || 0} всего`)}
        ${draftRun?.algorithm_version ? badge(draftRun.algorithm_version) : ""}
      </div>
    </div>
    ${renderDraftItems(items, pagination)}
    ${renderPageControls(pagination, "draft")}
  </section>`;
}

async function enhanceInterestContextDraftWithLlm(state) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/draft/enhance-llm`,
      {
        method: "POST",
        body: JSON.stringify({
          max_items: 1000,
          candidate_chunk_size: 10,
          agent_key: "catalog_extractor",
          route_role: "primary",
        }),
      }
    );
    renderInterestContextCandidateEnhancement(
      payload.progress,
      payload.job,
      payload.enhancement,
      payload.reviews
    );
    if (status) status.textContent = "LLM-улучшение кандидатов поставлено в очередь";
    scheduleInterestContextEnhancementPolling(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadInterestContextEnhancementStatus(state, { silent = false } = {}) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) return;
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/draft/enhance-llm/status`
    );
    renderInterestContextCandidateEnhancement(
      payload.progress,
      payload.job,
      payload.enhancement,
      payload.reviews
    );
    if (isActiveCandidateEnhancementStatus(payload.progress?.status)) {
      scheduleInterestContextEnhancementPolling(state);
      if (currentInterestStep() === "reviews") {
        await loadInterestContextReviewItemsPage(state);
      }
    } else {
      stopInterestContextEnhancementPolling(state);
      if (currentInterestStep() === "reviews") {
        await loadInterestContextReviewItemsPage(state);
      }
    }
  } catch (error) {
    if (!silent && status) status.textContent = error.message;
  }
}

function scheduleInterestContextEnhancementPolling(state) {
  if (state.enhancePollTimer) return;
  state.enhancePollTimer = window.setInterval(() => {
    loadInterestContextEnhancementStatus(state, { silent: true });
  }, 2000);
}

function stopInterestContextEnhancementPolling(state) {
  if (!state.enhancePollTimer) return;
  window.clearInterval(state.enhancePollTimer);
  state.enhancePollTimer = null;
}

function isActiveCandidateEnhancementStatus(status) {
  return ["queued", "running"].includes(String(status || ""));
}

async function loadInterestContextRawReview(state) {
  const target = document.querySelector("#interest-context-raw-review");
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  if (target) target.innerHTML = '<div class="empty-state">Загружаю проверку данных...</div>';
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/raw-review`
    );
    renderInterestContextRawReview(payload);
    if (status) status.textContent = "Проверка данных обновлена";
  } catch (error) {
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

async function startInterestContextDataPreparation(state) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) {
    if (status) status.textContent = "Сначала выберите контекст";
    return;
  }
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data`,
      {
        method: "POST",
        body: JSON.stringify({ embedding_profile: "local_hashing_v1" }),
      }
    );
    renderInterestContextPrepareProgress(payload.progress, payload.job);
    if (status) status.textContent = "Подготовка данных поставлена в очередь";
    scheduleInterestContextPreparePolling(state);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadInterestContextPrepareStatus(state, { silent = false } = {}) {
  const status = document.querySelector("#interest-context-status");
  if (!state.selectedId) return;
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/status`
    );
    renderInterestContextPrepareProgress(payload.progress, payload.job);
    if (isActivePrepareStatus(payload.progress?.status)) {
      scheduleInterestContextPreparePolling(state);
    } else {
      stopInterestContextPreparePolling(state);
    }
  } catch (error) {
    if (!silent && status) status.textContent = error.message;
  }
}

function scheduleInterestContextPreparePolling(state) {
  if (state.preparePollTimer) return;
  state.preparePollTimer = window.setInterval(() => {
    loadInterestContextPrepareStatus(state, { silent: true });
  }, 2000);
}

function stopInterestContextPreparePolling(state) {
  if (!state.preparePollTimer) return;
  window.clearInterval(state.preparePollTimer);
  state.preparePollTimer = null;
}

function isActivePrepareStatus(status) {
  return ["queued", "running"].includes(String(status || ""));
}

function renderInterestContextPrepareProgress(progress, job) {
  const target = document.querySelector("#interest-context-prepare-progress");
  if (!target) return;
  const status = String(progress?.status || "not_started");
  if (status === "not_started") {
    target.innerHTML = "";
    return;
  }
  const overall = normalizePercent(progress?.overall_percent);
  const stage = normalizePercent(progress?.stage_percent);
  const stageLabel = progress?.current_stage_label || "Подготовка данных";
  const message = progress?.message || status;
  const stageResults = progress?.stage_results || [];
  target.innerHTML = `<section class="prepare-progress-surface ${isActivePrepareStatus(status) ? "is-active" : ""}">
    <div class="section-head">
      <div>
        <h3>Подготовка данных</h3>
        <p class="muted">${escapeHtml(message)}</p>
      </div>
      <div class="badges">
        ${badge(label(status), status === "failed" ? "is-danger" : "")}
        ${job?.id ? badge(`job ${job.id}`) : ""}
      </div>
    </div>
    <div class="prepare-progress-bars">
      ${renderProgressLine("Общий прогресс", overall, `${progress?.completed_steps || 0}/${progress?.total_steps || 0} шагов`)}
      ${renderProgressLine(stageLabel, stage, progress?.run_count ? `запуск ${progress?.run_index || 0}/${progress.run_count}` : "этап")}
    </div>
    <div class="prepare-progress-meta">
      ${renderOpsMetric("Raw-запуски", progress?.raw_export_run_count || 0, "в контексте")}
      ${renderOpsMetric("Этап", progress?.stage_index || 0, `из ${progress?.stage_count || 0}`)}
      ${renderOpsMetric("Embedding", "local", "local_hashing_v1")}
    </div>
    ${renderPrepareStageResults(stageResults)}
  </section>`;
}

function renderInterestContextDraft(progress, job, draft) {
  const target =
    document.querySelector("#interest-context-draft-review") ||
    document.querySelector("#interest-context-draft-screen");
  if (!target) return;
  const status = String(progress?.status || "not_started");
  const draftItems = draft?.items || [];
  const draftRun = draft?.draft_run || null;
  if (status === "not_started" && !draftRun) {
    target.innerHTML = "";
    return;
  }
  const overall = normalizePercent(progress?.overall_percent);
  const stage = normalizePercent(progress?.stage_percent);
  const stageLabel = progress?.current_stage_label || "Сборка ядра интересов";
  const message = progress?.message || status;
  const stageResults = progress?.stage_results || [];
  if (target.dataset.summaryOnly === "true") {
    const contextId = document.body.dataset.interestContextId || "";
    target.innerHTML = `<section class="draft-review-section">
      <div class="section-head">
        <div>
          <h3>Статус ядра интересов</h3>
          <p class="muted">${escapeHtml(message)}</p>
        </div>
        <div class="badges">
          ${badge(label(status), status === "failed" ? "is-danger" : "")}
          ${badge("без LLM")}
          ${job?.id ? badge(`job ${job.id}`) : ""}
        </div>
      </div>
      <div class="prepare-progress-meta">
        ${renderOpsMetric("Кандидаты", progress?.candidate_count || 0, "в отдельной странице")}
        ${renderOpsMetric("Raw-запуски", progress?.raw_export_run_count || 0, "в контексте")}
        ${renderOpsMetric("Алгоритм", "rules", "NLP/POS/score")}
      </div>
      <div class="button-row">
        <a class="button-link" href="${escapeHtml(interestContextStepHref("/interest-contexts/core/candidates", contextId))}">Открыть кандидатов</a>
      </div>
    </section>`;
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head">
      <div>
        <h3>Черновик ядра интересов</h3>
        <p class="muted">${escapeHtml(message)}</p>
      </div>
      <div class="badges">
        ${badge(label(status), status === "failed" ? "is-danger" : "")}
        ${badge("без LLM")}
        ${job?.id ? badge(`job ${job.id}`) : ""}
      </div>
    </div>
    ${
      status !== "not_started"
        ? `<div class="prepare-progress-bars">
            ${renderProgressLine("Общий прогресс", overall, `${progress?.completed_steps || 0}/${progress?.total_steps || 0} шагов`)}
            ${renderProgressLine(stageLabel, stage, progress?.run_count ? `запуск ${progress?.run_index || 0}/${progress.run_count}` : "этап")}
          </div>`
        : ""
    }
    <div class="prepare-progress-meta">
      ${renderOpsMetric("Кандидаты", progress?.candidate_count || draftItems.length || 0, "ожидают ревью")}
      ${renderOpsMetric("Raw-запуски", progress?.raw_export_run_count || 0, "в контексте")}
      ${renderOpsMetric("Алгоритм", "rules", "NLP/POS/score")}
    </div>
    ${renderDraftStageResults(stageResults)}
    ${renderDraftItems(draftItems)}
  </section>`;
}

async function updateInterestCoreCandidateReviewStatus(event, state) {
  const button = event.target.closest("[data-review-id][data-review-status]");
  if (!button || !state.selectedId) return;
  const status = document.querySelector("#interest-context-status");
  try {
    await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/candidate-reviews/${encodeURIComponent(button.dataset.reviewId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          status: button.dataset.reviewStatus,
          note: button.dataset.reviewNote || null,
        }),
      }
    );
    if (currentInterestStep() === "reviews") {
      await loadInterestContextReviewItemsPage(state);
    } else {
      await loadInterestContextEnhancementStatus(state, { silent: true });
    }
    if (status) status.textContent = "Статус рекомендации обновлен";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function approveAllInterestCoreCandidateReviews(event, state) {
  const button = event.target.closest("[data-approve-all-reviews]");
  if (!button || !state.selectedId || button.disabled) return;
  const status = document.querySelector("#interest-context-status");
  button.disabled = true;
  if (status) status.textContent = "Принимаю все рекомендации...";
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/candidate-reviews/approve-all`,
      { method: "POST" }
    );
    if (currentInterestStep() === "reviews") {
      state.reviewItemsOffset = 0;
      await loadInterestContextReviewItemsPage(state);
    } else {
      renderInterestContextCandidateEnhancement(null, null, null, payload.reviews);
    }
    if (currentInterestStep() === "items") {
      await loadInterestContextCoreItemsPage(state);
    }
    if (status) {
      status.textContent = `Принято: ${payload.result?.approved || 0}, в рабочее ядро: ${payload.result?.applied || 0}`;
    }
  } catch (error) {
    button.disabled = false;
    if (status) status.textContent = error.message;
  }
}

async function loadInterestContextReviewItemsPage(state) {
  const target = document.querySelector("#interest-context-review-items-page");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  try {
    const params = new URLSearchParams({
      limit: String(state.reviewItemsLimit),
      offset: String(state.reviewItemsOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/candidate-reviews?${params.toString()}`
    );
    renderInterestContextReviewItemsPage(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function changeInterestContextReviewItemsPage(event, state) {
  const button = event.target.closest("[data-review-page-action]");
  if (!button) return;
  const action = button.dataset.reviewPageAction;
  if (action === "prev") {
    state.reviewItemsOffset = Math.max(0, state.reviewItemsOffset - state.reviewItemsLimit);
  }
  if (action === "next") {
    state.reviewItemsOffset += state.reviewItemsLimit;
  }
  loadInterestContextReviewItemsPage(state);
}

function renderInterestContextReviewItemsPage(payload, state) {
  const target = document.querySelector("#interest-context-review-items-page");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.reviewItemsLimit, offset: 0, total: 0 };
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head">
      <div>
        <h3>Рекомендации на ревью</h3>
        <p class="muted">Показаны только записи текущей страницы.</p>
      </div>
      <div class="badges">
        ${badge(`${pagination.total || 0} всего`)}
        ${payload.latest_job?.id ? badge(`job ${payload.latest_job.id}`) : ""}
      </div>
    </div>
    ${renderCandidateReviewSummary(payload)}
    ${renderApproveAllCandidateReviewsAction(payload)}
    ${items.length ? renderCandidateReviewSection(items, pagination) : '<div class="empty-state">LLM-рекомендаций пока нет</div>'}
    ${renderPageControls(pagination, "review")}
  </section>`;
}

function renderApproveAllCandidateReviewsAction(payload) {
  const pendingCount = Number(payload?.summary?.by_status?.pending_review || 0);
  if (!pendingCount) return "";
  const jobStatus = String(payload?.latest_job?.status || "");
  const isActive = isActiveCandidateEnhancementStatus(jobStatus);
  const disabled = isActive ? "disabled" : "";
  const hint = isActive
    ? "Дождитесь завершения LLM-прогона. Новые рекомендации еще добавляются."
    : `Будут приняты все ожидающие рекомендации: ${pendingCount}.`;
  return `<div class="button-row review-bulk-actions">
    <button type="button" data-approve-all-reviews ${disabled}>Принять все рекомендации</button>
    <span class="muted">${escapeHtml(hint)}</span>
  </div>`;
}

async function loadInterestContextCoreItemsPage(state) {
  const target = document.querySelector("#interest-context-core-items-page");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  try {
    const params = new URLSearchParams({
      limit: String(state.coreItemsLimit),
      offset: String(state.coreItemsOffset),
    });
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/core-items?${params.toString()}`
    );
    renderInterestContextCoreItemsPage(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function changeInterestContextCoreItemsPage(event, state) {
  const button = event.target.closest("[data-core-page-action]");
  if (!button) return;
  const action = button.dataset.corePageAction;
  if (action === "prev") {
    state.coreItemsOffset = Math.max(0, state.coreItemsOffset - state.coreItemsLimit);
  }
  if (action === "next") {
    state.coreItemsOffset += state.coreItemsLimit;
  }
  loadInterestContextCoreItemsPage(state);
}

function renderInterestContextCoreItemsPage(payload, state) {
  const target = document.querySelector("#interest-context-core-items-page");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.coreItemsLimit, offset: 0, total: 0 };
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head">
      <div>
        <h3>Утвержденные элементы</h3>
        <p class="muted">Это результат ручного approve. Следующий шаг - использовать эти элементы в поиске интересов и лидов.</p>
      </div>
      <div class="badges">${badge(`${pagination.total || 0} всего`)}</div>
    </div>
    ${items.length ? renderCoreItems(items, pagination) : '<div class="empty-state">Рабочее ядро пока пустое. Одобрите LLM-рекомендации.</div>'}
    ${renderPageControls(pagination, "core")}
  </section>`;
}

function renderInterestContextCandidateEnhancement(progress, job, enhancement, reviews) {
  const target = document.querySelector("#interest-context-llm-enhance-review");
  if (!target) return;
  const status = String(progress?.status || job?.status || "not_started");
  const reviewItems = reviews?.items || [];
  if (status === "not_started" && !enhancement && !reviewItems.length) {
    target.innerHTML = "";
    return;
  }
  const result = enhancement?.result || {};
  const overall = normalizePercent(progress?.overall_percent);
  const stage = normalizePercent(progress?.stage_percent);
  const message = progress?.message || status;
  if (target.dataset.summaryOnly === "true") {
    const contextId = document.body.dataset.interestContextId || "";
    target.innerHTML = `<section class="draft-review-section">
      <div class="section-head">
        <div>
          <h3>Статус LLM-рекомендаций</h3>
          <p class="muted">${escapeHtml(message)}</p>
        </div>
        <div class="badges">
          ${badge(label(status), status === "failed" ? "is-danger" : "")}
          ${progress?.model ? badge(progress.model) : ""}
          ${progress?.active_parallelism ? badge(`${progress.active_parallelism} потоков`) : ""}
          ${job?.id ? badge(`job ${job.id}`) : ""}
        </div>
      </div>
      <div class="prepare-progress-meta">
        ${renderOpsMetric("Улучшено", progress?.improved_count || 0, "из rule-based")}
        ${renderOpsMetric("Добавлено", progress?.new_count || 0, "из брифа/evidence")}
        ${renderOpsMetric("Отклонено", progress?.rejected_count || 0, "как шум")}
        ${progress?.failed_chunk_count ? renderOpsMetric("Ошибки", progress.failed_chunk_count, "фрагменты JSON") : ""}
      </div>
      ${renderCandidateReviewSummary(reviews)}
      <div class="button-row">
        <a class="button-link" href="${escapeHtml(interestContextStepHref("/interest-contexts/core/reviews", contextId))}">Открыть LLM-рекомендации</a>
      </div>
    </section>`;
    return;
  }
  target.innerHTML = `<section class="draft-review-section">
    <div class="section-head">
      <div>
        <h3>LLM-рекомендации по ядру</h3>
        <p class="muted">${escapeHtml(message)}</p>
      </div>
      <div class="badges">
        ${badge(label(status), status === "failed" ? "is-danger" : "")}
        ${progress?.model ? badge(progress.model) : ""}
        ${progress?.model_profile ? badge(progress.model_profile) : ""}
        ${progress?.active_parallelism ? badge(`${progress.active_parallelism} потоков`) : ""}
        ${job?.id ? badge(`job ${job.id}`) : ""}
      </div>
    </div>
    ${
      status !== "not_started"
        ? `<div class="prepare-progress-bars">
            ${renderProgressLine("Общий прогресс", overall, `${progress?.candidate_count || 0} кандидатов`)}
            ${renderProgressLine(progress?.current_stage_label || "LLM-улучшение", stage, enhancementProgressHint(progress))}
          </div>`
        : ""
    }
    <div class="prepare-progress-meta">
      ${renderOpsMetric("Улучшено", progress?.improved_count || 0, "из rule-based")}
      ${renderOpsMetric("Добавлено", progress?.new_count || 0, "из брифа/evidence")}
      ${renderOpsMetric("Отклонено", progress?.rejected_count || 0, "как шум")}
      ${progress?.failed_chunk_count ? renderOpsMetric("Ошибки", progress.failed_chunk_count, "фрагменты JSON") : ""}
    </div>
    ${renderCandidateReviewSummary(reviews)}
    ${renderCandidateReviewSection(reviewItems)}
    ${
      reviewItems.length
        ? ""
        : `${result?.summary ? `<p class="muted">${escapeHtml(result.summary)}</p>` : ""}
           ${renderEnhancedCandidateSection("Улучшенные кандидаты", result.improved_candidates || [], renderImprovedCandidateRow)}
           ${renderEnhancedCandidateSection("Новые кандидаты от LLM", result.new_candidates || [], renderNewCandidateRow)}
           ${renderEnhancedCandidateSection("Кандидаты на отклонение", result.rejected_candidates || [], renderRejectedCandidateRow)}`
    }
  </section>`;
}

function renderCandidateReviewSummary(reviews) {
  const summary = reviews?.summary;
  if (!summary || !summary.total) return "";
  return `<div class="prepare-progress-meta">
    ${renderOpsMetric("Ревью-записи", summary.total || 0, "сохранены")}
    ${renderOpsMetric("На проверке", summary.by_status?.pending_review || 0, "ожидают решения")}
    ${renderOpsMetric("Одобрено", summary.by_status?.approved || 0, "принято оператором")}
  </div>`;
}

function renderCandidateReviewSection(items, pagination = null) {
  if (!items.length) return "";
  const shownText = pagination
    ? `${pagination.offset + 1}-${Math.min(pagination.offset + items.length, pagination.total)} из ${pagination.total}`
    : "";
  const groups = [
    ["improved", "Улучшенные кандидаты"],
    ["new", "Новые кандидаты от LLM"],
    ["rejected", "Кандидаты на отклонение"],
  ];
  return groups
    .map(([type, title]) => {
      const rows = items.filter((item) => item.recommendation_type === type);
      if (!rows.length) return "";
      return `<div class="draft-items">
        <div class="section-head compact-section-head">
          <h4>${escapeHtml(title)}</h4>
          <span class="muted">${escapeHtml(shownText || String(rows.length))}</span>
        </div>
        <div class="table-list">${rows.slice(0, 160).map(renderCandidateReviewRow).join("")}</div>
      </div>`;
    })
    .join("");
}

function renderCandidateReviewRow(item) {
  const title = item.canonical_name || item.source_candidate_id || "кандидат";
  const statusClass = item.status === "rejected" ? "is-danger" : "";
  const coreItemId = item.metadata_json?.interest_core_item_id;
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(title)}</strong>
      <p class="muted">${escapeHtml(item.description || item.rationale || "")}</p>
      <div class="badges">
        ${badge(label(item.status || "pending_review"), statusClass)}
        ${badge(label(item.decision || "needs_review"), item.decision === "reject" ? "is-danger" : "")}
        ${item.category ? badge(item.category) : ""}
        ${badge(label(item.confidence || "medium"))}
        ${item.merge_into_candidate_id ? badge(`merge -> ${item.merge_into_candidate_id}`) : ""}
      </div>
      ${renderCandidateSignalLine("Сигналы", item.lead_signals_json)}
      ${renderCandidateSignalLine("Синонимы", item.synonyms_json)}
      ${renderCandidateSignalLine("Шум", item.noise_patterns_json)}
      ${coreItemId ? `<p class="draft-evidence"><strong>Куда попал:</strong> рабочее ядро, item ${escapeHtml(coreItemId)}</p>` : ""}
      ${item.review_note ? `<p class="draft-evidence"><strong>Комментарий:</strong> ${escapeHtml(item.review_note)}</p>` : ""}
    </div>
    <div class="row-actions">
      <button type="button" data-review-id="${escapeHtml(item.id)}" data-review-status="approved">Одобрить</button>
      <button type="button" class="secondary-button" data-review-id="${escapeHtml(item.id)}" data-review-status="rejected">Отклонить</button>
      <button type="button" class="secondary-button" data-review-id="${escapeHtml(item.id)}" data-review-status="pending_review">Вернуть</button>
    </div>
  </div>`;
}

function renderCoreItems(items, pagination) {
  const shownText = pagination
    ? `${pagination.offset + 1}-${Math.min(pagination.offset + items.length, pagination.total)} из ${pagination.total}`
    : `${items.length} показано`;
  return `<div class="draft-items">
    <div class="section-head compact-section-head">
      <h4>Рабочее ядро</h4>
      <span class="muted">${escapeHtml(shownText)}</span>
    </div>
    <div class="table-list">${items
      .map(
        (item) => `<div class="table-row draft-item-row">
          <div>
            <strong>${escapeHtml(item.canonical_name || "элемент")}</strong>
            <p class="muted">${escapeHtml(item.description || "")}</p>
            <div class="badges">
              ${badge(label(item.status || "active"))}
              ${badge(label(item.confidence || "medium"))}
              ${item.category ? badge(item.category) : ""}
              ${item.source_review_id ? badge(`review ${item.source_review_id}`) : ""}
            </div>
            ${renderCandidateSignalLine("Сигналы", item.lead_signals_json)}
            ${renderCandidateSignalLine("Синонимы", item.synonyms_json)}
            ${renderCandidateSignalLine("Шум", item.noise_patterns_json)}
          </div>
        </div>`
      )
      .join("")}</div>
  </div>`;
}

function enhancementProgressHint(progress) {
  const chunkIndex = progress?.chunk_index || 0;
  const chunkCount = progress?.chunk_count || 0;
  const parallelism = progress?.active_parallelism ? ` · ${progress.active_parallelism} потоков` : "";
  if (chunkCount) return `фрагмент ${chunkIndex}/${chunkCount}${parallelism}`;
  return progress?.model || "модель";
}

function renderEnhancedCandidateSection(title, items, rowRenderer) {
  if (!items.length) return "";
  return `<div class="draft-items">
    <div class="section-head compact-section-head">
      <h4>${escapeHtml(title)}</h4>
      <span class="muted">${escapeHtml(String(items.length))}</span>
    </div>
    <div class="table-list">${items.slice(0, 120).map(rowRenderer).join("")}</div>
  </div>`;
}

function renderImprovedCandidateRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.canonical_name || item.source_candidate_id || "кандидат")}</strong>
      <p class="muted">${escapeHtml(item.description || item.rationale || "")}</p>
      <div class="badges">
        ${badge(label(item.decision || "needs_review"), item.decision === "reject" ? "is-danger" : "")}
        ${item.category ? badge(item.category) : ""}
        ${badge(label(item.confidence || "medium"))}
        ${item.merge_into_candidate_id ? badge(`merge -> ${item.merge_into_candidate_id}`) : ""}
      </div>
      ${renderCandidateSignalLine("Сигналы", item.lead_signals)}
      ${renderCandidateSignalLine("Синонимы", item.synonyms)}
      ${renderCandidateSignalLine("Шум", item.noise_patterns)}
    </div>
  </div>`;
}

function renderNewCandidateRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.canonical_name || "новый кандидат")}</strong>
      <p class="muted">${escapeHtml(item.description || item.rationale || "")}</p>
      <div class="badges">
        ${item.category ? badge(item.category) : ""}
        ${badge(label(item.confidence || "medium"))}
      </div>
      ${renderCandidateSignalLine("Сигналы", item.lead_signals)}
      ${renderCandidateSignalLine("Синонимы", item.synonyms)}
      ${renderCandidateSignalLine("Шум", item.noise_patterns)}
    </div>
  </div>`;
}

function renderRejectedCandidateRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.source_candidate_id || "кандидат")}</strong>
      <p class="muted">${escapeHtml(item.reason || "")}</p>
      <div class="badges">${badge("reject", "is-danger")}</div>
    </div>
  </div>`;
}

function renderCandidateSignalLine(title, items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `<p class="draft-evidence"><strong>${escapeHtml(title)}:</strong> ${escapeHtml(items.slice(0, 5).join("; "))}</p>`;
}

function renderPageControls(pagination, kind) {
  if (!pagination || pagination.total <= pagination.limit) return "";
  const from = pagination.total ? pagination.offset + 1 : 0;
  const to = Math.min(pagination.offset + pagination.limit, pagination.total);
  const actionAttr =
    kind === "review"
      ? "data-review-page-action"
      : kind === "core"
        ? "data-core-page-action"
        : kind === "analysis-runs"
        ? "data-analysis-runs-page-action"
        : kind === "analysis-matches"
          ? "data-analysis-matches-page-action"
          : kind === "intent-runs"
            ? "data-intent-runs-page-action"
            : kind === "intent-matches"
              ? "data-intent-matches-page-action"
              : kind === "intent-exclusions"
                ? "data-intent-exclusions-page-action"
                : kind === "prep-texts"
                  ? "data-prep-texts-page-action"
                  : kind === "prep-features"
                    ? "data-prep-features-page-action"
                    : kind === "prep-entities"
                      ? "data-prep-entities-page-action"
                      : kind === "prep-ngrams"
                        ? "data-prep-ngrams-page-action"
                        : "data-draft-page-action";
  return `<div class="queue-pagination">
    <span class="muted">${escapeHtml(`${from}-${to} из ${pagination.total}`)}</span>
    <div class="button-row">
      <button type="button" class="secondary-button" ${actionAttr}="prev" ${pagination.offset <= 0 ? "disabled" : ""}>Назад</button>
      <button type="button" class="secondary-button" ${actionAttr}="next" ${pagination.has_more ? "" : "disabled"}>Дальше</button>
    </div>
  </div>`;
}

function initInterestContextDraftScreen() {
  const root = document.querySelector("#interest-context-draft-screen");
  const contextId = root?.dataset.contextId || "";
  if (!contextId) return;
  document.body.dataset.interestContextId = contextId;
  const state = {
    selectedId: contextId,
    draftPollTimer: null,
  };
  document
    .querySelector("#interest-context-draft-refresh")
    ?.addEventListener("click", () => loadInterestContextDraftStatus(state));
  loadInterestContextDraftStatus(state);
}

function renderDraftStageResults(stageResults) {
  if (!stageResults.length) return "";
  const rows = stageResults.slice(-7);
  return `<div class="table-list prepare-stage-results">${rows
    .map((result) => {
      const metrics = result.metrics || {};
      const metricText = [
        metrics.total_rows ? `${metrics.total_rows} строк` : "",
        metrics.entity_rows ? `${metrics.entity_rows} сущностей` : "",
        metrics.ranked_entity_rows ? `${metrics.ranked_entity_rows} ранжировано` : "",
        metrics.candidate_count ? `${metrics.candidate_count} кандидатов` : "",
      ]
        .filter(Boolean)
        .join(" / ");
      return `<div class="table-row">
        <div>
          <strong>${escapeHtml(result.stage_label || result.stage || "этап")}</strong>
          <p class="muted">${escapeHtml(metricText || result.raw_export_run_id || "готово")}</p>
          <p class="draft-evidence"><strong>Роль:</strong> ${escapeHtml(draftStageExplanation(result.stage || result.stage_label))}</p>
        </div>
        <span>${badge("готово")}</span>
      </div>`;
    })
    .join("")}</div>`;
}

function draftStageExplanation(stage) {
  const key = String(stage || "").toLowerCase();
  if (key.includes("entity") || key.includes("сущ")) return "вытащить термины-кандидаты из подготовленного текста";
  if (key.includes("rank") || key.includes("ранж")) return "очистить шум и отсортировать кандидатов по полезности";
  if (key.includes("draft") || key.includes("кандид")) return "создать черновые элементы, которые можно ревьюить постранично";
  return "промежуточный шаг сборки ядра из подготовленных данных";
}

function renderDraftItems(items, pagination = null) {
  if (!items.length) {
    return '<div class="empty-state">Кандидатов пока нет. Запустите формирование ядра интересов после подготовки данных.</div>';
  }
  const shownText = pagination
    ? `${pagination.offset + 1}-${Math.min(pagination.offset + items.length, pagination.total)} из ${pagination.total}`
    : `${items.length} показано`;
  return `<div class="draft-items">
    <div class="section-head compact-section-head">
      <h4>Кандидаты для ревью</h4>
      <span class="muted">${escapeHtml(shownText)}</span>
    </div>
    <div class="table-list">${items
      .map((item) => {
        const metadata = item.metadata_json || {};
        const evidence = item.evidence_json || [];
        const examples = evidence
          .map((entry) => entry.example)
          .filter(Boolean)
          .slice(0, 2);
        return `<div class="table-row draft-item-row">
          <div>
            <strong>${escapeHtml(item.title || item.normalized_key || "кандидат")}</strong>
            <p class="muted">${escapeHtml(item.description || "")}</p>
            <div class="badges">
              ${badge(label(item.item_type || "term"))}
              ${badge(`score ${formatScore(item.score)}`)}
              ${badge(`${item.evidence_count || evidence.length || 0} evidence`)}
              ${badge(`${item.source_message_count || 0} сообщений`)}
              ${badge(label(item.confidence || "medium"))}
              ${badge(label(item.status || "pending_review"))}
              ${badge(label(metadata.ai_review_status || "not_checked"), metadata.ai_review_status === "rejected" ? "is-danger" : "")}
              ${metadata.ai_review_decision ? badge(label(metadata.ai_review_decision)) : ""}
              ${metadata.uses_llm === false ? badge("без AI") : ""}
            </div>
            <p class="draft-evidence"><strong>Почему кандидат здесь:</strong> score = частота + POS/entity pattern + подтверждения из источников - штрафы за шум.</p>
            ${examples.length ? `<div class="draft-evidence">${examples.map((example) => `<p>${escapeHtml(example)}</p>`).join("")}</div>` : ""}
          </div>
        </div>`;
      })
      .join("")}</div>
  </div>`;
}

function formatScore(value) {
  const parsed = Number.parseFloat(value);
  if (Number.isNaN(parsed)) return "0.00";
  return parsed.toFixed(2);
}

function renderProgressLine(labelText, percent, hint) {
  const value = Math.max(0, Math.min(1, percent / 100));
  return `<div class="prepare-progress-line">
    <div>
      <strong>${escapeHtml(labelText)}</strong>
      <span>${escapeHtml(hint || "")}</span>
    </div>
    <md-linear-progress value="${escapeHtml(String(value))}"></md-linear-progress>
    <b>${escapeHtml(String(percent))}%</b>
  </div>`;
}

function renderPrepareStageResults(stageResults) {
  if (!stageResults.length) return "";
  const rows = stageResults.slice(-8);
  return `<div class="table-list prepare-stage-results">${rows
    .map((result) => {
      const metrics = result.metrics || {};
      const metricText = [
        metrics.total_messages ? `${metrics.total_messages} сообщений` : "",
        metrics.total_rows ? `${metrics.total_rows} строк` : "",
        metrics.rows_with_text ? `${metrics.rows_with_text} с текстом` : "",
        metrics.normalized_rows ? `${metrics.normalized_rows} нормализовано` : "",
        metrics.total_tokens ? `${metrics.total_tokens} токенов` : "",
        metrics.indexed_documents ? `${metrics.indexed_documents} документов в индексе` : "",
        metrics.collection_count ? `${metrics.collection_count} Chroma` : "",
        metrics.feature_rows ? `${metrics.feature_rows} features` : "",
        metrics.entity_rows ? `${metrics.entity_rows} сущностей` : "",
        metrics.ranked_entity_rows ? `${metrics.ranked_entity_rows} ранжировано` : "",
        metrics.candidate_count ? `${metrics.candidate_count} кандидатов` : "",
      ]
        .filter(Boolean)
        .join(" / ");
      return `<div class="table-row">
        <div>
          <strong>${escapeHtml(result.stage_label || result.stage || "этап")}</strong>
          <p class="muted">${escapeHtml(metricText || result.raw_export_run_id || "")}</p>
          <p class="draft-evidence"><strong>Что сделано:</strong> ${escapeHtml(prepareStageExplanation(result.stage || result.stage_label))}</p>
          ${renderPrepareStageArtifactLine(metrics)}
        </div>
        <span>${badge("готово")}</span>
      </div>`;
    })
    .join("")}</div>`;
}

function prepareStageExplanation(stage) {
  const key = String(stage || "").toLowerCase();
  if (key.includes("text") || key.includes("normal") || key.includes("stage_2")) {
    return "raw_text сохранен, clean_text очищен, построены tokens/lemmas/POS и token-map";
  }
  if (key.includes("index") || key.includes("chroma") || key.includes("embedding")) {
    return "подготовленный текст добавлен в PostgreSQL FTS и семантический индекс local_hashing_v1";
  }
  if (key.includes("feature") || key.includes("stage_3")) {
    return "в PostgreSQL добавлены признаки сообщения: вопрос/решение, ссылки, цены, контакты и технический score";
  }
  if (key.includes("stat") || key.includes("stage_4") || key.includes("aggregate")) {
    return "в PostgreSQL сохранены агрегаты по источникам, n-граммам, частотам, ссылкам и качеству данных";
  }
  if (key.includes("rank")) {
    return "сущности очищены от шума, получили score и порядок для сборки ядра";
  }
  if (key.includes("entity") || key.includes("stage_5")) {
    return "извлечены сущности по POS-паттернам и подготовлены кандидаты для ранжирования";
  }
  return "промежуточный артефакт подготовки данных";
}

function renderPrepareStageArtifactLine(metrics) {
  const paths = [
    metrics.texts_parquet_path ? `texts.parquet: ${shortPath(metrics.texts_parquet_path)}` : "",
    metrics.search_table_name ? `FTS: ${metrics.search_table_name}` : "",
    metrics.postgres_feature_rows ? `features: ${metrics.postgres_feature_rows}` : "",
    metrics.postgres_entity_rows ? `entities: ${metrics.postgres_entity_rows}` : "",
    metrics.postgres_ranked_entity_rows ? `ranked: ${metrics.postgres_ranked_entity_rows}` : "",
    metrics.report_path ? `отчет: ${shortPath(metrics.report_path)}` : "",
    metrics.entities_parquet_path ? `entities.parquet: ${shortPath(metrics.entities_parquet_path)}` : "",
    metrics.ranked_entities_parquet_path
      ? `ranked.parquet: ${shortPath(metrics.ranked_entities_parquet_path)}`
      : "",
  ].filter(Boolean);
  return paths.length
    ? `<p class="draft-evidence"><strong>Артефакты:</strong> ${escapeHtml(paths.join("; "))}</p>`
    : "";
}

function shortPath(value) {
  const text = String(value || "");
  if (text.length <= 76) return text;
  return `...${text.slice(-73)}`;
}

function normalizePercent(value) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return 0;
  return Math.max(0, Math.min(100, parsed));
}

function renderInterestContextRawReview(payload) {
  const target = document.querySelector("#interest-context-raw-review");
  if (!target) return;
  const summary = payload.summary || {};
  const runs = payload.raw_export_runs || [];
  const messages = (payload.messages || []).slice(0, 3);
  target.innerHTML = `<section class="raw-review-section">
    <div class="section-head">
      <div>
        <h3>Проверка данных контекста</h3>
        <p class="muted">${escapeHtml(rawReviewScopeText(payload))}</p>
      </div>
    </div>
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
      ${renderOpsMetric("Источники", summary.source_count || 0, "в этом контексте")}
      ${renderOpsMetric("Запуски", summary.raw_export_run_count || 0, "raw export")}
      ${renderOpsMetric("Сообщения", summary.raw_message_count || 0, "в raw/parquet")}
      ${renderOpsMetric("Вложения", summary.raw_attachment_count || 0, "найдено")}
      ${renderOpsMetric("Рабочая база", summary.source_message_count || 0, "сообщений для поиска")}
      ${renderOpsMetric("Нет файла", summary.missing_file_count || 0, "пути без файла")}
      </div>
    </div>
    <div class="raw-review-grid">
      <section>
        <h4>Raw/parquet файлы</h4>
        <p class="muted">Каждая строка ниже - отдельный raw-run: конкретная загрузка архива и ее файлы на диске.</p>
        ${renderRawReviewRuns(runs)}
      </section>
      <section>
        <h4>Короткая выборка сообщений</h4>
        ${renderRawReviewMessages(messages, payload.preview_source)}
      </section>
    </div>
  </section>`;
}

function rawReviewScopeText(payload) {
  const summary = payload.summary || {};
  const dates = [time(summary.date_from), time(summary.date_to)].filter(Boolean).join(" - ");
  const source =
    payload.preview_source === "source_messages"
      ? "примеры взяты из рабочей базы"
      : "примеры взяты напрямую из messages.jsonl";
  return dates ? `${source}; диапазон ${dates}` : source;
}

function renderRawReviewRuns(runs) {
  if (!runs.length) return '<div class="empty-state">Raw-запусков пока нет</div>';
  return `<div class="table-list">${runs
    .map((run) => {
      const files = run.files || [];
      return `<div class="table-row raw-review-run">
        <div>
          <strong>${escapeHtml(run.title || run.username || run.source_ref || run.id)}</strong>
          <p class="muted">${escapeHtml([run.export_format, time(run.started_at), `run ${run.id}`].filter(Boolean).join(" / "))}</p>
          <div class="badges">
            ${badge(label(run.status || "unknown"), run.status === "failed" ? "is-danger" : "")}
            ${badge(run.sync_source_messages ? "рабочая база включена" : "только raw-файлы", run.sync_source_messages ? "" : "is-warn")}
            ${badge(`${run.message_count || 0} сообщений`)}
            ${badge(`${run.attachment_count || 0} вложений`)}
          </div>
          <div class="raw-review-files">${renderRawReviewFiles(files)}</div>
        </div>
      </div>`;
    })
    .join("")}</div>`;
}

function renderRawReviewFiles(files) {
  if (!files.length) return "";
  return files
    .map(
      (file) => `<div class="raw-review-file ${file.exists ? "" : "is-missing"}">
        <span>${escapeHtml(rawReviewFileLabel(file.kind || "file"))}</span>
        <span>${escapeHtml(file.exists ? formatBytes(file.size_bytes || 0) : "нет файла")}</span>
      </div>`
    )
    .join("");
}

function rawReviewFileLabel(kind) {
  const labels = {
    messages_jsonl: "messages.jsonl - сырые сообщения",
    messages_parquet: "messages.parquet - табличный формат",
    attachments_jsonl: "attachments.jsonl - вложения",
    attachments_parquet: "attachments.parquet - вложения таблицей",
    media: "скачанный файл",
  };
  return labels[kind] || label(kind || "file");
}

function renderRawReviewMessages(messages, previewSource) {
  if (!messages.length) {
    return `<div class="empty-state">Сообщения не найдены. Если архив загружен без рабочей базы, проверьте raw-файлы в артефактах.</div>`;
  }
  const sourceNote =
    previewSource === "source_messages"
      ? "Показаны 3 последних сообщения из рабочей таблицы выбранного контекста. Это не полный список."
      : "Рабочая таблица пуста, показаны 3 первых сообщения из messages.jsonl выбранного raw-run.";
  return `<p class="muted">${escapeHtml(sourceNote)}</p>
    <div class="table-list">${messages
      .map(
        (message) => `<div class="table-row raw-review-message">
          <div>
            <strong>#${escapeHtml(String(message.telegram_message_id || "н/д"))}</strong>
            <p class="muted">${escapeHtml([time(message.message_date), message.sender_id].filter(Boolean).join(" / "))}</p>
            <p>${escapeHtml(message.text || "без текста")}</p>
            <div class="badges">
              ${message.has_media ? badge("есть вложение") : ""}
              ${message.reply_to_message_id ? badge(`reply ${message.reply_to_message_id}`) : ""}
              ${message.classification_status ? badge(label(message.classification_status)) : ""}
            </div>
            ${message.message_url ? `<p class="draft-evidence"><a href="${escapeHtml(message.message_url)}" target="_blank" rel="noreferrer">Открыть сообщение в Telegram</a></p>` : ""}
          </div>
        </div>`
      )
      .join("")}</div>`;
}

async function loadInterestContextPrepareTextsPage(state) {
  const target = document.querySelector("#interest-context-prep-texts");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  target.innerHTML = '<div class="empty-state">Загружаю Stage 2...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.prepTextsLimit),
      offset: String(state.prepTextsOffset),
    });
    appendPrepRunParam(params, state);
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/texts?${params.toString()}`
    );
    renderInterestContextPrepareTexts(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function changeInterestContextPrepTextsPage(event, state) {
  const button = event.target.closest("[data-prep-texts-page-action]");
  if (!button) return;
  if (button.dataset.prepTextsPageAction === "prev") {
    state.prepTextsOffset = Math.max(0, state.prepTextsOffset - state.prepTextsLimit);
  }
  if (button.dataset.prepTextsPageAction === "next") {
    state.prepTextsOffset += state.prepTextsLimit;
  }
  loadInterestContextPrepareTextsPage(state);
}

function renderInterestContextPrepareTexts(payload, state) {
  const target = document.querySelector("#interest-context-prep-texts");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.prepTextsLimit, offset: 0, total: 0 };
  const summary = payload.summary || {};
  target.innerHTML = `<section class="draft-review-section">
    ${renderPrepareRunSelector(payload, state)}
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
        ${renderOpsMetric("Строки", summary.total_rows || pagination.total || 0, "prepared documents")}
        ${renderOpsMetric("Токены", summary.total_tokens || 0, "в PostgreSQL")}
        ${renderOpsMetric("Хранилище", summary.storage || "postgresql", "операционная БД")}
      </div>
    </div>
    ${items.length ? `<div class="table-list">${items.map(renderPrepareTextRow).join("")}</div>` : '<div class="empty-state">Stage 2 еще не готов. Нажмите «Подготовить данные».</div>'}
    ${renderPageControls(pagination, "prep-texts")}
  </section>`;
}

function renderPrepareTextRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(prepareDocumentTitle(item))}</strong>
      <p class="muted">${escapeHtml([item.entity_type, `#${item.telegram_message_id || "н/д"}`, time(item.date)].filter(Boolean).join(" / "))}</p>
      <p class="draft-evidence"><strong>raw_text:</strong> ${escapeHtml(shortText(item.raw_text || "", 240))}</p>
      <p class="draft-evidence"><strong>clean_text:</strong> ${escapeHtml(shortText(item.clean_text || "", 240))}</p>
      <div class="badges">
        ${badge(`${item.token_count || 0} tokens`)}
        ${badge(item.normalization_lang || "unknown")}
        ${badge(label(item.normalization_status || "normalized"))}
        ${item.artifact_kind ? badge(item.artifact_kind) : ""}
      </div>
      ${renderSmallArray("tokens", item.tokens)}
      ${renderSmallArray("lemmas", item.lemmas)}
      ${renderSmallArray("POS", item.pos_tags)}
      ${renderTokenMapPreview(item.token_map)}
      ${renderTelegramMessageLink(item)}
    </div>
  </div>`;
}

function appendPrepRunParam(params, state) {
  if (state?.selectedPrepRawRunId) {
    params.set("raw_export_run_id", state.selectedPrepRawRunId);
  }
}

async function loadInterestPrepareRunSelector(state, metadataKey) {
  const target = document.querySelector("#interest-context-prep-run-selector");
  if (!target || !state.selectedId) return;
  const key = metadataKey || target.dataset.prepRunMetadataKey || "text_normalization";
  target.innerHTML = '<div class="empty-state">Загружаю источники данных...</div>';
  try {
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/runs?metadata_key=${encodeURIComponent(key)}`
    );
    const runs = payload.raw_runs || [];
    const activeId =
      state.selectedPrepRawRunId && runs.some((run) => run.id === state.selectedPrepRawRunId)
        ? state.selectedPrepRawRunId
        : runs[0]?.id || null;
    state.selectedPrepRawRunId = activeId;
    target.innerHTML = renderPrepareRunSelector(
      {
        raw_runs: runs,
        raw_export_run: runs.find((run) => run.id === activeId) || runs[0] || null,
      },
      state
    );
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderPrepareRunSelector(payload, state) {
  const runs = payload.raw_runs || [];
  const activeId = payload.raw_export_run?.id || state?.selectedPrepRawRunId || "";
  if (state && activeId) state.selectedPrepRawRunId = activeId;
  const current = payload.raw_export_run || {};
  return `<div class="explain-box compact-explain-box">
    <strong>Источник данных</strong>
    <p class="muted">${escapeHtml([
      current.title || current.username || current.source_ref || current.id || "raw-run не выбран",
      current.message_count != null ? `${current.message_count} сообщений` : "",
      current.attachment_count != null ? `${current.attachment_count} вложений` : "",
      current.id ? `run ${current.id}` : "",
    ].filter(Boolean).join(" / "))}</p>
    ${runs.length ? `<label class="material-select-line">Raw-run
      <select data-prep-run-select>
        ${runs.map((run) => `<option value="${escapeHtml(run.id)}" ${run.id === activeId ? "selected" : ""}>${escapeHtml(prepareRunLabel(run))}</option>`).join("")}
      </select>
    </label>` : ""}
  </div>`;
}

function prepareRunLabel(run) {
  return [
    run.title || run.username || run.source_ref || run.id,
    run.message_count != null ? `${run.message_count} msg` : "",
    run.attachment_count != null ? `${run.attachment_count} files` : "",
  ]
    .filter(Boolean)
    .join(" / ");
}

function handleInterestPrepRunChange(event, state) {
  const select = event.target.closest("[data-prep-run-select]");
  if (!select) return;
  state.selectedPrepRawRunId = select.value || null;
  state.prepTextsOffset = 0;
  state.prepFeaturesOffset = 0;
  state.prepEntitiesOffset = 0;
  state.prepNgramsOffset = 0;
  if (state.step === "prepare_texts") loadInterestContextPrepareTextsPage(state);
  if (state.step === "prepare_features") loadInterestContextPrepareFeaturesPage(state);
  if (state.step === "prepare_aggregates") loadInterestContextPrepareAggregates(state);
  if (state.step === "prepare_entities") loadInterestContextPrepareEntitiesPage(state);
  if (state.step === "prepare_search_fts") {
    const target = document.querySelector("#interest-context-prep-fts-results");
    if (target) target.innerHTML = '<div class="empty-state">Источник выбран. Введите запрос и нажмите поиск.</div>';
  }
  if (state.step === "prepare_search_chroma") {
    const target = document.querySelector("#interest-context-prep-chroma-results");
    if (target) target.innerHTML = '<div class="empty-state">Источник выбран. Введите запрос и нажмите поиск.</div>';
  }
}

function prepareDocumentTitle(item) {
  if (item.entity_type === "telegram_artifact") {
    return item.file_name || item.title || item.source_url || "текст вложения";
  }
  return "сообщение Telegram";
}

function renderSmallArray(title, values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `<p class="draft-evidence"><strong>${escapeHtml(title)}:</strong> ${escapeHtml(values.slice(0, 18).join(", "))}</p>`;
}

function renderTokenMapPreview(values) {
  if (!Array.isArray(values) || !values.length) return "";
  const preview = values
    .slice(0, 8)
    .map((item) => `${item.token || ""}->${item.lemma || ""}/${item.pos || ""}`)
    .join("; ");
  return `<p class="draft-evidence"><strong>token-map:</strong> ${escapeHtml(preview)}</p>`;
}

async function searchInterestContextPrepareFts(event, state) {
  event.preventDefault();
  await searchInterestContextPrepared(
    state,
    event.currentTarget,
    "#interest-context-prep-fts-results",
    "fts"
  );
}

async function searchInterestContextPrepareChroma(event, state) {
  event.preventDefault();
  await searchInterestContextPrepared(
    state,
    event.currentTarget,
    "#interest-context-prep-chroma-results",
    "chroma"
  );
}

async function searchInterestContextPrepared(state, form, selector, kind) {
  const target = document.querySelector(selector);
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  const query = formValue(form, "q");
  if (!query) return;
  target.innerHTML = `<div class="empty-state">Ищу: ${escapeHtml(query)}...</div>`;
  try {
    const params = new URLSearchParams({ q: query, limit: "10" });
    appendPrepRunParam(params, state);
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/search/${kind}?${params.toString()}`
    );
    renderInterestContextPreparedSearch(payload, selector, kind);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function renderInterestContextPreparedSearch(payload, selector, kind) {
  const target = document.querySelector(selector);
  if (!target) return;
  const items = payload.results || [];
  const metrics = payload.metrics || {};
  const explanation = payload.search_explanation || {};
  target.innerHTML = `<section class="draft-review-section">
    ${renderPrepareRunSelector(payload, null)}
    <div class="explain-box compact-explain-box">
      <strong>${kind === "fts" ? "Как работает FTS" : "Как работает Chroma"}</strong>
      <p class="muted">${escapeHtml([
        explanation.storage,
        explanation.query_normalization,
        explanation.ranking || explanation.embedding_profile,
      ].filter(Boolean).join(" / "))}</p>
    </div>
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
        ${renderOpsMetric("Найдено", items.length, kind === "fts" ? "PostgreSQL FTS" : "Chroma")}
        ${renderOpsMetric("FTS hits", metrics.fts_hits || 0, "точные")}
        ${renderOpsMetric("Chroma hits", metrics.chroma_hits || 0, "семантика")}
      </div>
    </div>
    ${items.length ? `<div class="table-list">${items.map(renderPreparedSearchRow).join("")}</div>` : '<div class="empty-state">Ничего не найдено.</div>'}
  </section>`;
}

function renderPreparedSearchRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(prepareDocumentTitle(item))}</strong>
      <p class="muted">${escapeHtml([item.entity_type, `#${item.telegram_message_id || "н/д"}`, time(item.date)].filter(Boolean).join(" / "))}</p>
      <p>${escapeHtml(shortText(item.clean_text || "", 420))}</p>
      <div class="badges">
        ${badge((item.sources || []).join("+") || "search")}
        ${badge(`score ${formatScore(item.score)}`)}
        ${badge(`fts ${formatScore(item.fts_score)}`)}
        ${badge(`chroma ${formatScore(item.chroma_score)}`)}
        ${item.artifact_kind ? badge(item.artifact_kind) : ""}
      </div>
      ${renderTelegramMessageLink(item)}
    </div>
  </div>`;
}

async function loadInterestContextPrepareFeaturesPage(state) {
  const target = document.querySelector("#interest-context-prep-features");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  target.innerHTML = '<div class="empty-state">Загружаю Stage 3...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.prepFeaturesLimit),
      offset: String(state.prepFeaturesOffset),
    });
    appendPrepRunParam(params, state);
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/features?${params.toString()}`
    );
    renderInterestContextPrepareFeatures(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function changeInterestContextPrepFeaturesPage(event, state) {
  const button = event.target.closest("[data-prep-features-page-action]");
  if (!button) return;
  if (button.dataset.prepFeaturesPageAction === "prev") {
    state.prepFeaturesOffset = Math.max(0, state.prepFeaturesOffset - state.prepFeaturesLimit);
  }
  if (button.dataset.prepFeaturesPageAction === "next") {
    state.prepFeaturesOffset += state.prepFeaturesLimit;
  }
  loadInterestContextPrepareFeaturesPage(state);
}

function renderInterestContextPrepareFeatures(payload, state) {
  const target = document.querySelector("#interest-context-prep-features");
  if (!target) return;
  const items = payload.items || [];
  const pagination = payload.pagination || { limit: state.prepFeaturesLimit, offset: 0, total: 0 };
  target.innerHTML = `<section class="draft-review-section">
    ${renderPrepareRunSelector(payload, state)}
    ${items.length ? `<div class="table-list">${items.map(renderPrepareFeatureRow).join("")}</div>` : '<div class="empty-state">Stage 3 еще не готов. Запустите подготовку данных.</div>'}
    ${renderPageControls(pagination, "prep-features")}
  </section>`;
}

function renderPrepareFeatureRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(prepareDocumentTitle(item))}</strong>
      <p class="muted">${escapeHtml([item.entity_type, `#${item.telegram_message_id || "н/д"}`, time(item.date)].filter(Boolean).join(" / "))}</p>
      <p>${escapeHtml(shortText(item.clean_text || "", 360))}</p>
      <div class="badges">
        ${item.is_question_like ? badge("question") : ""}
        ${item.is_solution_like ? badge("solution") : ""}
        ${item.is_offer_like ? badge("offer") : ""}
        ${item.has_price ? badge("price") : ""}
        ${item.has_phone ? badge("phone") : ""}
        ${item.has_url ? badge("url") : ""}
        ${badge(`tech ${formatScore(item.technical_language_score)}`)}
        ${badge(label(item.text_quality || "normal"))}
      </div>
      ${renderSmallArray("urls", item.urls)}
      ${renderTelegramMessageLink(item)}
    </div>
  </div>`;
}

async function loadInterestContextPrepareAggregates(state) {
  const target = document.querySelector("#interest-context-prep-aggregates");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  target.innerHTML = '<div class="empty-state">Загружаю Stage 4...</div>';
  try {
    const params = new URLSearchParams();
    appendPrepRunParam(params, state);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/aggregates${suffix}`
    );
    const ngramParams = new URLSearchParams({
      kind: state.prepNgramsKind || "lemmas",
      limit: String(state.prepNgramsLimit),
      offset: String(state.prepNgramsOffset),
    });
    appendPrepRunParam(ngramParams, state);
    payload.ngram_page = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/aggregates/ngrams?${ngramParams.toString()}`
    );
    renderInterestContextPrepareAggregates(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function renderInterestContextPrepareAggregates(payload, state) {
  const target = document.querySelector("#interest-context-prep-aggregates");
  if (!target) return;
  const summary = payload.summary?.metrics || payload.summary || {};
  const urls = payload.urls || {};
  const quality = payload.source_quality || {};
  const ngramPage = payload.ngram_page || {};
  target.innerHTML = `<section class="draft-review-section">
    ${renderPrepareRunSelector(payload, state)}
    <div class="operations-summary raw-review-summary">
      <div class="ops-metric-row">
        ${renderOpsMetric("Строки", summary.total_rows || 0, "features")}
        ${renderOpsMetric("Вопросы", summary.question_like_rows || 0, "question_like")}
        ${renderOpsMetric("URL", summary.rows_with_url || 0, "строк")}
      </div>
    </div>
    ${renderNgramPage(ngramPage, state)}
    <div class="raw-review-grid">
      ${renderAggregateList("Домены", urls.domains)}
      ${renderAggregateObject("Качество", quality)}
    </div>
  </section>`;
}

function changeInterestContextPrepNgramsPage(event, state) {
  const button = event.target.closest("[data-prep-ngrams-page-action]");
  if (!button) return;
  if (button.dataset.prepNgramsPageAction === "prev") {
    state.prepNgramsOffset = Math.max(0, state.prepNgramsOffset - state.prepNgramsLimit);
  }
  if (button.dataset.prepNgramsPageAction === "next") {
    state.prepNgramsOffset += state.prepNgramsLimit;
  }
  loadInterestContextPrepareAggregates(state);
}

function changeInterestContextPrepNgramsKind(event, state) {
  const select = event.target.closest("[data-prep-ngrams-kind]");
  if (!select) return;
  state.prepNgramsKind = select.value || "lemmas";
  state.prepNgramsOffset = 0;
  loadInterestContextPrepareAggregates(state);
}

function renderNgramPage(payload, state) {
  const items = payload.items || [];
  const pagination =
    payload.pagination || { limit: state.prepNgramsLimit, offset: state.prepNgramsOffset, total: 0 };
  const summary = payload.summary || {};
  const kind = payload.kind || state.prepNgramsKind || "lemmas";
  return `<section class="draft-items">
    <div class="section-head compact-section-head">
      <div>
        <h4>N-граммы по леммам</h4>
        <p class="muted">${escapeHtml(`Источник: ${summary.source || "feature_json"}; строк features: ${summary.feature_rows || 0}; уникальных: ${summary.unique_terms || 0}`)}</p>
      </div>
      <label class="material-select-line">Тип
        <select data-prep-ngrams-kind>
          ${["lemmas", "bigrams", "trigrams"].map((value) => `<option value="${value}" ${value === kind ? "selected" : ""}>${value}</option>`).join("")}
        </select>
      </label>
    </div>
    <p class="draft-evidence"><strong>Очистка:</strong> короткие токены и частые служебные слова вроде "или", "ваш", "наш" скрыты до подсчета.</p>
    <div class="table-list">${items.length ? items.map((item) => `<div class="table-row"><div><strong>${escapeHtml(item.term || "item")}</strong></div><span>${escapeHtml(String(item.count || 0))}</span></div>`).join("") : '<div class="empty-state">Нет данных</div>'}</div>
    ${renderPageControls(pagination, "prep-ngrams")}
  </section>`;
}

function renderAggregateList(title, items) {
  const rows = Array.isArray(items) ? items.slice(0, 10) : [];
  return `<section>
    <h4>${escapeHtml(title)}</h4>
    <div class="table-list">${rows.length ? rows.map((item) => `<div class="table-row"><div><strong>${escapeHtml(item.term || item.url || "item")}</strong></div><span>${escapeHtml(String(item.count || 0))}</span></div>`).join("") : '<div class="empty-state">Нет данных</div>'}</div>
  </section>`;
}

function renderAggregateObject(title, value) {
  const rows = value && typeof value === "object" ? Object.entries(value).slice(0, 8) : [];
  return `<section>
    <h4>${escapeHtml(title)}</h4>
    <div class="table-list">${rows.length ? rows.map(([key, item]) => `<div class="table-row"><div><strong>${escapeHtml(key)}</strong></div><span>${escapeHtml(typeof item === "object" ? JSON.stringify(item) : String(item))}</span></div>`).join("") : '<div class="empty-state">Нет данных</div>'}</div>
  </section>`;
}

async function loadInterestContextPrepareEntitiesPage(state) {
  const target = document.querySelector("#interest-context-prep-entities");
  const status = document.querySelector("#interest-context-status");
  if (!target || !state.selectedId) return;
  target.innerHTML = '<div class="empty-state">Загружаю Stage 5...</div>';
  try {
    const params = new URLSearchParams({
      limit: String(state.prepEntitiesLimit),
      offset: String(state.prepEntitiesOffset),
    });
    appendPrepRunParam(params, state);
    const payload = await api(
      `/api/interest-contexts/${encodeURIComponent(state.selectedId)}/prepare-data/entities?${params.toString()}`
    );
    renderInterestContextPrepareEntities(payload, state);
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (status) status.textContent = error.message;
  }
}

function changeInterestContextPrepEntitiesPage(event, state) {
  const button = event.target.closest("[data-prep-entities-page-action]");
  if (!button) return;
  if (button.dataset.prepEntitiesPageAction === "prev") {
    state.prepEntitiesOffset = Math.max(0, state.prepEntitiesOffset - state.prepEntitiesLimit);
  }
  if (button.dataset.prepEntitiesPageAction === "next") {
    state.prepEntitiesOffset += state.prepEntitiesLimit;
  }
  loadInterestContextPrepareEntitiesPage(state);
}

function renderInterestContextPrepareEntities(payload, state) {
  const target = document.querySelector("#interest-context-prep-entities");
  if (!target) return;
  const ranked = payload.ranked || {};
  const extracted = payload.extracted || {};
  const rules = payload.rules || {};
  const pagination =
    ranked.pagination || { limit: state.prepEntitiesLimit, offset: 0, total: 0 };
  target.innerHTML = `<section class="draft-review-section">
    ${renderPrepareRunSelector(payload, state)}
    ${renderEntityRules(rules)}
    <div class="section-head compact-section-head">
      <h4>Ранжированные сущности</h4>
      <span class="muted">${escapeHtml(`${pagination.total || 0} всего`)}</span>
    </div>
    ${ranked.items?.length ? `<div class="table-list">${ranked.items.map(renderRankedEntityRow).join("")}</div>` : '<div class="empty-state">Stage 5 еще не готов. Запустите подготовку данных.</div>'}
    ${renderPageControls(pagination, "prep-entities")}
    <div class="section-head compact-section-head">
      <h4>Извлеченные POS-сущности</h4>
      <span class="muted">${escapeHtml(`${extracted.pagination?.total || 0} всего`)}</span>
    </div>
    ${extracted.items?.length ? `<div class="table-list">${extracted.items.map(renderExtractedEntityRow).join("")}</div>` : ""}
  </section>`;
}

function renderEntityRules(rules) {
  if (!rules || typeof rules !== "object") return "";
  return `<div class="explain-box compact-explain-box">
    <strong>Правила выделения сущностей</strong>
    <ul>
      <li>Берутся POS: ${escapeHtml((rules.candidate_pos || []).join(", ") || "NOUN, PROPN, ADJ")}.</li>
      <li>Паттерны: ${escapeHtml((rules.candidate_patterns || []).join("; "))}.</li>
      <li>Слияние: ${escapeHtml(rules.auto_merge_policy || "exact_only")}; auto только confidence ${escapeHtml(rules.auto_merge_confidence || "high")}.</li>
      <li>Редактирование правил: ${rules.editable ? "включено" : "пока только просмотр; пересчет правил будет отдельным действием"}.</li>
    </ul>
  </div>`;
}

function renderRankedEntityRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.normalized_text || item.canonical_text || "сущность")}</strong>
      <p class="muted">${escapeHtml(item.canonical_text || "")}</p>
      <div class="badges">
        ${badge(`score ${formatScore(item.score)}`)}
        ${badge(label(item.ranking_status || "unknown"))}
        ${badge(`${item.mention_count || 0} mentions`)}
        ${badge(`${item.source_count || 0} sources`)}
      </div>
      ${renderSmallArray("POS", item.pos_pattern)}
      ${renderSmallArray("Причины", item.reasons)}
      ${renderSmallArray("Штрафы", item.penalties)}
      ${renderSmallArray("Примеры", item.example_contexts)}
    </div>
  </div>`;
}

function renderExtractedEntityRow(item) {
  return `<div class="table-row draft-item-row">
    <div>
      <strong>${escapeHtml(item.normalized_text || "сущность")}</strong>
      <div class="badges">
        ${badge(label(item.group_confidence || "high"))}
        ${badge(label(item.group_method || "exact"))}
        ${badge(`${item.mention_count || 0} mentions`)}
      </div>
      ${renderSmallArray("POS", item.pos_pattern)}
    </div>
  </div>`;
}

function setInterestContextFormsEnabled(enabled) {
  [
    "#interest-context-telegram-source-form",
    "#interest-context-telegram-archive-form",
    "#interest-analysis-archive-form",
    "#interest-core-brief-form",
    "#interest-context-prep-fts-form",
    "#interest-context-prep-chroma-form",
  ].forEach((selector) => {
    document
      .querySelectorAll(
        `${selector} input, ${selector} select, ${selector} md-outlined-text-field, ${selector} md-filled-button`
      )
      .forEach((field) => {
        field.disabled = !enabled;
      });
  });
  const draftButton = document.querySelector("#interest-context-build-draft");
  if (draftButton) draftButton.disabled = !enabled;
  const enhanceDraftButton = document.querySelector("#interest-context-enhance-draft-llm");
  if (enhanceDraftButton) enhanceDraftButton.disabled = !enabled;
  const rawReviewButton = document.querySelector("#interest-context-open-raw-review");
  if (rawReviewButton) rawReviewButton.disabled = !enabled;
  const prepareButton = document.querySelector("#interest-context-prepare-data");
  if (prepareButton) prepareButton.disabled = !enabled;
  const generateBriefButton = document.querySelector("#interest-core-brief-generate");
  if (generateBriefButton) generateBriefButton.disabled = !enabled;
  const analysisRefreshButton = document.querySelector("#interest-analysis-refresh");
  if (analysisRefreshButton) analysisRefreshButton.disabled = !enabled;
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
      const editButton = `<md-outlined-button type="button" data-edit-resource-type="${escapeHtml(resource.resource_type)}">
            Редактировать
          </md-outlined-button>`;
      const deleteButton = resource.delete_path
        ? `<md-outlined-button type="button"
            data-delete-resource="${escapeHtml(resource.id)}"
            data-resource-type="${escapeHtml(resource.resource_type)}"
            data-delete-path="${escapeHtml(resource.delete_path)}">
            Удалить
          </md-outlined-button>`
        : "";
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
          ${editButton}
          ${deleteButton}
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
    data_source_telegram_archive: "archive",
    telegram_data_source: "database",
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
  const path = button.dataset.deletePath || paths[resourceType];
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

async function uploadTelegramArchiveResource(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#onboarding-telegram-archive-status");
  const fileInput = form.querySelector('input[name="file"]');
  const submitButton = form.querySelector('md-filled-button[type="submit"]');
  const file = fileInput?.files?.[0];
  if (!file) {
    if (status) status.textContent = "Выберите zip-архив Telegram Desktop.";
    return;
  }
  const data = new FormData(form);
  const syncCheckbox = form.querySelector('[name="sync_source_messages"]');
  data.set("sync_source_messages", syncCheckbox?.checked ? "true" : "false");
  try {
    setTelegramArchiveUploadProgress({ visible: true, value: 0, label: "0%" });
    if (submitButton) submitButton.disabled = true;
    if (status) status.textContent = "Загружаю архив...";
    const payload = await uploadFormData("/api/onboarding/resources/telegram-desktop-archive", data, {
      onProgress: (value) => {
        const percent = Math.round(value * 100);
        setTelegramArchiveUploadProgress({
          visible: true,
          value,
          label: `${percent}%`,
        });
        if (status) status.textContent = `Загрузка архива: ${percent}%`;
      },
      onProcessing: () => {
        setTelegramArchiveUploadProgress({
          visible: true,
          indeterminate: true,
          label: "обработка",
        });
        if (status) status.textContent = "Архив получен. Создаю raw/parquet артефакты...";
      },
    });
    const count = payload.result?.message_count ?? 0;
    if (status) status.textContent = `Источник загружен. Сообщений: ${count}`;
    form.reset();
    closeOnboardingResourceDialog();
    await refreshOnboardingResourceState();
  } catch (error) {
    if (status) status.textContent = error.message;
  } finally {
    if (submitButton) submitButton.disabled = false;
    setTelegramArchiveUploadProgress({ visible: false, value: 0, label: "0%" });
  }
}

function setTelegramArchiveUploadProgress({ visible, value = 0, label = "", indeterminate = false }) {
  const container = document.querySelector("#onboarding-telegram-archive-progress");
  const progress = document.querySelector("#onboarding-telegram-archive-progress-bar");
  const labelTarget = document.querySelector("#onboarding-telegram-archive-progress-label");
  if (!container || !progress) return;
  container.classList.toggle("is-hidden", !visible);
  if (indeterminate) {
    progress.setAttribute("indeterminate", "");
    progress.removeAttribute("value");
  } else {
    progress.removeAttribute("indeterminate");
    progress.value = Math.max(0, Math.min(1, value));
    progress.setAttribute("value", String(progress.value));
  }
  if (labelTarget) labelTarget.textContent = label;
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
