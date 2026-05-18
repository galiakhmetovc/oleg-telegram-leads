import { Box, CircularProgress, Stack, Typography } from "@mui/material";
import {
  type GridColDef,
  type GridColumnOrderChangeParams,
  type GridColumnResizeParams,
  type GridColumnVisibilityModel,
  type GridFilterModel,
  type GridPaginationModel,
  type GridRenderCellParams,
  type GridRowParams,
  type GridSortModel
} from "@mui/x-data-grid";
import { useEffect, useMemo, useRef, useState } from "react";

import { CandidateColumnValue, candidateCellClass, candidateColumnGridValue } from "./CandidateQueueCells";
import { CandidateQueueSidePage } from "./CandidateQueueSidePage";
import { CandidateValueFilterMenu } from "./CandidateValueFilterMenu";
import { formatInteger } from "./analyticsFormat";
import type { AnalyticsCandidate, CandidatePage } from "./types";
import type {
  CandidateColumnConfig,
  CandidateColumnKey,
  CandidateGridColumnFilter,
  CandidateGridQueryState,
  CandidateValueFilterRequest
} from "./candidateQueueState";
import {
  candidateColumnLabels,
  defaultCandidateColumns,
  isCandidateColumnFilterable,
  isCandidateColumnSortable
} from "./candidateQueueState";
import { AppDataGrid } from "../ui/AppDataGrid";

const candidateGridLocaleText = {
  noRowsLabel: "По текущим фильтрам кандидатов нет.",
  footerRowSelected: (count: number) => `${formatInteger(count)} выбрано`,
  paginationRowsPerPage: "Строк на странице",
  paginationDisplayedRows: ({ from, to, count }: { from: number; to: number; count: number }) =>
    `${formatInteger(from)}-${formatInteger(to)} из ${formatInteger(count)}`,
  paginationItemAriaLabel: (type: "first" | "last" | "next" | "previous") => {
    if (type === "next") {
      return "Следующая страница";
    }
    if (type === "previous") {
      return "Предыдущая страница";
    }
    if (type === "first") {
      return "Первая страница";
    }
    return "Последняя страница";
  }
};

