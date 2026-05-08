import AddIcon from "@mui/icons-material/Add";
import ArticleIcon from "@mui/icons-material/Article";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ErrorIcon from "@mui/icons-material/Error";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsightsIcon from "@mui/icons-material/Insights";
import LogoutIcon from "@mui/icons-material/Logout";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import SaveIcon from "@mui/icons-material/Save";
import SendIcon from "@mui/icons-material/Send";
import SettingsIcon from "@mui/icons-material/Settings";
import VisibilityIcon from "@mui/icons-material/Visibility";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AppBar,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  CssBaseline,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Link as MuiLink,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
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
import type { ReactNode } from "react";

import { AnalyticsPage, AnalyticsReviewPage } from "./AnalyticsPage";

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
  explanation?: string | null;
  settings_refs?: SettingReference[];
};

type SettingReference = {
  section: string;
  key: string;
  label: string;
  kind: string;
  catalog?: string | null;
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

type LeadCategory = {
  type: string;
  label: string;
  matched_types: string[];
};

type LeadReason = {
  source: string;
  key: string;
  label: string;
  weight: number;
  matched_texts: string[];
};

type LeadAssessment = {
  is_lead: boolean;
  score: number;
  temperature: string;
  solution_areas: LeadCategory[];
  customer_segments: LeadCategory[];
  intent_signals: LeadCategory[];
  noise_signals: LeadCategory[];
  reasons: LeadReason[];
  review_lane?: LeadReviewLane | null;
};

type LeadReviewLane = {
  key: string;
  label: string;
  description?: string | null;
  matched_group_indexes: number[];
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
  lead_assessment?: LeadAssessment | null;
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

type AuthState = {
  status: "authenticated" | "anonymous";
  username?: string | null;
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

type PipelineStageSetting = {
  name: string;
  enabled: boolean;
};

type PatternTokenSetting = {
  predicate: "normalized";
  value: string;
};

type RulePatternSetting = {
  source_text?: string | null;
  tokens: PatternTokenSetting[];
};

type AliasMatchSetting = {
  catalog?: string | null;
  catalogs?: string[];
  keys?: string[];
  kinds?: string[];
};

type FactMatchSetting = {
  types: string[];
};

type RuleMatchSetting = {
  aliases: AliasMatchSetting[];
  facts: FactMatchSetting[];
};

type SemanticPatternResponse = {
  source_text: string;
  lemma_text: string;
  tokens: PatternTokenSetting[];
};

type RuleSetting = {
  type: string;
  label: string;
  group?: string | null;
  phrases: string[][];
  patterns: RulePatternSetting[];
  match?: RuleMatchSetting;
  color?: string | null;
  confidence?: number | null;
};

type AliasSetting = {
  key: string;
  canonical: string;
  type: "vendor" | "protocol" | "device" | "software" | "model";
  aliases: string[];
  fact_types: string[];
  color?: string | null;
  confidence?: number | null;
};

type LeadCategorySetting = {
  label: string;
  signal_types: string[];
  fact_types: string[];
};

type ReviewLaneMatchGroupSetting = {
  signal_types: string[];
  fact_types: string[];
  reason_keys: string[];
  solution_area_types: string[];
  customer_segment_types: string[];
  intent_signal_types: string[];
  noise_signal_types: string[];
};

type ReviewLaneSetting = {
  key: string;
  label: string;
  description?: string | null;
  priority: number;
  min_score?: number | null;
  max_score?: number | null;
  temperatures: string[];
  match_groups: ReviewLaneMatchGroupSetting[];
  excluded_signal_types: string[];
  excluded_fact_types: string[];
  excluded_reason_keys: string[];
  excluded_solution_area_types: string[];
  excluded_customer_segment_types: string[];
  excluded_intent_signal_types: string[];
  excluded_noise_signal_types: string[];
};

type LeadScoringSettings = {
  lead_threshold: number;
  warm_threshold: number;
  hot_threshold: number;
  signal_weights: Record<string, number>;
  fact_weights: Record<string, number>;
  solution_areas: Record<string, LeadCategorySetting>;
  customer_segments: Record<string, LeadCategorySetting>;
  intent_signal_types: string[];
  noise_signal_types: string[];
  review_lanes: ReviewLaneSetting[];
};

type AliasMatchingSettings = {
  normalize_separators: boolean;
  normalize_yo: boolean;
  normalize_latin_confusables: boolean;
  fuzzy_enabled: boolean;
  fuzzy_min_length: number;
  fuzzy_max_distance: number;
  fuzzy_long_min_length: number;
  fuzzy_long_max_distance: number;
  fuzzy_excluded_aliases: string[];
};

type NlpSettings = {
  pipeline: {
    stages: PipelineStageSetting[];
  };
  alias_matching?: AliasMatchingSettings;
  signals: RuleSetting[];
  facts: RuleSetting[];
  vendors: AliasSetting[];
  protocols: AliasSetting[];
  devices: AliasSetting[];
  software: AliasSetting[];
  lead_scoring: LeadScoringSettings;
  source?: {
    type: string;
    path: string;
    editable: boolean;
    revision?: number;
  };
};

type SystemSetting = {
  key: string;
  value: string;
  editable: boolean;
  sensitive?: boolean;
  source: string;
};

type TelegramBotSettings = {
  id: string;
  name: string;
  enabled: boolean;
  has_token: boolean;
  token_masked?: string | null;
  token?: string;
};

type TelegramChatSettings = {
  id: string;
  name: string;
  enabled: boolean;
  telegram_chat_id: string;
};

type NotificationRouteConditions = {
  is_lead?: boolean | null;
  score_min?: number | null;
  score_max?: number | null;
  temperatures: string[];
  review_lanes: string[];
  solution_areas: string[];
  customer_segments: string[];
  domain_signals: string[];
  facts: string[];
  reasons: string[];
  noise_signals: string[];
};

type NotificationRouteSettings = {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  bot_id: string;
  chat_id: string;
  match_mode: "all" | "any";
  conditions: NotificationRouteConditions;
  message_template: string;
};

type NotificationSettings = {
  bots: TelegramBotSettings[];
  chats: TelegramChatSettings[];
  routes: NotificationRouteSettings[];
  updated_at?: string | null;
};

type TelegramUserbotAccountSettings = {
  id: string;
  name: string;
  phone: string;
  api_id: number;
  enabled: boolean;
  status: string;
  has_api_hash: boolean;
  api_hash_masked?: string | null;
  has_session: boolean;
  last_error?: string | null;
  cooldown_until?: string | null;
  telegram_user_id?: string | null;
  telegram_username?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  api_hash?: string;
  session_string?: string;
};

type TelegramSourceChatSettings = {
  id: string;
  account_id: string;
  title: string;
  input_ref: string;
  telegram_chat_id?: string | null;
  enabled: boolean;
  status: string;
  last_message_id?: number | null;
  last_error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type TelegramIngestionSettings = {
  accounts: TelegramUserbotAccountSettings[];
  chats: TelegramSourceChatSettings[];
};

type SettingsSnapshot = {
  nlp: NlpSettings;
  notifications: NotificationSettings;
  telegram_ingestion: TelegramIngestionSettings;
  system: SystemSetting[];
};

type AliasCatalogName = "vendors" | "protocols" | "devices" | "software";

type SettingsSection =
  | "pipeline"
  | "signals"
  | "facts"
  | "aliases"
  | "lead_scoring"
  | "notifications"
  | "telegram_ingestion"
  | "system";

type SettingsTarget =
  | { kind: "signal"; key: string }
  | { kind: "fact"; key: string }
  | { kind: "alias"; catalog: AliasCatalogName; key: string }
  | { kind: "lead_signal_weight"; key: string }
  | { kind: "lead_fact_weight"; key: string }
  | { kind: "solution_area"; key: string }
  | { kind: "customer_segment"; key: string }
  | { kind: "review_lane"; key: string };

const defaultRouteMessageTemplate = [
  "Лид ПУР",
  "",
  "Оценка: {score} ({temperature})",
  "Очередь: {review_lane_label}",
  "Зоны решения: {solution_areas}",
  "Сегменты: {customer_segments}",
  "",
  "Почему сработало:",
  "{reasons_detailed}",
  "",
  "Текст:",
  "{text_preview}"
].join("\n");

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const openSettingsTargetEvent = "pur-open-settings-target";

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

  const loadSettingsSnapshot = useCallback(async (options: { force?: boolean } = {}): Promise<SettingsSnapshot> => {
    if (!options.force && settingsSnapshotRef.current) {
      return settingsSnapshotRef.current;
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
        startTransition(() => setSettingsSnapshot(snapshot));
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
      void loadSettingsSnapshot().catch(() => undefined);
    }
  }, [authState.status, loadSettingsSnapshot]);

  function updateSettingsSnapshot(snapshot: SettingsSnapshot) {
    settingsSnapshotRef.current = snapshot;
    startTransition(() => setSettingsSnapshot(snapshot));
    setSettingsError(null);
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
            <Box className="workspace-grid">
              <Paper component="form" onSubmit={handleSubmit} className="input-panel" variant="outlined">
                <Stack spacing={2}>
                  <Typography variant="h6">Входной текст</Typography>
                  <TextField
                    value={inputText}
                    onChange={(event) => setInputText(event.target.value)}
                    multiline
                    minRows={isNarrowScreen ? 8 : 16}
                    fullWidth
                    label="Произвольный текст"
                    slotProps={{ htmlInput: { "aria-label": "Текст для обогащения" } }}
                  />
                  <Button
                    className="primary-action"
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
                    <Tabs
                      value={activeTab}
                      onChange={handleTabChange}
                      variant="scrollable"
                      scrollButtons="auto"
                      allowScrollButtonsMobile
                      className="result-tabs"
                      aria-label="Разделы результата"
                    >
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
                      {activeTab === 0 && <Overview result={result} onOpenSettings={openSettingsSection} />}
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
          ) : currentPage === 1 ? (
            analyticsReviewMessageId ? (
              <AnalyticsReviewPage
                apiBaseUrl={apiBaseUrl}
                messageId={analyticsReviewMessageId}
                returnHash={analyticsReviewReturnHash}
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
            <ProjectDocumentationPage />
          ) : currentPage === 5 ? (
            <RuntimeLogsPage />
          ) : (
            <SystemStatusPage />
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

function RuntimeLogsPage() {
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
  }, [appliedFilters, limit, offset]);

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
              Последние события backend, userbot, worker и notification dispatcher.
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

function formatInteger(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function SystemStatusPage() {
  const [services, setServices] = useState<ServiceStatusItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  }, []);

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

function ProjectDocumentationPage() {
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
  }, []);

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
  }, [selectedPath]);

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
  messages_total: "Сообщений принято",
  next_cooldown_until: "Ближайший cooldown до",
  oldest_pending_at: "Самое старое ожидающее",
  outbox_by_status: "Уведомления по статусам",
  outbox_total: "Уведомлений всего",
  public_base_url: "Публичный URL",
  redis_ok: "Redis ping",
  source_chats_by_status: "Чаты по статусам",
  source_chats_enabled: "Чатов включено",
  source_chats_total: "Чатов-источников",
  status_checked_at: "Проверено",
  telegram_messages_enriched: "Сообщений видно в аналитике",
  telegram_messages_failed_enrichment: "Сообщений с ошибкой enrichment",
  telegram_messages_waiting_enrichment: "Сообщений ждут enrichment"
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

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium"
  }).format(new Date(value));
}

function SettingsCenter({
  section,
  activeTarget,
  settings,
  loading,
  loadError,
  loadSettings: loadSettingsSnapshot,
  onSettingsSnapshotChange,
  onSectionChange
}: {
  section: SettingsSection;
  activeTarget: SettingsTarget | null;
  settings: SettingsSnapshot | null;
  loading: boolean;
  loadError: string | null;
  loadSettings: (options?: { force?: boolean }) => Promise<SettingsSnapshot>;
  onSettingsSnapshotChange: (settings: SettingsSnapshot) => void;
  onSectionChange: (section: SettingsSection) => void;
}) {
  const [draft, setDraft] = useState<NlpSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState(
    "Подскажите, где можно заказать систему видеонаблюдения для квартиры?"
  );
  const [previewResult, setPreviewResult] = useState<TextEnrichmentResult | null>(null);
  const activeTargetElementId = activeTarget ? settingsTargetElementId(activeTarget) : null;
  const settingsReady = draft !== null;

  useEffect(() => {
    let active = true;
    async function loadInitialSettings() {
      setSettingsError(null);
      try {
        const snapshot = await loadSettingsSnapshot();
        if (active) {
          setDraft(snapshot.nlp);
        }
      } catch (caught) {
        if (active) {
          setSettingsError(caught instanceof Error ? caught.message : "Не удалось загрузить настройки");
        }
      }
    }
    void loadInitialSettings();
    return () => {
      active = false;
    };
  }, [loadSettingsSnapshot]);

  useEffect(() => {
    if (!activeTargetElementId || !settingsReady || loading) {
      return;
    }
    const timeout = window.setTimeout(() => {
      const element = document.getElementById(activeTargetElementId);
      if (typeof element?.scrollIntoView === "function") {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      if (element instanceof HTMLElement) {
        element.focus({ preventScroll: true });
      }
    }, 50);
    return () => window.clearTimeout(timeout);
  }, [activeTargetElementId, settingsReady, loading, section]);

  async function saveDraft() {
    if (!draft) {
      return;
    }
    setSaving(true);
    setSettingsError(null);
    setSettingsMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft)
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const saved = (await response.json()) as NlpSettings;
      if (settings) {
        onSettingsSnapshotChange({ ...settings, nlp: saved });
      } else {
        const snapshot = await loadSettingsSnapshot({ force: true });
        onSettingsSnapshotChange({ ...snapshot, nlp: saved });
      }
      setDraft(saved);
      setSettingsMessage("NLP-настройки сохранены. Следующая обработка возьмет новую конфигурацию.");
    } catch (caught) {
      setSettingsError(caught instanceof Error ? caught.message : "Не удалось сохранить настройки");
    } finally {
      setSaving(false);
    }
  }

  async function runPreview() {
    if (!draft || !previewText.trim()) {
      return;
    }
    setPreviewing(true);
    setSettingsError(null);
    setPreviewResult(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: previewText, nlp: draft })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      setPreviewResult((await response.json()) as TextEnrichmentResult);
    } catch (caught) {
      setSettingsError(caught instanceof Error ? caught.message : "Не удалось выполнить preview");
    } finally {
      setPreviewing(false);
    }
  }

  function updateDraft(next: NlpSettings) {
    setDraft(next);
    setSettingsMessage(null);
  }

  function updateStage(index: number, enabled: boolean) {
    if (!draft) {
      return;
    }
    updateDraft({
      ...draft,
      pipeline: {
        stages: draft.pipeline.stages.map((stage, itemIndex) =>
          itemIndex === index ? { ...stage, enabled } : stage
        )
      }
    });
  }

  function updateAliasMatching(aliasMatching: AliasMatchingSettings) {
    if (!draft) {
      return;
    }
    updateDraft({ ...draft, alias_matching: aliasMatching });
  }

  function updateRule(collection: "signals" | "facts", index: number, rule: RuleSetting) {
    if (!draft) {
      return;
    }
    updateDraft({
      ...draft,
      [collection]: draft[collection].map((item, itemIndex) => (itemIndex === index ? rule : item))
    });
  }

  function addRule(collection: "signals" | "facts") {
    if (!draft) {
      return;
    }
    const rule: RuleSetting = {
      type: collection === "signals" ? "new_signal" : "new_fact",
      label: collection === "signals" ? "Новый сигнал" : "Новый факт",
      group: collection === "signals" ? "Новые сигналы" : "Новые факты",
      color: collection === "signals" ? "#0b57d0" : null,
      confidence: 0.5,
      phrases: [["пример"]],
      patterns: [],
      match: { aliases: [], facts: [] }
    };
    updateDraft({ ...draft, [collection]: [...draft[collection], rule] });
  }

  function removeRule(collection: "signals" | "facts", index: number) {
    if (!draft) {
      return;
    }
    updateDraft({ ...draft, [collection]: draft[collection].filter((_, itemIndex) => itemIndex !== index) });
  }

  function updateAlias(catalog: AliasCatalogName, index: number, alias: AliasSetting) {
    if (!draft) {
      return;
    }
    updateDraft({
      ...draft,
      [catalog]: draft[catalog].map((item, itemIndex) => (itemIndex === index ? alias : item))
    });
  }

  function addAlias(catalog: AliasCatalogName) {
    if (!draft) {
      return;
    }
    const alias: AliasSetting = {
      key: `new_${catalog.slice(0, -1)}`,
      canonical: "Новый alias",
      type: aliasTypeForCatalog(catalog),
      aliases: ["новый alias"],
      fact_types: [aliasTypeForCatalog(catalog)],
      confidence: 0.7,
      color: null
    };
    updateDraft({ ...draft, [catalog]: [...draft[catalog], alias] });
  }

  function removeAlias(catalog: AliasCatalogName, index: number) {
    if (!draft) {
      return;
    }
    updateDraft({ ...draft, [catalog]: draft[catalog].filter((_, itemIndex) => itemIndex !== index) });
  }

  function updateLeadScoring(leadScoring: LeadScoringSettings) {
    if (!draft) {
      return;
    }
    updateDraft({ ...draft, lead_scoring: leadScoring });
  }

  function updateNotificationSettings(notifications: NotificationSettings) {
    if (!settings) {
      return;
    }
    onSettingsSnapshotChange({
      ...settings,
      notifications
    });
  }

  function updateTelegramIngestionSettings(telegramIngestion: TelegramIngestionSettings) {
    if (!settings) {
      return;
    }
    onSettingsSnapshotChange({
      ...settings,
      telegram_ingestion: telegramIngestion
    });
  }

  const dirty = draft !== null && JSON.stringify(settings?.nlp ?? null) !== JSON.stringify(draft);

  return (
    <Box className="settings-shell">
      <Paper variant="outlined" className="settings-sidebar">
        <Typography variant="subtitle2" color="text.secondary">
          Настройки
        </Typography>
        <Button
          fullWidth
          variant={section === "pipeline" ? "contained" : "text"}
          onClick={() => onSectionChange("pipeline")}
        >
          Pipeline
        </Button>
        <Button
          fullWidth
          variant={section === "signals" ? "contained" : "text"}
          onClick={() => onSectionChange("signals")}
        >
          Доменные сигналы
        </Button>
        <Button
          fullWidth
          variant={section === "facts" ? "contained" : "text"}
          onClick={() => onSectionChange("facts")}
        >
          Факты
        </Button>
        <Button
          fullWidth
          variant={section === "aliases" ? "contained" : "text"}
          onClick={() => onSectionChange("aliases")}
        >
          Словари
        </Button>
        <Button
          fullWidth
          variant={section === "lead_scoring" ? "contained" : "text"}
          onClick={() => onSectionChange("lead_scoring")}
        >
          Оценка лида
        </Button>
        <Button
          fullWidth
          variant={section === "notifications" ? "contained" : "text"}
          onClick={() => onSectionChange("notifications")}
        >
          Уведомления
        </Button>
        <Button
          fullWidth
          variant={section === "telegram_ingestion" ? "contained" : "text"}
          onClick={() => onSectionChange("telegram_ingestion")}
        >
          Telegram вход
        </Button>
        <Button
          fullWidth
          variant={section === "system" ? "contained" : "text"}
          onClick={() => onSectionChange("system")}
        >
          Runtime
        </Button>
      </Paper>

      <Stack spacing={2} className="settings-main">
        <Paper variant="outlined" className="settings-toolbar">
          <Box>
            <Typography variant="h6">Центр настроек</Typography>
            <Typography variant="body2" color="text.secondary">
              NLP/domain правила редактируются здесь; runtime-настройки показаны только для контроля.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} className="settings-actions">
            {dirty && <Chip label="Есть изменения" color="warning" size="small" />}
            <Button
              variant="contained"
              startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
              disabled={!draft || saving || !dirty}
              onClick={saveDraft}
            >
              Сохранить
            </Button>
          </Stack>
        </Paper>

        {loading && (
          <Paper variant="outlined" className="settings-panel">
            <LinearProgress />
            <Typography variant="body2" sx={{ mt: 1 }}>
              Загрузка настроек...
            </Typography>
          </Paper>
        )}
        {(loadError || settingsError) && <Alert severity="error">{settingsError ?? loadError}</Alert>}
        {settingsMessage && <Alert severity="success">{settingsMessage}</Alert>}

        {draft && !loading && (
          <Box className="settings-content-grid">
            <Paper variant="outlined" className="settings-panel">
              {section === "pipeline" && (
                <PipelineSettingsEditor
                  draft={draft}
                  onStageChange={updateStage}
                  onAliasMatchingChange={updateAliasMatching}
                />
              )}
              {section === "signals" && (
                <RuleCollectionEditor
                  title="Доменные сигналы"
                  collection="signals"
                  activeTarget={activeTarget}
                  settings={draft}
                  rules={draft.signals}
                  onAdd={addRule}
                  onRemove={removeRule}
                  onUpdate={updateRule}
                />
              )}
              {section === "facts" && (
                <RuleCollectionEditor
                  title="Факты"
                  collection="facts"
                  activeTarget={activeTarget}
                  settings={draft}
                  rules={draft.facts}
                  onAdd={addRule}
                  onRemove={removeRule}
                  onUpdate={updateRule}
                />
              )}
              {section === "aliases" && (
                <AliasCatalogsEditor
                  settings={draft}
                  activeTarget={activeTarget}
                  onAdd={addAlias}
                  onRemove={removeAlias}
                  onUpdate={updateAlias}
                />
              )}
              {section === "lead_scoring" && (
                <LeadScoringSettingsEditor
                  settings={draft.lead_scoring}
                  activeTarget={activeTarget}
                  onUpdate={updateLeadScoring}
                />
              )}
              {section === "notifications" && (
                <NotificationSettingsEditor
                  settings={settings?.notifications ?? defaultNotificationSettings()}
                  nlpSettings={draft}
                  onUpdate={updateNotificationSettings}
                />
              )}
              {section === "telegram_ingestion" && (
                <TelegramIngestionSettingsEditor
                  settings={settings?.telegram_ingestion ?? defaultTelegramIngestionSettings()}
                  onUpdate={updateTelegramIngestionSettings}
                />
              )}
              {section === "system" && <SystemSettingsTable settings={settings?.system ?? []} />}
            </Paper>

            <Paper variant="outlined" className="settings-panel">
              <Stack spacing={2}>
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Preview draft
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Проверяет текущие несохраненные настройки без сохранения.
                  </Typography>
                </Box>
                <TextField
                  value={previewText}
                  onChange={(event) => setPreviewText(event.target.value)}
                  label="Текст для проверки"
                  multiline
                  minRows={4}
                  fullWidth
                />
                <Button
                  variant="outlined"
                  startIcon={previewing ? <CircularProgress size={18} /> : <VisibilityIcon />}
                  disabled={previewing || !previewText.trim()}
                  onClick={runPreview}
                >
                  Проверить draft
                </Button>
                {previewResult && (
                  <Stack spacing={1}>
                    <Typography variant="subtitle2">Найдено</Typography>
                    {previewResult.lead_assessment && (
                      <LeadAssessmentSummary assessment={previewResult.lead_assessment} compact />
                    )}
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                      {[...previewResult.domain_signals, ...previewResult.facts].map((item) => (
                        <Chip key={`${item.type}-${item.text}-${item.range.start}`} label={`${item.label ?? item.type}: ${item.text}`} />
                      ))}
                    </Box>
                  </Stack>
                )}
              </Stack>
            </Paper>
          </Box>
        )}
      </Stack>
    </Box>
  );
}

