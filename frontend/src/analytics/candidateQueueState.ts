import type { AnalyticsAggregate, CandidateFilters } from "./types";

export type CandidateColumnKey =
  | "sourceType"
  | "receivedAt"
  | "messageDate"
  | "sourceChat"
  | "sourceChatId"
  | "sourceInputRef"
  | "sourceChatStatus"
  | "telegramMessageId"
  | "telegramChatId"
  | "sender"
  | "messageId"
  | "score"
  | "temperature"
  | "reviewLane"
  | "autoLead"
  | "effectiveLead"
  | "leadStatusSource"
  | "reviewStatus"
  | "llmSummary"
  | "llmStatus"
  | "llmVerdict"
  | "llmConfidence"
  | "llmRecommendation"
  | "llmAgreement"
  | "llmModel"
  | "llmRoute"
  | "llmAttempts"
  | "llmUpdatedAt"
  | "llmError"
  | "text"
  | "reasons"
  | "solutionAreas"
  | "customerSegments"
  | "domainSignals"
  | "intentSignals"
  | "noiseSignals"
  | "facts"
  | "enrichmentJobId"
  | "enrichmentStatus"
  | "enrichmentFinishedAt"
  | "enrichmentError"
  | "telegramUrl"
  | "appUrl"
  | "testingUrl"
  | "sourceAccountId"
  | "rawPayload";

export type CandidateColumnConfig = {
  key: CandidateColumnKey;
  visible: boolean;
  width: number;
};

export type CandidateGridSort = {
  field: CandidateColumnKey;
  direction: "asc" | "desc";
};

export type CandidateGridColumnFilter = {
  field: CandidateColumnKey;
  operator: string;
  value: string;
};

export type CandidateValueFilterRequest = {
  field: CandidateColumnKey;
  value: string;
  label: string;
  numeric?: boolean;
};

export type CandidateGridQueryState = {
  sort: CandidateGridSort | null;
  columnFilters: CandidateGridColumnFilter[];
  quickFilter: string;
};

export type CandidateFilterChip = {
  key: keyof CandidateFilters;
  label: string;
  removable: boolean;
};

export type CandidateGridFilterChip = {
  key: string;
  label: string;
  kind: "column" | "quick" | "sort";
  index?: number;
  removable: boolean;
};

export type CandidateQueueSavedFilter = {
  id: string;
  name: string;
  filters: CandidateFilters;
  gridState: CandidateGridQueryState;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
};

export type CandidateColumnFieldset = {
  id: string;
  name: string;
  columns: CandidateColumnConfig[];
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
};

export type CandidateQueueInitialState = {
  filters: CandidateFilters;
  grid: CandidateGridQueryState;
};

export const candidateColumnLabels: Record<CandidateColumnKey, string> = {
  sourceType: "Тип источника",
  receivedAt: "Принято",
  messageDate: "Дата в Telegram",
  sourceChat: "Чат",
  sourceChatId: "ID чата",
  sourceInputRef: "Источник",
  sourceChatStatus: "Статус чата",
  telegramMessageId: "TG message",
  telegramChatId: "TG chat",
  sender: "Автор",
  messageId: "source_message_id",
  score: "Score",
  temperature: "Температура",
  reviewLane: "Очередь",
  autoLead: "Авто лид",
  effectiveLead: "Итог лид",
  leadStatusSource: "Источник статуса",
  reviewStatus: "Ревью",
  llmSummary: "LLM",
  llmStatus: "LLM статус",
  llmVerdict: "LLM вердикт",
  llmConfidence: "LLM confidence",
  llmRecommendation: "LLM рекомендация",
  llmAgreement: "LLM согласие",
  llmModel: "LLM модель",
  llmRoute: "LLM route",
  llmAttempts: "LLM попытки",
  llmUpdatedAt: "LLM обновлено",
  llmError: "LLM ошибка",
  text: "Текст",
  reasons: "Причины",
  solutionAreas: "Зоны решения",
  customerSegments: "Сегменты",
  domainSignals: "Сигналы",
  intentSignals: "Intent",
  noiseSignals: "Шум",
  facts: "Факты",
  enrichmentJobId: "Enrichment job",
  enrichmentStatus: "Enrichment статус",
  enrichmentFinishedAt: "Enrichment готов",
  enrichmentError: "Enrichment ошибка",
  telegramUrl: "Telegram URL",
  appUrl: "App URL",
  testingUrl: "Проверка URL",
  sourceAccountId: "Аккаунт",
  rawPayload: "Raw payload"
};

