import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ConstructionIcon from "@mui/icons-material/Construction";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import TuneIcon from "@mui/icons-material/Tune";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  FormGroup,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";

import type { SpanItem, TextEnrichmentResult } from "../enrichment/types";
import type { AliasCatalogName } from "../settings/navigation";
import type { AliasSetting, NlpSettings, RulePatternSetting, RuleSetting, SettingsSnapshot } from "../settings/types";
import {
  applyAliasDraft,
  applyFactDraft,
  applyNoiseDraft,
  applySignalDraft,
  constructorKeyFromText,
  defaultAliasTypeForCatalog,
  exactPhraseTokens,
  factDependencyTypes,
  type ConstructorPhraseKind
} from "./draftMutations";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const aliasCatalogs: AliasCatalogName[] = ["vendors", "protocols", "devices", "software"];

type TextSelectionState = {
  text: string;
  start: number;
  end: number;
};

type SelectionEditorState =
  | {
      kind: "alias";
      text: string;
      catalog: AliasCatalogName;
      key: string;
      canonical: string;
      alias_type: AliasSetting["type"];
      fact_types: string;
      confidence: string;
      color: string;
    }
  | {
      kind: "fact";
      text: string;
      target_type: string;
      target_label: string;
      group: string;
      phrase_kind: ConstructorPhraseKind;
      confidence: string;
      color: string;
    };

type SignalEditorState = {
  selected_signal_type: string;
  type: string;
  label: string;
  group: string;
  confidence: string;
  color: string;
  score_weight: string;
  fact_types: string[];
};

type SelectionOwner =
  | {
      kind: "alias";
      label: string;
      catalog: AliasCatalogName;
      alias: AliasSetting;
    }
  | {
      kind: "fact";
      label: string;
      rule: RuleSetting;
    };

type PreviewFactChoice = {
  type: string;
  label: string;
  matchedTexts: string[];
};

