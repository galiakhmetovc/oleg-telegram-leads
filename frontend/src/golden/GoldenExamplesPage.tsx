import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import StarIcon from "@mui/icons-material/Star";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import { type FormEvent, type SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";

import { TestingWorkspace } from "../enrichment/TestingWorkspace";
import type { EnrichmentEvent, EnrichmentJob, TextEnrichmentResult } from "../enrichment/types";
import type { SettingsSection } from "../settings/navigation";

type GoldenVerdict = "lead" | "not_lead" | "uncertain" | "noise";

type GoldenExample = {
  id: string;
  title: string;
  text: string;
  expected_verdict?: GoldenVerdict | null;
  comment: string;
  source_message_id?: string | null;
  source_chat_title?: string | null;
  telegram_message_id?: number | null;
  telegram_message_url?: string | null;
  last_enrichment_job_id?: string | null;
  created_at: string;
  updated_at: string;
};

type GoldenExamplePage = {
  total: number;
  limit: number;
  offset: number;
  items: GoldenExample[];
};

const verdictOptions: Array<{ value: GoldenVerdict; label: string }> = [
  { value: "lead", label: "Лид" },
  { value: "not_lead", label: "Не лид" },
  { value: "uncertain", label: "Сомнительно" },
  { value: "noise", label: "Шум" }
];

export function GoldenExamplesPage({
  apiBaseUrl,
  isNarrowScreen,
  onOpenSettings
}: {
  apiBaseUrl: string;
  isNarrowScreen: boolean;
  onOpenSettings: (section: SettingsSection) => void;
}) {
  const [examples, setExamples] = useState<GoldenExample[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newText, setNewText] = useState("");
  const [newVerdict, setNewVerdict] = useState<GoldenVerdict | "">("lead");
  const [newComment, setNewComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [job, setJob] = useState<EnrichmentJob | null>(null);
  const [events, setEvents] = useState<EnrichmentEvent[]>([]);
  const [activeTab, setActiveTab] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  const selectedExample = useMemo(
    () => examples.find((example) => example.id === selectedId) ?? examples[0] ?? null,
    [examples, selectedId]
  );
  const result: TextEnrichmentResult | null = job?.result ?? null;
  const isProcessing = running || job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    let active = true;
    async function loadExamples() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/golden-examples`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const payload = (await response.json()) as GoldenExamplePage;
        if (!active) {
          return;
        }
        const items = Array.isArray(payload.items) ? payload.items : [];
        setExamples(items);
        setTotal(payload.total ?? items.length);
        setSelectedId((current) => (current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null));
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Не удалось загрузить golden-примеры");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadExamples();
    return () => {
      active = false;
      eventSourceRef.current?.close();
    };
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!selectedExample) {
      setInputText("");
      return;
    }
    setInputText(selectedExample.text);
  }, [selectedExample?.id, selectedExample?.text]);

  async function reloadExamples() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/golden-examples`);
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as GoldenExamplePage;
      const items = Array.isArray(payload.items) ? payload.items : [];
      setExamples(items);
      setTotal(payload.total ?? items.length);
      setSelectedId((current) => (current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось обновить golden-примеры");
    } finally {
      setLoading(false);
    }
  }

  async function createExample(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newText.trim()) {
      setError("Введите текст golden-примера");
      return;
    }
    setCreating(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/golden-examples`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTitle.trim() || null,
          text: newText,
          expected_verdict: newVerdict || null,
          comment: newComment
        })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const example = (await response.json()) as GoldenExample;
      setExamples((current) => [example, ...current.filter((item) => item.id !== example.id)]);
      setTotal((current) => current + 1);
      setSelectedId(example.id);
      setNewTitle("");
      setNewText("");
      setNewComment("");
      setNewVerdict("lead");
      setMessage("Golden-пример создан");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось создать golden-пример");
    } finally {
      setCreating(false);
    }
  }

  async function runSelectedExample(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!selectedExample) {
      setError("Выберите golden-пример");
      return;
    }
    eventSourceRef.current?.close();
    setRunning(true);
    setError(null);
    setMessage(null);
    setEvents([]);
    setJob(null);
    setActiveTab(0);
    setInputText(selectedExample.text);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/golden-examples/${selectedExample.id}/run`, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const payload = (await response.json()) as { example: GoldenExample; job: EnrichmentJob };
      setExamples((current) =>
        current.map((item) => (item.id === payload.example.id ? payload.example : item))
      );
      setSelectedId(payload.example.id);
      setJob(payload.job);
      connectToEvents(payload.job.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось запустить golden-пример");
    } finally {
      setRunning(false);
    }
  }

  function connectToEvents(jobId: string) {
    const source = new EventSource(`${apiBaseUrl}/api/v1/enrichments/${jobId}/events`);
    eventSourceRef.current = source;

    const handleEvent = (messageEvent: MessageEvent<string>) => {
      const parsed = JSON.parse(messageEvent.data) as EnrichmentEvent;
      setEvents((current) => [parsed, ...current].slice(0, 20));
      setJob((current) => {
        if (current === null) {
          return current;
        }
        return {
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
      });

      if (parsed.event_type === "job_completed" || parsed.event_type === "job_failed") {
        source.close();
        void refreshSnapshot(jobId);
      }
    };

    for (const eventName of ["job_queued", "job_started", "stage_completed", "job_completed", "job_failed"]) {
      source.addEventListener(eventName, handleEvent);
    }

    source.onerror = () => {
      setError("SSE-соединение golden-прогона прервано");
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
    <Box className="golden-shell">
      <Stack spacing={2}>
        <Paper variant="outlined" className="analytics-header">
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
            <Box>
              <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
                Golden-примеры
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Эталонные сообщения для проверки качества правил и регрессий.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Chip label={`${total} примеров`} variant="outlined" />
              <Button
                variant="outlined"
                startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <RefreshIcon />}
                disabled={loading}
                onClick={() => void reloadExamples()}
              >
                Обновить
              </Button>
            </Stack>
          </Stack>
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          {message && <Alert severity="success" sx={{ mt: 2 }}>{message}</Alert>}
        </Paper>

        <Box className="golden-layout">
          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.25}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Набор golden
                </Typography>
                {loading && examples.length === 0 ? (
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <CircularProgress size={18} />
                    <Typography variant="body2" color="text.secondary">
                      Загружаю примеры
                    </Typography>
                  </Stack>
                ) : examples.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    Golden-примеров пока нет. Добавьте вручную или из карточки аналитики.
                  </Typography>
                ) : (
                  <List dense disablePadding className="golden-list">
                    {examples.map((example) => (
                      <ListItemButton
                        key={example.id}
                        selected={example.id === selectedExample?.id}
                        onClick={() => setSelectedId(example.id)}
                      >
                        <ListItemText
                          slotProps={{ secondary: { component: "div" } }}
                          primary={example.title}
                          secondary={
                            <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", mt: 0.5 }}>
                              {example.expected_verdict && <Chip size="small" label={verdictLabel(example.expected_verdict)} />}
                              {example.source_chat_title && <Chip size="small" variant="outlined" label={example.source_chat_title} />}
                            </Stack>
                          }
                        />
                      </ListItemButton>
                    ))}
                  </List>
                )}
              </Stack>
            </Paper>

            <Paper component="form" onSubmit={createExample} variant="outlined" className="analytics-section">
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Создать вручную
                </Typography>
                <TextField
                  label="Название"
                  size="small"
                  value={newTitle}
                  onChange={(event) => setNewTitle(event.target.value)}
                />
                <TextField
                  label="Текст"
                  value={newText}
                  onChange={(event) => setNewText(event.target.value)}
                  multiline
                  minRows={4}
                />
                <TextField
                  select
                  size="small"
                  label="Ожидаемый вердикт"
                  value={newVerdict}
                  onChange={(event) => setNewVerdict(event.target.value as GoldenVerdict | "")}
                >
                  <MenuItem value="">Не указан</MenuItem>
                  {verdictOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Комментарий"
                  value={newComment}
                  onChange={(event) => setNewComment(event.target.value)}
                  multiline
                  minRows={2}
                />
                <Button
                  type="submit"
                  variant="contained"
                  startIcon={creating ? <CircularProgress size={18} color="inherit" /> : <AddIcon />}
                  disabled={creating}
                >
                  Добавить
                </Button>
              </Stack>
            </Paper>
          </Stack>

          <Stack spacing={2} className="golden-run-panel" sx={{ minWidth: 0 }}>
            {selectedExample && (
              <Paper variant="outlined" className="analytics-section">
                <Stack spacing={1}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }} noWrap>
                        Выбрано: {selectedExample.title}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {selectedExample.comment || "Комментарий не указан"}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                      {selectedExample.telegram_message_url && (
                        <Button size="small" href={selectedExample.telegram_message_url} target="_blank" rel="noreferrer">
                          Telegram
                        </Button>
                      )}
                      <Chip
                        icon={<StarIcon fontSize="small" />}
                        label={selectedExample.expected_verdict ? verdictLabel(selectedExample.expected_verdict) : "Вердикт не указан"}
                        variant="outlined"
                      />
                    </Stack>
                  </Stack>
                  <Divider />
                  <Typography variant="caption" color="text.secondary">
                    Последний job: {selectedExample.last_enrichment_job_id ?? "еще не запускался"}
                  </Typography>
                </Stack>
              </Paper>
            )}
            <TestingWorkspace
              inputText={inputText}
              onInputTextChange={setInputText}
              onSubmit={runSelectedExample}
              isNarrowScreen={isNarrowScreen}
              isProcessing={isProcessing}
              isSubmitting={running}
              error={error}
              job={job}
              events={events}
              result={result}
              activeTab={activeTab}
              onTabChange={handleTabChange}
              onOpenSettings={onOpenSettings}
              submitLabel="Запустить golden"
            />
          </Stack>
        </Box>
      </Stack>
    </Box>
  );
}

function verdictLabel(verdict: GoldenVerdict): string {
  return verdictOptions.find((option) => option.value === verdict)?.label ?? verdict;
}
