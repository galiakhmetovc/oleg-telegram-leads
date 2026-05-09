import {
  Box,
  Chip,
  Divider,
  Stack,
  Typography
} from "@mui/material";
import type { ReactNode } from "react";
import { useMemo } from "react";

export type EvidenceFlowSpan = {
  id?: string;
  text?: string;
  type: string;
  label?: string;
  source?: string;
  range?: { start: number; stop: number } | null;
};

export type EvidenceFlowReason = {
  source: string;
  key: string;
  label?: string;
  weight: number;
  matched_texts: string[];
};

export type EvidenceFlowCategory = {
  type: string;
  label?: string;
  matched_types?: string[];
};

export type EvidenceFlowReviewLane = {
  key: string;
  label?: string;
};

export type EvidenceFlowAssessment = {
  is_lead: boolean;
  score: number;
  temperature: string;
  solution_areas: EvidenceFlowCategory[];
  customer_segments: EvidenceFlowCategory[];
  reasons: EvidenceFlowReason[];
  review_lane?: EvidenceFlowReviewLane | null;
};

type EvidenceFlowProps<TTarget> = {
  facts: EvidenceFlowSpan[];
  domainSignals: EvidenceFlowSpan[];
  assessment?: EvidenceFlowAssessment | null;
  renderLink: (target: TTarget | null, children: ReactNode) => ReactNode;
  targetForSpan: (span: EvidenceFlowSpan, kind: "fact" | "signal") => TTarget | null;
  targetForReasonType: (reason: EvidenceFlowReason) => TTarget | null;
  targetForReasonWeight: (reason: EvidenceFlowReason) => TTarget | null;
  targetForCategory?: (kind: "solution_area" | "customer_segment", key: string) => TTarget | null;
  targetForReviewLane?: (key: string) => TTarget | null;
};

type EvidenceFlowRow = {
  id: string;
  fragments: string[];
  sourceFacts: EvidenceFlowSpan[];
  facts: EvidenceFlowSpan[];
  signals: EvidenceFlowSpan[];
  reason?: EvidenceFlowReason;
};

