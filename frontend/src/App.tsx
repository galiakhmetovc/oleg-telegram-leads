import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  CssBaseline,
  Divider,
  LinearProgress,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  ThemeProvider,
  Toolbar,
  Typography,
  createTheme
} from "@mui/material";
import { FormEvent, SyntheticEvent, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

type TextRange = {
  start: number;
  stop: number;
};

type SpanItem = {
  id: string;
  text: string;
  type: string;
  label?: string;
  range: TextRange;
  source: string;
  confidence?: number | null;
  color?: string | null;
};

type EnrichedToken = {
  id: string;
  text: string;
  lemma?: string | null;
  pos?: string | null;
  range: TextRange;
  features: Record<string, string>;
};

type SyntaxDependency = {
  token_id: string;
  head_id?: string | null;
  relation?: string | null;
};

type PipelineTraceItem = {
  stage: string;
  status: string;
  message: string;
  progress_percent: number;
};

type TextEnrichmentResult = {
  original_text: string;
  normalized_text: string;
  entities: SpanItem[];
  facts: SpanItem[];
  domain_signals: SpanItem[];
  tokens: EnrichedToken[];
  syntax: SyntaxDependency[];
  metrics: Record<string, number>;
  pipeline_trace: PipelineTraceItem[];
};

type EnrichmentJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress_percent: number;
  current_stage?: string | null;
  stage_index: number;
  stage_count: number;
  stage_progress_percent: number;
  message: string;
  result?: TextEnrichmentResult | null;
  error?: { type?: string; message?: string } | null;
};

type EnrichmentEvent = {
  event_type: string;
  progress_percent: number;
  current_stage?: string | null;
  stage_index: number;
  stage_count: number;
  stage_progress_percent: number;
  message: string;
  payload?: {
    result?: TextEnrichmentResult;
    error?: { type?: string; message?: string };
  };
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#0b57d0"
    },
    background: {
      default: "#f6f8fb"
    }
  },
  shape: {
    borderRadius: 8
  },
  typography: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
  }
});

