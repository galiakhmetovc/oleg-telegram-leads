import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import StarIcon from "@mui/icons-material/Star";
import { Alert, Box, Button, Chip, InputAdornment, LinearProgress, Paper, Stack, TextField, Typography } from "@mui/material";
import type { GridColumnVisibilityModel } from "@mui/x-data-grid";
import { useEffect, useMemo, useRef, useState } from "react";

import { SectionTitle } from "./AnalyticsShared";
import { CandidateDetails } from "./CandidateEvidence";
import { CandidateFieldsetControls } from "./CandidateFieldsetControls";
import { CandidateQueueAutoRefreshMenu, autoRefreshLabel } from "./CandidateQueueAutoRefreshMenu";
import { CandidateFilterDialog } from "./CandidateQueueControls";
import { CandidateQueueIntervalMenu, candidateIntervalChipLabel } from "./CandidateQueueIntervalMenu";
import { CandidateQueueSavedFilters } from "./CandidateQueueSavedFilters";
import { CandidateTable } from "./CandidateQueueTable";
import { formatInteger } from "./analyticsFormat";
import {
  analyticsListHash,
  candidatePageSize,
  parseAnalyticsUrlState,
  replaceAnalyticsListHash
} from "./analyticsRoutes";
import type { AnalyticsCandidate, AnalyticsSummary, CandidateFilters, CandidatePage } from "./types";
import type {
  CandidateColumnConfig,
  CandidateColumnFieldset,
  CandidateColumnKey,
  CandidateGridColumnFilter,
  CandidateGridFilterChip,
  CandidateGridQueryState,
  CandidateQueueSavedFilter
} from "./candidateQueueState";
import {
  buildFilterOptionLabels,
  candidateFilterChips,
  candidateGridFilterChips,
  candidateQuery,
  candidateRouteHasExplicitFilters,
  clampColumnWidth,
  defaultCandidateFilters,
  deleteCandidateFieldset,
  deleteCandidateSavedFilter,
  loadCandidateFieldsets,
  loadCandidateColumns,
  loadCandidateSavedFilters,
  normalizeCandidateColumns,
  saveCandidateFieldsets,
  saveCandidateColumns,
  saveCandidateSavedFilters,
  upsertCandidateFieldset,
  upsertCandidateSavedFilter
} from "./candidateQueueState";
import { currentRoute, routeQuery } from "../routes";

