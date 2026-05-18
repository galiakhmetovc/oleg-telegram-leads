import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography
} from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";

import { AnalyticsOverviewPanel, collapsedSummaryBlocks } from "./analytics/AnalyticsOverviewPanel";
import { CandidateQueueSection } from "./analytics/CandidateQueueSection";
import { LlmRuntimePanel, type LlmVerificationConfig } from "./analytics/LlmVerificationPanels";
import { ReviewEvalPanel } from "./analytics/ReviewEvalPanel";
import {
  analyticsSectionHash,
  effectiveAnalyticsSection,
  parseAnalyticsSection,
  parseAnalyticsUrlState,
  replaceAnalyticsSectionHash,
  type AnalyticsSection,
  type AnalyticsUrlState
} from "./analytics/analyticsRoutes";
import { defaultCandidateFilters } from "./analytics/candidateQueueState";
import type {
  AnalyticsCandidate,
  AnalyticsRun,
  AnalyticsSummary,
  AnalyticsSummaryBlockKey,
  ReviewEvalReport
} from "./analytics/types";
import { currentRoute, navigateRoute } from "./routes";

export { AnalyticsReviewPage } from "./analytics/AnalyticsReviewPage";

type AnalyticsPageProps = {
  apiBaseUrl: string;
  focusMessageId?: string | null;
  onTestMessage?: (candidate: AnalyticsCandidate) => void;
  sectionScope?: "workspace" | "reports";
};

