import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import RateReviewIcon from "@mui/icons-material/RateReview";
import ScienceIcon from "@mui/icons-material/Science";
import StarIcon from "@mui/icons-material/Star";
import { Box, Button, Checkbox, Chip, FormControlLabel, IconButton, Stack, Typography } from "@mui/material";
import type { MouseEvent, ReactNode } from "react";
import { useMemo, useState } from "react";

import {
  ReviewStatusChip,
  candidateTemperatureLabel,
  formatDateTime,
  reviewLaneLabel
} from "./CandidateEvidence";
import { analyticsReviewHash } from "./analyticsRoutes";
import type { AnalyticsCandidate } from "./types";
import type { CandidateColumnKey, CandidateValueFilterRequest } from "./candidateQueueState";

type SideField = {
  key: string;
  label: string;
  value: ReactNode;
  rawValue?: string;
  filterField?: CandidateColumnKey;
  numeric?: boolean;
};

type AnalysisChip = {
  key: string;
  label: string;
  value: string;
  field: CandidateColumnKey;
  numeric?: boolean;
};

export function CandidateQueueSidePage({
  candidate,
  returnHash,
  goldenSavingId,
  onClose,
  onAddGolden,
  onFilterValue
}: {
  candidate: AnalyticsCandidate;
  returnHash: string;
  goldenSavingId?: string | null;
  onClose: () => void;
  onAddGolden?: (candidate: AnalyticsCandidate) => void;
  onFilterValue: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
}) {
  const [showEmpty, setShowEmpty] = useState(false);
  const fields = useMemo(() => candidateSideFields(candidate), [candidate]);
  const visibleFields = showEmpty ? fields : fields.filter((field) => fieldHasValue(field));
  const summaryChips = useMemo(() => candidateSummaryChips(candidate), [candidate]);
  const signalChips = useMemo(() => candidateSignalChips(candidate), [candidate]);
  const visibleReasons = candidate.reasons.filter((reason) => reason.key || reason.label);

  return (
    <Box component="aside" className="candidate-side-page" role="complementary" aria-label="Сообщение очереди">
      <Box className="candidate-side-page__header">
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" component="h3" noWrap>
            Сообщение {candidate.telegram_message_id ? `#${candidate.telegram_message_id}` : candidate.message_id}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {candidate.source_chat_title || candidate.source_chat_id || "Источник не указан"}
            {candidate.received_at ? ` · принято ${formatDateTime(candidate.received_at)}` : ""}
          </Typography>
        </Box>
        <IconButton size="small" aria-label="Закрыть side page" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box className="candidate-side-page__controls">
        <FormControlLabel
          control={
            <Checkbox
              size="small"
              checked={showEmpty}
              onChange={(event) => setShowEmpty(event.target.checked)}
            />
          }
          label="Показывать пустые"
        />
      </Box>

      <Stack direction="row" spacing={0.75} useFlexGap className="candidate-side-page__actions">
        {candidate.telegram_message_url && (
          <Button
            size="small"
            variant="text"
            startIcon={<OpenInNewIcon fontSize="small" />}
            href={candidate.telegram_message_url}
            target="_blank"
            rel="noreferrer"
          >
            Telegram
          </Button>
        )}
        <Button
          size="small"
          variant="text"
          startIcon={<RateReviewIcon fontSize="small" />}
          href={analyticsReviewHash(candidate.message_id, returnHash)}
        >
          Ревью / LLM
        </Button>
        <Button
          size="small"
          variant="text"
          startIcon={<ScienceIcon fontSize="small" />}
          href={candidate.testing_url ?? `/testing?message_id=${encodeURIComponent(candidate.message_id)}`}
        >
          Проверить
        </Button>
        {onAddGolden && (
          <Button
            size="small"
            variant="text"
            startIcon={<StarIcon fontSize="small" />}
            disabled={goldenSavingId === candidate.message_id}
            onClick={() => onAddGolden(candidate)}
          >
            В golden
          </Button>
        )}
      </Stack>

      <Box className="candidate-side-page__body">
        <section className="candidate-side-section">
          <Box className="candidate-side-summary">
            {summaryChips.map((chip) => (
              <SideFilterValue
                key={chip.key}
                field={chip.field}
                value={chip.value}
                label={chip.label}
                numeric={chip.numeric}
                onFilterValue={onFilterValue}
              >
                <Chip size="small" label={chip.label} />
              </SideFilterValue>
            ))}
          </Box>
        </section>

        <section className="candidate-side-section">
          <Typography className="candidate-side-section__title">Текст</Typography>
          <Typography variant="body2" className="candidate-side-text">
            {candidate.text}
          </Typography>
        </section>

        <section className="candidate-side-section">
          <Typography className="candidate-side-section__title">Поля</Typography>
          <Box className="candidate-side-fields">
            {visibleFields.map((field) => (
              <Box key={field.key} className="candidate-side-field">
                <Typography variant="caption" color="text.secondary">
                  {field.label}
                </Typography>
                <Box className="candidate-side-field__value">
                  {field.filterField && field.rawValue ? (
                    <SideFilterValue
                      field={field.filterField}
                      value={field.rawValue}
                      label={stringValue(field.value) || field.rawValue}
                      numeric={field.numeric}
                      onFilterValue={onFilterValue}
                    >
                      {field.value}
                    </SideFilterValue>
                  ) : (
                    field.value || "не указано"
                  )}
                </Box>
              </Box>
            ))}
          </Box>
        </section>

        {visibleReasons.length > 0 && (
          <section className="candidate-side-section">
            <Typography className="candidate-side-section__title">Причины</Typography>
            <Box className="candidate-side-reasons">
              {visibleReasons.slice(0, 7).map((reason, index) => {
                const value = reason.key || reason.label || "";
                return (
                  <SideFilterValue
                    key={`${value}-${index}`}
                    field="reasons"
                    value={value}
                    label={reason.label || reason.key}
                    onFilterValue={onFilterValue}
                  >
                    <Box component="span" className="candidate-side-reason">
                      <span className="candidate-side-reason__main">{reason.label || reason.key}</span>
                      <span className="candidate-side-reason__meta">{reason.weight > 0 ? `+${reason.weight}` : reason.weight}</span>
                    </Box>
                  </SideFilterValue>
                );
              })}
            </Box>
          </section>
        )}

        {signalChips.length > 0 && (
          <section className="candidate-side-section">
            <Typography className="candidate-side-section__title">Сигналы и факты</Typography>
            <Box className="candidate-side-chip-grid">
              {signalChips.map((chip) => (
                <SideFilterValue
                  key={chip.key}
                  field={chip.field}
                  value={chip.value}
                  label={chip.label}
                  onFilterValue={onFilterValue}
                >
                  <Chip size="small" variant="outlined" label={chip.label} />
                </SideFilterValue>
              ))}
            </Box>
          </section>
        )}

        {candidate.llm?.error && (
          <section className="candidate-side-section">
            <Typography className="candidate-side-section__title">LLM ошибка</Typography>
            <Typography variant="body2" className="candidate-side-note">
              {candidate.llm.error}
            </Typography>
          </section>
        )}
      </Box>
    </Box>
  );
}

