import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import {
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Tooltip
} from "@mui/material";

import type { AnalyticsAggregate, AnalyticsReviewVerdict, CandidateFilters } from "./types";
import type { CandidateColumnConfig, CandidateColumnKey } from "./candidateQueueState";
import { candidateColumnLabels } from "./candidateQueueState";

type ReviewVerdictFilterOption = {
  value: AnalyticsReviewVerdict;
  label: string;
};

const reviewVerdictFilterOptions: ReviewVerdictFilterOption[] = [
  { value: "lead", label: "Лид" },
  { value: "not_lead", label: "Не лид" },
  { value: "uncertain", label: "Сомнительно" },
  { value: "noise", label: "Шум" }
];

export function CandidateFilterDialog({
  open,
  filters,
  signalOptions,
  reasonOptions,
  solutionAreaOptions,
  customerSegmentOptions,
  laneOptions,
  sourceChatOptions,
  onChange,
  onReset,
  onClose,
  onApply
}: {
  open: boolean;
  filters: CandidateFilters;
  signalOptions: AnalyticsAggregate[];
  reasonOptions: AnalyticsAggregate[];
  solutionAreaOptions: AnalyticsAggregate[];
  customerSegmentOptions: AnalyticsAggregate[];
  laneOptions: AnalyticsAggregate[];
  sourceChatOptions: AnalyticsAggregate[];
  onChange: (key: keyof CandidateFilters, value: string) => void;
  onReset: () => void;
  onClose: () => void;
  onApply: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Фильтры</DialogTitle>
      <DialogContent dividers>
        <Box className="candidate-filter-dialog-grid">
          <TextField
            select
            size="small"
            label="Тип источника"
            value={filters.sourceType}
            onChange={(event) => onChange("sourceType", event.target.value)}
          >
            <MenuItem value="">Любой</MenuItem>
            <MenuItem value="telegram">telegram</MenuItem>
            <MenuItem value="max">MAX</MenuItem>
          </TextField>
          <AggregateFilterSelect
            label="Канал"
            value={filters.sourceChatId}
            options={sourceChatOptions}
            onChange={(value) => onChange("sourceChatId", value)}
          />
          <TextField
            size="small"
            label="Текст"
            value={filters.q}
            onChange={(event) => onChange("q", event.target.value)}
          />
          <TextField
            size="small"
            label="Min score"
            value={filters.scoreMin}
            onChange={(event) => onChange("scoreMin", event.target.value)}
          />
          <TextField
            select
            size="small"
            label="Температура"
            value={filters.temperature}
            onChange={(event) => onChange("temperature", event.target.value)}
          >
            <MenuItem value="">Любая</MenuItem>
            <MenuItem value="hot">hot</MenuItem>
            <MenuItem value="warm">warm</MenuItem>
            <MenuItem value="cold">cold</MenuItem>
          </TextField>
          <AggregateFilterSelect
            label="Очередь"
            value={filters.lane}
            options={laneOptions}
            onChange={(value) => onChange("lane", value)}
          />
          <AggregateFilterSelect
            label="Сигнал"
            value={filters.signal}
            options={signalOptions}
            onChange={(value) => onChange("signal", value)}
          />
          <AggregateFilterSelect
            label="Причина score"
            value={filters.reason}
            options={reasonOptions}
            onChange={(value) => onChange("reason", value)}
          />
          <AggregateFilterSelect
            label="Зона решения"
            value={filters.solutionArea}
            options={solutionAreaOptions}
            onChange={(value) => onChange("solutionArea", value)}
          />
          <AggregateFilterSelect
            label="Сегмент клиента"
            value={filters.customerSegment}
            options={customerSegmentOptions}
            onChange={(value) => onChange("customerSegment", value)}
          />
          <TextField
            select
            size="small"
            label="Статус ревью"
            value={filters.reviewStatus}
            onChange={(event) => onChange("reviewStatus", event.target.value)}
          >
            <MenuItem value="">Любой</MenuItem>
            <MenuItem value="unreviewed">Без ревью</MenuItem>
            <MenuItem value="reviewed">С ревью</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Вердикт ревью"
            value={filters.verdict}
            onChange={(event) => onChange("verdict", event.target.value)}
          >
            <MenuItem value="">Любой</MenuItem>
            {reviewVerdictFilterOptions.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="LLM обработано"
            value={filters.llmProcessed}
            onChange={(event) => onChange("llmProcessed", event.target.value)}
          >
            <MenuItem value="">Любое</MenuItem>
            <MenuItem value="true">Да</MenuItem>
            <MenuItem value="false">Нет</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="LLM статус"
            value={filters.llmStatus}
            onChange={(event) => onChange("llmStatus", event.target.value)}
          >
            <MenuItem value="">Любой</MenuItem>
            <MenuItem value="queued">queued</MenuItem>
            <MenuItem value="running">running</MenuItem>
            <MenuItem value="completed">completed</MenuItem>
            <MenuItem value="failed">failed</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="LLM вердикт"
            value={filters.llmVerdict}
            onChange={(event) => onChange("llmVerdict", event.target.value)}
          >
            <MenuItem value="">Любой</MenuItem>
            <MenuItem value="lead">lead</MenuItem>
            <MenuItem value="not_lead">not_lead</MenuItem>
            <MenuItem value="uncertain">uncertain</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="LLM рекомендация"
            value={filters.llmRecommendation}
            onChange={(event) => onChange("llmRecommendation", event.target.value)}
          >
            <MenuItem value="">Любая</MenuItem>
            <MenuItem value="keep">keep</MenuItem>
            <MenuItem value="promote">promote</MenuItem>
            <MenuItem value="demote">demote</MenuItem>
            <MenuItem value="manual_review">manual_review</MenuItem>
          </TextField>
          <TextField
            size="small"
            label="LLM модель"
            value={filters.llmModel}
            onChange={(event) => onChange("llmModel", event.target.value)}
          />
          <TextField
            size="small"
            label="LLM route"
            value={filters.llmRoute}
            onChange={(event) => onChange("llmRoute", event.target.value)}
          />
          <TextField
            select
            size="small"
            label="LLM согласен с правилами"
            value={filters.llmAgreesWithRules}
            onChange={(event) => onChange("llmAgreesWithRules", event.target.value)}
          >
            <MenuItem value="">Любое</MenuItem>
            <MenuItem value="true">Да</MenuItem>
            <MenuItem value="false">Нет</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="LLM ошибка"
            value={filters.llmHasError}
            onChange={(event) => onChange("llmHasError", event.target.value)}
          >
            <MenuItem value="">Любая</MenuItem>
            <MenuItem value="true">Есть</MenuItem>
            <MenuItem value="false">Нет</MenuItem>
          </TextField>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onReset}>Сбросить</Button>
        <Button onClick={onClose}>Закрыть</Button>
        <Button variant="contained" startIcon={<FilterAltIcon />} onClick={onApply}>
          Применить
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function CandidateColumnDialog({
  open,
  columns,
  onToggle,
  onMove,
  onResize,
  onReset,
  onClose
}: {
  open: boolean;
  columns: CandidateColumnConfig[];
  onToggle: (key: CandidateColumnKey, visible: boolean) => void;
  onMove: (key: CandidateColumnKey, direction: -1 | 1) => void;
  onResize: (key: CandidateColumnKey, width: number) => void;
  onReset: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Поля очереди</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={0.75}>
          {columns.map((column, index) => (
            <Box key={column.key} className="candidate-column-editor-row">
              <FormControlLabel
                control={
                  <Checkbox
                    checked={column.visible}
                    onChange={(event) => onToggle(column.key, event.target.checked)}
                  />
                }
                label={candidateColumnLabels[column.key]}
              />
              <TextField
                size="small"
                type="number"
                label="Ширина"
                value={column.width}
                onChange={(event) => onResize(column.key, Number(event.target.value))}
                sx={{ width: 110 }}
              />
              <Tooltip title="Выше">
                <span>
                  <IconButton size="small" disabled={index === 0} onClick={() => onMove(column.key, -1)}>
                    <ArrowUpwardIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Ниже">
                <span>
                  <IconButton size="small" disabled={index === columns.length - 1} onClick={() => onMove(column.key, 1)}>
                    <ArrowDownwardIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Box>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onReset}>Сбросить</Button>
        <Button variant="contained" onClick={onClose}>
          Готово
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function AggregateFilterSelect({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: AnalyticsAggregate[];
  onChange: (value: string) => void;
}) {
  return (
    <TextField
      select
      size="small"
      label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={options.length === 0}
    >
      <MenuItem value="">Любой</MenuItem>
      {options.map((option) => (
        <MenuItem key={option.key} value={option.key}>
          {aggregateOptionLabel(option)}
        </MenuItem>
      ))}
    </TextField>
  );
}

function aggregateOptionLabel(item: AnalyticsAggregate) {
  return `${item.label || item.key} · ${new Intl.NumberFormat("ru-RU").format(item.count)}`;
}