export function AnalyticsPage({ apiBaseUrl, focusMessageId, onTestMessage, sectionScope }: AnalyticsPageProps) {
  const initialAnalyticsStateRef = useRef<AnalyticsUrlState | null>(null);
  if (initialAnalyticsStateRef.current === null) {
    initialAnalyticsStateRef.current = parseAnalyticsUrlState(currentRoute());
  }
  const initialAnalyticsState = initialAnalyticsStateRef.current;
  const [activeSection, setActiveSection] = useState<AnalyticsSection>(() => parseAnalyticsSection(currentRoute()));
  const [runs, setRuns] = useState<AnalyticsRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState(initialAnalyticsState.runId);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [reviewEval, setReviewEval] = useState<ReviewEvalReport | null>(null);
  const [llmConfig, setLlmConfig] = useState<LlmVerificationConfig | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingReviewEval, setLoadingReviewEval] = useState(false);
  const [loadingLlmConfig, setLoadingLlmConfig] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [reviewEvalError, setReviewEvalError] = useState<string | null>(null);
  const [llmConfigError, setLlmConfigError] = useState<string | null>(null);
  const [expandedSummaryBlocks, setExpandedSummaryBlocks] = useState<Record<AnalyticsSummaryBlockKey, boolean>>(
    () => ({ ...collapsedSummaryBlocks })
  );
  const effectiveSection = effectiveAnalyticsSection(activeSection, sectionScope);
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? summary?.run ?? null,
    [runs, selectedRunId, summary]
  );
  const runForKpi = summary?.run ?? selectedRun;

  useEffect(() => {
    function syncActiveSection() {
      setActiveSection(parseAnalyticsSection(currentRoute()));
    }

    syncActiveSection();
    window.addEventListener("hashchange", syncActiveSection);
    window.addEventListener("popstate", syncActiveSection);
    return () => {
      window.removeEventListener("hashchange", syncActiveSection);
      window.removeEventListener("popstate", syncActiveSection);
    };
  }, []);

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
  }, [apiBaseUrl, initialAnalyticsState.runId]);

  useEffect(() => {
    if (effectiveSection !== "quality") {
      return;
    }

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
  }, [effectiveSection, apiBaseUrl]);

  useEffect(() => {
    if (effectiveSection !== "llm") {
      return;
    }

    let active = true;
    async function loadLlmConfig() {
      setLoadingLlmConfig(true);
      setLlmConfigError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/llm-verifications/config`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const nextConfig = (await response.json()) as LlmVerificationConfig;
        if (active) {
          setLlmConfig(nextConfig);
        }
      } catch (caught) {
        if (active) {
          setLlmConfigError(caught instanceof Error ? caught.message : "Не удалось загрузить настройки LLM");
        }
      } finally {
        if (active) {
          setLoadingLlmConfig(false);
        }
      }
    }

    void loadLlmConfig();
    return () => {
      active = false;
    };
  }, [effectiveSection, apiBaseUrl]);

  useEffect(() => {
    if (!selectedRunId) {
      setSummary(null);
      return;
    }
    if (effectiveSection === "quality" || effectiveSection === "llm") {
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
  }, [effectiveSection, apiBaseUrl, selectedRunId]);

  function refreshRuns() {
    setSelectedRunId("");
    setRuns([]);
    setSummary(null);
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
    if (effectiveSection === "quality") {
      setLoadingReviewEval(true);
      setReviewEvalError(null);
      void fetchReviewEval(apiBaseUrl)
        .then((nextReviewEval) => setReviewEval(nextReviewEval))
        .catch((caught) => {
          setReviewEvalError(caught instanceof Error ? caught.message : "Не удалось обновить качество по ревью");
        })
        .finally(() => setLoadingReviewEval(false));
    }
  }

  function handleSelectedRunChange(nextRunId: string) {
    setSelectedRunId(nextRunId);
    replaceAnalyticsSectionHash(effectiveSection, defaultCandidateFilters(), 0, nextRunId);
  }

  function toggleSummaryBlock(key: AnalyticsSummaryBlockKey) {
    setExpandedSummaryBlocks((current) => ({ ...current, [key]: !current[key] }));
  }

  function navigateAnalyticsSection(nextSection: AnalyticsSection) {
    setActiveSection(nextSection);
    const nextRoute = analyticsSectionHash(nextSection, defaultCandidateFilters(), 0, selectedRunId);
    if (currentRoute() === nextRoute) {
      window.dispatchEvent(new Event("popstate"));
      return;
    }
    navigateRoute(nextRoute);
  }

  return (
    <Box className="analytics-shell">
      <Paper variant="outlined" className="analytics-header">
        <Stack className="analytics-toolbar" direction={{ xs: "column", md: "row" }} spacing={2}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              {sectionScope === "workspace" ? "Очередь сообщений" : "Аналитика лидов"}
            </Typography>
            {sectionScope !== "workspace" && (
              <Typography variant="body2" color="text.secondary" noWrap>
                {runForKpi?.name ?? "Нет активного источника аналитики"}
              </Typography>
            )}
          </Box>
          {sectionScope !== "workspace" && (
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
          )}
        </Stack>
      </Paper>

      {analyticsError && <Alert severity="error">{analyticsError}</Alert>}

      {sectionScope !== "workspace" && (
        <Paper variant="outlined" className="analytics-section">
          <Tabs
            value={effectiveSection}
            onChange={(_, nextSection) => navigateAnalyticsSection(nextSection as AnalyticsSection)}
            variant="scrollable"
            scrollButtons="auto"
            aria-label="Разделы аналитики"
          >
            <Tab value="overview" label="Обзор" />
            <Tab value="quality" label="Качество ревью" />
            <Tab value="llm" label="LLM-проверка" />
          </Tabs>
        </Paper>
      )}

      {loadingRuns ? (
        <Paper variant="outlined" className="analytics-section">
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Загрузка аналитики...</Typography>
          </Stack>
        </Paper>
      ) : runs.length === 0 && effectiveSection !== "llm" ? (
        <Paper variant="outlined" className="analytics-section">
          <Typography variant="body2" color="text.secondary">
            Нет данных аналитики. Подключите Telegram-источники или импортируйте тестовый batch.
          </Typography>
        </Paper>
      ) : (
        <>
          {effectiveSection === "overview" && (
            <AnalyticsOverviewPanel
              summary={summary}
              run={runForKpi}
              loading={loadingSummary}
              expandedBlocks={expandedSummaryBlocks}
              onToggleBlock={toggleSummaryBlock}
            />
          )}

          {effectiveSection === "quality" && (
            <ReviewEvalPanel report={reviewEval} loading={loadingReviewEval} error={reviewEvalError} />
          )}

          {effectiveSection === "llm" && (
            <LlmRuntimePanel config={llmConfig} loading={loadingLlmConfig} error={llmConfigError} />
          )}

          {effectiveSection === "candidates" && (
            <CandidateQueueSection
              apiBaseUrl={apiBaseUrl}
              selectedRunId={selectedRunId}
              summary={summary}
              loadingSummary={loadingSummary}
              focusMessageId={focusMessageId}
              onRefresh={refreshRuns}
              onTestMessage={onTestMessage}
            />
          )}
        </>
      )}
    </Box>
  );
}

async function fetchReviewEval(apiBaseUrl: string): Promise<ReviewEvalReport> {
  const response = await fetch(`${apiBaseUrl}/api/v1/analytics/review-eval`);
  if (!response.ok) {
    throw new Error(`Backend вернул ${response.status}`);
  }
  return await response.json() as ReviewEvalReport;
}
