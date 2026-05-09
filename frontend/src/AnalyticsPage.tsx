import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import RateReviewIcon from "@mui/icons-material/RateReview";
import RefreshIcon from "@mui/icons-material/Refresh";
import SaveIcon from "@mui/icons-material/Save";
import ScienceIcon from "@mui/icons-material/Science";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  IconButton,
  LinearProgress,
  Link as MuiLink,
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
import { Fragment, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  CandidateDetails,
  ReviewStatusChip,
  ReviewReasonSummary,
  candidateTemperatureColor,
  candidateTemperatureLabel,
  formatDateTime,
  formatWeight,
  reviewLaneLabel
} from "./analytics/CandidateEvidence";
import {
  ConstructorDialog,
  createConstructorDialog,
  saveConstructorDialogRequest,
  saveNoiseConstructorRequest
} from "./analytics/ReviewConstructor";
import type { ConstructorDialogState, ReviewNlpSettings } from "./analytics/ReviewConstructor";
import type {
  AnalyticsAggregate,
  AnalyticsCandidate,
  AnalyticsReviewVerdict,
  AnalyticsRun,
  ReviewEvalExample,
  ReviewEvalReport,
  AnalyticsSummary,
  AnalyticsSummaryBlockKey,
  CandidateFilters,
  CandidatePage
} from "./analytics/types";

type AnalyticsPageProps = {
  apiBaseUrl: string;
  focusMessageId?: string | null;
  onTestMessage?: (candidate: AnalyticsCandidate) => void;
};

type AnalyticsReviewPageProps = {
  apiBaseUrl: string;
  messageId: string;
  returnHash?: string | null;
  nlpSettings?: ReviewNlpSettings | null;
  onBack?: () => void;
  onTestMessage?: (candidate: AnalyticsCandidate) => void;
  onNlpSettingsChange?: (nlpSettings: unknown) => void;
};

const numberFormatter = new Intl.NumberFormat("ru-RU");
const candidatePageSize = 50;
const reviewVerdictOptions: Array<{
  value: AnalyticsReviewVerdict;
  label: string;
  color: "primary" | "secondary" | "error" | "info" | "success" | "warning";
}> = [
  { value: "lead", label: "Лид", color: "success" },
  { value: "not_lead", label: "Не лид", color: "error" },
  { value: "uncertain", label: "Сомнительно", color: "warning" },
  { value: "noise", label: "Шум", color: "secondary" }
];
const reviewTagOptions = [
  { value: "no_provider_intent", label: "Нет запроса на подрядчика" },
  { value: "diy", label: "DIY / сам делает" },
  { value: "equipment_only", label: "Только оборудование" },
  { value: "sale", label: "Продажа / наличие" },
  { value: "not_pur_domain", label: "Не домен ПУР" },
  { value: "weak_context", label: "Слабый контекст" },
  { value: "false_alias", label: "Ложный alias" },
  { value: "needs_alias", label: "Нужен alias" },
  { value: "needs_rule", label: "Нужно правило" }
];
const defaultFilters: CandidateFilters = {
  scoreMin: "",
  temperature: "",
  signal: "",
  reason: "",
  solutionArea: "",
  customerSegment: "",
  lane: "",
  sourceChatId: "",
  receivedFrom: "",
  receivedTo: "",
  reviewStatus: "unreviewed",
  verdict: "",
  q: ""
};
const collapsedSummaryBlocks: Record<AnalyticsSummaryBlockKey, boolean> = {
  score: false,
  signals: false,
  reasons: false,
  segments: false,
  lanes: false
};