export const defaultCandidateColumns: CandidateColumnConfig[] = [
  { key: "sourceType", visible: true, width: 120 },
  { key: "receivedAt", visible: true, width: 170 },
  { key: "sourceChat", visible: true, width: 220 },
  { key: "telegramMessageId", visible: true, width: 130 },
  { key: "sender", visible: true, width: 160 },
  { key: "score", visible: true, width: 92 },
  { key: "temperature", visible: true, width: 130 },
  { key: "reviewLane", visible: true, width: 180 },
  { key: "reviewStatus", visible: true, width: 140 },
  { key: "llmSummary", visible: true, width: 210 },
  { key: "text", visible: true, width: 420 },
  { key: "reasons", visible: true, width: 300 },
  { key: "messageId", visible: false, width: 260 },
  { key: "messageDate", visible: false, width: 170 },
  { key: "sourceChatId", visible: false, width: 260 },
  { key: "sourceInputRef", visible: false, width: 180 },
  { key: "sourceChatStatus", visible: false, width: 150 },
  { key: "telegramChatId", visible: false, width: 180 },
  { key: "autoLead", visible: false, width: 110 },
  { key: "effectiveLead", visible: false, width: 110 },
  { key: "leadStatusSource", visible: false, width: 140 },
  { key: "llmStatus", visible: false, width: 130 },
  { key: "llmVerdict", visible: false, width: 130 },
  { key: "llmConfidence", visible: false, width: 140 },
  { key: "llmRecommendation", visible: false, width: 160 },
  { key: "llmAgreement", visible: false, width: 130 },
  { key: "llmModel", visible: false, width: 170 },
  { key: "llmRoute", visible: false, width: 140 },
  { key: "llmAttempts", visible: false, width: 120 },
  { key: "llmUpdatedAt", visible: false, width: 170 },
  { key: "llmError", visible: false, width: 260 },
  { key: "solutionAreas", visible: false, width: 240 },
  { key: "customerSegments", visible: false, width: 240 },
  { key: "domainSignals", visible: false, width: 260 },
  { key: "intentSignals", visible: false, width: 240 },
  { key: "noiseSignals", visible: false, width: 240 },
  { key: "facts", visible: false, width: 280 },
  { key: "enrichmentJobId", visible: false, width: 260 },
  { key: "enrichmentStatus", visible: false, width: 160 },
  { key: "enrichmentFinishedAt", visible: false, width: 170 },
  { key: "enrichmentError", visible: false, width: 260 },
  { key: "telegramUrl", visible: false, width: 260 },
  { key: "appUrl", visible: false, width: 260 },
  { key: "testingUrl", visible: false, width: 260 },
  { key: "sourceAccountId", visible: false, width: 260 },
  { key: "rawPayload", visible: false, width: 360 }
];

export const periodQuickFilters = [
  { label: "1 час", chipLabel: "за час", hours: 1 },
  { label: "3 часа", chipLabel: "за 3 часа", hours: 3 },
  { label: "5 часов", chipLabel: "за 5 часов", hours: 5 },
  { label: "12 часов", chipLabel: "за 12 часов", hours: 12 },
  { label: "24 часа", chipLabel: "последние 24 часа", hours: 24 },
  { label: "2 дня", chipLabel: "за 2 дня", hours: 48 },
  { label: "3 дня", chipLabel: "за 3 дня", hours: 72 },
  { label: "Неделя", chipLabel: "за неделю", hours: 168 }
];

export const defaultCandidateGridState: CandidateGridQueryState = {
  sort: null,
  columnFilters: [],
  quickFilter: ""
};

const candidateColumnStorageKey = "pur-leads.analytics.candidate-columns.v1";
const candidateSavedFiltersStorageKey = "pur-leads.analytics.saved-filters.v1";
const candidateFieldsetStorageKey = "pur-leads.analytics.fieldsets.v1";

export function defaultCandidateFilters(): CandidateFilters {
  return {
    scoreMin: "",
    temperature: "",
    signal: "",
    reason: "",
    solutionArea: "",
    customerSegment: "",
    lane: "",
    sourceChatId: "",
    receivedFrom: periodStartDatetimeLocal(24),
    receivedTo: "",
    reviewStatus: "unreviewed",
    verdict: "",
    sourceType: "",
    llmProcessed: "",
    llmStatus: "",
    llmVerdict: "",
    llmRecommendation: "",
    llmModel: "",
    llmRoute: "",
    llmAgreesWithRules: "",
    llmHasError: "",
    q: ""
  };
}