function NotificationSettingsEditor({
  settings,
  nlpSettings,
  onUpdate
}: {
  settings: NotificationSettings;
  nlpSettings: NlpSettings;
  onUpdate: (settings: NotificationSettings) => void;
}) {
  const [tab, setTab] = useState(0);
  const [draft, setDraft] = useState<NotificationSettings>(() => notificationDraftFromSnapshot(settings));
  const [testMessage, setTestMessage] = useState("Проверка уведомлений PUR Leads v2");
  const [testBotId, setTestBotId] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const routeOptions = useMemo(() => notificationRouteOptions(nlpSettings), [nlpSettings]);

  useEffect(() => {
    setDraft(notificationDraftFromSnapshot(settings));
    setTestBotId(settings.bots[0]?.id ?? "");
  }, [settings]);

  async function saveNotificationSettings() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/notifications`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(notificationPayload(draft))
      });
      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }
      const saved = (await response.json()) as NotificationSettings;
      onUpdate(saved);
      setDraft(notificationDraftFromSnapshot(saved));
      setMessage("Настройки уведомлений сохранены");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить настройки уведомлений");
    } finally {
      setSaving(false);
    }
  }

  async function sendChatTestMessage(chat: TelegramChatSettings) {
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/notifications/telegram/chats/${chat.id}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_id: testBotId || draft.bots[0]?.id || "", message: testMessage })
      });
      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }
      const payload = (await response.json()) as { message: string };
      setMessage(payload.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отправить тестовое сообщение");
    } finally {
      setTesting(false);
    }
  }

  function updateBot(index: number, patch: Partial<TelegramBotSettings>) {
    setDraft({
      ...draft,
      bots: draft.bots.map((bot, itemIndex) => (itemIndex === index ? { ...bot, ...patch } : bot))
    });
  }

  function updateChat(index: number, patch: Partial<TelegramChatSettings>) {
    setDraft({
      ...draft,
      chats: draft.chats.map((chat, itemIndex) => (itemIndex === index ? { ...chat, ...patch } : chat))
    });
  }

  function updateRoute(index: number, patch: Partial<NotificationRouteSettings>) {
    setDraft({
      ...draft,
      routes: draft.routes.map((route, itemIndex) => (itemIndex === index ? { ...route, ...patch } : route))
    });
  }

  function updateRouteConditions(index: number, patch: Partial<NotificationRouteConditions>) {
    const route = draft.routes[index];
    updateRoute(index, { conditions: { ...route.conditions, ...patch } });
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h2">
          Уведомления
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Боты хранят Telegram-токены, чаты хранят адреса доставки, маршруты решают,
          куда отправлять сообщение по итогам enrichment. Batch-runner уведомления не отправляет.
        </Typography>
      </Box>
      {error && <Alert severity="error">{error}</Alert>}
      {message && <Alert severity="success">{message}</Alert>}
      <Tabs value={tab} onChange={(_, value: number) => setTab(value)} variant="scrollable">
        <Tab label="Боты" />
        <Tab label="Чаты" />
        <Tab label="Маршруты" />
      </Tabs>
      {tab === 0 && (
        <Stack spacing={1.5}>
          <Button
            startIcon={<AddIcon />}
            variant="outlined"
            onClick={() =>
              setDraft({
                ...draft,
                bots: [...draft.bots, newNotificationBot()]
              })
            }
          >
            Добавить бота
          </Button>
          {draft.bots.map((bot, index) => (
            <Paper key={`${bot.id}-${index}`} variant="outlined" className="settings-nested-panel">
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
                  <Typography variant="subtitle2">{bot.name || "Новый бот"}</Typography>
                  <IconButton
                    aria-label={`Удалить бота ${bot.name || bot.id}`}
                    onClick={() => setDraft({ ...draft, bots: draft.bots.filter((_, itemIndex) => itemIndex !== index) })}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <FormControlLabel
                  control={<Switch checked={bot.enabled} onChange={(event) => updateBot(index, { enabled: event.target.checked })} />}
                  label="Бот включен"
                />
                <Box className="settings-two-column">
                  <TextField value={bot.id} onChange={(event) => updateBot(index, { id: event.target.value })} label="ID бота" fullWidth />
                  <TextField value={bot.name} onChange={(event) => updateBot(index, { name: event.target.value })} label="Название бота" fullWidth />
                </Box>
                <TextField
                  value={bot.token ?? ""}
                  onChange={(event) => updateBot(index, { token: event.target.value })}
                  label="Токен бота"
                  type="password"
                  fullWidth
                  autoComplete="off"
                  helperText={
                    bot.has_token
                      ? `Сохранен: ${bot.token_masked}. Оставьте поле пустым, чтобы не менять токен.`
                      : "Введите токен бота из BotFather."
                  }
                />
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      {tab === 1 && (
        <Stack spacing={1.5}>
          <Button
            startIcon={<AddIcon />}
            variant="outlined"
            onClick={() =>
              setDraft({
                ...draft,
                chats: [...draft.chats, newNotificationChat()]
              })
            }
          >
            Добавить чат
          </Button>
          <TextField select value={testBotId} onChange={(event) => setTestBotId(event.target.value)} label="Бот для теста" fullWidth>
            {draft.bots.map((bot) => (
              <MenuItem key={bot.id} value={bot.id}>
                {bot.name || bot.id}
              </MenuItem>
            ))}
          </TextField>
          <TextField value={testMessage} onChange={(event) => setTestMessage(event.target.value)} label="Текст тестового сообщения" multiline minRows={2} fullWidth />
          {draft.chats.map((chat, index) => (
            <Paper key={`${chat.id}-${index}`} variant="outlined" className="settings-nested-panel">
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
                  <Typography variant="subtitle2">{chat.name || "Новый чат"}</Typography>
                  <IconButton
                    aria-label={`Удалить чат ${chat.name || chat.id}`}
                    onClick={() => setDraft({ ...draft, chats: draft.chats.filter((_, itemIndex) => itemIndex !== index) })}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <FormControlLabel
                  control={<Switch checked={chat.enabled} onChange={(event) => updateChat(index, { enabled: event.target.checked })} />}
                  label="Чат включен"
                />
                <Box className="settings-two-column">
                  <TextField value={chat.id} onChange={(event) => updateChat(index, { id: event.target.value })} label="ID чата" fullWidth />
                  <TextField value={chat.name} onChange={(event) => updateChat(index, { name: event.target.value })} label="Название чата" fullWidth />
                </Box>
                <TextField value={chat.telegram_chat_id} onChange={(event) => updateChat(index, { telegram_chat_id: event.target.value })} label="Telegram chat_id" fullWidth />
                <Button
                  variant="outlined"
                  startIcon={testing ? <CircularProgress size={18} /> : <SendIcon />}
                  disabled={testing || !testBotId}
                  onClick={() => sendChatTestMessage(chat)}
                >
                  Отправить тест в чат {chat.name || chat.id}
                </Button>
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      {tab === 2 && (
        <Stack spacing={1.5}>
          <Button
            startIcon={<AddIcon />}
            variant="outlined"
            onClick={() =>
              setDraft({
                ...draft,
                routes: [...draft.routes, newNotificationRoute(draft)]
              })
            }
          >
            Добавить маршрут
          </Button>
          {draft.routes.map((route, index) => (
            <Paper key={`${route.id}-${index}`} variant="outlined" className="settings-nested-panel">
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
                  <Typography variant="subtitle2">{route.name || "Новый маршрут"}</Typography>
                  <IconButton
                    aria-label={`Удалить маршрут ${route.name || route.id}`}
                    onClick={() => setDraft({ ...draft, routes: draft.routes.filter((_, itemIndex) => itemIndex !== index) })}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <FormControlLabel
                  control={<Switch checked={route.enabled} onChange={(event) => updateRoute(index, { enabled: event.target.checked })} />}
                  label="Маршрут включен"
                />
                <Box className="settings-two-column">
                  <TextField value={route.id} onChange={(event) => updateRoute(index, { id: event.target.value })} label="ID маршрута" fullWidth />
                  <TextField value={route.name} onChange={(event) => updateRoute(index, { name: event.target.value })} label="Название маршрута" fullWidth />
                  <TextField value={route.priority} onChange={(event) => updateRoute(index, { priority: Number(event.target.value) })} label="Приоритет" type="number" fullWidth />
                  <TextField select value={route.match_mode} onChange={(event) => updateRoute(index, { match_mode: event.target.value as "all" | "any" })} label="Режим условий" fullWidth>
                    <MenuItem value="all">Все условия</MenuItem>
                    <MenuItem value="any">Любое условие</MenuItem>
                  </TextField>
                  <TextField select value={route.bot_id} onChange={(event) => updateRoute(index, { bot_id: event.target.value })} label="Бот" fullWidth>
                    {draft.bots.map((bot) => (
                      <MenuItem key={bot.id} value={bot.id}>
                        {bot.name || bot.id}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField select value={route.chat_id} onChange={(event) => updateRoute(index, { chat_id: event.target.value })} label="Чат" fullWidth>
                    {draft.chats.map((chat) => (
                      <MenuItem key={chat.id} value={chat.id}>
                        {chat.name || chat.id}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField value={route.conditions.score_min ?? ""} onChange={(event) => updateRouteConditions(index, { score_min: optionalNumber(event.target.value) })} label="Минимальный score" type="number" fullWidth />
                  <TextField value={route.conditions.score_max ?? ""} onChange={(event) => updateRouteConditions(index, { score_max: optionalNumber(event.target.value) })} label="Максимальный score" type="number" fullWidth />
                </Box>
                <FormControlLabel
                  control={<Switch checked={route.conditions.is_lead === true} onChange={(event) => updateRouteConditions(index, { is_lead: event.target.checked ? true : null })} />}
                  label="Только лиды"
                />
                <NotificationMultiSelect label="Температура" options={routeOptions.temperatures} value={route.conditions.temperatures} onChange={(value) => updateRouteConditions(index, { temperatures: value })} />
                <NotificationMultiSelect label="Очереди разбора" options={routeOptions.review_lanes} value={route.conditions.review_lanes} onChange={(value) => updateRouteConditions(index, { review_lanes: value })} />
                <NotificationMultiSelect label="Направления решений" options={routeOptions.solution_areas} value={route.conditions.solution_areas} onChange={(value) => updateRouteConditions(index, { solution_areas: value })} />
                <NotificationMultiSelect label="Сегменты клиентов" options={routeOptions.customer_segments} value={route.conditions.customer_segments} onChange={(value) => updateRouteConditions(index, { customer_segments: value })} />
                <NotificationMultiSelect label="Доменные сигналы" options={routeOptions.domain_signals} value={route.conditions.domain_signals} onChange={(value) => updateRouteConditions(index, { domain_signals: value })} />
                <NotificationMultiSelect label="Факты" options={routeOptions.facts} value={route.conditions.facts} onChange={(value) => updateRouteConditions(index, { facts: value })} />
                <NotificationMultiSelect label="Причины score" options={routeOptions.reasons} value={route.conditions.reasons} onChange={(value) => updateRouteConditions(index, { reasons: value })} />
                <NotificationMultiSelect label="Шумовые сигналы" options={routeOptions.noise_signals} value={route.conditions.noise_signals} onChange={(value) => updateRouteConditions(index, { noise_signals: value })} />
                <TextField
                  value={route.message_template}
                  onChange={(event) => updateRoute(index, { message_template: event.target.value })}
                  label="Шаблон сообщения"
                  helperText="Доступны: {score}, {temperature}, {review_lane_label}, {solution_areas}, {customer_segments}, {reasons_detailed}, {text_preview}, {telegram_message_url}, {app_message_url}."
                  multiline
                  minRows={8}
                  fullWidth
                />
                <Box>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => updateRoute(index, { message_template: defaultRouteMessageTemplate })}
                  >
                    Вставить шаблон по умолчанию
                  </Button>
                </Box>
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          disabled={saving}
          onClick={saveNotificationSettings}
        >
          Сохранить уведомления
        </Button>
      </Stack>
    </Stack>
  );
}

function TelegramIngestionSettingsEditor({
  settings,
  onUpdate
}: {
  settings: TelegramIngestionSettings;
  onUpdate: (settings: TelegramIngestionSettings) => void;
}) {
  const [tab, setTab] = useState(0);
  const [draft, setDraft] = useState<TelegramIngestionSettings>(() => telegramIngestionDraftFromSnapshot(settings));
  const [loginCodes, setLoginCodes] = useState<Record<string, string>>({});
  const [loginPasswords, setLoginPasswords] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busyAccountId, setBusyAccountId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setDraft(telegramIngestionDraftFromSnapshot(settings));
  }, [settings]);

  async function saveTelegramIngestionSettings(nextDraft: TelegramIngestionSettings = draft) {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/telegram-ingestion`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(telegramIngestionPayload(nextDraft))
      });
      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }
      const saved = (await response.json()) as TelegramIngestionSettings;
      onUpdate(saved);
      setDraft(telegramIngestionDraftFromSnapshot(saved));
      setMessage("Настройки Telegram входа сохранены");
      return saved;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить Telegram вход");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function refreshTelegramIngestionStatus() {
    setRefreshing(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/telegram-ingestion`);
      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }
      const refreshed = (await response.json()) as TelegramIngestionSettings;
      onUpdate(refreshed);
      setDraft(telegramIngestionDraftFromSnapshot(refreshed));
      setMessage("Статусы Telegram входа обновлены");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось обновить статусы Telegram входа");
    } finally {
      setRefreshing(false);
    }
  }

  async function sendLoginCode(account: TelegramUserbotAccountSettings) {
    const saved = await saveTelegramIngestionSettings();
    if (!saved) {
      return;
    }
    setBusyAccountId(account.id);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/telegram-ingestion/accounts/${account.id}/send-code`, {
        method: "POST"
      });
      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }
      const payload = (await response.json()) as { account: TelegramUserbotAccountSettings };
      const next = replaceTelegramAccount(saved, payload.account);
      onUpdate(next);
      setDraft(telegramIngestionDraftFromSnapshot(next));
      setMessage("Код Telegram отправлен");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отправить код Telegram");
    } finally {
      setBusyAccountId(null);
    }
  }

  async function completeLogin(account: TelegramUserbotAccountSettings) {
    setBusyAccountId(account.id);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/telegram-ingestion/accounts/${account.id}/sign-in`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: loginCodes[account.id] ?? "",
          password: loginPasswords[account.id] || null
        })
      });
      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }
      const payload = (await response.json()) as { account: TelegramUserbotAccountSettings };
      const next = replaceTelegramAccount(draft, payload.account);
      onUpdate(next);
      setDraft(telegramIngestionDraftFromSnapshot(next));
      setLoginCodes({ ...loginCodes, [account.id]: "" });
      setLoginPasswords({ ...loginPasswords, [account.id]: "" });
      setMessage("Telegram userbot авторизован");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось завершить вход Telegram");
    } finally {
      setBusyAccountId(null);
    }
  }

  function updateAccount(index: number, patch: Partial<TelegramUserbotAccountSettings>) {
    setDraft({
      ...draft,
      accounts: draft.accounts.map((account, itemIndex) => (itemIndex === index ? { ...account, ...patch } : account))
    });
  }

  function updateChat(index: number, patch: Partial<TelegramSourceChatSettings>) {
    setDraft({
      ...draft,
      chats: draft.chats.map((chat, itemIndex) => (itemIndex === index ? { ...chat, ...patch } : chat))
    });
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h2">
          Telegram вход
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Userbot читает исходные чаты, сохраняет сообщения и создает обычные enrichment jobs.
          Уведомления потом уходят через отдельный bot dispatcher пачками.
        </Typography>
      </Box>
      {error && <Alert severity="error">{error}</Alert>}
      {message && <Alert severity="success">{message}</Alert>}
      <Alert severity="info">
        Кнопка "Сохранить Telegram вход" сохраняет и userbot аккаунты, и чаты-источники.
        `draft` у чата-источника означает, что строка сохранена, но userbot еще не успел
        резолвить `input_ref`. После первого polling статус станет `resolved`, появятся
        найденный Telegram chat_id и cursor `last_message_id`. Для актуального состояния
        нажмите "Обновить статус".
      </Alert>
      {(saving || refreshing || busyAccountId) && <LinearProgress />}
      <Tabs value={tab} onChange={(_, value: number) => setTab(value)} variant="scrollable">
        <Tab label="Аккаунты" />
        <Tab label="Чаты-источники" />
      </Tabs>

      {tab === 0 && (
        <Stack spacing={1.5}>
          <Button
            startIcon={<AddIcon />}
            variant="outlined"
            onClick={() => setDraft({ ...draft, accounts: [...draft.accounts, newTelegramAccount()] })}
          >
            Добавить userbot
          </Button>
          {draft.accounts.map((account, index) => (
            <Paper key={`${account.id}-${index}`} variant="outlined" className="settings-nested-panel">
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
                  <Box>
                    <Typography variant="subtitle2">{account.name || "Новый userbot"}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Статус: {account.status}
                      {account.telegram_username ? `, @${account.telegram_username}` : ""}
                      {account.cooldown_until ? `, cooldown до ${formatDateTime(account.cooldown_until)}` : ""}
                    </Typography>
                  </Box>
                  <IconButton
                    aria-label={`Удалить userbot ${account.name || account.id}`}
                    onClick={() => setDraft({ ...draft, accounts: draft.accounts.filter((_, itemIndex) => itemIndex !== index) })}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <FormControlLabel
                  control={<Switch checked={account.enabled} onChange={(event) => updateAccount(index, { enabled: event.target.checked })} />}
                  label="Userbot включен"
                />
                <Box className="settings-two-column">
                  <TextField value={account.id} onChange={(event) => updateAccount(index, { id: event.target.value })} label="ID аккаунта" fullWidth />
                  <TextField value={account.name} onChange={(event) => updateAccount(index, { name: event.target.value })} label="Название аккаунта" fullWidth />
                  <TextField value={account.phone} onChange={(event) => updateAccount(index, { phone: event.target.value })} label="Телефон" fullWidth />
                  <TextField value={account.api_id} onChange={(event) => updateAccount(index, { api_id: Number(event.target.value) })} label="Telegram app api_id" type="number" fullWidth />
                </Box>
                <TextField
                  value={account.api_hash ?? ""}
                  onChange={(event) => updateAccount(index, { api_hash: event.target.value })}
                  label="Telegram app api_hash"
                  type="password"
                  fullWidth
                  autoComplete="off"
                  helperText={
                    account.has_api_hash
                      ? `Сохранен: ${account.api_hash_masked}. Оставьте поле пустым, чтобы не менять api_hash.`
                      : "Введите api_hash приложения Telegram."
                  }
                />
                <Box className="settings-two-column">
                  <TextField
                    value={loginCodes[account.id] ?? ""}
                    onChange={(event) => setLoginCodes({ ...loginCodes, [account.id]: event.target.value })}
                    label="Код из Telegram"
                    fullWidth
                  />
                  <TextField
                    value={loginPasswords[account.id] ?? ""}
                    onChange={(event) => setLoginPasswords({ ...loginPasswords, [account.id]: event.target.value })}
                    label="2FA пароль"
                    type="password"
                    fullWidth
                    autoComplete="off"
                  />
                </Box>
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                  <Button
                    variant="outlined"
                    startIcon={busyAccountId === account.id ? <CircularProgress size={18} /> : <SendIcon />}
                    disabled={busyAccountId === account.id || saving}
                    onClick={() => sendLoginCode(account)}
                  >
                    Отправить код
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={busyAccountId === account.id ? <CircularProgress size={18} /> : <CheckCircleIcon />}
                    disabled={busyAccountId === account.id || !(loginCodes[account.id] ?? "").trim()}
                    onClick={() => completeLogin(account)}
                  >
                    Завершить вход
                  </Button>
                  <Chip
                    size="small"
                    color={account.has_session ? "success" : "default"}
                    label={account.has_session ? "session сохранена" : "session нет"}
                  />
                  {account.cooldown_until && (
                    <Chip
                      size="small"
                      color="warning"
                      label={`cooldown до ${formatDateTime(account.cooldown_until)}`}
                    />
                  )}
                </Stack>
                {account.last_error && <Alert severity="warning">{account.last_error}</Alert>}
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}

      {tab === 1 && (
        <Stack spacing={1.5}>
          <Button
            startIcon={<AddIcon />}
            variant="outlined"
            onClick={() => setDraft({ ...draft, chats: [...draft.chats, newTelegramSourceChat(draft)] })}
            disabled={draft.accounts.length === 0}
          >
            Добавить чат-источник
          </Button>
          {draft.chats.map((chat, index) => (
            <Paper key={`${chat.id}-${index}`} variant="outlined" className="settings-nested-panel">
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
                  <Box>
                    <Typography variant="subtitle2">{chat.title || "Новый чат"}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Статус: {chat.status}
                      {chat.last_message_id ? `, cursor ${chat.last_message_id}` : ""}
                    </Typography>
                  </Box>
                  <IconButton
                    aria-label={`Удалить чат-источник ${chat.title || chat.id}`}
                    onClick={() => setDraft({ ...draft, chats: draft.chats.filter((_, itemIndex) => itemIndex !== index) })}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <FormControlLabel
                  control={<Switch checked={chat.enabled} onChange={(event) => updateChat(index, { enabled: event.target.checked })} />}
                  label="Чат включен"
                />
                <Box className="settings-two-column">
                  <TextField value={chat.id} onChange={(event) => updateChat(index, { id: event.target.value })} label="ID источника" fullWidth />
                  <TextField value={chat.title} onChange={(event) => updateChat(index, { title: event.target.value })} label="Название источника" fullWidth />
                  <TextField select value={chat.account_id} onChange={(event) => updateChat(index, { account_id: event.target.value })} label="Userbot аккаунт" fullWidth>
                    {draft.accounts.map((account) => (
                      <MenuItem key={account.id} value={account.id}>
                        {account.name || account.id}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField value={chat.input_ref} onChange={(event) => updateChat(index, { input_ref: event.target.value })} label="Telegram input_ref" fullWidth />
                  <TextField value={chat.telegram_chat_id ?? ""} onChange={(event) => updateChat(index, { telegram_chat_id: event.target.value })} label="Resolved chat_id" fullWidth />
                </Box>
                {chat.last_error && <Alert severity="warning">{chat.last_error}</Alert>}
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}

      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          disabled={saving}
          onClick={() => void saveTelegramIngestionSettings()}
        >
          Сохранить Telegram вход
        </Button>
        <Button
          variant="outlined"
          startIcon={refreshing ? <CircularProgress size={18} /> : <RefreshIcon />}
          disabled={refreshing}
          onClick={refreshTelegramIngestionStatus}
        >
          Обновить статус
        </Button>
      </Stack>
    </Stack>
  );
}

function defaultTelegramIngestionSettings(): TelegramIngestionSettings {
  return { accounts: [], chats: [] };
}

function telegramIngestionDraftFromSnapshot(settings: TelegramIngestionSettings): TelegramIngestionSettings {
  return {
    accounts: settings.accounts.map((account) => ({ ...account, api_hash: "", session_string: "" })),
    chats: settings.chats.map((chat) => ({ ...chat }))
  };
}

function telegramIngestionPayload(settings: TelegramIngestionSettings) {
  return {
    accounts: settings.accounts.map((account) => ({
      id: account.id,
      name: account.name,
      phone: account.phone,
      api_id: account.api_id,
      api_hash: account.api_hash ?? "",
      session_string: account.session_string ?? "",
      enabled: account.enabled,
      status: account.status === "authorized" ? "authorized" : account.status === "code_sent" ? "code_sent" : "draft"
    })),
    chats: settings.chats.map((chat) => ({
      id: chat.id,
      account_id: chat.account_id,
      title: chat.title,
      input_ref: chat.input_ref,
      telegram_chat_id: chat.telegram_chat_id ?? "",
      enabled: chat.enabled,
      status: chat.status === "resolved" ? "resolved" : "draft"
    }))
  };
}

function newTelegramAccount(): TelegramUserbotAccountSettings {
  return {
    id: newClientUuid(),
    name: "Основной userbot",
    phone: "",
    api_id: 0,
    enabled: true,
    status: "draft",
    has_api_hash: false,
    api_hash_masked: null,
    has_session: false,
    last_error: null,
    telegram_user_id: null,
    telegram_username: null,
    cooldown_until: null,
    api_hash: "",
    session_string: ""
  };
}

function newTelegramSourceChat(settings: TelegramIngestionSettings): TelegramSourceChatSettings {
  return {
    id: newClientUuid(),
    account_id: settings.accounts[0]?.id ?? "",
    title: "Новый источник",
    input_ref: "",
    telegram_chat_id: "",
    enabled: true,
    status: "draft",
    last_message_id: null,
    last_error: null
  };
}

function replaceTelegramAccount(
  settings: TelegramIngestionSettings,
  account: TelegramUserbotAccountSettings
): TelegramIngestionSettings {
  return {
    ...settings,
    accounts: settings.accounts.map((item) => (item.id === account.id ? account : item))
  };
}

function newClientUuid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (char) =>
    (Number(char) ^ (Math.random() * 16) >> (Number(char) / 4)).toString(16)
  );
}

function defaultNotificationSettings(): NotificationSettings {
  return {
    bots: [],
    chats: [],
    routes: [],
    updated_at: null
  };
}

function notificationDraftFromSnapshot(settings: NotificationSettings): NotificationSettings {
  return {
    bots: settings.bots.map((bot) => ({ ...bot, token: "" })),
    chats: settings.chats.map((chat) => ({ ...chat })),
    routes: settings.routes.map((route) => ({
      ...route,
      conditions: normalizeNotificationConditions(route.conditions)
    })),
    updated_at: settings.updated_at ?? null
  };
}

function notificationPayload(settings: NotificationSettings) {
  return {
    bots: settings.bots.map((bot) => ({
      id: bot.id,
      name: bot.name,
      enabled: bot.enabled,
      token: bot.token ?? ""
    })),
    chats: settings.chats.map((chat) => ({
      id: chat.id,
      name: chat.name,
      enabled: chat.enabled,
      telegram_chat_id: chat.telegram_chat_id
    })),
    routes: settings.routes.map((route) => ({
      id: route.id,
      name: route.name,
      enabled: route.enabled,
      priority: route.priority,
      bot_id: route.bot_id,
      chat_id: route.chat_id,
      match_mode: route.match_mode,
      conditions: normalizeNotificationConditions(route.conditions),
      message_template: route.message_template
    }))
  };
}

function newNotificationBot(): TelegramBotSettings {
  return { id: "main_bot", name: "Основной бот", enabled: true, has_token: false, token_masked: null, token: "" };
}

function newNotificationChat(): TelegramChatSettings {
  return { id: "sales_chat", name: "Продажи", enabled: true, telegram_chat_id: "" };
}

function newNotificationRoute(settings: NotificationSettings): NotificationRouteSettings {
  return {
    id: "hot_leads",
    name: "Горячие лиды",
    enabled: true,
    priority: 100,
    bot_id: settings.bots[0]?.id ?? "",
    chat_id: settings.chats[0]?.id ?? "",
    match_mode: "all",
    conditions: normalizeNotificationConditions({ is_lead: true, score_min: 80 }),
    message_template: defaultRouteMessageTemplate
  };
}

function normalizeNotificationConditions(
  conditions: Partial<NotificationRouteConditions>
): NotificationRouteConditions {
  return {
    is_lead: conditions.is_lead ?? null,
    score_min: conditions.score_min ?? null,
    score_max: conditions.score_max ?? null,
    temperatures: conditions.temperatures ?? [],
    review_lanes: conditions.review_lanes ?? [],
    solution_areas: conditions.solution_areas ?? [],
    customer_segments: conditions.customer_segments ?? [],
    domain_signals: conditions.domain_signals ?? [],
    facts: conditions.facts ?? [],
    reasons: conditions.reasons ?? [],
    noise_signals: conditions.noise_signals ?? []
  };
}

function optionalNumber(value: string): number | null {
  return value.trim() ? Number(value) : null;
}

type NotificationOption = {
  key: string;
  label: string;
};

function NotificationMultiSelect({
  label,
  options,
  value,
  onChange
}: {
  label: string;
  options: NotificationOption[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const selected = options.filter((option) => value.includes(option.key));
  return (
    <Autocomplete
      multiple
      options={options}
      value={selected}
      getOptionLabel={(option) => option.label}
      isOptionEqualToValue={(option, selectedOption) => option.key === selectedOption.key}
      onChange={(_, nextValue) => onChange(nextValue.map((option) => option.key))}
      renderInput={(params) => <TextField {...params} label={label} />}
    />
  );
}

function notificationRouteOptions(settings: NlpSettings) {
  const signalOptions = settings.signals.map((signal) => ({ key: signal.type, label: signal.label }));
  const factOptions = settings.facts.map((fact) => ({ key: fact.type, label: fact.label }));
  return {
    temperatures: [
      { key: "cold", label: "cold" },
      { key: "warm", label: "warm" },
      { key: "hot", label: "hot" }
    ],
    review_lanes: settings.lead_scoring.review_lanes.map((lane) => ({
      key: lane.key,
      label: lane.label
    })),
    solution_areas: Object.entries(settings.lead_scoring.solution_areas).map(([key, value]) => ({
      key,
      label: value.label
    })),
    customer_segments: Object.entries(settings.lead_scoring.customer_segments).map(([key, value]) => ({
      key,
      label: value.label
    })),
    domain_signals: signalOptions,
    facts: factOptions,
    reasons: [...signalOptions, ...factOptions],
    noise_signals: signalOptions
  };
}

async function readBackendError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // Keep the generic HTTP status below when the backend response is not JSON.
  }
  return `Backend вернул ${response.status}`;
}

function SettingsTargetDialog({
  target,
  settings,
  loading,
  error,
  loadSettings,
  onClose,
  onOpenPage
}: {
  target: SettingsTarget | null;
  settings: SettingsSnapshot | null;
  loading: boolean;
  error: string | null;
  loadSettings: (options?: { force?: boolean }) => Promise<SettingsSnapshot>;
  onClose: () => void;
  onOpenPage: (target: SettingsTarget) => void;
}) {
  useEffect(() => {
    if (!target) {
      return;
    }
    void loadSettings().catch(() => undefined);
  }, [target, loadSettings]);

  const title = target && settings ? settingsTargetTitle(target, settings.nlp) : "Настройка";

  return (
    <Dialog
      open={target !== null}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      transitionDuration={0}
      aria-labelledby="settings-target-dialog-title"
    >
      <DialogTitle id="settings-target-dialog-title">{title}</DialogTitle>
      <DialogContent dividers className="settings-target-dialog-content">
        <Stack spacing={2}>
          {loading && <LinearProgress />}
          {error && <Alert severity="error">{error}</Alert>}
          {target && settings && <SettingsTargetDetails target={target} settings={settings.nlp} />}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Закрыть</Button>
        {target && (
          <MuiLink
            href={settingsTargetHash(target)}
            underline="hover"
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
                return;
              }
              event.preventDefault();
              onOpenPage(target);
            }}
          >
            Открыть страницу настройки
          </MuiLink>
        )}
      </DialogActions>
    </Dialog>
  );
}

function SettingsTargetDetails({ target, settings }: { target: SettingsTarget; settings: NlpSettings }) {
  if (target.kind === "signal") {
    const rule = settings.signals.find((item) => item.type === target.key);
    return rule ? <RuleSettingsDetails rule={rule} settings={settings} collection="signals" /> : <MissingSetting target={target} />;
  }
  if (target.kind === "fact") {
    const rule = settings.facts.find((item) => item.type === target.key);
    return rule ? <RuleSettingsDetails rule={rule} settings={settings} collection="facts" /> : <MissingSetting target={target} />;
  }
  if (target.kind === "alias") {
    const alias = settings[target.catalog].find((item) => item.key === target.key);
    return alias ? <AliasSettingsDetails alias={alias} catalog={target.catalog} /> : <MissingSetting target={target} />;
  }
  return <LeadScoringTargetDetails target={target} settings={settings} />;
}

function MissingSetting({ target }: { target: SettingsTarget }) {
  return (
    <Alert severity="warning">
      Настройка по ссылке не найдена в активной ревизии: {settingsTargetHash(target)}
    </Alert>
  );
}

function RuleSettingsDetails({
  rule,
  settings,
  collection
}: {
  rule: RuleSetting;
  settings: NlpSettings;
  collection: "signals" | "facts";
}) {
  return (
    <Stack spacing={2}>
      <SettingsRows
        rows={[
          ["Раздел", collection === "signals" ? "Доменные сигналы" : "Факты"],
          ["type", rule.type],
          ["label", rule.label],
          ["group", rule.group || "Без папки"],
          ["confidence", rule.confidence ?? "не задано"]
        ]}
      />
      <SettingsListBlock title="Точные фразы" items={rule.phrases.map((phrase) => phrase.join(" "))} />
      <SettingsListBlock
        title="Лемматические фразы"
        items={rule.patterns.map((pattern) => `${patternSourceText(pattern)} -> ${patternLemmaText(pattern)}`)}
      />
      {collection === "signals" && (
        <Stack spacing={1}>
          <Typography variant="subtitle2">Зависимости</Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Тип</TableCell>
                  <TableCell>Значения</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(rule.match?.aliases ?? []).map((dependency, index) => {
                  const catalog = aliasCatalogFromDependency(dependency);
                  return (
                    <TableRow key={`alias-${index}`}>
                      <TableCell>Словарь: {catalog}</TableCell>
                      <TableCell>
                        <InlineSettingsLinks
                          links={(dependency.keys ?? []).map((key) => ({
                            label: aliasLabel(settings, catalog, key),
                            target: { kind: "alias", catalog, key }
                          }))}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
                {(rule.match?.facts ?? []).map((dependency, index) => (
                  <TableRow key={`fact-${index}`}>
                    <TableCell>Факты</TableCell>
                    <TableCell>
                      <InlineSettingsLinks
                        links={dependency.types.map((type) => ({
                          label: settingsTypeLabel(settings, type),
                          target: settingsTargetForType(settings, type)
                        }))}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      )}
    </Stack>
  );
}

function AliasSettingsDetails({ alias, catalog }: { alias: AliasSetting; catalog: AliasCatalogName }) {
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Каталог: {catalog}
      </Typography>
      <SettingsRows
        rows={[
          ["Каталог", catalog],
          ["key", alias.key],
          ["canonical", alias.canonical],
          ["type", alias.type],
          ["confidence", alias.confidence ?? "не задано"]
        ]}
      />
      <SettingsListBlock title="Варианты написания" items={alias.aliases} />
      <SettingsListBlock title="fact_types" items={alias.fact_types} />
    </Stack>
  );
}

function LeadScoringTargetDetails({ target, settings }: { target: SettingsTarget; settings: NlpSettings }) {
  const scoring = settings.lead_scoring;
  if (target.kind === "lead_signal_weight") {
    return (
      <Stack spacing={2}>
        <SettingsRows rows={[["Ключ", `signal_weights.${target.key}`], ["Вес", scoring.signal_weights[target.key] ?? "не задан"]]} />
        <InlineSettingsLinks links={[{ label: settingsTypeLabel(settings, target.key), target: settingsTargetForType(settings, target.key) }]} />
      </Stack>
    );
  }
  if (target.kind === "lead_fact_weight") {
    return (
      <Stack spacing={2}>
        <SettingsRows rows={[["Ключ", `fact_weights.${target.key}`], ["Вес", scoring.fact_weights[target.key] ?? "не задан"]]} />
        <InlineSettingsLinks links={[{ label: settingsTypeLabel(settings, target.key), target: settingsTargetForType(settings, target.key) }]} />
      </Stack>
    );
  }
  if (target.kind === "solution_area" || target.kind === "customer_segment") {
    const mappings = target.kind === "solution_area" ? scoring.solution_areas : scoring.customer_segments;
    const mapping = mappings[target.key];
    if (!mapping) {
      return <MissingSetting target={target} />;
    }
    return (
      <Stack spacing={2}>
        <SettingsRows rows={[["key", target.key], ["label", mapping.label]]} />
        <SettingsLinkedTypes title="signal_types" types={mapping.signal_types} settings={settings} />
        <SettingsLinkedTypes title="fact_types" types={mapping.fact_types} settings={settings} />
      </Stack>
    );
  }
  if (target.kind === "review_lane") {
    const lane = scoring.review_lanes.find((item) => item.key === target.key);
    if (!lane) {
      return <MissingSetting target={target} />;
    }
    return (
      <Stack spacing={2}>
        <SettingsRows
          rows={[
            ["key", lane.key],
            ["label", lane.label],
            ["priority", lane.priority],
            ["description", lane.description || "не задано"],
            ["temperatures", lane.temperatures.join(", ") || "любые"],
            ["min_score", lane.min_score ?? "не задан"],
            ["max_score", lane.max_score ?? "не задан"]
          ]}
        />
        {lane.match_groups.map((group, index) => (
          <Paper key={index} variant="outlined" sx={{ p: 1.5 }}>
            <Stack spacing={1}>
              <Typography variant="subtitle2">match group {index + 1}</Typography>
              <SettingsLinkedTypes title="signal_types" types={group.signal_types} settings={settings} />
              <SettingsLinkedTypes title="fact_types" types={group.fact_types} settings={settings} />
              <SettingsLinkedTypes title="reason_keys" types={group.reason_keys} settings={settings} />
              <SettingsLinkedTypes title="solution_area_types" types={group.solution_area_types} settings={settings} />
              <SettingsLinkedTypes title="customer_segment_types" types={group.customer_segment_types} settings={settings} />
            </Stack>
          </Paper>
        ))}
      </Stack>
    );
  }
  return <MissingSetting target={target} />;
}

function SettingsLinkedTypes({ title, types, settings }: { title: string; types: string[]; settings: NlpSettings }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="subtitle2">{title}</Typography>
      <InlineSettingsLinks
        links={types.map((type) => ({
          label: settingsTypeLabel(settings, type),
          target: settingsTargetForType(settings, type)
        }))}
      />
    </Stack>
  );
}

function SettingsRows({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <TableContainer>
      <Table size="small">
        <TableBody>
          {rows.map(([key, value]) => (
            <TableRow key={key}>
              <TableCell sx={{ width: 220, fontWeight: 700 }}>{key}</TableCell>
              <TableCell>{value}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function SettingsListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">{title}</Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Не задано.</Typography>
      ) : (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          {items.map((item) => (
            <Chip key={item} label={item} size="small" variant="outlined" />
          ))}
        </Box>
      )}
    </Stack>
  );
}

function SettingsHelpPage() {
  return (
    <Box className="help-shell">
      <Paper variant="outlined" className="settings-panel">
        <Stack spacing={3}>
          <Box>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 800 }}>
              Справка по настройкам
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Настройки управляют тем, какие фрагменты текста найдёт pipeline, какие причины
              попадут в объяснение и как из них получится оценка потенциального лида ПУР.
            </Typography>
          </Box>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Pipeline</Typography>
            <Typography variant="body2" color="text.secondary">
              Pipeline - список этапов обработки. Выключенный этап не запускается и не добавляет
              данные в результат. Если выключить `domain_signals`, сообщение не получит доменные
              сигналы; если выключить `facts`, не появятся факты; если выключить `lead_scoring`,
              не будет verdict, score, температуры, причин и очереди разбора.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Этап</TableCell>
                    <TableCell>Что добавляет</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>segmentation / morphology / lemmatization</TableCell>
                    <TableCell>предложения, токены, леммы, части речи</TableCell>
                    <TableCell>нужны для лемматического совпадения и объяснимой разметки текста</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>domain_signals</TableCell>
                    <TableCell>смысловые признаки: умный дом, видеонаблюдение, протечки</TableCell>
                    <TableCell>дают основные причины `weights.signals` для score</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>facts</TableCell>
                    <TableCell>структурные факты: устройство, город, тип работ, выводы</TableCell>
                    <TableCell>добавляют контекст и причины `weights.facts` для score</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>lead_scoring</TableCell>
                    <TableCell>lead_assessment: score, temperature, reasons, segments, lanes</TableCell>
                    <TableCell>превращает найденные сигналы и факты в решение "лид / не лид"</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Box className="help-grid">
            <Paper variant="outlined" className="help-section">
              <Typography variant="h6">Точное совпадение</Typography>
              <Typography variant="body2" color="text.secondary">
                Используй для фраз, где важна именно запись: аббревиатуры, бренды, протоколы,
                технические обозначения и короткие устойчивые выражения. Регистр не важен.
              </Typography>
              <Stack spacing={0.75}>
                {["с ндс", "white box", "220v", "wi-fi"].map((item) => (
                  <Chip key={item} label={item} size="small" variant="outlined" />
                ))}
              </Stack>
            </Paper>

            <Paper variant="outlined" className="help-section">
              <Typography variant="h6">Лемматическое совпадение</Typography>
              <Typography variant="body2" color="text.secondary">
                Используй для русских доменных смыслов. Оператор вводит обычную фразу, backend
                приводит слова к леммам, а правило потом находит разные падежи, роды и числа.
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Ввод оператора</TableCell>
                      <TableCell>Леммы в правиле</TableCell>
                      <TableCell>Что найдет</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>нужна консультация</TableCell>
                      <TableCell>нужный консультация</TableCell>
                      <TableCell>нужную консультацию, нужны консультации</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>умный дом</TableCell>
                      <TableCell>умный дом</TableCell>
                      <TableCell>умного дома, умному дому</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>система видеонаблюдения</TableCell>
                      <TableCell>система видеонаблюдение</TableCell>
                      <TableCell>систему видеонаблюдения</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Box>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Доменные сигналы</Typography>
            <Typography variant="body2" color="text.secondary">
              Доменный сигнал - это смысловой маркер в сообщении. Он отвечает на вопрос:
              "О чём здесь говорят с точки зрения бизнеса ПУР?". Например,
              `smart_home_platform`, `video_surveillance`, `water_leak_protection`,
              `access_control`. Один сигнал может быть найден точной фразой,
              лемматической фразой или зависимостью `match` от словаря/факта.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Как настраивать</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>type</TableCell>
                    <TableCell>стабильный технический ключ сигнала</TableCell>
                    <TableCell>type пишем латиницей в snake_case: `video_surveillance`, `smart_home_platform`</TableCell>
                    <TableCell>по этому ключу считаются веса, зоны решений, intent/noise и фильтры аналитики</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>label</TableCell>
                    <TableCell>человеческое имя в интерфейсе</TableCell>
                    <TableCell>label - русское название: "Видеонаблюдение", "Умный дом"</TableCell>
                    <TableCell>показывается оператору, но не должен использоваться как стабильный идентификатор</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>confidence</TableCell>
                    <TableCell>доверие к самому правилу, число от 0 до 1</TableCell>
                    <TableCell>confidence - доверие к правилу; ставь выше для точных терминов, ниже для широких формулировок</TableCell>
                    <TableCell>попадает в разметку найденного span; score сейчас считается весами, а не confidence</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>group</TableCell>
                    <TableCell>папка для навигации по большому списку правил</TableCell>
                    <TableCell>group - папка, можно писать по-русски: "Безопасность", "Спрос и намерение"</TableCell>
                    <TableCell>не влияет на детекцию и score; только группирует правила в интерфейсе настроек</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>phrases</TableCell>
                    <TableCell>точные фразы</TableCell>
                    <TableCell>используй для коротких устойчивых выражений; бренды, модели и протоколы держи в словарях</TableCell>
                    <TableCell>если фраза найдена, в сообщении появляется сигнал с этим type</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>patterns</TableCell>
                    <TableCell>лемматические фразы</TableCell>
                    <TableCell>оператор вводит обычный текст, backend сохраняет исходный текст и леммы</TableCell>
                    <TableCell>находит формы слов: "умного дома", "умному дому", "систему видеонаблюдения"</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>match.aliases</TableCell>
                    <TableCell>явные зависимости сигнала от словарей</TableCell>
                    <TableCell>в строке зависимости выбери каталог `vendors`, `software` или `devices`, затем конкретные alias-ключи</TableCell>
                    <TableCell>если найден alias с указанным ключом/каталогом, появляется этот доменный сигнал</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>match.facts</TableCell>
                    <TableCell>зависимости сигнала от уже найденных фактов</TableCell>
                    <TableCell>выбери `automation_component`, `vendor`, `service_location` или другой fact_type из списка</TableCell>
                    <TableCell>позволяет строить сигнал поверх структурных фактов без повторного поиска текста</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              `type` технически является строкой, но в рабочих настройках не пишем его по-русски.
              Русский текст живёт в `label`. Это нужно, чтобы ключи были стабильными в API,
              аналитике, весах, миграциях и будущих eval-наборах.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Факты</Typography>
            <Typography variant="body2" color="text.secondary">
              Факт - это структурная деталь, которую можно использовать в объяснении и scoring:
              тип работ, устройство, город, помещение, вывод под оборудование, протокол, модель,
              поверхность монтажа. Факт обычно отвечает не "о чём сообщение", а "какая конкретика
              в нём есть".
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Как влияет на сообщение</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>type</TableCell>
                    <TableCell>технический ключ факта, тоже латиницей в snake_case</TableCell>
                    <TableCell>`controlled_device`, `wiring_output`, `service_location` могут добавить score через `weights.facts`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>label</TableCell>
                    <TableCell>русское имя факта для оператора</TableCell>
                    <TableCell>показывается в таблицах фактов и в preview draft</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>phrases / patterns</TableCell>
                    <TableCell>такие же режимы совпадения, как у сигналов</TableCell>
                    <TableCell>создают span в `facts`; затем scorer может учесть этот fact type</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>confidence</TableCell>
                    <TableCell>доверие к правилу извлечения факта</TableCell>
                    <TableCell>помогает читать результат, но не заменяет вес в scoring</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Словари</Typography>
            <Typography variant="body2" color="text.secondary">
              Словари нужны для сущностей с множеством человеческих написаний: vendors,
              protocols, devices, software. Они ловят конкретные имена и варианты записи:
              `Yandex/Яндекс`, `Aqara/Акара`, `Zigbee/Зигби`, `Home Assistant/Хоум Ассистант`.
              Входной текст перед точным матчингом приводится к нижнему регистру, поэтому регистр
              в alias не влияет на поиск.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле</TableCell>
                    <TableCell>Что это</TableCell>
                    <TableCell>Как настраивать</TableCell>
                    <TableCell>Как влияет</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>key</TableCell>
                    <TableCell>стабильный ключ записи словаря</TableCell>
                    <TableCell>латиница snake_case: `yandex`, `aqara`, `neptun_prow`</TableCell>
                    <TableCell>нужен для обслуживания словаря и будущих связей</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>canonical</TableCell>
                    <TableCell>каноническое имя</TableCell>
                    <TableCell>`Yandex Smart Home`, `Aqara`, `Neptun ProW`</TableCell>
                    <TableCell>показывает, что именно имелось в виду при любом alias</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>aliases</TableCell>
                    <TableCell>варианты написания</TableCell>
                    <TableCell>латиница, кириллица, транслитерация, частые ошибки: `Нептун`, `Нептуп`</TableCell>
                    <TableCell>сам alias создаёт факты; сигналы ссылаются на него через `match.aliases`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fact_types</TableCell>
                    <TableCell>какие факты добавить при совпадении</TableCell>
                    <TableCell>например `vendor`, `protocol`, `software`, `model`</TableCell>
                    <TableCell>добавляет структурную конкретику и может дать вес через `weights.facts`</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Alias matching</Typography>
            <Typography variant="body2" color="text.secondary">
              Alias-словари всегда сравниваются через casefold, поэтому регистр не важен:
              `Neptun`, `neptun`, `НЕПТУН` и `Нептун` обрабатываются без отдельного
              перечисления регистра. Дополнительно можно включить нормализацию `ё/е`,
              похожих латинских/кириллических букв и небольшой fuzzy-допуск.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Настройка</TableCell>
                    <TableCell>Что делает</TableCell>
                    <TableCell>Риск</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>normalize_separators</TableCell>
                    <TableCell>считает `Profi Wi-Fi`, `Profi-WiFi`, `profi wifi` близкими написаниями</TableCell>
                    <TableCell>низкий, потому что alias всё равно должен совпасть целиком</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>normalize_yo</TableCell>
                    <TableCell>считает `ё` и `е` одной буквой</TableCell>
                    <TableCell>низкий для русских технических названий</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>normalize_latin_confusables</TableCell>
                    <TableCell>ловит смешанные буквы вроде `Нептyн`, где `y` латинская</TableCell>
                    <TableCell>средний, поэтому применяется только к похожим буквам внутри слова</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fuzzy_enabled</TableCell>
                    <TableCell>разрешает небольшую редакционную дистанцию для alias</TableCell>
                    <TableCell>может дать шум, если включить слишком большой distance</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fuzzy_min_length</TableCell>
                    <TableCell>короткие alias не проходят fuzzy; например `sst`, `knx`, `dvr` не должны ловить случайные слова</TableCell>
                    <TableCell>если поставить слишком низко, короткие alias начнут шуметь</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>fuzzy_excluded_aliases</TableCell>
                    <TableCell>ручной стоп-лист alias, для которых fuzzy запрещён даже при достаточной длине</TableCell>
                    <TableCell>используется для спорных брендов, аббревиатур и коротких моделей</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Связь сигналов и словарей</Typography>
            <Typography variant="body2" color="text.secondary">
              Доменный сигнал и словарь не заменяют друг друга. Они являются разными источниками
              данных. Смысловая категория остаётся в доменных сигналах, а конкретные бренды,
              модели, протоколы и приложения живут в словарях. Связь хранится на стороне
              сигнала в `match.aliases`.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Где настроено</TableCell>
                    <TableCell>Что произойдёт при тексте "Нептун"</TableCell>
                    <TableCell>Когда использовать</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>patterns у `water_leak_protection`</TableCell>
                    <TableCell>общие фразы вроде "датчик протечки" создают сигнал `water_leak_protection` с `source=yargy`</TableCell>
                    <TableCell>когда фраза описывает смысловую категорию, а не бренд или модель</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>`match.aliases` у `water_leak_protection`</TableCell>
                    <TableCell>сигнал явно ссылается на каталог `vendors` и alias `neptun`; "Нептун" не добавляем в `phrases`, но сигнал появляется с `source=alias_catalog`</TableCell>
                    <TableCell>когда смысловой сигнал должен опираться на словарную сущность</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>alias `neptun` в словаре vendors</TableCell>
                    <TableCell>словарь создаёт факты `vendor`, `model` и хранит `Нептун`, `Нептуп`, `Neptun ProW`, `Profi Wi-Fi`</TableCell>
                    <TableCell>когда нужно хранить каноническое имя, варианты написания и ошибки</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>lead_scoring</TableCell>
                    <TableCell>score учитывает найденные типы, а не место настройки; один и тот же type в причинах считается один раз</TableCell>
                    <TableCell>веса задаются в `weights.signals` и `weights.facts` по техническим ключам type</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">
              Практическое правило: бренды, модели, протоколы, приложения и человеческие ошибки
              написания держим в словарях. Доменные сигналы ссылаются на словари через
              `match.aliases`; словари не содержат `signal_types`, чтобы не было двух источников
              правды. Факты от alias задаются через `fact_types`.
            </Alert>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Оценка лида</Typography>
            <Typography variant="body2" color="text.secondary">
              Оценка лида - детерминированный слой поверх найденных сигналов и фактов. Он не
              перечитывает текст заново и не использует LLM. Он берёт уже найденные `domain_signals`
              и `facts`, суммирует настроенные веса, определяет температуру, зоны решений,
              сегменты клиента, причины и очередь разбора.
            </Typography>
            <Stack spacing={2}>
              <Alert severity="info">
                score = сумма весов всех найденных типов из `weights.signals` и `weights.facts`.
                Один type учитывается как причина, если он встретился хотя бы один раз; найденные
                тексты сохраняются в `matched_texts`, чтобы было видно, почему правило сработало.
              </Alert>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Настройка</TableCell>
                      <TableCell>Что означает</TableCell>
                      <TableCell>Как влияет</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>thresholds.lead</TableCell>
                      <TableCell>минимальный score, с которого `is_lead = true`</TableCell>
                      <TableCell>ниже порога сообщение остаётся не лидом, даже если есть отдельные признаки</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>thresholds.warm / thresholds.hot</TableCell>
                      <TableCell>пороги температуры</TableCell>
                      <TableCell>дают `cold`, `warm`, `hot`; это не отдельные правила, а диапазоны score</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>weights.signals</TableCell>
                      <TableCell>веса доменных сигналов</TableCell>
                      <TableCell>`video_surveillance: 35` добавит 35 баллов, если найден сигнал `video_surveillance`</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>weights.facts</TableCell>
                      <TableCell>веса фактов</TableCell>
                      <TableCell>`wiring_output: 8` добавит 8 баллов, если найден факт вывода под оборудование</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>negative weights</TableCell>
                      <TableCell>отрицательные веса для шума</TableCell>
                      <TableCell>`diy_or_equipment_only: -50` снижает score, если сообщение похоже на DIY или покупку железки без услуги</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>solution_areas</TableCell>
                      <TableCell>карта типов в направления решений ПУР</TableCell>
                      <TableCell>показывает "Умный дом", "Безопасность", "Климат", "СКУД" и даёт фильтры аналитики</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>customer_segments</TableCell>
                      <TableCell>карта типов в сегменты клиентов</TableCell>
                      <TableCell>выделяет дизайнеров, частное жильё, коммерческие объекты, активные запросы</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>intent_signal_types</TableCell>
                      <TableCell>какие сигналы считать намерением</TableCell>
                      <TableCell>показывает, что пользователь ищет подрядчика, консультацию, установку или подбор решения</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>noise_signal_types</TableCell>
                      <TableCell>какие сигналы считать шумом</TableCell>
                      <TableCell>объясняет, почему кандидат может быть слабым или нецелевым</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>review_lanes</TableCell>
                      <TableCell>очереди ручного разбора кандидатов</TableCell>
                      <TableCell>после batch import кандидат получает lane: прямой лид, проектный контекст, доменный интерес, шум</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Пример</TableCell>
                      <TableCell>Что найдётся</TableCell>
                      <TableCell>Почему станет лидом</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>нужно подключить zigbee шлюз к Алисе</TableCell>
                      <TableCell>protocol_gateway, smart_home_platform, work_type</TableCell>
                      <TableCell>сумма весов проходит lead/hot threshold, появляются причины и smart_home area</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>где заказать видеонаблюдение для квартиры</TableCell>
                      <TableCell>provider_search, video_surveillance, apartment_context</TableCell>
                      <TableCell>есть домен безопасности и активный поиск поставщика/подрядчика</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>продам камеру, сам поставлю</TableCell>
                      <TableCell>video_surveillance плюс noise/DIY или sale</TableCell>
                      <TableCell>отрицательные веса и noise signals могут увести ниже порога или в lane "Шум"</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </Stack>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Очереди разбора</Typography>
            <Typography variant="body2" color="text.secondary">
              `review_lanes` - это не новая детекция текста, а способ разложить уже найденных
              кандидатов по очередям для ручного анализа. Lane с большим `priority` проверяется
              первой. `match_groups` работают как группы условий: внутри группы достаточно одного
              совпадения, а группы между собой должны выполниться все. Excluded-поля убирают
              кандидата из lane, даже если положительные условия совпали.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Поле lane</TableCell>
                    <TableCell>Назначение</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>key / label / description</TableCell>
                    <TableCell>технический ключ, русское имя и пояснение для аналитики</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>priority</TableCell>
                    <TableCell>чем выше число, тем раньше lane заберёт кандидата</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>match_groups</TableCell>
                    <TableCell>условия по signal_types, fact_types, reason_keys, solution_area_types, customer_segment_types</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>excluded_* fields</TableCell>
                    <TableCell>запреты по шуму, причинам, сигналам, сегментам или зонам решений</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Уведомления</Typography>
            <Typography variant="body2" color="text.secondary">
              Раздел управляет доставкой уведомлений после runtime enrichment. Batch-runner сюда
              не подключен: он нужен для тестирования и калибровки на архивах. Продовая цепочка
              будет такой: userbot получает сообщение, создает обычную задачу enrichment, после
              завершения результата маршруты кладут уведомления в outbox, а отдельный dispatcher
              отправляет их пачками.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Сущность</TableCell>
                    <TableCell>Что настраивается</TableCell>
                    <TableCell>Как работает</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Боты</TableCell>
                    <TableCell>ID, название, включен/выключен, токен BotFather</TableCell>
                    <TableCell>бот владеет токеном; токен хранится в PostgreSQL и в UI/API показывается только маской</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Чаты</TableCell>
                    <TableCell>ID, название, включен/выключен, Telegram `chat_id`</TableCell>
                    <TableCell>чат не знает про токен; тестовая отправка выбирает сохраненного бота отдельно</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Маршруты</TableCell>
                    <TableCell>priority, bot, chat, режим all/any, условия и шаблон</TableCell>
                    <TableCell>после обработки текста выбирают доставку по score, temperature, lane, сегментам, сигналам, фактам и причинам; каждый match создает запись в `notification_outbox`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Шаблон сообщения</TableCell>
                    <TableCell>{`{score}, {temperature}, {review_lane_label}, {solution_areas}, {customer_segments}, {reasons_detailed}, {text_preview}`}</TableCell>
                    <TableCell>дефолтный шаблон разбивает уведомление на блоки: оценка, очередь, направления, причины score и короткий текст; ссылки на Telegram и аналитику добавляются отдельным блоком</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Outbox batching</TableCell>
                    <TableCell>группировка по bot+chat, лимит текста, интервал flush</TableCell>
                    <TableCell>dispatcher пакует лиды под 4096 символов Telegram `sendMessage`; неполная пачка уходит, когда старейшая запись ждёт 5 минут</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Отправить тест</TableCell>
                    <TableCell>бот + чат + текст проверки</TableCell>
                    <TableCell>проверяет реальную доставку в Telegram до включения маршрутов</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Telegram вход</Typography>
            <Typography variant="body2" color="text.secondary">
              Раздел управляет входящими Telegram-источниками. Userbot - это пользовательский
              Telegram-аккаунт через Telethon, а не Bot API. Он читает указанные чаты, сохраняет
              исходные сообщения и создает обычные enrichment jobs. Секреты не показываются:
              `api_hash` и `StringSession` возвращаются в UI только как факт наличия и маска.
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Сущность</TableCell>
                    <TableCell>Что настраивается</TableCell>
                    <TableCell>Как работает</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Userbot аккаунт</TableCell>
                    <TableCell>телефон, Telegram app `api_id`, `api_hash`, включен/выключен</TableCell>
                    <TableCell>кнопка "Отправить код" запускает login; "Завершить вход" сохраняет Telethon `StringSession`</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Чат-источник</TableCell>
                    <TableCell>userbot account, `input_ref`, resolved chat id, cursor</TableCell>
                    <TableCell>`input_ref` может быть username или id; userbot хранит `last_message_id` и не импортирует историю без явного batch-runner</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Статус чата-источника</TableCell>
                    <TableCell>`draft`, `resolved`, `error`</TableCell>
                    <TableCell>`draft` означает, что запись сохранена, но userbot еще не резолвил `input_ref`; `resolved` означает, что найден Telegram chat id и сохранен cursor; "Обновить статус" перечитывает актуальное состояние из backend</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Очередь анализа</TableCell>
                    <TableCell>создается обычный enrichment job</TableCell>
                    <TableCell>userbot не анализирует текст сам; он сохраняет сообщение и публикует задачу в существующую Celery/Redis очередь</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper variant="outlined" className="help-section">
            <Typography variant="h6">Как выбирать режим</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Ситуация</TableCell>
                    <TableCell>Что выбрать</TableCell>
                    <TableCell>Почему</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Русская предметная фраза</TableCell>
                    <TableCell>Лемматическое совпадение</TableCell>
                    <TableCell>Поймает формы слов без перечисления падежей.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Аббревиатура, бренд, техническая запись</TableCell>
                    <TableCell>Точное совпадение</TableCell>
                    <TableCell>Такие токены часто нельзя надежно лемматизировать.</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Новое правило непонятно как сработает</TableCell>
                    <TableCell>Preview draft</TableCell>
                    <TableCell>Проверяет черновик без сохранения новой ревизии.</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Stack>
      </Paper>
    </Box>
  );
}

function PipelineSettingsEditor({
  draft,
  onStageChange,
  onAliasMatchingChange
}: {
  draft: NlpSettings;
  onStageChange: (index: number, enabled: boolean) => void;
  onAliasMatchingChange: (settings: AliasMatchingSettings) => void;
}) {
  const aliasMatching = normalizedAliasMatchingSettings(draft.alias_matching);

  function updateAliasMatching(patch: Partial<AliasMatchingSettings>) {
    onAliasMatchingChange({ ...aliasMatching, ...patch });
  }

  return (
    <Stack spacing={1.5}>
      <Typography variant="h6">Pipeline</Typography>
      {draft.pipeline.stages.map((stage, index) => (
        <FormControlLabel
          key={stage.name}
          control={<Switch checked={stage.enabled} onChange={(event) => onStageChange(index, event.target.checked)} />}
          label={`${stage.name} ${stage.enabled ? "включен" : "выключен"}`}
        />
      ))}
      <Divider />
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="h6">Alias matching</Typography>
          <Typography variant="body2" color="text.secondary">
            Настройки нормализации и небольшого fuzzy-допуска для alias-словарей.
          </Typography>
        </Box>
        <Box className="settings-two-column">
          <FormControlLabel
            control={
              <Switch
                checked={aliasMatching.normalize_separators}
                onChange={(event) => updateAliasMatching({ normalize_separators: event.target.checked })}
              />
            }
            label="Нормализовать пробелы и дефисы"
          />
          <FormControlLabel
            control={
              <Switch
                checked={aliasMatching.normalize_yo}
                onChange={(event) => updateAliasMatching({ normalize_yo: event.target.checked })}
              />
            }
            label="ё = е"
          />
          <FormControlLabel
            control={
              <Switch
                checked={aliasMatching.normalize_latin_confusables}
                onChange={(event) => updateAliasMatching({ normalize_latin_confusables: event.target.checked })}
              />
            }
            label="Латиница/кириллица в похожих буквах"
          />
          <FormControlLabel
            control={
              <Switch
                checked={aliasMatching.fuzzy_enabled}
                onChange={(event) => updateAliasMatching({ fuzzy_enabled: event.target.checked })}
              />
            }
            label="Fuzzy alias matching"
          />
        </Box>
        <Box className="rule-grid">
          <TextField
            label="Минимальная длина fuzzy"
            type="number"
            value={aliasMatching.fuzzy_min_length}
            onChange={(event) => updateAliasMatching({ fuzzy_min_length: numberInput(event.target.value) })}
            slotProps={{ htmlInput: { min: 1, step: 1 } }}
          />
          <TextField
            label="Макс. distance"
            type="number"
            value={aliasMatching.fuzzy_max_distance}
            onChange={(event) => updateAliasMatching({ fuzzy_max_distance: numberInput(event.target.value) })}
            slotProps={{ htmlInput: { min: 0, max: 3, step: 1 } }}
          />
          <TextField
            label="Длинный alias от"
            type="number"
            value={aliasMatching.fuzzy_long_min_length}
            onChange={(event) => updateAliasMatching({ fuzzy_long_min_length: numberInput(event.target.value) })}
            slotProps={{ htmlInput: { min: 1, step: 1 } }}
          />
          <TextField
            label="Distance для длинных"
            type="number"
            value={aliasMatching.fuzzy_long_max_distance}
            onChange={(event) => updateAliasMatching({ fuzzy_long_max_distance: numberInput(event.target.value) })}
            slotProps={{ htmlInput: { min: 0, max: 3, step: 1 } }}
          />
        </Box>
        <TextField
          label="Исключения fuzzy"
          helperText="Один alias в строке. Используй для коротких или рискованных написаний, где fuzzy может дать шум."
          value={stringListToText(aliasMatching.fuzzy_excluded_aliases)}
          onChange={(event) => updateAliasMatching({ fuzzy_excluded_aliases: textToStringList(event.target.value) })}
          multiline
          minRows={3}
          fullWidth
        />
      </Stack>
    </Stack>
  );
}

function AliasCatalogsEditor({
  settings,
  activeTarget,
  onAdd,
  onRemove,
  onUpdate
}: {
  settings: NlpSettings;
  activeTarget: SettingsTarget | null;
  onAdd: (catalog: AliasCatalogName) => void;
  onRemove: (catalog: AliasCatalogName, index: number) => void;
  onUpdate: (catalog: AliasCatalogName, index: number, alias: AliasSetting) => void;
}) {
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6">Alias-словари</Typography>
        <Typography variant="body2" color="text.secondary">
          Вендоры, протоколы, устройства и ПО матчятся как словари написаний и привязаны к смысловым сигналам и фактам.
        </Typography>
      </Box>
      {aliasCatalogDefinitions.map((definition) => (
        <AliasCatalogEditor
          key={definition.name}
          definition={definition}
          aliases={settings[definition.name]}
          activeKey={activeTarget?.kind === "alias" && activeTarget.catalog === definition.name ? activeTarget.key : null}
          onAdd={() => onAdd(definition.name)}
          onRemove={(index) => onRemove(definition.name, index)}
          onUpdate={(index, alias) => onUpdate(definition.name, index, alias)}
        />
      ))}
    </Stack>
  );
}

function AliasCatalogEditor({
  definition,
  aliases,
  activeKey,
  onAdd,
  onRemove,
  onUpdate
}: {
  definition: AliasCatalogDefinition;
  aliases: AliasSetting[];
  activeKey: string | null;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, alias: AliasSetting) => void;
}) {
  return (
    <Stack spacing={1}>
      <Box className="rule-list-header">
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {definition.label}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {aliases.length} записей
          </Typography>
        </Box>
        <Button
          aria-label={`Добавить alias в ${definition.label}`}
          startIcon={<AddIcon />}
          variant="outlined"
          onClick={onAdd}
        >
          Добавить
        </Button>
      </Box>
      {aliases.map((alias, index) => (
        <AliasEditor
          key={`${definition.name}-${alias.key}-${index}`}
          alias={alias}
          catalog={definition.name}
          isTarget={alias.key === activeKey}
          onRemove={() => onRemove(index)}
          onUpdate={(nextAlias) => onUpdate(index, nextAlias)}
        />
      ))}
    </Stack>
  );
}

function AliasEditor({
  alias,
  catalog,
  isTarget,
  onRemove,
  onUpdate
}: {
  alias: AliasSetting;
  catalog: AliasCatalogName;
  isTarget: boolean;
  onRemove: () => void;
  onUpdate: (alias: AliasSetting) => void;
}) {
  const [expanded, setExpanded] = useState(isTarget);

  useEffect(() => {
    if (isTarget) {
      setExpanded(true);
    }
  }, [isTarget]);

  return (
    <Accordion
      id={settingsTargetElementId({ kind: "alias", catalog, key: alias.key })}
      className={isTarget ? "settings-target-highlight" : undefined}
      tabIndex={isTarget ? -1 : undefined}
      variant="outlined"
      disableGutters
      expanded={expanded}
      onChange={(_, nextExpanded) => setExpanded(nextExpanded)}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ alignItems: "center", display: "flex", gap: 1, minWidth: 0, width: "100%" }}>
          {alias.color && <Box className="rule-color" sx={{ backgroundColor: alias.color }} />}
          <Typography sx={{ flex: 1, fontWeight: 700 }} noWrap>
            {alias.canonical}
          </Typography>
          {alias.aliases.slice(0, 3).map((aliasText) => (
            <Chip key={aliasText} label={aliasText} size="small" variant="outlined" />
          ))}
          <Chip label={alias.type} size="small" variant="outlined" />
          <Chip label={alias.key} size="small" variant="outlined" />
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <Box className="rule-grid">
            <TextField label="key" value={alias.key} onChange={(event) => onUpdate({ ...alias, key: event.target.value })} />
            <TextField
              label="canonical"
              value={alias.canonical}
              onChange={(event) => onUpdate({ ...alias, canonical: event.target.value })}
            />
            <TextField
              label="type"
              value={alias.type}
              onChange={(event) => onUpdate({ ...alias, type: aliasTypeFromText(event.target.value) })}
            />
            <TextField
              label="confidence"
              type="number"
              value={alias.confidence ?? ""}
              onChange={(event) =>
                onUpdate({ ...alias, confidence: event.target.value === "" ? null : Number(event.target.value) })
              }
              slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
            />
          </Box>
          <Box className="settings-two-column">
            <TextField
              label="aliases"
              helperText="Один вариант написания в строке"
              value={stringListToText(alias.aliases)}
              onChange={(event) => onUpdate({ ...alias, aliases: textToStringList(event.target.value) })}
              multiline
              minRows={5}
              fullWidth
            />
            <Stack spacing={2}>
              <TextField
                label="fact_types"
                value={stringListToText(alias.fact_types)}
                onChange={(event) => onUpdate({ ...alias, fact_types: textToStringList(event.target.value) })}
                multiline
                minRows={2}
              />
            </Stack>
          </Box>
          <Box>
            <Tooltip title="Удалить">
              <IconButton aria-label={`Удалить alias: ${alias.canonical}`} color="error" onClick={onRemove}>
                <DeleteIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

function LeadScoringSettingsEditor({
  settings,
  activeTarget,
  onUpdate
}: {
  settings: LeadScoringSettings;
  activeTarget: SettingsTarget | null;
  onUpdate: (settings: LeadScoringSettings) => void;
}) {
  function updateLane(index: number, lane: ReviewLaneSetting) {
    onUpdate({
      ...settings,
      review_lanes: settings.review_lanes.map((item, itemIndex) => (itemIndex === index ? lane : item))
    });
  }

  function addLane() {
    onUpdate({
      ...settings,
      review_lanes: [
        ...settings.review_lanes,
        {
          key: "new_review_lane",
          label: "Новая lane",
          description: "",
          priority: 0,
          min_score: null,
          max_score: null,
          temperatures: [],
          match_groups: [],
          excluded_signal_types: [],
          excluded_fact_types: [],
          excluded_reason_keys: [],
          excluded_solution_area_types: [],
          excluded_customer_segment_types: [],
          excluded_intent_signal_types: [],
          excluded_noise_signal_types: []
        }
      ]
    });
  }

  function removeLane(index: number) {
    onUpdate({
      ...settings,
      review_lanes: settings.review_lanes.filter((_, itemIndex) => itemIndex !== index)
    });
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Оценка лида</Typography>
      <Box className="rule-grid">
        <TextField
          label="lead threshold"
          type="number"
          value={settings.lead_threshold}
          onChange={(event) => onUpdate({ ...settings, lead_threshold: numberInput(event.target.value) })}
        />
        <TextField
          label="warm threshold"
          type="number"
          value={settings.warm_threshold}
          onChange={(event) => onUpdate({ ...settings, warm_threshold: numberInput(event.target.value) })}
        />
        <TextField
          label="hot threshold"
          type="number"
          value={settings.hot_threshold}
          onChange={(event) => onUpdate({ ...settings, hot_threshold: numberInput(event.target.value) })}
        />
      </Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        Пороги оценки
      </Typography>
      <Box className="settings-two-column">
        <Box
          id={
            activeTarget?.kind === "lead_signal_weight"
              ? settingsTargetElementId(activeTarget)
              : undefined
          }
          className={activeTarget?.kind === "lead_signal_weight" ? "settings-target-highlight" : undefined}
          tabIndex={activeTarget?.kind === "lead_signal_weight" ? -1 : undefined}
        >
          <TextField
            label="signal weights"
            helperText="Одна строка: type: weight"
            value={numberRecordToText(settings.signal_weights)}
            onChange={(event) => onUpdate({ ...settings, signal_weights: textToNumberRecord(event.target.value) })}
            multiline
            minRows={8}
            fullWidth
          />
        </Box>
        <Box
          id={
            activeTarget?.kind === "lead_fact_weight"
              ? settingsTargetElementId(activeTarget)
              : undefined
          }
          className={activeTarget?.kind === "lead_fact_weight" ? "settings-target-highlight" : undefined}
          tabIndex={activeTarget?.kind === "lead_fact_weight" ? -1 : undefined}
        >
          <TextField
            label="fact weights"
            helperText="Одна строка: type: weight"
            value={numberRecordToText(settings.fact_weights)}
            onChange={(event) => onUpdate({ ...settings, fact_weights: textToNumberRecord(event.target.value) })}
            multiline
            minRows={8}
            fullWidth
          />
        </Box>
      </Box>
      <CategoryMappingEditor
        title="Направления решений"
        mappings={settings.solution_areas}
        activeTarget={activeTarget?.kind === "solution_area" ? activeTarget : null}
        onUpdate={(solutionAreas) => onUpdate({ ...settings, solution_areas: solutionAreas })}
      />
      <CategoryMappingEditor
        title="Сегменты клиентов"
        mappings={settings.customer_segments}
        activeTarget={activeTarget?.kind === "customer_segment" ? activeTarget : null}
        onUpdate={(customerSegments) => onUpdate({ ...settings, customer_segments: customerSegments })}
      />
      <Box className="settings-two-column">
        <TextField
          label="intent signal types"
          value={stringListToText(settings.intent_signal_types)}
          onChange={(event) => onUpdate({ ...settings, intent_signal_types: textToStringList(event.target.value) })}
          multiline
          minRows={4}
          fullWidth
        />
        <TextField
          label="noise signal types"
          value={stringListToText(settings.noise_signal_types)}
          onChange={(event) => onUpdate({ ...settings, noise_signal_types: textToStringList(event.target.value) })}
          multiline
          minRows={4}
          fullWidth
        />
      </Box>
      <ReviewLaneSettingsEditor
        lanes={settings.review_lanes}
        activeTarget={activeTarget?.kind === "review_lane" ? activeTarget : null}
        onAdd={addLane}
        onRemove={removeLane}
        onUpdate={updateLane}
      />
    </Stack>
  );
}

function ReviewLaneSettingsEditor({
  lanes,
  activeTarget,
  onAdd,
  onRemove,
  onUpdate
}: {
  lanes: ReviewLaneSetting[];
  activeTarget: Extract<SettingsTarget, { kind: "review_lane" }> | null;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, lane: ReviewLaneSetting) => void;
}) {
  return (
    <Stack spacing={1}>
      <Box className="rule-list-header">
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Очереди разбора
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Очереди ручной проверки строятся из причин, сигналов, сегментов и направлений решений.
          </Typography>
        </Box>
        <Button startIcon={<AddIcon />} variant="outlined" onClick={onAdd}>
          Добавить lane
        </Button>
      </Box>
      {lanes.map((lane, index) => (
        <ReviewLaneEditor
          key={`${lane.key}-${index}`}
          lane={lane}
          isTarget={lane.key === activeTarget?.key}
          onRemove={() => onRemove(index)}
          onUpdate={(nextLane) => onUpdate(index, nextLane)}
        />
      ))}
    </Stack>
  );
}

function ReviewLaneEditor({
  lane,
  isTarget,
  onRemove,
  onUpdate
}: {
  lane: ReviewLaneSetting;
  isTarget: boolean;
  onRemove: () => void;
  onUpdate: (lane: ReviewLaneSetting) => void;
}) {
  const [expanded, setExpanded] = useState(isTarget);

  useEffect(() => {
    if (isTarget) {
      setExpanded(true);
    }
  }, [isTarget]);

  return (
    <Accordion
      id={settingsTargetElementId({ kind: "review_lane", key: lane.key })}
      className={isTarget ? "settings-target-highlight" : undefined}
      tabIndex={isTarget ? -1 : undefined}
      variant="outlined"
      disableGutters
      expanded={expanded}
      onChange={(_, nextExpanded) => setExpanded(nextExpanded)}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ alignItems: "center", display: "flex", gap: 1, minWidth: 0, width: "100%" }}>
          <Typography sx={{ flex: 1, fontWeight: 700 }} noWrap>
            {lane.label}
          </Typography>
          <Chip label={lane.key} size="small" variant="outlined" />
          <Chip label={`priority ${lane.priority}`} size="small" variant="outlined" />
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <Box className="rule-grid">
            <TextField label="key" value={lane.key} onChange={(event) => onUpdate({ ...lane, key: event.target.value })} />
            <TextField
              label="label"
              value={lane.label}
              onChange={(event) => onUpdate({ ...lane, label: event.target.value })}
            />
            <TextField
              label="priority"
              type="number"
              value={lane.priority}
              onChange={(event) => onUpdate({ ...lane, priority: numberInput(event.target.value) })}
            />
            <TextField
              label="temperatures"
              helperText="Одна температура в строке"
              value={stringListToText(lane.temperatures)}
              onChange={(event) => onUpdate({ ...lane, temperatures: textToStringList(event.target.value) })}
            />
          </Box>
          <TextField
            label="description"
            value={lane.description ?? ""}
            onChange={(event) => onUpdate({ ...lane, description: event.target.value || null })}
            fullWidth
          />
          <Box className="settings-two-column">
            <TextField
              label="match_groups JSON"
              helperText="Каждый объект - группа OR; группы между собой работают как AND."
              value={reviewLaneMatchGroupsToText(lane.match_groups)}
              onChange={(event) =>
                onUpdate({ ...lane, match_groups: textToReviewLaneMatchGroups(event.target.value, lane.match_groups) })
              }
              multiline
              minRows={8}
              fullWidth
            />
            <Stack spacing={2}>
              <TextField
                label="excluded_signal_types"
                value={stringListToText(lane.excluded_signal_types)}
                onChange={(event) =>
                  onUpdate({ ...lane, excluded_signal_types: textToStringList(event.target.value) })
                }
                multiline
                minRows={2}
              />
              <TextField
                label="excluded_noise_signal_types"
                value={stringListToText(lane.excluded_noise_signal_types)}
                onChange={(event) =>
                  onUpdate({ ...lane, excluded_noise_signal_types: textToStringList(event.target.value) })
                }
                multiline
                minRows={2}
              />
              <TextField
                label="excluded_solution_area_types"
                value={stringListToText(lane.excluded_solution_area_types)}
                onChange={(event) =>
                  onUpdate({ ...lane, excluded_solution_area_types: textToStringList(event.target.value) })
                }
                multiline
                minRows={2}
              />
            </Stack>
          </Box>
          <Box>
            <Tooltip title="Удалить">
              <IconButton aria-label={`Удалить lane: ${lane.label}`} color="error" onClick={onRemove}>
                <DeleteIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

function CategoryMappingEditor({
  title,
  mappings,
  activeTarget,
  onUpdate
}: {
  title: string;
  mappings: Record<string, LeadCategorySetting>;
  activeTarget: Extract<SettingsTarget, { kind: "solution_area" | "customer_segment" }> | null;
  onUpdate: (mappings: Record<string, LeadCategorySetting>) => void;
}) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {Object.entries(mappings).map(([key, mapping]) => (
        <CategoryMappingItem
          key={key}
          itemKey={key}
          mapping={mapping}
          isTarget={key === activeTarget?.key}
          targetKind={activeTarget?.kind ?? null}
          mappings={mappings}
          onUpdate={onUpdate}
        />
      ))}
    </Stack>
  );
}

function CategoryMappingItem({
  itemKey,
  mapping,
  isTarget,
  targetKind,
  mappings,
  onUpdate
}: {
  itemKey: string;
  mapping: LeadCategorySetting;
  isTarget: boolean;
  targetKind: "solution_area" | "customer_segment" | null;
  mappings: Record<string, LeadCategorySetting>;
  onUpdate: (mappings: Record<string, LeadCategorySetting>) => void;
}) {
  const [expanded, setExpanded] = useState(isTarget);

  useEffect(() => {
    if (isTarget) {
      setExpanded(true);
    }
  }, [isTarget]);

  return (
    <Accordion
      id={targetKind ? settingsTargetElementId({ kind: targetKind, key: itemKey }) : undefined}
      className={isTarget ? "settings-target-highlight" : undefined}
      tabIndex={isTarget ? -1 : undefined}
      variant="outlined"
      disableGutters
      expanded={expanded}
      onChange={(_, nextExpanded) => setExpanded(nextExpanded)}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ alignItems: "center", display: "flex", gap: 1, width: "100%" }}>
          <Typography sx={{ flex: 1, fontWeight: 700 }} noWrap>
            {mapping.label}
          </Typography>
          <Chip label={itemKey} size="small" variant="outlined" />
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <TextField
            label="label"
            value={mapping.label}
            onChange={(event) =>
              onUpdate({
                ...mappings,
                [itemKey]: { ...mapping, label: event.target.value }
              })
            }
          />
          <TextField
            label="signal_types"
            value={stringListToText(mapping.signal_types)}
            onChange={(event) =>
              onUpdate({
                ...mappings,
                [itemKey]: { ...mapping, signal_types: textToStringList(event.target.value) }
              })
            }
            multiline
            minRows={3}
          />
          <TextField
            label="fact_types"
            value={stringListToText(mapping.fact_types)}
            onChange={(event) =>
              onUpdate({
                ...mappings,
                [itemKey]: { ...mapping, fact_types: textToStringList(event.target.value) }
              })
            }
            multiline
            minRows={3}
          />
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

function RuleCollectionEditor({
  title,
  collection,
  activeTarget,
  settings,
  rules,
  onAdd,
  onRemove,
  onUpdate
}: {
  title: string;
  collection: "signals" | "facts";
  activeTarget: SettingsTarget | null;
  settings: NlpSettings;
  rules: RuleSetting[];
  onAdd: (collection: "signals" | "facts") => void;
  onRemove: (collection: "signals" | "facts", index: number) => void;
  onUpdate: (collection: "signals" | "facts", index: number, rule: RuleSetting) => void;
}) {
  const groups = groupRulesByFolder(rules);
  const activeRuleKey =
    (collection === "signals" && activeTarget?.kind === "signal") ||
    (collection === "facts" && activeTarget?.kind === "fact")
      ? activeTarget.key
      : null;

  return (
    <Stack spacing={1.5}>
      <Box sx={{ alignItems: "center", display: "flex", justifyContent: "space-between" }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {rules.length} правил в {groups.length} папках
          </Typography>
        </Box>
        <Button startIcon={<AddIcon />} variant="outlined" onClick={() => onAdd(collection)}>
          Добавить
        </Button>
      </Box>
      {groups.map((group, groupIndex) => (
        <RuleGroupAccordion
          key={group.label}
          group={group}
          collection={collection}
          settings={settings}
          activeRuleKey={activeRuleKey}
          defaultExpanded={groups.length === 1 || groupIndex === 0}
          onRemove={onRemove}
          onUpdate={onUpdate}
        />
      ))}
    </Stack>
  );
}

function RuleGroupAccordion({
  group,
  collection,
  settings,
  activeRuleKey,
  defaultExpanded,
  onRemove,
  onUpdate
}: {
  group: GroupedRule;
  collection: "signals" | "facts";
  settings: NlpSettings;
  activeRuleKey: string | null;
  defaultExpanded: boolean;
  onRemove: (collection: "signals" | "facts", index: number) => void;
  onUpdate: (collection: "signals" | "facts", index: number, rule: RuleSetting) => void;
}) {
  const hasTarget = group.items.some(({ rule }) => rule.type === activeRuleKey);
  const [expanded, setExpanded] = useState(defaultExpanded || hasTarget);

  useEffect(() => {
    if (hasTarget) {
      setExpanded(true);
    }
  }, [hasTarget]);

  return (
    <Accordion
      variant="outlined"
      disableGutters
      expanded={expanded}
      onChange={(_, nextExpanded) => setExpanded(nextExpanded)}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ alignItems: "center", display: "flex", gap: 1, minWidth: 0, width: "100%" }}>
          <Typography sx={{ flex: 1, fontWeight: 800 }} noWrap>
            {group.label}
          </Typography>
          <Chip label={`${group.items.length} правил`} size="small" variant="outlined" />
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={1}>
          {group.items.map(({ rule, index }) => (
            <RuleEditor
              key={`${rule.type}-${index}`}
              collection={collection}
              settings={settings}
              rule={rule}
              isTarget={rule.type === activeRuleKey}
              onRemove={() => onRemove(collection, index)}
              onUpdate={(nextRule) => onUpdate(collection, index, nextRule)}
            />
          ))}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

function RuleEditor({
  collection,
  settings,
  rule,
  isTarget,
  onRemove,
  onUpdate
}: {
  collection: "signals" | "facts";
  settings: NlpSettings;
  rule: RuleSetting;
  isTarget: boolean;
  onRemove: () => void;
  onUpdate: (rule: RuleSetting) => void;
}) {
  const [expanded, setExpanded] = useState(isTarget);

  useEffect(() => {
    if (isTarget) {
      setExpanded(true);
    }
  }, [isTarget]);

  return (
    <Accordion
      id={settingsTargetElementId({
        kind: collection === "signals" ? "signal" : "fact",
        key: rule.type
      })}
      className={isTarget ? "settings-target-highlight" : undefined}
      tabIndex={isTarget ? -1 : undefined}
      variant="outlined"
      disableGutters
      expanded={expanded}
      onChange={(_, nextExpanded) => setExpanded(nextExpanded)}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ alignItems: "center", display: "flex", gap: 1, minWidth: 0, width: "100%" }}>
          {rule.color && <Box className="rule-color" sx={{ backgroundColor: rule.color }} />}
          <Typography sx={{ flex: 1, fontWeight: 700 }} noWrap>
            {rule.label}
          </Typography>
          <Chip label={ruleFolderLabel(rule)} size="small" variant="outlined" />
          <Chip label={rule.type} size="small" variant="outlined" />
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <Box className="rule-grid">
            <TextField label="type" value={rule.type} onChange={(event) => onUpdate({ ...rule, type: event.target.value })} />
            <TextField label="label" value={rule.label} onChange={(event) => onUpdate({ ...rule, label: event.target.value })} />
            <TextField
              label="Папка"
              value={rule.group ?? ""}
              onChange={(event) => onUpdate({ ...rule, group: event.target.value || null })}
            />
            <TextField
              label="confidence"
              type="number"
              value={rule.confidence ?? ""}
              onChange={(event) =>
                onUpdate({ ...rule, confidence: event.target.value === "" ? null : Number(event.target.value) })
              }
              slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
            />
            <TextField
              label="color"
              type="color"
              value={rule.color ?? "#0b57d0"}
              onChange={(event) => onUpdate({ ...rule, color: event.target.value })}
            />
          </Box>
          <ExactPhraseEditor
            phrases={rule.phrases}
            onUpdate={(phrases) => onUpdate({ ...rule, phrases })}
          />
          <SemanticPatternEditor
            patterns={rule.patterns}
            onUpdate={(patterns) => onUpdate({ ...rule, patterns })}
          />
          {collection === "signals" && (
            <SignalMatchEditor
              match={normalizeRuleMatch(rule.match)}
              settings={settings}
              onUpdate={(match) => onUpdate({ ...rule, match })}
            />
          )}
          <Box>
            <IconButton aria-label="Удалить правило" color="error" onClick={onRemove}>
              <DeleteIcon />
            </IconButton>
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

type GroupedRule = {
  label: string;
  items: Array<{ rule: RuleSetting; index: number }>;
};

function groupRulesByFolder(rules: RuleSetting[]): GroupedRule[] {
  const groups = new Map<string, GroupedRule>();
  rules.forEach((rule, index) => {
    const label = ruleFolderLabel(rule);
    if (!groups.has(label)) {
      groups.set(label, { label, items: [] });
    }
    groups.get(label)?.items.push({ rule, index });
  });
  return [...groups.values()];
}

function ruleFolderLabel(rule: RuleSetting) {
  return rule.group?.trim() || "Без папки";
}

type RuleDialogState = {
  index: number | null;
  value: string;
};

function ExactPhraseEditor({
  phrases,
  onUpdate
}: {
  phrases: string[][];
  onUpdate: (phrases: string[][]) => void;
}) {
  const [dialog, setDialog] = useState<RuleDialogState | null>(null);

  function savePhrase() {
    if (!dialog) {
      return;
    }
    const phrase = textToExactPhrase(dialog.value);
    if (phrase.length === 0) {
      return;
    }
    const nextPhrases =
      dialog.index === null
        ? [...phrases, phrase]
        : phrases.map((item, itemIndex) => (itemIndex === dialog.index ? phrase : item));
    onUpdate(nextPhrases);
    setDialog(null);
  }

  return (
    <Stack spacing={1}>
      <RuleListHeader
        title="Точные фразы"
        description="Совпадение по такой же последовательности слов без учета регистра. Используй для устойчивых выражений и аббревиатур; бренды, модели и протоколы держи в словарях."
        addLabel="Добавить точную фразу"
        onAdd={() => setDialog({ index: null, value: "" })}
      />
      {phrases.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Точных фраз нет.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {phrases.map((phrase, index) => {
            const phraseText = phrase.join(" ");
            return (
              <Box className="rule-list-row" key={`${phraseText}-${index}`}>
                <Typography sx={{ flex: 1 }} noWrap>
                  {phraseText}
                </Typography>
                <Tooltip title="Редактировать">
                  <IconButton
                    aria-label={`Редактировать точную фразу: ${phraseText}`}
                    onClick={() => setDialog({ index, value: phraseText })}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Удалить">
                  <IconButton
                    aria-label={`Удалить точную фразу: ${phraseText}`}
                    color="error"
                    onClick={() => onUpdate(phrases.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            );
          })}
        </Stack>
      )}
      <RuleTextDialog
        open={dialog !== null}
        title={dialog?.index === null ? "Добавить точную фразу" : "Редактировать точную фразу"}
        label="Текст точной фразы"
        value={dialog?.value ?? ""}
        saveLabel="Сохранить фразу"
        onChange={(value) => setDialog((current) => (current ? { ...current, value } : current))}
        onClose={() => setDialog(null)}
        onSave={savePhrase}
      />
    </Stack>
  );
}

function SemanticPatternEditor({
  patterns,
  onUpdate
}: {
  patterns: RulePatternSetting[];
  onUpdate: (patterns: RulePatternSetting[]) => void;
}) {
  const [dialog, setDialog] = useState<RuleDialogState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function savePattern() {
    if (!dialog || !dialog.value.trim()) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/semantic-pattern`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: dialog.value.trim() })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const semanticPattern = (await response.json()) as SemanticPatternResponse;
      const nextPattern: RulePatternSetting = {
        source_text: semanticPattern.source_text,
        tokens: semanticPattern.tokens
      };
      const nextPatterns =
        dialog.index === null
          ? [...patterns, nextPattern]
          : patterns.map((item, itemIndex) => (itemIndex === dialog.index ? nextPattern : item));
      onUpdate(nextPatterns);
      setDialog(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось построить лемматическое правило");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack spacing={1}>
      <RuleListHeader
        title="Лемматические фразы"
        description="Оператор вводит обычную фразу. Backend превращает слова в леммы, а правило потом находит разные падежи, роды и числа."
        addLabel="Добавить лемматическую фразу"
        onAdd={() => {
          setError(null);
          setDialog({ index: null, value: "" });
        }}
      />
      {patterns.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Лемматических фраз нет.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {patterns.map((pattern, index) => {
            const sourceText = patternSourceText(pattern);
            const lemmaText = patternLemmaText(pattern);
            return (
              <Box className="rule-list-row" key={`${sourceText}-${index}`}>
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography noWrap>{sourceText}</Typography>
                  <Typography variant="caption" color="text.secondary" noWrap>
                    {lemmaText}
                  </Typography>
                </Box>
                <Tooltip title="Редактировать">
                  <IconButton
                    aria-label={`Редактировать лемматическую фразу: ${sourceText}`}
                    onClick={() => {
                      setError(null);
                      setDialog({ index, value: sourceText });
                    }}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Удалить">
                  <IconButton
                    aria-label={`Удалить лемматическую фразу: ${sourceText}`}
                    color="error"
                    onClick={() => onUpdate(patterns.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            );
          })}
        </Stack>
      )}
      {error && <Alert severity="error">{error}</Alert>}
      <RuleTextDialog
        open={dialog !== null}
        title={dialog?.index === null ? "Добавить лемматическую фразу" : "Редактировать лемматическую фразу"}
        label="Текст правила"
        value={dialog?.value ?? ""}
        saveLabel="Сохранить правило"
        saving={saving}
        onChange={(value) => setDialog((current) => (current ? { ...current, value } : current))}
        onClose={() => {
          if (!saving) {
            setDialog(null);
          }
        }}
        onSave={() => {
          void savePattern();
        }}
      />
    </Stack>
  );
}

