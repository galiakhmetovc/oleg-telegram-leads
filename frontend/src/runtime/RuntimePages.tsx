import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography
} from "@mui/material";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type RuntimePageProps = {
  apiBaseUrl: string;
};

type RuntimeLogEntry = {
  created_at: string;
  service: string;
  level: string;
  message: string;
  payload: Record<string, unknown>;
};

type RuntimeLogsResponse = {
  items: RuntimeLogEntry[];
  total: number;
  limit: number;
  offset: number;
};

type RuntimeLogFilters = {
  service: string;
  level: string;
  q: string;
  createdFrom: string;
  createdTo: string;
};

type ServiceStatusItem = {
  service: string;
  status: string;
  details: Record<string, unknown>;
};

type ProjectDocumentSummary = {
  path: string;
  title: string;
  size_bytes: number;
  updated_at: string;
};

type ProjectDocumentContent = ProjectDocumentSummary & {
  content: string;
};

export function RuntimeLogsPage({ apiBaseUrl }: RuntimePageProps) {
  const [items, setItems] = useState<RuntimeLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<RuntimeLogFilters>({
    service: "",
    level: "",
    q: "",
    createdFrom: "",
    createdTo: ""
  });
  const [appliedFilters, setAppliedFilters] = useState<RuntimeLogFilters>({
    service: "",
    level: "",
    q: "",
    createdFrom: "",
    createdTo: ""
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/runtime/logs?${runtimeLogsQuery({
        limit,
        offset,
        filters: appliedFilters
      })}`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as RuntimeLogsResponse;
      setItems(payload.items);
      setTotal(payload.total);
      setLimit(payload.limit);
      setOffset(payload.offset);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить логи");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, appliedFilters, limit, offset]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  function applyRuntimeLogFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setAppliedFilters(filters);
  }

  function resetRuntimeLogFilters() {
    const next = { service: "", level: "", q: "", createdFrom: "", createdTo: "" };
    setFilters(next);
    setAppliedFilters(next);
    setOffset(0);
  }

  function handleLogPageChange(_: unknown, nextPage: number) {
    setOffset(nextPage * limit);
  }

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" className="runtime-header">
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <Box>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              Логи
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Последние события backend, userbot, worker, enrichment dispatcher и notification dispatcher.
            </Typography>
          </Box>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadLogs()} disabled={loading}>
            Обновить
          </Button>
        </Stack>
      </Paper>
      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      <Paper variant="outlined" className="runtime-panel">
        <Stack
          component="form"
          className="runtime-log-filters"
          direction={{ xs: "column", md: "row" }}
          spacing={1}
          onSubmit={applyRuntimeLogFilters}
        >
          <TextField
            select
            size="small"
            label="Сервис"
            value={filters.service}
            onChange={(event) => setFilters((current) => ({ ...current, service: event.target.value }))}
            sx={{ minWidth: { md: 210 } }}
          >
            <MenuItem value="">Все</MenuItem>
            <MenuItem value="userbot">userbot</MenuItem>
            <MenuItem value="worker">worker</MenuItem>
            <MenuItem value="enrichment-dispatcher">enrichment-dispatcher</MenuItem>
            <MenuItem value="notification-dispatcher">notification-dispatcher</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Уровень"
            value={filters.level}
            onChange={(event) => setFilters((current) => ({ ...current, level: event.target.value }))}
            sx={{ minWidth: { md: 140 } }}
          >
            <MenuItem value="">Все</MenuItem>
            <MenuItem value="info">info</MenuItem>
            <MenuItem value="error">error</MenuItem>
          </TextField>
          <TextField
            size="small"
            label="Поиск"
            value={filters.q}
            onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
            sx={{ minWidth: { md: 220 } }}
          />
          <TextField
            size="small"
            label="С"
            type="datetime-local"
            value={filters.createdFrom}
            onChange={(event) => setFilters((current) => ({ ...current, createdFrom: event.target.value }))}
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ minWidth: { md: 200 } }}
          />
          <TextField
            size="small"
            label="По"
            type="datetime-local"
            value={filters.createdTo}
            onChange={(event) => setFilters((current) => ({ ...current, createdTo: event.target.value }))}
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ minWidth: { md: 200 } }}
          />
          <Button type="submit" variant="contained" disabled={loading}>
            Применить фильтры
          </Button>
          <Button type="button" variant="outlined" onClick={resetRuntimeLogFilters} disabled={loading}>
            Сбросить
          </Button>
        </Stack>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Время</TableCell>
                <TableCell>Сервис</TableCell>
                <TableCell>Уровень</TableCell>
                <TableCell>Сообщение</TableCell>
                <TableCell>Данные</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item, index) => (
                <TableRow key={`${item.created_at}-${item.service}-${index}`}>
                  <TableCell>{formatDateTime(item.created_at)}</TableCell>
                  <TableCell>{item.service}</TableCell>
                  <TableCell>
                    <Chip size="small" color={item.level === "error" ? "error" : "default"} label={item.level} />
                  </TableCell>
                  <TableCell>{item.message}</TableCell>
                  <TableCell className="runtime-payload">{JSON.stringify(item.payload)}</TableCell>
                </TableRow>
              ))}
              {!loading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>Логов пока нет.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={total}
          page={Math.floor(offset / limit)}
          rowsPerPage={limit}
          rowsPerPageOptions={[limit]}
          labelRowsPerPage="Строк на странице"
          labelDisplayedRows={({ from, to, count }) =>
            `${formatInteger(from)}-${formatInteger(to)} из ${formatInteger(count)}`
          }
          onPageChange={handleLogPageChange}
          getItemAriaLabel={(type) => {
            if (type === "next") {
              return "Следующая страница";
            }
            if (type === "previous") {
              return "Предыдущая страница";
            }
            if (type === "first") {
              return "Первая страница";
            }
            return "Последняя страница";
          }}
        />
      </Paper>
    </Stack>
  );
}

function runtimeLogsQuery({
  limit,
  offset,
  filters
}: {
  limit: number;
  offset: number;
  filters: RuntimeLogFilters;
}): string {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (filters.service) {
    params.set("service", filters.service);
  }
  if (filters.level) {
    params.set("level", filters.level);
  }
  if (filters.q.trim()) {
    params.set("q", filters.q.trim());
  }
  if (filters.createdFrom) {
    params.set("created_from", new Date(filters.createdFrom).toISOString());
  }
  if (filters.createdTo) {
    params.set("created_to", new Date(filters.createdTo).toISOString());
  }
  return params.toString();
}

export function SystemStatusPage({ apiBaseUrl }: RuntimePageProps) {
  const [services, setServices] = useState<ServiceStatusItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const backendService = useMemo(() => services.find((service) => service.service === "backend") ?? null, [services]);
  const workerService = useMemo(() => services.find((service) => service.service === "worker") ?? null, [services]);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/runtime/status`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as { services: ServiceStatusItem[] };
      setServices(payload.services);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить статус системы");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" className="runtime-header">
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <Box>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              Статус системы
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Основные runtime-компоненты и счетчики ошибок/очередей.
            </Typography>
          </Box>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadStatus()} disabled={loading}>
            Обновить
          </Button>
        </Stack>
      </Paper>
      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      <SystemFreshnessPanel backend={backendService} worker={workerService} />
      <Box className="system-status-grid">
        {services.map((service) => (
          <Paper key={service.service} variant="outlined" className="system-status-card">
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  {service.service}
                </Typography>
                <Chip size="small" color={statusColor(service.status)} label={service.status} />
              </Stack>
              <SystemStatusDetails details={service.details} />
            </Stack>
          </Paper>
        ))}
      </Box>
    </Stack>
  );
}

