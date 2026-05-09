import ArticleIcon from "@mui/icons-material/Article";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsightsIcon from "@mui/icons-material/Insights";
import LightModeIcon from "@mui/icons-material/LightMode";
import LogoutIcon from "@mui/icons-material/Logout";
import SettingsIcon from "@mui/icons-material/Settings";
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
import { FormEvent, SyntheticEvent, startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AnalyticsPage, AnalyticsReviewPage } from "./AnalyticsPage";
import { LeadAssessmentSummary, TestingWorkspace } from "./enrichment/TestingWorkspace";
import type { EnrichmentEvent, EnrichmentJob, TextEnrichmentResult } from "./enrichment/types";
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
  const [activePage, setActivePage] = useState(() => (parseTestingMessageId(window.location.hash) ? 0 : 1));
  const [inputText, setInputText] = useState(
    "Ищем поставщика в Москве. Нужно 20 тонн до 12 мая, желательно с НДС."
  );
  const [job, setJob] = useState<EnrichmentJob | null>(null);
  const [events, setEvents] = useState<EnrichmentEvent[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [settingsTarget, setSettingsTarget] = useState<SettingsTarget | null>(() =>
    parseSettingsTargetHash(window.location.hash)
  );
  const [analyticsMessageId, setAnalyticsMessageId] = useState<string | null>(() =>
    parseAnalyticsMessageId(window.location.hash)
  );
  const [analyticsReviewMessageId, setAnalyticsReviewMessageId] = useState<string | null>(() =>
    parseAnalyticsReviewMessageId(window.location.hash)
  );
  const [analyticsReviewReturnHash, setAnalyticsReviewReturnHash] = useState<string | null>(() =>
    parseAnalyticsReviewReturnHash(window.location.hash)
  );
  const [settingsSection, setSettingsSection] = useState<SettingsSection>(() => {
    const initialTarget = parseSettingsTargetHash(window.location.hash);
    return initialTarget ? settingsSectionForTarget(initialTarget) : "signals";
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
  const currentPage = settingsTarget ? 2 : activePage;
  const displayedPage = currentPage;
  const visibleSettingsSnapshot = settingsSnapshot ?? settingsSnapshotRef.current;
  const themeToggleLabel = themeMode === "dark" ? "Включить светлую тему" : "Включить темную тему";

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
    function handleHashChange() {
      const testingMessageId = parseTestingMessageId(window.location.hash);
      if (testingMessageId) {
        setSettingsTarget(null);
        setAnalyticsMessageId(null);
        setAnalyticsReviewMessageId(null);
        setActivePage(0);
        void loadAnalyticsMessageIntoTesting(testingMessageId);
        return;
      }
      const target = parseSettingsTargetHash(window.location.hash);
      const reviewMessageId = parseAnalyticsReviewMessageId(window.location.hash);
      setSettingsTarget(target);
      setAnalyticsReviewMessageId(reviewMessageId);
      setAnalyticsReviewReturnHash(reviewMessageId ? parseAnalyticsReviewReturnHash(window.location.hash) : null);
      setAnalyticsMessageId(reviewMessageId ? null : parseAnalyticsMessageId(window.location.hash));
      if (target) {
        setSettingsSection(settingsSectionForTarget(target));
        setActivePage(2);
      } else if (window.location.hash.startsWith("#/analytics")) {
        setActivePage(1);
      }
    }
    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
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
    clearRoutedHash();
    setSettingsTarget(null);
    setAnalyticsMessageId(null);
    setAnalyticsReviewMessageId(null);
    setAnalyticsReviewReturnHash(null);
    setActivePage(value);
  }

  function openSettingsSection(section: SettingsSection) {
    clearSettingsHash();
    setSettingsTarget(null);
    setSettingsSection(section);
    setActivePage(2);
  }

  function handleSettingsSectionChange(section: SettingsSection) {
    clearSettingsHash();
    setSettingsTarget(null);
    setSettingsSection(section);
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
    setActivePage(1);
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
        <AppBar position="static" color="default" elevation={0} className="top-bar">
          <Toolbar variant="dense" className="top-toolbar">
            <AutoAwesomeIcon color="primary" fontSize="small" />
            <Typography variant="subtitle1" component="h1" className="app-title" sx={{ ml: 1, fontWeight: 700 }}>
              PUR Leads v2
            </Typography>
            <Tabs
              value={displayedPage}
              onChange={handlePageChange}
              className="main-nav"
              variant="scrollable"
              scrollButtons="auto"
              allowScrollButtonsMobile
              aria-label="Основная навигация"
            >
              <Tab label="Тестирование" />
              <Tab icon={<InsightsIcon fontSize="small" />} iconPosition="start" label="Аналитика" />
              <Tab icon={<SettingsIcon fontSize="small" />} iconPosition="start" label="Настройки" />
              <Tab icon={<HelpOutlineIcon fontSize="small" />} iconPosition="start" label="Справка" />
              <Tab icon={<ArticleIcon fontSize="small" />} iconPosition="start" label="Проектная документация" />
              <Tab label="Логи" />
              <Tab label="Статус системы" />
            </Tabs>
            <Button
              size="small"
              variant="text"
              startIcon={<LogoutIcon />}
              onClick={() => void handleLogout()}
              sx={{ ml: 1, whiteSpace: "nowrap" }}
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
          </Toolbar>
        </AppBar>
        {settingsLoading && (
          <Box className="background-settings-loading" role="status" aria-live="polite">
            <LinearProgress className="background-settings-progress" />
            <Typography variant="caption">Загружаю настройки и словари</Typography>
          </Box>
        )}

        <Container maxWidth={false} className="workspace">
          {currentPage === 0 ? (
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
          ) : currentPage === 1 ? (
            analyticsReviewMessageId ? (
              <AnalyticsReviewPage
                apiBaseUrl={apiBaseUrl}
                messageId={analyticsReviewMessageId}
                returnHash={analyticsReviewReturnHash}
                nlpSettings={visibleSettingsSnapshot?.nlp ?? null}
                onBack={() => {
                  window.location.hash =
                    analyticsReviewReturnHash ?? `#/analytics/message/${encodeURIComponent(analyticsReviewMessageId)}`;
                  setAnalyticsReviewMessageId(null);
                  setActivePage(1);
                }}
                onTestMessage={(candidate) => {
                  clearRoutedHash();
                  setSettingsTarget(null);
                  setAnalyticsMessageId(null);
                  setAnalyticsReviewMessageId(null);
                  setAnalyticsReviewReturnHash(null);
                  setInputText(candidate.text);
                  setActivePage(0);
                  void startEnrichment(candidate.text);
                }}
                onNlpSettingsChange={updateNlpSettingsSnapshot}
              />
            ) : (
              <AnalyticsPage
                apiBaseUrl={apiBaseUrl}
                focusMessageId={analyticsMessageId}
                onTestMessage={(candidate) => {
                  clearRoutedHash();
                  setSettingsTarget(null);
                  setAnalyticsMessageId(null);
                  setAnalyticsReviewMessageId(null);
                  setAnalyticsReviewReturnHash(null);
                  setInputText(candidate.text);
                  setActivePage(0);
                  void startEnrichment(candidate.text);
                }}
              />
            )
          ) : currentPage === 2 ? (
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
          ) : currentPage === 3 ? (
            <SettingsHelpPage />
          ) : currentPage === 4 ? (
            <ProjectDocumentationPage apiBaseUrl={apiBaseUrl} />
          ) : currentPage === 5 ? (
            <RuntimeLogsPage apiBaseUrl={apiBaseUrl} />
          ) : (
            <SystemStatusPage apiBaseUrl={apiBaseUrl} />
          )}
        </Container>
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

function parseTestingMessageId(hash: string): string | null {
  if (!hash.startsWith("#/testing")) {
    return null;
  }
  const queryIndex = hash.indexOf("?");
  if (queryIndex === -1) {
    return null;
  }
  const params = new URLSearchParams(hash.slice(queryIndex + 1));
  const messageId = params.get("message_id");
  return messageId?.trim() || null;
}

function parseAnalyticsMessageId(hash: string): string | null {
  const route = stripHashQuery(hash);
  const parts = route.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] !== "analytics" || parts[1] !== "message") {
    return null;
  }
  return parts[2]?.trim() || null;
}

function parseAnalyticsReviewMessageId(hash: string): string | null {
  const route = stripHashQuery(hash);
  const parts = route.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] !== "analytics" || parts[1] !== "review") {
    return null;
  }
  return parts[2]?.trim() || null;
}