export function CandidateQueueSection({
  apiBaseUrl,
  selectedRunId,
  summary,
  loadingSummary,
  focusMessageId,
  onRefresh,
  onTestMessage
}: {
  apiBaseUrl: string;
  selectedRunId: string;
  summary: AnalyticsSummary | null;
  loadingSummary: boolean;
  focusMessageId?: string | null;
  onRefresh?: () => void;
  onTestMessage?: (candidate: AnalyticsCandidate) => void;
}) {
  const initialRouteRef = useRef(currentRoute());
  const initialAnalyticsStateRef = useRef(parseAnalyticsUrlState(initialRouteRef.current));
  const initialSavedFiltersRef = useRef(loadCandidateSavedFilters());
  const initialFieldsetsRef = useRef(loadCandidateFieldsets());
  const initialAnalyticsState = initialAnalyticsStateRef.current;
  const initialDefaultFieldset = initialFieldsetsRef.current.find((fieldset) => fieldset.isDefault) ?? null;
  const [candidatePage, setCandidatePage] = useState<CandidatePage | null>(null);
  const [focusedCandidate, setFocusedCandidate] = useState<AnalyticsCandidate | null>(null);
  const [filters, setFilters] = useState<CandidateFilters>(initialAnalyticsState.filters);
  const [appliedFilters, setAppliedFilters] = useState<CandidateFilters>(initialAnalyticsState.filters);
  const [candidateGridState, setCandidateGridState] = useState<CandidateGridQueryState>(initialAnalyticsState.grid);
  const [quickSearchDraft, setQuickSearchDraft] = useState(initialAnalyticsState.grid.quickFilter);
  const [savedFilters, setSavedFilters] = useState<CandidateQueueSavedFilter[]>(initialSavedFiltersRef.current);
  const [candidateFieldsets, setCandidateFieldsets] = useState<CandidateColumnFieldset[]>(initialFieldsetsRef.current);
  const [selectedFieldsetId, setSelectedFieldsetId] = useState(initialDefaultFieldset?.id ?? "");
  const [selectedSavedFilterId, setSelectedSavedFilterId] = useState(() =>
    candidateRouteHasExplicitFilters(routeQuery(initialRouteRef.current))
      ? ""
      : initialSavedFiltersRef.current.find((savedFilter) => savedFilter.isDefault)?.id ?? ""
  );
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [filterDialogDraft, setFilterDialogDraft] = useState<CandidateFilters>(initialAnalyticsState.filters);
  const [candidateColumns, setCandidateColumns] = useState<CandidateColumnConfig[]>(() =>
    initialDefaultFieldset?.columns ?? loadCandidateColumns()
  );
  const [candidateOffset, setCandidateOffset] = useState(initialAnalyticsState.offset);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(0);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [goldenSavingId, setGoldenSavingId] = useState<string | null>(null);
  const [goldenMessage, setGoldenMessage] = useState<string | null>(null);
  const [goldenError, setGoldenError] = useState<string | null>(null);
  const focusedCandidatePanelRef = useRef<HTMLDivElement | null>(null);

  const loadingData = loadingSummary || loadingCandidates;
  const focusedCandidateInCurrentPage = useMemo(
    () => Boolean(focusMessageId && candidatePage?.items.some((candidate) => candidate.message_id === focusMessageId)),
    [candidatePage, focusMessageId]
  );

  useEffect(() => {
    if (!selectedRunId) {
      setCandidatePage(null);
      return;
    }

    let active = true;
    async function loadCandidates() {
      setLoadingCandidates(true);
      setCandidateError(null);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/analytics/runs/${selectedRunId}/candidates?${candidateQuery(
            appliedFilters,
            candidatePageSize,
            candidateOffset,
            candidateGridState
          )}`
        );
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const nextCandidates = (await response.json()) as CandidatePage;
        if (active) {
          setCandidatePage(nextCandidates);
        }
      } catch (caught) {
        if (active) {
          setCandidateError(caught instanceof Error ? caught.message : "Не удалось загрузить кандидатов");
        }
      } finally {
        if (active) {
          setLoadingCandidates(false);
        }
      }
    }

    void loadCandidates();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedRunId, appliedFilters, candidateOffset, candidateGridState, refreshNonce]);

  useEffect(() => {
    if (!autoRefreshSeconds) {
      return;
    }
    const intervalId = window.setInterval(() => {
      setRefreshNonce((value) => value + 1);
      onRefresh?.();
    }, autoRefreshSeconds * 1000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshSeconds, onRefresh]);

  useEffect(() => {
    if (!focusMessageId) {
      setFocusedCandidate(null);
      return;
    }

    const messageId = focusMessageId;
    let active = true;
    async function loadFocusedCandidate() {
      setCandidateError(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const candidate = (await response.json()) as AnalyticsCandidate;
        if (active) {
          setFocusedCandidate(candidate);
        }
      } catch (caught) {
        if (active) {
          setCandidateError(caught instanceof Error ? caught.message : "Не удалось загрузить сообщение аналитики");
        }
      }
    }

    void loadFocusedCandidate();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, focusMessageId]);

  useEffect(() => {
    if (!focusMessageId || !focusedCandidate || focusedCandidate.message_id !== focusMessageId || focusedCandidateInCurrentPage) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      focusedCandidatePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [focusedCandidate, focusedCandidateInCurrentPage, focusMessageId]);

  useEffect(() => {
    setQuickSearchDraft(candidateGridState.quickFilter);
  }, [candidateGridState.quickFilter]);

  useEffect(() => {
    const nextQuickSearch = quickSearchDraft.trim();
    if (nextQuickSearch === candidateGridState.quickFilter) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      applyCandidateGridState({ ...candidateGridState, quickFilter: nextQuickSearch });
    }, 450);
    return () => window.clearTimeout(timeoutId);
  }, [candidateGridState, quickSearchDraft]);

  const signalOptions = summary?.aggregates.signal ?? [];
  const reasonOptions = summary?.aggregates.reason ?? [];
  const solutionAreaOptions = summary?.aggregates.solution_area ?? [];
  const customerSegmentOptions = summary?.aggregates.customer_segment ?? [];
  const laneOptions = summary?.aggregates.review_lane ?? [];
  const sourceChatOptions = summary?.aggregates.source_chat ?? [];
  const analyticsReturnHash = analyticsListHash(appliedFilters, candidateOffset, selectedRunId, candidateGridState);
  const filterOptionLabels = useMemo(
    () =>
      buildFilterOptionLabels({
        signalOptions,
        reasonOptions,
        solutionAreaOptions,
        customerSegmentOptions,
        laneOptions,
        sourceChatOptions
      }),
    [signalOptions, reasonOptions, solutionAreaOptions, customerSegmentOptions, laneOptions, sourceChatOptions]
  );
  const activeFilterChips = useMemo(
    () => candidateFilterChips(appliedFilters, filterOptionLabels),
    [appliedFilters, filterOptionLabels]
  );
  const visibleActiveFilterChips = useMemo(
    () => activeFilterChips.filter((chip) => chip.key !== "receivedFrom" && chip.key !== "receivedTo"),
    [activeFilterChips]
  );
  const activeGridFilterChips = useMemo(
    () => candidateGridFilterChips(candidateGridState),
    [candidateGridState]
  );
  const selectedFieldset = candidateFieldsets.find((fieldset) => fieldset.id === selectedFieldsetId) ?? null;

  function applyCandidateFilters(next: CandidateFilters) {
    setFilters(next);
    setFilterDialogDraft(next);
    setCandidateOffset(0);
    setAppliedFilters(next);
    setSelectedSavedFilterId("");
    replaceAnalyticsListHash(next, 0, selectedRunId, candidateGridState);
  }

  function applyFilterDialog() {
    applyCandidateFilters(filterDialogDraft);
    setFilterDialogOpen(false);
  }

  function updateFilterDraft(key: keyof CandidateFilters, value: string) {
    const next = { ...filterDialogDraft, [key]: value };
    setFilterDialogDraft(next);
    setFilters(next);
    return next;
  }

  function openFilterDialog() {
    setFilterDialogDraft(appliedFilters);
    setFilters(appliedFilters);
    setFilterDialogOpen(true);
  }

  function removeAppliedFilter(key: keyof CandidateFilters) {
    applyCandidateFilters({ ...appliedFilters, [key]: "" });
  }

  function applyCandidateGridState(next: CandidateGridQueryState) {
    setCandidateOffset(0);
    setCandidateGridState(next);
    setSelectedSavedFilterId("");
    replaceAnalyticsListHash(appliedFilters, 0, selectedRunId, next);
  }

  function applyCandidateGridFilter(filter: CandidateGridColumnFilter) {
    applyCandidateGridState({
      ...candidateGridState,
      columnFilters: [
        ...candidateGridState.columnFilters.filter(
          (current) =>
            current.field !== filter.field ||
            current.operator !== filter.operator ||
            current.value !== filter.value
        ),
        filter
      ]
    });
  }

  function removeGridFilterChip(chip: CandidateGridFilterChip) {
    if (chip.kind === "quick") {
      applyCandidateGridState({ ...candidateGridState, quickFilter: "" });
      return;
    }
    if (chip.kind === "sort") {
      applyCandidateGridState({ ...candidateGridState, sort: null });
      return;
    }
    if (chip.kind === "column" && typeof chip.index === "number") {
      applyCandidateGridState({
        ...candidateGridState,
        columnFilters: candidateGridState.columnFilters.filter((_filter, index) => index !== chip.index)
      });
    }
  }

  function resetFilters() {
    const next = defaultCandidateFilters();
    setFilters(next);
    setFilterDialogDraft(next);
  }

  function persistSavedFilters(nextSavedFilters: CandidateQueueSavedFilter[]) {
    setSavedFilters(nextSavedFilters);
    saveCandidateSavedFilters(nextSavedFilters);
  }

  function saveCurrentSavedFilter(savedFilter: CandidateQueueSavedFilter) {
    const nextSavedFilters = upsertCandidateSavedFilter(savedFilters, savedFilter);
    persistSavedFilters(nextSavedFilters);
    setSelectedSavedFilterId(savedFilter.id);
  }

  function applySavedFilter(savedFilter: CandidateQueueSavedFilter) {
    setFilters(savedFilter.filters);
    setFilterDialogDraft(savedFilter.filters);
    setAppliedFilters(savedFilter.filters);
    setCandidateGridState(savedFilter.gridState);
    setCandidateOffset(0);
    setSelectedSavedFilterId(savedFilter.id);
    replaceAnalyticsListHash(savedFilter.filters, 0, selectedRunId, savedFilter.gridState);
  }

  function deleteSavedFilter(id: string) {
    const nextSavedFilters = deleteCandidateSavedFilter(savedFilters, id);
    persistSavedFilters(nextSavedFilters);
    if (selectedSavedFilterId === id) {
      setSelectedSavedFilterId("");
    }
  }

  function setDefaultSavedFilter(id: string) {
    const target = savedFilters.find((savedFilter) => savedFilter.id === id);
    if (!target) {
      return;
    }
    persistSavedFilters(
      upsertCandidateSavedFilter(savedFilters, {
        ...target,
        isDefault: true,
        updatedAt: new Date().toISOString()
      })
    );
  }

  function updateSavedFilterFromCurrent(id: string) {
    const target = savedFilters.find((savedFilter) => savedFilter.id === id);
    if (!target) {
      return;
    }
    persistSavedFilters(
      upsertCandidateSavedFilter(savedFilters, {
        ...target,
        filters: appliedFilters,
        gridState: candidateGridState,
        updatedAt: new Date().toISOString()
      })
    );
  }

  function renameSavedFilter(id: string, name: string) {
    const target = savedFilters.find((savedFilter) => savedFilter.id === id);
    const trimmed = name.trim();
    if (!target || !trimmed) {
      return;
    }
    persistSavedFilters(
      upsertCandidateSavedFilter(savedFilters, {
        ...target,
        name: trimmed,
        updatedAt: new Date().toISOString()
      })
    );
  }

  function persistFieldsets(nextFieldsets: CandidateColumnFieldset[]) {
    setCandidateFieldsets(nextFieldsets);
    saveCandidateFieldsets(nextFieldsets);
  }

  function saveCurrentFieldset(fieldset: CandidateColumnFieldset) {
    const nextFieldsets = upsertCandidateFieldset(candidateFieldsets, fieldset);
    persistFieldsets(nextFieldsets);
    setSelectedFieldsetId(fieldset.id);
  }

  function applyFieldset(fieldset: CandidateColumnFieldset) {
    const normalized = normalizeCandidateColumns(fieldset.columns);
    setCandidateColumns(normalized);
    saveCandidateColumns(normalized);
    setSelectedFieldsetId(fieldset.id);
  }

  function deleteFieldset(id: string) {
    const nextFieldsets = deleteCandidateFieldset(candidateFieldsets, id);
    persistFieldsets(nextFieldsets);
    if (selectedFieldsetId === id) {
      setSelectedFieldsetId("");
    }
  }

  function setDefaultFieldset(id: string) {
    const target = candidateFieldsets.find((fieldset) => fieldset.id === id);
    if (!target) {
      return;
    }
    persistFieldsets(
      upsertCandidateFieldset(candidateFieldsets, {
        ...target,
        isDefault: true,
        updatedAt: new Date().toISOString()
      })
    );
  }

  function updateFieldsetFromCurrent(id: string) {
    const target = candidateFieldsets.find((fieldset) => fieldset.id === id);
    if (!target) {
      return;
    }
    persistFieldsets(
      upsertCandidateFieldset(candidateFieldsets, {
        ...target,
        columns: candidateColumns,
        updatedAt: new Date().toISOString()
      })
    );
  }

  function renameFieldset(id: string, name: string) {
    const target = candidateFieldsets.find((fieldset) => fieldset.id === id);
    const trimmed = name.trim();
    if (!target || !trimmed) {
      return;
    }
    persistFieldsets(
      upsertCandidateFieldset(candidateFieldsets, {
        ...target,
        name: trimmed,
        updatedAt: new Date().toISOString()
      })
    );
  }

  function updateCandidateColumns(nextColumns: CandidateColumnConfig[]) {
    const normalized = normalizeCandidateColumns(nextColumns);
    setCandidateColumns(normalized);
    saveCandidateColumns(normalized);
  }

  function reorderCandidateColumn(key: CandidateColumnKey, targetIndex: number) {
    const columnByKey = new Map(candidateColumns.map((column) => [column.key, column]));
    const visibleKeys = candidateColumns.filter((column) => column.visible).map((column) => column.key);
    const currentIndex = visibleKeys.indexOf(key);
    if (currentIndex < 0) {
      return;
    }
    const nextVisibleKeys = [...visibleKeys];
    const [movedKey] = nextVisibleKeys.splice(currentIndex, 1);
    nextVisibleKeys.splice(Math.max(0, Math.min(targetIndex, nextVisibleKeys.length)), 0, movedKey);
    const hiddenColumns = candidateColumns.filter((column) => !column.visible);
    const nextColumns = [
      ...nextVisibleKeys.flatMap((visibleKey) => {
        const column = columnByKey.get(visibleKey);
        return column ? [column] : [];
      }),
      ...hiddenColumns
    ];
    setSelectedFieldsetId("");
    updateCandidateColumns(nextColumns);
  }

  function resizeCandidateColumn(key: CandidateColumnKey, width: number) {
    setSelectedFieldsetId("");
    updateCandidateColumns(
      candidateColumns.map((column) =>
        column.key === key ? { ...column, width: clampColumnWidth(width) } : column
      )
    );
  }

  function updateCandidateColumnVisibility(model: GridColumnVisibilityModel) {
    const nextColumns = candidateColumns.map((column) => ({
      ...column,
      visible: model[column.key] ?? column.visible
    }));
    setSelectedFieldsetId("");
    updateCandidateColumns(
      nextColumns.some((column) => column.visible)
        ? nextColumns
        : nextColumns.map((column, index) => (index === 0 ? { ...column, visible: true } : column))
    );
  }

  function refreshCandidates() {
    setRefreshNonce((value) => value + 1);
    onRefresh?.();
  }

  function handleCandidatePageChange(nextPage: number) {
    const limit = candidatePage?.limit ?? candidatePageSize;
    const nextOffset = nextPage * limit;
    setCandidateOffset(nextOffset);
    replaceAnalyticsListHash(appliedFilters, nextOffset, selectedRunId, candidateGridState);
  }

  async function addCandidateToGolden(candidate: AnalyticsCandidate) {
    setGoldenSavingId(candidate.message_id);
    setGoldenMessage(null);
    setGoldenError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/golden-examples/from-message/${encodeURIComponent(candidate.message_id)}`,
        { method: "POST" }
      );
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      setGoldenMessage("Сообщение добавлено в golden-примеры");
    } catch (caught) {
      setGoldenError(caught instanceof Error ? caught.message : "Не удалось добавить сообщение в golden");
    } finally {
      setGoldenSavingId(null);
    }
  }

  return (
    <>
      {candidateError && <Alert severity="error">{candidateError}</Alert>}
      {goldenError && <Alert severity="error">{goldenError}</Alert>}
      {goldenMessage && <Alert severity="success">{goldenMessage}</Alert>}
      {loadingData && <LinearProgress />}

      {focusedCandidate && !focusedCandidateInCurrentPage && (
        <Paper ref={focusedCandidatePanelRef} variant="outlined" className="analytics-section candidate-row-focused">
          <Stack spacing={1.5}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
              <SectionTitle
                title="Сообщение из ссылки"
                subtitle={focusedCandidate.source_chat_title || focusedCandidate.message_id}
              />
              <Button variant="outlined" onClick={() => onTestMessage?.(focusedCandidate)}>
                Проверить
              </Button>
              <Button
                variant="outlined"
                startIcon={<StarIcon />}
                disabled={goldenSavingId === focusedCandidate.message_id}
                onClick={() => void addCandidateToGolden(focusedCandidate)}
                aria-label={`Добавить в golden ${focusedCandidate.message_id}`}
              >
                В golden
              </Button>
            </Stack>
            <CandidateDetails candidate={focusedCandidate} />
          </Stack>
        </Paper>
      )}

      <Paper variant="outlined" className="analytics-section candidate-queue-section">
        <Stack spacing={1}>
          <Box className="candidate-queue-headerline">
            <Box className="candidate-queue-total" aria-label={`${formatInteger(candidatePage?.total ?? 0)} сообщений по текущим условиям`}>
              <Typography className="candidate-queue-total__value" component="span">
                {formatInteger(candidatePage?.total ?? 0)}
              </Typography>
              <Typography className="candidate-queue-total__label" component="span">
                сообщений
              </Typography>
            </Box>
            <Stack className="candidate-queue-commandbar" direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", justifyContent: { md: "flex-end" } }}>
                <TextField
                  className="candidate-queue-search"
                  size="small"
                  placeholder="Поиск"
                  value={quickSearchDraft}
                  onChange={(event) => setQuickSearchDraft(event.target.value)}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <SearchIcon fontSize="small" />
                        </InputAdornment>
                      )
                    }
                  }}
                />
                <CandidateQueueIntervalMenu filters={appliedFilters} onApply={applyCandidateFilters} />
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<AddIcon fontSize="small" />}
                  onClick={openFilterDialog}
                  disabled={!selectedRunId}
                  aria-label="Открыть фильтры очереди"
                >
                  Фильтры
                </Button>
                <CandidateFieldsetControls
                  fieldsets={candidateFieldsets}
                  selectedFieldsetId={selectedFieldsetId}
                  currentColumns={candidateColumns}
                  onApply={applyFieldset}
                  onSave={saveCurrentFieldset}
                  onDelete={deleteFieldset}
                  onSetDefault={setDefaultFieldset}
                  onUpdateFromCurrent={updateFieldsetFromCurrent}
                  onRename={renameFieldset}
                />
                <Button size="small" variant="outlined" startIcon={<RefreshIcon fontSize="small" />} onClick={refreshCandidates} disabled={!selectedRunId}>
                  Обновить
                </Button>
                <CandidateQueueAutoRefreshMenu value={autoRefreshSeconds} onChange={setAutoRefreshSeconds} />
            </Stack>
          </Box>
          <Box className="candidate-queue-statebar">
              <CandidateQueueSavedFilters
                savedFilters={savedFilters}
                selectedSavedFilterId={selectedSavedFilterId}
                currentFilters={appliedFilters}
                currentGridState={candidateGridState}
                onApply={applySavedFilter}
                onClearSelection={() => setSelectedSavedFilterId("")}
                onSave={saveCurrentSavedFilter}
                onDelete={deleteSavedFilter}
                onSetDefault={setDefaultSavedFilter}
                onUpdateFromCurrent={updateSavedFilterFromCurrent}
                onRename={renameSavedFilter}
              />
              <Stack className="candidate-applied-chips" direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", justifyContent: { md: "flex-end" } }}>
                <Chip
                  size="small"
                  label={`Интервал: ${candidateIntervalChipLabel(appliedFilters)}`}
                  onDelete={() => applyCandidateFilters({ ...appliedFilters, receivedFrom: "", receivedTo: "" })}
                />
                {selectedFieldset && <Chip size="small" label={`Набор полей: ${selectedFieldset.name}`} onDelete={() => setSelectedFieldsetId("")} />}
                {autoRefreshSeconds > 0 && (
                  <Chip size="small" label={`Автообновление: ${autoRefreshLabel(autoRefreshSeconds)}`} onDelete={() => setAutoRefreshSeconds(0)} />
                )}
                {visibleActiveFilterChips.map((chip) => (
                  <Chip
                    key={chip.key}
                    size="small"
                    label={chip.label}
                    onDelete={chip.removable ? () => removeAppliedFilter(chip.key) : undefined}
                  />
                ))}
                {activeGridFilterChips.map((chip) => (
                  <Chip
                    key={chip.key}
                    size="small"
                    label={chip.label}
                    onDelete={chip.removable ? () => removeGridFilterChip(chip) : undefined}
                  />
                ))}
              </Stack>
          </Box>
          <CandidateTable
            page={candidatePage}
            loading={loadingData}
            focusMessageId={focusMessageId}
            returnHash={analyticsReturnHash}
            goldenSavingId={goldenSavingId}
            columns={candidateColumns}
            gridState={candidateGridState}
            onPageChange={handleCandidatePageChange}
            onAddGolden={(candidate) => void addCandidateToGolden(candidate)}
            onColumnResize={resizeCandidateColumn}
            onColumnOrderChange={reorderCandidateColumn}
            onColumnVisibilityChange={updateCandidateColumnVisibility}
            onApplyGridFilter={applyCandidateGridFilter}
            onGridStateChange={applyCandidateGridState}
          />
        </Stack>
      </Paper>

      <CandidateFilterDialog
        open={filterDialogOpen}
        filters={filters}
        signalOptions={signalOptions}
        reasonOptions={reasonOptions}
        solutionAreaOptions={solutionAreaOptions}
        customerSegmentOptions={customerSegmentOptions}
        laneOptions={laneOptions}
        sourceChatOptions={sourceChatOptions}
        onChange={updateFilterDraft}
        onReset={resetFilters}
        onClose={() => setFilterDialogOpen(false)}
        onApply={applyFilterDialog}
      />
    </>
  );
}