function SystemFreshnessPanel({
  backend,
  worker
}: {
  backend: ServiceStatusItem | null;
  worker: ServiceStatusItem | null;
}) {
  if (!backend && !worker) {
    return null;
  }
  const activeRevision = detailNumber(backend?.details.active_nlp_config_revision);
  const workerRevision = detailNumber(worker?.details.latest_worker_nlp_config_revision);
  const backendCodeVersion = stringDetail(
    worker?.details.backend_code_version ?? backend?.details.code_version
  );
  const workerCodeVersion = stringDetail(worker?.details.latest_worker_code_version);
  const workerConfigStale = worker?.details.worker_config_stale === true;
  const workerCodeStale = worker?.details.worker_code_stale === true;

  return (
    <Paper variant="outlined" className="runtime-panel">
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="h6" component="h3" sx={{ fontWeight: 700 }}>
            Свежесть правил и кода
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Контроль того, какой ревизией NLP-настроек и какой версией кода реально работает worker.
          </Typography>
        </Box>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ flexWrap: "wrap" }}>
          <StatusMetric label="Активная NLP-ревизия" value={formatRevision(activeRevision)} />
          <StatusMetric label="Последняя ревизия worker" value={formatRevision(workerRevision)} />
          <StatusMetric label="Backend code" value={backendCodeVersion ?? "нет данных"} />
          <StatusMetric label="Worker code" value={workerCodeVersion ?? "нет данных"} />
        </Stack>
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
          <Chip
            size="small"
            color={workerConfigStale ? "warning" : "success"}
            label={workerConfigStale ? "Worker еще не обработал активную ревизию" : "Worker использует активную ревизию"}
          />
          <Chip
            size="small"
            color={workerCodeStale ? "warning" : "success"}
            label={workerCodeStale ? "Код worker отличается от backend" : "Код worker актуален"}
          />
        </Stack>
      </Stack>
    </Paper>
  );
}

