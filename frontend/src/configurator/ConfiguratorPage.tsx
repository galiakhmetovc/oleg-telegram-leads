import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
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
  TextField,
  Typography
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { TextEnrichmentResult } from "../enrichment/types";
import { settingsTargetHash, type AliasCatalogName, type SettingsTarget } from "../settings/navigation";
import type { AliasSetting, NlpSettings, RuleSetting, SettingsSnapshot } from "../settings/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const aliasCatalogs: AliasCatalogName[] = ["vendors", "protocols", "devices", "software"];

type ConfiguratorLayer = "aliases" | "facts" | "signals" | "lead_scoring";

type ConfiguratorSelection =
  | { kind: "domain"; key: string }
  | { kind: "layer"; key: ConfiguratorLayer }
  | { kind: "signal"; key: string }
  | { kind: "fact"; key: string }
  | { kind: "alias"; catalog: AliasCatalogName; key: string };

type AliasEntry = {
  catalog: AliasCatalogName;
  alias: AliasSetting;
};

type DomainGroup = {
  key: string;
  label: string;
  signalCount: number;
  factCount: number;
};

type GraphLane = {
  signal: RuleSetting;
  aliases: AliasEntry[];
  factTypes: string[];
  scoreWeight: number;
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
  const [selection, setSelection] = useState<ConfiguratorSelection | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const domainGroups = useMemo(() => (draft ? buildDomainGroups(draft) : []), [draft]);
  const activeSelection = useMemo(
    () => normalizeSelection(selection, draft, domainGroups),
    [domainGroups, draft, selection]
  );
  const activeDomainKey = useMemo(
    () => (draft ? domainKeyForSelection(activeSelection, draft, domainGroups) : "__ungrouped__"),
    [activeSelection, domainGroups, draft]
  );
  const activeRevision = draft?.source?.revision ?? settings?.nlp.source?.revision ?? null;

  function updateDraft(updater: (current: NlpSettings) => NlpSettings) {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const next = updater(current);
      setDirty(true);
      setMessage(null);
      setError(null);
      return next;
    });
  }

  function updateSignal(key: string, patch: Partial<RuleSetting>) {
    updateDraft((current) => ({
      ...current,
      signals: current.signals.map((signal) => (signal.type === key ? { ...signal, ...patch } : signal))
    }));
  }

  function updateFact(key: string, patch: Partial<RuleSetting>) {
    updateDraft((current) => ({
      ...current,
      facts: current.facts.map((fact) => (fact.type === key ? { ...fact, ...patch } : fact))
    }));
  }

  function updateAlias(catalog: AliasCatalogName, key: string, patch: Partial<AliasSetting>) {
    updateDraft((current) => ({
      ...current,
      [catalog]: current[catalog].map((alias) => (alias.key === key ? { ...alias, ...patch } : alias))
    }));
  }

  function updateSignalWeight(key: string, weight: number) {
    updateDraft((current) => ({
      ...current,
      lead_scoring: {
        ...current.lead_scoring,
        signal_weights: { ...current.lead_scoring.signal_weights, [key]: weight }
      }
    }));
  }

  function updateFactWeight(key: string, weight: number) {
    updateDraft((current) => ({
      ...current,
      lead_scoring: {
        ...current.lead_scoring,
        fact_weights: { ...current.lead_scoring.fact_weights, [key]: weight }
      }
    }));
  }

  async function saveDraft() {
    if (!draft) {
      return;
    }
    setSaving(true);
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
      setSaving(false);
    }
  }

  if (!draft) {
    return (
      <Stack className="configurator-page configurator-empty" spacing={2}>
        <Paper variant="outlined" className="configurator-panel">
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

  return (
    <Box className="configurator-page">
      <Paper variant="outlined" className="rule-ide-header">
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between" }}>
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <AccountTreeIcon color="primary" fontSize="small" />
              <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
                Rule IDE
              </Typography>
              <Chip size="small" variant="outlined" label="Конфигуратор правил" />
              {activeRevision !== null && (
                <Chip size="small" color="primary" variant="outlined" label={`NLP-ревизия #${activeRevision}`} />
              )}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Видимая цепочка: словари выпускают факты, факты собирают сигналы, сигналы и факты дают score.
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} className="configurator-actions" sx={{ alignItems: "center" }}>
            {dirty && <Chip size="small" color="warning" label="Есть несохраненные изменения" />}
            <Button
              variant="contained"
              startIcon={saving ? <CircularProgress color="inherit" size={18} /> : <SaveIcon />}
              disabled={!dirty || saving}
              onClick={() => void saveDraft()}
            >
              Сохранить ревизию
            </Button>
          </Stack>
        </Stack>
        {loading && <LinearProgress sx={{ mt: 2 }} />}
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

      <Box className="rule-ide-shell">
        <Paper variant="outlined" className="rule-ide-panel rule-ide-explorer">
          <RuleIdeExplorer
            draft={draft}
            domainGroups={domainGroups}
            selection={activeSelection}
            onSelect={setSelection}
          />
        </Paper>

        <Paper variant="outlined" className="rule-ide-panel rule-ide-graph-panel">
          <RuleGraph
            draft={draft}
            domainKey={activeDomainKey}
            selection={activeSelection}
            onSelect={setSelection}
          />
        </Paper>

        <Paper variant="outlined" className="rule-ide-panel rule-ide-side-panel">
          <RuleDetails
            draft={draft}
            selection={activeSelection}
            domainKey={activeDomainKey}
            onSelect={setSelection}
            onUpdateSignal={updateSignal}
            onUpdateFact={updateFact}
            onUpdateAlias={updateAlias}
            onUpdateSignalWeight={updateSignalWeight}
            onUpdateFactWeight={updateFactWeight}
          />
          <Divider />
          <DraftPreview draft={draft} />
        </Paper>
      </Box>
    </Box>
  );
}