export function ConfiguratorPage({
  settings,
  loading,
  loadError,
  loadSettings,
  onSettingsSnapshotChange
}: {
  settings: SettingsSnapshot | null;
  loading: boolean;
  loadError: string | null;
  loadSettings: (options?: { force?: boolean; commit?: boolean }) => Promise<SettingsSnapshot>;
  onSettingsSnapshotChange: (settings: SettingsSnapshot) => void;
}) {
  const [draft, setDraft] = useState<NlpSettings | null>(settings?.nlp ?? null);
  const [dirty, setDirty] = useState(false);
  const [savingRevision, setSavingRevision] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [selection, setSelection] = useState<TextSelectionState | null>(null);
  const [selectionEditor, setSelectionEditor] = useState<SelectionEditorState | null>(null);
  const [selectionSaving, setSelectionSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewResult, setPreviewResult] = useState<TextEnrichmentResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [signalEditor, setSignalEditor] = useState<SignalEditorState>(() => createSignalEditor());
  const messageInputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (settings?.nlp) {
      setDraft(settings.nlp);
      setDirty(false);
    }
  }, [settings?.nlp]);

  useEffect(() => {
    if (!settings && !loading) {
      void loadSettings().catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Не удалось загрузить настройки");
      });
    }
  }, [loadSettings, loading, settings]);

  const activeRevision = draft?.source?.revision ?? settings?.nlp.source?.revision ?? null;
  const previewFacts = previewResult?.facts ?? [];
  const previewSignals = previewResult?.domain_signals ?? [];
  const previewEntities = previewResult?.entities ?? [];
  const previewFactChoices = useMemo(() => buildPreviewFactChoices(previewFacts), [previewFacts]);
  const availableSignalFactChoices = useMemo(
    () => mergeSignalFactChoices(previewFactChoices, signalEditor.fact_types),
    [previewFactChoices, signalEditor.fact_types]
  );
  const selectionOwner = useMemo(
    () => (selection && draft ? findSelectionOwner(draft, selection.text) : null),
    [draft, selection]
  );

  if (!draft) {
    return (
      <Stack className="constructor-page constructor-empty" spacing={2}>
        <Paper variant="outlined" className="constructor-panel">
          <Stack spacing={2}>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
              <CircularProgress size={20} />
              <Typography variant="h6">Загружаю конфигурацию</Typography>
            </Stack>
            {loadError && <Alert severity="error">{loadError}</Alert>}
          </Stack>
        </Paper>
      </Stack>
    );
  }

  const activeDraft = draft;

  async function runPreview(targetDraft?: NlpSettings) {
    const draftForPreview = targetDraft ?? activeDraft;
    const text = inputText.trim();
    if (!text) {
      setPreviewError("Вставь сообщение для разбора");
      return;
    }
    setPreviewing(true);
    setPreviewError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, nlp: draftForPreview })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      setPreviewResult((await response.json()) as TextEnrichmentResult);
    } catch (caught) {
      setPreviewError(caught instanceof Error ? caught.message : "Не удалось выполнить preview");
    } finally {
      setPreviewing(false);
    }
  }

  async function applyDraftChange(
    updater: (current: NlpSettings) => NlpSettings,
    successMessage: string,
    options?: { closeSelectionEditor?: boolean }
  ) {
    let nextDraft: NlpSettings;
    try {
      nextDraft = updater(activeDraft);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось обновить draft");
      return;
    }
    setDraft(nextDraft);
    setDirty(true);
    setMessage(successMessage);
    setError(null);
    if (options?.closeSelectionEditor !== false) {
      setSelectionEditor(null);
    }
    if (inputText.trim()) {
      await runPreview(nextDraft);
    }
  }

  async function saveDraft() {
    if (!draft) {
      return;
    }
    setSavingRevision(true);
    setError(null);
    setMessage(null);
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
      const snapshot = settings ?? (await loadSettings({ force: true }));
      onSettingsSnapshotChange({ ...snapshot, nlp: saved });
      setDraft(saved);
      setDirty(false);
      setMessage(
        saved.source?.revision
          ? `Сохранено как NLP-ревизия #${saved.source.revision}`
          : "NLP-настройки сохранены"
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить настройки");
    } finally {
      setSavingRevision(false);
    }
  }

  function handleMessageSelection() {
    const textarea = messageInputRef.current;
    if (!textarea) {
      return;
    }
    const start = textarea.selectionStart ?? 0;
    const end = textarea.selectionEnd ?? 0;
    if (start === end) {
      setSelection(null);
      return;
    }
    const rawText = inputText.slice(start, end);
    const text = rawText.trim();
    if (!text) {
      setSelection(null);
      return;
    }
    setSelection({ text, start, end });
  }

  function openAliasEditor(owner?: SelectionOwner | null) {
    if (!selection) {
      return;
    }
    if (owner?.kind === "alias") {
      setSelectionEditor(selectionEditorFromAlias(owner.catalog, owner.alias, selection.text));
      return;
    }
    setSelectionEditor(createAliasEditor(selection.text));
  }

  function openFactEditor(owner?: SelectionOwner | null) {
    if (!selection) {
      return;
    }
    if (owner?.kind === "fact") {
      setSelectionEditor(selectionEditorFromFact(owner.rule, selection.text));
      return;
    }
    setSelectionEditor(createFactEditor(selection.text));
  }

  async function saveSelectionEditor() {
    if (!selectionEditor || selectionSaving) {
      return;
    }
    setSelectionSaving(true);
    setError(null);
    try {
      if (selectionEditor.kind === "alias") {
        await applyDraftChange(
          (current) =>
            applyAliasDraft(current, {
              text: selectionEditor.text,
              catalog: selectionEditor.catalog,
              key: selectionEditor.key,
              canonical: selectionEditor.canonical,
              alias_type: selectionEditor.alias_type,
              fact_types: stringListFromMultiline(selectionEditor.fact_types),
              confidence: parseNumberOrNull(selectionEditor.confidence),
              color: selectionEditor.color.trim() || null
            }),
          `Словарь обновлен: ${selectionEditor.canonical || selectionEditor.key}`
        );
        return;
      }

      let semanticPattern: RulePatternSetting | null = null;
      if (selectionEditor.phrase_kind === "semantic") {
        const response = await fetch(`${apiBaseUrl}/api/v1/settings/nlp/semantic-pattern`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: selectionEditor.text })
        });
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const payload = (await response.json()) as {
          source_text: string;
          tokens: RulePatternSetting["tokens"];
        };
        semanticPattern = { source_text: payload.source_text, tokens: payload.tokens };
      }

      await applyDraftChange(
        (current) =>
          applyFactDraft(current, {
            text: selectionEditor.text,
            target_type: selectionEditor.target_type,
            target_label: selectionEditor.target_label,
            group: selectionEditor.group,
            phrase_kind: selectionEditor.phrase_kind,
            confidence: parseNumberOrNull(selectionEditor.confidence),
            color: selectionEditor.color.trim() || null,
            semantic_pattern: semanticPattern
          }),
        `Факт обновлен: ${selectionEditor.target_label || selectionEditor.target_type}`
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось обновить draft");
    } finally {
      setSelectionSaving(false);
    }
  }

  async function saveNoiseSelection() {
    if (!selection || selectionSaving) {
      return;
    }
    setSelectionSaving(true);
    setError(null);
    try {
      await applyDraftChange(
        (current) => applyNoiseDraft(current, selection.text),
        "Шумовой факт обновлен"
      );
    } finally {
      setSelectionSaving(false);
    }
  }

  async function saveSignalEditor() {
    if (selectionSaving) {
      return;
    }
    setSelectionSaving(true);
    setError(null);
    try {
      await applyDraftChange(
        (current) =>
          applySignalDraft(current, {
            type: signalEditor.type,
            label: signalEditor.label,
            group: signalEditor.group,
            fact_types: signalEditor.fact_types,
            confidence: parseNumberOrNull(signalEditor.confidence),
            color: signalEditor.color.trim() || null,
            score_weight: parseNumber(signalEditor.score_weight, 0)
          }),
        `Сигнал обновлен: ${signalEditor.label || signalEditor.type}`,
        { closeSelectionEditor: false }
      );
    } finally {
      setSelectionSaving(false);
    }
  }

  function handleSignalTemplateChange(nextType: string) {
    if (!nextType) {
      setSignalEditor(createSignalEditor({ fact_types: signalEditor.fact_types }));
      return;
    }
    const existing = activeDraft.signals.find((signal) => signal.type === nextType);
    if (!existing) {
      return;
    }
    setSignalEditor(signalEditorFromRule(existing, activeDraft.lead_scoring.signal_weights[existing.type] ?? 0));
  }

  return (
    <Box className="constructor-page">
      <Paper variant="outlined" className="constructor-panel constructor-header">
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between" }}>
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <ConstructionIcon color="primary" fontSize="small" />
              <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
                Конструктор
              </Typography>
              <Chip size="small" variant="outlined" label="Работа через draft-ревизию" />
              {activeRevision !== null && (
                <Chip size="small" color="primary" variant="outlined" label={`NLP-ревизия #${activeRevision}`} />
              )}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Вставь сообщение, выдели фрагмент, назначь ему owner и пересчитай preview на том же draft.
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} className="constructor-actions" sx={{ alignItems: "center" }}>
            {dirty && <Chip size="small" color="warning" label="Есть несохраненные изменения" />}
            <Button
              variant="contained"
              startIcon={savingRevision ? <CircularProgress color="inherit" size={18} /> : <SaveIcon />}
              disabled={!dirty || savingRevision}
              onClick={() => void saveDraft()}
            >
              Сохранить ревизию
            </Button>
          </Stack>
        </Stack>
        {loading && <CircularProgress size={18} sx={{ mt: 2 }} />}
        {message && (
          <Alert severity="success" icon={<CheckCircleIcon fontSize="inherit" />} sx={{ mt: 2 }}>
            {message}
          </Alert>
        )}
        {(error || loadError) && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error ?? loadError}
          </Alert>
        )}
      </Paper>

      <Box className="constructor-shell">
        <Stack spacing={2} className="constructor-main">
          <Paper variant="outlined" className="constructor-panel">
            <Stack spacing={2}>
              <SectionTitle eyebrow="MESSAGE" title="Сообщение" />
              <TextField
                label="Сообщение для разбора"
                value={inputText}
                inputRef={messageInputRef}
                multiline
                minRows={8}
                onChange={(event) => {
                  setInputText(event.target.value);
                  setSelection(null);
                  setPreviewError(null);
                }}
                onSelect={handleMessageSelection}
              />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <Button
                  variant="contained"
                  startIcon={previewing ? <CircularProgress color="inherit" size={18} /> : <PlayArrowIcon />}
                  disabled={previewing || !inputText.trim()}
                  onClick={() => void runPreview()}
                >
                  Разобрать
                </Button>
                <Button
                  variant="outlined"
                  color="inherit"
                  disabled={!inputText}
                  onClick={() => {
                    setInputText("");
                    setSelection(null);
                    setPreviewResult(null);
                    setPreviewError(null);
                  }}
                >
                  Очистить
                </Button>
              </Stack>

              <Divider />

              <Stack spacing={1.5}>
                <SectionTitle eyebrow="SELECTION" title="Работа с выделением" />
                <Typography variant="body2" color="text.secondary">
                  Выдели фрагмент прямо в тексте. Сигнал сюда не пишется: отсюда можно создать только alias, fact или шум.
                </Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <Button
                    variant="outlined"
                    color="inherit"
                    disabled={!selection}
                    onClick={() => openAliasEditor(selectionOwner)}
                  >
                    В словарь
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    disabled={!selection}
                    onClick={() => openFactEditor(selectionOwner)}
                  >
                    В факт
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    disabled={!selection || selectionSaving}
                    onClick={() => void saveNoiseSelection()}
                  >
                    В шум
                  </Button>
                </Stack>
                {selection ? (
                  <Box className="constructor-selection-bar">
                    <Stack spacing={1}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        «{selection.text}»
                      </Typography>
                      <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                        <Chip size="small" variant="outlined" label={`range ${selection.start}-${selection.end}`} />
                        {selectionOwner && <Chip size="small" color="info" label={selectionOwner.label} />}
                      </Stack>
                    </Stack>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "flex-end" }}>
                      {selectionOwner && (
                        <Button
                          variant="outlined"
                          color="inherit"
                          onClick={() =>
                            selectionOwner.kind === "alias"
                              ? openAliasEditor(selectionOwner)
                              : openFactEditor(selectionOwner)
                          }
                        >
                          Открыть owner
                        </Button>
                      )}
                    </Stack>
                  </Box>
                ) : (
                  <EmptyHint>Пока нет выделения. Начни с текста сообщения.</EmptyHint>
                )}
              </Stack>
            </Stack>
          </Paper>

          <Paper variant="outlined" className="constructor-panel">
            <Stack spacing={2}>
              <SectionTitle eyebrow="PREVIEW" title="Текущий preview" />
              {previewError && <Alert severity="error">{previewError}</Alert>}
              {previewResult === null ? (
                <EmptyHint>Сначала запусти preview по сообщению и текущему draft.</EmptyHint>
              ) : (
                <>
                  <PreviewAssessment result={previewResult} />
                  {isPreviewEmpty(previewResult) && (
                    <Alert severity="info">
                      Ничего не найдено. Добавь факт, alias или сигнал в draft и повтори preview.
                    </Alert>
                  )}
                  <EvidenceSection title="Словарные совпадения" items={previewEntities} empty="Словарь пока ничего не нашел." />
                  <EvidenceSection title="Найденные facts" items={previewFacts} empty="Facts пока нет." />
                  <EvidenceSection title="Сработавшие сигналы" items={previewSignals} empty="Сигналы пока не сработали." />
                </>
              )}
            </Stack>
          </Paper>
        </Stack>

        <Stack spacing={2} className="constructor-rail">
          <Paper variant="outlined" className="constructor-panel constructor-sticky-panel">
            <Stack spacing={2}>
              <SectionTitle eyebrow="OWNER" title="Конструктор выделения" />
              {selectionEditor === null ? (
                <EmptyHint>Выбери действие для выделенного текста: словарь, факт или шум.</EmptyHint>
              ) : selectionEditor.kind === "alias" ? (
                <>
                  <Alert severity="info">Alias нужен для брендов, протоколов, устройств, моделей и ПО.</Alert>
                  <TextField
                    label="Каталог"
                    select
                    value={selectionEditor.catalog}
                    onChange={(event) => {
                      const catalog = event.target.value as AliasCatalogName;
                      setSelectionEditor((current) =>
                        current && current.kind === "alias"
                          ? {
                              ...current,
                              catalog,
                              alias_type: defaultAliasTypeForCatalog(catalog)
                            }
                          : current
                      );
                    }}
                  >
                    {aliasCatalogs.map((catalog) => (
                      <MenuItem key={catalog} value={catalog}>
                        {catalogLabel(catalog)}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Существующая запись"
                    select
                    value=""
                    onChange={(event) => {
                      const selected = draft[selectionEditor.catalog].find((alias) => alias.key === event.target.value);
                      if (!selected) {
                        return;
                      }
                      setSelectionEditor(selectionEditorFromAlias(selectionEditor.catalog, selected, selectionEditor.text));
                    }}
                  >
                    <MenuItem value="">Новая или ручной ввод</MenuItem>
                    {draft[selectionEditor.catalog].map((alias) => (
                      <MenuItem key={alias.key} value={alias.key}>
                        {alias.key} — {alias.canonical}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="key"
                    value={selectionEditor.key}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "alias" ? { ...current, key: event.target.value } : current
                      )
                    }
                  />
                  <TextField
                    label="canonical"
                    value={selectionEditor.canonical}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "alias" ? { ...current, canonical: event.target.value } : current
                      )
                    }
                  />
                  <TextField
                    label="alias_type"
                    select
                    value={selectionEditor.alias_type}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "alias"
                          ? { ...current, alias_type: event.target.value as AliasSetting["type"] }
                          : current
                      )
                    }
                  >
                    {["vendor", "protocol", "device", "software", "model"].map((value) => (
                      <MenuItem key={value} value={value}>
                        {value}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="fact_types"
                    helperText="По одному fact_type на строку."
                    multiline
                    minRows={3}
                    value={selectionEditor.fact_types}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "alias" ? { ...current, fact_types: event.target.value } : current
                      )
                    }
                  />
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField
                      label="confidence"
                      type="number"
                      value={selectionEditor.confidence}
                      slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
                      onChange={(event) =>
                        setSelectionEditor((current) =>
                          current && current.kind === "alias" ? { ...current, confidence: event.target.value } : current
                        )
                      }
                    />
                    <TextField
                      label="color"
                      value={selectionEditor.color}
                      onChange={(event) =>
                        setSelectionEditor((current) =>
                          current && current.kind === "alias" ? { ...current, color: event.target.value } : current
                        )
                      }
                    />
                  </Stack>
                </>
              ) : (
                <>
                  <Alert severity="info">Fact нужен для намерения, контекста, домена, объекта и шума.</Alert>
                  <TextField
                    label="Существующее правило"
                    select
                    value=""
                    onChange={(event) => {
                      const selected = draft.facts.find((rule) => rule.type === event.target.value);
                      if (!selected) {
                        return;
                      }
                      setSelectionEditor(selectionEditorFromFact(selected, selectionEditor.text));
                    }}
                  >
                    <MenuItem value="">Новое или ручной ввод</MenuItem>
                    {draft.facts.map((rule) => (
                      <MenuItem key={rule.type} value={rule.type}>
                        {rule.type} — {rule.label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="type"
                    value={selectionEditor.target_type}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "fact" ? { ...current, target_type: event.target.value } : current
                      )
                    }
                  />
                  <TextField
                    label="label"
                    value={selectionEditor.target_label}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "fact" ? { ...current, target_label: event.target.value } : current
                      )
                    }
                  />
                  <TextField
                    label="Папка"
                    value={selectionEditor.group}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "fact" ? { ...current, group: event.target.value } : current
                      )
                    }
                  />
                  <TextField
                    label="Тип совпадения"
                    select
                    value={selectionEditor.phrase_kind}
                    onChange={(event) =>
                      setSelectionEditor((current) =>
                        current && current.kind === "fact"
                          ? { ...current, phrase_kind: event.target.value as ConstructorPhraseKind }
                          : current
                      )
                    }
                  >
                    <MenuItem value="exact">Точная фраза</MenuItem>
                    <MenuItem value="semantic">Лемматическая фраза</MenuItem>
                  </TextField>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField
                      label="confidence"
                      type="number"
                      value={selectionEditor.confidence}
                      slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
                      onChange={(event) =>
                        setSelectionEditor((current) =>
                          current && current.kind === "fact" ? { ...current, confidence: event.target.value } : current
                        )
                      }
                    />
                    <TextField
                      label="color"
                      value={selectionEditor.color}
                      onChange={(event) =>
                        setSelectionEditor((current) =>
                          current && current.kind === "fact" ? { ...current, color: event.target.value } : current
                        )
                      }
                    />
                  </Stack>
                </>
              )}
              {selectionEditor && (
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <Button
                    variant="contained"
                    startIcon={selectionSaving ? <CircularProgress color="inherit" size={18} /> : <AutoFixHighIcon />}
                    disabled={selectionSaving}
                    onClick={() => void saveSelectionEditor()}
                  >
                    Сохранить в draft
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    disabled={selectionSaving}
                    onClick={() => setSelectionEditor(null)}
                  >
                    Отмена
                  </Button>
                </Stack>
              )}
            </Stack>
          </Paper>

          <Paper variant="outlined" className="constructor-panel constructor-sticky-panel">
            <Stack spacing={2}>
              <SectionTitle eyebrow="SIGNALS" title="Конструктор сигналов" />
              <Typography variant="body2" color="text.secondary">
                Сигналы строятся только из найденных facts.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Сигнал срабатывает по любому из отмеченных facts.
              </Typography>
              <TextField
                label="Существующий сигнал"
                select
                value={signalEditor.selected_signal_type}
                onChange={(event) => handleSignalTemplateChange(event.target.value)}
              >
                <MenuItem value="">Новый сигнал / ручной ввод</MenuItem>
                {draft.signals.map((signal) => (
                  <MenuItem key={signal.type} value={signal.type}>
                    {signal.type} — {signal.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Тип сигнала"
                value={signalEditor.type}
                onChange={(event) => setSignalEditor((current) => ({ ...current, selected_signal_type: "", type: event.target.value }))}
              />
              <TextField
                label="Название сигнала"
                value={signalEditor.label}
                onChange={(event) => setSignalEditor((current) => ({ ...current, label: event.target.value }))}
              />
              <TextField
                label="Папка сигнала"
                value={signalEditor.group}
                onChange={(event) => setSignalEditor((current) => ({ ...current, group: event.target.value }))}
              />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <TextField
                  label="Confidence сигнала"
                  type="number"
                  value={signalEditor.confidence}
                  slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
                  onChange={(event) => setSignalEditor((current) => ({ ...current, confidence: event.target.value }))}
                />
                <TextField
                  label="Вес в score"
                  type="number"
                  value={signalEditor.score_weight}
                  onChange={(event) => setSignalEditor((current) => ({ ...current, score_weight: event.target.value }))}
                />
              </Stack>
              <TextField
                label="Цвет сигнала"
                value={signalEditor.color}
                onChange={(event) => setSignalEditor((current) => ({ ...current, color: event.target.value }))}
              />
              <Box className="constructor-section">
                <Stack spacing={1}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                    Facts для сигнала
                  </Typography>
                  {availableSignalFactChoices.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      Сначала нужен preview с фактами.
                    </Typography>
                  ) : (
                    <FormGroup>
                      {availableSignalFactChoices.map((fact) => {
                        const checked = signalEditor.fact_types.includes(fact.type);
                        return (
                          <FormControlLabel
                            key={fact.type}
                            control={
                              <Checkbox
                                checked={checked}
                                onChange={(event) =>
                                  setSignalEditor((current) => ({
                                    ...current,
                                    fact_types: event.target.checked
                                      ? [...current.fact_types, fact.type]
                                      : current.fact_types.filter((item) => item !== fact.type)
                                  }))
                                }
                              />
                            }
                            label={`${fact.label} (${fact.type})`}
                          />
                        );
                      })}
                    </FormGroup>
                  )}
                </Stack>
              </Box>
              <Button
                variant="contained"
                startIcon={selectionSaving ? <CircularProgress color="inherit" size={18} /> : <TuneIcon />}
                disabled={selectionSaving || availableSignalFactChoices.length === 0}
                onClick={() => void saveSignalEditor()}
              >
                Сохранить сигнал в draft
              </Button>
            </Stack>
          </Paper>
        </Stack>
      </Box>
    </Box>
  );
}

function SectionTitle({
  eyebrow,
  title
}: {
  eyebrow: string;
  title: string;
}) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        {eyebrow}
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
    </Box>
  );
}

