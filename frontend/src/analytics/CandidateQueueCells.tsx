import { Box, Button, Chip, Link as MuiLink, Stack, Typography } from "@mui/material";
import type { MouseEvent, ReactNode } from "react";

import {
  ReviewStatusChip,
  candidateTemperatureLabel,
  formatDateTime,
  formatWeight,
  reviewLaneLabel
} from "./CandidateEvidence";
import { formatInteger } from "./analyticsFormat";
import type { AnalyticsCandidate } from "./types";
import type { CandidateColumnKey, CandidateValueFilterRequest } from "./candidateQueueState";

export type CandidateGridCellValue = string | number | boolean | Date | null;

export function candidateColumnGridValue(
  columnKey: CandidateColumnKey,
  candidate: AnalyticsCandidate
): CandidateGridCellValue {
  switch (columnKey) {
    case "sourceType":
      return candidate.source_type ?? "telegram";
    case "receivedAt":
      return dateCellValue(candidate.received_at);
    case "messageDate":
      return dateCellValue(candidate.message_date);
    case "sourceChat":
      return candidate.source_chat_title || candidate.source_chat_id || "";
    case "sourceChatId":
      return candidate.source_chat_id ?? "";
    case "sourceInputRef":
      return candidate.source_input_ref ?? "";
    case "sourceChatStatus":
      return candidate.source_chat_status ?? "";
    case "telegramMessageId":
      return candidate.telegram_message_id ?? null;
    case "telegramChatId":
      return candidate.telegram_chat_id ?? "";
    case "sender":
      return candidate.sender_username ? `@${candidate.sender_username}` : candidate.sender_id ?? "";
    case "messageId":
      return candidate.message_id;
    case "score":
      return candidate.score;
    case "temperature":
      return candidate.temperature;
    case "reviewLane":
      return candidate.review_lane;
    case "autoLead":
      return candidate.auto_is_lead ?? candidate.is_lead ?? false;
    case "effectiveLead":
      return candidate.effective_is_lead ?? candidate.is_lead ?? false;
    case "leadStatusSource":
      return candidate.lead_status_source ?? "auto";
    case "reviewStatus":
      return candidate.review ? "reviewed" : "unreviewed";
    case "llmSummary":
      return candidate.llm?.processed ? [candidate.llm.status, candidate.llm.verdict].filter(Boolean).join(" ") : "not_processed";
    case "llmStatus":
      return candidate.llm?.status ?? (candidate.llm?.processed ? "processed" : "not_processed");
    case "llmVerdict":
      return candidate.llm?.verdict ?? "";
    case "llmConfidence":
      return candidate.llm?.confidence ?? null;
    case "llmRecommendation":
      return candidate.llm?.recommendation ?? "";
    case "llmAgreement":
      return candidate.llm?.agrees_with_rule_engine ?? null;
    case "llmModel":
      return candidate.llm?.model ?? "";
    case "llmRoute":
      return candidate.llm?.route_id ?? "";
    case "llmAttempts":
      return candidate.llm?.attempts ?? null;
    case "llmUpdatedAt":
      return dateCellValue(candidate.llm?.updated_at);
    case "llmError":
      return candidate.llm?.error ?? (candidate.llm?.has_error ? "error" : "");
    case "text":
      return candidate.text;
    case "reasons":
      return labelList(candidate.reasons, "key");
    case "solutionAreas":
      return labelList(candidate.solution_areas, "type");
    case "customerSegments":
      return labelList(candidate.customer_segments, "type");
    case "domainSignals":
      return labelList(candidate.domain_signals, "type");
    case "intentSignals":
      return labelList(candidate.intent_signals, "type");
    case "noiseSignals":
      return labelList(candidate.noise_signals, "type");
    case "facts":
      return labelList(candidate.facts, "type");
    case "enrichmentJobId":
      return candidate.enrichment_job_id ?? "";
    case "enrichmentStatus":
      return candidate.enrichment_status ?? "";
    case "enrichmentFinishedAt":
      return dateCellValue(candidate.enrichment_finished_at);
    case "enrichmentError":
      return stringifyJson(candidate.enrichment_error);
    case "telegramUrl":
      return candidate.telegram_message_url ?? "";
    case "appUrl":
      return candidate.app_message_url ?? "";
    case "testingUrl":
      return candidate.testing_url ?? "";
    case "sourceAccountId":
      return candidate.source_account_id ?? "";
    case "rawPayload":
      return stringifyJson(candidate.raw_payload);
    default:
      return "";
  }
}

