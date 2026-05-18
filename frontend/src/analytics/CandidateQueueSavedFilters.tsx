import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import StarIcon from "@mui/icons-material/Star";
import UpdateIcon from "@mui/icons-material/Update";
import {
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import { useState } from "react";

import type { CandidateFilters } from "./types";
import type { CandidateGridQueryState, CandidateQueueSavedFilter } from "./candidateQueueState";

export function CandidateQueueSavedFilters({
  savedFilters,
  selectedSavedFilterId,
  currentFilters,
  currentGridState,
  onApply,
  onClearSelection,
  onSave,
  onDelete,
  onSetDefault,
  onUpdateFromCurrent,
  onRename
}: {
  savedFilters: CandidateQueueSavedFilter[];
  selectedSavedFilterId: string;
  currentFilters: CandidateFilters;
  currentGridState: CandidateGridQueryState;
  onApply: (savedFilter: CandidateQueueSavedFilter) => void;
  onClearSelection: () => void;
  onSave: (savedFilter: CandidateQueueSavedFilter) => void;
  onDelete: (id: string) => void;
  onSetDefault: (id: string) => void;
  onUpdateFromCurrent: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [manageDialogOpen, setManageDialogOpen] = useState(false);
  const [newFilterName, setNewFilterName] = useState("");
  const [newFilterDefault, setNewFilterDefault] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editingName, setEditingName] = useState("");
  const selectedSavedFilter = savedFilters.find((savedFilter) => savedFilter.id === selectedSavedFilterId) ?? null;

  function openSaveDialog() {
    setNewFilterName("");
    setNewFilterDefault(false);
    setSaveDialogOpen(true);
  }

  function saveCurrentFilter() {
    const name = newFilterName.trim();
    if (!name) {
      return;
    }
    const now = new Date().toISOString();
    onSave({
      id: createSavedFilterId(),
      name,
      filters: currentFilters,
      gridState: currentGridState,
      isDefault: newFilterDefault,
      createdAt: now,
      updatedAt: now
    });
    setSaveDialogOpen(false);
  }

  function applySelectedFilter(id: string) {
    if (!id) {
      onClearSelection();
      return;
    }
    const savedFilter = savedFilters.find((filter) => filter.id === id);
    if (savedFilter) {
      onApply(savedFilter);
    }
  }

  function startRename(savedFilter: CandidateQueueSavedFilter) {
    setEditingId(savedFilter.id);
    setEditingName(savedFilter.name);
  }

  function saveRename() {
    const name = editingName.trim();
    if (!editingId || !name) {
      return;
    }
    onRename(editingId, name);
    setEditingId("");
    setEditingName("");
  }

  return (
    <>
      <Stack className="candidate-saved-filter-toolbar" direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
        <TextField
          select
          size="small"
          aria-label="Сохраненный фильтр"
          value={selectedSavedFilterId}
          onChange={(event) => applySelectedFilter(event.target.value)}
          slotProps={{
            select: {
              displayEmpty: true,
              renderValue: (value) => {
                const id = String(value);
                if (!id) {
                  return "Без фильтра";
                }
                const savedFilter = savedFilters.find((filter) => filter.id === id);
                return savedFilter ? `${savedFilter.name}${savedFilter.isDefault ? " · по умолчанию" : ""}` : "Без фильтра";
              }
            }
          }}
          sx={{ minWidth: { xs: 220, sm: 260 } }}
        >
          <MenuItem value="">Без фильтра</MenuItem>
          {savedFilters.map((savedFilter) => (
            <MenuItem key={savedFilter.id} value={savedFilter.id}>
              {savedFilter.name}
              {savedFilter.isDefault ? " · по умолчанию" : ""}
            </MenuItem>
          ))}
        </TextField>
        <Button size="small" variant="outlined" startIcon={<SaveIcon />} onClick={openSaveDialog}>
          Сохранить
        </Button>
        {selectedSavedFilter && (
          <Chip className="candidate-saved-filter-active" size="small" variant="outlined" label={selectedSavedFilter.name} />
        )}
        <Button
          size="small"
          variant="outlined"
          disabled={savedFilters.length === 0}
          onClick={() => setManageDialogOpen(true)}
        >
          Каталог
        </Button>
      </Stack>

      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Сохранить фильтр</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 0.5 }}>
            <TextField
              autoFocus
              fullWidth
              label="Название фильтра"
              value={newFilterName}
              onChange={(event) => setNewFilterName(event.target.value)}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={newFilterDefault}
                  onChange={(event) => setNewFilterDefault(event.target.checked)}
                />
              }
              label="Сделать по умолчанию"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveDialogOpen(false)}>Отмена</Button>
          <Button variant="contained" disabled={!newFilterName.trim()} onClick={saveCurrentFilter}>
            Сохранить фильтр
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={manageDialogOpen} onClose={() => setManageDialogOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Сохраненные фильтры</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.25}>
            {savedFilters.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Сохраненных фильтров нет.
              </Typography>
            ) : (
              savedFilters.map((savedFilter) => (
                <Box key={savedFilter.id} className="candidate-saved-filter-row">
                  <Box sx={{ minWidth: 0 }}>
                    {editingId === savedFilter.id ? (
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                        <TextField
                          fullWidth
                          size="small"
                          label="Название"
                          value={editingName}
                          onChange={(event) => setEditingName(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              saveRename();
                            }
                          }}
                        />
                        <Button size="small" variant="contained" disabled={!editingName.trim()} onClick={saveRename}>
                          Сохранить
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            setEditingId("");
                            setEditingName("");
                          }}
                        >
                          Отмена
                        </Button>
                      </Stack>
                    ) : (
                      <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
                        <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
                          {savedFilter.name}
                        </Typography>
                        {savedFilter.isDefault && <Chip size="small" color="primary" label="По умолчанию" />}
                      </Stack>
                    )}
                    <Typography variant="caption" color="text.secondary">
                      Обновлено {formatSavedFilterDate(savedFilter.updatedAt)}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", justifyContent: "flex-end" }}>
                    <Button size="small" startIcon={<PlayArrowIcon />} onClick={() => onApply(savedFilter)}>
                      Применить
                    </Button>
                    <Tooltip title="Заменить сохраненный фильтр текущими фильтрами и состоянием таблицы">
                      <Button size="small" startIcon={<UpdateIcon />} onClick={() => onUpdateFromCurrent(savedFilter.id)}>
                        Обновить
                      </Button>
                    </Tooltip>
                    <Button
                      size="small"
                      startIcon={<StarIcon />}
                      disabled={savedFilter.isDefault}
                      onClick={() => onSetDefault(savedFilter.id)}
                    >
                      По умолчанию
                    </Button>
                    <Tooltip title="Переименовать">
                      <IconButton size="small" aria-label={`Переименовать ${savedFilter.name}`} onClick={() => startRename(savedFilter)}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Удалить">
                      <IconButton size="small" aria-label={`Удалить ${savedFilter.name}`} onClick={() => onDelete(savedFilter.id)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Box>
              ))
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setManageDialogOpen(false)}>Закрыть</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

function createSavedFilterId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `saved-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function formatSavedFilterDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric"
  });
}
