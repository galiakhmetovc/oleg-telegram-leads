import {
  Box,
  Chip,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography
} from "@mui/material";
import { useMemo } from "react";
import type { ReactNode } from "react";
import type {
  AliasCatalogName,
  AnalyticsCandidate,
  AnalyticsCategory,
  AnalyticsReason,
  AnalyticsReviewVerdict,
  AnalyticsSettingsLink,
  AnalyticsSettingsTarget,
  AnalyticsSpan,
  SettingReference
} from "./types";

const openSettingsTargetEvent = "pur-open-settings-target";
const reviewVerdictOptions: Array<{
  value: AnalyticsReviewVerdict;
  label: string;
  color: "primary" | "secondary" | "error" | "info" | "success" | "warning";
}> = [
  { value: "lead", label: "Лид", color: "success" },
  { value: "not_lead", label: "Не лид", color: "error" },
  { value: "uncertain", label: "Сомнительно", color: "warning" },
  { value: "noise", label: "Шум", color: "secondary" }
];
const reviewLaneFallbackLabels: Record<string, string> = {
  direct_pur_lead: "Прямой лид ПУР",
  domain_interest: "Доменный интерес",
  pur_design_context: "Проектный контекст ПУР",
  research_warm: "Исследование / теплый интерес",
  noise: "Шум",
  none: "Без очереди"
};

export function CandidateDetails({ candidate }: { candidate: AnalyticsCandidate }) {
  return (
    <Box className="candidate-detail">
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Chip label={candidateTemperatureLabel(candidate)} color={candidateTemperatureColor(candidate)} />
          <Chip label={`${candidate.score} баллов`} variant="outlined" />
          <AnalyticsSettingLink target={{ kind: "review_lane", key: candidate.review_lane }}>
            <Chip label={reviewLaneLabel(candidate.review_lane)} variant="outlined" />
          </AnalyticsSettingLink>
          <ReviewStatusChip review={candidate.review ?? null} />
          <Typography variant="body2" color="text.secondary">
            {candidate.source_chat_title ? `${candidate.source_chat_title}, ` : ""}
            сообщение {candidate.telegram_message_id ?? candidate.message_id}
            {candidate.received_at ? `, принято ${formatDateTime(candidate.received_at)}` : ""}
          </Typography>
        </Stack>

        <Stack spacing={1}>
          <Typography variant="subtitle2">Раскрашенное сообщение</Typography>
          <AnnotatedCandidateText candidate={candidate} />
        </Stack>

        <Box className="candidate-detail-grid">
          <Stack spacing={1.25}>
            <CandidateCategoryGroup
              title="Направления"
              items={candidate.solution_areas}
              targetKind="solution_area"
              candidate={candidate}
            />
            <CandidateCategoryGroup
              title="Сегменты"
              items={candidate.customer_segments}
              targetKind="customer_segment"
              candidate={candidate}
            />
            <CandidateCategoryGroup title="Намерения" items={candidate.intent_signals} candidate={candidate} />
            <CandidateCategoryGroup title="Шум" items={candidate.noise_signals} color="warning" candidate={candidate} />
          </Stack>
          <Stack spacing={1.25}>
            <CandidateSpanGroup title="Доменные сигналы" items={candidate.domain_signals} kind="signals" />
            <CandidateSpanGroup title="Факты" items={candidate.facts} kind="facts" />
          </Stack>
        </Box>

        <CandidateReasonTable candidate={candidate} />
      </Stack>
    </Box>
  );
}