function SignalMatchEditor({
  match,
  settings,
  onUpdate
}: {
  match: RuleMatchSetting;
  settings: NlpSettings;
  onUpdate: (match: RuleMatchSetting) => void;
}) {
  function updateAliasDependency(index: number, dependency: AliasMatchSetting) {
    onUpdate({
      ...match,
      aliases: match.aliases.map((item, itemIndex) => (itemIndex === index ? dependency : item))
    });
  }

  function updateFactDependency(index: number, dependency: FactMatchSetting) {
    onUpdate({
      ...match,
      facts: match.facts.map((item, itemIndex) => (itemIndex === index ? dependency : item))
    });
  }

  const allFactTypes = factTypeOptions(settings, match.facts.flatMap((dependency) => dependency.types));

  return (
    <Stack spacing={2}>
      <Stack spacing={1}>
        <RuleListHeader
          title="Зависимости от словарей"
          description="Сигнал срабатывает от выбранных alias-записей: брендов, протоколов, устройств или ПО. Названия вроде Neptun держим здесь, в словарях."
          addLabel="Добавить зависимость от словаря"
          onAdd={() =>
            onUpdate({
              ...match,
              aliases: [...match.aliases, { catalog: defaultAliasCatalog, keys: [], kinds: [] }]
            })
          }
        />
        {match.aliases.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Зависимостей от словарей нет.
          </Typography>
        ) : (
          <Stack spacing={1}>
            {match.aliases.map((dependency, index) => {
              const catalog = aliasCatalogFromDependency(dependency);
              const keys = dependency.keys ?? [];
              const aliasOptions = aliasOptionsForCatalog(settings, catalog, keys);
              const selectedAliases = selectedAliasOptions(settings, catalog, keys);
              const kindOptions = uniqueStrings([...aliasKindOptions, ...(dependency.kinds ?? [])]);

              return (
                <Box className="rule-list-row" key={`alias-${catalog}-${index}`} sx={{ alignItems: "flex-start" }}>
                  <Box
                    sx={{
                      alignItems: "start",
                      display: "grid",
                      flex: 1,
                      gap: 1,
                      gridTemplateColumns: { xs: "1fr", md: "180px minmax(220px, 1fr) minmax(180px, 0.6fr)" },
                      minWidth: 0
                    }}
                  >
                    <TextField
                      label="Каталог зависимости"
                      select
                      value={catalog}
                      onChange={(event) =>
                        updateAliasDependency(index, {
                          catalog: aliasCatalogFromText(event.target.value),
                          catalogs: [],
                          keys: [],
                          kinds: []
                        })
                      }
                      slotProps={{ select: { native: true } }}
                      size="small"
                      fullWidth
                    >
                      {aliasCatalogDefinitions.map((definition) => (
                        <option key={definition.name} value={definition.name}>
                          {definition.label}
                        </option>
                      ))}
                    </TextField>
                    <Autocomplete
                      multiple
                      size="small"
                      options={aliasOptions}
                      value={selectedAliases}
                      isOptionEqualToValue={(option, value) => option.key === value.key}
                      getOptionLabel={(option) => option.label}
                      onChange={(_event, values) =>
                        updateAliasDependency(index, {
                          ...dependency,
                          catalog,
                          catalogs: [],
                          keys: values.map((value) => value.key)
                        })
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="Alias"
                          helperText="Выбери конкретные записи словаря, которые должны включать этот сигнал."
                        />
                      )}
                    />
                    <Autocomplete
                      multiple
                      size="small"
                      options={kindOptions}
                      value={dependency.kinds ?? []}
                      getOptionLabel={(option) => `type: ${option}`}
                      onChange={(_event, values) =>
                        updateAliasDependency(index, {
                          ...dependency,
                          catalog,
                          catalogs: [],
                          kinds: values
                        })
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="Типы alias"
                          helperText="Оставь пустым, если достаточно выбранного каталога и alias."
                        />
                      )}
                    />
                  </Box>
                  <Tooltip title="Удалить">
                    <IconButton
                      aria-label={`Удалить зависимость от словаря: ${catalog}`}
                      color="error"
                      onClick={() =>
                        onUpdate({ ...match, aliases: match.aliases.filter((_, itemIndex) => itemIndex !== index) })
                      }
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Tooltip>
                </Box>
              );
            })}
          </Stack>
        )}
      </Stack>

      <Stack spacing={1}>
        <RuleListHeader
          title="Зависимости от фактов"
          description="Сигнал может опираться на факты, которые уже нашел Yargy или alias-словари. Здесь выбираются технические fact_type."
          addLabel="Добавить зависимость от факта"
          onAdd={() => onUpdate({ ...match, facts: [...match.facts, { types: [] }] })}
        />
        {match.facts.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Зависимостей от фактов нет.
          </Typography>
        ) : (
          <Stack spacing={1}>
            {match.facts.map((dependency, index) => (
              <Box className="rule-list-row" key={`fact-${index}`} sx={{ alignItems: "flex-start" }}>
                <Autocomplete
                  multiple
                  size="small"
                  options={allFactTypes}
                  value={dependency.types}
                  onChange={(_event, values) => updateFactDependency(index, { types: values })}
                  sx={{ flex: 1, minWidth: 0 }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Типы фактов"
                      helperText="Выбери один или несколько fact_type, которые должны включать этот сигнал."
                    />
                  )}
                />
                <Tooltip title="Удалить">
                  <IconButton
                    aria-label="Удалить зависимость от факта"
                    color="error"
                    onClick={() =>
                      onUpdate({ ...match, facts: match.facts.filter((_, itemIndex) => itemIndex !== index) })
                    }
                  >
                    <DeleteIcon />
                  </IconButton>
                </Tooltip>
              </Box>
            ))}
          </Stack>
        )}
      </Stack>
    </Stack>
  );
}