export function EvidenceFlow<TTarget>({
  facts,
  domainSignals,
  assessment,
  renderLink,
  targetForSpan,
  targetForReasonType,
  targetForReasonWeight,
  targetForCategory,
  targetForReviewLane
}: EvidenceFlowProps<TTarget>) {
  const rows = useMemo(
    () => buildEvidenceFlowRows(facts, domainSignals, assessment?.reasons ?? []),
    [facts, domainSignals, assessment?.reasons]
  );

  if (rows.length === 0 && !assessment) {
    return null;
  }

  return (
    <Box className="evidence-flow" aria-label="Визуальная цепочка анализа">
      <Stack spacing={1.5}>
        <Box sx={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: 1, justifyContent: "space-between" }}>
          <Box>
            <Typography variant="subtitle2">Визуальная цепочка анализа</Typography>
            <Typography variant="caption" color="text.secondary">
              Как фрагменты текста проходят через словари, факты, доменные сигналы и оценку лида.
            </Typography>
          </Box>
          {assessment && (
            <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
              <Chip size="small" label={`${assessment.score} баллов`} color={assessment.is_lead ? "primary" : "default"} />
              <Chip size="small" label={temperatureLabel(assessment)} variant="outlined" />
              {assessment.review_lane &&
                renderLink(
                  targetForReviewLane?.(assessment.review_lane.key) ?? null,
                  <Chip size="small" label={assessment.review_lane.label ?? assessment.review_lane.key} variant="outlined" />
                )}
            </Stack>
          )}
        </Box>

        <Box className="evidence-flow-table">
          <Box className="evidence-flow-row evidence-flow-header-row">
            <Typography variant="caption">Фрагмент текста</Typography>
            <Typography variant="caption">Словарь / правило</Typography>
            <Typography variant="caption">Факт</Typography>
            <Typography variant="caption">Сигнал</Typography>
            <Typography variant="caption">Вклад в score</Typography>
          </Box>
          {rows.map((row) => (
            <Box key={row.id} className="evidence-flow-row">
              <EvidenceFlowCell label="Фрагмент текста">
                <FlowChipList
                  items={row.fragments.map((fragment) => ({ id: fragment, label: fragment }))}
                  emptyText="Нет явного фрагмента"
                />
              </EvidenceFlowCell>
              <EvidenceFlowCell label="Словарь / правило">
                <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                  {sourceNodes(row).map((node) => (
                    <Box key={node.id} component="span">
                      {renderLink(
                        node.targetKind === "signal"
                          ? targetForSpan(node.span, "signal")
                          : targetForSpan(node.span, "fact"),
                        <Chip size="small" label={node.label} variant="outlined" />
                      )}
                    </Box>
                  ))}
                  {sourceNodes(row).length === 0 && (
                    <Typography variant="caption" color="text.secondary">
                      Не связано
                    </Typography>
                  )}
                </Stack>
              </EvidenceFlowCell>
              <EvidenceFlowCell label="Факт">
                <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                  {row.facts.map((fact) => (
                    <Box key={spanIdentity(fact)} component="span">
                      {renderLink(targetForSpan(fact, "fact"), <Chip size="small" label={spanLabel(fact)} />)}
                    </Box>
                  ))}
                  {row.facts.length === 0 && (
                    <Typography variant="caption" color="text.secondary">
                      Нет факта
                    </Typography>
                  )}
                </Stack>
              </EvidenceFlowCell>
              <EvidenceFlowCell label="Сигнал">
                <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                  {row.signals.map((signal) => (
                    <Box key={spanIdentity(signal)} component="span">
                      {renderLink(
                        targetForSpan(signal, "signal"),
                        <Chip
                          size="small"
                          label={spanLabel(signal)}
                          color={signal.source === "fact_dependency" ? "primary" : "default"}
                          variant={signal.source === "fact_dependency" ? "filled" : "outlined"}
                        />
                      )}
                    </Box>
                  ))}
                  {row.signals.length === 0 && (
                    <Typography variant="caption" color="text.secondary">
                      Нет сигнала
                    </Typography>
                  )}
                </Stack>
              </EvidenceFlowCell>
              <EvidenceFlowCell label="Вклад в score">
                {row.reason ? (
                  <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                    {renderLink(
                      targetForReasonWeight(row.reason),
                      <Chip size="small" label={formatSignedWeight(row.reason.weight)} color={row.reason.weight < 0 ? "warning" : "success"} />
                    )}
                    {renderLink(
                      targetForReasonType(row.reason),
                      <Typography component="span" variant="caption">
                        {row.reason.label ?? row.reason.key}
                      </Typography>
                    )}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    Не влияет напрямую
                  </Typography>
                )}
              </EvidenceFlowCell>
            </Box>
          ))}
        </Box>

        {assessment && (
          <>
            <Divider />
            <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
              {assessment.solution_areas.map((item) => (
                <Box key={`area-${item.type}`} component="span">
                  {renderLink(
                    targetForCategory?.("solution_area", item.type) ?? null,
                    <Chip size="small" label={`Направление: ${item.label ?? item.type}`} variant="outlined" />
                  )}
                </Box>
              ))}
              {assessment.customer_segments.map((item) => (
                <Box key={`segment-${item.type}`} component="span">
                  {renderLink(
                    targetForCategory?.("customer_segment", item.type) ?? null,
                    <Chip size="small" label={`Сегмент: ${item.label ?? item.type}`} variant="outlined" />
                  )}
                </Box>
              ))}
            </Stack>
          </>
        )}
      </Stack>
    </Box>
  );
}

function EvidenceFlowCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box className="evidence-flow-cell">
      <Typography className="evidence-flow-cell-label" variant="caption" color="text.secondary">
        {label}
      </Typography>
      {children}
    </Box>
  );
}

function FlowChipList({
  items,
  emptyText
}: {
  items: Array<{ id: string; label: string }>;
  emptyText: string;
}) {
  if (items.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary">
        {emptyText}
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
      {items.map((item) => (
        <Chip key={item.id} size="small" label={item.label} variant="outlined" />
      ))}
    </Stack>
  );
}