function RuleIdeExplorer({
  draft,
  domainGroups,
  selection,
  onSelect
}: {
  draft: NlpSettings;
  domainGroups: DomainGroup[];
  selection: ConfiguratorSelection | null;
  onSelect: (selection: ConfiguratorSelection) => void;
}) {
  const aliasCount = aliasCatalogs.reduce((total, catalog) => total + draft[catalog].length, 0);

  return (
    <Stack spacing={2}>
      <PanelTitle eyebrow="EXPLORER" title="Карта правил" />
      <Stack spacing={0.75}>
        {domainGroups.map((group) => (
          <Button
            key={group.key}
            variant={selection?.kind === "domain" && selection.key === group.key ? "contained" : "text"}
            color="inherit"
            className="rule-ide-explorer-button"
            aria-label={`${group.label} ${group.signalCount} сигнал ${group.factCount} фактов`}
            onClick={() => onSelect({ kind: "domain", key: group.key })}
          >
            <Box className="rule-ide-explorer-button-content">
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {group.label}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {group.signalCount} сигналов · {group.factCount} фактов
              </Typography>
            </Box>
          </Button>
        ))}
      </Stack>
      <Divider />
      <Stack spacing={0.75}>
        <ExplorerLayerButton
          label="Словари сущностей"
          meta={`${aliasCount} сущностей`}
          active={selection?.kind === "layer" && selection.key === "aliases"}
          onClick={() => onSelect({ kind: "layer", key: "aliases" })}
        />
        <ExplorerLayerButton
          label="Факты правил"
          meta={`${draft.facts.length} правил`}
          active={selection?.kind === "layer" && selection.key === "facts"}
          onClick={() => onSelect({ kind: "layer", key: "facts" })}
        />
        <ExplorerLayerButton
          label="Доменные сигналы"
          meta={`${draft.signals.length} правил`}
          active={selection?.kind === "layer" && selection.key === "signals"}
          onClick={() => onSelect({ kind: "layer", key: "signals" })}
        />
        <ExplorerLayerButton
          label="Score-модель"
          meta={`${Object.keys(draft.lead_scoring.signal_weights).length} весов`}
          active={selection?.kind === "layer" && selection.key === "lead_scoring"}
          onClick={() => onSelect({ kind: "layer", key: "lead_scoring" })}
        />
      </Stack>
    </Stack>
  );
}

function ExplorerLayerButton({
  label,
  meta,
  active,
  onClick
}: {
  label: string;
  meta: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant={active ? "contained" : "text"}
      color="inherit"
      className="rule-ide-explorer-button"
      onClick={onClick}
    >
      <Box className="rule-ide-explorer-button-content">
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {label}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {meta}
        </Typography>
      </Box>
    </Button>
  );
}