function RuleListHeader({
  title,
  description,
  addLabel,
  onAdd
}: {
  title: string;
  description: string;
  addLabel: string;
  onAdd: () => void;
}) {
  return (
    <Box className="rule-list-header">
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {description}
        </Typography>
      </Box>
      <Button aria-label={addLabel} startIcon={<AddIcon />} variant="outlined" onClick={onAdd}>
        Добавить
      </Button>
    </Box>
  );
}

function RuleTextDialog({
  open,
  title,
  label,
  value,
  saveLabel,
  saving = false,
  onChange,
  onClose,
  onSave
}: {
  open: boolean;
  title: string;
  label: string;
  value: string;
  saveLabel: string;
  saving?: boolean;
  onChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          fullWidth
          label={label}
          margin="dense"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Отмена
        </Button>
        <Button
          variant="contained"
          onClick={onSave}
          disabled={saving || !value.trim()}
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : undefined}
        >
          {saveLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function SystemSettingsTable({ settings }: { settings: SystemSetting[] }) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="h6">Runtime</Typography>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Ключ</TableCell>
              <TableCell>Значение</TableCell>
              <TableCell>Источник</TableCell>
              <TableCell>Редактирование</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {settings.map((item) => (
              <TableRow key={item.key}>
                <TableCell>{item.key}</TableCell>
                <TableCell>{item.value}</TableCell>
                <TableCell>{item.source}</TableCell>
                <TableCell>{item.editable ? "доступно" : "read-only"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

type AliasCatalogDefinition = {
  name: AliasCatalogName;
  label: string;
};

const aliasCatalogDefinitions: AliasCatalogDefinition[] = [
  { name: "vendors", label: "Вендоры" },
  { name: "protocols", label: "Протоколы" },
  { name: "devices", label: "Устройства" },
  { name: "software", label: "ПО" }
];

const defaultAliasMatchingSettings: AliasMatchingSettings = {
  normalize_separators: true,
  normalize_yo: true,
  normalize_latin_confusables: true,
  fuzzy_enabled: true,
  fuzzy_min_length: 5,
  fuzzy_max_distance: 1,
  fuzzy_long_min_length: 10,
  fuzzy_long_max_distance: 2,
  fuzzy_excluded_aliases: []
};

function normalizedAliasMatchingSettings(settings?: AliasMatchingSettings): AliasMatchingSettings {
  return {
    ...defaultAliasMatchingSettings,
    ...(settings ?? {}),
    fuzzy_excluded_aliases: settings?.fuzzy_excluded_aliases ?? []
  };
}

type AliasOption = {
  key: string;
  label: string;
};

const defaultAliasCatalog: AliasCatalogName = "vendors";
const aliasKindOptions = ["vendor", "protocol", "device", "software", "model"];

function isAliasCatalogName(value: string | null | undefined): value is AliasCatalogName {
  return aliasCatalogDefinitions.some((definition) => definition.name === value);
}

function aliasCatalogFromText(value: string): AliasCatalogName {
  return isAliasCatalogName(value) ? value : defaultAliasCatalog;
}

function aliasCatalogFromDependency(dependency: AliasMatchSetting): AliasCatalogName {
  const candidates = [dependency.catalog, ...(dependency.catalogs ?? [])];
  const catalog = candidates.find(isAliasCatalogName);
  return catalog ?? defaultAliasCatalog;
}

function aliasOptionsForCatalog(
  settings: NlpSettings,
  catalog: AliasCatalogName,
  selectedKeys: string[] = []
): AliasOption[] {
  const options = settings[catalog].map((alias) => ({
    key: alias.key,
    label: `${alias.key} — ${alias.canonical}`
  }));
  const knownKeys = new Set(options.map((option) => option.key));
  selectedKeys
    .filter((key) => !knownKeys.has(key))
    .forEach((key) => {
      knownKeys.add(key);
      options.push({ key, label: key });
    });
  return options;
}

function selectedAliasOptions(
  settings: NlpSettings,
  catalog: AliasCatalogName,
  selectedKeys: string[] = []
): AliasOption[] {
  const optionsByKey = new Map(
    aliasOptionsForCatalog(settings, catalog, selectedKeys).map((option) => [option.key, option])
  );
  return uniqueStrings(selectedKeys).map((key) => optionsByKey.get(key) ?? { key, label: key });
}

function factTypeOptions(settings: NlpSettings, selectedTypes: string[] = []): string[] {
  const aliasFactTypes = aliasCatalogDefinitions.flatMap((definition) =>
    settings[definition.name].flatMap((alias) => alias.fact_types ?? [])
  );
  return uniqueStrings([
    ...settings.facts.map((fact) => fact.type),
    ...aliasFactTypes,
    ...Object.keys(settings.lead_scoring.fact_weights),
    ...selectedTypes
  ]).sort((left, right) => left.localeCompare(right));
}

function uniqueStrings(items: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  items.forEach((item) => {
    const value = item.trim();
    if (!value || seen.has(value)) {
      return;
    }
    seen.add(value);
    result.push(value);
  });
  return result;
}

function settingsTargetHash(target: SettingsTarget | null): string {
  if (!target) {
    return "";
  }
  if (target.kind === "signal") {
    return `#/settings/signals/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "fact") {
    return `#/settings/facts/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "alias") {
    return `#/settings/aliases/${target.catalog}/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "lead_signal_weight") {
    return `#/settings/lead-scoring/signal-weight/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "lead_fact_weight") {
    return `#/settings/lead-scoring/fact-weight/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "solution_area") {
    return `#/settings/lead-scoring/solution-area/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "customer_segment") {
    return `#/settings/lead-scoring/customer-segment/${encodeURIComponent(target.key)}`;
  }
  return `#/settings/lead-scoring/review-lane/${encodeURIComponent(target.key)}`;
}

function settingsTargetElementId(target: SettingsTarget): string {
  if (target.kind === "signal") {
    return `settings-target-signals-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "fact") {
    return `settings-target-facts-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "alias") {
    return `settings-target-aliases-${target.catalog}-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "lead_signal_weight") {
    return `settings-target-lead-scoring-signal-weight-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "lead_fact_weight") {
    return `settings-target-lead-scoring-fact-weight-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "solution_area") {
    return `settings-target-lead-scoring-solution-area-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "customer_segment") {
    return `settings-target-lead-scoring-customer-segment-${settingsTargetIdPart(target.key)}`;
  }
  return `settings-target-lead-scoring-review-lane-${settingsTargetIdPart(target.key)}`;
}

function settingsTargetIdPart(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function parseSettingsTargetHash(hash: string): SettingsTarget | null {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] !== "settings") {
    return null;
  }
  if (parts[1] === "signals" && parts[2]) {
    return { kind: "signal", key: parts[2] };
  }
  if (parts[1] === "facts" && parts[2]) {
    return { kind: "fact", key: parts[2] };
  }
  if (parts[1] === "aliases" && isAliasCatalogName(parts[2]) && parts[3]) {
    return { kind: "alias", catalog: parts[2], key: parts[3] };
  }
  if (parts[1] === "lead-scoring" && parts[3]) {
    if (parts[2] === "signal-weight") {
      return { kind: "lead_signal_weight", key: parts[3] };
    }
    if (parts[2] === "fact-weight") {
      return { kind: "lead_fact_weight", key: parts[3] };
    }
    if (parts[2] === "solution-area") {
      return { kind: "solution_area", key: parts[3] };
    }
    if (parts[2] === "customer-segment") {
      return { kind: "customer_segment", key: parts[3] };
    }
    if (parts[2] === "review-lane") {
      return { kind: "review_lane", key: parts[3] };
    }
  }
  return null;
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

function settingsSectionForTarget(target: SettingsTarget): SettingsSection {
  if (target.kind === "signal") {
    return "signals";
  }
  if (target.kind === "fact") {
    return "facts";
  }
  if (target.kind === "alias") {
    return "aliases";
  }
  return "lead_scoring";
}

function settingsTargetTitle(target: SettingsTarget, settings: NlpSettings): string {
  if (target.kind === "signal") {
    return `Настройка: ${settings.signals.find((item) => item.type === target.key)?.label ?? target.key}`;
  }
  if (target.kind === "fact") {
    return `Настройка: ${settings.facts.find((item) => item.type === target.key)?.label ?? target.key}`;
  }
  if (target.kind === "alias") {
    return `Настройка: ${settings[target.catalog].find((item) => item.key === target.key)?.canonical ?? target.key}`;
  }
  if (target.kind === "lead_signal_weight" || target.kind === "lead_fact_weight") {
    return `Настройка веса: ${settingsTypeLabel(settings, target.key)}`;
  }
  if (target.kind === "solution_area") {
    return `Настройка: ${settings.lead_scoring.solution_areas[target.key]?.label ?? target.key}`;
  }
  if (target.kind === "customer_segment") {
    return `Настройка: ${settings.lead_scoring.customer_segments[target.key]?.label ?? target.key}`;
  }
  return `Настройка: ${settings.lead_scoring.review_lanes.find((item) => item.key === target.key)?.label ?? target.key}`;
}

function settingsTargetForType(settings: NlpSettings, type: string): SettingsTarget | null {
  if (settings.signals.some((signal) => signal.type === type)) {
    return { kind: "signal", key: type };
  }
  if (settings.facts.some((fact) => fact.type === type)) {
    return { kind: "fact", key: type };
  }
  if (Object.hasOwn(settings.lead_scoring.signal_weights, type)) {
    return { kind: "lead_signal_weight", key: type };
  }
  if (Object.hasOwn(settings.lead_scoring.fact_weights, type)) {
    return { kind: "lead_fact_weight", key: type };
  }
  if (Object.hasOwn(settings.lead_scoring.solution_areas, type)) {
    return { kind: "solution_area", key: type };
  }
  if (Object.hasOwn(settings.lead_scoring.customer_segments, type)) {
    return { kind: "customer_segment", key: type };
  }
  return null;
}

function settingsTypeLabel(settings: NlpSettings, type: string): string {
  return (
    settings.signals.find((signal) => signal.type === type)?.label ??
    settings.facts.find((fact) => fact.type === type)?.label ??
    settings.lead_scoring.solution_areas[type]?.label ??
    settings.lead_scoring.customer_segments[type]?.label ??
    type
  );
}

function aliasLabel(settings: NlpSettings, catalog: AliasCatalogName, key: string): string {
  const alias = settings[catalog].find((item) => item.key === key);
  return alias ? `${alias.key} — ${alias.canonical}` : key;
}

function aliasTypeForCatalog(catalog: AliasCatalogName): AliasSetting["type"] {
  if (catalog === "vendors") {
    return "vendor";
  }
  if (catalog === "protocols") {
    return "protocol";
  }
  if (catalog === "devices") {
    return "device";
  }
  return "software";
}

function aliasTypeFromText(value: string): AliasSetting["type"] {
  const normalizedValue = value.trim();
  if (
    normalizedValue === "vendor" ||
    normalizedValue === "protocol" ||
    normalizedValue === "device" ||
    normalizedValue === "software" ||
    normalizedValue === "model"
  ) {
    return normalizedValue;
  }
  return "device";
}

function textToExactPhrase(value: string): string[] {
  return value
    .trim()
    .toLocaleLowerCase("ru-RU")
    .split(/\s+/)
    .filter(Boolean);
}

function patternSourceText(pattern: RulePatternSetting) {
  return pattern.source_text?.trim() || patternLemmaText(pattern);
}

function patternLemmaText(pattern: RulePatternSetting) {
  return pattern.tokens.map((token) => token.value).join(" ");
}

function numberInput(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function numberRecordToText(record: Record<string, number>) {
  return Object.entries(record)
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
}

function textToNumberRecord(value: string): Record<string, number> {
  return Object.fromEntries(
    value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [key, ...rawValue] = line.split(":");
        return [key.trim(), numberInput(rawValue.join(":").trim())] as const;
      })
      .filter(([key]) => key)
  );
}

function stringListToText(items?: string[]) {
  return (items ?? []).join("\n");
}

function textToStringList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function normalizeRuleMatch(match?: RuleMatchSetting): RuleMatchSetting {
  return {
    aliases: match?.aliases ?? [],
    facts: match?.facts ?? []
  };
}

function reviewLaneMatchGroupsToText(groups?: ReviewLaneMatchGroupSetting[]) {
  return JSON.stringify(groups ?? [], null, 2);
}

function textToReviewLaneMatchGroups(
  value: string,
  fallback: ReviewLaneMatchGroupSetting[]
): ReviewLaneMatchGroupSetting[] {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return fallback;
    }
    return parsed.map(reviewLaneMatchGroupFromUnknown);
  } catch {
    return fallback;
  }
}

function reviewLaneMatchGroupFromUnknown(value: unknown): ReviewLaneMatchGroupSetting {
  const source = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
  return {
    signal_types: stringArrayFromUnknown(source.signal_types),
    fact_types: stringArrayFromUnknown(source.fact_types),
    reason_keys: stringArrayFromUnknown(source.reason_keys),
    solution_area_types: stringArrayFromUnknown(source.solution_area_types),
    customer_segment_types: stringArrayFromUnknown(source.customer_segment_types),
    intent_signal_types: stringArrayFromUnknown(source.intent_signal_types),
    noise_signal_types: stringArrayFromUnknown(source.noise_signal_types)
  };
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item)).filter(Boolean);
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

function Overview({
  result,
  onOpenSettings
}: {
  result: TextEnrichmentResult;
  onOpenSettings: (section: SettingsSection) => void;
}) {
  const typeLabels = useMemo(() => typeLabelMap(result), [result]);
  const dictionaryItems = result.facts.filter((item) => item.source === "alias_catalog");

  return (
    <Stack spacing={2}>
      {result.lead_assessment && (
        <LeadAssessmentPanel
          result={result}
          assessment={result.lead_assessment}
          typeLabels={typeLabels}
          onOpenSettings={() => onOpenSettings("lead_scoring")}
        />
      )}
      <AnnotatedText result={result} />
      <EvidenceTable
        title="Словарные сущности"
        kind="dictionary"
        items={dictionaryItems}
        emptyText="Словарные alias не найдены."
        settingsLabel="Открыть словари"
        onOpenSettings={() => onOpenSettings("aliases")}
      />
      <EvidenceTable
        title="Факты"
        kind="facts"
        items={result.facts}
        emptyText="Факты не найдены."
        settingsLabel="Открыть факты"
        onOpenSettings={() => onOpenSettings("facts")}
      />
      <EvidenceTable
        title="Доменные сигналы"
        kind="signals"
        items={result.domain_signals}
        emptyText="Доменные сигналы не найдены."
        settingsLabel="Открыть сигналы"
        onOpenSettings={() => onOpenSettings("signals")}
      />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {Object.entries(result.metrics).map(([key, value]) => (
          <Chip key={key} label={`${key}: ${value}`} variant="outlined" />
        ))}
      </Box>
    </Stack>
  );
}

function LeadAssessmentPanel({
  result,
  assessment,
  typeLabels,
  onOpenSettings
}: {
  result: TextEnrichmentResult;
  assessment: LeadAssessment;
  typeLabels: Map<string, string>;
  onOpenSettings: () => void;
}) {
  return (
    <Paper variant="outlined" className="lead-assessment-panel">
      <Stack spacing={2}>
        <Box sx={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: 1, justifyContent: "space-between" }}>
          <LeadAssessmentSummary assessment={assessment} />
          <Button size="small" startIcon={<SettingsIcon />} onClick={onOpenSettings}>
            Настройки оценки
          </Button>
        </Box>
        <ScoreFormula assessment={assessment} result={result} />
        <CategoryCalculationGroup
          title="Расчет направления решения"
          targetKind="solution_area"
          items={assessment.solution_areas}
          typeLabels={typeLabels}
          result={result}
        />
        <CategoryCalculationGroup
          title="Расчет сегмента клиентов"
          targetKind="customer_segment"
          items={assessment.customer_segments}
          typeLabels={typeLabels}
          result={result}
        />
        <ReviewLaneCalculation assessment={assessment} />
        <ChipGroup title="Шум" items={assessment.noise_signals.map((item) => item.label)} color="warning" />
      </Stack>
    </Paper>
  );
}

function ScoreFormula({
  assessment,
  result
}: {
  assessment: LeadAssessment;
  result: TextEnrichmentResult;
}) {
  if (assessment.reasons.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Формула score: совпавших весов нет, score = 0.
      </Typography>
    );
  }
  const rawScore = assessment.reasons.reduce((sum, reason) => sum + reason.weight, 0);

  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">Точный расчет оценки лида</Typography>
      <TableContainer>
        <Table size="small" aria-label="Точный расчет оценки лида">
          <TableHead>
            <TableRow>
              <TableCell>Причина</TableCell>
              <TableCell>Источник</TableCell>
              <TableCell>Вес</TableCell>
              <TableCell>Совпадения</TableCell>
              <TableCell>Настройки</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {assessment.reasons.map((reason) => (
              <TableRow key={`${reason.source}-${reason.key}`}>
                <TableCell>
                  <SettingLink target={reasonTypeTarget(reason, result)}>
                    {reason.label}
                  </SettingLink>
                </TableCell>
                <TableCell>{sourceLabel(reason.source)}</TableCell>
                <TableCell>
                  <SettingLink target={reasonWeightTarget(reason)}>
                    {formatSignedWeight(reason.weight)}
                  </SettingLink>
                </TableCell>
                <TableCell>{reason.matched_texts.join(", ")}</TableCell>
                <TableCell>
                  <InlineSettingsLinks
                    links={[
                      { label: "тип", target: reasonTypeTarget(reason, result) },
                      { label: "вес", target: reasonWeightTarget(reason) }
                    ]}
                  />
                </TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={2} sx={{ fontWeight: 700 }}>
                Итого
              </TableCell>
              <TableCell sx={{ fontWeight: 700 }}>{rawScore}</TableCell>
              <TableCell colSpan={2}>score = max(0, {rawScore}) = {assessment.score}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
      <Typography variant="caption" color="text.secondary">
        Порог лида применяется на backend; температура определяется по настроенным порогам lead/warm/hot.
      </Typography>
    </Stack>
  );
}

function CategoryCalculationGroup({
  title,
  targetKind,
  items,
  typeLabels,
  result
}: {
  title: string;
  targetKind: "solution_area" | "customer_segment";
  items: LeadCategory[];
  typeLabels: Map<string, string>;
  result: TextEnrichmentResult;
}) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{title}</Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Совпадений по настроенным типам нет.
        </Typography>
      ) : (
        <TableContainer>
          <Table size="small" aria-label={title}>
            <TableHead>
              <TableRow>
                <TableCell>Категория</TableCell>
                <TableCell>Найденные типы</TableCell>
                <TableCell>Почему</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.type}>
                  <TableCell>
                    <SettingLink target={categoryTarget(targetKind, item.type)}>
                      {item.label}
                    </SettingLink>
                  </TableCell>
                  <TableCell>
                    <InlineSettingsLinks
                      links={item.matched_types.map((type) => ({
                        label: typeLabels.get(type) ?? type,
                        target: matchedTypeTarget(type, result)
                      }))}
                    />
                  </TableCell>
                  <TableCell>Сработало, потому что найдены указанные типы.</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}

