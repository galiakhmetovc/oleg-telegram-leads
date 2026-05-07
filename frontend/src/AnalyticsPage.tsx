import FilterAltIcon from "@mui/icons-material/FilterAlt";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
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
import { FormEvent, useEffect, useMemo, useState } from "react";

type AnalyticsRun = {
  id: string;
  name: string;
  source: string;
  input_path: string;
  run_dir: string;
  processed: number;
  skipped: number;
  failed: number;
  leads: number;
  candidate_rate: number;
  started_at?: string | null;
  finished_at?: string | null;
  imported_at: string;
  summary: Record<string, unknown>;
};

type AnalyticsAggregate = {
  kind: string;
  key: string;
  label: string;
  count: number;
  payload: {
    examples?: string[];
    matched_types?: string[];
    weight?: number;
    [key: string]: unknown;
  };
};

type AnalyticsSummary = {
  run: AnalyticsRun;
  aggregates: Record<string, AnalyticsAggregate[]>;
};

type AnalyticsCandidate = {
  message_id: string;
  text: string;
  score: number;
  temperature: string;
  solution_areas: AnalyticsCategory[];
  customer_segments: AnalyticsCategory[];
  intent_signals: AnalyticsCategory[];
  noise_signals: AnalyticsCategory[];
  reasons: AnalyticsReason[];
  domain_signals: AnalyticsSpan[];
  facts: AnalyticsSpan[];
};

type AnalyticsCategory = {
  type: string;
  label?: string;
  matched_types?: string[];
};

type AnalyticsReason = {
  source: string;
  key: string;
  label?: string;
  weight: number;
  matched_texts: string[];
};

type AnalyticsSpan = {
  type: string;
  label?: string;
  text?: string;
};

type CandidatePage = {
  total: number;
  limit: number;
  offset: number;
  items: AnalyticsCandidate[];
};

type CandidateFilters = {
  scoreMin: string;
  temperature: string;
  signal: string;
  reason: string;
  solutionArea: string;
  customerSegment: string;
  q: string;
};

type AnalyticsPageProps = {
  apiBaseUrl: string;
};

const numberFormatter = new Intl.NumberFormat("ru-RU");
const candidatePageSize = 50;
const defaultFilters: CandidateFilters = {
  scoreMin: "",
  temperature: "",
  signal: "",
  reason: "",
  solutionArea: "",
  customerSegment: "",
  q: ""
};