function SideFilterValue({
  field,
  value,
  label,
  numeric,
  onFilterValue,
  children
}: {
  field: CandidateColumnKey;
  value: string;
  label: string;
  numeric?: boolean;
  onFilterValue: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
  children: ReactNode;
}) {
  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation();
    onFilterValue({ field, value, label: label || value, numeric }, event.currentTarget);
  }
  return (
    <button type="button" className="candidate-filter-value" aria-label={`Фильтровать значение: ${label || value}`} onClick={handleClick}>
      {children}
    </button>
  );
}

function candidateSideFields(candidate: AnalyticsCandidate): SideField[] {
  return [
    field("sourceType", "Тип источника", candidate.source_type ?? "telegram", "sourceType"),
    field("receivedAt", "Принято", candidate.received_at ? formatDateTime(candidate.received_at) : ""),
    field("messageDate", "Дата сообщения", candidate.message_date ? formatDateTime(candidate.message_date) : ""),
    field("sourceChat", "Чат", candidate.source_chat_title || candidate.source_chat_id || "", "sourceChat"),
    field("sourceChatId", "ID чата", candidate.source_chat_id ?? "", "sourceChatId"),
    field("sender", "Автор", candidate.sender_username ? `@${candidate.sender_username}` : candidate.sender_id ?? "", "sender"),
    field("score", "Score", String(candidate.score), "score", true),
    field("temperature", "Температура", candidateTemperatureLabel(candidate), "temperature", false, candidate.temperature),
    field("reviewLane", "Очередь", reviewLaneLabel(candidate.review_lane), "reviewLane", false, candidate.review_lane),
    {
      key: "reviewStatus",
      label: "Ревью",
      value: <ReviewStatusChip review={candidate.review ?? null} />,
      rawValue: candidate.review ? "reviewed" : "unreviewed",
      filterField: "reviewStatus"
    },
    field("llmStatus", "LLM статус", candidate.llm?.status ?? "", "llmStatus"),
    field("llmVerdict", "LLM verdict", candidate.llm?.verdict ?? "", "llmVerdict"),
    field(
      "llmConfidence",
      "LLM confidence",
      typeof candidate.llm?.confidence === "number" ? candidate.llm.confidence.toFixed(2) : "",
      "llmConfidence",
      true
    ),
    field("llmRecommendation", "LLM рекомендация", candidate.llm?.recommendation ?? "", "llmRecommendation"),
    field("llmModel", "LLM модель", candidate.llm?.model ?? "", "llmModel"),
    field("llmRoute", "LLM route", candidate.llm?.route_id ?? "", "llmRoute"),
    field(
      "solutionAreas",
      "Зоны решения",
      chipList(candidate.solution_areas.map((item) => item.label || item.type)),
      "solutionAreas",
      false,
      candidate.solution_areas[0]?.type
    ),
    field(
      "customerSegments",
      "Сегменты",
      chipList(candidate.customer_segments.map((item) => item.label || item.type)),
      "customerSegments",
      false,
      candidate.customer_segments[0]?.type
    ),
    field(
      "domainSignals",
      "Доменные сигналы",
      chipList(candidate.domain_signals.map((item) => item.label || item.type)),
      "domainSignals",
      false,
      candidate.domain_signals[0]?.type
    ),
    field(
      "facts",
      "Факты",
      chipList(candidate.facts.map((item) => item.text || item.label || item.type)),
      "text",
      false,
      candidate.facts[0]?.text || candidate.facts[0]?.label || candidate.facts[0]?.type
    ),
    field("enrichmentStatus", "Enrichment", candidate.enrichment_status ?? "", "enrichmentStatus")
  ];
}

