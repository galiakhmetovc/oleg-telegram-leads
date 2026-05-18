import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import {
  Box,
  Chip,
  Collapse,
  Divider,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Typography
} from "@mui/material";
import type { ReactNode } from "react";

import { Kpi, SectionTitle } from "./AnalyticsShared";
import { aggregateDetail, formatInteger, formatPercent } from "./analyticsFormat";
import type { AnalyticsAggregate, AnalyticsRun, AnalyticsSummary, AnalyticsSummaryBlockKey } from "./types";

export const collapsedSummaryBlocks: Record<AnalyticsSummaryBlockKey, boolean> = {
  score: false,
  signals: false,
  reasons: false,
  segments: false,
  lanes: false
};

export function AnalyticsOverviewPanel({
  summary,
  run,
  loading,
  expandedBlocks,
  onToggleBlock
}: {
  summary: AnalyticsSummary | null;
  run: AnalyticsRun | null;
  loading: boolean;
  expandedBlocks: Record<AnalyticsSummaryBlockKey, boolean>;
  onToggleBlock: (key: AnalyticsSummaryBlockKey) => void;
}) {
  const scoreBuckets = summary?.aggregates.score_bucket ?? [];
  const topSignals = (summary?.aggregates.signal ?? []).slice(0, 8);
  const topReasons = (summary?.aggregates.reason ?? []).slice(0, 8);
  const solutionAreas = (summary?.aggregates.solution_area ?? []).slice(0, 6);
  const customerSegments = (summary?.aggregates.customer_segment ?? []).slice(0, 6);
  const reviewLanes = summary?.aggregates.review_lane ?? [];

  return (
    <>
      <Box className="analytics-kpi-grid">
        <Kpi label="Сообщений" value={formatInteger(run?.processed ?? 0)} />
        <Kpi label="Кандидатов" value={formatInteger(run?.leads ?? 0)} />
        <Kpi label="Доля кандидатов" value={formatPercent(run?.candidate_rate ?? 0)} />
        <Kpi label="Ошибок" value={formatInteger(run?.failed ?? 0)} />
      </Box>

      {loading && <LinearProgress />}

      <Box className="analytics-grid">
        <CollapsibleAnalyticsSection
          title="Score"
          subtitle={`${formatInteger(run?.leads ?? 0)} кандидатов`}
          expanded={expandedBlocks.score}
          onToggle={() => onToggleBlock("score")}
        >
          <ScoreBars buckets={scoreBuckets} total={run?.leads ?? 0} />
        </CollapsibleAnalyticsSection>
        <CollapsibleAnalyticsSection
          title="Доменные сигналы"
          subtitle="Самые частые причины попадания в лиды"
          expanded={expandedBlocks.signals}
          onToggle={() => onToggleBlock("signals")}
        >
          <AggregateList items={topSignals} />
        </CollapsibleAnalyticsSection>
        <CollapsibleAnalyticsSection
          title="Причины score"
          subtitle="Что сильнее всего поднимает оценку"
          expanded={expandedBlocks.reasons}
          onToggle={() => onToggleBlock("reasons")}
        >
          <AggregateList items={topReasons} />
        </CollapsibleAnalyticsSection>
        <CollapsibleAnalyticsSection
          title="Сегменты"
          subtitle="Зоны решений и типы клиентов"
          expanded={expandedBlocks.segments}
          onToggle={() => onToggleBlock("segments")}
        >
          <Stack spacing={1.5}>
            <AggregateChips items={solutionAreas} />
            <Divider />
            <AggregateChips items={customerSegments} />
          </Stack>
        </CollapsibleAnalyticsSection>
        <CollapsibleAnalyticsSection
          title="Очереди разбора"
          subtitle="Очереди ручной проверки кандидатов"
          expanded={expandedBlocks.lanes}
          onToggle={() => onToggleBlock("lanes")}
        >
          <AggregateList items={reviewLanes} />
        </CollapsibleAnalyticsSection>
      </Box>
    </>
  );
}

function CollapsibleAnalyticsSection({
  title,
  subtitle,
  expanded,
  onToggle,
  children
}: {
  title: string;
  subtitle: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <Paper variant="outlined" className="analytics-section">
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", justifyContent: "space-between" }}>
          <SectionTitle title={title} subtitle={subtitle} />
          <IconButton
            aria-label={expanded ? `Скрыть блок ${title}` : `Показать блок ${title}`}
            size="small"
            onClick={onToggle}
          >
            {expanded ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
          </IconButton>
        </Stack>
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          {children}
        </Collapse>
      </Stack>
    </Paper>
  );
}

function ScoreBars({ buckets, total }: { buckets: AnalyticsAggregate[]; total: number }) {
  const maxCount = Math.max(...buckets.map((bucket) => bucket.count), 1);

  if (buckets.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет данных по score.
      </Typography>
    );
  }

  return (
    <Stack className="analytics-bars" spacing={1.25}>
      {buckets.map((bucket) => {
        const width = Math.max(4, (bucket.count / maxCount) * 100);
        const share = total > 0 ? `${(bucket.count * 100 / total).toFixed(1)}%` : "0.0%";
        return (
          <Box key={bucket.key} className="analytics-bar-row">
            <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between" }}>
              <Typography variant="body2">{bucket.label}</Typography>
              <Typography variant="body2" color="text.secondary">
                {formatInteger(bucket.count)} / {share}
              </Typography>
            </Stack>
            <Box className="analytics-bar-track">
              <Box className="analytics-bar-fill" sx={{ width: `${width}%` }} />
            </Box>
          </Box>
        );
      })}
    </Stack>
  );
}

function AggregateList({ items }: { items: AnalyticsAggregate[] }) {
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет данных.
      </Typography>
    );
  }

  return (
    <Stack spacing={1}>
      {items.map((item) => {
        const detail = aggregateDetail(item);
        return (
          <Box key={item.key} className="analytics-list-row">
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                {item.label || item.key}
              </Typography>
              {detail && (
                <Typography variant="caption" color="text.secondary" noWrap>
                  {detail}
                </Typography>
              )}
            </Box>
            <Chip size="small" label={formatInteger(item.count)} />
          </Box>
        );
      })}
    </Stack>
  );
}

function AggregateChips({ items }: { items: AnalyticsAggregate[] }) {
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Нет данных.
      </Typography>
    );
  }

  return (
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
      {items.map((item) => (
        <Chip key={item.key} label={`${item.label || item.key}: ${formatInteger(item.count)}`} size="small" />
      ))}
    </Stack>
  );
}
