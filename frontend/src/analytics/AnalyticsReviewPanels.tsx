import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import ScienceIcon from "@mui/icons-material/Science";
import StarIcon from "@mui/icons-material/Star";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  LinearProgress,
  Link as MuiLink,
  Paper,
  Stack,
  TextField,
  Typography
} from "@mui/material";

import { SectionTitle } from "./AnalyticsShared";
import {
  CandidateDetails,
  candidateTemperatureColor,
  candidateTemperatureLabel,
  formatDateTime,
  reviewLaneLabel
} from "./CandidateEvidence";
import { formatInteger } from "./analyticsFormat";
import { LeadAssessmentSummary } from "../enrichment/TestingWorkspace";
import type { EnrichmentEvent, EnrichmentJob, TextEnrichmentResult } from "../enrichment/types";
import type { AnalyticsCandidate, AnalyticsReviewVerdict } from "./types";

export const reviewVerdictOptions: Array<{
  value: AnalyticsReviewVerdict;
  label: string;
  color: "primary" | "secondary" | "error" | "info" | "success" | "warning";
}> = [
  { value: "lead", label: "Лид", color: "success" },
  { value: "not_lead", label: "Не лид", color: "error" },
  { value: "uncertain", label: "Сомнительно", color: "warning" },
  { value: "noise", label: "Шум", color: "secondary" }
];

export const reviewTagOptions = [
  { value: "no_provider_intent", label: "Нет запроса на подрядчика" },
  { value: "diy", label: "DIY / сам делает" },
  { value: "equipment_only", label: "Только оборудование" },
  { value: "sale", label: "Продажа / наличие" },
  { value: "not_pur_domain", label: "Не целевой домен" },
  { value: "weak_context", label: "Слабый контекст" },
  { value: "false_alias", label: "Ложный alias" },
  { value: "needs_alias", label: "Нужен alias" },
  { value: "needs_rule", label: "Нужно правило" }
];

