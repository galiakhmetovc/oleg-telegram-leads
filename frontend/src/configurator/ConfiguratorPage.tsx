import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
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

import { settingsTargetHash, type AliasCatalogName, type SettingsTarget } from "../settings/navigation";
import type { AliasSetting, NlpSettings, RuleSetting, SettingsSnapshot } from "../settings/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const aliasCatalogs: AliasCatalogName[] = ["vendors", "protocols", "devices", "software"];

type ConfiguratorLayer = "signals" | "facts" | "aliases" | "lead_scoring";

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

  function updateLeadScoring(patch: Partial<NlpSettings["lead_scoring"]>) {
    updateDraft((current) => ({
      ...current,
      lead_scoring: { ...current.lead_scoring, ...patch }
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
      <Stack className="configurator-shell configurator-empty" spacing={2}>
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
      <Paper variant="outlined" className="configurator-header">
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between" }}>
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <AccountTreeIcon color="primary" fontSize="small" />
              <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
                Конфигуратор правил
              </Typography>
              {activeRevision !== null && (
                <Chip size="small" color="primary" variant="outlined" label={`NLP-ревизия #${activeRevision}`} />
              )}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Рабочее место для цепочки: словари &rarr; факты &rarr; доменные сигналы &rarr; оценка лида.
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

      <Box className="configurator-shell">
        <Paper variant="outlined" className="configurator-nav configurator-panel">
          <ConfiguratorNavigator
            draft={draft}
            domainGroups={domainGroups}
            selection={activeSelection}
            onSelect={setSelection}
          />
        </Paper>

        <Paper variant="outlined" className="configurator-workspace configurator-panel">
          <ConfiguratorWorkspace
            draft={draft}
            selection={activeSelection}
            domainGroups={domainGroups}
            onSelect={setSelection}
            onUpdateSignal={updateSignal}
            onUpdateFact={updateFact}
            onUpdateAlias={updateAlias}
            onUpdateLeadScoring={updateLeadScoring}
          />
        </Paper>

        <Paper variant="outlined" className="configurator-inspector configurator-panel">
          <DependencyInspector draft={draft} selection={activeSelection} onSelect={setSelection} />
        </Paper>
      </Box>
    </Box>
  );
}

function ConfiguratorNavigator({
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
      <Box>
        <Typography variant="overline" color="text.secondary">
          Домены
        </Typography>
        <Stack spacing={0.75}>
          {domainGroups.map((group) => (
            <Button
              key={group.key}
              variant={selection?.kind === "domain" && selection.key === group.key ? "contained" : "text"}
              color="inherit"
              className="configurator-nav-button"
              aria-label={`${group.label} ${group.signalCount} сигнал ${group.factCount} фактов`}
              onClick={() => onSelect({ kind: "domain", key: group.key })}
            >
              <Box className="configurator-nav-button-content">
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
      </Box>
      <Divider />
      <Box>
        <Typography variant="overline" color="text.secondary">
          Слои
        </Typography>
        <Stack spacing={0.75}>
          <LayerButton
            label="Словари"
            meta={`${aliasCount} сущностей`}
            active={selection?.kind === "layer" && selection.key === "aliases"}
            onClick={() => onSelect({ kind: "layer", key: "aliases" })}
          />
          <LayerButton
            label="Факты"
            meta={`${draft.facts.length} правил`}
            active={selection?.kind === "layer" && selection.key === "facts"}
            onClick={() => onSelect({ kind: "layer", key: "facts" })}
          />
          <LayerButton
            label="Доменные сигналы"
            meta={`${draft.signals.length} правил`}
            active={selection?.kind === "layer" && selection.key === "signals"}
            onClick={() => onSelect({ kind: "layer", key: "signals" })}
          />
          <LayerButton
            label="Оценка лида"
            meta={`${Object.keys(draft.lead_scoring.signal_weights).length} весов сигналов`}
            active={selection?.kind === "layer" && selection.key === "lead_scoring"}
            onClick={() => onSelect({ kind: "layer", key: "lead_scoring" })}
          />
        </Stack>
      </Box>
    </Stack>
  );
}

function LayerButton({
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
      className="configurator-nav-button"
      onClick={onClick}
    >
      <Box className="configurator-nav-button-content">
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

function ConfiguratorWorkspace({
  draft,
  selection,
  domainGroups,
  onSelect,
  onUpdateSignal,
  onUpdateFact,
  onUpdateAlias,
  onUpdateLeadScoring
}: {
  draft: NlpSettings;
  selection: ConfiguratorSelection | null;
  domainGroups: DomainGroup[];
  onSelect: (selection: ConfiguratorSelection) => void;
  onUpdateSignal: (key: string, patch: Partial<RuleSetting>) => void;
  onUpdateFact: (key: string, patch: Partial<RuleSetting>) => void;
  onUpdateAlias: (catalog: AliasCatalogName, key: string, patch: Partial<AliasSetting>) => void;
  onUpdateLeadScoring: (patch: Partial<NlpSettings["lead_scoring"]>) => void;
}) {
  if (!selection) {
    return <EmptyWorkspace />;
  }
  if (selection.kind === "domain") {
    return <DomainWorkspace draft={draft} groupKey={selection.key} onSelect={onSelect} />;
  }
  if (selection.kind === "layer") {
    return (
      <LayerWorkspace
        draft={draft}
        layer={selection.key}
        domainGroups={domainGroups}
        onSelect={onSelect}
        onUpdateLeadScoring={onUpdateLeadScoring}
      />
    );
  }
  if (selection.kind === "signal") {
    const signal = draft.signals.find((item) => item.type === selection.key);
    return signal ? (
      <RuleEditor
        title="Доменный сигнал"
        rule={signal}
        scoreWeight={draft.lead_scoring.signal_weights[signal.type] ?? 0}
        onChange={(patch) => onUpdateSignal(signal.type, patch)}
        onWeightChange={(weight) =>
          onUpdateLeadScoring({
            signal_weights: { ...draft.lead_scoring.signal_weights, [signal.type]: weight }
          })
        }
        onOpenSettings={() => openSettingsTarget({ kind: "signal", key: signal.type })}
      />
    ) : (
      <EmptyWorkspace />
    );
  }
  if (selection.kind === "fact") {
    const fact = draft.facts.find((item) => item.type === selection.key);
    return fact ? (
      <RuleEditor
        title="Факт"
        rule={fact}
        scoreWeight={draft.lead_scoring.fact_weights[fact.type] ?? 0}
        onChange={(patch) => onUpdateFact(fact.type, patch)}
        onWeightChange={(weight) =>
          onUpdateLeadScoring({
            fact_weights: { ...draft.lead_scoring.fact_weights, [fact.type]: weight }
          })
        }
        onOpenSettings={() => openSettingsTarget({ kind: "fact", key: fact.type })}
      />
    ) : (
      <EmptyWorkspace />
    );
  }
  const alias = draft[selection.catalog].find((item) => item.key === selection.key);
  return alias ? (
    <AliasEditor
      catalog={selection.catalog}
      alias={alias}
      onChange={(patch) => onUpdateAlias(selection.catalog, alias.key, patch)}
      onOpenSettings={() => openSettingsTarget({ kind: "alias", catalog: selection.catalog, key: alias.key })}
    />
  ) : (
    <EmptyWorkspace />
  );
}

function DomainWorkspace({
  draft,
  groupKey,
  onSelect
}: {
  draft: NlpSettings;
  groupKey: string;
  onSelect: (selection: ConfiguratorSelection) => void;
}) {
  const signals = draft.signals.filter((signal) => groupKeyFor(signal.group) === groupKey);
  const facts = draft.facts.filter((fact) => groupKeyFor(fact.group) === groupKey);
  const dependencies = unique([...signals, ...facts].flatMap(ruleFactDependencies));
  const aliases = aliasesForDependencies(draft, dependencies);
  const label = groupLabelFromKey(groupKey);

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
          {label}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Доменная папка группирует правила навигационно. Поведение создают зависимости ниже.
        </Typography>
      </Box>

      <WorkspaceSection
        title="Доменные сигналы"
        meta={`${signals.length} правил`}
        emptyText="В этой папке нет сигналов."
      >
        {signals.map((signal) => (
          <EntityButton
            key={signal.type}
            title={signal.label}
            subtitle={signal.type}
            chips={ruleFactDependencies(signal)}
            onClick={() => onSelect({ kind: "signal", key: signal.type })}
          />
        ))}
      </WorkspaceSection>

      <WorkspaceSection title="Факты" meta={`${facts.length} правил`} emptyText="В этой папке нет фактов.">
        {facts.map((fact) => (
          <EntityButton
            key={fact.type}
            title={fact.label}
            subtitle={fact.type}
            chips={ruleFactDependencies(fact)}
            onClick={() => onSelect({ kind: "fact", key: fact.type })}
          />
        ))}
      </WorkspaceSection>

      <WorkspaceSection
        title="Словари в цепочке"
        meta={`${aliases.length} сущностей`}
        emptyText="Сигналы и факты домена пока не ссылаются на словари."
      >
        {aliases.map(({ catalog, alias }) => (
          <EntityButton
            key={`${catalog}:${alias.key}`}
            title={alias.canonical}
            subtitle={`${catalog}:${alias.key}`}
            chips={alias.aliases.slice(0, 4)}
            onClick={() => onSelect({ kind: "alias", catalog, key: alias.key })}
          />
        ))}
      </WorkspaceSection>
    </Stack>
  );
}

function LayerWorkspace({
  draft,
  layer,
  domainGroups,
  onSelect,
  onUpdateLeadScoring
}: {
  draft: NlpSettings;
  layer: ConfiguratorLayer;
  domainGroups: DomainGroup[];
  onSelect: (selection: ConfiguratorSelection) => void;
  onUpdateLeadScoring: (patch: Partial<NlpSettings["lead_scoring"]>) => void;
}) {
  if (layer === "signals") {
    return (
      <Stack spacing={2}>
        <LayerHeader title="Доменные сигналы" description="Сигналы зависят от фактов и дают веса в оценку лида." />
        {draft.signals.map((signal) => (
          <EntityButton
            key={signal.type}
            title={signal.label}
            subtitle={`${signal.type} · ${groupLabelFromKey(groupKeyFor(signal.group))}`}
            chips={ruleFactDependencies(signal)}
            onClick={() => onSelect({ kind: "signal", key: signal.type })}
          />
        ))}
      </Stack>
    );
  }
  if (layer === "facts") {
    return (
      <Stack spacing={2}>
        <LayerHeader title="Факты" description="Факты извлекаются правилами или выпускаются словарями." />
        {draft.facts.map((fact) => (
          <EntityButton
            key={fact.type}
            title={fact.label}
            subtitle={`${fact.type} · ${groupLabelFromKey(groupKeyFor(fact.group))}`}
            chips={ruleFactDependencies(fact)}
            onClick={() => onSelect({ kind: "fact", key: fact.type })}
          />
        ))}
      </Stack>
    );
  }
  if (layer === "aliases") {
    return (
      <Stack spacing={2}>
        <LayerHeader title="Словари" description="Словари хранят написания брендов, устройств, протоколов и ПО." />
        {aliasCatalogs.map((catalog) => (
          <WorkspaceSection
            key={catalog}
            title={catalogLabel(catalog)}
            meta={`${draft[catalog].length} сущностей`}
            emptyText="Пока пусто."
          >
            {draft[catalog].map((alias) => (
              <EntityButton
                key={alias.key}
                title={alias.canonical}
                subtitle={`${catalog}:${alias.key}`}
                chips={[...alias.fact_types, ...alias.aliases.slice(0, 3)]}
                onClick={() => onSelect({ kind: "alias", catalog, key: alias.key })}
              />
            ))}
          </WorkspaceSection>
        ))}
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <LayerHeader
        title="Оценка лида"
        description="Порог, веса и таксономия превращают найденные сигналы и факты в решение оператора."
      />
      <Box className="configurator-form-grid">
        <TextField
          label="Порог lead"
          type="number"
          value={draft.lead_scoring.lead_threshold}
          onChange={(event) => onUpdateLeadScoring({ lead_threshold: numberFromInput(event.target.value) })}
        />
        <TextField
          label="Порог warm"
          type="number"
          value={draft.lead_scoring.warm_threshold}
          onChange={(event) => onUpdateLeadScoring({ warm_threshold: numberFromInput(event.target.value) })}
        />
        <TextField
          label="Порог hot"
          type="number"
          value={draft.lead_scoring.hot_threshold}
          onChange={(event) => onUpdateLeadScoring({ hot_threshold: numberFromInput(event.target.value) })}
        />
      </Box>
      <WorkspaceSection title="Папки доменов" meta={`${domainGroups.length} групп`} emptyText="Папок нет.">
        {domainGroups.map((group) => (
          <EntityButton
            key={group.key}
            title={group.label}
            subtitle={`${group.signalCount} сигналов · ${group.factCount} фактов`}
            chips={[]}
            onClick={() => onSelect({ kind: "domain", key: group.key })}
          />
        ))}
      </WorkspaceSection>
      <ScoringUsage draft={draft} />
    </Stack>
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
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
        <Box>
          <Typography variant="overline" color="text.secondary">
            {title}
          </Typography>
          <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
            {rule.label}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {rule.type}
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<OpenInNewIcon />} onClick={onOpenSettings}>
          Детально в настройках
        </Button>
      </Stack>

      <Box className="configurator-form-grid">
        <TextField label="Название" value={rule.label} onChange={(event) => onChange({ label: event.target.value })} />
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

      <WorkspaceSection
        title="Зависит от фактов"
        meta={`${dependencies.length} типов`}
        emptyText="Правило не зависит от других фактов."
      >
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          {dependencies.map((dependency) => (
            <Chip key={dependency} size="small" label={dependency} />
          ))}
        </Stack>
      </WorkspaceSection>

      <WorkspaceSection
        title="Матчинги правила"
        meta={`${rule.phrases.length} точных · ${rule.patterns.length} лемматических`}
        emptyText="Точные и лемматические фразы редактируются в детальной форме настроек."
      >
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          {rule.phrases.slice(0, 8).map((phrase, index) => (
            <Chip key={`phrase-${index}`} size="small" label={phrase.join(" ")} />
          ))}
          {rule.patterns.slice(0, 8).map((pattern, index) => (
            <Chip
              key={`pattern-${index}`}
              size="small"
              variant="outlined"
              label={pattern.source_text ?? pattern.tokens.map((token) => token.value).join(" ")}
            />
          ))}
        </Stack>
      </WorkspaceSection>
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
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
        <Box>
          <Typography variant="overline" color="text.secondary">
            Словарь: {catalogLabel(catalog)}
          </Typography>
          <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
            {alias.canonical}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {catalog}:{alias.key}
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<OpenInNewIcon />} onClick={onOpenSettings}>
          Детально в настройках
        </Button>
      </Stack>

      <Box className="configurator-form-grid">
        <TextField
          label="Каноническое имя"
          value={alias.canonical}
          onChange={(event) => onChange({ canonical: event.target.value })}
        />
        <TextField select label="Тип" value={alias.type} onChange={(event) => onChange({ type: event.target.value as AliasSetting["type"] })}>
          <MenuItem value="vendor">vendor</MenuItem>
          <MenuItem value="protocol">protocol</MenuItem>
          <MenuItem value="device">device</MenuItem>
          <MenuItem value="software">software</MenuItem>
          <MenuItem value="model">model</MenuItem>
        </TextField>
      </Box>

      <TextField
        label="Alias, по одному на строку"
        value={alias.aliases.join("\n")}
        multiline
        minRows={5}
        onChange={(event) => onChange({ aliases: linesFromInput(event.target.value) })}
      />
      <TextField
        label="Выпускаемые fact_types, по одному на строку"
        value={alias.fact_types.join("\n")}
        multiline
        minRows={4}
        onChange={(event) => onChange({ fact_types: linesFromInput(event.target.value) })}
      />
    </Stack>
  );
}

function DependencyInspector({
  draft,
  selection,
  onSelect
}: {
  draft: NlpSettings;
  selection: ConfiguratorSelection | null;
  onSelect: (selection: ConfiguratorSelection) => void;
}) {
  const report = useMemo(() => buildDependencyReport(draft, selection), [draft, selection]);

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="overline" color="text.secondary">
          Инспектор
        </Typography>
        <Typography variant="h6" component="h2" sx={{ fontWeight: 700 }}>
          Связи и влияние
        </Typography>
      </Box>
      <InspectorSection title="Выпускает / содержит" values={report.emits} />
      <InspectorSection title="Зависит от" values={report.depends} />
      <WorkspaceSection
        title="Используется в"
        meta={`${report.usedBy.length} связей`}
        emptyText="Явных downstream-связей не найдено."
      >
        {report.usedBy.map((usage) => (
          <Button
            key={usage.key}
            variant="text"
            color="inherit"
            className="configurator-usage-button"
            onClick={() => {
              if (usage.selection) {
                onSelect(usage.selection);
              }
            }}
          >
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {usage.label}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {usage.detail}
              </Typography>
            </Box>
          </Button>
        ))}
      </WorkspaceSection>
      <InspectorSection title="Score / таксономия" values={report.scoring} />
    </Stack>
  );
}

function InspectorSection({ title, values }: { title: string; values: string[] }) {
  return (
    <WorkspaceSection title={title} meta={`${values.length}`} emptyText="Нет данных для текущего выбора.">
      <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
        {values.map((value) => (
          <Chip key={value} size="small" variant="outlined" label={value} />
        ))}
      </Stack>
    </WorkspaceSection>
  );
}

function WorkspaceSection({
  title,
  meta,
  emptyText,
  children
}: {
  title: string;
  meta: string;
  emptyText: string;
  children: ReactNode;
}) {
  const hasChildren = Array.isArray(children) ? children.length > 0 : Boolean(children);
  return (
    <Box className="configurator-section">
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Chip size="small" variant="outlined" label={meta} />
      </Stack>
      {hasChildren ? <Stack spacing={1}>{children}</Stack> : <Typography variant="body2" color="text.secondary">{emptyText}</Typography>}
    </Box>
  );
}

function EntityButton({
  title,
  subtitle,
  chips,
  onClick
}: {
  title: string;
  subtitle: string;
  chips: string[];
  onClick: () => void;
}) {
  return (
    <Button variant="text" color="inherit" className="configurator-entity-button" onClick={onClick}>
      <Stack spacing={0.75} sx={{ minWidth: 0, width: "100%" }}>
        <Box>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary" className="configurator-mono">
            {subtitle}
          </Typography>
        </Box>
        {chips.length > 0 && (
          <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
            {chips.slice(0, 6).map((chip) => (
              <Chip key={chip} size="small" label={chip} />
            ))}
            {chips.length > 6 && <Chip size="small" variant="outlined" label={`+${chips.length - 6}`} />}
          </Stack>
        )}
      </Stack>
    </Button>
  );
}

function LayerHeader({ title, description }: { title: string; description: string }) {
  return (
    <Box>
      <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {description}
      </Typography>
    </Box>
  );
}

function EmptyWorkspace() {
  return (
    <Stack spacing={1}>
      <Typography variant="h6">Выберите узел конфигурации</Typography>
      <Typography variant="body2" color="text.secondary">
        Слева доступны домены и слои. В центре появится карточка выбранной сущности.
      </Typography>
    </Stack>
  );
}

function ScoringUsage({ draft }: { draft: NlpSettings }) {
  return (
    <Stack spacing={2}>
      <WorkspaceSection
        title="Зоны решения"
        meta={`${Object.keys(draft.lead_scoring.solution_areas).length}`}
        emptyText="Зон решения нет."
      >
        {Object.entries(draft.lead_scoring.solution_areas).map(([key, area]) => (
          <EntityButton
            key={key}
            title={area.label}
            subtitle={key}
            chips={[...area.signal_types, ...area.fact_types]}
            onClick={() => openSettingsTarget({ kind: "solution_area", key })}
          />
        ))}
      </WorkspaceSection>
      <WorkspaceSection
        title="Сегменты клиентов"
        meta={`${Object.keys(draft.lead_scoring.customer_segments).length}`}
        emptyText="Сегментов нет."
      >
        {Object.entries(draft.lead_scoring.customer_segments).map(([key, segment]) => (
          <EntityButton
            key={key}
            title={segment.label}
            subtitle={key}
            chips={[...segment.signal_types, ...segment.fact_types]}
            onClick={() => openSettingsTarget({ kind: "customer_segment", key })}
          />
        ))}
      </WorkspaceSection>
      <WorkspaceSection
        title="Очереди разбора"
        meta={`${draft.lead_scoring.review_lanes.length}`}
        emptyText="Очередей нет."
      >
        {draft.lead_scoring.review_lanes.map((lane) => (
          <EntityButton
            key={lane.key}
            title={lane.label}
            subtitle={`${lane.key} · priority ${lane.priority}`}
            chips={lane.match_groups.flatMap((group) => [
              ...group.signal_types,
              ...group.fact_types,
              ...group.solution_area_types,
              ...group.customer_segment_types
            ])}
            onClick={() => openSettingsTarget({ kind: "review_lane", key: lane.key })}
          />
        ))}
      </WorkspaceSection>
    </Stack>
  );
}

function buildDomainGroups(draft: NlpSettings): DomainGroup[] {
  const labels = new Map<string, string>();
  for (const rule of [...draft.signals, ...draft.facts]) {
    const key = groupKeyFor(rule.group);
    labels.set(key, groupLabelFromKey(key));
  }
  return [...labels.entries()]
    .map(([key, label]) => ({
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

function buildDependencyReport(draft: NlpSettings, selection: ConfiguratorSelection | null) {
  if (!selection) {
    return { emits: [], depends: [], usedBy: [], scoring: [] };
  }

  if (selection.kind === "domain") {
    const signals = draft.signals.filter((signal) => groupKeyFor(signal.group) === selection.key);
    const facts = draft.facts.filter((fact) => groupKeyFor(fact.group) === selection.key);
    return {
      emits: [...signals.map((signal) => signal.type), ...facts.map((fact) => fact.type)],
      depends: unique([...signals, ...facts].flatMap(ruleFactDependencies)),
      usedBy: [],
      scoring: unique([
        ...signals
          .filter((signal) => draft.lead_scoring.signal_weights[signal.type] !== undefined)
          .map((signal) => `signal weight ${draft.lead_scoring.signal_weights[signal.type]}: ${signal.label}`),
        ...facts
          .filter((fact) => draft.lead_scoring.fact_weights[fact.type] !== undefined)
          .map((fact) => `fact weight ${draft.lead_scoring.fact_weights[fact.type]}: ${fact.label}`)
      ])
    };
  }

  if (selection.kind === "layer") {
    return {
      emits: layerEmits(draft, selection.key),
      depends: [],
      usedBy: [],
      scoring: selection.key === "lead_scoring" ? [`lead >= ${draft.lead_scoring.lead_threshold}`, `warm >= ${draft.lead_scoring.warm_threshold}`, `hot >= ${draft.lead_scoring.hot_threshold}`] : []
    };
  }

  if (selection.kind === "alias") {
    const alias = draft[selection.catalog].find((item) => item.key === selection.key);
    if (!alias) {
      return { emits: [], depends: [], usedBy: [], scoring: [] };
    }
    const identity = aliasIdentityFact(selection.catalog, alias.key);
    const emitted = [identity, ...alias.fact_types];
    return {
      emits: emitted,
      depends: [],
      usedBy: usedByFacts(draft, emitted),
      scoring: scoringUsageForFacts(draft, emitted)
    };
  }

  const rule =
    selection.kind === "signal"
      ? draft.signals.find((signal) => signal.type === selection.key)
      : draft.facts.find((fact) => fact.type === selection.key);
  if (!rule) {
    return { emits: [], depends: [], usedBy: [], scoring: [] };
  }
  const emitted = [rule.type];
  return {
    emits: emitted,
    depends: ruleFactDependencies(rule),
    usedBy: usedByFacts(draft, emitted),
    scoring:
      selection.kind === "signal"
        ? scoringUsageForSignals(draft, emitted)
        : scoringUsageForFacts(draft, emitted)
  };
}

function usedByFacts(draft: NlpSettings, factTypes: string[]) {
  const factSet = new Set(factTypes);
  return [...draft.facts.map((fact) => ({ kind: "fact" as const, rule: fact })), ...draft.signals.map((signal) => ({ kind: "signal" as const, rule: signal }))]
    .filter(({ rule }) => ruleFactDependencies(rule).some((dependency) => factSet.has(dependency)))
    .map(({ kind, rule }) => ({
      key: `${kind}:${rule.type}`,
      label: rule.label,
      detail: kind === "signal" ? "доменный сигнал зависит от этого факта" : "факт зависит от этого факта",
      selection: { kind, key: rule.type } as ConfiguratorSelection
    }));
}

function scoringUsageForSignals(draft: NlpSettings, signalTypes: string[]): string[] {
  const signalSet = new Set(signalTypes);
  return unique([
    ...signalTypes
      .filter((signalType) => draft.lead_scoring.signal_weights[signalType] !== undefined)
      .map((signalType) => `score +${draft.lead_scoring.signal_weights[signalType]}: ${signalType}`),
    ...Object.entries(draft.lead_scoring.solution_areas)
      .filter(([, area]) => area.signal_types.some((signalType) => signalSet.has(signalType)))
      .map(([, area]) => `зона решения: ${area.label}`),
    ...Object.entries(draft.lead_scoring.customer_segments)
      .filter(([, segment]) => segment.signal_types.some((signalType) => signalSet.has(signalType)))
      .map(([, segment]) => `сегмент: ${segment.label}`),
    ...draft.lead_scoring.review_lanes
      .filter((lane) => lane.match_groups.some((group) => group.signal_types.some((signalType) => signalSet.has(signalType))))
      .map((lane) => `очередь: ${lane.label}`)
  ]);
}

function scoringUsageForFacts(draft: NlpSettings, factTypes: string[]): string[] {
  const factSet = new Set(factTypes);
  return unique([
    ...factTypes
      .filter((factType) => draft.lead_scoring.fact_weights[factType] !== undefined)
      .map((factType) => `score +${draft.lead_scoring.fact_weights[factType]}: ${factType}`),
    ...Object.entries(draft.lead_scoring.solution_areas)
      .filter(([, area]) => area.fact_types.some((factType) => factSet.has(factType)))
      .map(([, area]) => `зона решения: ${area.label}`),
    ...Object.entries(draft.lead_scoring.customer_segments)
      .filter(([, segment]) => segment.fact_types.some((factType) => factSet.has(factType)))
      .map(([, segment]) => `сегмент: ${segment.label}`),
    ...draft.lead_scoring.review_lanes
      .filter((lane) => lane.match_groups.some((group) => group.fact_types.some((factType) => factSet.has(factType))))
      .map((lane) => `очередь: ${lane.label}`)
  ]);
}

function layerEmits(draft: NlpSettings, layer: ConfiguratorLayer): string[] {
  if (layer === "signals") {
    return draft.signals.map((signal) => signal.type);
  }
  if (layer === "facts") {
    return draft.facts.map((fact) => fact.type);
  }
  if (layer === "aliases") {
    return aliasEntries(draft).map(({ catalog, alias }) => `${catalog}:${alias.key}`);
  }
  return [
    `${Object.keys(draft.lead_scoring.signal_weights).length} signal weights`,
    `${Object.keys(draft.lead_scoring.fact_weights).length} fact weights`,
    `${draft.lead_scoring.review_lanes.length} review lanes`
  ];
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