export function CandidateTable({
  page,
  loading,
  focusMessageId,
  returnHash,
  goldenSavingId,
  columns,
  gridState,
  onPageChange,
  onAddGolden,
  onColumnResize,
  onColumnOrderChange,
  onColumnVisibilityChange,
  onApplyGridFilter,
  onGridStateChange
}: {
  page: CandidatePage | null;
  loading: boolean;
  focusMessageId?: string | null;
  returnHash: string;
  goldenSavingId?: string | null;
  columns: CandidateColumnConfig[];
  gridState: CandidateGridQueryState;
  onPageChange: (nextPage: number) => void;
  onAddGolden?: (candidate: AnalyticsCandidate) => void;
  onColumnResize: (key: CandidateColumnKey, width: number) => void;
  onColumnOrderChange: (key: CandidateColumnKey, targetIndex: number) => void;
  onColumnVisibilityChange: (model: GridColumnVisibilityModel) => void;
  onApplyGridFilter: (filter: CandidateGridColumnFilter) => void;
  onGridStateChange: (nextState: CandidateGridQueryState) => void;
}) {
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [dismissedFocusMessageId, setDismissedFocusMessageId] = useState<string | null>(null);
  const [filterMenuAnchorEl, setFilterMenuAnchorEl] = useState<HTMLElement | null>(null);
  const [filterMenuRequest, setFilterMenuRequest] = useState<CandidateValueFilterRequest | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const effectiveColumns = columns.some((column) => column.visible)
    ? columns
    : defaultCandidateColumns.map((column, index) => ({ ...column, visible: index === 0 }));
  const rows = page?.items ?? [];
  const focusedPageMessageId =
    focusMessageId && rows.some((candidate) => candidate.message_id === focusMessageId) ? focusMessageId : null;
  const activeSelectedMessageId =
    selectedMessageId ?? (focusedPageMessageId !== dismissedFocusMessageId ? focusedPageMessageId : null);
  const selectedCandidate = rows.find((candidate) => candidate.message_id === activeSelectedMessageId) ?? null;
  const currentPage = page ? Math.floor(page.offset / page.limit) : 0;
  const pageSize = page?.limit ?? 50;
  const paginationModel = useMemo<GridPaginationModel>(
    () => ({ page: currentPage, pageSize }),
    [currentPage, pageSize]
  );
  const gridColumns = useMemo(
    () =>
      buildGridColumns(effectiveColumns, (request, anchorEl) => {
        setFilterMenuRequest(request);
        setFilterMenuAnchorEl(anchorEl);
      }),
    [effectiveColumns]
  );
  const columnVisibilityModel = useMemo<GridColumnVisibilityModel>(
    () =>
      Object.fromEntries(
        effectiveColumns.map((column) => [column.key, column.visible])
      ) as GridColumnVisibilityModel,
    [effectiveColumns]
  );
  const sortModel = useMemo<GridSortModel>(
    () => (gridState.sort ? [{ field: gridState.sort.field, sort: gridState.sort.direction }] : []),
    [gridState.sort]
  );
  const filterModel = useMemo<GridFilterModel>(
    () => ({
      items: gridState.columnFilters.slice(-1).map((filter, index) => ({
        id: `${filter.field}-${index}`,
        field: filter.field,
        operator: filter.operator,
        value: filter.value
      })),
      quickFilterValues: gridState.quickFilter ? [gridState.quickFilter] : []
    }),
    [gridState.columnFilters, gridState.quickFilter]
  );
  useEffect(() => {
    setSelectedMessageId(null);
    setDismissedFocusMessageId(null);
  }, [focusMessageId]);

  useEffect(() => {
    if (!focusedPageMessageId) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      gridRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [focusedPageMessageId]);

  if (loading && page === null) {
    return (
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
        <CircularProgress size={20} />
        <Typography variant="body2">Загрузка кандидатов...</Typography>
      </Stack>
    );
  }

  return (
    <Box className={selectedCandidate ? "candidate-grid-layout candidate-grid-layout--with-side" : "candidate-grid-layout"} ref={gridRef}>
      <Box className="candidate-grid-shell">
        <AppDataGrid
          className="analytics-candidate-grid"
          columns={gridColumns}
          columnVisibilityModel={columnVisibilityModel}
          disableVirtualization
          filterMode="server"
          filterModel={filterModel}
          getEstimatedRowHeight={() => 76}
          getRowClassName={(params) => candidateRowClass(params.row.message_id === activeSelectedMessageId, params.row.message_id === focusMessageId)}
          getRowHeight={() => "auto"}
          getRowId={(row) => row.message_id}
          label="Очередь кандидатов"
          loading={loading}
          localeText={candidateGridLocaleText}
          onColumnOrderChange={(params: GridColumnOrderChangeParams) => {
            onColumnOrderChange(params.column.field as CandidateColumnKey, params.targetIndex);
          }}
          onColumnVisibilityModelChange={onColumnVisibilityChange}
          onColumnWidthChange={(params: GridColumnResizeParams) => {
            onColumnResize(params.colDef.field as CandidateColumnKey, params.width);
          }}
          onFilterModelChange={(model) => {
            const nextColumnFilters = model.items.flatMap((item) => {
              const field = toCandidateColumnKey(item.field);
              if (!field || !isCandidateColumnFilterable(field)) {
                return [];
              }
              const value = item.value === undefined || item.value === null ? "" : String(item.value);
              return [{ field, operator: item.operator, value }];
            });
            onGridStateChange({
              ...gridState,
              columnFilters:
                nextColumnFilters.length > 0
                  ? mergeColumnFilters(gridState.columnFilters, nextColumnFilters)
                  : gridState.columnFilters,
              quickFilter: (model.quickFilterValues ?? []).map((value) => String(value)).join(" ").trim()
            });
          }}
          onPaginationModelChange={(model) => {
            if (model.page !== currentPage) {
              onPageChange(model.page);
            }
          }}
          onRowClick={(params: GridRowParams<AnalyticsCandidate>) => {
            setSelectedMessageId(params.row.message_id);
          }}
          onSortModelChange={(model) => {
            const item = model[0];
            const field = toCandidateColumnKey(item?.field ?? "");
            onGridStateChange({
              ...gridState,
              sort: field && item?.sort ? { field, direction: item.sort === "asc" ? "asc" : "desc" } : null
            });
          }}
          pageSizeOptions={[pageSize]}
          paginationMode="server"
          paginationModel={paginationModel}
          rowCount={page?.total ?? 0}
          rows={rows}
          showToolbar={false}
          sortingMode="server"
          sortModel={sortModel}
        />
      </Box>
      {selectedCandidate && (
        <CandidateQueueSidePage
          candidate={selectedCandidate}
          returnHash={returnHash}
          goldenSavingId={goldenSavingId}
          onClose={() => {
            setSelectedMessageId(null);
            if (focusMessageId === selectedCandidate.message_id) {
              setDismissedFocusMessageId(selectedCandidate.message_id);
            }
          }}
          onAddGolden={onAddGolden}
          onFilterValue={(request, anchorEl) => {
            setFilterMenuRequest(request);
            setFilterMenuAnchorEl(anchorEl);
          }}
        />
      )}
      <CandidateValueFilterMenu
        anchorEl={filterMenuAnchorEl}
        request={filterMenuRequest}
        onClose={() => {
          setFilterMenuAnchorEl(null);
          setFilterMenuRequest(null);
        }}
        onApply={onApplyGridFilter}
      />
    </Box>
  );
}

function buildGridColumns(
  columns: CandidateColumnConfig[],
  onFilterValue: (request: CandidateValueFilterRequest, anchorEl: HTMLElement) => void
): Array<GridColDef<AnalyticsCandidate>> {
  return columns.map((column) => {
    const valueOptions = candidateColumnValueOptions[column.key];
    return {
      field: column.key,
      headerName: candidateColumnLabels[column.key],
      width: column.width,
      minWidth: Math.min(column.width, 120),
      maxWidth: 720,
      sortable: isCandidateColumnSortable(column.key),
      filterable: isCandidateColumnFilterable(column.key),
      hideable: true,
      resizable: true,
      type: candidateColumnType(column.key),
      valueOptions,
      valueGetter: (_value, row) => candidateColumnGridValue(column.key, row),
      cellClassName: candidateCellClass(column.key),
      renderCell: (params: GridRenderCellParams<AnalyticsCandidate>) => (
        <CandidateColumnValue
          columnKey={column.key}
          candidate={params.row}
          onFilterValue={onFilterValue}
        />
      )
    };
  });
}

const numberColumns = new Set<CandidateColumnKey>([
  "telegramMessageId",
  "score",
  "llmConfidence",
  "llmAttempts"
]);

const dateColumns = new Set<CandidateColumnKey>([
  "receivedAt",
  "messageDate",
  "llmUpdatedAt",
  "enrichmentFinishedAt"
]);

const booleanColumns = new Set<CandidateColumnKey>([
  "autoLead",
  "effectiveLead",
  "llmAgreement"
]);

const singleSelectColumns = new Set<CandidateColumnKey>([
  "sourceType",
  "temperature",
  "reviewStatus",
  "llmStatus",
  "llmVerdict",
  "llmRecommendation",
  "enrichmentStatus"
]);

const candidateColumnValueOptions: Partial<Record<CandidateColumnKey, Array<{ value: string; label: string }>>> = {
  sourceType: [
    { value: "telegram", label: "telegram" },
    { value: "max", label: "MAX" }
  ],
  temperature: [
    { value: "hot", label: "hot" },
    { value: "warm", label: "warm" },
    { value: "cold", label: "cold" }
  ],
  reviewStatus: [
    { value: "unreviewed", label: "Без ревью" },
    { value: "reviewed", label: "С ревью" }
  ],
  llmStatus: [
    { value: "queued", label: "queued" },
    { value: "running", label: "running" },
    { value: "completed", label: "completed" },
    { value: "failed", label: "failed" },
    { value: "not_processed", label: "Не обработано" }
  ],
  llmVerdict: [
    { value: "lead", label: "lead" },
    { value: "not_lead", label: "not_lead" },
    { value: "uncertain", label: "uncertain" }
  ],
  llmRecommendation: [
    { value: "keep", label: "keep" },
    { value: "promote", label: "promote" },
    { value: "demote", label: "demote" },
    { value: "manual_review", label: "manual_review" }
  ],
  enrichmentStatus: [
    { value: "pending", label: "pending" },
    { value: "running", label: "running" },
    { value: "completed", label: "completed" },
    { value: "failed", label: "failed" }
  ]
};

function candidateColumnType(key: CandidateColumnKey): GridColDef<AnalyticsCandidate>["type"] {
  if (numberColumns.has(key)) {
    return "number";
  }
  if (dateColumns.has(key)) {
    return "dateTime";
  }
  if (booleanColumns.has(key)) {
    return "boolean";
  }
  if (singleSelectColumns.has(key)) {
    return "singleSelect";
  }
  return "string";
}

function toCandidateColumnKey(value: string): CandidateColumnKey | null {
  if (candidateColumnLabels[value as CandidateColumnKey]) {
    return value as CandidateColumnKey;
  }
  return null;
}

function mergeColumnFilters(
  currentFilters: CandidateGridColumnFilter[],
  nextFilters: CandidateGridColumnFilter[]
): CandidateGridColumnFilter[] {
  const nextKeys = new Set(nextFilters.map((filter) => `${filter.field}:${filter.operator}`));
  return [
    ...currentFilters.filter((filter) => !nextKeys.has(`${filter.field}:${filter.operator}`)),
    ...nextFilters
  ];
}

function candidateRowClass(expanded: boolean, focused: boolean): string {
  return [
    expanded ? "candidate-row-expanded" : "",
    focused ? "candidate-row-focused" : ""
  ].filter(Boolean).join(" ");
}