function PreviewAssessment({ result }: { result: TextEnrichmentResult }) {
  const assessment = result.lead_assessment ?? null;
  if (!assessment) {
    return null;
  }
  return (
    <Box className="constructor-summary">
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Chip
          size="small"
          color={assessment.is_lead ? "success" : "default"}
          label={assessment.is_lead ? "lead" : "not lead"}
        />
        <Typography variant="h5" sx={{ fontWeight: 800 }}>
          {assessment.score}
        </Typography>
        <Chip size="small" variant="outlined" label={assessment.temperature} />
      </Stack>
      {assessment.reasons.length > 0 && (
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", mt: 1.5 }}>
          {assessment.reasons.slice(0, 6).map((reason) => (
            <Chip key={`${reason.source}:${reason.key}`} size="small" label={`+${reason.weight} ${reason.label}`} />
          ))}
        </Stack>
      )}
    </Box>
  );
}

function EvidenceSection({
  title,
  items,
  empty
}: {
  title: string;
  items: SpanItem[];
  empty: string;
}) {
  return (
    <Box className="constructor-section">
      <Stack spacing={1.25}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        {items.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {empty}
          </Typography>
        ) : (
          <Stack spacing={1}>
            {items.map((item) => (
              <Box key={item.id} className="constructor-evidence-row">
                <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                    {item.label ?? item.type}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" className="constructor-mono">
                    {item.type}
                  </Typography>
                  <Typography variant="body2">«{item.text}»</Typography>
                </Stack>
                <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <Chip size="small" variant="outlined" label={sourceLabel(item.source)} />
                  {item.settings_refs?.[0] && (
                    <Chip
                      size="small"
                      color="info"
                      variant="outlined"
                      label={`${item.settings_refs[0].section}:${item.settings_refs[0].key}`}
                    />
                  )}
                </Stack>
              </Box>
            ))}
          </Stack>
        )}
      </Stack>
    </Box>
  );
}