function candidateSummaryChips(candidate: AnalyticsCandidate): AnalysisChip[] {
  const chips: AnalysisChip[] = [
    { key: "score", label: `Score ${candidate.score}`, value: String(candidate.score), field: "score", numeric: true },
    {
      key: "temperature",
      label: candidateTemperatureLabel(candidate),
      value: candidate.temperature,
      field: "temperature"
    },
    {
      key: "reviewLane",
      label: reviewLaneLabel(candidate.review_lane),
      value: candidate.review_lane,
      field: "reviewLane"
    },
    {
      key: "reviewStatus",
      label: candidate.review ? "С ревью" : "Без ревью",
      value: candidate.review ? "reviewed" : "unreviewed",
      field: "reviewStatus"
    }
  ];
  if (candidate.llm?.processed) {
    chips.push({
      key: "llmStatus",
      label: `LLM ${candidate.llm.status || "processed"}`,
      value: candidate.llm.status || "processed",
      field: "llmStatus"
    });
    if (candidate.llm.verdict) {
      chips.push({
        key: "llmVerdict",
        label: `Verdict ${candidate.llm.verdict}`,
        value: candidate.llm.verdict,
        field: "llmVerdict"
      });
    }
    if (typeof candidate.llm.confidence === "number") {
      chips.push({
        key: "llmConfidence",
        label: `Conf ${candidate.llm.confidence.toFixed(2)}`,
        value: candidate.llm.confidence.toFixed(2),
        field: "llmConfidence",
        numeric: true
      });
    }
  } else {
    chips.push({ key: "llmProcessed", label: "LLM нет", value: "not_processed", field: "llmStatus" });
  }
  return chips.filter((chip) => chip.value.trim());
}

function candidateSignalChips(candidate: AnalyticsCandidate): AnalysisChip[] {
  const chips: AnalysisChip[] = [];
  candidate.domain_signals.forEach((item, index) => {
    const value = item.type || item.label || "";
    if (value) {
      chips.push({
        key: `domain-${value}-${index}`,
        label: item.label || item.type,
        value,
        field: "domainSignals"
      });
    }
  });
  candidate.solution_areas.forEach((item, index) => {
    const value = item.type || item.label || "";
    if (value) {
      chips.push({
        key: `solution-${value}-${index}`,
        label: item.label || item.type,
        value,
        field: "solutionAreas"
      });
    }
  });
  candidate.customer_segments.forEach((item, index) => {
    const value = item.type || item.label || "";
    if (value) {
      chips.push({
        key: `segment-${value}-${index}`,
        label: item.label || item.type,
        value,
        field: "customerSegments"
      });
    }
  });
  candidate.facts.forEach((item, index) => {
    const value = item.text || item.label || item.type || "";
    if (value) {
      chips.push({
        key: `fact-${value}-${index}`,
        label: item.text || item.label || item.type,
        value,
        field: "text"
      });
    }
  });
  return chips.slice(0, 16);
}

function field(
  key: string,
  label: string,
  value: ReactNode,
  filterField?: CandidateColumnKey,
  numeric?: boolean,
  rawValue?: string
): SideField {
  return {
    key,
    label,
    value,
    rawValue: rawValue ?? (typeof value === "string" ? value : undefined),
    filterField,
    numeric
  };
}

function chipList(values: string[]): ReactNode {
  const filtered = values.filter(Boolean);
  if (filtered.length === 0) {
    return "";
  }
  return (
    <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
      {filtered.slice(0, 6).map((value) => (
        <Chip key={value} size="small" label={value} variant="outlined" />
      ))}
    </Stack>
  );
}

function fieldHasValue(field: SideField): boolean {
  if (typeof field.value === "string") {
    return Boolean(field.value.trim());
  }
  return Boolean(field.rawValue?.trim()) || Boolean(field.value);
}

function stringValue(value: ReactNode): string {
  return typeof value === "string" ? value : "";
}