function StatusMetric({ label, value }: { label: string; value: string }) {
  return (
    <Box className="system-status-detail-row" sx={{ minWidth: { md: 190 } }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
    </Box>
  );
}

function SystemStatusDetails({ details }: { details: Record<string, unknown> }) {
  const rows = Object.entries(details);
  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет дополнительных данных.
      </Typography>
    );
  }
  return (
    <Stack spacing={0.75}>
      {rows.map(([key, value]) => (
        <Box key={key} className="system-status-detail-row">
          <Typography variant="caption" color="text.secondary">
            {systemStatusDetailLabel(key)}
          </Typography>
          <Typography variant="body2" className={systemStatusDetailClass(value)}>
            {formatSystemStatusDetail(value)}
          </Typography>
        </Box>
      ))}
    </Stack>
  );
}

export function ProjectDocumentationPage({ apiBaseUrl }: RuntimePageProps) {
  const [items, setItems] = useState<ProjectDocumentSummary[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [document, setDocument] = useState<ProjectDocumentContent | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDocument, setLoadingDocument] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groupedItems = useMemo(() => groupProjectDocuments(items), [items]);

  const loadDocuments = useCallback(async () => {
    setLoadingList(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/project-docs`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as { items: ProjectDocumentSummary[] };
      setItems(payload.items);
      setSelectedPath((current) => current ?? payload.items[0]?.path ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить список документов");
    } finally {
      setLoadingList(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!selectedPath) {
      setDocument(null);
      return;
    }

    let active = true;
    const pathToLoad = selectedPath;
    async function loadDocument() {
      setLoadingDocument(true);
      setError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/project-docs/${encodeDocumentPath(pathToLoad)}`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const payload = (await response.json()) as ProjectDocumentContent;
        if (active) {
          setDocument(payload);
        }
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Не удалось загрузить документ");
        }
      } finally {
        if (active) {
          setLoadingDocument(false);
        }
      }
    }

    void loadDocument();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedPath]);

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" className="project-docs-header">
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <Box>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              Проектная документация
            </Typography>
            <Typography variant="body2" color="text.secondary">
              README, AGENTS, docs, notes и state из текущего worktree.
            </Typography>
          </Box>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDocuments()} disabled={loadingList}>
            Обновить
          </Button>
        </Stack>
      </Paper>
      {(loadingList || loadingDocument) && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      <Box className="project-docs-shell">
        <Paper variant="outlined" className="project-docs-sidebar">
          <Stack spacing={1.5}>
            {groupedItems.map((group) => (
              <Box key={group.label}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, textTransform: "uppercase" }}>
                  {group.label}
                </Typography>
                <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                  {group.items.map((item) => (
                    <Button
                      key={item.path}
                      variant={selectedPath === item.path ? "contained" : "text"}
                      color={selectedPath === item.path ? "primary" : "inherit"}
                      className="project-docs-file-button"
                      onClick={() => setSelectedPath(item.path)}
                    >
                      <Box component="span" sx={{ minWidth: 0, textAlign: "left" }}>
                        <Typography component="span" variant="body2" sx={{ display: "block", fontWeight: 700 }}>
                          {item.path}
                        </Typography>
                        <Typography component="span" variant="caption" sx={{ display: "block" }}>
                          {item.title}
                        </Typography>
                      </Box>
                    </Button>
                  ))}
                </Stack>
              </Box>
            ))}
            {!loadingList && items.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                Документы не найдены.
              </Typography>
            )}
          </Stack>
        </Paper>
        <Paper variant="outlined" className="project-docs-reader">
          {document ? (
            <Stack spacing={2}>
              <Box>
                <Typography variant="h5" component="h3" sx={{ fontWeight: 700 }}>
                  {document.title}
                </Typography>
                <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", mt: 1 }}>
                  <Chip size="small" label={document.path} />
                  <Chip size="small" label={`${document.size_bytes} bytes`} />
                  <Chip size="small" label={formatDateTime(document.updated_at)} />
                </Stack>
              </Box>
              <Divider />
              <MarkdownPreview content={document.content} />
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Выберите файл документации.
            </Typography>
          )}
        </Paper>
      </Box>
    </Stack>
  );
}