function EmptyHint({ children }: { children: string }) {
  return (
    <Typography variant="body2" color="text.secondary" className="constructor-empty-hint">
      {children}
    </Typography>
  );
}

function createAliasEditor(text: string): SelectionEditorState {
  const catalog: AliasCatalogName = "vendors";
  return {
    kind: "alias",
    text,
    catalog,
    key: constructorKeyFromText(text),
    canonical: text,
    alias_type: defaultAliasTypeForCatalog(catalog),
    fact_types: defaultAliasTypeForCatalog(catalog),
    confidence: "0.7",
    color: ""
  };
}

function selectionEditorFromAlias(catalog: AliasCatalogName, alias: AliasSetting, selectedText: string): SelectionEditorState {
  return {
    kind: "alias",
    text: selectedText,
    catalog,
    key: alias.key,
    canonical: alias.canonical,
    alias_type: alias.type,
    fact_types: alias.fact_types.join("\n"),
    confidence: alias.confidence === null || alias.confidence === undefined ? "" : String(alias.confidence),
    color: alias.color ?? ""
  };
}

function createFactEditor(text: string): SelectionEditorState {
  return {
    kind: "fact",
    text,
    target_type: constructorKeyFromText(text),
    target_label: text,
    group: "Операторские факты",
    phrase_kind: "exact",
    confidence: "0.5",
    color: ""
  };
}