function ReviewLaneCalculation({ assessment }: { assessment: LeadAssessment }) {
  const lane = assessment.review_lane;
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">Расчет очереди разбора</Typography>
      {lane ? (
        <TableContainer>
          <Table size="small" aria-label="Расчет очереди разбора">
            <TableHead>
              <TableRow>
                <TableCell>Очередь</TableCell>
                <TableCell>Совпавшие группы</TableCell>
                <TableCell>Почему</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>
                  <SettingLink target={{ kind: "review_lane", key: lane.key }}>
                    {lane.label}
                  </SettingLink>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                    {lane.matched_group_indexes.map((index) => (
                      <SettingLink key={index} target={{ kind: "review_lane", key: lane.key }}>
                        match group {index + 1}
                      </SettingLink>
                    ))}
                  </Box>
                </TableCell>
                <TableCell>
                  Очередь выбрана первым подходящим правилом `review_lanes` по priority:
                  score/temperature прошли ограничения, excluded-условия не сработали,
                  все обязательные match groups совпали.
                  {lane.description ? ` ${lane.description}` : ""}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">
          Очереди разбора в активной конфигурации не заданы.
        </Typography>
      )}
    </Stack>
  );
}

function LeadAssessmentSummary({
  assessment,
  compact = false
}: {
  assessment: LeadAssessment;
  compact?: boolean;
}) {
  return (
    <Box sx={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: 1 }}>
      <Chip
        label={leadTemperatureLabel(assessment)}
        color={leadTemperatureColor(assessment)}
        size={compact ? "small" : "medium"}
      />
      <Chip label={`${assessment.score} баллов`} variant="outlined" size={compact ? "small" : "medium"} />
      <Typography variant={compact ? "caption" : "body2"} color="text.secondary">
        {assessment.is_lead ? "Потенциальный клиент ПУР" : "Недостаточно признаков лида"}
      </Typography>
    </Box>
  );
}