export function ReviewReasonSummary({ candidate }: { candidate: AnalyticsCandidate }) {
  const topReasons = candidate.reasons.slice(0, 5);
  const hasNoise = candidate.noise_signals.length > 0;
  if (topReasons.length === 0 && !hasNoise) {
    return (
      <Typography variant="body2" color="text.secondary">
        Автоматический разбор не вернул причин score или шумовых сигналов.
      </Typography>
    );
  }
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
        <Chip label={candidateTemperatureLabel(candidate)} color={candidateTemperatureColor(candidate)} />
        <Chip label={`${candidate.score} баллов`} variant="outlined" />
        <Chip label={reviewLaneLabel(candidate.review_lane)} variant="outlined" />
      </Stack>
      {hasNoise && (
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          {candidate.noise_signals.map((signal) => (
            <Chip
              key={`noise-${signal.type}`}
              size="small"
              color="warning"
              label={`Шум: ${signal.label || signal.type}`}
            />
          ))}
        </Stack>
      )}
      <Stack spacing={0.75}>
        {topReasons.map((reason) => (
          <Box key={`${reason.source}-${reason.key}`} className="review-summary-reason">
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {formatWeight(reason.weight)} {reason.label || reason.key}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {reason.matched_texts.slice(0, 3).join(", ") || reason.source}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}

export function ReviewStatusChip({
  review
}: {
  review: AnalyticsCandidate["review"];
}) {
  if (!review) {
    return <Chip size="small" label="Без ревью" variant="outlined" />;
  }
  const option = reviewVerdictOptions.find((item) => item.value === review.verdict);
  return (
    <Chip
      size="small"
      label={option?.label ?? "С ревью"}
      color={option?.color ?? "default"}
      variant={option ? "filled" : "outlined"}
    />
  );
}

function AnnotatedCandidateText({ candidate }: { candidate: AnalyticsCandidate }) {
  const highlights = useMemo(() => collectCandidateHighlights(candidate), [candidate]);
  const parts: ReactNode[] = [];
  let cursor = 0;

  for (const highlight of highlights) {
    if (highlight.start > cursor) {
      parts.push(<span key={`text-${cursor}`}>{candidate.text.slice(cursor, highlight.start)}</span>);
    }
    parts.push(
      <mark
        key={`${highlight.type}-${highlight.start}-${highlight.stop}`}
        className="annotation"
        style={{
          borderColor: highlight.color,
          backgroundColor: `${highlight.color}1a`
        }}
        title={`${highlight.label}: ${highlight.source}`}
      >
        {candidate.text.slice(highlight.start, highlight.stop)}
      </mark>
    );
    cursor = highlight.stop;
  }

  if (cursor < candidate.text.length) {
    parts.push(<span key={`text-${cursor}`}>{candidate.text.slice(cursor)}</span>);
  }

  return (
    <Box className="annotated-text analytics-annotated-text">
      <Typography component="div" variant="body2">
        {parts.length > 0 ? parts : candidate.text}
      </Typography>
    </Box>
  );
}

type CandidateHighlight = {
  start: number;
  stop: number;
  type: string;
  label: string;
  source: string;
  color: string;
};

function collectCandidateHighlights(candidate: AnalyticsCandidate): CandidateHighlight[] {
  const candidates = [
    ...candidate.domain_signals.map((span) => ({ ...span, fallbackSource: "domain_signal", fallbackColor: "#0b57d0" })),
    ...candidate.facts.map((span) => ({ ...span, fallbackSource: "fact", fallbackColor: "#7b1fa2" }))
  ];
  const highlights: CandidateHighlight[] = [];
  const seen = new Set<string>();
  const codeUnitOffsets = codePointToCodeUnitOffsets(candidate.text);

  for (const span of candidates) {
    const ranges = span.range
      ? [[
          codePointOffsetToCodeUnit(span.range.start, codeUnitOffsets),
          codePointOffsetToCodeUnit(span.range.stop, codeUnitOffsets)
        ] as [number, number]]
      : findTextOccurrences(candidate.text, span.text?.trim() ?? "");
    for (const [start, stop] of ranges) {
      if (stop <= start) {
        continue;
      }
      const key = `${span.type}-${start}-${stop}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      highlights.push({
        start,
        stop,
        type: span.type,
        label: span.label || span.type,
        source: span.source || span.fallbackSource,
        color: span.color || span.fallbackColor
      });
    }
  }

  const sorted = highlights.sort((left, right) => left.start - right.start || right.stop - left.stop);
  const accepted: CandidateHighlight[] = [];
  let cursor = -1;
  for (const highlight of sorted) {
    if (highlight.start >= cursor) {
      accepted.push(highlight);
      cursor = highlight.stop;
    }
  }
  return accepted;
}

function findTextOccurrences(text: string, phrase: string): Array<[number, number]> {
  if (!phrase) {
    return [];
  }
  const haystack = text.toLocaleLowerCase("ru-RU");
  const needle = phrase.toLocaleLowerCase("ru-RU");
  const occurrences: Array<[number, number]> = [];
  let start = haystack.indexOf(needle);
  while (start !== -1) {
    occurrences.push([start, start + phrase.length]);
    start = haystack.indexOf(needle, start + Math.max(needle.length, 1));
  }
  return occurrences;
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

function CandidateCategoryGroup({
  title,
  items,
  color = "default",
  targetKind,
  candidate
}: {
  title: string;
  items: AnalyticsCategory[];
  color?: "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning";
  targetKind?: "solution_area" | "customer_segment";
  candidate: AnalyticsCandidate;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">{title}</Typography>
      <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
        {items.map((item) => {
          const target = targetKind ? categoryTarget(targetKind, item.type) : matchedTypeTarget(item.type, candidate);
          return (
            <AnalyticsSettingLink key={`${title}-${item.type}`} target={target}>
              <Chip
                label={item.label || item.type}
                size="small"
                color={color}
                variant={color === "default" ? "outlined" : "filled"}
              />
            </AnalyticsSettingLink>
          );
        })}
      </Stack>
      {items.some((item) => (item.matched_types ?? []).length > 0) && (
        <Stack spacing={0.5}>
          {items.map((item) =>
            (item.matched_types ?? []).length > 0 ? (
              <Box key={`${title}-${item.type}-matched`} sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                <Typography variant="caption" color="text.secondary">
                  {item.label || item.type}:
                </Typography>
                <AnalyticsInlineSettingsLinks
                  links={(item.matched_types ?? []).map((type) => ({
                    label: typeLabelFromCandidate(type, candidate),
                    target: matchedTypeTarget(type, candidate)
                  }))}
                />
              </Box>
            ) : null
          )}
        </Stack>
      )}
    </Stack>
  );
}

function CandidateSpanGroup({
  title,
  items,
  kind
}: {
  title: string;
  items: AnalyticsSpan[];
  kind: "facts" | "signals";
}) {
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">{title}</Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Не найдено.
        </Typography>
      ) : (
        <Stack spacing={0.75}>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
            {items.map((item, index) => (
              <AnalyticsSettingLink
                key={`${title}-${item.type}-${item.text ?? ""}-${index}`}
                target={spanPrimaryTarget(item, kind)}
              >
                <Chip
                  label={`${item.label || item.type}${item.text ? `: ${item.text}` : ""}`}
                  size="small"
                  variant="outlined"
                />
              </AnalyticsSettingLink>
            ))}
          </Stack>
          {items.map((item, index) => (
            <AnalyticsInlineSettingsLinks
              key={`${title}-${item.type}-${item.text ?? ""}-${index}-settings`}
              links={spanSettingLinks(item, kind)}
            />
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function CandidateReasonTable({ candidate }: { candidate: AnalyticsCandidate }) {
  const reasons = candidate.reasons;
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">Причины score</Typography>
      {reasons.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Причин score нет.
        </Typography>
      ) : (
        <TableContainer>
          <Table size="small">
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
              {reasons.map((reason) => (
                <TableRow key={`${reason.source}-${reason.key}`}>
                  <TableCell>
                    <AnalyticsSettingLink target={reasonTypeTarget(reason, candidate)}>
                      {reason.label || reason.key}
                    </AnalyticsSettingLink>
                  </TableCell>
                  <TableCell>{reasonSourceLabel(reason.source)}</TableCell>
                  <TableCell>
                    <AnalyticsSettingLink target={reasonWeightTarget(reason)}>
                      {formatWeight(reason.weight)}
                    </AnalyticsSettingLink>
                  </TableCell>
                  <TableCell>{reason.matched_texts.join(", ")}</TableCell>
                  <TableCell>
                    <AnalyticsInlineSettingsLinks
                      links={[
                        { label: "тип", target: reasonTypeTarget(reason, candidate) },
                        { label: "вес", target: reasonWeightTarget(reason) }
                      ]}
                    />
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

function AnalyticsInlineSettingsLinks({ links }: { links: AnalyticsSettingsLink[] }) {
  const visibleLinks = links.filter((link) => link.label !== "");
  if (visibleLinks.length === 0) {
    return null;
  }
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
      {visibleLinks.map((link, index) => (
        <AnalyticsSettingLink key={`${analyticsSettingsTargetHash(link.target)}-${String(link.label)}-${index}`} target={link.target}>
          <Typography component="span" variant="caption">
            {link.label}
          </Typography>
        </AnalyticsSettingLink>
      ))}
    </Box>
  );
}

function AnalyticsSettingLink({ target, children }: { target: AnalyticsSettingsTarget | null; children: ReactNode }) {
  if (!target) {
    return <>{children}</>;
  }
  const href = analyticsSettingsTargetHash(target);
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

function spanPrimaryTarget(item: AnalyticsSpan, kind: "facts" | "signals"): AnalyticsSettingsTarget | null {
  const aliasTarget = analyticsSettingsTargetFromRef(item.settings_refs?.find((ref) => ref.section === "aliases"));
  const signalTarget = analyticsSettingsTargetFromRef(item.settings_refs?.find((ref) => ref.section === "signals"));
  const factTarget = analyticsSettingsTargetFromRef(item.settings_refs?.find((ref) => ref.section === "facts"));
  if (kind === "signals") {
    return signalTarget ?? { kind: "signal", key: item.type };
  }
  if (item.source === "alias_catalog") {
    return aliasTarget ?? { kind: "lead_fact_weight", key: item.type };
  }
  return factTarget ?? { kind: "fact", key: item.type };
}

function spanSettingLinks(item: AnalyticsSpan, kind: "facts" | "signals"): AnalyticsSettingsLink[] {
  const links = (item.settings_refs ?? [])
    .map((ref) => ({
      label: ref.label,
      target: analyticsSettingsTargetFromRef(ref)
    }))
    .filter((link) => link.target);
  const primaryTarget = spanPrimaryTarget(item, kind);
  if (links.length === 0 && primaryTarget) {
    return [{ label: item.label ?? item.type, target: primaryTarget }];
  }
  return links;
}

function analyticsSettingsTargetFromRef(ref: SettingReference | undefined): AnalyticsSettingsTarget | null {
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

function reasonTypeTarget(reason: AnalyticsReason, candidate: AnalyticsCandidate): AnalyticsSettingsTarget | null {
  if (reason.source === "domain_signal") {
    return { kind: "signal", key: reason.key };
  }
  if (reason.source === "fact") {
    const hasFactRuleMatch = candidate.facts.some((fact) => fact.type === reason.key && fact.source === "yargy");
    return hasFactRuleMatch ? { kind: "fact", key: reason.key } : { kind: "lead_fact_weight", key: reason.key };
  }
  return null;
}

function reasonWeightTarget(reason: AnalyticsReason): AnalyticsSettingsTarget | null {
  if (reason.source === "score_cap") {
    return null;
  }
  return reason.source === "domain_signal"
    ? { kind: "lead_signal_weight", key: reason.key }
    : { kind: "lead_fact_weight", key: reason.key };
}

function reasonSourceLabel(source: string): string {
  if (source === "domain_signal") {
    return "Доменный сигнал";
  }
  if (source === "fact") {
    return "Факт";
  }
  if (source === "score_cap") {
    return "Ограничитель score";
  }
  return source;
}

function categoryTarget(kind: "solution_area" | "customer_segment", key: string): AnalyticsSettingsTarget {
  return kind === "solution_area"
    ? { kind: "solution_area", key }
    : { kind: "customer_segment", key };
}

function matchedTypeTarget(type: string, candidate: AnalyticsCandidate): AnalyticsSettingsTarget | null {
  if (candidate.domain_signals.some((signal) => signal.type === type)) {
    return { kind: "signal", key: type };
  }
  if (candidate.facts.some((fact) => fact.type === type && fact.source === "yargy")) {
    return { kind: "fact", key: type };
  }
  if (candidate.reasons.some((reason) => reason.source === "fact" && reason.key === type)) {
    return { kind: "lead_fact_weight", key: type };
  }
  if (candidate.reasons.some((reason) => reason.source === "domain_signal" && reason.key === type)) {
    return { kind: "lead_signal_weight", key: type };
  }
  return null;
}

function typeLabelFromCandidate(type: string, candidate: AnalyticsCandidate): string {
  const signal = candidate.domain_signals.find((item) => item.type === type);
  if (signal) {
    return signal.label || signal.type;
  }
  const fact = candidate.facts.find((item) => item.type === type);
  if (fact) {
    return fact.label || fact.type;
  }
  const reason = candidate.reasons.find((item) => item.key === type);
  return reason?.label || type;
}

function analyticsSettingsTargetHash(target: AnalyticsSettingsTarget | null): string {
  if (!target) {
    return "";
  }
  if (target.kind === "signal") {
    return `#/settings/signals/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "fact") {
    return `#/settings/facts/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "alias") {
    return `#/settings/aliases/${target.catalog}/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "lead_signal_weight") {
    return `#/settings/lead-scoring/signal-weight/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "lead_fact_weight") {
    return `#/settings/lead-scoring/fact-weight/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "solution_area") {
    return `#/settings/lead-scoring/solution-area/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "customer_segment") {
    return `#/settings/lead-scoring/customer-segment/${encodeURIComponent(target.key)}`;
  }
  return `#/settings/lead-scoring/review-lane/${encodeURIComponent(target.key)}`;
}

function isAliasCatalogName(value: string | null | undefined): value is AliasCatalogName {
  return value === "vendors" || value === "protocols" || value === "devices" || value === "software";
}

export function candidateTemperatureLabel(candidate: AnalyticsCandidate) {
  const verdict = candidate.review?.verdict;
  if (verdict === "noise") {
    return "Шум (ревью)";
  }
  if (verdict === "not_lead") {
    return "Не лид (ревью)";
  }
  if (verdict === "lead") {
    return "Лид (ревью)";
  }
  if (!candidateEffectiveIsLead(candidate)) {
    return "Не лид";
  }
  if (candidate.temperature === "hot") {
    return "Горячий лид";
  }
  if (candidate.temperature === "warm") {
    return "Теплый лид";
  }
  if (candidate.temperature === "cold") {
    return "Холодный лид";
  }
  return "Кандидат";
}

export function candidateTemperatureColor(
  candidate: AnalyticsCandidate
): "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning" {
  const verdict = candidate.review?.verdict;
  if (verdict === "noise") {
    return "secondary";
  }
  if (verdict === "not_lead") {
    return "error";
  }
  if (verdict === "lead") {
    return "success";
  }
  if (!candidateEffectiveIsLead(candidate)) {
    return "default";
  }
  if (candidate.temperature === "hot") {
    return "error";
  }
  if (candidate.temperature === "warm") {
    return "warning";
  }
  if (candidate.temperature === "cold") {
    return "success";
  }
  return "default";
}

function candidateEffectiveIsLead(candidate: AnalyticsCandidate): boolean {
  if (typeof candidate.effective_is_lead === "boolean") {
    return candidate.effective_is_lead;
  }
  const verdict = candidate.review?.verdict;
  if (verdict === "lead") {
    return true;
  }
  if (verdict === "not_lead" || verdict === "noise") {
    return false;
  }
  return candidate.is_lead ?? false;
}

export function reviewLaneLabel(lane: string): string {
  return reviewLaneFallbackLabels[lane] ?? lane;
}

export function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

export function formatWeight(value: number) {
  return value >= 0 ? `+${value}` : String(value);
}