export function CandidateColumnValue({
  columnKey,
  candidate,
  onFilterValue
}: {
  columnKey: CandidateColumnKey;
  candidate: AnalyticsCandidate;
  onFilterValue?: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
}) {
  switch (columnKey) {
    case "sourceType":
      return (
        <FilterValueButton
          field="sourceType"
          value={candidate.source_type ?? "telegram"}
          label={candidate.source_type ?? "telegram"}
          onFilterValue={onFilterValue}
        >
          <Chip size="small" label={candidate.source_type ?? "telegram"} variant="outlined" />
        </FilterValueButton>
      );
    case "receivedAt":
      return candidate.received_at ? formatDateTime(candidate.received_at) : "не указано";
    case "messageDate":
      return candidate.message_date ? formatDateTime(candidate.message_date) : "не указано";
    case "sourceChat":
      return (
        <Stack spacing={0.25} sx={{ minWidth: 0 }}>
          <Typography variant="body2" noWrap>
            <FilterValueButton
              field="sourceChat"
              value={candidate.source_chat_title || candidate.source_chat_id || ""}
              label={candidate.source_chat_title || candidate.source_chat_id || ""}
              onFilterValue={onFilterValue}
            >
              {candidate.source_chat_title || candidate.source_chat_id || "не указано"}
            </FilterValueButton>
          </Typography>
          {candidate.source_input_ref && (
            <Typography variant="caption" color="text.secondary" noWrap>
              {candidate.source_input_ref}
            </Typography>
          )}
        </Stack>
      );
    case "sourceChatId":
      return (
        <FilterValueButton field="sourceChatId" value={candidate.source_chat_id ?? ""} label={candidate.source_chat_id ?? ""} onFilterValue={onFilterValue}>
          {candidate.source_chat_id ?? "не указано"}
        </FilterValueButton>
      );
    case "sourceInputRef":
      return (
        <FilterValueButton field="sourceInputRef" value={candidate.source_input_ref ?? ""} label={candidate.source_input_ref ?? ""} onFilterValue={onFilterValue}>
          {candidate.source_input_ref ?? "не указано"}
        </FilterValueButton>
      );
    case "sourceChatStatus":
      return (
        <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
          <FilterValueButton
            field="sourceChatStatus"
            value={candidate.source_chat_status ?? ""}
            label={candidate.source_chat_status ?? ""}
            onFilterValue={onFilterValue}
          >
            <Chip size="small" label={candidate.source_chat_status ?? "не указано"} variant="outlined" />
          </FilterValueButton>
          {candidate.source_chat_enabled !== undefined && candidate.source_chat_enabled !== null && (
            <Chip size="small" label={candidate.source_chat_enabled ? "enabled" : "disabled"} />
          )}
          {candidate.source_chat_last_error && <Chip size="small" color="error" label={candidate.source_chat_last_error} />}
        </Stack>
      );
    case "telegramMessageId":
      return (
        <FilterValueButton
          field="telegramMessageId"
          value={candidate.telegram_message_id?.toString() ?? ""}
          label={candidate.telegram_message_id?.toString() ?? ""}
          numeric
          onFilterValue={onFilterValue}
        >
          {candidate.telegram_message_id ?? "не указано"}
        </FilterValueButton>
      );
    case "telegramChatId":
      return (
        <FilterValueButton field="telegramChatId" value={candidate.telegram_chat_id ?? ""} label={candidate.telegram_chat_id ?? ""} onFilterValue={onFilterValue}>
          {candidate.telegram_chat_id ?? "не указано"}
        </FilterValueButton>
      );
    case "sender":
      return (
        <FilterValueButton
          field="sender"
          value={candidate.sender_username ? `@${candidate.sender_username}` : candidate.sender_id ?? ""}
          label={candidate.sender_username ? `@${candidate.sender_username}` : candidate.sender_id ?? ""}
          onFilterValue={onFilterValue}
        >
          {candidate.sender_username ? `@${candidate.sender_username}` : candidate.sender_id ?? "не указано"}
        </FilterValueButton>
      );
    case "messageId":
      return (
        <FilterValueButton field="messageId" value={candidate.message_id} label={candidate.message_id} onFilterValue={onFilterValue}>
          {candidate.message_id}
        </FilterValueButton>
      );
    case "score":
      return (
        <FilterValueButton field="score" value={String(candidate.score)} label={formatInteger(candidate.score)} numeric onFilterValue={onFilterValue}>
          {formatInteger(candidate.score)}
        </FilterValueButton>
      );
    case "temperature":
      return (
        <FilterValueButton field="temperature" value={candidate.temperature} label={candidateTemperatureLabel(candidate)} onFilterValue={onFilterValue}>
          {candidateTemperatureLabel(candidate)}
        </FilterValueButton>
      );
    case "reviewLane":
      return (
        <FilterValueButton field="reviewLane" value={candidate.review_lane} label={reviewLaneLabel(candidate.review_lane)} onFilterValue={onFilterValue}>
          <Chip size="small" label={reviewLaneLabel(candidate.review_lane)} variant="outlined" />
        </FilterValueButton>
      );
    case "autoLead":
      return formatBoolean(candidate.auto_is_lead ?? candidate.is_lead);
    case "effectiveLead":
      return formatBoolean(candidate.effective_is_lead ?? candidate.is_lead);
    case "leadStatusSource":
      return candidate.lead_status_source ?? "auto";
    case "reviewStatus":
      return (
        <FilterValueButton
          field="reviewStatus"
          value={candidate.review ? "reviewed" : "unreviewed"}
          label={candidate.review ? "С ревью" : "Без ревью"}
          onFilterValue={onFilterValue}
        >
          <ReviewStatusChip review={candidate.review ?? null} />
        </FilterValueButton>
      );
    case "llmSummary":
      return <CandidateLlmSummary value={candidate.llm ?? null} onFilterValue={onFilterValue} />;
    case "llmStatus":
      return (
        <FilterValueButton
          field="llmStatus"
          value={candidate.llm?.status ?? (candidate.llm?.processed ? "processed" : "not_processed")}
          label={candidate.llm?.status ?? (candidate.llm?.processed ? "processed" : "не обработано")}
          onFilterValue={onFilterValue}
        >
          {candidate.llm?.status ?? (candidate.llm?.processed ? "processed" : "не обработано")}
        </FilterValueButton>
      );
    case "llmVerdict":
      return (
        <FilterValueButton field="llmVerdict" value={candidate.llm?.verdict ?? ""} label={candidate.llm?.verdict ?? ""} onFilterValue={onFilterValue}>
          {candidate.llm?.verdict ?? "не указано"}
        </FilterValueButton>
      );
    case "llmConfidence":
      return (
        <FilterValueButton
          field="llmConfidence"
          value={typeof candidate.llm?.confidence === "number" ? candidate.llm.confidence.toFixed(2) : ""}
          label={typeof candidate.llm?.confidence === "number" ? candidate.llm.confidence.toFixed(2) : ""}
          numeric
          onFilterValue={onFilterValue}
        >
          {typeof candidate.llm?.confidence === "number" ? candidate.llm.confidence.toFixed(2) : "не указано"}
        </FilterValueButton>
      );
    case "llmRecommendation":
      return (
        <FilterValueButton field="llmRecommendation" value={candidate.llm?.recommendation ?? ""} label={candidate.llm?.recommendation ?? ""} onFilterValue={onFilterValue}>
          {candidate.llm?.recommendation ?? "не указано"}
        </FilterValueButton>
      );
    case "llmAgreement":
      return formatBoolean(candidate.llm?.agrees_with_rule_engine);
    case "llmModel":
      return (
        <FilterValueButton field="llmModel" value={candidate.llm?.model ?? ""} label={candidate.llm?.model ?? ""} onFilterValue={onFilterValue}>
          {candidate.llm?.model ?? "не указано"}
        </FilterValueButton>
      );
    case "llmRoute":
      return (
        <FilterValueButton field="llmRoute" value={candidate.llm?.route_id ?? ""} label={candidate.llm?.route_id ?? ""} onFilterValue={onFilterValue}>
          {candidate.llm?.route_id ?? "не указано"}
        </FilterValueButton>
      );
    case "llmAttempts":
      return (
        <FilterValueButton
          field="llmAttempts"
          value={typeof candidate.llm?.attempts === "number" ? String(candidate.llm.attempts) : ""}
          label={typeof candidate.llm?.attempts === "number" ? String(candidate.llm.attempts) : ""}
          numeric
          onFilterValue={onFilterValue}
        >
          {candidate.llm?.attempts ?? "не указано"}
        </FilterValueButton>
      );
    case "llmUpdatedAt":
      return candidate.llm?.updated_at ? formatDateTime(candidate.llm.updated_at) : "не указано";
    case "llmError":
      return candidate.llm?.error ?? (candidate.llm?.has_error ? "ошибка без текста" : "нет");
    case "text":
      return <span>{candidate.text}</span>;
    case "reasons":
      return <CandidateReasonChips candidate={candidate} onFilterValue={onFilterValue} />;
    case "solutionAreas":
      return <CategoryChips items={candidate.solution_areas} field="solutionAreas" onFilterValue={onFilterValue} />;
    case "customerSegments":
      return <CategoryChips items={candidate.customer_segments} field="customerSegments" onFilterValue={onFilterValue} />;
    case "domainSignals":
      return <CategoryChips items={candidate.domain_signals} field="domainSignals" onFilterValue={onFilterValue} />;
    case "intentSignals":
      return <CategoryChips items={candidate.intent_signals} />;
    case "noiseSignals":
      return <CategoryChips items={candidate.noise_signals} />;
    case "facts":
      return <CategoryChips items={candidate.facts} />;
    case "enrichmentJobId":
      return candidate.enrichment_job_id ?? "не указано";
    case "enrichmentStatus":
      return (
        <FilterValueButton field="enrichmentStatus" value={candidate.enrichment_status ?? ""} label={candidate.enrichment_status ?? ""} onFilterValue={onFilterValue}>
          {candidate.enrichment_status ?? "не указано"}
        </FilterValueButton>
      );
    case "enrichmentFinishedAt":
      return candidate.enrichment_finished_at ? formatDateTime(candidate.enrichment_finished_at) : "не указано";
    case "enrichmentError":
      return <JsonPreview value={candidate.enrichment_error} emptyLabel="нет" />;
    case "telegramUrl":
      return candidate.telegram_message_url ? (
        <MuiLink href={candidate.telegram_message_url} target="_blank" rel="noreferrer">
          Telegram
        </MuiLink>
      ) : (
        "нет"
      );
    case "appUrl":
      return candidate.app_message_url ? <MuiLink href={candidate.app_message_url}>App</MuiLink> : "нет";
    case "testingUrl":
      return candidate.testing_url ? (
        <MuiLink href={candidate.testing_url}>Проверка</MuiLink>
      ) : (
        <Button size="small" href={`/testing?message_id=${encodeURIComponent(candidate.message_id)}`}>
          Проверить
        </Button>
      );
    case "sourceAccountId":
      return candidate.source_account_id ?? "не указано";
    case "rawPayload":
      return <JsonPreview value={candidate.raw_payload} emptyLabel="нет" />;
    default:
      return null;
  }
}

