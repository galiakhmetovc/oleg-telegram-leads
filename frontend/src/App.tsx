import ArticleIcon from "@mui/icons-material/Article";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ConstructionIcon from "@mui/icons-material/Construction";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsightsIcon from "@mui/icons-material/Insights";
import LightModeIcon from "@mui/icons-material/LightMode";
import LogoutIcon from "@mui/icons-material/Logout";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import RateReviewIcon from "@mui/icons-material/RateReview";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";
import ScienceIcon from "@mui/icons-material/Science";
import SettingsIcon from "@mui/icons-material/Settings";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import StarIcon from "@mui/icons-material/Star";
import {
  Alert,
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  CssBaseline,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  ThemeProvider,
  Toolbar,
  Tooltip,
  Typography,
  createTheme,
  useMediaQuery
} from "@mui/material";
import { FormEvent, ReactNode, SyntheticEvent, startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AnalyticsPage, AnalyticsReviewPage } from "./AnalyticsPage";
import { ConfiguratorPage } from "./configurator/ConfiguratorPage";
import { LeadAssessmentSummary, TestingWorkspace } from "./enrichment/TestingWorkspace";
import type { EnrichmentEvent, EnrichmentJob, TextEnrichmentResult } from "./enrichment/types";
import { GoldenExamplesPage } from "./golden/GoldenExamplesPage";
import { LlmPage } from "./llm/LlmPage";
import { OperatorGuidePage, type OperatorGuideRouteTarget } from "./operator-guide/OperatorGuidePage";
import { currentRoute, navigateRoute, normalizeRoute, routeParts, routeQuery, routeWithoutQuery } from "./routes";
import { ProjectDocumentationPage, RuntimeLogsPage, SystemStatusPage } from "./runtime/RuntimePages";
import { SettingsCenter, SettingsTargetDialog, settingsSectionForTarget } from "./settings/SettingsCenter";
import { SettingsHelpPage } from "./settings/SettingsHelpPage";
import {
  openSettingsTargetEvent,
  parseSettingsTargetHash,
  settingsTargetHash,
  type SettingsSection,
  type SettingsTarget
} from "./settings/navigation";
import type { NlpSettings, SettingsSnapshot } from "./settings/types";