function ChipGroup({
  title,
  items,
  color = "default"
}: {
  title: string;
  items: string[];
  color?: "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning";
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">{title}</Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {items.map((item) => (
          <Chip key={item} label={item} color={color} size="small" variant={color === "default" ? "outlined" : "filled"} />
        ))}
      </Box>
    </Stack>
  );
}

function leadTemperatureLabel(assessment: LeadAssessment) {
  if (!assessment.is_lead) {
    return "Не лид";
  }
  if (assessment.temperature === "hot") {
    return "Горячий лид";
  }
  if (assessment.temperature === "warm") {
    return "Теплый лид";
  }
  return "Холодный лид";
}

function leadTemperatureColor(
  assessment: LeadAssessment
): "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning" {
  if (!assessment.is_lead) {
    return "default";
  }
  if (assessment.temperature === "hot") {
    return "error";
  }
  if (assessment.temperature === "warm") {
    return "warning";
  }
  return "success";
}

function AnnotatedText({ result }: { result: TextEnrichmentResult }) {
  const spans = useMemo(() => collectNonOverlappingSpans(result), [result]);
  const codeUnitOffsets = useMemo(() => codePointToCodeUnitOffsets(result.original_text), [result.original_text]);
  const parts: ReactNode[] = [];
  let cursor = 0;

  for (const span of spans) {
    const start = codePointOffsetToCodeUnit(span.range.start, codeUnitOffsets);
    const stop = codePointOffsetToCodeUnit(span.range.stop, codeUnitOffsets);
    if (start > cursor) {
      parts.push(<span key={`text-${cursor}`}>{result.original_text.slice(cursor, start)}</span>);
    }
    parts.push(
      <mark
        key={span.id}
        className="annotation"
        style={{ borderColor: span.color ?? "#0b57d0", backgroundColor: `${span.color ?? "#0b57d0"}1a` }}
        title={`${span.label ?? span.type}: ${span.source}`}
      >
        {result.original_text.slice(start, stop)}
      </mark>
    );
    cursor = stop;
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

function EvidenceTable({
  title,
  kind,
  items,
  emptyText,
  settingsLabel,
  onOpenSettings
}: {
  title: string;
  kind: "dictionary" | "facts" | "signals";
  items: SpanItem[];
  emptyText: string;
  settingsLabel: string;
  onOpenSettings: () => void;
}) {
  return (
    <Stack spacing={1}>
      <Box sx={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: 1, justifyContent: "space-between" }}>
        <Typography variant="subtitle2">{title}</Typography>
        <Button size="small" startIcon={<SettingsIcon />} onClick={onOpenSettings}>
          {settingsLabel}
        </Button>
      </Box>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyText}
        </Typography>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Что найдено</TableCell>
                <TableCell>Тип</TableCell>
                <TableCell>Источник</TableCell>
                <TableCell>Почему</TableCell>
                <TableCell>Настройки</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => {
                const primaryTarget = spanPrimaryTarget(item, kind);
                const settingLinks = spanSettingLinks(item, kind);
                return (
                  <TableRow key={`${title}-${item.id}`}>
                    <TableCell>{item.text}</TableCell>
                    <TableCell>
                      <SettingLink target={primaryTarget}>
                        {item.label ?? item.type}
                      </SettingLink>
                    </TableCell>
                    <TableCell>{sourceLabel(item.source)}</TableCell>
                    <TableCell>{item.explanation ?? fallbackExplanation(item)}</TableCell>
                    <TableCell>
                      <InlineSettingsLinks links={settingLinks} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}

type InlineSettingsLink = {
  label: ReactNode;
  target: SettingsTarget | null;
};

function InlineSettingsLinks({ links }: { links: InlineSettingsLink[] }) {
  const visibleLinks = links.filter((link) => link.label !== "");
  if (visibleLinks.length === 0) {
    return <Typography variant="caption" color="text.secondary">Нет ссылки</Typography>;
  }
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
      {visibleLinks.map((link, index) => (
        <SettingLink key={`${settingsTargetHash(link.target)}-${String(link.label)}-${index}`} target={link.target}>
          {link.label}
        </SettingLink>
      ))}
    </Box>
  );
}

function SettingLink({
  target,
  children
}: {
  target: SettingsTarget | null;
  children: ReactNode;
}) {
  if (!target) {
    return <>{children}</>;
  }
  const href = settingsTargetHash(target);
  return (
    <MuiLink
      href={href}
      underline="hover"
      title="ЛКМ - быстрый просмотр, Ctrl/Cmd или средняя кнопка - открыть страницу настройки"
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
          return;
        }
        event.preventDefault();
        window.dispatchEvent(new CustomEvent(openSettingsTargetEvent, { detail: target }));
      }}
    >
      {children}
    </MuiLink>
  );
}

