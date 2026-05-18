import ScienceIcon from "@mui/icons-material/Science";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography
} from "@mui/material";

import { SectionTitle } from "./AnalyticsShared";
import { formatDateTime } from "./CandidateEvidence";
import { formatLlmTimeout, parseJsonObject, prettyJson } from "./analyticsFormat";
import type { AnalyticsCandidate } from "./types";

export type LlmVerificationConfig = {
  model: string;
  endpoint: string;
  timeout_seconds: number;
  execution_mode: string;
};

export type LlmVerificationRun = {
  id: string;
  source_message_id: string;
  enrichment_job_id: string;
  model: string;
  route_id?: string | null;
  schema_version: string;
  status: string;
  prompt?: string | null;
  attempts?: number;
  context_pack: Record<string, unknown>;
  response: Record<string, unknown> | null;
  raw_response: string | null;
  error: string | null;
  claimed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type LlmVerificationPage = {
  total: number;
  items: LlmVerificationRun[];
};

export function LlmRuntimePanel({
  config,
  loading,
  error
}: {
  config: LlmVerificationConfig | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Paper variant="outlined" className="analytics-section llm-verification-panel">
      <Stack spacing={1.5}>
        <SectionTitle
          title="LLM-проверка"
          subtitle="Настройки локальной модели и место, где смотреть полные запуски"
        />
        {loading && <LinearProgress />}
        {error && <Alert severity="error">{error}</Alert>}
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          <Chip label={config?.model ?? "модель не загружена"} color={config ? "primary" : "default"} />
          <Chip label={config?.execution_mode ?? "режим неизвестен"} variant="outlined" />
          <Chip label={`timeout ${formatLlmTimeout(config?.timeout_seconds)}`} variant="outlined" />
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
          Endpoint: {config?.endpoint ?? "не загружен"}
        </Typography>
        <Typography variant="body2">
          Проверки выполняет отдельный worker очереди llm. В списке кандидатов нажмите кнопку LLM у нужного
          сообщения, затем в карточке сообщения будет видно context_pack, очищенный response, raw_response,
          статус и связь с исходным сообщением.
        </Typography>
      </Stack>
    </Paper>
  );
}

export function LlmVerificationPanel({
  candidate,
  config,
  runs,
  loading,
  running,
  error,
  expandedRunId,
  onRun,
  onToggleRun
}: {
  candidate: AnalyticsCandidate;
  config: LlmVerificationConfig | null;
  runs: LlmVerificationRun[];
  loading: boolean;
  running: boolean;
  error: string | null;
  expandedRunId: string | null;
  onRun: () => void;
  onToggleRun: (runId: string) => void;
}) {
  return (
    <Paper variant="outlined" className="analytics-section llm-verification-panel">
      <Stack spacing={1.5}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <SectionTitle
            title="LLM-проверка"
            subtitle="Локальная модель получает trace сообщения и сохраняет полный запуск"
          />
          <Button
            variant="outlined"
            startIcon={running ? <CircularProgress size={18} color="inherit" /> : <ScienceIcon />}
            disabled={running}
            onClick={onRun}
          >
            Запустить LLM
          </Button>
        </Stack>

        {loading && <LinearProgress />}
        {error && <Alert severity="error">{error}</Alert>}

        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          <Chip label={config?.model ?? "модель не загружена"} color={config ? "primary" : "default"} />
          <Chip label={config?.execution_mode ?? "режим неизвестен"} variant="outlined" />
          <Chip label={`timeout ${formatLlmTimeout(config?.timeout_seconds)}`} variant="outlined" />
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
          Endpoint: {config?.endpoint ?? "не загружен"}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Worker: запуск ставится в очередь llm, отдельный llm-worker забирает задачу и сохраняет результат
          в таблицу llm_verifications.
        </Typography>

        <Box className="llm-linked-message">
          <Typography variant="caption" color="text.secondary">
            Связано с сообщением
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {candidate.source_chat_title ? `${candidate.source_chat_title}, ` : ""}
            {candidate.telegram_message_id ?? candidate.message_id}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            source_message_id: {candidate.message_id}
          </Typography>
        </Box>

        {runs.length === 0 && !loading ? (
          <Typography variant="body2" color="text.secondary">
            LLM-проверок для этого сообщения еще нет.
          </Typography>
        ) : (
          <Stack spacing={1}>
            {runs.map((run) => {
              const expanded = expandedRunId === run.id;
              return (
                <Box key={run.id} className="llm-run">
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    sx={{ alignItems: { xs: "flex-start", sm: "center" }, justifyContent: "space-between" }}
                  >
                    <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                      <Chip size="small" label={run.status} color={run.status === "completed" ? "success" : "error"} />
                      <Chip size="small" label={run.model} variant="outlined" />
                      <Chip size="small" label={formatDateTime(run.created_at)} variant="outlined" />
                    </Stack>
                    <Button
                      size="small"
                      variant="text"
                      onClick={() => onToggleRun(run.id)}
                      aria-label={`${expanded ? "Скрыть" : "Показать"} LLM run ${run.id}`}
                    >
                      {expanded ? "Скрыть" : "Показать"}
                    </Button>
                  </Stack>
                  <Collapse in={expanded} timeout="auto" unmountOnExit>
                    <Stack spacing={1.25} sx={{ pt: 1.25 }}>
                      <LlmRunMeta run={run} />
                      <JsonBlock title="System prompt" value={run.prompt ?? "Промпт не сохранен для этого run"} />
                      <JsonBlock title="Отдано модели: context_pack" value={run.context_pack} />
                      <JsonBlock title="Очищенный response" value={run.response} />
                      <NetworkResponseBlock rawResponse={run.raw_response} />
                      {run.error && <Alert severity="error">{run.error}</Alert>}
                    </Stack>
                  </Collapse>
                </Box>
              );
            })}
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}

function LlmRunMeta({ run }: { run: LlmVerificationRun }) {
  const message = run.context_pack.message as
    | {
        source_message_id?: string;
        source_chat_title?: string | null;
        telegram_message_id?: number | null;
        text?: string;
      }
    | undefined;
  return (
    <Box className="llm-run-meta">
      <Typography variant="caption" color="text.secondary">
        Run {run.id}
      </Typography>
      <Typography variant="body2">
        schema {run.schema_version}, enrichment_job {run.enrichment_job_id}
      </Typography>
      {message && (
        <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
          message: {message.source_chat_title ? `${message.source_chat_title}, ` : ""}
          {message.telegram_message_id ?? message.source_message_id}
        </Typography>
      )}
    </Box>
  );
}

function NetworkResponseBlock({ rawResponse }: { rawResponse: string | null }) {
  const parsed = parseJsonObject(rawResponse);
  return (
    <Box className="llm-json-block">
      <Typography variant="caption" color="text.secondary">
        Сетевой ответ модели
      </Typography>
      {parsed ? (
        <TableContainer>
          <Table size="small" aria-label="Сетевой ответ модели">
            <TableHead>
              <TableRow>
                <TableCell>Поле</TableCell>
                <TableCell>Значение</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(parsed).map(([key, value]) => (
                <TableRow key={key}>
                  <TableCell>{key}</TableCell>
                  <TableCell>
                    <Box component="pre" className="llm-json-pre">
                      {prettyJson(value)}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">
          JSON не распознан, смотри raw_response ниже.
        </Typography>
      )}
      <JsonBlock title="raw_response" value={rawResponse ?? ""} />
    </Box>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <Box className="llm-json-block">
      <Typography variant="caption" color="text.secondary">
        {title}
      </Typography>
      <Box component="pre" className="llm-json-pre">
        {prettyJson(value)}
      </Box>
    </Box>
  );
}