type AuthState = {
  status: "authenticated" | "anonymous";
  username?: string | null;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const themeStorageKey = "pur-leads-theme-mode";

type AppThemeMode = "light" | "dark";
type WorkbenchSection = "queue" | "review" | "testing" | "constructor";

function createAppTheme(mode: AppThemeMode) {
  return createTheme({
    palette: {
      mode,
      primary: {
        main: mode === "dark" ? "#8ab4f8" : "#0b57d0"
      },
      background: {
        default: mode === "dark" ? "#0f172a" : "#f6f8fb",
        paper: mode === "dark" ? "#111827" : "#ffffff"
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
}

function readStoredThemeMode(): AppThemeMode {
  try {
    return window.localStorage.getItem(themeStorageKey) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function persistThemeMode(mode: AppThemeMode) {
  try {
    window.localStorage.setItem(themeStorageKey, mode);
  } catch {
    // The theme still applies for the current session when browser storage is unavailable.
  }
}

export function App() {
  const [themeMode, setThemeMode] = useState<AppThemeMode>(() => readStoredThemeMode());
  const theme = useMemo(() => createAppTheme(themeMode), [themeMode]);
  const [authState, setAuthState] = useState<AuthState>({ status: "authenticated", username: null });
  const [activePage, setActivePage] = useState(() => pageFromRoute(currentRoute()));
  const [inputText, setInputText] = useState(
    "Ищем поставщика в Москве. Нужно 20 тонн до 12 мая, желательно с НДС."
  );
  const [job, setJob] = useState<EnrichmentJob | null>(null);
  const [events, setEvents] = useState<EnrichmentEvent[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [settingsTarget, setSettingsTarget] = useState<SettingsTarget | null>(() =>
    parseSettingsTargetHash(currentRoute())
  );
  const [analyticsMessageId, setAnalyticsMessageId] = useState<string | null>(() =>
    parseAnalyticsMessageId(currentRoute())
  );
  const [analyticsReviewMessageId, setAnalyticsReviewMessageId] = useState<string | null>(() =>
    parseAnalyticsReviewMessageId(currentRoute())
  );
  const [analyticsReviewReturnHash, setAnalyticsReviewReturnHash] = useState<string | null>(() =>
    parseAnalyticsReviewReturnHash(currentRoute())
  );
  const [settingsSection, setSettingsSection] = useState<SettingsSection>(() => {
    const route = currentRoute();
    const initialTarget = parseSettingsTargetHash(route);
    return initialTarget ? settingsSectionForTarget(initialTarget) : settingsSectionFromRoute(route);
  });
  const [settingsModalTarget, setSettingsModalTarget] = useState<SettingsTarget | null>(null);
  const [settingsSnapshot, setSettingsSnapshot] = useState<SettingsSnapshot | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const settingsSnapshotRef = useRef<SettingsSnapshot | null>(null);
  const settingsRequestRef = useRef<Promise<SettingsSnapshot> | null>(null);
  const handledTestingMessageIdRef = useRef<string | null>(null);

  const result = job?.result ?? null;
  const isProcessing = isSubmitting || job?.status === "queued" || job?.status === "running";
  const isNarrowScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const currentPage = settingsTarget ? 4 : activePage;
  const displayedPage = isWorkbenchPage(currentPage) ? 1 : currentPage;
  const visibleSettingsSnapshot = settingsSnapshot ?? settingsSnapshotRef.current;
  const themeToggleLabel = themeMode === "dark" ? "Включить светлую тему" : "Включить темную тему";
  const workspaceClassName = [
    "workspace",
    currentPage === 1 ? "workspace--queue" : "",
    currentPage === 12 ? "workspace--review" : ""
  ].filter(Boolean).join(" ");

  useEffect(() => {
    document.documentElement.dataset.colorScheme = themeMode;
    document.documentElement.style.colorScheme = themeMode;
    persistThemeMode(themeMode);
  }, [themeMode]);

  useEffect(() => {
    let active = true;
    async function checkAuth() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/auth/me`);
        if (!response.ok) {
          if (response.status === 401 && active) {
            setAuthState({ status: "anonymous", username: null });
          }
          return;
        }
        const payload = (await response.json()) as { authenticated: boolean; username?: string | null };
        if (active && payload.authenticated === true) {
          setAuthState(
            { status: "authenticated", username: payload.username ?? null }
          );
        } else if (active && payload.authenticated === false) {
          setAuthState({ status: "anonymous", username: null });
        }
      } catch {
        // Keep the current state during Vite/test reload races.
      }
    }

    void checkAuth();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    function handleRouteChange() {
      const route = currentRoute();
      setSettingsModalTarget(null);
      const testingMessageId = parseTestingMessageId(route);
      if (testingMessageId) {
        setSettingsTarget(null);
        setAnalyticsMessageId(null);
        setAnalyticsReviewMessageId(null);
        setActivePage(0);
        void loadAnalyticsMessageIntoTesting(testingMessageId);
        return;
      }
      const target = parseSettingsTargetHash(route);
      const reviewMessageId = parseAnalyticsReviewMessageId(route);
      setSettingsTarget(target);
      setAnalyticsReviewMessageId(reviewMessageId);
      setAnalyticsReviewReturnHash(reviewMessageId ? parseAnalyticsReviewReturnHash(route) : null);
      setAnalyticsMessageId(reviewMessageId ? null : parseAnalyticsMessageId(route));
      if (target) {
        setSettingsSection(settingsSectionForTarget(target));
        setActivePage(4);
      } else {
        setSettingsSection(settingsSectionFromRoute(route));
        setActivePage(pageFromRoute(route));
      }
    }
    handleRouteChange();
    window.addEventListener("hashchange", handleRouteChange);
    window.addEventListener("popstate", handleRouteChange);
    return () => {
      window.removeEventListener("hashchange", handleRouteChange);
      window.removeEventListener("popstate", handleRouteChange);
    };
  }, []);

  const loadSettingsSnapshot = useCallback(async (options: { commit?: boolean; force?: boolean } = {}): Promise<SettingsSnapshot> => {
    if (!options.force && settingsSnapshotRef.current) {
      const cachedSnapshot = settingsSnapshotRef.current;
      if (options.commit !== false) {
        startTransition(() => setSettingsSnapshot(cachedSnapshot));
      }
      return cachedSnapshot;
    }
    if (!options.force && settingsRequestRef.current) {
      return settingsRequestRef.current;
    }
    const request = (async () => {
      setSettingsLoading(true);
      setSettingsError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/settings`);
        if (!response.ok) {
          if (response.status === 401) {
            setAuthState({ status: "anonymous", username: null });
          }
          throw new Error(`Backend вернул ${response.status}`);
        }
        const snapshot = (await response.json()) as SettingsSnapshot;
        settingsSnapshotRef.current = snapshot;
        if (options.commit !== false) {
          startTransition(() => setSettingsSnapshot(snapshot));
        }
        return snapshot;
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "Не удалось загрузить настройки";
        setSettingsError(message);
        throw caught;
      } finally {
        setSettingsLoading(false);
        settingsRequestRef.current = null;
      }
    })();
    settingsRequestRef.current = request;
    return request;
  }, []);

  useEffect(() => {
    function handleOpenSettingsTarget(event: Event) {
      const target = (event as CustomEvent<SettingsTarget>).detail;
      setSettingsModalTarget(target);
      void loadSettingsSnapshot().catch(() => undefined);
    }
    window.addEventListener(openSettingsTargetEvent, handleOpenSettingsTarget);
    return () => window.removeEventListener(openSettingsTargetEvent, handleOpenSettingsTarget);
  }, [loadSettingsSnapshot]);

  useEffect(() => {
    if (authState.status === "authenticated") {
      void loadSettingsSnapshot({ commit: false }).catch(() => undefined);
    }
  }, [authState.status, loadSettingsSnapshot]);

  function updateSettingsSnapshot(snapshot: SettingsSnapshot) {
    settingsSnapshotRef.current = snapshot;
    startTransition(() => setSettingsSnapshot(snapshot));
    setSettingsError(null);
  }

  function updateNlpSettingsSnapshot(nlpSettings: unknown) {
    const currentSnapshot = settingsSnapshotRef.current;
    if (!currentSnapshot) {
      void loadSettingsSnapshot({ force: true }).catch(() => undefined);
      return;
    }
    updateSettingsSnapshot({
      ...currentSnapshot,
      nlp: nlpSettings as NlpSettings
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = inputText.trim();
    if (!text) {
      setError("Введите текст для анализа");
      return;
    }
    await startEnrichment(text);
  }

  async function startEnrichment(text: string) {
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

  async function loadAnalyticsMessageIntoTesting(messageId: string) {
    if (handledTestingMessageIdRef.current === messageId) {
      return;
    }
    handledTestingMessageIdRef.current = messageId;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const candidate = (await response.json()) as { text: string };
      setInputText(candidate.text);
      setActivePage(0);
      await startEnrichment(candidate.text);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить сообщение из аналитики");
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

  function handlePageChange(_: SyntheticEvent, value: number) {
    setSettingsTarget(null);
    setAnalyticsMessageId(null);
    setAnalyticsReviewMessageId(null);
    setAnalyticsReviewReturnHash(null);
    setActivePage(value);
    if (value === 4) {
      setSettingsSection((current) => current || "signals");
    }
    navigateRoute(pageRoute(value, value === 4 ? settingsSection : undefined));
  }

  function handleWorkbenchSectionChange(section: WorkbenchSection) {
    const currentReviewMessageId = analyticsReviewMessageId;
    const currentReviewReturnHash = analyticsReviewReturnHash;
    setSettingsTarget(null);
    setAnalyticsMessageId(null);
    if (section === "review") {
      setActivePage(12);
      if (currentReviewMessageId) {
        const returnQuery = currentReviewReturnHash ? `?return=${encodeURIComponent(currentReviewReturnHash)}` : "";
        navigateRoute(`/analytics/review/${encodeURIComponent(currentReviewMessageId)}${returnQuery}`);
      } else {
        setAnalyticsReviewMessageId(null);
        setAnalyticsReviewReturnHash(null);
        navigateRoute("/review");
      }
      return;
    }
    setAnalyticsReviewMessageId(null);
    setAnalyticsReviewReturnHash(null);
    if (section === "testing") {
      setActivePage(0);
      navigateRoute("/testing");
      return;
    }
    if (section === "constructor") {
      setActivePage(3);
      navigateRoute("/constructor");
      return;
    }
    setActivePage(1);
    navigateRoute("/analytics");
  }

  function openSettingsSection(section: SettingsSection) {
    setSettingsTarget(null);
    setSettingsSection(section);
    setActivePage(4);
    navigateRoute(settingsSectionRoute(section));
  }

  function handleSettingsSectionChange(section: SettingsSection) {
    setSettingsTarget(null);
    setSettingsSection(section);
    navigateRoute(settingsSectionRoute(section));
  }

  function openPageFromGuide(target: OperatorGuideRouteTarget) {
    setSettingsTarget(null);
    setAnalyticsMessageId(null);
    setAnalyticsReviewMessageId(null);
    setAnalyticsReviewReturnHash(null);
    if (target === "testing") {
      setActivePage(0);
      navigateRoute("/testing");
      return;
    }
    if (target === "analytics") {
      setActivePage(1);
      navigateRoute("/analytics");
      return;
    }
    if (target === "golden") {
      setActivePage(2);
      navigateRoute("/golden");
      return;
    }
    if (target === "constructor") {
      setActivePage(3);
      navigateRoute("/constructor");
      return;
    }
    if (target === "settings") {
      setActivePage(4);
      navigateRoute(settingsSectionRoute(settingsSection));
      return;
    }
    setActivePage(5);
    navigateRoute("/help");
  }

  async function handleLogin(username: string, password: string): Promise<void> {
    const response = await fetch(`${apiBaseUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    if (!response.ok) {
      throw new Error(response.status === 401 ? "Неверный логин или пароль" : `Backend вернул ${response.status}`);
    }
    const payload = (await response.json()) as { authenticated: boolean; username?: string | null };
    if (!payload.authenticated) {
      throw new Error("Backend не подтвердил авторизацию");
    }
    setAuthState({ status: "authenticated", username: payload.username ?? username });
    setActivePage(pageFromRoute(currentRoute()));
    await loadSettingsSnapshot({ force: true });
  }

  async function handleLogout(): Promise<void> {
    await fetch(`${apiBaseUrl}/api/v1/auth/logout`, { method: "POST" }).catch(() => undefined);
    eventSourceRef.current?.close();
    setAuthState({ status: "anonymous", username: null });
    setJob(null);
    setEvents([]);
  }

  if (authState.status === "anonymous") {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <LoginPage onLogin={handleLogin} />
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box className="app-shell">
        <AppBar position="sticky" color="default" elevation={0} className="top-bar">
          <Toolbar variant="dense" className="top-toolbar">
            <Box className="brand-lockup">
              <Box className="brand-mark" aria-hidden="true">
                <AutoAwesomeIcon color="primary" fontSize="small" />
              </Box>
              <Typography variant="subtitle1" component="h1" className="app-title">
                PUR Leads v2
              </Typography>
            </Box>
            <Tabs
              value={displayedPage}
              onChange={handlePageChange}
              className="main-nav"
              variant="scrollable"
              scrollButtons="auto"
              allowScrollButtonsMobile
              aria-label="Основная навигация"
            >
              <Tab value={1} icon={<RateReviewIcon fontSize="small" />} iconPosition="start" label="Рабочее место" />
              <Tab value={11} icon={<InsightsIcon fontSize="small" />} iconPosition="start" label="Аналитика" />
              <Tab value={10} icon={<SmartToyIcon fontSize="small" />} iconPosition="start" label="LLM" />
              <Tab value={2} icon={<StarIcon fontSize="small" />} iconPosition="start" label="Golden" />
              <Tab value={4} icon={<SettingsIcon fontSize="small" />} iconPosition="start" label="Настройки" />
              <Tab value={9} icon={<ArticleIcon fontSize="small" />} iconPosition="start" label="Как работать" />
              <Tab value={5} icon={<HelpOutlineIcon fontSize="small" />} iconPosition="start" label="Справка" />
              <Tab value={6} icon={<ArticleIcon fontSize="small" />} iconPosition="start" label="Проектная документация" />
              <Tab value={7} icon={<ReceiptLongIcon fontSize="small" />} iconPosition="start" label="Логи" />
              <Tab value={8} icon={<MonitorHeartIcon fontSize="small" />} iconPosition="start" label="Статус системы" />
            </Tabs>
            <Box className="top-actions">
              <Button
                size="small"
                variant="text"
                startIcon={<LogoutIcon />}
                onClick={() => void handleLogout()}
              >
                Выйти
              </Button>
              <Tooltip title={themeToggleLabel}>
                <IconButton
                  size="small"
                  color="inherit"
                  aria-label={themeToggleLabel}
                  onClick={() => setThemeMode((current) => (current === "dark" ? "light" : "dark"))}
                >
                  {themeMode === "dark" ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Toolbar>
        </AppBar>
        {settingsLoading && (
          <Box className="background-settings-loading" role="status" aria-live="polite">
            <LinearProgress className="background-settings-progress" />
            <Typography variant="caption">Загружаю настройки и словари</Typography>
          </Box>
        )}

        <Container component="main" aria-label="Рабочая область" maxWidth={false} className={workspaceClassName}>
          {isWorkbenchPage(currentPage) ? (
            <WorkbenchShell
              activeSection={workbenchSectionForPage(currentPage)}
              onSectionChange={handleWorkbenchSectionChange}
            >
              {currentPage === 12 ? (
                analyticsReviewMessageId ? (
                  <AnalyticsReviewPage
                    apiBaseUrl={apiBaseUrl}
                    messageId={analyticsReviewMessageId}
                    returnHash={analyticsReviewReturnHash}
                    nlpSettings={visibleSettingsSnapshot?.nlp ?? null}
                    onBack={() => {
                      navigateRoute(
                        analyticsReviewReturnHash ?? `/analytics/message/${encodeURIComponent(analyticsReviewMessageId)}`
                      );
                      setAnalyticsReviewMessageId(null);
                      setActivePage(1);
                    }}
                    onNlpSettingsChange={updateNlpSettingsSnapshot}
                  />
                ) : (
                  <ReviewEmptyState />
                )
              ) : currentPage === 0 ? (
                <TestingWorkspace
                  inputText={inputText}
                  onInputTextChange={setInputText}
                  onSubmit={handleSubmit}
                  isNarrowScreen={isNarrowScreen}
                  isProcessing={isProcessing}
                  isSubmitting={isSubmitting}
                  error={error}
                  job={job}
                  events={events}
                  result={result}
                  activeTab={activeTab}
                  onTabChange={handleTabChange}
                  onOpenSettings={openSettingsSection}
                />
              ) : currentPage === 3 ? (
                <ConfiguratorPage
                  settings={visibleSettingsSnapshot}
                  loading={settingsLoading}
                  loadError={settingsError}
                  loadSettings={loadSettingsSnapshot}
                  onSettingsSnapshotChange={updateSettingsSnapshot}
                />
              ) : (
                <AnalyticsPage
                  apiBaseUrl={apiBaseUrl}
                  focusMessageId={analyticsMessageId}
                  sectionScope="workspace"
                  onTestMessage={(candidate) => {
                    setSettingsTarget(null);
                    setAnalyticsMessageId(null);
                    setAnalyticsReviewMessageId(null);
                    setAnalyticsReviewReturnHash(null);
                    setInputText(candidate.text);
                    setActivePage(0);
                    navigateRoute("/testing");
                    void startEnrichment(candidate.text);
                  }}
                />
              )}
            </WorkbenchShell>
          ) : currentPage === 2 ? (
            <GoldenExamplesPage
              apiBaseUrl={apiBaseUrl}
              isNarrowScreen={isNarrowScreen}
              onOpenSettings={openSettingsSection}
            />
          ) : currentPage === 4 ? (
            <SettingsCenter
              section={settingsSection}
              activeTarget={settingsTarget}
              settings={visibleSettingsSnapshot}
              loading={settingsLoading}
              loadError={settingsError}
              loadSettings={loadSettingsSnapshot}
              onSettingsSnapshotChange={updateSettingsSnapshot}
              onSectionChange={handleSettingsSectionChange}
            />
          ) : currentPage === 10 ? (
            <LlmPage apiBaseUrl={apiBaseUrl} />
          ) : currentPage === 11 ? (
            <AnalyticsPage apiBaseUrl={apiBaseUrl} sectionScope="reports" />
          ) : currentPage === 9 ? (
            <OperatorGuidePage apiBaseUrl={apiBaseUrl} onNavigate={openPageFromGuide} />
          ) : currentPage === 5 ? (
            <SettingsHelpPage />
          ) : currentPage === 6 ? (
            <ProjectDocumentationPage apiBaseUrl={apiBaseUrl} />
          ) : currentPage === 7 ? (
            <RuntimeLogsPage apiBaseUrl={apiBaseUrl} />
          ) : (
            <SystemStatusPage apiBaseUrl={apiBaseUrl} />
          )}
        </Container>
        {settingsModalTarget && (
          <SettingsTargetDialog
            target={settingsModalTarget}
            settings={visibleSettingsSnapshot}
            loading={settingsLoading}
            error={settingsError}
            loadSettings={loadSettingsSnapshot}
            onClose={() => setSettingsModalTarget(null)}
            onOpenPage={(target) => {
              setSettingsModalTarget(null);
              navigateToSettingsTarget(target);
            }}
          />
        )}
      </Box>
    </ThemeProvider>
  );
}

function LoginPage({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onLogin(username, password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось войти");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box className="login-shell">
      <Paper component="form" onSubmit={handleSubmit} variant="outlined" className="login-panel">
        <Stack spacing={2}>
          <Box>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
              PUR Leads v2
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Вход в операторский интерфейс
            </Typography>
          </Box>
          <TextField
            label="Логин"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            fullWidth
          />
          <TextField
            label="Пароль"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
          <Button
            type="submit"
            variant="contained"
            disabled={submitting}
            startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : undefined}
          >
            Войти
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}

function ReviewEmptyState() {
  return (
    <Paper variant="outlined" className="review-empty-state">
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="h5" component="h2" sx={{ fontWeight: 750 }}>
            Разбор сообщения
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Выберите запись в очереди и откройте разбор, чтобы увидеть ревью, проверку, LLM и конструктор в одном рабочем экране.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          <Button variant="contained" onClick={() => navigateRoute("/analytics")}>
            Открыть очередь
          </Button>
          <Button variant="outlined" onClick={() => navigateRoute("/testing")}>
            Произвольная проверка
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}

function WorkbenchShell({
  activeSection,
  onSectionChange,
  children
}: {
  activeSection: WorkbenchSection;
  onSectionChange: (section: WorkbenchSection) => void;
  children: ReactNode;
}) {
  return (
    <Stack
      spacing={2}
      className={["workbench-shell", activeSection === "queue" ? "workbench-shell--queue" : ""]
        .filter(Boolean)
        .join(" ")}
    >
      <Paper variant="outlined" className="workspace-section-nav">
        <Tabs
          value={activeSection}
          onChange={(_, value) => onSectionChange(value as WorkbenchSection)}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
          aria-label="Разделы рабочего места"
        >
          <Tab value="queue" icon={<InsightsIcon fontSize="small" />} iconPosition="start" label="Очередь" />
          <Tab value="review" icon={<RateReviewIcon fontSize="small" />} iconPosition="start" label="Ревью" />
          <Tab value="testing" icon={<ScienceIcon fontSize="small" />} iconPosition="start" label="Проверка" />
          <Tab value="constructor" icon={<ConstructionIcon fontSize="small" />} iconPosition="start" label="Конструктор" />
        </Tabs>
      </Paper>
      {children}
    </Stack>
  );
}

function parseTestingMessageId(hash: string): string | null {
  const route = normalizeRoute(hash);
  if (!routeWithoutQuery(route).startsWith("/testing")) {
    return null;
  }
  const params = routeQuery(route);
  const messageId = params.get("message_id");
  return messageId?.trim() || null;
}

function parseAnalyticsMessageId(route: string): string | null {
  const parts = routeParts(route);
  if (parts[0] !== "analytics" || parts[1] !== "message") {
    return null;
  }
  return parts[2]?.trim() || null;
}

function parseAnalyticsReviewMessageId(route: string): string | null {
  const parts = routeParts(route);
  if (parts[0] === "review") {
    return parts[1]?.trim() || null;
  }
  if (parts[0] === "analytics" && parts[1] === "review") {
    return parts[2]?.trim() || null;
  }
  return null;
}

function parseAnalyticsReviewReturnHash(route: string): string | null {
  if (parseAnalyticsReviewMessageId(route) === null) {
    return null;
  }
  const params = routeQuery(route);
  const value = params.get("return")?.trim() ?? "";
  const normalized = normalizeRoute(value);
  return normalized.startsWith("/analytics") ? normalized : null;
}

function pageFromRoute(route: string): number {
  const normalizedRoute = normalizeRoute(route);
  const parts = routeParts(normalizedRoute);
  if (parseTestingMessageId(normalizedRoute) || parts[0] === "testing") {
    return 0;
  }
  if (parseSettingsTargetHash(normalizedRoute) || parts[0] === "settings") {
    return 4;
  }
  if (parts[0] === "guide") {
    return 9;
  }
  if (parts[0] === "golden") {
    return 2;
  }
  if (parts[0] === "llm") {
    return 10;
  }
  if (parts[0] === "review") {
    return 12;
  }
  if (parts[0] === "analytics" && parts[1] === "review") {
    return 12;
  }
  if (parts[0] === "analytics" && ["overview", "quality", "llm"].includes(parts[1] ?? "")) {
    return 11;
  }
  if (parts[0] === "configurator" || parts[0] === "constructor") {
    return 3;
  }
  if (parts[0] === "help") {
    return 5;
  }
  if (parts[0] === "project-docs") {
    return 6;
  }
  if (parts[0] === "logs") {
    return 7;
  }
  if (parts[0] === "status") {
    return 8;
  }
  return 1;
}

function navigateToSettingsTarget(target: SettingsTarget) {
  navigateRoute(settingsTargetHash(target));
}

function settingsSectionFromRoute(route: string): SettingsSection {
  const parts = routeParts(route);
  if (parts[0] !== "settings") {
    return "signals";
  }
  if (parts[1] === "pipeline") {
    return "pipeline";
  }
  if (parts[1] === "facts") {
    return "facts";
  }
  if (parts[1] === "aliases") {
    return "aliases";
  }
  if (parts[1] === "lead-scoring") {
    return "lead_scoring";
  }
  if (parts[1] === "solution-areas") {
    return "solution_areas";
  }
  if (parts[1] === "review-lanes") {
    return "review_lanes";
  }
  if (parts[1] === "schema") {
    return "dependency_graph";
  }
  if (parts[1] === "llm") {
    return "llm";
  }
  if (parts[1] === "notifications") {
    return "notifications";
  }
  if (parts[1] === "telegram-ingestion") {
    return "telegram_ingestion";
  }
  if (parts[1] === "runtime") {
    return "system";
  }
  return "signals";
}

function pageRoute(page: number, settingsSection?: SettingsSection): string {
  if (page === 0) {
    return "/testing";
  }
  if (page === 1) {
    return "/analytics";
  }
  if (page === 2) {
    return "/golden";
  }
  if (page === 4) {
    return settingsSectionRoute(settingsSection ?? "signals");
  }
  if (page === 5) {
    return "/help";
  }
  if (page === 6) {
    return "/project-docs";
  }
  if (page === 7) {
    return "/logs";
  }
  if (page === 8) {
    return "/status";
  }
  if (page === 9) {
    return "/guide";
  }
  if (page === 10) {
    return "/llm";
  }
  if (page === 11) {
    return "/analytics/overview";
  }
  if (page === 12) {
    return "/review";
  }
  return "/analytics";
}

function isWorkbenchPage(page: number): boolean {
  return page === 0 || page === 1 || page === 3 || page === 12;
}

function workbenchSectionForPage(page: number): WorkbenchSection {
  if (page === 0) {
    return "testing";
  }
  if (page === 3) {
    return "constructor";
  }
  if (page === 12) {
    return "review";
  }
  return "queue";
}

function settingsSectionRoute(section: SettingsSection): string {
  if (section === "pipeline") {
    return "/settings/pipeline";
  }
  if (section === "facts") {
    return "/settings/facts";
  }
  if (section === "aliases") {
    return "/settings/aliases";
  }
  if (section === "lead_scoring") {
    return "/settings/lead-scoring";
  }
  if (section === "solution_areas") {
    return "/settings/solution-areas";
  }
  if (section === "review_lanes") {
    return "/settings/review-lanes";
  }
  if (section === "dependency_graph") {
    return "/settings/schema";
  }
  if (section === "llm") {
    return "/settings/llm";
  }
  if (section === "notifications") {
    return "/settings/notifications";
  }
  if (section === "telegram_ingestion") {
    return "/settings/telegram-ingestion";
  }
  if (section === "system") {
    return "/settings/runtime";
  }
  return "/settings/signals";
}
