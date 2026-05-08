import AddIcon from "@mui/icons-material/Add";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ErrorIcon from "@mui/icons-material/Error";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsightsIcon from "@mui/icons-material/Insights";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import SettingsIcon from "@mui/icons-material/Settings";
import VisibilityIcon from "@mui/icons-material/Visibility";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AppBar,
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
  Paper,
  Stack,
  Switch,
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
  Tooltip,
  Typography,
  createTheme,
  useMediaQuery
} from "@mui/material";
import { FormEvent, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { AnalyticsPage } from "./AnalyticsPage";

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

type NlpSettings = {
  pipeline: {
    stages: PipelineStageSetting[];
  };
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

type SettingsSnapshot = {
  nlp: NlpSettings;
  system: SystemSetting[];
};

type AliasCatalogName = "vendors" | "protocols" | "devices" | "software";

type SettingsSection = "pipeline" | "signals" | "facts" | "aliases" | "lead_scoring" | "system";

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
  const [activePage, setActivePage] = useState(0);
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
  const isNarrowScreen = useMediaQuery(theme.breakpoints.down("sm"));

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

  function handlePageChange(_: SyntheticEvent, value: number) {
    setActivePage(value);
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box className="app-shell">
        <AppBar position="static" color="default" elevation={0} className="top-bar">
          <Toolbar variant="dense" className="top-toolbar">
            <AutoAwesomeIcon color="primary" fontSize="small" />
            <Typography variant="subtitle1" component="h1" className="app-title" sx={{ ml: 1, fontWeight: 700 }}>
              PUR Leads v2 - обогащение текста
            </Typography>
            <Tabs
              value={activePage}
              onChange={handlePageChange}
              className="main-nav"
              variant="scrollable"
              scrollButtons="auto"
              allowScrollButtonsMobile
              aria-label="Основная навигация"
            >
              <Tab label="Обогащение" />
              <Tab icon={<InsightsIcon fontSize="small" />} iconPosition="start" label="Аналитика" />
              <Tab icon={<SettingsIcon fontSize="small" />} iconPosition="start" label="Настройки" />
              <Tab icon={<HelpOutlineIcon fontSize="small" />} iconPosition="start" label="Справка" />
            </Tabs>
          </Toolbar>
        </AppBar>

        <Container maxWidth={false} className="workspace">
          {activePage === 0 ? (
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
          ) : activePage === 1 ? (
            <AnalyticsPage apiBaseUrl={apiBaseUrl} />
          ) : activePage === 2 ? (
            <SettingsCenter />
          ) : (
            <SettingsHelpPage />
          )}
        </Container>
      </Box>
    </ThemeProvider>
  );
}

function SettingsCenter() {
  const [settings, setSettings] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<NlpSettings | null>(null);
  const [section, setSection] = useState<SettingsSection>("signals");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState(
    "Подскажите, где можно заказать систему видеонаблюдения для квартиры?"
  );
  const [previewResult, setPreviewResult] = useState<TextEnrichmentResult | null>(null);

  useEffect(() => {
    let active = true;
    async function loadSettings() {
      setLoading(true);
      setSettingsError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/settings`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const snapshot = (await response.json()) as SettingsSnapshot;
        if (active) {
          setSettings(snapshot);
          setDraft(snapshot.nlp);
        }
      } catch (caught) {
        if (active) {
          setSettingsError(caught instanceof Error ? caught.message : "Не удалось загрузить настройки");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void loadSettings();
    return () => {
      active = false;
    };
  }, []);

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
      setSettings((current) => (current ? { ...current, nlp: saved } : current));
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

  const dirty = JSON.stringify(settings?.nlp ?? null) !== JSON.stringify(draft);

  return (
    <Box className="settings-shell">
      <Paper variant="outlined" className="settings-sidebar">
        <Typography variant="subtitle2" color="text.secondary">
          Настройки
        </Typography>
        <Button
          fullWidth
          variant={section === "pipeline" ? "contained" : "text"}
          onClick={() => setSection("pipeline")}
        >
          Pipeline
        </Button>
        <Button fullWidth variant={section === "signals" ? "contained" : "text"} onClick={() => setSection("signals")}>
          Доменные сигналы
        </Button>
        <Button fullWidth variant={section === "facts" ? "contained" : "text"} onClick={() => setSection("facts")}>
          Факты
        </Button>
        <Button
          fullWidth
          variant={section === "aliases" ? "contained" : "text"}
          onClick={() => setSection("aliases")}
        >
          Словари
        </Button>
        <Button
          fullWidth
          variant={section === "lead_scoring" ? "contained" : "text"}
          onClick={() => setSection("lead_scoring")}
        >
          Оценка лида
        </Button>
        <Button fullWidth variant={section === "system" ? "contained" : "text"} onClick={() => setSection("system")}>
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
        {settingsError && <Alert severity="error">{settingsError}</Alert>}
        {settingsMessage && <Alert severity="success">{settingsMessage}</Alert>}

        {draft && !loading && (
          <Box className="settings-content-grid">
            <Paper variant="outlined" className="settings-panel">
              {section === "pipeline" && <PipelineSettingsEditor draft={draft} onStageChange={updateStage} />}
              {section === "signals" && (
                <RuleCollectionEditor
                  title="Доменные сигналы"
                  collection="signals"
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
                  rules={draft.facts}
                  onAdd={addRule}
                  onRemove={removeRule}
                  onUpdate={updateRule}
                />
              )}
              {section === "aliases" && (
                <AliasCatalogsEditor
                  settings={draft}
                  onAdd={addAlias}
                  onRemove={removeAlias}
                  onUpdate={updateAlias}
                />
              )}
              {section === "lead_scoring" && (
                <LeadScoringSettingsEditor
                  settings={draft.lead_scoring}
                  onUpdate={updateLeadScoring}
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
                    <TableCell>используй для брендов, протоколов, `Wi-Fi`, `220v`, `white box`</TableCell>
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
                    <TableCell>`vendors:yandex, aqara`, `software:alice`, `devices:leak_sensor`</TableCell>
                    <TableCell>если найден alias с указанным ключом/каталогом, появляется этот доменный сигнал</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>match.facts</TableCell>
                    <TableCell>зависимости сигнала от уже найденных фактов</TableCell>
                    <TableCell>`automation_component`, `vendor`, `service_location`</TableCell>
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
                    <TableCell>сигнал явно ссылается на `vendors:neptun`; "Нептун" не добавляем в `phrases`, но сигнал появляется с `source=alias_catalog`</TableCell>
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
  onStageChange
}: {
  draft: NlpSettings;
  onStageChange: (index: number, enabled: boolean) => void;
}) {
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
    </Stack>
  );
}

function AliasCatalogsEditor({
  settings,
  onAdd,
  onRemove,
  onUpdate
}: {
  settings: NlpSettings;
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
  onAdd,
  onRemove,
  onUpdate
}: {
  definition: AliasCatalogDefinition;
  aliases: AliasSetting[];
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
          onRemove={() => onRemove(index)}
          onUpdate={(nextAlias) => onUpdate(index, nextAlias)}
        />
      ))}
    </Stack>
  );
}

function AliasEditor({
  alias,
  onRemove,
  onUpdate
}: {
  alias: AliasSetting;
  onRemove: () => void;
  onUpdate: (alias: AliasSetting) => void;
}) {
  return (
    <Accordion variant="outlined" disableGutters>
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
  onUpdate
}: {
  settings: LeadScoringSettings;
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
        <TextField
          label="signal weights"
          helperText="Одна строка: type: weight"
          value={numberRecordToText(settings.signal_weights)}
          onChange={(event) => onUpdate({ ...settings, signal_weights: textToNumberRecord(event.target.value) })}
          multiline
          minRows={8}
          fullWidth
        />
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
      <CategoryMappingEditor
        title="Направления решений"
        mappings={settings.solution_areas}
        onUpdate={(solutionAreas) => onUpdate({ ...settings, solution_areas: solutionAreas })}
      />
      <CategoryMappingEditor
        title="Сегменты клиентов"
        mappings={settings.customer_segments}
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
        onAdd={addLane}
        onRemove={removeLane}
        onUpdate={updateLane}
      />
    </Stack>
  );
}

function ReviewLaneSettingsEditor({
  lanes,
  onAdd,
  onRemove,
  onUpdate
}: {
  lanes: ReviewLaneSetting[];
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
          onRemove={() => onRemove(index)}
          onUpdate={(nextLane) => onUpdate(index, nextLane)}
        />
      ))}
    </Stack>
  );
}

function ReviewLaneEditor({
  lane,
  onRemove,
  onUpdate
}: {
  lane: ReviewLaneSetting;
  onRemove: () => void;
  onUpdate: (lane: ReviewLaneSetting) => void;
}) {
  return (
    <Accordion variant="outlined" disableGutters>
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
  onUpdate
}: {
  title: string;
  mappings: Record<string, LeadCategorySetting>;
  onUpdate: (mappings: Record<string, LeadCategorySetting>) => void;
}) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {Object.entries(mappings).map(([key, mapping]) => (
        <Accordion key={key} variant="outlined" disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ alignItems: "center", display: "flex", gap: 1, width: "100%" }}>
              <Typography sx={{ flex: 1, fontWeight: 700 }} noWrap>
                {mapping.label}
              </Typography>
              <Chip label={key} size="small" variant="outlined" />
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
                    [key]: { ...mapping, label: event.target.value }
                  })
                }
              />
              <TextField
                label="signal_types"
                value={stringListToText(mapping.signal_types)}
                onChange={(event) =>
                  onUpdate({
                    ...mappings,
                    [key]: { ...mapping, signal_types: textToStringList(event.target.value) }
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
                    [key]: { ...mapping, fact_types: textToStringList(event.target.value) }
                  })
                }
                multiline
                minRows={3}
              />
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
}

function RuleCollectionEditor({
  title,
  collection,
  rules,
  onAdd,
  onRemove,
  onUpdate
}: {
  title: string;
  collection: "signals" | "facts";
  rules: RuleSetting[];
  onAdd: (collection: "signals" | "facts") => void;
  onRemove: (collection: "signals" | "facts", index: number) => void;
  onUpdate: (collection: "signals" | "facts", index: number, rule: RuleSetting) => void;
}) {
  const groups = groupRulesByFolder(rules);

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
        <Accordion
          key={group.label}
          variant="outlined"
          disableGutters
          defaultExpanded={groups.length === 1 || groupIndex === 0}
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
                  rule={rule}
                  onRemove={() => onRemove(collection, index)}
                  onUpdate={(nextRule) => onUpdate(collection, index, nextRule)}
                />
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
}

function RuleEditor({
  collection,
  rule,
  onRemove,
  onUpdate
}: {
  collection: "signals" | "facts";
  rule: RuleSetting;
  onRemove: () => void;
  onUpdate: (rule: RuleSetting) => void;
}) {
  return (
    <Accordion variant="outlined" disableGutters>
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
  onUpdate
}: {
  match: RuleMatchSetting;
  onUpdate: (match: RuleMatchSetting) => void;
}) {
  return (
    <Stack spacing={1}>
      <RuleListHeader
        title="Зависимости сигнала"
        description="Сигнал может срабатывать от записей словарей и уже найденных фактов. Формат alias: catalog:key1, key2."
        addLabel="Добавить зависимость"
        onAdd={() => onUpdate({ ...match, aliases: [...match.aliases, { catalog: "vendors", keys: [] }] })}
      />
      <Box className="settings-two-column">
        <TextField
          label="match.aliases"
          helperText="Например: vendors:yandex, aqara"
          value={aliasMatchesToText(match.aliases)}
          onChange={(event) => onUpdate({ ...match, aliases: textToAliasMatches(event.target.value) })}
          multiline
          minRows={3}
          fullWidth
        />
        <TextField
          label="match.facts"
          helperText="Одна строка: fact_type или список через запятую"
          value={factMatchesToText(match.facts)}
          onChange={(event) => onUpdate({ ...match, facts: textToFactMatches(event.target.value) })}
          multiline
          minRows={3}
          fullWidth
        />
      </Box>
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

function aliasMatchesToText(items?: AliasMatchSetting[]) {
  return (items ?? []).map(aliasMatchToText).join("\n");
}

function aliasMatchToText(item: AliasMatchSetting) {
  const catalogs = [item.catalog ?? "", ...(item.catalogs ?? [])].filter(Boolean);
  const kindItems = (item.kinds ?? []).map((kind) => `kind=${kind}`);
  const left = [...catalogs, ...kindItems].join(",");
  const keys = item.keys ?? [];
  const right = keys.length > 0 ? keys.join(", ") : "*";
  return `${left || "*"}:${right}`;
}

function textToAliasMatches(value: string): AliasMatchSetting[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const separatorIndex = line.indexOf(":");
      const leftRaw = separatorIndex >= 0 ? line.slice(0, separatorIndex) : line;
      const rightRaw = separatorIndex >= 0 ? line.slice(separatorIndex + 1) : "";
      const leftItems = commaListToStrings(leftRaw).filter((item) => item !== "*");
      const kindItems = leftItems
        .filter((item) => item.startsWith("kind=") || item.startsWith("kind:"))
        .map((item) => item.slice(5));
      const catalogItems = leftItems.filter((item) => !item.startsWith("kind=") && !item.startsWith("kind:"));
      const keys = commaListToStrings(rightRaw).filter((item) => item !== "*");
      return {
        catalog: catalogItems[0] ?? null,
        catalogs: catalogItems.slice(1),
        keys,
        kinds: kindItems
      };
    });
}

function factMatchesToText(items?: FactMatchSetting[]) {
  return (items ?? []).map((item) => item.types.join(", ")).join("\n");
}

function textToFactMatches(value: string): FactMatchSetting[] {
  return value
    .split("\n")
    .map((line) => commaListToStrings(line))
    .filter((types) => types.length > 0)
    .map((types) => ({ types }));
}

function commaListToStrings(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
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

function Overview({ result }: { result: TextEnrichmentResult }) {
  return (
    <Stack spacing={2}>
      {result.lead_assessment && <LeadAssessmentPanel assessment={result.lead_assessment} />}
      <AnnotatedText result={result} />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {Object.entries(result.metrics).map(([key, value]) => (
          <Chip key={key} label={`${key}: ${value}`} variant="outlined" />
        ))}
      </Box>
    </Stack>
  );
}

function LeadAssessmentPanel({ assessment }: { assessment: LeadAssessment }) {
  return (
    <Paper variant="outlined" className="lead-assessment-panel">
      <Stack spacing={1.5}>
        <LeadAssessmentSummary assessment={assessment} />
        <ChipGroup title="Направления" items={assessment.solution_areas.map((item) => item.label)} />
        <ChipGroup title="Сегменты" items={assessment.customer_segments.map((item) => item.label)} />
        <ChipGroup title="Шум" items={assessment.noise_signals.map((item) => item.label)} color="warning" />
        {assessment.reasons.length > 0 && (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Причина</TableCell>
                  <TableCell>Вес</TableCell>
                  <TableCell>Совпадения</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {assessment.reasons.map((reason) => (
                  <TableRow key={`${reason.source}-${reason.key}`}>
                    <TableCell>{reason.label}</TableCell>
                    <TableCell>{reason.weight}</TableCell>
                    <TableCell>{reason.matched_texts.join(", ")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Stack>
    </Paper>
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