export function AnalyticsPage({ apiBaseUrl, focusMessageId, onTestMessage }: AnalyticsPageProps) {
  const initialAnalyticsStateRef = useRef<AnalyticsUrlState | null>(null);
  if (initialAnalyticsStateRef.current === null) {
    initialAnalyticsStateRef.current = parseAnalyticsUrlState(window.location.hash);
  }
  const initialAnalyticsState = initialAnalyticsStateRef.current;
  const [runs, setRuns] = useState<AnalyticsRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState(initialAnalyticsState.runId);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [reviewEval, setReviewEval] = useState<ReviewEvalReport | null>(null);
  const [candidatePage, setCandidatePage] = useState<CandidatePage | null>(null);
  const [focusedCandidate, setFocusedCandidate] = useState<AnalyticsCandidate | null>(null);
  const [filters, setFilters] = useState<CandidateFilters>(initialAnalyticsState.filters);
  const [appliedFilters, setAppliedFilters] = useState<CandidateFilters>(initialAnalyticsState.filters);
  const [candidateOffset, setCandidateOffset] = useState(initialAnalyticsState.offset);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingReviewEval, setLoadingReviewEval] = useState(false);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [reviewEvalError, setReviewEvalError] = useState<string | null>(null);
  const [expandedSummaryBlocks, setExpandedSummaryBlocks] = useState<Record<AnalyticsSummaryBlockKey, boolean>>(
    () => ({ ...collapsedSummaryBlocks })
  );
  const focusedCandidatePanelRef = useRef<HTMLDivElement | null>(null);
  const filterDraftRef = useRef<CandidateFilters>(initialAnalyticsState.filters);

  const loadingData = loadingSummary || loadingCandidates;
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? summary?.run ?? null,
    [runs, selectedRunId, summary]
  );
  const focusedCandidateInCurrentPage = useMemo(
    () => Boolean(focusMessageId && candidatePage?.items.some((candidate) => candidate.message_id === focusMessageId)),
    [candidatePage, focusMessageId]
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
        const payload = (await response.json()) as { runs?: AnalyticsRun[] };
        const runs = Array.isArray(payload.runs) ? payload.runs : [];
        if (!active) {
          return;
        }
        setRuns(runs);
        setSelectedRunId((current) => {
          if (current && runs.some((run) => run.id === current)) {
            return current;
          }
          if (initialAnalyticsState.runId && runs.some((run) => run.id === initialAnalyticsState.runId)) {
            return initialAnalyticsState.runId;
          }
          return runs[0]?.id ?? "";
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
    let active = true;
    async function loadReviewEval() {
      setLoadingReviewEval(true);
      setReviewEvalError(null);
      try {
        const nextReviewEval = await fetchReviewEval(apiBaseUrl);
        if (active) {
          setReviewEval(nextReviewEval);
        }
      } catch (caught) {
        if (active) {
          setReviewEvalError(caught instanceof Error ? caught.message : "Не удалось загрузить качество по ревью");
        }
      } finally {
        if (active) {
          setLoadingReviewEval(false);
        }
      }
    }

    void loadReviewEval();
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

  useEffect(() => {
    if (!focusMessageId) {
      setFocusedCandidate(null);
      return;
    }

    const messageId = focusMessageId;
    let active = true;
    async function loadFocusedCandidate() {
      setAnalyticsError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const candidate = (await response.json()) as AnalyticsCandidate;
        if (active) {
          setFocusedCandidate(candidate);
        }
      } catch (caught) {
        if (active) {
          setAnalyticsError(caught instanceof Error ? caught.message : "Не удалось загрузить сообщение аналитики");
        }
      }
    }

    void loadFocusedCandidate();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, focusMessageId]);

  useEffect(() => {
    if (!focusMessageId || !focusedCandidate || focusedCandidate.message_id !== focusMessageId || focusedCandidateInCurrentPage) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      focusedCandidatePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [focusedCandidate, focusedCandidateInCurrentPage, focusMessageId]);

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
        return response.json() as Promise<{ runs?: AnalyticsRun[] }>;
      })
      .then((payload) => {
        const runs = Array.isArray(payload.runs) ? payload.runs : [];
        setRuns(runs);
        setSelectedRunId(runs[0]?.id ?? "");
      })
      .catch((caught) => {
        setAnalyticsError(caught instanceof Error ? caught.message : "Не удалось обновить аналитику");
      })
      .finally(() => setLoadingRuns(false));
    setLoadingReviewEval(true);
    setReviewEvalError(null);
    void fetchReviewEval(apiBaseUrl)
      .then((nextReviewEval) => setReviewEval(nextReviewEval))
      .catch((caught) => {
        setReviewEvalError(caught instanceof Error ? caught.message : "Не удалось обновить качество по ревью");
      })
      .finally(() => setLoadingReviewEval(false));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = filterDraftRef.current;
    setCandidateOffset(0);
    setAppliedFilters(next);
    replaceAnalyticsListHash(next, 0, selectedRunId);
  }

  function updateSelectFilter(key: keyof CandidateFilters, value: string) {
    setCandidateOffset(0);
    const next = updateFilterDraft(key, value);
    setAppliedFilters(next);
    replaceAnalyticsListHash(next, 0, selectedRunId);
  }

  function updateFilterDraft(key: keyof CandidateFilters, value: string) {
    const next = { ...filterDraftRef.current, [key]: value };
    filterDraftRef.current = next;
    setFilters(next);
    return next;
  }

  function handleSelectedRunChange(nextRunId: string) {
    setCandidateOffset(0);
    setSelectedRunId(nextRunId);
    replaceAnalyticsListHash(appliedFilters, 0, nextRunId);
  }

  function handleCandidatePageChange(nextPage: number) {
    const limit = candidatePage?.limit ?? candidatePageSize;
    const nextOffset = nextPage * limit;
    setCandidateOffset(nextOffset);
    replaceAnalyticsListHash(appliedFilters, nextOffset, selectedRunId);
  }

  function toggleSummaryBlock(key: AnalyticsSummaryBlockKey) {
    setExpandedSummaryBlocks((current) => ({ ...current, [key]: !current[key] }));
  }

  const runForKpi = summary?.run ?? selectedRun;
  const scoreBuckets = summary?.aggregates.score_bucket ?? [];
  const topSignals = (summary?.aggregates.signal ?? []).slice(0, 8);
  const topReasons = (summary?.aggregates.reason ?? []).slice(0, 8);
  const solutionAreas = (summary?.aggregates.solution_area ?? []).slice(0, 6);
  const customerSegments = (summary?.aggregates.customer_segment ?? []).slice(0, 6);
  const reviewLanes = summary?.aggregates.review_lane ?? [];
  const signalOptions = summary?.aggregates.signal ?? [];
  const reasonOptions = summary?.aggregates.reason ?? [];
  const solutionAreaOptions = summary?.aggregates.solution_area ?? [];
  const customerSegmentOptions = summary?.aggregates.customer_segment ?? [];
  const laneOptions = summary?.aggregates.review_lane ?? [];
  const sourceChatOptions = summary?.aggregates.source_chat ?? [];
  const analyticsReturnHash = analyticsListHash(appliedFilters, candidateOffset, selectedRunId);

  return (
    <Box className="analytics-shell">
      <Paper variant="outlined" className="analytics-header">
        <Stack className="analytics-toolbar" direction={{ xs: "column", md: "row" }} spacing={2}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              Аналитика лидов
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {runForKpi?.name ?? "Нет активного источника аналитики"}
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
            Нет данных аналитики. Подключите Telegram-источники или импортируйте тестовый batch.
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

          <ReviewEvalPanel report={reviewEval} loading={loadingReviewEval} error={reviewEvalError} />

          {loadingData && <LinearProgress />}

          {focusedCandidate && !focusedCandidateInCurrentPage && (
            <Paper ref={focusedCandidatePanelRef} variant="outlined" className="analytics-section candidate-row-focused">
              <Stack spacing={1.5}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
                  <SectionTitle
                    title="Сообщение из ссылки"
                    subtitle={focusedCandidate.source_chat_title || focusedCandidate.message_id}
                  />
                  <Button variant="outlined" onClick={() => onTestMessage?.(focusedCandidate)}>
                    Проверить
                  </Button>
                </Stack>
                <CandidateDetails candidate={focusedCandidate} />
              </Stack>
            </Paper>
          )}

          <Box className="analytics-grid">
            <CollapsibleAnalyticsSection
              title="Score"
              subtitle={`${formatInteger(candidatePage?.total ?? 0)} в текущей выборке`}
              expanded={expandedSummaryBlocks.score}
              onToggle={() => toggleSummaryBlock("score")}
            >
              <ScoreBars buckets={scoreBuckets} total={runForKpi?.leads ?? 0} />
            </CollapsibleAnalyticsSection>
            <CollapsibleAnalyticsSection
              title="Доменные сигналы"
              subtitle="Самые частые причины попадания в лиды"
              expanded={expandedSummaryBlocks.signals}
              onToggle={() => toggleSummaryBlock("signals")}
            >
              <AggregateList items={topSignals} />
            </CollapsibleAnalyticsSection>
            <CollapsibleAnalyticsSection
              title="Причины score"
              subtitle="Что сильнее всего поднимает оценку"
              expanded={expandedSummaryBlocks.reasons}
              onToggle={() => toggleSummaryBlock("reasons")}
            >
              <AggregateList items={topReasons} />
            </CollapsibleAnalyticsSection>
            <CollapsibleAnalyticsSection
              title="Сегменты"
              subtitle="Зоны решений и типы клиентов"
              expanded={expandedSummaryBlocks.segments}
              onToggle={() => toggleSummaryBlock("segments")}
            >
              <Stack spacing={1.5}>
                <AggregateChips items={solutionAreas} />
                <Divider />
                <AggregateChips items={customerSegments} />
              </Stack>
            </CollapsibleAnalyticsSection>
            <CollapsibleAnalyticsSection
              title="Очереди разбора"
              subtitle="Очереди ручной проверки кандидатов"
              expanded={expandedSummaryBlocks.lanes}
              onToggle={() => toggleSummaryBlock("lanes")}
            >
              <AggregateList items={reviewLanes} />
            </CollapsibleAnalyticsSection>
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
                    onChange={(event) => updateFilterDraft("scoreMin", event.target.value)}
                    sx={{ width: { sm: 120 } }}
                  />
                  <TextField
                    select
                    size="small"
                    label="Температура"
                    value={filters.temperature}
                    onChange={(event) => updateSelectFilter("temperature", event.target.value)}
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
                    onChange={(value) => updateSelectFilter("signal", value)}
                  />
                  <AggregateFilterSelect
                    label="Причина score"
                    value={filters.reason}
                    options={reasonOptions}
                    onChange={(value) => updateSelectFilter("reason", value)}
                  />
                  <AggregateFilterSelect
                    label="Зона решения"
                    value={filters.solutionArea}
                    options={solutionAreaOptions}
                    onChange={(value) => updateSelectFilter("solutionArea", value)}
                  />
                  <AggregateFilterSelect
                    label="Сегмент клиента"
                    value={filters.customerSegment}
                    options={customerSegmentOptions}
                    onChange={(value) => updateSelectFilter("customerSegment", value)}
                  />
                  <AggregateFilterSelect
                    label="Очередь"
                    value={filters.lane}
                    options={laneOptions}
                    onChange={(value) => updateSelectFilter("lane", value)}
                  />
                  <TextField
                    select
                    size="small"
                    label="Статус ревью"
                    value={filters.reviewStatus}
                    onChange={(event) => updateSelectFilter("reviewStatus", event.target.value)}
                    sx={{ width: { sm: 170 } }}
                  >
                    <MenuItem value="">Любой</MenuItem>
                    <MenuItem value="unreviewed">Без ревью</MenuItem>
                    <MenuItem value="reviewed">С ревью</MenuItem>
                  </TextField>
                  <TextField
                    select
                    size="small"
                    label="Вердикт"
                    value={filters.verdict}
                    onChange={(event) => updateSelectFilter("verdict", event.target.value)}
                    sx={{ width: { sm: 170 } }}
                  >
                    <MenuItem value="">Любой</MenuItem>
                    {reviewVerdictOptions.map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <AggregateFilterSelect
                    label="Канал"
                    value={filters.sourceChatId}
                    options={sourceChatOptions}
                    onChange={(value) => updateSelectFilter("sourceChatId", value)}
                  />
                  <TextField
                    size="small"
                    type="datetime-local"
                    label="Дата с"
                    value={filters.receivedFrom}
                    onChange={(event) => updateFilterDraft("receivedFrom", event.target.value)}
                    slotProps={{ inputLabel: { shrink: true } }}
                    sx={{ width: { sm: 190 } }}
                  />
                  <TextField
                    size="small"
                    type="datetime-local"
                    label="Дата по"
                    value={filters.receivedTo}
                    onChange={(event) => updateFilterDraft("receivedTo", event.target.value)}
                    slotProps={{ inputLabel: { shrink: true } }}
                    sx={{ width: { sm: 190 } }}
                  />
                  <TextField
                    size="small"
                    label="Текст"
                    value={filters.q}
                    onChange={(event) => updateFilterDraft("q", event.target.value)}
                    sx={{ width: { sm: 220 } }}
                  />
                  <Button type="submit" variant="contained" startIcon={<FilterAltIcon />} disabled={!selectedRunId}>
                    Применить
                  </Button>
                </Stack>
              </Stack>
              <CandidateTable
                page={candidatePage}
                loading={loadingData}
                focusMessageId={focusMessageId}
                returnHash={analyticsReturnHash}
                onPageChange={handleCandidatePageChange}
              />
            </Stack>
          </Paper>
        </>
      )}
    </Box>
  );
}