function buildEvidenceFlowRows(
  facts: EvidenceFlowSpan[],
  domainSignals: EvidenceFlowSpan[],
  reasons: EvidenceFlowReason[]
): EvidenceFlowRow[] {
  const rows: EvidenceFlowRow[] = [];
  const usedFacts = new Set<string>();
  const usedSignals = new Set<string>();

  for (const reason of reasons) {
    const matchedSignals =
      reason.source === "domain_signal"
        ? domainSignals.filter((signal) => signal.type === reason.key && reasonMatchesSpan(reason, signal))
        : [];
    const matchedFacts =
      reason.source === "fact"
        ? facts.filter((fact) => fact.type === reason.key && reasonMatchesSpan(reason, fact))
        : facts.filter((fact) => matchedSignals.some((signal) => spansReferToSameText(fact, signal)));
    const fragments = uniqueStrings([
      ...reason.matched_texts,
      ...matchedSignals.map((signal) => signal.text ?? ""),
      ...matchedFacts.map((fact) => fact.text ?? "")
    ]);
    for (const fact of matchedFacts) {
      usedFacts.add(spanIdentity(fact));
    }
    for (const signal of matchedSignals) {
      usedSignals.add(spanIdentity(signal));
    }
    rows.push({
      id: `reason-${reason.source}-${reason.key}-${rows.length}`,
      fragments,
      sourceFacts: matchedFacts,
      facts: matchedFacts,
      signals: matchedSignals,
      reason
    });
  }

  for (const signal of domainSignals) {
    if (usedSignals.has(spanIdentity(signal))) {
      continue;
    }
    const matchedFacts = facts.filter((fact) => spansReferToSameText(fact, signal));
    for (const fact of matchedFacts) {
      usedFacts.add(spanIdentity(fact));
    }
    rows.push({
      id: `signal-${spanIdentity(signal)}`,
      fragments: uniqueStrings([signal.text ?? "", ...matchedFacts.map((fact) => fact.text ?? "")]),
      sourceFacts: matchedFacts,
      facts: matchedFacts,
      signals: [signal]
    });
  }

  for (const fact of facts) {
    if (usedFacts.has(spanIdentity(fact))) {
      continue;
    }
    rows.push({
      id: `fact-${spanIdentity(fact)}`,
      fragments: uniqueStrings([fact.text ?? ""]),
      sourceFacts: [fact],
      facts: [fact],
      signals: []
    });
  }

  return rows;
}

function reasonMatchesSpan(reason: EvidenceFlowReason, span: EvidenceFlowSpan): boolean {
  if (reason.matched_texts.length === 0) {
    return true;
  }
  const spanText = normalizeText(span.text ?? "");
  return reason.matched_texts.some((text) => {
    const normalized = normalizeText(text);
    return spanText === normalized || spanText.includes(normalized) || normalized.includes(spanText);
  });
}

function spansReferToSameText(left: EvidenceFlowSpan, right: EvidenceFlowSpan): boolean {
  if (left.range && right.range && left.range.start === right.range.start && left.range.stop === right.range.stop) {
    return true;
  }
  const leftText = normalizeText(left.text ?? "");
  const rightText = normalizeText(right.text ?? "");
  return Boolean(leftText && rightText && (leftText === rightText || leftText.includes(rightText) || rightText.includes(leftText)));
}

function sourceNodes(row: EvidenceFlowRow): Array<{
  id: string;
  label: string;
  span: EvidenceFlowSpan;
  targetKind: "fact" | "signal";
}> {
  const nodes: Array<{ id: string; label: string; span: EvidenceFlowSpan; targetKind: "fact" | "signal" }> = [];
  const seen = new Set<string>();
  for (const fact of row.sourceFacts) {
    const prefix = fact.source === "alias_catalog" ? "Словарь" : "Правило факта";
    const id = `fact-source-${spanIdentity(fact)}`;
    if (!seen.has(id)) {
      seen.add(id);
      nodes.push({ id, label: `${prefix}: ${spanLabel(fact)}`, span: fact, targetKind: "fact" });
    }
  }
  if (nodes.length === 0) {
    for (const signal of row.signals) {
      const prefix = signal.source === "fact_dependency" ? "Зависимость от факта" : "Правило сигнала";
      const id = `signal-source-${spanIdentity(signal)}`;
      if (!seen.has(id)) {
        seen.add(id);
        nodes.push({ id, label: `${prefix}: ${spanLabel(signal)}`, span: signal, targetKind: "signal" });
      }
    }
  }
  return nodes;
}

function spanIdentity(span: EvidenceFlowSpan): string {
  return [
    span.id ?? "",
    span.type,
    span.text ?? "",
    span.range?.start ?? "",
    span.range?.stop ?? "",
    span.source ?? ""
  ].join("|");
}

function spanLabel(span: EvidenceFlowSpan): string {
  return span.label || span.type;
}

function normalizeText(text: string): string {
  return text.trim().toLocaleLowerCase("ru-RU");
}

function uniqueStrings(values: string[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const trimmed = value.trim();
    const key = normalizeText(trimmed);
    if (!trimmed || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(trimmed);
  }
  return result;
}

function formatSignedWeight(value: number): string {
  return value >= 0 ? `+${value}` : String(value);
}

function temperatureLabel(assessment: EvidenceFlowAssessment): string {
  if (!assessment.is_lead) {
    return "Не лид";
  }
  if (assessment.temperature === "hot") {
    return "Горячий лид";
  }
  if (assessment.temperature === "warm") {
    return "Теплый лид";
  }
  return assessment.temperature || "Лид";
}