function selectionEditorFromFact(rule: RuleSetting, selectedText: string): SelectionEditorState {
  return {
    kind: "fact",
    text: selectedText,
    target_type: rule.type,
    target_label: rule.label,
    group: rule.group ?? "",
    phrase_kind: "exact",
    confidence: rule.confidence === null || rule.confidence === undefined ? "" : String(rule.confidence),
    color: rule.color ?? ""
  };
}

function createSignalEditor(overrides?: Partial<SignalEditorState>): SignalEditorState {
  return {
    selected_signal_type: "",
    type: "",
    label: "",
    group: "Доменные сигналы",
    confidence: "0.7",
    color: "#0b57d0",
    score_weight: "0",
    fact_types: [],
    ...overrides
  };
}

function signalEditorFromRule(rule: RuleSetting, weight: number): SignalEditorState {
  return createSignalEditor({
    selected_signal_type: rule.type,
    type: rule.type,
    label: rule.label,
    group: rule.group ?? "Доменные сигналы",
    confidence: rule.confidence === null || rule.confidence === undefined ? "" : String(rule.confidence),
    color: rule.color ?? "#0b57d0",
    score_weight: String(weight),
    fact_types: factDependencyTypes(rule)
  });
}

function buildPreviewFactChoices(items: SpanItem[]): PreviewFactChoice[] {
  const byType = new Map<string, PreviewFactChoice>();
  for (const item of items) {
    const existing = byType.get(item.type);
    if (existing) {
      existing.matchedTexts = uniqueStrings([...existing.matchedTexts, item.text]);
      continue;
    }
    byType.set(item.type, {
      type: item.type,
      label: item.label ?? item.type,
      matchedTexts: [item.text]
    });
  }
  return Array.from(byType.values());
}