export function AnalyticsReviewPage({
  apiBaseUrl,
  messageId,
  returnHash,
  nlpSettings,
  onBack,
  onTestMessage,
  onNlpSettingsChange
}: AnalyticsReviewPageProps) {
  const [candidate, setCandidate] = useState<AnalyticsCandidate | null>(null);
  const [verdict, setVerdict] = useState<AnalyticsReviewVerdict | null>(null);
  const [comment, setComment] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [selectedText, setSelectedText] = useState("");
  const [constructorDraft, setConstructorDraft] = useState<string | null>(null);
  const [constructorSaving, setConstructorSaving] = useState(false);
  const [constructorMessage, setConstructorMessage] = useState<string | null>(null);
  const [constructorError, setConstructorError] = useState<string | null>(null);
  const [constructorDialog, setConstructorDialog] = useState<ConstructorDialogState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [nextStatus, setNextStatus] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadCandidate() {
      setLoading(true);
      setError(null);
      setSaved(false);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const nextCandidate = (await response.json()) as AnalyticsCandidate;
        if (!active) {
          return;
        }
        setCandidate(nextCandidate);
        setVerdict(nextCandidate.review?.verdict ?? null);
        setComment(nextCandidate.review?.comment ?? "");
        setTags(nextCandidate.review?.tags ?? []);
        setSelectedText("");
        setConstructorDraft(null);
        setConstructorMessage(null);
        setConstructorError(null);
        setConstructorDialog(null);
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Не удалось загрузить сообщение для ревью");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadCandidate();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, messageId]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editingText =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.getAttribute("contenteditable") === "true");
      if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        void saveReview();
        return;
      }
      if (editingText || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) {
        return;
      }
      const index = Number(event.key) - 1;
      const option = reviewVerdictOptions[index];
      if (option) {
        event.preventDefault();
        setVerdict(option.value);
      }
      if (event.key.toLocaleLowerCase("ru-RU") === "n" || event.key.toLocaleLowerCase("ru-RU") === "т") {
        event.preventDefault();
        void saveReview({ goNext: true });
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [apiBaseUrl, comment, messageId, returnHash, tags, verdict]);

  async function saveReview(options: { goNext?: boolean } = {}) {
    setSaving(true);
    setError(null);
    setSaved(false);
    setNextStatus(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}/review`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict, comment, tags })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const nextCandidate = (await response.json()) as AnalyticsCandidate;
      setCandidate(nextCandidate);
      setVerdict(nextCandidate.review?.verdict ?? verdict);
      setComment(nextCandidate.review?.comment ?? comment);
      setTags(nextCandidate.review?.tags ?? tags);
      setSaved(true);
      if (options.goNext) {
        await openNextCandidate();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить ревью");
    } finally {
      setSaving(false);
    }
  }

  async function openNextCandidate() {
    if (!returnHash) {
      setNextStatus("Нет сохраненного контекста очереди для перехода к следующему сообщению.");
      return;
    }
    const state = parseAnalyticsUrlState(returnHash);
    if (!state.runId) {
      setNextStatus("В ссылке возврата нет выбранного запуска аналитики.");
      return;
    }
    const page = await fetchCandidatePage(state.runId, state.filters, state.offset);
    const currentIndex = page.items.findIndex((item) => item.message_id === messageId);
    const nextCandidate = currentIndex >= 0 ? page.items[currentIndex + 1] : page.items[0];
    if (nextCandidate) {
      window.location.hash = analyticsReviewHash(nextCandidate.message_id, returnHash);
      return;
    }
    if (page.total > state.offset + page.limit) {
      const nextOffset = state.offset + page.limit;
      const nextReturnHash = analyticsListHash(state.filters, nextOffset, state.runId);
      const nextPage = await fetchCandidatePage(state.runId, state.filters, nextOffset);
      if (nextPage.items[0]) {
        window.location.hash = analyticsReviewHash(nextPage.items[0].message_id, nextReturnHash);
        return;
      }
    }
    setNextStatus("В этой очереди больше нет сообщений.");
  }

  async function fetchCandidatePage(runId: string, filters: CandidateFilters, offset: number): Promise<CandidatePage> {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/analytics/runs/${encodeURIComponent(runId)}/candidates?${candidateQuery(
        filters,
        candidatePageSize,
        offset
      )}`
    );
    if (!response.ok) {
      throw new Error(`Backend вернул ${response.status}`);
    }
    return (await response.json()) as CandidatePage;
  }

  function rememberSelection() {
    const text = window.getSelection()?.toString().trim();
    if (text) {
      setSelectedText(text);
      setConstructorDraft(null);
      setConstructorMessage(null);
      setConstructorError(null);
    }
  }

  function toggleTag(tag: string) {
    setTags((current) => (current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]));
  }

  function openConstructorDialog(kind: "alias" | "fact" | "signal") {
    if (!selectedText) {
      return;
    }
    setConstructorDraft(null);
    setConstructorMessage(null);
    setConstructorError(null);
    setConstructorDialog(createConstructorDialog(kind, selectedText));
  }

  async function saveConstructorDialog() {
    if (!constructorDialog) {
      return;
    }
    setConstructorSaving(true);
    setConstructorError(null);
    setConstructorMessage(null);
    try {
      const payload = await saveConstructorDialogRequest({
        apiBaseUrl,
        messageId,
        dialog: constructorDialog
      });
      onNlpSettingsChange?.(payload.nlp);
      setConstructorDraft(payload.draft);
      setConstructorMessage(payload.message);
      setConstructorDialog(null);
    } catch (caught) {
      setConstructorError(caught instanceof Error ? caught.message : "Не удалось сохранить настройку конструктора");
    } finally {
      setConstructorSaving(false);
    }
  }

  async function saveSelectedTextAsNoise() {
    if (!selectedText) {
      return;
    }
    setConstructorSaving(true);
    setConstructorError(null);
    setConstructorMessage(null);
    try {
      const payload = await saveNoiseConstructorRequest({
        apiBaseUrl,
        messageId,
        text: selectedText
      });
      onNlpSettingsChange?.(payload.nlp);
      setConstructorDraft(payload.draft);
      setConstructorMessage(payload.message);
    } catch (caught) {
      setConstructorError(caught instanceof Error ? caught.message : "Не удалось добавить шумовое правило");
    } finally {
      setConstructorSaving(false);
    }
  }

  return (
    <Box className="analytics-shell analytics-review-shell">
      <Paper variant="outlined" className="analytics-header">
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
                Ревью сообщения
              </Typography>
              <Typography variant="body2" color="text.secondary" noWrap>
                {candidate?.source_chat_title || candidate?.source_chat_id || messageId}
              </Typography>
            </Box>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <Button variant="outlined" startIcon={<ArrowBackIcon />} onClick={onBack} href={onBack ? undefined : "#/analytics"}>
                Аналитика
              </Button>
              {candidate?.telegram_message_url && (
                <Button variant="outlined" href={candidate.telegram_message_url} target="_blank" rel="noreferrer">
                  Telegram
                </Button>
              )}
              <Button
                variant="outlined"
                startIcon={<ScienceIcon />}
                disabled={!candidate}
                onClick={() => candidate && onTestMessage?.(candidate)}
              >
                Проверить
              </Button>
            </Stack>
          </Stack>

          {loading && (
            <Stack spacing={1}>
              <LinearProgress />
              <Typography variant="caption" color="text.secondary">
                Загружаю сообщение, разбор и сохраненное ревью
              </Typography>
            </Stack>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          {saved && <Alert severity="success">Ревью сохранено</Alert>}
          {nextStatus && <Alert severity="info">{nextStatus}</Alert>}
        </Stack>
      </Paper>

      {candidate && (
        <Box className="analytics-review-grid">
          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.25}>
                <SectionTitle title="Почему сработало" subtitle="Короткая сводка автоматического разбора перед решением" />
                <ReviewReasonSummary candidate={candidate} />
              </Stack>
            </Paper>

            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.5}>
                <SectionTitle title="Разметка" subtitle="1-4 выбирают вердикт, Ctrl+Enter сохраняет, N сохраняет и открывает следующее" />
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                  {reviewVerdictOptions.map((option) => (
                    <Button
                      key={option.value}
                      variant={verdict === option.value ? "contained" : "outlined"}
                      color={option.color}
                      onClick={() => setVerdict(option.value)}
                    >
                      {option.label}
                    </Button>
                  ))}
                  <Button variant={verdict === null ? "contained" : "outlined"} onClick={() => setVerdict(null)}>
                    Без оценки
                  </Button>
                </Stack>
                <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                  {reviewTagOptions.map((option) => (
                    <Button
                      key={option.value}
                      size="small"
                      variant={tags.includes(option.value) ? "contained" : "outlined"}
                      onClick={() => toggleTag(option.value)}
                    >
                      {option.label}
                    </Button>
                  ))}
                </Stack>
                <TextField
                  label="Комментарий ревью"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  multiline
                  minRows={4}
                  fullWidth
                />
                <Button
                  variant="contained"
                  startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
                  disabled={saving}
                  onClick={() => void saveReview()}
                >
                  Сохранить ревью
                </Button>
                <Button
                  variant="outlined"
                  startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
                  disabled={saving}
                  onClick={() => void saveReview({ goNext: true })}
                >
                  Сохранить и следующий
                </Button>
              </Stack>
            </Paper>

            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.25}>
                <SectionTitle
                  title="Исходный текст"
                  subtitle="Выделите фрагмент мышью, чтобы использовать его в конструкторе"
                />
                <Box className="review-message-text" onMouseUp={rememberSelection} onKeyUp={rememberSelection}>
                  {candidate.text}
                </Box>
              </Stack>
            </Paper>

            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.25}>
                <SectionTitle
                  title="Конструктор сущностей"
                  subtitle="Выделенный фрагмент можно превратить в правило настроек"
                />
                {selectedText ? (
                  <Alert severity="info">
                    Выделено: <strong>{selectedText}</strong>
                  </Alert>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Выделите часть исходного текста, чтобы подготовить новую словарную сущность, факт, доменный сигнал или шум.
                  </Typography>
                )}
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                  <Button variant="outlined" disabled={!selectedText} onClick={() => openConstructorDialog("alias")}>
                    В словарь
                  </Button>
                  <Button variant="outlined" disabled={!selectedText} onClick={() => openConstructorDialog("fact")}>
                    В факт
                  </Button>
                  <Button variant="outlined" disabled={!selectedText} onClick={() => openConstructorDialog("signal")}>
                    В доменный сигнал
                  </Button>
                  <Button
                    variant="outlined"
                    disabled={!selectedText || constructorSaving}
                    onClick={() => void saveSelectedTextAsNoise()}
                    startIcon={constructorSaving ? <CircularProgress size={18} color="inherit" /> : undefined}
                  >
                    В шум
                  </Button>
                </Stack>
                {constructorError && <Alert severity="error">{constructorError}</Alert>}
                {constructorMessage && (
                  <Alert severity="success">
                    {constructorMessage}.{" "}
                    <MuiLink href="#/settings/signals/operator_noise">Открыть настройку</MuiLink>
                  </Alert>
                )}
                {constructorDraft && <Chip label={constructorDraft} variant="outlined" />}
              </Stack>
            </Paper>
          </Stack>

          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.25}>
                <SectionTitle title="Карточка кандидата" subtitle="Текущий автоматический разбор сообщения" />
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                  <Chip label={candidateTemperatureLabel(candidate)} color={candidateTemperatureColor(candidate)} />
                  <Chip label={`${candidate.score} баллов`} variant="outlined" />
                  <Chip label={reviewLaneLabel(candidate.review_lane)} variant="outlined" />
                  {candidate.received_at && <Chip label={formatDateTime(candidate.received_at)} variant="outlined" />}
                </Stack>
              </Stack>
            </Paper>
            <CandidateDetails candidate={candidate} />
          </Stack>
        </Box>
      )}
      <ConstructorDialog
        dialog={constructorDialog}
        nlpSettings={nlpSettings}
        saving={constructorSaving}
        onChange={setConstructorDialog}
        onClose={() => {
          if (!constructorSaving) {
            setConstructorDialog(null);
          }
        }}
        onSave={() => void saveConstructorDialog()}
      />
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