export function App() {
  const [inputText, setInputText] = useState(
    "Ищем поставщика в Москве. Нужно 20 тонн до 12 мая, желательно с НДС."
  );
  const [job, setJob] = useState<EnrichmentJob | null>(null);
  const [events, setEvents] = useState<EnrichmentEvent[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  const result = job?.result ?? null;
  const isProcessing = isSubmitting || job?.status === "queued" || job?.status === "running";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = inputText.trim();
    if (!text) {
      setError("Введите текст для анализа");
      return;
    }

    eventSourceRef.current?.close();
    setIsSubmitting(true);
    setError(null);
    setEvents([]);
    setJob(null);
    setActiveTab(0);

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/enrichments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const createdJob = (await response.json()) as EnrichmentJob;
      setJob(createdJob);
      connectToEvents(createdJob.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось запустить обработку");
    } finally {
      setIsSubmitting(false);
    }
  }

  function connectToEvents(jobId: string) {
    const source = new EventSource(`${apiBaseUrl}/api/v1/enrichments/${jobId}/events`);
    eventSourceRef.current = source;

    const handleEvent = (message: MessageEvent<string>) => {
      const parsed = JSON.parse(message.data) as EnrichmentEvent;
      setEvents((current) => [parsed, ...current].slice(0, 20));
      setJob((current) => {
        if (current === null) {
          return current;
        }
        const next: EnrichmentJob = {
          ...current,
          status:
            parsed.event_type === "job_completed"
              ? "completed"
              : parsed.event_type === "job_failed"
                ? "failed"
                : "running",
          progress_percent: parsed.progress_percent,
          current_stage: parsed.current_stage,
          stage_index: parsed.stage_index,
          stage_count: parsed.stage_count,
          stage_progress_percent: parsed.stage_progress_percent,
          message: parsed.message,
          result: parsed.payload?.result ?? current.result,
          error: parsed.payload?.error ?? current.error
        };
        return next;
      });

      if (parsed.event_type === "job_completed" || parsed.event_type === "job_failed") {
        source.close();
        void refreshSnapshot(jobId);
      }
    };

    for (const eventName of [
      "job_queued",
      "job_started",
      "stage_completed",
      "job_completed",
      "job_failed"
    ]) {
      source.addEventListener(eventName, handleEvent);
    }

    source.onerror = () => {
      setError("SSE-соединение прервано");
      source.close();
    };
  }

  async function refreshSnapshot(jobId: string) {
    const response = await fetch(`${apiBaseUrl}/api/v1/enrichments/${jobId}`);
    if (response.ok) {
      setJob((await response.json()) as EnrichmentJob);
    }
  }

  function handleTabChange(_: SyntheticEvent, value: number) {
    setActiveTab(value);
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box className="app-shell">
        <AppBar position="static" color="default" elevation={0} className="top-bar">
          <Toolbar variant="dense">
            <AutoAwesomeIcon color="primary" fontSize="small" />
            <Typography variant="subtitle1" component="h1" sx={{ ml: 1, fontWeight: 700 }}>
              PUR Leads v2 - обогащение текста
            </Typography>
          </Toolbar>
        </AppBar>

        <Container maxWidth={false} className="workspace">
          <Box className="workspace-grid">
            <Paper component="form" onSubmit={handleSubmit} className="input-panel" variant="outlined">
              <Stack spacing={2}>
                <Typography variant="h6">Входной текст</Typography>
                <TextField
                  value={inputText}
                  onChange={(event) => setInputText(event.target.value)}
                  multiline
                  minRows={16}
                  fullWidth
                  label="Произвольный текст"
                  slotProps={{ htmlInput: { "aria-label": "Текст для обогащения" } }}
                />
                <Button
                  type="submit"
                  variant="contained"
                  startIcon={isProcessing ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />}
                  disabled={isProcessing}
                >
                  Запустить обогащение
                </Button>
                {error && (
                  <Alert severity="error" icon={<ErrorIcon />}>
                    {error}
                  </Alert>
                )}
              </Stack>
            </Paper>

            <Stack spacing={2} className="result-panel">
              <StatusPanel job={job} events={events} isSubmitting={isSubmitting} />
              {result ? (
                <Paper variant="outlined" className="result-card">
                  <Tabs value={activeTab} onChange={handleTabChange} variant="scrollable">
                    <Tab label="Обзор" />
                    <Tab label="Сущности" />
                    <Tab label="Факты" />
                    <Tab label="Сигналы" />
                    <Tab label="Токены" />
                    <Tab label="Синтаксис" />
                    <Tab label="Trace" />
                  </Tabs>
                  <Divider />
                  <Box className="tab-body">
                    {activeTab === 0 && <Overview result={result} />}
                    {activeTab === 1 && <SpanTable items={result.entities} fallbackLabel="Сущность" />}
                    {activeTab === 2 && <SpanTable items={result.facts} fallbackLabel="Факт" />}
                    {activeTab === 3 && <SpanTable items={result.domain_signals} fallbackLabel="Сигнал" />}
                    {activeTab === 4 && <TokenTable tokens={result.tokens} />}
                    {activeTab === 5 && <SyntaxTable syntax={result.syntax} />}
                    {activeTab === 6 && <TraceTable trace={result.pipeline_trace} />}
                  </Box>
                </Paper>
              ) : (
                <Paper variant="outlined" className="empty-result">
                  <Typography variant="body2" color="text.secondary">
                    Результат появится после завершения backend pipeline.
                  </Typography>
                </Paper>
              )}
            </Stack>
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

function StatusPanel({
  job,
  events,
  isSubmitting
}: {
  job: EnrichmentJob | null;
  events: EnrichmentEvent[];
  isSubmitting: boolean;
}) {
  const progress = job?.progress_percent ?? (isSubmitting ? 2 : 0);
  const statusLabel = job ? job.status : isSubmitting ? "queued" : "idle";

  return (
    <Paper variant="outlined" className="status-panel">
      <Stack spacing={1.5}>
        <Box
          sx={{
            alignItems: "center",
            display: "flex",
            gap: 2,
            justifyContent: "space-between"
          }}
        >
          <Box sx={{ alignItems: "center", display: "flex", gap: 1 }}>
            {job?.status === "completed" ? (
              <CheckCircleIcon color="success" />
            ) : job?.status === "failed" ? (
              <ErrorIcon color="error" />
            ) : (
              <CircularProgress size={20} />
            )}
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Статус: {statusLabel}
            </Typography>
          </Box>
          <Chip label={`${progress}%`} color={job?.status === "failed" ? "error" : "primary"} size="small" />
        </Box>
        <LinearProgress variant="determinate" value={progress} />
        <Typography variant="body2">
          {job?.message ?? "Backend ожидает текст для обработки"}
        </Typography>
        {job && (
          <Typography variant="caption" color="text.secondary">
            Этап: {job.current_stage ?? "не начат"}; {job.stage_index}/{job.stage_count}; этап выполнен на{" "}
            {job.stage_progress_percent}%
          </Typography>
        )}
        {events.length > 0 && (
          <Stack spacing={0.5} className="event-list">
            {events.slice(0, 5).map((event) => (
              <Typography key={`${event.event_type}-${event.progress_percent}-${event.message}`} variant="caption">
                {event.progress_percent}% - {event.message}
              </Typography>
            ))}
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}

function Overview({ result }: { result: TextEnrichmentResult }) {
  return (
    <Stack spacing={2}>
      <AnnotatedText result={result} />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {Object.entries(result.metrics).map(([key, value]) => (
          <Chip key={key} label={`${key}: ${value}`} variant="outlined" />
        ))}
      </Box>
    </Stack>
  );
}

function AnnotatedText({ result }: { result: TextEnrichmentResult }) {
  const spans = useMemo(() => collectNonOverlappingSpans(result), [result]);
  const parts: ReactNode[] = [];
  let cursor = 0;

  for (const span of spans) {
    if (span.range.start > cursor) {
      parts.push(<span key={`text-${cursor}`}>{result.original_text.slice(cursor, span.range.start)}</span>);
    }
    parts.push(
      <mark
        key={span.id}
        className="annotation"
        style={{ borderColor: span.color ?? "#0b57d0", backgroundColor: `${span.color ?? "#0b57d0"}1a` }}
        title={`${span.label ?? span.type}: ${span.source}`}
      >
        {result.original_text.slice(span.range.start, span.range.stop)}
      </mark>
    );
    cursor = span.range.stop;
  }

  if (cursor < result.original_text.length) {
    parts.push(<span key={`text-${cursor}`}>{result.original_text.slice(cursor)}</span>);
  }

  return (
    <Box className="annotated-text">
      <Typography component="div" variant="body1">
        {parts}
      </Typography>
    </Box>
  );
}

function collectNonOverlappingSpans(result: TextEnrichmentResult): SpanItem[] {
  const allSpans = [
    ...result.entities.map((item) => ({ ...item, label: item.label ?? item.type })),
    ...result.facts,
    ...result.domain_signals
  ].sort((left, right) => left.range.start - right.range.start || right.range.stop - left.range.stop);
  const accepted: SpanItem[] = [];
  let cursor = -1;
  for (const span of allSpans) {
    if (span.range.start >= cursor) {
      accepted.push(span);
      cursor = span.range.stop;
    }
  }
  return accepted;
}

function SpanTable({ items, fallbackLabel }: { items: SpanItem[]; fallbackLabel: string }) {
  if (items.length === 0) {
    return <Typography color="text.secondary">Нет данных</Typography>;
  }
  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{fallbackLabel}</TableCell>
            <TableCell>Тип</TableCell>
            <TableCell>Источник</TableCell>
            <TableCell>Позиция</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>{item.text}</TableCell>
              <TableCell>{item.label ?? item.type}</TableCell>
              <TableCell>{item.source}</TableCell>
              <TableCell>
                {item.range.start}-{item.range.stop}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function TokenTable({ tokens }: { tokens: EnrichedToken[] }) {
  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Токен</TableCell>
            <TableCell>Лемма</TableCell>
            <TableCell>POS</TableCell>
            <TableCell>Признаки</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {tokens.map((token) => (
            <TableRow key={token.id}>
              <TableCell>{token.text}</TableCell>
              <TableCell>{token.lemma ?? ""}</TableCell>
              <TableCell>{token.pos ?? ""}</TableCell>
              <TableCell>{Object.entries(token.features).map(([key, value]) => `${key}=${value}`).join(", ")}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function SyntaxTable({ syntax }: { syntax: SyntaxDependency[] }) {
  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Token ID</TableCell>
            <TableCell>Head ID</TableCell>
            <TableCell>Relation</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {syntax.map((item) => (
            <TableRow key={`${item.token_id}-${item.relation}`}>
              <TableCell>{item.token_id}</TableCell>
              <TableCell>{item.head_id ?? ""}</TableCell>
              <TableCell>{item.relation ?? ""}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function TraceTable({ trace }: { trace: PipelineTraceItem[] }) {
  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Stage</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Progress</TableCell>
            <TableCell>Message</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {trace.map((item) => (
            <TableRow key={`${item.stage}-${item.progress_percent}`}>
              <TableCell>{item.stage}</TableCell>
              <TableCell>{item.status}</TableCell>
              <TableCell>{item.progress_percent}%</TableCell>
              <TableCell>{item.message}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