function spanPrimaryTarget(item: SpanItem, kind: "dictionary" | "facts" | "signals"): SettingsTarget | null {
  const aliasTarget = settingsTargetFromRef(item.settings_refs?.find((ref) => ref.section === "aliases"));
  const signalTarget = settingsTargetFromRef(item.settings_refs?.find((ref) => ref.section === "signals"));
  const factTarget = settingsTargetFromRef(item.settings_refs?.find((ref) => ref.section === "facts"));
  if (kind === "dictionary") {
    return aliasTarget;
  }
  if (kind === "signals") {
    return signalTarget ?? { kind: "signal", key: item.type };
  }
  if (item.source === "alias_catalog") {
    return aliasTarget ?? { kind: "lead_fact_weight", key: item.type };
  }
  return factTarget ?? { kind: "fact", key: item.type };
}

function spanSettingLinks(item: SpanItem, kind: "dictionary" | "facts" | "signals"): InlineSettingsLink[] {
  const links = (item.settings_refs ?? [])
    .map((ref) => ({
      label: ref.label,
      target: settingsTargetFromRef(ref)
    }))
    .filter((link) => link.target);
  const primaryTarget = spanPrimaryTarget(item, kind);
  if (links.length === 0 && primaryTarget) {
    return [{ label: item.label ?? item.type, target: primaryTarget }];
  }
  return links;
}