export function candidateFiltersFromSearchParams(params: URLSearchParams): CandidateFilters {
  const defaults = defaultCandidateFilters();
  return {
    ...defaults,
    scoreMin: params.get("score_min") ?? defaults.scoreMin,
    temperature: params.get("temperature") ?? defaults.temperature,
    signal: params.get("signal") ?? defaults.signal,
    reason: params.get("reason") ?? defaults.reason,
    solutionArea: params.get("solution_area") ?? defaults.solutionArea,
    customerSegment: params.get("customer_segment") ?? defaults.customerSegment,
    lane: params.get("lane") ?? defaults.lane,
    sourceChatId: params.get("source_chat_id") ?? defaults.sourceChatId,
    receivedFrom: params.has("received_from")
      ? isoToDatetimeLocal(params.get("received_from") ?? "")
      : defaults.receivedFrom,
    receivedTo: isoToDatetimeLocal(params.get("received_to") ?? ""),
    reviewStatus: params.get("review_status") ?? defaults.reviewStatus,
    verdict: params.get("verdict") ?? defaults.verdict,
    sourceType: params.get("source_type") ?? defaults.sourceType,
    llmProcessed: params.get("llm_processed") ?? defaults.llmProcessed,
    llmStatus: params.get("llm_status") ?? defaults.llmStatus,
    llmVerdict: params.get("llm_verdict") ?? defaults.llmVerdict,
    llmRecommendation: params.get("llm_recommendation") ?? defaults.llmRecommendation,
    llmModel: params.get("llm_model") ?? defaults.llmModel,
    llmRoute: params.get("llm_route") ?? defaults.llmRoute,
    llmAgreesWithRules: params.get("llm_agrees_with_rules") ?? defaults.llmAgreesWithRules,
    llmHasError: params.get("llm_has_error") ?? defaults.llmHasError,
    q: params.get("q") ?? defaults.q
  };
}

export function candidateGridStateFromSearchParams(params: URLSearchParams): CandidateGridQueryState {
  const sortBy = normalizeCandidateColumnKey(params.get("sort_by"));
  const sortDirection = params.get("sort_direction") === "asc" ? "asc" : "desc";
  const columnFilters: CandidateGridColumnFilter[] = parseSerializedGridFilters(params.getAll("grid_filter"));
  if (columnFilters.length === 0) {
    addSearchParamColumnFilter(columnFilters, params, "sourceChat", "source_chat");
    addSearchParamColumnFilter(columnFilters, params, "messageId", "message_id");
    addSearchParamColumnFilter(columnFilters, params, "sourceInputRef", "source_input_ref");
    addSearchParamColumnFilter(columnFilters, params, "sourceChatStatus", "source_chat_status");
    addSearchParamColumnFilter(columnFilters, params, "telegramChatId", "telegram_chat_id");
    addSearchParamColumnFilter(columnFilters, params, "telegramMessageId", "telegram_message_id", "equals");
    addSearchParamColumnFilter(columnFilters, params, "sender", "sender");
    addSearchParamColumnFilter(columnFilters, params, "sourceAccountId", "source_account_id");
    addSearchParamColumnFilter(columnFilters, params, "llmConfidence", "llm_confidence_min", ">=");
    addSearchParamColumnFilter(columnFilters, params, "llmConfidence", "llm_confidence_max", "<=");
    addSearchParamColumnFilter(columnFilters, params, "llmAttempts", "llm_attempts_min", ">=");
    addSearchParamColumnFilter(columnFilters, params, "llmAttempts", "llm_attempts_max", "<=");
    addSearchParamColumnFilter(columnFilters, params, "enrichmentStatus", "enrichment_status", "equals");
  }
  return {
    sort: sortBy ? { field: sortBy, direction: sortDirection } : null,
    columnFilters,
    quickFilter: params.get("grid_q")?.trim() ?? ""
  };
}

export function initialCandidateQueueStateFromSearchParams(params: URLSearchParams): CandidateQueueInitialState {
  if (!candidateRouteHasExplicitFilters(params)) {
    const defaultSavedFilter = loadCandidateSavedFilters().find((filter) => filter.isDefault);
    if (defaultSavedFilter) {
      return {
        filters: normalizeCandidateFilters(defaultSavedFilter.filters),
        grid: normalizeCandidateGridState(defaultSavedFilter.gridState)
      };
    }
  }
  return {
    filters: candidateFiltersFromSearchParams(params),
    grid: candidateGridStateFromSearchParams(params)
  };
}

export function candidateRouteHasExplicitFilters(params: URLSearchParams): boolean {
  for (const key of params.keys()) {
    if (candidateExplicitRouteParams.has(key)) {
      return true;
    }
  }
  return false;
}

export function candidateQuery(
  filters: CandidateFilters,
  limit: number,
  offset: number,
  gridState: CandidateGridQueryState = defaultCandidateGridState
) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  setTrimmed(params, "score_min", filters.scoreMin);
  setTrimmed(params, "temperature", filters.temperature);
  setTrimmed(params, "signal", filters.signal);
  setTrimmed(params, "reason", filters.reason);
  setTrimmed(params, "solution_area", filters.solutionArea);
  setTrimmed(params, "customer_segment", filters.customerSegment);
  setTrimmed(params, "lane", filters.lane);
  setTrimmed(params, "review_status", filters.reviewStatus);
  setTrimmed(params, "verdict", filters.verdict);
  setTrimmed(params, "source_chat_id", filters.sourceChatId);
  setTrimmed(params, "source_type", filters.sourceType);
  setTrimmed(params, "llm_processed", filters.llmProcessed);
  setTrimmed(params, "llm_status", filters.llmStatus);
  setTrimmed(params, "llm_verdict", filters.llmVerdict);
  setTrimmed(params, "llm_recommendation", filters.llmRecommendation);
  setTrimmed(params, "llm_model", filters.llmModel);
  setTrimmed(params, "llm_route", filters.llmRoute);
  setTrimmed(params, "llm_agrees_with_rules", filters.llmAgreesWithRules);
  setTrimmed(params, "llm_has_error", filters.llmHasError);
  const receivedFrom = datetimeLocalToIso(filters.receivedFrom);
  if (receivedFrom) {
    params.set("received_from", receivedFrom);
  }
  const receivedTo = datetimeLocalToIso(filters.receivedTo);
  if (receivedTo) {
    params.set("received_to", receivedTo);
  }
  setTrimmed(params, "q", filters.q);
  appendCandidateGridQuery(params, gridState, filters);
  return params.toString();
}