export function candidateCellClass(key: CandidateColumnKey): string | undefined {
  if (key === "text") {
    return "candidate-text";
  }
  if (key === "reasons") {
    return "candidate-reasons";
  }
  if (key === "rawPayload" || key === "enrichmentError") {
    return "candidate-json-column";
  }
  return undefined;
}

function dateCellValue(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function labelList(items: Array<{ type?: string; key?: string; label?: string; text?: string }>, fallbackKey: "type" | "key") {
  return items.map((item) => item.label ?? item.text ?? item[fallbackKey] ?? "").filter(Boolean).join(", ");
}

function stringifyJson(value: unknown): string {
  if (!value || (typeof value === "object" && Object.keys(value as Record<string, unknown>).length === 0)) {
    return "";
  }
  return JSON.stringify(value);
}

function FilterValueButton({
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
  onFilterValue?: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
  children: ReactNode;
}) {
  const trimmed = value.trim();
  if (!trimmed || !onFilterValue) {
    return <>{children}</>;
  }
  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation();
    onFilterValue?.({ field, value: trimmed, label: label.trim() || trimmed, numeric }, event.currentTarget);
  }
  return (
    <button type="button" className="candidate-filter-value" aria-label={`Фильтровать значение: ${label.trim() || trimmed}`} onClick={handleClick}>
      {children}
    </button>
  );
}

