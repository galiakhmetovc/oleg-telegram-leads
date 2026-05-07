import AddIcon from "@mui/icons-material/Add";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ErrorIcon from "@mui/icons-material/Error";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
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
  createTheme
} from "@mui/material";
import { FormEvent, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
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
  predicate: "caseless" | "normalized";
  value: string;
};

type RulePatternSetting = {
  source_text?: string | null;
  tokens: PatternTokenSetting[];
};

type SemanticPatternResponse = {
  source_text: string;
  lemma_text: string;
  tokens: PatternTokenSetting[];
};

type RuleSetting = {
  type: string;
  label: string;
  phrases: string[][];
  patterns: RulePatternSetting[];
  color?: string | null;
  confidence?: number | null;
};

type LeadCategorySetting = {
  label: string;
  signal_types: string[];
  fact_types: string[];
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
};

type NlpSettings = {
  pipeline: {
    stages: PipelineStageSetting[];
  };
  signals: RuleSetting[];
  facts: RuleSetting[];
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

type SettingsSection = "pipeline" | "signals" | "facts" | "lead_scoring" | "system";

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
          <Toolbar variant="dense">
            <AutoAwesomeIcon color="primary" fontSize="small" />
            <Typography variant="subtitle1" component="h1" sx={{ ml: 1, fontWeight: 700 }}>
              PUR Leads v2 - обогащение текста
            </Typography>
            <Tabs value={activePage} onChange={handlePageChange} className="main-nav">
              <Tab label="Обогащение" />
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
          ) : activePage === 1 ? (
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
      color: collection === "signals" ? "#0b57d0" : null,
      confidence: 0.5,
      phrases: [["пример"]],
      patterns: []
    };
    updateDraft({ ...draft, [collection]: [...draft[collection], rule] });
  }

  function removeRule(collection: "signals" | "facts", index: number) {
    if (!draft) {
      return;
    }
    updateDraft({ ...draft, [collection]: draft[collection].filter((_, itemIndex) => itemIndex !== index) });
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
          <Stack direction="row" spacing={1}>
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
              Правила поиска делятся на точные фразы и лемматические фразы. Это разные инструменты:
              первый ищет устойчивую запись, второй ищет смысловую словоформу.
            </Typography>
          </Box>

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

function LeadScoringSettingsEditor({
  settings,
  onUpdate
}: {
  settings: LeadScoringSettings;
  onUpdate: (settings: LeadScoringSettings) => void;
}) {
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
    </Stack>
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
  return (
    <Stack spacing={1.5}>
      <Box sx={{ alignItems: "center", display: "flex", justifyContent: "space-between" }}>
        <Typography variant="h6">{title}</Typography>
        <Button startIcon={<AddIcon />} variant="outlined" onClick={() => onAdd(collection)}>
          Добавить
        </Button>
      </Box>
      {rules.map((rule, index) => (
        <RuleEditor
          key={`${rule.type}-${index}`}
          rule={rule}
          onRemove={() => onRemove(collection, index)}
          onUpdate={(nextRule) => onUpdate(collection, index, nextRule)}
        />
      ))}
    </Stack>
  );
}

function RuleEditor({
  rule,
  onRemove,
  onUpdate
}: {
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
          <Chip label={rule.type} size="small" variant="outlined" />
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <Box className="rule-grid">
            <TextField label="type" value={rule.type} onChange={(event) => onUpdate({ ...rule, type: event.target.value })} />
            <TextField label="label" value={rule.label} onChange={(event) => onUpdate({ ...rule, label: event.target.value })} />
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
        description="Совпадение по такой же последовательности слов без учета регистра. Используй для устойчивых выражений, аббревиатур, брендов и технических обозначений."
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

function stringListToText(items: string[]) {
  return items.join("\n");
}

function textToStringList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
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
