import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  CircularProgress,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography
} from "@mui/material";
import { Fragment, useEffect, useState } from "react";

type LlmVerificationRun = {
  id: string;
  source_message_id: string;
  enrichment_job_id: string;
  model: string;
  route_id?: string | null;
  schema_version: string;
  status: string;
  prompt?: string | null;
  attempts?: number;
  context_pack: Record<string, unknown>;
  response: Record<string, unknown> | null;
  raw_response: string | null;
  error: string | null;
  claimed_at?: string | null;
  created_at: string;
  updated_at: string;
};

type LlmVerificationPageResponse = {
  total: number;
  items: LlmVerificationRun[];
};

export function LlmPage({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [runs, setRuns] = useState<LlmVerificationRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);

  async function loadRuns() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/llm-verifications?limit=50&offset=0`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as LlmVerificationPageResponse;
      setRuns(payload.items ?? []);
      setTotal(payload.total ?? payload.items?.length ?? 0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить LLM-проверки");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRuns();
  }, []);

  return (
    <Box className="analytics-shell">
      <Paper variant="outlined" className="analytics-header">
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <Box>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 760 }}>
              LLM
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Очередь и результаты дополнительной проверки сообщений локальной моделью.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Chip label={`${total} запусков`} variant="outlined" />
            <Button
              variant="outlined"
              startIcon={loading ? <CircularProgress size={18} /> : <RefreshIcon />}
              disabled={loading}
              onClick={() => void loadRuns()}
            >
              Обновить
            </Button>
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" className="analytics-section">
        <Stack spacing={1.5}>
          {loading && <LinearProgress />}
          {error && <Alert severity="error">{error}</Alert>}
          {runs.length === 0 && !loading ? (
            <Typography variant="body2" color="text.secondary">
              LLM-проверок пока нет.
            </Typography>
          ) : (
            <TableContainer>
              <Table size="small" aria-label="LLM verifications">
                <TableHead>
                  <TableRow>
                    <TableCell>Время</TableCell>
                    <TableCell>Статус</TableCell>
                    <TableCell>Модель</TableCell>
                    <TableCell>Маршрут</TableCell>
                    <TableCell>Ответ модели</TableCell>
                    <TableCell>Сообщение</TableCell>
                    <TableCell>Связь</TableCell>
                    <TableCell>Детали</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {runs.map((run) => {
                    const expanded = expandedRunId === run.id;
                    return (
                      <Fragment key={run.id}>
                        <TableRow key={run.id} hover>
                          <TableCell>{formatDateTime(run.created_at)}</TableCell>
                          <TableCell>
                            <Chip size="small" label={run.status} color={statusColor(run.status)} />
                          </TableCell>
                          <TableCell>{run.model}</TableCell>
                          <TableCell>{run.route_id ?? "manual"}</TableCell>
                          <TableCell>
                            <LlmResponseSummary run={run} />
                          </TableCell>
                          <TableCell sx={{ maxWidth: 520 }}>
                            <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                              {runMessageText(run)}
                            </Typography>
                            {run.error && (
                              <Typography variant="caption" color="error" sx={{ overflowWrap: "anywhere" }}>
                                {run.error}
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
                              message {run.source_message_id}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>
                              job {run.enrichment_job_id}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Button
                              size="small"
                              variant="text"
                              aria-label={`${expanded ? "Скрыть" : "Показать"} детали LLM run ${run.id}`}
                              onClick={() => setExpandedRunId(expanded ? null : run.id)}
                            >
                              {expanded ? "Скрыть" : "Показать"}
                            </Button>
                          </TableCell>
                        </TableRow>
                        <TableRow key={`${run.id}-details`}>
                          <TableCell colSpan={8} sx={{ py: 0 }}>
                            <Collapse in={expanded} timeout="auto" unmountOnExit>
                              <Stack spacing={1.25} sx={{ py: 1.5 }}>
                                <JsonBlock title="System prompt" value={run.prompt ?? "Промпт не сохранен для этого run"} />
                                <JsonBlock title="Отдано модели: context_pack" value={run.context_pack} />
                                <JsonBlock title="Очищенный response" value={run.response} />
                                <NetworkResponseBlock rawResponse={run.raw_response} />
                              </Stack>
                            </Collapse>
                          </TableCell>
                        </TableRow>
                      </Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Stack>
      </Paper>
    </Box>
  );
}

function LlmResponseSummary({ run }: { run: LlmVerificationRun }) {
  const response = run.response ?? parseJsonObject(run.raw_response);
  const verdict = stringValue(response?.verdict) ?? "нет verdict";
  const confidence = response?.confidence;
  return (
    <Stack spacing={0.5}>
      <Chip size="small" label={verdict} color={verdict === "lead" ? "success" : verdict === "not_lead" ? "default" : "warning"} />
      {typeof confidence === "number" && (
        <Typography variant="caption" color="text.secondary">
          confidence {confidence}
        </Typography>
      )}
    </Stack>
  );
}

function NetworkResponseBlock({ rawResponse }: { rawResponse: string | null }) {
  const parsed = parseJsonObject(rawResponse);
  return (
    <Box className="llm-json-block">
      <Typography variant="caption" color="text.secondary">
        Сетевой ответ модели
      </Typography>
      {parsed ? (
        <TableContainer>
          <Table size="small" aria-label="Сетевой ответ модели">
            <TableHead>
              <TableRow>
                <TableCell>Поле</TableCell>
                <TableCell>Значение</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(parsed).map(([key, value]) => (
                <TableRow key={key}>
                  <TableCell>{key}</TableCell>
                  <TableCell>
                    <Box component="pre" className="llm-json-pre">
                      {prettyJson(value)}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">
          JSON не распознан, смотри raw_response ниже.
        </Typography>
      )}
      <JsonBlock title="raw_response" value={rawResponse ?? ""} />
    </Box>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <Box className="llm-json-block">
      <Typography variant="caption" color="text.secondary">
        {title}
      </Typography>
      <Box component="pre" className="llm-json-pre">
        {prettyJson(value)}
      </Box>
    </Box>
  );
}

function prettyJson(value: unknown): string {
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}

function parseJsonObject(value: unknown): Record<string, unknown> | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function runMessageText(run: LlmVerificationRun): string {
  const message = run.context_pack.message as { text?: unknown } | undefined;
  return typeof message?.text === "string" ? message.text : "Текст не найден в context_pack";
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium"
  }).format(new Date(value));
}

function statusColor(status: string): "success" | "warning" | "error" | "default" {
  if (status === "completed") {
    return "success";
  }
  if (status === "queued" || status === "running") {
    return "warning";
  }
  if (status === "failed") {
    return "error";
  }
  return "default";
}