function CandidateLlmSummary({
  value,
  onFilterValue
}: {
  value: AnalyticsCandidate["llm"] | null;
  onFilterValue?: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
}) {
  if (!value?.processed) {
    return <Chip size="small" label="LLM нет" variant="outlined" />;
  }
  const color: "default" | "error" | "success" =
    value.has_error || value.status === "failed" ? "error" : value.status === "completed" ? "success" : "default";
  return (
    <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
      <FilterValueButton field="llmStatus" value={value.status ?? "processed"} label={value.status ?? "processed"} onFilterValue={onFilterValue}>
        <Chip size="small" label={value.status ?? "processed"} color={color} />
      </FilterValueButton>
      {value.verdict && (
        <FilterValueButton field="llmVerdict" value={value.verdict} label={value.verdict} onFilterValue={onFilterValue}>
          <Chip size="small" label={value.verdict} variant="outlined" />
        </FilterValueButton>
      )}
      {typeof value.confidence === "number" && (
        <FilterValueButton field="llmConfidence" value={value.confidence.toFixed(2)} label={value.confidence.toFixed(2)} numeric onFilterValue={onFilterValue}>
          <Chip size="small" label={value.confidence.toFixed(2)} variant="outlined" />
        </FilterValueButton>
      )}
    </Stack>
  );
}

