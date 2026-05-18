import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Link as MuiLink,
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

import { Kpi, SectionTitle } from "./AnalyticsShared";
import { formatInteger, formatRatioPercent } from "./analyticsFormat";
import type { ReviewEvalExample, ReviewEvalReport } from "./types";

export function ReviewEvalPanel({
  report,
  loading,
  error
}: {
  report: ReviewEvalReport | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Paper variant="outlined" className="analytics-section">
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between" }}>
          <SectionTitle
            title="Качество по ревью"
            subtitle="Сравнение ручных вердиктов с автоматической оценкой лида"
          />
          {loading && (
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                Обновление
              </Typography>
            </Stack>
          )}
        </Stack>
        {error && <Alert severity="warning">{error}</Alert>}
        {!report ? (
          <Typography variant="body2" color="text.secondary">
            Метрики появятся после загрузки ручных ревью.
          </Typography>
        ) : (
          <>
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Chip label={`Размечено: ${formatInteger(report.reviewed)}`} />
              <Chip label={`В оценке: ${formatInteger(report.evaluated)}`} variant="outlined" />
              <Chip
                label={`FP: ${formatInteger(report.false_positive)}`}
                color={report.false_positive > 0 ? "warning" : "default"}
              />
              <Chip
                label={`FN: ${formatInteger(report.false_negative)}`}
                color={report.false_negative > 0 ? "error" : "default"}
              />
              {report.skipped_uncertain > 0 && <Chip label={`Сомнительно: ${formatInteger(report.skipped_uncertain)}`} />}
            </Stack>
            <Box className="analytics-kpi-grid">
              <Kpi label="Precision" value={formatRatioPercent(report.precision)} />
              <Kpi label="Recall" value={formatRatioPercent(report.recall)} />
              <Kpi label="F1" value={formatRatioPercent(report.f1)} />
              <Kpi label="Accuracy" value={formatRatioPercent(report.accuracy)} />
            </Box>
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" } }}>
              <ReviewEvalExamples title="False Positives" examples={report.false_positives} />
              <ReviewEvalExamples title="False Negatives" examples={report.false_negatives} />
            </Box>
          </>
        )}
      </Stack>
    </Paper>
  );
}

function ReviewEvalExamples({ title, examples }: { title: string; examples: ReviewEvalExample[] }) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {examples.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Нет примеров.
        </Typography>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Сообщение</TableCell>
                <TableCell>Score</TableCell>
                <TableCell>Текст</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {examples.map((example) => (
                <TableRow key={example.source_message_id}>
                  <TableCell>
                    <MuiLink href={`/review/${encodeURIComponent(example.source_message_id)}`}>
                      {example.telegram_message_id ?? example.source_message_id}
                    </MuiLink>
                    {example.source_chat_title && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                        {example.source_chat_title}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.5}>
                      <Typography variant="body2">{formatInteger(example.score)}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {example.review_lane || example.temperature}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{example.text_preview}</Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}