function settingsTargetFromRef(ref: SettingReference | undefined): SettingsTarget | null {
  if (!ref) {
    return null;
  }
  if (ref.section === "signals") {
    return { kind: "signal", key: ref.key };
  }
  if (ref.section === "facts") {
    return { kind: "fact", key: ref.key };
  }
  if (ref.section === "aliases" && isAliasCatalogName(ref.catalog)) {
    return { kind: "alias", catalog: ref.catalog, key: ref.key };
  }
  return null;
}

function reasonTypeTarget(reason: LeadReason, result: TextEnrichmentResult): SettingsTarget | null {
  if (reason.source === "domain_signal") {
    return { kind: "signal", key: reason.key };
  }
  if (reason.source === "fact") {
    const hasFactRuleMatch = result.facts.some((fact) => fact.type === reason.key && fact.source === "yargy");
    return hasFactRuleMatch ? { kind: "fact", key: reason.key } : { kind: "lead_fact_weight", key: reason.key };
  }
  return null;
}

function reasonWeightTarget(reason: LeadReason): SettingsTarget {
  return reason.source === "domain_signal"
    ? { kind: "lead_signal_weight", key: reason.key }
    : { kind: "lead_fact_weight", key: reason.key };
}

function categoryTarget(kind: "solution_area" | "customer_segment", key: string): SettingsTarget {
  return kind === "solution_area"
    ? { kind: "solution_area", key }
    : { kind: "customer_segment", key };
}

function matchedTypeTarget(type: string, result: TextEnrichmentResult): SettingsTarget | null {
  if (result.domain_signals.some((signal) => signal.type === type)) {
    return { kind: "signal", key: type };
  }
  if (result.facts.some((fact) => fact.type === type && fact.source === "yargy")) {
    return { kind: "fact", key: type };
  }
  if (result.lead_assessment?.reasons.some((reason) => reason.source === "fact" && reason.key === type)) {
    return { kind: "lead_fact_weight", key: type };
  }
  return null;
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

function typeLabelMap(result: TextEnrichmentResult): Map<string, string> {
  const labels = new Map<string, string>();
  for (const item of [...result.entities, ...result.facts, ...result.domain_signals]) {
    if (item.label) {
      labels.set(item.type, item.label.includes(":") ? item.label.split(":", 1)[0] : item.label);
    }
  }
  for (const reason of result.lead_assessment?.reasons ?? []) {
    labels.set(reason.key, reason.label);
  }
  return labels;
}

function codePointToCodeUnitOffsets(text: string): number[] {
  const offsets = [0];
  let codeUnitOffset = 0;
  for (const char of text) {
    codeUnitOffset += char.length;
    offsets.push(codeUnitOffset);
  }
  return offsets;
}

function codePointOffsetToCodeUnit(codePointOffset: number, offsets: number[]): number {
  if (codePointOffset <= 0) {
    return 0;
  }
  if (codePointOffset >= offsets.length) {
    return offsets[offsets.length - 1] ?? 0;
  }
  return offsets[codePointOffset] ?? 0;
}

function sourceLabel(source: string): string {
  if (source === "domain_signal") {
    return "Доменный сигнал";
  }
  if (source === "fact") {
    return "Факт";
  }
  if (source === "alias_catalog") {
    return "Словарь";
  }
  if (source === "fact_dependency") {
    return "Зависимость от факта";
  }
  if (source === "yargy") {
    return "Правило Yargy";
  }
  if (source === "natasha") {
    return "Natasha";
  }
  return source;
}

function fallbackExplanation(item: SpanItem): string {
  if (item.source === "alias_catalog") {
    return "Найдено совпадение в alias-словаре активной NLP-конфигурации.";
  }
  if (item.source === "fact_dependency") {
    return "Сигнал построен из уже найденного факта по match.facts.";
  }
  if (item.source === "yargy") {
    return "Сработало точное или лемматическое правило активной NLP-конфигурации.";
  }
  return "Источник вернул этот span без дополнительного объяснения.";
}

function formatSignedWeight(value: number): string {
  return value >= 0 ? `+${value}` : String(value);
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
