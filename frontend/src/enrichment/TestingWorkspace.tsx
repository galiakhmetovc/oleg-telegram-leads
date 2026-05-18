import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SettingsIcon from "@mui/icons-material/Settings";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  LinearProgress,
  Link as MuiLink,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography
} from "@mui/material";
import { type FormEvent, type SyntheticEvent, useMemo } from "react";
import type { ReactNode } from "react";

import { EvidenceFlow } from "../EvidenceFlow";
import type { EvidenceFlowReason, EvidenceFlowSpan } from "../EvidenceFlow";
import {
  isAliasCatalogName,
  openSettingsTargetEvent,
  settingsTargetHash,
  type AliasCatalogName,
  type SettingsSection,
  type SettingsTarget
} from "../settings/navigation";
import type {
  EnrichedToken,
  EnrichmentEvent,
  EnrichmentJob,
  LeadAssessment,
  LeadCategory,
  LeadReason,
  PipelineTraceItem,
  SettingReference,
  SpanItem,
  SyntaxDependency,
  TextEnrichmentResult
} from "./types";

export function TestingWorkspace({
  inputText,
  onInputTextChange,
  onSubmit,
  isNarrowScreen,
  isProcessing,
  isSubmitting,
  error,
  job,
  events,
  result,
  activeTab,
  onTabChange,
  onOpenSettings,
  submitLabel = "Запустить обогащение"
}: {
  inputText: string;
  onInputTextChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  isNarrowScreen: boolean;
  isProcessing: boolean;
  isSubmitting: boolean;
  error: string | null;
  job: EnrichmentJob | null;
  events: EnrichmentEvent[];
  result: TextEnrichmentResult | null;
  activeTab: number;
  onTabChange: (event: SyntheticEvent, value: number) => void;
  onOpenSettings: (section: SettingsSection) => void;
  submitLabel?: string;
}) {
  return (
    <Box className="workspace-grid">
      <Paper component="form" onSubmit={onSubmit} className="input-panel" variant="outlined">
        <Stack spacing={2}>
          <Typography variant="h6">Входной текст</Typography>
          <TextField
            value={inputText}
            onChange={(event) => onInputTextChange(event.target.value)}
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
            {submitLabel}
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
              onChange={onTabChange}
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
              {activeTab === 0 && <Overview result={result} onOpenSettings={onOpenSettings} />}
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
  );
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
            ) : !job && !isSubmitting ? (
              <PlayArrowIcon color="disabled" />
            ) : (
              <CircularProgress size={20} />
            )}
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Статус: {statusLabel}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            {job?.nlp_config_revision !== null && job?.nlp_config_revision !== undefined && (
              <Chip label={`NLP-ревизия #${job.nlp_config_revision}`} variant="outlined" size="small" />
            )}
            <Chip label={`${progress}%`} color={job?.status === "failed" ? "error" : "primary"} size="small" />
          </Stack>
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
      <EvidenceFlow
        facts={result.facts}
        domainSignals={result.domain_signals}
        assessment={result.lead_assessment}
        renderLink={(target, children) => <SettingLink target={target}>{children}</SettingLink>}
        targetForSpan={evidenceFlowSpanTarget}
        targetForReasonType={(reason) => evidenceFlowReasonTypeTarget(reason, result)}
        targetForReasonWeight={(reason) => reasonWeightTarget(reason as LeadReason)}
        targetForCategory={(kind, key) => categoryTarget(kind, key)}
        targetForReviewLane={(key): SettingsTarget => ({ kind: "review_lane", key })}
      />
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

export function LeadAssessmentSummary({
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
        {assessment.is_lead ? "Потенциальный клиент" : "Недостаточно признаков лида"}
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
    const hasFactRuleMatch = result.facts.some(
      (fact) => fact.type === reason.key && isFactRuleSource(fact.source)
    );
    return hasFactRuleMatch ? { kind: "fact", key: reason.key } : { kind: "lead_fact_weight", key: reason.key };
  }
  return null;
}

function reasonWeightTarget(reason: LeadReason): SettingsTarget | null {
  if (reason.source === "score_cap") {
    return null;
  }
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
  if (result.facts.some((fact) => fact.type === type && isFactRuleSource(fact.source))) {
    return { kind: "fact", key: type };
  }
  if (result.lead_assessment?.reasons.some((reason) => reason.source === "fact" && reason.key === type)) {
    return { kind: "lead_fact_weight", key: type };
  }
  return null;
}

function evidenceFlowSpanTarget(span: EvidenceFlowSpan, kind: "fact" | "signal"): SettingsTarget | null {
  return spanPrimaryTarget(span as SpanItem, kind === "fact" ? "facts" : "signals");
}

function evidenceFlowReasonTypeTarget(reason: EvidenceFlowReason, result: TextEnrichmentResult): SettingsTarget | null {
  return reasonTypeTarget(reason as LeadReason, result);
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
  if (source === "score_cap") {
    return "Ограничитель score";
  }
  if (source === "exact_phrase") {
    return "Точная фраза";
  }
  if (source === "semantic_pattern") {
    return "Лемматическая фраза";
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
  if (item.source === "exact_phrase") {
    return "Сработало правило факта по точной фразе активной NLP-конфигурации.";
  }
  if (item.source === "semantic_pattern") {
    return "Сработало правило факта по лемматической фразе активной NLP-конфигурации.";
  }
  if (item.source === "yargy") {
    return "Сработало точное или лемматическое правило активной NLP-конфигурации.";
  }
  return "Источник вернул этот span без дополнительного объяснения.";
}

function isFactRuleSource(source: string): boolean {
  return source === "yargy" || source === "exact_phrase" || source === "semantic_pattern";
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