export function ReviewPageHeader({
  candidate,
  messageId,
  loading,
  error,
  goldenSaving,
  goldenError,
  goldenMessage,
  saved,
  nextStatus,
  onBack,
  onTestMessage,
  onAddGolden
}: {
  candidate: AnalyticsCandidate | null;
  messageId: string;
  loading: boolean;
  error: string | null;
  goldenSaving: boolean;
  goldenError: string | null;
  goldenMessage: string | null;
  saved: boolean;
  nextStatus: string | null;
  onBack?: () => void;
  onTestMessage?: (candidate: AnalyticsCandidate) => void;
  onAddGolden: () => void;
}) {
  return (
    <Paper variant="outlined" className="analytics-header">
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
              Разбор сообщения
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {candidate?.source_chat_title || candidate?.source_chat_id || messageId}
            </Typography>
          </Box>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Button variant="outlined" startIcon={<ArrowBackIcon />} onClick={onBack} href={onBack ? undefined : "/analytics"}>
              Аналитика
            </Button>
            {candidate?.telegram_message_url && (
              <Button variant="outlined" href={candidate.telegram_message_url} target="_blank" rel="noreferrer">
                Telegram
              </Button>
            )}
            <Button
              variant="outlined"
              startIcon={<ScienceIcon />}
              disabled={!candidate}
              onClick={() => candidate && onTestMessage?.(candidate)}
            >
              Проверить
            </Button>
            <Button
              variant="outlined"
              startIcon={goldenSaving ? <CircularProgress size={18} color="inherit" /> : <StarIcon />}
              disabled={!candidate || goldenSaving}
              onClick={onAddGolden}
              aria-label={candidate ? `Добавить в golden ${candidate.message_id}` : "Добавить в golden"}
            >
              В golden
            </Button>
          </Stack>
        </Stack>

        {loading && (
          <Stack spacing={1}>
            <LinearProgress />
            <Typography variant="caption" color="text.secondary">
              Загружаю сообщение, разбор и сохраненное ревью
            </Typography>
          </Stack>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        {goldenError && <Alert severity="error">{goldenError}</Alert>}
        {goldenMessage && <Alert severity="success">{goldenMessage}</Alert>}
        {saved && <Alert severity="success">Ревью сохранено</Alert>}
        {nextStatus && <Alert severity="info">{nextStatus}</Alert>}
      </Stack>
    </Paper>
  );
}

export function ReviewPipelineCheckPanel({
  job,
  events,
  result,
  running,
  error,
  onRun
}: {
  job: EnrichmentJob | null;
  events: EnrichmentEvent[];
  result: TextEnrichmentResult | null;
  running: boolean;
  error: string | null;
  onRun: () => void;
}) {
  const progress = job?.progress_percent ?? (running ? 2 : 0);
  return (
    <Paper variant="outlined" className="analytics-section review-check-panel">
      <Stack spacing={1.25}>
        <Box className="review-check-panel__header">
          <SectionTitle
            title="Проверка"
            subtitle="Повторный прогон текущего текста через backend pipeline и активные настройки"
          />
          <Button
            size="small"
            variant="outlined"
            startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon fontSize="small" />}
            disabled={running}
            onClick={onRun}
          >
            Запустить
          </Button>
        </Box>
        {(job || running) && (
          <Stack spacing={0.75}>
            <Box className="review-check-panel__status">
              <Chip size="small" label={job?.status ?? "queued"} />
              <Typography variant="caption" color="text.secondary">
                {job?.message ?? "Ожидаю запуск pipeline"}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {progress}%
              </Typography>
            </Box>
            <LinearProgress variant="determinate" value={progress} />
          </Stack>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        {result?.lead_assessment ? (
          <Box className="review-check-panel__result">
            <LeadAssessmentSummary assessment={result.lead_assessment} compact />
            <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Chip size="small" variant="outlined" label={`Факты: ${result.facts.length}`} />
              <Chip size="small" variant="outlined" label={`Сигналы: ${result.domain_signals.length}`} />
              <Chip size="small" variant="outlined" label={`Trace: ${result.pipeline_trace.length}`} />
            </Stack>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Запуск покажет, как сообщение классифицируется текущими настройками прямо сейчас.
          </Typography>
        )}
        {events.length > 0 && (
          <Stack spacing={0.35} className="review-check-panel__events">
            {events.slice(0, 4).map((event) => (
              <Typography key={`${event.event_type}-${event.progress_percent}-${event.message}`} variant="caption" color="text.secondary">
                {event.progress_percent}% - {event.message}
              </Typography>
            ))}
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}

export function ReviewMarkupPanel({
  verdict,
  tags,
  comment,
  saving,
  onVerdictChange,
  onToggleTag,
  onCommentChange,
  onSave,
  onSaveNext
}: {
  verdict: AnalyticsReviewVerdict | null;
  tags: string[];
  comment: string;
  saving: boolean;
  onVerdictChange: (verdict: AnalyticsReviewVerdict | null) => void;
  onToggleTag: (tag: string) => void;
  onCommentChange: (comment: string) => void;
  onSave: () => void;
  onSaveNext: () => void;
}) {
  return (
    <Paper variant="outlined" className="analytics-section">
      <Stack spacing={1.5}>
        <SectionTitle title="Разметка" subtitle="1-4 выбирают вердикт, Ctrl+Enter сохраняет, N сохраняет и открывает следующее" />
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          {reviewVerdictOptions.map((option) => (
            <Button
              key={option.value}
              variant={verdict === option.value ? "contained" : "outlined"}
              color={option.color}
              onClick={() => onVerdictChange(option.value)}
            >
              {option.label}
            </Button>
          ))}
          <Button variant={verdict === null ? "contained" : "outlined"} onClick={() => onVerdictChange(null)}>
            Без оценки
          </Button>
        </Stack>
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          {reviewTagOptions.map((option) => (
            <Button
              key={option.value}
              size="small"
              variant={tags.includes(option.value) ? "contained" : "outlined"}
              onClick={() => onToggleTag(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </Stack>
        <TextField
          label="Комментарий ревью"
          value={comment}
          onChange={(event) => onCommentChange(event.target.value)}
          multiline
          minRows={4}
          fullWidth
        />
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          disabled={saving}
          onClick={onSave}
        >
          Сохранить ревью
        </Button>
        <Button
          variant="outlined"
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          disabled={saving}
          onClick={onSaveNext}
        >
          Сохранить и следующий
        </Button>
      </Stack>
    </Paper>
  );
}

export function ReviewSourceConstructorPanel({
  candidate,
  selectedText,
  constructorSaving,
  constructorError,
  constructorMessage,
  constructorDraft,
  onRememberSelection,
  onOpenConstructorDialog,
  onSaveNoise
}: {
  candidate: AnalyticsCandidate;
  selectedText: string;
  constructorSaving: boolean;
  constructorError: string | null;
  constructorMessage: string | null;
  constructorDraft: string | null;
  onRememberSelection: () => void;
  onOpenConstructorDialog: (kind: "alias" | "fact") => void;
  onSaveNoise: () => void;
}) {
  return (
    <>
      <Paper variant="outlined" className="analytics-section">
        <Stack spacing={1.25}>
          <SectionTitle
            title="Исходный текст"
            subtitle="Выделите фрагмент мышью, чтобы использовать его в конструкторе"
          />
          <Box className="review-message-text" onMouseUp={onRememberSelection} onKeyUp={onRememberSelection}>
            {candidate.text}
          </Box>
        </Stack>
      </Paper>

      <Paper variant="outlined" className="analytics-section">
        <Stack spacing={1.25}>
          <SectionTitle
            title="Конструктор сущностей"
            subtitle="Выделенный фрагмент можно превратить в правило настроек"
          />
          {selectedText ? (
            <Alert severity="info">
              Выделено: <strong>{selectedText}</strong>
            </Alert>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Выделите часть исходного текста, чтобы подготовить новую словарную сущность, факт или шум.
            </Typography>
          )}
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button variant="outlined" disabled={!selectedText} onClick={() => onOpenConstructorDialog("alias")}>
              В словарь
            </Button>
            <Button variant="outlined" disabled={!selectedText} onClick={() => onOpenConstructorDialog("fact")}>
              В факт
            </Button>
            <Button
              variant="outlined"
              disabled={!selectedText || constructorSaving}
              onClick={onSaveNoise}
              startIcon={constructorSaving ? <CircularProgress size={18} color="inherit" /> : undefined}
            >
              В шум
            </Button>
          </Stack>
          {constructorError && <Alert severity="error">{constructorError}</Alert>}
          {constructorMessage && (
            <Alert severity="success">
              {constructorMessage}.{" "}
              <MuiLink href="/settings/signals/operator_noise">Открыть настройку</MuiLink>
            </Alert>
          )}
          {constructorDraft && <Chip label={constructorDraft} variant="outlined" />}
        </Stack>
      </Paper>
    </>
  );
}

export function ReviewCandidateSummaryPanel({ candidate }: { candidate: AnalyticsCandidate }) {
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Paper variant="outlined" className="analytics-section">
        <Stack spacing={1.25}>
          <SectionTitle title="Карточка кандидата" subtitle="Текущий автоматический разбор сообщения" />
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Chip label={candidateTemperatureLabel(candidate)} color={candidateTemperatureColor(candidate)} />
            <Chip label={`${formatInteger(candidate.score)} баллов`} variant="outlined" />
            <Chip label={reviewLaneLabel(candidate.review_lane)} variant="outlined" />
            {candidate.received_at && <Chip label={formatDateTime(candidate.received_at)} variant="outlined" />}
          </Stack>
        </Stack>
      </Paper>
      <CandidateDetails candidate={candidate} />
    </Stack>
  );
}