export function loadCandidateSavedFilters(): CandidateQueueSavedFilter[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(candidateSavedFiltersStorageKey);
    if (!raw) {
      return [];
    }
    return normalizeCandidateSavedFilters(JSON.parse(raw) as unknown);
  } catch {
    return [];
  }
}

export function saveCandidateSavedFilters(filters: CandidateQueueSavedFilter[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(candidateSavedFiltersStorageKey, JSON.stringify(normalizeCandidateSavedFilters(filters)));
}

export function upsertCandidateSavedFilter(
  filters: CandidateQueueSavedFilter[],
  savedFilter: CandidateQueueSavedFilter
): CandidateQueueSavedFilter[] {
  const normalized = normalizeCandidateSavedFilter(savedFilter);
  if (!normalized) {
    return normalizeCandidateSavedFilters(filters);
  }
  const current = normalizeCandidateSavedFilters(filters).filter((filter) => filter.id !== normalized.id);
  const next = normalized.isDefault
    ? current.map((filter) => ({ ...filter, isDefault: false }))
    : current;
  return normalizeCandidateSavedFilters([...next, normalized]);
}

export function deleteCandidateSavedFilter(
  filters: CandidateQueueSavedFilter[],
  id: string
): CandidateQueueSavedFilter[] {
  return normalizeCandidateSavedFilters(filters).filter((filter) => filter.id !== id);
}

export function loadCandidateColumns(): CandidateColumnConfig[] {
  if (typeof window === "undefined") {
    return defaultCandidateColumns;
  }
  try {
    const raw = window.localStorage.getItem(candidateColumnStorageKey);
    if (!raw) {
      return defaultCandidateColumns;
    }
    const parsed = JSON.parse(raw) as unknown;
    return normalizeCandidateColumns(Array.isArray(parsed) ? parsed : defaultCandidateColumns);
  } catch {
    return defaultCandidateColumns;
  }
}

export function saveCandidateColumns(columns: CandidateColumnConfig[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(candidateColumnStorageKey, JSON.stringify(normalizeCandidateColumns(columns)));
}

export function loadCandidateFieldsets(): CandidateColumnFieldset[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(candidateFieldsetStorageKey);
    if (!raw) {
      return [];
    }
    return normalizeCandidateFieldsets(JSON.parse(raw) as unknown);
  } catch {
    return [];
  }
}

export function saveCandidateFieldsets(fieldsets: CandidateColumnFieldset[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(candidateFieldsetStorageKey, JSON.stringify(normalizeCandidateFieldsets(fieldsets)));
}

export function upsertCandidateFieldset(
  fieldsets: CandidateColumnFieldset[],
  fieldset: CandidateColumnFieldset
): CandidateColumnFieldset[] {
  const normalized = normalizeCandidateFieldset(fieldset);
  if (!normalized) {
    return normalizeCandidateFieldsets(fieldsets);
  }
  const current = normalizeCandidateFieldsets(fieldsets).filter((item) => item.id !== normalized.id);
  const next = normalized.isDefault
    ? current.map((item) => ({ ...item, isDefault: false }))
    : current;
  return normalizeCandidateFieldsets([...next, normalized]);
}

export function deleteCandidateFieldset(
  fieldsets: CandidateColumnFieldset[],
  id: string
): CandidateColumnFieldset[] {
  return normalizeCandidateFieldsets(fieldsets).filter((fieldset) => fieldset.id !== id);
}

export function normalizeCandidateColumns(columns: unknown[]): CandidateColumnConfig[] {
  const savedByKey = new Map<string, Partial<CandidateColumnConfig>>();
  for (const item of columns) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const candidate = item as Partial<CandidateColumnConfig>;
    if (typeof candidate.key === "string") {
      savedByKey.set(candidate.key, candidate);
    }
  }
  const result = defaultCandidateColumns.map((defaultColumn) => {
    const saved = savedByKey.get(defaultColumn.key);
    return {
      ...defaultColumn,
      visible: typeof saved?.visible === "boolean" ? saved.visible : defaultColumn.visible,
      width: clampColumnWidth(Number(saved?.width) || defaultColumn.width)
    };
  });
  return result.sort((left, right) => {
    const leftIndex = columns.findIndex((item) => (item as Partial<CandidateColumnConfig>)?.key === left.key);
    const rightIndex = columns.findIndex((item) => (item as Partial<CandidateColumnConfig>)?.key === right.key);
    if (leftIndex === -1 && rightIndex === -1) {
      return 0;
    }
    if (leftIndex === -1) {
      return 1;
    }
    if (rightIndex === -1) {
      return -1;
    }
    return leftIndex - rightIndex;
  });
}

export function clampColumnWidth(width: number): number {
  if (!Number.isFinite(width)) {
    return 160;
  }
  return Math.min(Math.max(Math.round(width), 80), 720);
}

export function periodStartDatetimeLocal(hours: number): string {
  return dateToDatetimeLocal(new Date(Date.now() - hours * 60 * 60 * 1000));
}

export function isActivePeriod(filters: CandidateFilters, hours: number): boolean {
  if (filters.receivedTo.trim()) {
    return false;
  }
  const receivedFrom = new Date(datetimeLocalToIso(filters.receivedFrom));
  if (Number.isNaN(receivedFrom.getTime())) {
    return false;
  }
  const expected = Date.now() - hours * 60 * 60 * 1000;
  return Math.abs(receivedFrom.getTime() - expected) < 90_000;
}

export function buildFilterOptionLabels({
  signalOptions,
  reasonOptions,
  solutionAreaOptions,
  customerSegmentOptions,
  laneOptions,
  sourceChatOptions
}: {
  signalOptions: AnalyticsAggregate[];
  reasonOptions: AnalyticsAggregate[];
  solutionAreaOptions: AnalyticsAggregate[];
  customerSegmentOptions: AnalyticsAggregate[];
  laneOptions: AnalyticsAggregate[];
  sourceChatOptions: AnalyticsAggregate[];
}): Partial<Record<keyof CandidateFilters, Map<string, string>>> {
  return {
    signal: optionsToLabelMap(signalOptions),
    reason: optionsToLabelMap(reasonOptions),
    solutionArea: optionsToLabelMap(solutionAreaOptions),
    customerSegment: optionsToLabelMap(customerSegmentOptions),
    lane: optionsToLabelMap(laneOptions),
    sourceChatId: optionsToLabelMap(sourceChatOptions)
  };
}

export function candidateFilterChips(
  filters: CandidateFilters,
  optionLabels: Partial<Record<keyof CandidateFilters, Map<string, string>>>
): CandidateFilterChip[] {
  const chips: CandidateFilterChip[] = [];
  const labels: Record<keyof CandidateFilters, string> = {
    scoreMin: "Score от",
    temperature: "Температура",
    signal: "Сигнал",
    reason: "Причина",
    solutionArea: "Зона",
    customerSegment: "Сегмент",
    lane: "Очередь",
    sourceChatId: "Чат",
    receivedFrom: "С",
    receivedTo: "По",
    reviewStatus: "Ревью",
    verdict: "Вердикт",
    sourceType: "Источник",
    llmProcessed: "LLM обработано",
    llmStatus: "LLM статус",
    llmVerdict: "LLM вердикт",
    llmRecommendation: "LLM рекомендация",
    llmModel: "LLM модель",
    llmRoute: "LLM route",
    llmAgreesWithRules: "LLM согласие",
    llmHasError: "LLM ошибка",
    q: "Текст"
  };
  for (const [key, value] of Object.entries(filters) as Array<[keyof CandidateFilters, string]>) {
    const trimmed = value.trim();
    if (!trimmed) {
      continue;
    }
    const display = optionLabels[key]?.get(trimmed) ?? filterValueLabel(key, trimmed);
    chips.push({ key, label: `${labels[key]}: ${display}`, removable: true });
  }
  return chips;
}

export function candidateGridFilterChips(gridState: CandidateGridQueryState): CandidateGridFilterChip[] {
  const chips: CandidateGridFilterChip[] = [];
  const quickFilter = gridState.quickFilter.trim();
  if (quickFilter) {
    chips.push({
      key: "grid-quick",
      label: `Быстрый поиск: ${quickFilter}`,
      kind: "quick",
      removable: true
    });
  }
  if (gridState.sort) {
    chips.push({
      key: "grid-sort",
      label: `Сортировка: ${candidateColumnLabels[gridState.sort.field]} ${
        gridState.sort.direction === "asc" ? "по возрастанию" : "по убыванию"
      }`,
      kind: "sort",
      removable: true
    });
  }
  gridState.columnFilters.forEach((filter, index) => {
    const value = filter.value.trim();
    if (!value) {
      return;
    }
    chips.push({
      key: `grid-column-${filter.field}-${index}`,
      label: `${candidateColumnLabels[filter.field]} ${gridOperatorLabel(filter.operator)} ${value}`,
      kind: "column",
      index,
      removable: true
    });
  });
  return chips;
}

function appendCandidateGridQuery(
  params: URLSearchParams,
  gridState: CandidateGridQueryState,
  filters: CandidateFilters
) {
  const sort = gridState.sort;
  const sortField = sort?.field;
  if (sortField && sortableCandidateColumns.has(sortField)) {
    params.set("sort_by", sortField);
    params.set("sort_direction", sort.direction);
  }
  for (const filter of gridState.columnFilters) {
    appendSerializedGridFilter(params, filter);
    appendCandidateGridFilter(params, filter);
  }
  const quickFilter = gridState.quickFilter.trim();
  if (quickFilter && !filters.q.trim() && !params.has("q")) {
    params.set("q", quickFilter);
  }
  setTrimmed(params, "grid_q", gridState.quickFilter);
}

function appendSerializedGridFilter(params: URLSearchParams, filter: CandidateGridColumnFilter) {
  const value = filter.value.trim();
  if (!value || !filterableCandidateColumns.has(filter.field)) {
    return;
  }
  params.append("grid_filter", JSON.stringify({ field: filter.field, operator: filter.operator, value }));
}

function appendCandidateGridFilter(params: URLSearchParams, filter: CandidateGridColumnFilter) {
  const value = filter.value.trim();
  if (!value) {
    return;
  }
  if (filter.operator === "notEquals" || filter.operator === "!=" || filter.operator === "notContains") {
    return;
  }
  switch (filter.field) {
    case "sourceType":
      params.set("source_type", value);
      break;
    case "sourceChat":
      params.set("source_chat", value);
      break;
    case "sourceChatId":
      params.set("source_chat_id", value);
      break;
    case "sourceInputRef":
      params.set("source_input_ref", value);
      break;
    case "sourceChatStatus":
      params.set("source_chat_status", value);
      break;
    case "telegramMessageId":
      params.set("telegram_message_id", value);
      break;
    case "telegramChatId":
      params.set("telegram_chat_id", value);
      break;
    case "sender":
      params.set("sender", value);
      break;
    case "messageId":
      params.set("message_id", value);
      break;
    case "sourceAccountId":
      params.set("source_account_id", value);
      break;
    case "score":
      appendNumericRangeFilter(params, filter.operator, value, "score_min", "score_max");
      break;
    case "temperature":
      params.set("temperature", value);
      break;
    case "reviewLane":
      params.set("lane", value);
      break;
    case "reviewStatus":
      params.set("review_status", value);
      break;
    case "llmStatus":
      if (value === "not_processed") {
        params.set("llm_processed", "false");
      } else {
        params.set("llm_status", value);
      }
      break;
    case "llmVerdict":
      params.set("llm_verdict", value);
      break;
    case "llmConfidence":
      appendNumericRangeFilter(params, filter.operator, value, "llm_confidence_min", "llm_confidence_max");
      break;
    case "llmRecommendation":
      params.set("llm_recommendation", value);
      break;
    case "llmAgreement":
      params.set("llm_agrees_with_rules", normalizeBooleanFilterValue(value));
      break;
    case "llmModel":
      params.set("llm_model", value);
      break;
    case "llmRoute":
      params.set("llm_route", value);
      break;
    case "llmAttempts":
      appendNumericRangeFilter(params, filter.operator, value, "llm_attempts_min", "llm_attempts_max");
      break;
    case "llmError":
      params.set("llm_has_error", normalizeBooleanFilterValue(value));
      break;
    case "reasons":
      params.set("reason", value);
      break;
    case "solutionAreas":
      params.set("solution_area", value);
      break;
    case "customerSegments":
      params.set("customer_segment", value);
      break;
    case "domainSignals":
      params.set("signal", value);
      break;
    case "enrichmentStatus":
      params.set("enrichment_status", value);
      break;
    case "text":
      params.set("q", value);
      break;
    default:
      break;
  }
}

function parseSerializedGridFilters(values: string[]): CandidateGridColumnFilter[] {
  return values.flatMap((raw) => {
    try {
      const parsed = JSON.parse(raw) as Partial<CandidateGridColumnFilter>;
      const field = normalizeCandidateColumnKey(typeof parsed.field === "string" ? parsed.field : null);
      const value = typeof parsed.value === "string" ? parsed.value.trim() : "";
      const operator = typeof parsed.operator === "string" && parsed.operator.trim()
        ? parsed.operator.trim()
        : "contains";
      if (!field || !filterableCandidateColumns.has(field) || !value) {
        return [];
      }
      return [{ field, operator, value }];
    } catch {
      return [];
    }
  });
}

function appendNumericRangeFilter(
  params: URLSearchParams,
  operator: string,
  value: string,
  minParam: string,
  maxParam: string
) {
  if (operator === "<" || operator === "<=" || operator === "before" || operator === "onOrBefore") {
    params.set(maxParam, value);
    return;
  }
  if (operator === "=" || operator === "equals" || operator === "is") {
    params.set(minParam, value);
    params.set(maxParam, value);
    return;
  }
  params.set(minParam, value);
}

function addSearchParamColumnFilter(
  filters: CandidateGridColumnFilter[],
  params: URLSearchParams,
  field: CandidateColumnKey,
  param: string,
  operator = "contains"
) {
  const value = params.get(param)?.trim();
  if (value) {
    filters.push({ field, operator, value });
  }
}

function normalizeCandidateColumnKey(value: string | null): CandidateColumnKey | null {
  if (value && candidateColumnLabels[value as CandidateColumnKey]) {
    return value as CandidateColumnKey;
  }
  return null;
}

function normalizeBooleanFilterValue(value: string): string {
  const lower = value.trim().toLowerCase();
  if (["да", "yes", "true", "1"].includes(lower)) {
    return "true";
  }
  if (["нет", "no", "false", "0"].includes(lower)) {
    return "false";
  }
  return value;
}

function gridOperatorLabel(operator: string): string {
  const labels: Record<string, string> = {
    contains: "содержит",
    notContains: "не содержит",
    equals: "=",
    notEquals: "!=",
    is: "=",
    not: "!=",
    "!=": "!=",
    startsWith: "начинается с",
    endsWith: "заканчивается на",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<="
  };
  return labels[operator] ?? operator;
}

const sortableCandidateColumns = new Set<CandidateColumnKey>([
  "sourceType",
  "receivedAt",
  "messageDate",
  "sourceChat",
  "sourceChatId",
  "sourceInputRef",
  "sourceChatStatus",
  "telegramMessageId",
  "telegramChatId",
  "sender",
  "messageId",
  "score",
  "temperature",
  "reviewLane",
  "autoLead",
  "effectiveLead",
  "leadStatusSource",
  "reviewStatus",
  "llmStatus",
  "llmVerdict",
  "llmConfidence",
  "llmRecommendation",
  "llmAgreement",
  "llmModel",
  "llmRoute",
  "llmAttempts",
  "llmUpdatedAt",
  "text",
  "enrichmentStatus",
  "enrichmentFinishedAt",
  "sourceAccountId"
]);

const filterableCandidateColumns = new Set<CandidateColumnKey>([
  "sourceType",
  "sourceChat",
  "sourceChatId",
  "sourceInputRef",
  "sourceChatStatus",
  "telegramMessageId",
  "telegramChatId",
  "sender",
  "messageId",
  "sourceAccountId",
  "score",
  "temperature",
  "reviewLane",
  "reviewStatus",
  "llmStatus",
  "llmVerdict",
  "llmConfidence",
  "llmRecommendation",
  "llmAgreement",
  "llmModel",
  "llmRoute",
  "llmAttempts",
  "llmError",
  "text",
  "reasons",
  "solutionAreas",
  "customerSegments",
  "domainSignals",
  "enrichmentStatus"
]);

const candidateExplicitRouteParams = new Set([
  "score_min",
  "score_max",
  "temperature",
  "signal",
  "reason",
  "solution_area",
  "customer_segment",
  "lane",
  "message_id",
  "source_chat",
  "source_chat_id",
  "source_input_ref",
  "source_chat_status",
  "telegram_message_id",
  "telegram_chat_id",
  "sender",
  "source_account_id",
  "received_from",
  "received_to",
  "review_status",
  "verdict",
  "source_type",
  "llm_processed",
  "llm_status",
  "llm_verdict",
  "llm_recommendation",
  "llm_model",
  "llm_route",
  "llm_agrees_with_rules",
  "llm_has_error",
  "llm_confidence_min",
  "llm_confidence_max",
  "llm_attempts_min",
  "llm_attempts_max",
  "enrichment_status",
  "sort_by",
  "sort_direction",
  "q",
  "grid_q"
]);

export function isCandidateColumnSortable(key: CandidateColumnKey): boolean {
  return sortableCandidateColumns.has(key);
}

export function isCandidateColumnFilterable(key: CandidateColumnKey): boolean {
  return filterableCandidateColumns.has(key);
}

export function normalizeCandidateFieldsets(value: unknown): CandidateColumnFieldset[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const normalized: CandidateColumnFieldset[] = [];
  let hasDefault = false;
  for (const item of value) {
    const fieldset = normalizeCandidateFieldset(item);
    if (!fieldset) {
      continue;
    }
    if (fieldset.isDefault) {
      if (hasDefault) {
        normalized.push({ ...fieldset, isDefault: false });
        continue;
      }
      hasDefault = true;
    }
    normalized.push(fieldset);
  }
  return normalized;
}

function normalizeCandidateFieldset(value: unknown): CandidateColumnFieldset | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const candidate = value as Partial<CandidateColumnFieldset>;
  const id = typeof candidate.id === "string" ? candidate.id.trim() : "";
  const name = typeof candidate.name === "string" ? candidate.name.trim() : "";
  if (!id || !name) {
    return null;
  }
  const now = new Date().toISOString();
  return {
    id,
    name,
    columns: normalizeCandidateColumns(Array.isArray(candidate.columns) ? candidate.columns : defaultCandidateColumns),
    isDefault: candidate.isDefault === true,
    createdAt: typeof candidate.createdAt === "string" && candidate.createdAt.trim() ? candidate.createdAt : now,
    updatedAt: typeof candidate.updatedAt === "string" && candidate.updatedAt.trim() ? candidate.updatedAt : now
  };
}