export function AnalyticsPage({ apiBaseUrl }: AnalyticsPageProps) {
  const [runs, setRuns] = useState<AnalyticsRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [candidatePage, setCandidatePage] = useState<CandidatePage | null>(null);
  const [filters, setFilters] = useState<CandidateFilters>(defaultFilters);
  const [appliedFilters, setAppliedFilters] = useState<CandidateFilters>(defaultFilters);
  const [candidateOffset, setCandidateOffset] = useState(0);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  const loadingData = loadingSummary || loadingCandidates;
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? summary?.run ?? null,
    [runs, selectedRunId, summary]
  );

  useEffect(() => {
    let active = true;
    async function loadRuns() {
      setLoadingRuns(true);
      setAnalyticsError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/analytics/runs`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const payload = (await response.json()) as { runs: AnalyticsRun[] };
        if (!active) {
          return;
        }
        setRuns(payload.runs);
        setSelectedRunId((current) => {
          if (current && payload.runs.some((run) => run.id === current)) {
            return current;
          }
          return payload.runs[0]?.id ?? "";
        });
      } catch (caught) {
        if (active) {
          setAnalyticsError(caught instanceof Error ? caught.message : "Не удалось загрузить запуски аналитики");
        }
      } finally {
        if (active) {
          setLoadingRuns(false);
        }
      }
    }

    void loadRuns();
    return () => {
      active = false;
    };
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!selectedRunId) {
      setSummary(null);
      return;
    }

    let active = true;
    async function loadSummary() {
      setLoadingSummary(true);
      setAnalyticsError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/analytics/runs/${selectedRunId}/summary`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const nextSummary = (await response.json()) as AnalyticsSummary;
        if (active) {
          setSummary(nextSummary);
        }
      } catch (caught) {
        if (active) {
          setAnalyticsError(caught instanceof Error ? caught.message : "Не удалось загрузить сводку аналитики");
        }
      } finally {
        if (active) {
          setLoadingSummary(false);
        }
      }
    }

    void loadSummary();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      setCandidatePage(null);
      return;
    }

    let active = true;
    async function loadCandidates() {
      setLoadingCandidates(true);
      setAnalyticsError(null);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/analytics/runs/${selectedRunId}/candidates?${candidateQuery(
            appliedFilters,
            candidatePageSize,
            candidateOffset
          )}`
        );
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const nextCandidates = (await response.json()) as CandidatePage;
        if (active) {
          setCandidatePage(nextCandidates);
        }
      } catch (caught) {
        if (active) {
          setAnalyticsError(caught instanceof Error ? caught.message : "Не удалось загрузить кандидатов");
        }
      } finally {
        if (active) {
          setLoadingCandidates(false);
        }
      }
    }

    void loadCandidates();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedRunId, appliedFilters, candidateOffset]);

  function refreshRuns() {
    setSelectedRunId("");
    setRuns([]);
    setSummary(null);
    setCandidatePage(null);
    setCandidateOffset(0);
    setLoadingRuns(true);
    void fetch(`${apiBaseUrl}/api/v1/analytics/runs`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        return response.json() as Promise<{ runs: AnalyticsRun[] }>;
      })
      .then((payload) => {
        setRuns(payload.runs);
        setSelectedRunId(payload.runs[0]?.id ?? "");
      })
      .catch((caught) => {
        setAnalyticsError(caught instanceof Error ? caught.message : "Не удалось обновить аналитику");
      })
      .finally(() => setLoadingRuns(false));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCandidateOffset(0);
    setAppliedFilters(filters);
  }

  function handleSelectedRunChange(nextRunId: string) {
    setCandidateOffset(0);
    setSelectedRunId(nextRunId);
  }

  function handleCandidatePageChange(nextPage: number) {
    const limit = candidatePage?.limit ?? candidatePageSize;
    setCandidateOffset(nextPage * limit);
  }

  const runForKpi = summary?.run ?? selectedRun;
  const scoreBuckets = summary?.aggregates.score_bucket ?? [];
  const topSignals = (summary?.aggregates.signal ?? []).slice(0, 8);
  const topReasons = (summary?.aggregates.reason ?? []).slice(0, 8);
  const solutionAreas = (summary?.aggregates.solution_area ?? []).slice(0, 6);
  const customerSegments = (summary?.aggregates.customer_segment ?? []).slice(0, 6);
  const signalOptions = summary?.aggregates.signal ?? [];
  const reasonOptions = summary?.aggregates.reason ?? [];
  const solutionAreaOptions = summary?.aggregates.solution_area ?? [];
  const customerSegmentOptions = summary?.aggregates.customer_segment ?? [];

  return (
    <Box className="analytics-shell">
      <Paper variant="outlined" className="analytics-header">
        <Stack className="analytics-toolbar" direction={{ xs: "column", md: "row" }} spacing={2}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              Аналитика лидов
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {runForKpi?.name ?? "Загрузки batch-runner еще не импортированы"}
            </Typography>
          </Box>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ minWidth: { md: 420 } }}>
            <TextField
              select
              size="small"
              fullWidth
              label="Запуск"
              value={selectedRunId}
              onChange={(event) => handleSelectedRunChange(event.target.value)}
              disabled={loadingRuns || runs.length === 0}
            >
              {runs.map((run) => (
                <MenuItem key={run.id} value={run.id}>
                  {run.name}
                </MenuItem>
              ))}
            </TextField>
            <Button variant="outlined" startIcon={<RefreshIcon />} onClick={refreshRuns} disabled={loadingRuns}>
              Обновить
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {analyticsError && <Alert severity="error">{analyticsError}</Alert>}

      {loadingRuns ? (
        <Paper variant="outlined" className="analytics-section">
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Загрузка аналитики...</Typography>
          </Stack>
        </Paper>
      ) : runs.length === 0 ? (
        <Paper variant="outlined" className="analytics-section">
          <Typography variant="body2" color="text.secondary">
            Нет импортированных запусков. Импорт выполняется CLI-командой backend.
          </Typography>
        </Paper>
      ) : (
        <>
          <Box className="analytics-kpi-grid">
            <Kpi label="Сообщений" value={formatInteger(runForKpi?.processed ?? 0)} />
            <Kpi label="Кандидатов" value={formatInteger(runForKpi?.leads ?? 0)} />
            <Kpi label="Доля кандидатов" value={formatPercent(runForKpi?.candidate_rate ?? 0)} />
            <Kpi label="Ошибок" value={formatInteger(runForKpi?.failed ?? 0)} />
          </Box>

          {loadingData && <LinearProgress />}

          <Box className="analytics-grid">
            <Paper variant="outlined" className="analytics-section">
              <SectionTitle title="Score" subtitle={`${formatInteger(candidatePage?.total ?? 0)} в текущей выборке`} />
              <ScoreBars buckets={scoreBuckets} total={runForKpi?.leads ?? 0} />
            </Paper>
            <Paper variant="outlined" className="analytics-section">
              <SectionTitle title="Доменные сигналы" subtitle="Самые частые причины попадания в лиды" />
              <AggregateList items={topSignals} />
            </Paper>
            <Paper variant="outlined" className="analytics-section">
              <SectionTitle title="Причины score" subtitle="Что сильнее всего поднимает оценку" />
              <AggregateList items={topReasons} />
            </Paper>
            <Paper variant="outlined" className="analytics-section">
              <SectionTitle title="Сегменты" subtitle="Зоны решений и типы клиентов" />
              <Stack spacing={1.5}>
                <AggregateChips items={solutionAreas} />
                <Divider />
                <AggregateChips items={customerSegments} />
              </Stack>
            </Paper>
          </Box>

          <Paper variant="outlined" className="analytics-section">
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
                <SectionTitle
                  title="Кандидаты"
                  subtitle={`${formatInteger(candidatePage?.total ?? 0)} сообщений по текущим фильтрам`}
                />
                <Stack
                  component="form"
                  className="analytics-filter-row"
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1}
                  onSubmit={applyFilters}
                >
                  <TextField
                    size="small"
                    label="Min score"
                    value={filters.scoreMin}
                    onChange={(event) => setFilters((current) => ({ ...current, scoreMin: event.target.value }))}
                    sx={{ width: { sm: 120 } }}
                  />
                  <TextField
                    select
                    size="small"
                    label="Температура"
                    value={filters.temperature}
                    onChange={(event) => setFilters((current) => ({ ...current, temperature: event.target.value }))}
                    sx={{ width: { sm: 150 } }}
                  >
                    <MenuItem value="">Любая</MenuItem>
                    <MenuItem value="hot">hot</MenuItem>
                    <MenuItem value="warm">warm</MenuItem>
                    <MenuItem value="cold">cold</MenuItem>
                  </TextField>
                  <AggregateFilterSelect
                    label="Сигнал"
                    value={filters.signal}
                    options={signalOptions}
                    onChange={(value) => setFilters((current) => ({ ...current, signal: value }))}
                  />
                  <AggregateFilterSelect
                    label="Причина score"
                    value={filters.reason}
                    options={reasonOptions}
                    onChange={(value) => setFilters((current) => ({ ...current, reason: value }))}
                  />
                  <AggregateFilterSelect
                    label="Зона решения"
                    value={filters.solutionArea}
                    options={solutionAreaOptions}
                    onChange={(value) => setFilters((current) => ({ ...current, solutionArea: value }))}
                  />
                  <AggregateFilterSelect
                    label="Сегмент клиента"
                    value={filters.customerSegment}
                    options={customerSegmentOptions}
                    onChange={(value) => setFilters((current) => ({ ...current, customerSegment: value }))}
                  />
                  <TextField
                    size="small"
                    label="Текст"
                    value={filters.q}
                    onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
                    sx={{ width: { sm: 220 } }}
                  />
                  <Button type="submit" variant="contained" startIcon={<FilterAltIcon />} disabled={loadingData}>
                    Применить
                  </Button>
                </Stack>
              </Stack>
              <CandidateTable page={candidatePage} loading={loadingData} onPageChange={handleCandidatePageChange} />
            </Stack>
          </Paper>
        </>
      )}
    </Box>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <Box className="analytics-kpi">
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
    </Box>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {subtitle}
      </Typography>
    </Box>
  );
}

function ScoreBars({ buckets, total }: { buckets: AnalyticsAggregate[]; total: number }) {
  const maxCount = Math.max(...buckets.map((bucket) => bucket.count), 1);

  if (buckets.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет данных по score.
      </Typography>
    );
  }

  return (
    <Stack className="analytics-bars" spacing={1.25}>
      {buckets.map((bucket) => {
        const width = Math.max(4, (bucket.count / maxCount) * 100);
        const share = total > 0 ? `${(bucket.count * 100 / total).toFixed(1)}%` : "0.0%";
        return (
          <Box key={bucket.key} className="analytics-bar-row">
            <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between" }}>
              <Typography variant="body2">{bucket.label}</Typography>
              <Typography variant="body2" color="text.secondary">
                {formatInteger(bucket.count)} / {share}
              </Typography>
            </Stack>
            <Box className="analytics-bar-track">
              <Box className="analytics-bar-fill" sx={{ width: `${width}%` }} />
            </Box>
          </Box>
        );
      })}
    </Stack>
  );
}

function AggregateList({ items }: { items: AnalyticsAggregate[] }) {
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет данных.
      </Typography>
    );
  }

  return (
    <Stack spacing={1}>
      {items.map((item) => {
        const detail = aggregateDetail(item);
        return (
          <Box key={item.key} className="analytics-list-row">
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                {item.label || item.key}
              </Typography>
              {detail && (
                <Typography variant="caption" color="text.secondary" noWrap>
                  {detail}
                </Typography>
              )}
            </Box>
            <Chip size="small" label={formatInteger(item.count)} />
          </Box>
        );
      })}
    </Stack>
  );
}

function AggregateChips({ items }: { items: AnalyticsAggregate[] }) {
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет данных.
      </Typography>
    );
  }

  return (
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
      {items.map((item) => (
        <Chip key={item.key} label={`${item.label || item.key}: ${formatInteger(item.count)}`} size="small" />
      ))}
    </Stack>
  );
}

function AggregateFilterSelect({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: AnalyticsAggregate[];
  onChange: (value: string) => void;
}) {
  return (
    <TextField
      select
      size="small"
      label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={options.length === 0}
      sx={{ width: { sm: 220 } }}
    >
      <MenuItem value="">Любой</MenuItem>
      {options.map((option) => (
        <MenuItem key={option.key} value={option.key}>
          {aggregateOptionLabel(option)}
        </MenuItem>
      ))}
    </TextField>
  );
}

function CandidateTable({
  page,
  loading,
  onPageChange
}: {
  page: CandidatePage | null;
  loading: boolean;
  onPageChange: (nextPage: number) => void;
}) {
  if (loading && page === null) {
    return (
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
        <CircularProgress size={20} />
        <Typography variant="body2">Загрузка кандидатов...</Typography>
      </Stack>
    );
  }

  if (!page || page.items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        По текущим фильтрам кандидатов нет.
      </Typography>
    );
  }

  const currentPage = Math.floor(page.offset / page.limit);

  return (
    <Box>
      <TableContainer>
        <Table size="small" className="analytics-candidate-table">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Score</TableCell>
              <TableCell>Температура</TableCell>
              <TableCell>Текст</TableCell>
              <TableCell>Причины</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {page.items.map((candidate) => (
              <TableRow key={candidate.message_id}>
                <TableCell>{candidate.message_id}</TableCell>
                <TableCell>{candidate.score}</TableCell>
                <TableCell>{candidate.temperature}</TableCell>
                <TableCell className="candidate-text">{candidate.text}</TableCell>
                <TableCell className="candidate-reasons">
                  <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
                    {candidate.reasons.slice(0, 4).map((reason) => (
                      <Chip
                        key={`${candidate.message_id}-${reason.source}-${reason.key}`}
                        size="small"
                        label={`${reason.label || reason.key} +${reason.weight}`}
                      />
                    ))}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={page.total}
        page={currentPage}
        rowsPerPage={page.limit}
        rowsPerPageOptions={[page.limit]}
        labelRowsPerPage="Строк на странице"
        labelDisplayedRows={({ from, to, count }) =>
          `${formatInteger(from)}-${formatInteger(to)} из ${formatInteger(count)}`
        }
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
        onPageChange={(_, nextPage) => onPageChange(nextPage)}
        onRowsPerPageChange={() => undefined}
      />
    </Box>
  );
}

function candidateQuery(filters: CandidateFilters, limit: number, offset: number) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (filters.scoreMin.trim()) {
    params.set("score_min", filters.scoreMin.trim());
  }
  if (filters.temperature) {
    params.set("temperature", filters.temperature);
  }
  if (filters.signal.trim()) {
    params.set("signal", filters.signal.trim());
  }
  if (filters.reason.trim()) {
    params.set("reason", filters.reason.trim());
  }
  if (filters.solutionArea.trim()) {
    params.set("solution_area", filters.solutionArea.trim());
  }
  if (filters.customerSegment.trim()) {
    params.set("customer_segment", filters.customerSegment.trim());
  }
  if (filters.q.trim()) {
    params.set("q", filters.q.trim());
  }
  return params.toString();
}

function formatInteger(value: number) {
  return numberFormatter.format(value);
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

function aggregateDetail(item: AnalyticsAggregate) {
  const parts: string[] = [];
  if (item.label && item.label !== item.key) {
    parts.push(item.key);
  }
  if (item.payload.examples && item.payload.examples.length > 0) {
    parts.push(item.payload.examples.slice(0, 3).join(", "));
  }
  return parts.join(" · ");
}

function aggregateOptionLabel(item: AnalyticsAggregate) {
  return `${item.label || item.key} · ${formatInteger(item.count)}`;
}