function CandidateReasonChips({
  candidate,
  onFilterValue
}: {
  candidate: AnalyticsCandidate;
  onFilterValue?: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
}) {
  return (
    <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
      {candidate.reasons.slice(0, 4).map((reason) => (
        <FilterValueButton
          key={`${candidate.message_id}-${reason.source}-${reason.key}`}
          field="reasons"
          value={reason.key}
          label={reason.label || reason.key}
          onFilterValue={onFilterValue}
        >
          <Chip
            size="small"
            label={`${reason.label || reason.key} ${formatWeight(reason.weight)}`}
          />
        </FilterValueButton>
      ))}
      {candidate.reasons.length > 4 && <Chip size="small" variant="outlined" label={`+${candidate.reasons.length - 4}`} />}
    </Stack>
  );
}

function CategoryChips({
  items,
  field,
  onFilterValue
}: {
  items: Array<{ type?: string; label?: string; text?: string }>;
  field?: CandidateColumnKey;
  onFilterValue?: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void;
}) {
  if (!items.length) {
    return "нет";
  }
  return (
    <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
      {items.slice(0, 5).map((item, index) => (
        <FilterValueButton
          key={`${item.type ?? item.label ?? item.text ?? "item"}-${index}`}
          field={field ?? "text"}
          value={item.type ?? item.text ?? item.label ?? ""}
          label={item.label ?? item.text ?? item.type ?? "item"}
          onFilterValue={field ? onFilterValue : undefined}
        >
          <Chip
            size="small"
            label={item.label ?? item.text ?? item.type ?? "item"}
            variant="outlined"
          />
        </FilterValueButton>
      ))}
      {items.length > 5 && <Chip size="small" label={`+${items.length - 5}`} />}
    </Stack>
  );
}

function JsonPreview({ value, emptyLabel }: { value: unknown; emptyLabel: string }) {
  if (!value || (typeof value === "object" && Object.keys(value as Record<string, unknown>).length === 0)) {
    return emptyLabel;
  }
  return (
    <Box component="pre" className="candidate-json-cell">
      {JSON.stringify(value)}
    </Box>
  );
}

function formatBoolean(value: boolean | null | undefined): string {
  if (value === true) {
    return "да";
  }
  if (value === false) {
    return "нет";
  }
  return "не указано";
}