function parseAnalyticsReviewReturnHash(hash: string): string | null {
  if (parseAnalyticsReviewMessageId(hash) === null) {
    return null;
  }
  const queryIndex = hash.indexOf("?");
  if (queryIndex === -1) {
    return null;
  }
  const params = new URLSearchParams(hash.slice(queryIndex + 1));
  const value = params.get("return")?.trim() ?? "";
  return value.startsWith("#/analytics") ? value : null;
}

function stripHashQuery(hash: string): string {
  const queryIndex = hash.indexOf("?");
  return queryIndex === -1 ? hash : hash.slice(0, queryIndex);
}

function navigateToSettingsTarget(target: SettingsTarget) {
  const hash = settingsTargetHash(target);
  if (window.location.hash === hash) {
    window.dispatchEvent(new Event("hashchange"));
    return;
  }
  window.location.hash = hash;
}

function clearSettingsHash() {
  if (window.location.hash.startsWith("#/settings/")) {
    window.history.pushState(null, "", `${window.location.pathname}${window.location.search}`);
  }
}

function clearRoutedHash() {
  if (
    window.location.hash.startsWith("#/settings/") ||
    window.location.hash.startsWith("#/analytics") ||
    window.location.hash.startsWith("#/testing")
  ) {
    window.history.pushState(null, "", `${window.location.pathname}${window.location.search}`);
  }
}