function RuleGraph({
  draft,
  domainKey,
  selection,
  onSelect
}: {
  draft: NlpSettings;
  domainKey: string;
  selection: ConfiguratorSelection | null;
  onSelect: (selection: ConfiguratorSelection) => void;
}) {
  const lanes = useMemo(() => buildGraphLanes(draft, domainKey), [domainKey, draft]);
  const domain = groupLabelFromKey(domainKey);

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
        <PanelTitle eyebrow="GRAPH" title={domain} heading />
        <Chip size="small" variant="outlined" label={`${lanes.length} цепочек`} />
      </Stack>

      <Box className="rule-ide-node-grid rule-ide-graph-head">
        <Typography variant="caption">Словари</Typography>
        <Typography variant="caption">Факты</Typography>
        <Typography variant="caption">Сигналы</Typography>
        <Typography variant="caption">Score</Typography>
      </Box>

      {lanes.length === 0 ? (
        <EmptyHint>В этой доменной папке пока нет сигналов.</EmptyHint>
      ) : (
        <Stack spacing={1.25}>
          {lanes.map((lane) => (
            <Box key={lane.signal.type} className="rule-ide-node-grid rule-ide-graph-row">
              <NodeColumn>
                {lane.aliases.length === 0 ? (
                  <EmptyNode>нет словаря</EmptyNode>
                ) : (
                  lane.aliases.map(({ catalog, alias }) => (
                    <GraphNode
                      key={`${catalog}:${alias.key}`}
                      title={alias.canonical}
                      subtitle={alias.aliases[0] ?? `${catalog}:${alias.key}`}
                      selected={selection?.kind === "alias" && selection.catalog === catalog && selection.key === alias.key}
                      onClick={() => onSelect({ kind: "alias", catalog, key: alias.key })}
                    />
                  ))
                )}
              </NodeColumn>
              <NodeColumn>
                {lane.factTypes.length === 0 ? (
                  <EmptyNode>нет факта</EmptyNode>
                ) : (
                  lane.factTypes.map((factType) => {
                    const fact = draft.facts.find((item) => item.type === factType);
                    return (
                      <GraphNode
                        key={factType}
                        title={fact?.label ?? factType}
                        subtitle={factType}
                        selected={selection?.kind === "fact" && selection.key === factType}
                        onClick={() =>
                          fact ? onSelect({ kind: "fact", key: fact.type }) : onSelect({ kind: "layer", key: "facts" })
                        }
                      />
                    );
                  })
                )}
              </NodeColumn>
              <NodeColumn>
                <GraphNode
                  title={lane.signal.label}
                  subtitle={lane.signal.type}
                  selected={selection?.kind === "signal" && selection.key === lane.signal.type}
                  onClick={() => onSelect({ kind: "signal", key: lane.signal.type })}
                />
              </NodeColumn>
              <NodeColumn>
                <GraphNode
                  title={`+${lane.scoreWeight}`}
                  subtitle="signal weight"
                  selected={false}
                  onClick={() => onSelect({ kind: "signal", key: lane.signal.type })}
                />
              </NodeColumn>
            </Box>
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function RuleDetails({
  draft,
  selection,
  domainKey,
  onSelect,
  onUpdateSignal,
  onUpdateFact,
  onUpdateAlias,
  onUpdateSignalWeight,
  onUpdateFactWeight
}: {
  draft: NlpSettings;
  selection: ConfiguratorSelection | null;
  domainKey: string;
  onSelect: (selection: ConfiguratorSelection) => void;
  onUpdateSignal: (key: string, patch: Partial<RuleSetting>) => void;
  onUpdateFact: (key: string, patch: Partial<RuleSetting>) => void;
  onUpdateAlias: (catalog: AliasCatalogName, key: string, patch: Partial<AliasSetting>) => void;
  onUpdateSignalWeight: (key: string, weight: number) => void;
  onUpdateFactWeight: (key: string, weight: number) => void;
}) {
  if (!selection || selection.kind === "domain") {
    const lanes = buildGraphLanes(draft, domainKey);
    return (
      <Stack spacing={2}>
        <PanelTitle eyebrow="DETAILS" title={groupLabelFromKey(domainKey)} />
        <EmptyHint>Выберите узел в графе, чтобы редактировать его без перехода в полную форму.</EmptyHint>
        <MetricList
          items={[
            ["Сигнал-цепочки", String(lanes.length)],
            ["Словарные связи", String(unique(lanes.flatMap((lane) => lane.aliases.map(({ alias }) => alias.key))).length)],
            ["Факт-узлы", String(unique(lanes.flatMap((lane) => lane.factTypes)).length)]
          ]}
        />
      </Stack>
    );
  }

  if (selection.kind === "layer") {
    return (
      <Stack spacing={2}>
        <PanelTitle eyebrow="DETAILS" title={layerTitle(selection.key)} />
        <LayerDetails draft={draft} layer={selection.key} onSelect={onSelect} />
      </Stack>
    );
  }

  if (selection.kind === "signal") {
    const signal = draft.signals.find((item) => item.type === selection.key);
    if (!signal) {
      return <MissingDetails />;
    }
    return (
      <RuleEditor
        title="Доменный сигнал"
        rule={signal}
        scoreWeight={draft.lead_scoring.signal_weights[signal.type] ?? 0}
        onChange={(patch) => onUpdateSignal(signal.type, patch)}
        onWeightChange={(weight) => onUpdateSignalWeight(signal.type, weight)}
        onOpenSettings={() => openSettingsTarget({ kind: "signal", key: signal.type })}
      />
    );
  }

  if (selection.kind === "fact") {
    const fact = draft.facts.find((item) => item.type === selection.key);
    if (!fact) {
      return <MissingDetails />;
    }
    return (
      <RuleEditor
        title="Факт"
        rule={fact}
        scoreWeight={draft.lead_scoring.fact_weights[fact.type] ?? 0}
        onChange={(patch) => onUpdateFact(fact.type, patch)}
        onWeightChange={(weight) => onUpdateFactWeight(fact.type, weight)}
        onOpenSettings={() => openSettingsTarget({ kind: "fact", key: fact.type })}
      />
    );
  }

  const alias = draft[selection.catalog].find((item) => item.key === selection.key);
  if (!alias) {
    return <MissingDetails />;
  }
  return (
    <AliasEditor
      catalog={selection.catalog}
      alias={alias}
      onChange={(patch) => onUpdateAlias(selection.catalog, alias.key, patch)}
      onOpenSettings={() => openSettingsTarget({ kind: "alias", catalog: selection.catalog, key: alias.key })}
    />
  );
}

function RuleEditor({
  title,
  rule,
  scoreWeight,
  onChange,
  onWeightChange,
  onOpenSettings
}: {
  title: string;
  rule: RuleSetting;
  scoreWeight: number;
  onChange: (patch: Partial<RuleSetting>) => void;
  onWeightChange: (weight: number) => void;
  onOpenSettings: () => void;
}) {
  const dependencies = ruleFactDependencies(rule);

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
        <PanelTitle eyebrow="DETAILS" title={title} subtitle={rule.type} />
        <Button variant="outlined" size="small" startIcon={<OpenInNewIcon />} onClick={onOpenSettings}>
          Advanced
        </Button>
      </Stack>

      <TextField label="Название" value={rule.label} onChange={(event) => onChange({ label: event.target.value })} />
      <Box className="rule-ide-form-grid">
        <TextField label="Папка" value={rule.group ?? ""} onChange={(event) => onChange({ group: event.target.value })} />
        <TextField
          label="Confidence"
          type="number"
          value={rule.confidence ?? ""}
          slotProps={{ htmlInput: { min: 0, max: 1, step: 0.05 } }}
          onChange={(event) =>
            onChange({ confidence: event.target.value === "" ? null : numberFromInput(event.target.value) })
          }
        />
        <TextField
          label="Вес в score"
          type="number"
          value={scoreWeight}
          onChange={(event) => onWeightChange(numberFromInput(event.target.value))}
        />
      </Box>

      <MiniSection title="Зависит от" meta={`${dependencies.length}`}>
        <ChipRow values={dependencies} empty="Нет зависимостей" />
      </MiniSection>
      <MiniSection title="Матчинги" meta={`${rule.phrases.length} exact · ${rule.patterns.length} semantic`}>
        <ChipRow
          values={[
            ...rule.phrases.slice(0, 4).map((phrase) => phrase.join(" ")),
            ...rule.patterns.slice(0, 4).map((pattern) => pattern.source_text ?? pattern.tokens.map((token) => token.value).join(" "))
          ]}
          empty="Редактируются в полной форме настроек"
        />
      </MiniSection>
    </Stack>
  );
}

function AliasEditor({
  catalog,
  alias,
  onChange,
  onOpenSettings
}: {
  catalog: AliasCatalogName;
  alias: AliasSetting;
  onChange: (patch: Partial<AliasSetting>) => void;
  onOpenSettings: () => void;
}) {
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
        <PanelTitle eyebrow="DETAILS" title={alias.canonical} subtitle={`${catalog}:${alias.key}`} />
        <Button variant="outlined" size="small" startIcon={<OpenInNewIcon />} onClick={onOpenSettings}>
          Advanced
        </Button>
      </Stack>
      <TextField
        label="Каноническое имя"
        value={alias.canonical}
        onChange={(event) => onChange({ canonical: event.target.value })}
      />
      <TextField
        select
        label="Тип"
        value={alias.type}
        onChange={(event) => onChange({ type: event.target.value as AliasSetting["type"] })}
      >
        <MenuItem value="vendor">vendor</MenuItem>
        <MenuItem value="protocol">protocol</MenuItem>
        <MenuItem value="device">device</MenuItem>
        <MenuItem value="software">software</MenuItem>
        <MenuItem value="model">model</MenuItem>
      </TextField>
      <TextField
        label="Alias, по одному на строку"
        value={alias.aliases.join("\n")}
        multiline
        minRows={4}
        onChange={(event) => onChange({ aliases: linesFromInput(event.target.value) })}
      />
      <TextField
        label="Выпускаемые fact_types"
        value={alias.fact_types.join("\n")}
        multiline
        minRows={3}
        onChange={(event) => onChange({ fact_types: linesFromInput(event.target.value) })}
      />
    </Stack>
  );
}

function LayerDetails({
  draft,
  layer,
  onSelect
}: {
  draft: NlpSettings;
  layer: ConfiguratorLayer;
  onSelect: (selection: ConfiguratorSelection) => void;
}) {
  if (layer === "aliases") {
    return (
      <Stack spacing={1}>
        {aliasCatalogs.map((catalog) => (
          <Button
            key={catalog}
            color="inherit"
            className="rule-ide-explorer-button"
            onClick={() => {
              const first = draft[catalog][0];
              if (first) {
                onSelect({ kind: "alias", catalog, key: first.key });
              }
            }}
          >
            <Box className="rule-ide-explorer-button-content">
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {catalogLabel(catalog)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {draft[catalog].length} сущностей
              </Typography>
            </Box>
          </Button>
        ))}
      </Stack>
    );
  }
  if (layer === "facts") {
    return <EntityPicker items={draft.facts} onPick={(fact) => onSelect({ kind: "fact", key: fact.type })} />;
  }
  if (layer === "signals") {
    return <EntityPicker items={draft.signals} onPick={(signal) => onSelect({ kind: "signal", key: signal.type })} />;
  }
  return (
    <MetricList
      items={[
        ["Порог lead", String(draft.lead_scoring.lead_threshold)],
        ["Порог warm", String(draft.lead_scoring.warm_threshold)],
        ["Порог hot", String(draft.lead_scoring.hot_threshold)],
        ["Очереди разбора", String(draft.lead_scoring.review_lanes.length)]
      ]}
    />
  );
}

function EntityPicker({
  items,
  onPick
}: {
  items: RuleSetting[];
  onPick: (item: RuleSetting) => void;
}) {
  return (
    <Stack spacing={1}>
      {items.slice(0, 12).map((item) => (
        <Button key={item.type} color="inherit" className="rule-ide-explorer-button" onClick={() => onPick(item)}>
          <Box className="rule-ide-explorer-button-content">
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {item.label}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {item.type}
            </Typography>
          </Box>
        </Button>
      ))}
    </Stack>
  );
}

function DraftPreview({ draft }: { draft: NlpSettings }) {
  const [previewText, setPreviewText] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewResult, setPreviewResult] = useState<TextEnrichmentResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  async function runPreview() {
    if (!previewText.trim()) {
      return;
    }
    setPreviewing(true);
    setPreviewError(null);
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
      setPreviewError(caught instanceof Error ? caught.message : "Не удалось выполнить preview");
    } finally {
      setPreviewing(false);
    }
  }

  const assessment = previewResult?.lead_assessment ?? null;

  return (
    <Stack spacing={1.5}>
      <PanelTitle eyebrow="TEST MODE" title="Проверка draft" />
      <TextField
        label="Текст для проверки"
        value={previewText}
        multiline
        minRows={4}
        onChange={(event) => setPreviewText(event.target.value)}
      />
      <Button
        variant="contained"
        startIcon={previewing ? <CircularProgress color="inherit" size={18} /> : <PlayArrowIcon />}
        disabled={previewing || !previewText.trim()}
        onClick={() => void runPreview()}
      >
        Run
      </Button>
      {previewError && <Alert severity="error">{previewError}</Alert>}
      {assessment && (
        <Box className="rule-ide-preview-summary">
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Chip size="small" color={assessment.is_lead ? "success" : "default"} label={assessment.is_lead ? "lead" : "not lead"} />
            <Typography variant="h5" sx={{ fontWeight: 800 }}>
              {assessment.score}
            </Typography>
            <Chip size="small" variant="outlined" label={assessment.temperature} />
          </Stack>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", mt: 1 }}>
            {assessment.reasons.slice(0, 5).map((reason) => (
              <Chip key={`${reason.source}:${reason.key}`} size="small" label={`+${reason.weight} ${reason.label}`} />
            ))}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}

function PanelTitle({
  eyebrow,
  title,
  subtitle,
  heading = false
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  heading?: boolean;
}) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        {eyebrow}
      </Typography>
      <Typography variant={heading ? "h5" : "h6"} component={heading ? "h2" : "div"} sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {subtitle && (
        <Typography variant="caption" color="text.secondary" className="configurator-mono">
          {subtitle}
        </Typography>
      )}
    </Box>
  );
}

function NodeColumn({ children }: { children: ReactNode }) {
  return <Stack spacing={0.75}>{children}</Stack>;
}

function GraphNode({
  title,
  subtitle,
  selected,
  onClick
}: {
  title: string;
  subtitle: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant="text"
      color="inherit"
      className={selected ? "rule-ide-node rule-ide-node-selected" : "rule-ide-node"}
      onClick={onClick}
    >
      <Box>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary" className="configurator-mono">
          {subtitle}
        </Typography>
      </Box>
    </Button>
  );
}

function EmptyNode({ children }: { children: ReactNode }) {
  return (
    <Box className="rule-ide-empty-node">
      <Typography variant="caption" color="text.secondary">
        {children}
      </Typography>
    </Box>
  );
}

function EmptyHint({ children }: { children: ReactNode }) {
  return (
    <Typography variant="body2" color="text.secondary" className="rule-ide-empty-hint">
      {children}
    </Typography>
  );
}

function MissingDetails() {
  return (
    <Stack spacing={2}>
      <PanelTitle eyebrow="DETAILS" title="Узел не найден" />
      <EmptyHint>Настройки обновились, выберите другой узел в графе.</EmptyHint>
    </Stack>
  );
}

function MiniSection({ title, meta, children }: { title: string; meta: string; children: ReactNode }) {
  return (
    <Box className="configurator-section">
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Chip size="small" variant="outlined" label={meta} />
      </Stack>
      {children}
    </Box>
  );
}

function ChipRow({ values, empty }: { values: string[]; empty: string }) {
  const uniqueValues = unique(values);
  if (uniqueValues.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {empty}
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
      {uniqueValues.map((value) => (
        <Chip key={value} size="small" label={value} />
      ))}
    </Stack>
  );
}

function MetricList({ items }: { items: [string, string][] }) {
  return (
    <Box className="rule-ide-metric-list">
      {items.map(([label, value]) => (
        <Box key={label} className="rule-ide-metric-row">
          <Typography variant="caption" color="text.secondary">
            {label}
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {value}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function buildDomainGroups(draft: NlpSettings): DomainGroup[] {
  const labels = new Map<string, string>();
  for (const rule of [...draft.signals, ...draft.facts]) {
    const key = groupKeyFor(rule.group);
    labels.set(key, groupLabelFromKey(key));
  }
  return [...labels.entries()].map(([key, label]) => ({
    key,
    label,
    signalCount: draft.signals.filter((signal) => groupKeyFor(signal.group) === key).length,
    factCount: draft.facts.filter((fact) => groupKeyFor(fact.group) === key).length
  }));
}

function normalizeSelection(
  selection: ConfiguratorSelection | null,
  draft: NlpSettings | null,
  domainGroups: DomainGroup[]
): ConfiguratorSelection | null {
  if (!draft) {
    return null;
  }
  if (selection && selectionExists(selection, draft, domainGroups)) {
    return selection;
  }
  const firstGroup = domainGroups[0];
  if (firstGroup) {
    return { kind: "domain", key: firstGroup.key };
  }
  return { kind: "layer", key: "signals" };
}

function selectionExists(selection: ConfiguratorSelection, draft: NlpSettings, domainGroups: DomainGroup[]): boolean {
  if (selection.kind === "domain") {
    return domainGroups.some((group) => group.key === selection.key);
  }
  if (selection.kind === "layer") {
    return true;
  }
  if (selection.kind === "signal") {
    return draft.signals.some((signal) => signal.type === selection.key);
  }
  if (selection.kind === "fact") {
    return draft.facts.some((fact) => fact.type === selection.key);
  }
  return draft[selection.catalog].some((alias) => alias.key === selection.key);
}

function domainKeyForSelection(
  selection: ConfiguratorSelection | null,
  draft: NlpSettings,
  domainGroups: DomainGroup[]
): string {
  const fallback = domainGroups[0]?.key ?? "__ungrouped__";
  if (!selection) {
    return fallback;
  }
  if (selection.kind === "domain") {
    return selection.key;
  }
  if (selection.kind === "signal") {
    return groupKeyFor(draft.signals.find((signal) => signal.type === selection.key)?.group) || fallback;
  }
  if (selection.kind === "fact") {
    return groupKeyFor(draft.facts.find((fact) => fact.type === selection.key)?.group) || fallback;
  }
  if (selection.kind === "alias") {
    const alias = draft[selection.catalog].find((item) => item.key === selection.key);
    if (!alias) {
      return fallback;
    }
    const emitted = [aliasIdentityFact(selection.catalog, alias.key), ...alias.fact_types];
    const downstreamSignal = draft.signals.find((signal) =>
      ruleFactDependencies(signal).some((dependency) => emitted.includes(dependency))
    );
    return downstreamSignal ? groupKeyFor(downstreamSignal.group) : fallback;
  }
  return fallback;
}

function buildGraphLanes(draft: NlpSettings, domainKey: string): GraphLane[] {
  return draft.signals
    .filter((signal) => groupKeyFor(signal.group) === domainKey)
    .map((signal) => {
      const dependencies = ruleFactDependencies(signal);
      const aliases = aliasesForDependencies(draft, dependencies);
      const factTypes = unique([
        ...dependencies.filter((dependency) => !dependency.startsWith("alias:")),
        ...aliases.flatMap(({ alias }) => alias.fact_types)
      ]);
      return {
        signal,
        aliases,
        factTypes,
        scoreWeight: draft.lead_scoring.signal_weights[signal.type] ?? 0
      };
    });
}

function ruleFactDependencies(rule: RuleSetting): string[] {
  return unique((rule.match?.facts ?? []).flatMap((group) => group.types));
}

function aliasEntries(draft: NlpSettings): AliasEntry[] {
  return aliasCatalogs.flatMap((catalog) => draft[catalog].map((alias) => ({ catalog, alias })));
}

function aliasesForDependencies(draft: NlpSettings, dependencies: string[]): AliasEntry[] {
  const dependencySet = new Set(dependencies);
  return aliasEntries(draft).filter(({ catalog, alias }) => {
    if (dependencySet.has(aliasIdentityFact(catalog, alias.key))) {
      return true;
    }
    return alias.fact_types.some((factType) => dependencySet.has(factType));
  });
}

function openSettingsTarget(target: SettingsTarget) {
  const hash = settingsTargetHash(target);
  if (window.location.hash === hash) {
    window.dispatchEvent(new Event("hashchange"));
  } else {
    window.location.hash = hash;
  }
}

function aliasIdentityFact(catalog: AliasCatalogName, key: string): string {
  return `alias:${catalog}:${key}`;
}

function groupKeyFor(group: string | null | undefined): string {
  return group?.trim() || "__ungrouped__";
}

function groupLabelFromKey(key: string): string {
  return key === "__ungrouped__" ? "Без группы" : key;
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

function layerTitle(layer: ConfiguratorLayer): string {
  if (layer === "aliases") {
    return "Словари";
  }
  if (layer === "facts") {
    return "Факты";
  }
  if (layer === "signals") {
    return "Сигналы";
  }
  return "Score";
}

function numberFromInput(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function linesFromInput(value: string): string[] {
  return unique(value.split("\n").map((line) => line.trim()).filter(Boolean));
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}