export function normalizeCandidateSavedFilters(value: unknown): CandidateQueueSavedFilter[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const normalized: CandidateQueueSavedFilter[] = [];
  let hasDefault = false;
  for (const item of value) {
    const savedFilter = normalizeCandidateSavedFilter(item);
    if (!savedFilter) {
      continue;
    }
    if (savedFilter.isDefault) {
      if (hasDefault) {
        normalized.push({ ...savedFilter, isDefault: false });
        continue;
      }
      hasDefault = true;
    }
    normalized.push(savedFilter);
  }
  return normalized;
}

function normalizeCandidateSavedFilter(value: unknown): CandidateQueueSavedFilter | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const candidate = value as Partial<CandidateQueueSavedFilter>;
  const id = typeof candidate.id === "string" ? candidate.id.trim() : "";
  const name = typeof candidate.name === "string" ? candidate.name.trim() : "";
  if (!id || !name) {
    return null;
  }
  const now = new Date().toISOString();
  return {
    id,
    name,
    filters: normalizeCandidateFilters(candidate.filters),
    gridState: normalizeCandidateGridState(candidate.gridState),
    isDefault: candidate.isDefault === true,
    createdAt: typeof candidate.createdAt === "string" && candidate.createdAt.trim() ? candidate.createdAt : now,
    updatedAt: typeof candidate.updatedAt === "string" && candidate.updatedAt.trim() ? candidate.updatedAt : now
  };
}