function mergeSignalFactChoices(previewFacts: PreviewFactChoice[], selectedFactTypes: string[]): PreviewFactChoice[] {
  const byType = new Map<string, PreviewFactChoice>();
  for (const item of previewFacts) {
    byType.set(item.type, item);
  }
  for (const factType of selectedFactTypes) {
    if (!byType.has(factType)) {
      byType.set(factType, { type: factType, label: factType, matchedTexts: [] });
    }
  }
  return Array.from(byType.values());
}

function findSelectionOwner(draft: NlpSettings, text: string): SelectionOwner | null {
  const normalizedText = text.trim().toLocaleLowerCase("ru-RU");
  for (const catalog of aliasCatalogs) {
    const alias = draft[catalog].find((item) =>
      item.aliases.some((candidate) => candidate.trim().toLocaleLowerCase("ru-RU") === normalizedText)
    );
    if (alias) {
      return {
        kind: "alias",
        label: `${catalogLabel(catalog)}: ${alias.canonical}`,
        catalog,
        alias
      };
    }
  }

  const exactTokens = safeExactPhraseTokens(text);
  const exactKey = exactTokens?.join(" ") ?? null;
  const rule = draft.facts.find((item) => {
    const exactMatch =
      exactKey !== null && item.phrases.some((phrase) => phrase.join(" ") === exactKey);
    const semanticMatch = item.patterns.some(
      (pattern) => (pattern.source_text ?? "").trim().toLocaleLowerCase("ru-RU") === normalizedText
    );
    return exactMatch || semanticMatch;
  });
  if (!rule) {
    return null;
  }
  return {
    kind: "fact",
    label: `Факт: ${rule.label}`,
    rule
  };
}

function safeExactPhraseTokens(text: string): string[] | null {
  try {
    return exactPhraseTokens(text);
  } catch {
    return null;
  }
}

function parseNumberOrNull(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stringListFromMultiline(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function catalogLabel(catalog: AliasCatalogName): string {
  if (catalog === "vendors") {
    return "Вендоры";
  }
  if (catalog === "protocols") {
    return "Протоколы";
  }
  if (catalog === "devices") {
    return "Устройства";
  }
  return "ПО";
}

function sourceLabel(source: string): string {
  if (source === "alias_catalog") {
    return "словарь";
  }
  if (source === "semantic_pattern") {
    return "лемматическое";
  }
  if (source === "exact_phrase") {
    return "точное";
  }
  if (source === "punctuation") {
    return "пунктуация";
  }
  return source;
}

function isPreviewEmpty(result: TextEnrichmentResult): boolean {
  return result.entities.length === 0 && result.facts.length === 0 && result.domain_signals.length === 0;
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      result.push(value);
    }
  }
  return result;
}