function groupProjectDocuments(items: ProjectDocumentSummary[]): { label: string; items: ProjectDocumentSummary[] }[] {
  const labels = new Map<string, ProjectDocumentSummary[]>();
  for (const item of items) {
    const root = item.path.includes("/") ? item.path.split("/")[0] : "Корень";
    const label = root === "docs" ? "docs" : root === "state" ? "state" : root === "notes" ? "notes" : "Корень";
    labels.set(label, [...(labels.get(label) ?? []), item]);
  }

  return ["Корень", "docs", "notes", "state"]
    .map((label) => ({ label, items: labels.get(label) ?? [] }))
    .filter((group) => group.items.length > 0);
}

function encodeDocumentPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

function MarkdownPreview({ content }: { content: string }) {
  return (
    <Box className="project-docs-markdown">
      {content.split("\n").map((line, index) => {
        const key = `${index}-${line.slice(0, 12)}`;
        const trimmed = line.trim();
        if (trimmed === "") {
          return <Box key={key} sx={{ height: 8 }} />;
        }
        if (trimmed.startsWith("### ")) {
          return (
            <Typography key={key} variant="h6" component="h4">
              {trimmed.replace(/^###\s+/, "")}
            </Typography>
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <Typography key={key} variant="h6" component="h3" sx={{ fontWeight: 700 }}>
              {trimmed.replace(/^##\s+/, "")}
            </Typography>
          );
        }
        if (trimmed.startsWith("# ")) {
          return (
            <Typography key={key} variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              {trimmed.replace(/^#\s+/, "")}
            </Typography>
          );
        }
        if (trimmed.startsWith("- ")) {
          return (
            <Typography key={key} component="li" variant="body2">
              {trimmed.replace(/^-\s+/, "")}
            </Typography>
          );
        }
        if (/^\d+\.\s+/.test(trimmed)) {
          return (
            <Typography key={key} component="li" variant="body2">
              {trimmed.replace(/^\d+\.\s+/, "")}
            </Typography>
          );
        }
        return (
          <Typography key={key} variant="body2">
            {line}
          </Typography>
        );
      })}
    </Box>
  );
}

function statusColor(status: string): "default" | "success" | "warning" | "error" {
  if (status === "ok") {
    return "success";
  }
  if (status === "warning") {
    return "warning";
  }
  if (status === "error") {
    return "error";
  }
  return "default";
}

const systemStatusDetailLabels: Record<string, string> = {
  accounts_enabled: "Аккаунтов включено",
  accounts_in_cooldown: "Аккаунтов в cooldown",
  accounts_total: "Аккаунтов всего",
  account_errors: "Ошибки аккаунтов",
  auth_enabled: "Авторизация",
  database_ok: "PostgreSQL ping",
  enrichment_events_retained: "Записей журнала worker, не лидов",
  environment: "Окружение",
  errored_sources: "Проблемные источники",
  failed_latest_error: "Последняя ошибка",
  jobs_by_status: "Задачи по статусам",
  jobs_total: "Задач всего",
  latest_event_at: "Последнее событие worker",
  latest_job_created_at: "Последняя задача",
  latest_message_at: "Последнее сообщение",
  latest_notification_at: "Последнее уведомление",
  latest_task_published_at: "Последняя задача отправлена в worker",
  messages_total: "Сообщений принято",
  next_cooldown_until: "Ближайший cooldown до",
  oldest_pending_at: "Самое старое ожидающее",
  oldest_task_pending_at: "Старая задача ждет отправки",
  outbox_by_status: "Уведомления по статусам",
  outbox_total: "Уведомлений всего",
  public_base_url: "Публичный URL",
  redis_ok: "Redis ping",
  source_chats_by_status: "Чаты по статусам",
  source_chats_enabled: "Чатов включено",
  source_chats_total: "Чатов-источников",
  status_checked_at: "Проверено",
  stale_task_sending: "Зависшие отправки задач",
  task_outbox_by_status: "Задачи на отправку по статусам",
  task_outbox_total: "Задач на отправку всего",
  task_publish_latest_error: "Последняя ошибка отправки задач",
  telegram_messages_enriched: "Сообщений видно в аналитике",
  telegram_messages_failed_enrichment: "Сообщений с ошибкой enrichment",
  telegram_messages_waiting_enrichment: "Сообщений ждут enrichment",
  active_nlp_config_revision: "Активная NLP-ревизия",
  active_nlp_config_revision_id: "ID активной NLP-ревизии",
  backend_code_version: "Версия кода backend",
  code_version: "Версия кода",
  latest_worker_code_version: "Версия кода worker",
  latest_worker_nlp_config_revision: "Последняя NLP-ревизия worker",
  latest_worker_nlp_config_revision_id: "ID последней NLP-ревизии worker",
  process_role: "Роль процесса",
  worker_code_stale: "Код worker устарел",
  worker_config_stale: "Worker отстал от активной ревизии"
};

function systemStatusDetailLabel(key: string): string {
  return systemStatusDetailLabels[key] ?? key;
}

function systemStatusDetailClass(value: unknown): string | undefined {
  if (typeof value === "object" && value !== null) {
    return "runtime-payload";
  }
  return undefined;
}

function formatSystemStatusDetail(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "нет данных";
  }
  if (typeof value === "boolean") {
    return value ? "да" : "нет";
  }
  if (typeof value === "number") {
    return formatInteger(value);
  }
  if (typeof value === "string") {
    return formatMaybeDate(value);
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "нет";
    }
    return value.map((item) => formatSystemStatusArrayItem(item)).join("; ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${formatSystemStatusDetail(item)}`)
      .join(", ");
  }
  return String(value);
}

function formatSystemStatusArrayItem(value: unknown): string {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return formatSystemStatusDetail(value);
  }
  const item = value as Record<string, unknown>;
  const title = item.title ?? item.service ?? item.id ?? item.source_chat_id;
  const error = item.last_error ?? item.error;
  if (title && error) {
    return `${formatSystemStatusDetail(title)}: ${formatSystemStatusDetail(error)}`;
  }
  return formatSystemStatusDetail(item);
}

function formatMaybeDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return value;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return formatDateTime(value);
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium"
  }).format(new Date(value));
}

function detailNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringDetail(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function formatRevision(value: number | null): string {
  return value === null ? "нет данных" : `#${value}`;
}