function normalizeCandidateFilters(value: unknown): CandidateFilters {
  const defaults = defaultCandidateFilters();
  if (typeof value !== "object" || value === null) {
    return defaults;
  }
  const source = value as Partial<Record<keyof CandidateFilters, unknown>>;
  return Object.fromEntries(
    (Object.keys(defaults) as Array<keyof CandidateFilters>).map((key) => [
      key,
      typeof source[key] === "string" ? source[key] : defaults[key]
    ])
  ) as CandidateFilters;
}

function normalizeCandidateGridState(value: unknown): CandidateGridQueryState {
  if (typeof value !== "object" || value === null) {
    return defaultCandidateGridState;
  }
  const source = value as Partial<CandidateGridQueryState>;
  const sortField = normalizeCandidateColumnKey(source.sort?.field ?? null);
  const sort: CandidateGridSort | null =
    sortField && source.sort?.direction
      ? { field: sortField, direction: source.sort.direction === "asc" ? "asc" : "desc" }
      : null;
  const columnFilters = Array.isArray(source.columnFilters)
    ? source.columnFilters.flatMap((filter) => {
        if (typeof filter !== "object" || filter === null) {
          return [];
        }
        const candidate = filter as Partial<CandidateGridColumnFilter>;
        const field = normalizeCandidateColumnKey(candidate.field ?? null);
        if (!field || !filterableCandidateColumns.has(field)) {
          return [];
        }
        const value = typeof candidate.value === "string" ? candidate.value : "";
        const operator = typeof candidate.operator === "string" && candidate.operator.trim()
          ? candidate.operator
          : "contains";
        return [{ field, operator, value }];
      })
    : [];
  return {
    sort,
    columnFilters,
    quickFilter: typeof source.quickFilter === "string" ? source.quickFilter : ""
  };
}

function setTrimmed(params: URLSearchParams, key: string, value: string) {
  const trimmed = value.trim();
  if (trimmed) {
    params.set(key, trimmed);
  }
}

function datetimeLocalToIso(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) {
    return trimmed;
  }
  return date.toISOString();
}

function isoToDatetimeLocal(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) {
    return trimmed;
  }
  return dateToDatetimeLocal(date);
}

function dateToDatetimeLocal(date: Date): string {
  const localOffset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - localOffset).toISOString().slice(0, 16);
}

function optionsToLabelMap(options: AnalyticsAggregate[]): Map<string, string> {
  return new Map(options.map((option) => [option.key, option.label || option.key]));
}

function filterValueLabel(key: keyof CandidateFilters, value: string): string {
  if (key === "receivedFrom" || key === "receivedTo") {
    return value.replace("T", " ");
  }
  if (value === "true") {
    return "да";
  }
  if (value === "false") {
    return "нет";
  }
  return value;
}