function CollapsibleAnalyticsSection({
  title,
  subtitle,
  expanded,
  onToggle,
  children
}: {
  title: string;
  subtitle: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <Paper variant="outlined" className="analytics-section">
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", justifyContent: "space-between" }}>
          <SectionTitle title={title} subtitle={subtitle} />
          <IconButton
            aria-label={expanded ? `Скрыть блок ${title}` : `Показать блок ${title}`}
            size="small"
            onClick={onToggle}
          >
            {expanded ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
          </IconButton>
        </Stack>
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          {children}
        </Collapse>
      </Stack>
    </Paper>
  );
}

function ReviewEvalPanel({
  report,
  loading,
  error
}: {
  report: ReviewEvalReport | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Paper variant="outlined" className="analytics-section">
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <SectionTitle
            title="Качество по ревью"
            subtitle="Сравнение ручных вердиктов с автоматической оценкой лида"
          />
          {loading && (
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                Обновление
              </Typography>
            </Stack>
          )}
        </Stack>
        {error && <Alert severity="warning">{error}</Alert>}
        {!report ? (
          <Typography variant="body2" color="text.secondary">
            Метрики появятся после загрузки ручных ревью.
          </Typography>
        ) : (
          <>
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Chip label={`Размечено: ${formatInteger(report.reviewed)}`} />
              <Chip label={`В оценке: ${formatInteger(report.evaluated)}`} variant="outlined" />
              <Chip label={`FP: ${formatInteger(report.false_positive)}`} color={report.false_positive > 0 ? "warning" : "default"} />
              <Chip label={`FN: ${formatInteger(report.false_negative)}`} color={report.false_negative > 0 ? "error" : "default"} />
              {report.skipped_uncertain > 0 && <Chip label={`Сомнительно: ${formatInteger(report.skipped_uncertain)}`} />}
            </Stack>
            <Box className="analytics-kpi-grid">
              <Kpi label="Precision" value={formatRatioPercent(report.precision)} />
              <Kpi label="Recall" value={formatRatioPercent(report.recall)} />
              <Kpi label="F1" value={formatRatioPercent(report.f1)} />
              <Kpi label="Accuracy" value={formatRatioPercent(report.accuracy)} />
            </Box>
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" } }}>
              <ReviewEvalExamples title="False Positives" examples={report.false_positives} />
              <ReviewEvalExamples title="False Negatives" examples={report.false_negatives} />
            </Box>
          </>
        )}
      </Stack>
    </Paper>
  );
}

function ReviewEvalExamples({ title, examples }: { title: string; examples: ReviewEvalExample[] }) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {examples.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Нет примеров.
        </Typography>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Сообщение</TableCell>
                <TableCell>Score</TableCell>
                <TableCell>Текст</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {examples.map((example) => (
                <TableRow key={example.source_message_id}>
                  <TableCell>
                    <MuiLink href={`#/analytics/review/${encodeURIComponent(example.source_message_id)}`}>
                      {example.telegram_message_id ?? example.source_message_id}
                    </MuiLink>
                    {example.source_chat_title && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                        {example.source_chat_title}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.5}>
                      <Typography variant="body2">{formatInteger(example.score)}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {example.review_lane || example.temperature}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{example.text_preview}</Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
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

function candidateRowClass(expanded: boolean, focused: boolean): string | undefined {
  const classes = [
    expanded ? "candidate-row-expanded" : "",
    focused ? "candidate-row-focused" : ""
  ].filter(Boolean);
  return classes.length > 0 ? classes.join(" ") : undefined;
}

function CandidateTable({
  page,
  loading,
  focusMessageId,
  returnHash,
  onPageChange
}: {
  page: CandidatePage | null;
  loading: boolean;
  focusMessageId?: string | null;
  returnHash: string;
  onPageChange: (nextPage: number) => void;
}) {
  const [expandedMessageId, setExpandedMessageId] = useState<string | null>(null);
  const [dismissedFocusMessageId, setDismissedFocusMessageId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const focusedPageMessageId =
    focusMessageId && page?.items.some((candidate) => candidate.message_id === focusMessageId)
      ? focusMessageId
      : null;
  const activeExpandedMessageId =
    expandedMessageId ?? (focusedPageMessageId !== dismissedFocusMessageId ? focusedPageMessageId : null);

  useEffect(() => {
    setExpandedMessageId(null);
    setDismissedFocusMessageId(null);
  }, [focusMessageId]);

  useEffect(() => {
    if (!focusedPageMessageId) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      rowRefs.current.get(focusedPageMessageId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [focusedPageMessageId]);

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
              <TableCell />
              <TableCell>ID</TableCell>
              <TableCell>Score</TableCell>
              <TableCell>Температура</TableCell>
              <TableCell>Очередь</TableCell>
              <TableCell>Ревью</TableCell>
              <TableCell>Принято</TableCell>
              <TableCell>Канал</TableCell>
              <TableCell>Текст</TableCell>
              <TableCell>Причины</TableCell>
              <TableCell>Ссылки</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {page.items.map((candidate) => {
              const expanded = activeExpandedMessageId === candidate.message_id;
              const focused = focusMessageId === candidate.message_id;
              return (
                <Fragment key={candidate.message_id}>
                  <TableRow
                    ref={(element) => {
                      if (element) {
                        rowRefs.current.set(candidate.message_id, element);
                      } else {
                        rowRefs.current.delete(candidate.message_id);
                      }
                    }}
                    hover
                    className={candidateRowClass(expanded, focused)}
                  >
                    <TableCell>
                      <IconButton
                        aria-label={
                          expanded
                            ? `Скрыть разбор сообщения ${candidate.message_id}`
                            : `Показать разбор сообщения ${candidate.message_id}`
                        }
                        size="small"
                        onClick={() => {
                          setExpandedMessageId(expanded ? null : candidate.message_id);
                          setDismissedFocusMessageId(expanded && focused ? candidate.message_id : null);
                        }}
                      >
                        {expanded ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
                      </IconButton>
                    </TableCell>
                    <TableCell>{candidate.message_id}</TableCell>
                    <TableCell>{candidate.score}</TableCell>
                    <TableCell>{candidateTemperatureLabel(candidate)}</TableCell>
                    <TableCell>
                      <Chip size="small" label={reviewLaneLabel(candidate.review_lane)} variant="outlined" />
                    </TableCell>
                    <TableCell>
                      <ReviewStatusChip review={candidate.review ?? null} />
                    </TableCell>
                    <TableCell>{candidate.received_at ? formatDateTime(candidate.received_at) : "не указано"}</TableCell>
                    <TableCell>{candidate.source_chat_title || candidate.source_chat_id || "не указано"}</TableCell>
                    <TableCell className="candidate-text">{candidate.text}</TableCell>
                    <TableCell className="candidate-reasons">
                      <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
                        {candidate.reasons.slice(0, 4).map((reason) => (
                          <Chip
                            key={`${candidate.message_id}-${reason.source}-${reason.key}`}
                            size="small"
                            label={`${reason.label || reason.key} ${formatWeight(reason.weight)}`}
                          />
                        ))}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
                        {candidate.telegram_message_url && (
                          <Button size="small" href={candidate.telegram_message_url} target="_blank" rel="noreferrer">
                            TG
                          </Button>
                        )}
                        <Button size="small" href={`#/analytics/message/${candidate.message_id}`}>
                          Аналитика
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<RateReviewIcon fontSize="small" />}
                          href={analyticsReviewHash(candidate.message_id, returnHash)}
                        >
                          Ревью
                        </Button>
                        <Button size="small" href={`#/testing?message_id=${encodeURIComponent(candidate.message_id)}`}>
                          Проверить
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                  <TableRow className="candidate-detail-row">
                    <TableCell colSpan={11} sx={{ p: 0 }}>
                      <Collapse in={expanded} timeout="auto" unmountOnExit>
                        <CandidateDetails candidate={candidate} />
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </Fragment>
              );
            })}
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

type AnalyticsUrlState = {
  runId: string;
  offset: number;
  filters: CandidateFilters;
};

function parseAnalyticsUrlState(hash: string): AnalyticsUrlState {
  const queryIndex = hash.indexOf("?");
  const params = queryIndex === -1 ? new URLSearchParams() : new URLSearchParams(hash.slice(queryIndex + 1));
  return {
    runId: params.get("run")?.trim() ?? "",
    offset: Math.max(0, Number(params.get("offset") ?? "0") || 0),
    filters: {
      scoreMin: params.get("score_min") ?? "",
      temperature: params.get("temperature") ?? "",
      signal: params.get("signal") ?? "",
      reason: params.get("reason") ?? "",
      solutionArea: params.get("solution_area") ?? "",
      customerSegment: params.get("customer_segment") ?? "",
      lane: params.get("lane") ?? "",
      sourceChatId: params.get("source_chat_id") ?? "",
      receivedFrom: isoToDatetimeLocal(params.get("received_from") ?? ""),
      receivedTo: isoToDatetimeLocal(params.get("received_to") ?? ""),
      reviewStatus: params.get("review_status") ?? "",
      verdict: params.get("verdict") ?? "",
      q: params.get("q") ?? ""
    }
  };
}

function analyticsListHash(filters: CandidateFilters, offset: number, runId: string): string {
  const query = candidateQuery(filters, candidatePageSize, offset);
  const params = new URLSearchParams(query);
  if (runId) {
    params.set("run", runId);
  }
  return `#/analytics${params.toString() ? `?${params.toString()}` : ""}`;
}

function replaceAnalyticsListHash(filters: CandidateFilters, offset: number, runId: string) {
  if (!window.location.hash.startsWith("#/analytics")) {
    return;
  }
  window.history.replaceState(null, "", analyticsListHash(filters, offset, runId));
}

function analyticsReviewHash(messageId: string, returnHash: string): string {
  const params = new URLSearchParams();
  params.set("return", returnHash);
  return `#/analytics/review/${encodeURIComponent(messageId)}?${params.toString()}`;
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
  if (filters.lane.trim()) {
    params.set("lane", filters.lane.trim());
  }
  if (filters.reviewStatus.trim()) {
    params.set("review_status", filters.reviewStatus.trim());
  }
  if (filters.verdict.trim()) {
    params.set("verdict", filters.verdict.trim());
  }
  if (filters.sourceChatId.trim()) {
    params.set("source_chat_id", filters.sourceChatId.trim());
  }
  const receivedFrom = datetimeLocalToIso(filters.receivedFrom);
  if (receivedFrom) {
    params.set("received_from", receivedFrom);
  }
  const receivedTo = datetimeLocalToIso(filters.receivedTo);
  if (receivedTo) {
    params.set("received_to", receivedTo);
  }
  if (filters.q.trim()) {
    params.set("q", filters.q.trim());
  }
  return params.toString();
}

async function fetchReviewEval(apiBaseUrl: string): Promise<ReviewEvalReport> {
  const response = await fetch(`${apiBaseUrl}/api/v1/analytics/review-eval`);
  if (!response.ok) {
    throw new Error(`Backend вернул ${response.status}`);
  }
  return await response.json() as ReviewEvalReport;
}

function formatInteger(value: number) {
  return numberFormatter.format(value);
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

function formatRatioPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
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
  const localOffset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - localOffset).toISOString().slice(0, 16);
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
