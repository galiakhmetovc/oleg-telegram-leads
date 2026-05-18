import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import StarIcon from "@mui/icons-material/Star";
import ViewColumnIcon from "@mui/icons-material/ViewColumn";
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
  Stack,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import { useState } from "react";

import type { CandidateColumnConfig, CandidateColumnFieldset } from "./candidateQueueState";

export function CandidateFieldsetControls({
  fieldsets,
  selectedFieldsetId,
  currentColumns,
  onApply,
  onSave,
  onDelete,
  onSetDefault,
  onUpdateFromCurrent,
  onRename
}: {
  fieldsets: CandidateColumnFieldset[];
  selectedFieldsetId: string;
  currentColumns: CandidateColumnConfig[];
  onApply: (fieldset: CandidateColumnFieldset) => void;
  onSave: (fieldset: CandidateColumnFieldset) => void;
  onDelete: (id: string) => void;
  onSetDefault: (id: string) => void;
  onUpdateFromCurrent: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editingName, setEditingName] = useState("");
  void selectedFieldsetId;

  function saveCurrent() {
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    const now = new Date().toISOString();
    onSave({
      id: createFieldsetId(),
      name: trimmed,
      columns: currentColumns,
      isDefault,
      createdAt: now,
      updatedAt: now
    });
    setName("");
    setIsDefault(false);
  }

  function saveRename() {
    const trimmed = editingName.trim();
    if (!editingId || !trimmed) {
      return;
    }
    onRename(editingId, trimmed);
    setEditingId("");
    setEditingName("");
  }

  return (
    <>
      <Button size="small" variant="outlined" startIcon={<ViewColumnIcon fontSize="small" />} onClick={() => setOpen(true)}>
        Наборы полей
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Наборы полей</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5}>
            <Box className="candidate-fieldset-save">
              <TextField
                size="small"
                label="Название набора"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={isDefault}
                    onChange={(event) => setIsDefault(event.target.checked)}
                  />
                }
                label="По умолчанию"
              />
              <Button size="small" variant="contained" startIcon={<SaveIcon fontSize="small" />} disabled={!name.trim()} onClick={saveCurrent}>
                Сохранить текущий набор
              </Button>
            </Box>

            {fieldsets.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Наборов полей пока нет.
              </Typography>
            ) : (
              fieldsets.map((fieldset) => (
                <Box key={fieldset.id} className="candidate-saved-filter-row">
                  <Box sx={{ minWidth: 0 }}>
                    {editingId === fieldset.id ? (
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
                        <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>
                          {fieldset.name}
                        </Typography>
                        {fieldset.isDefault && <Chip size="small" color="primary" label="По умолчанию" />}
                      </Stack>
                    )}
                    <Typography variant="caption" color="text.secondary">
                      {fieldset.columns.filter((column) => column.visible).length} видимых полей
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", justifyContent: "flex-end" }}>
                    <Button size="small" startIcon={<PlayArrowIcon fontSize="small" />} onClick={() => onApply(fieldset)}>
                      Применить
                    </Button>
                    <Button size="small" onClick={() => onUpdateFromCurrent(fieldset.id)}>
                      Обновить
                    </Button>
                    <Button size="small" startIcon={<StarIcon fontSize="small" />} disabled={fieldset.isDefault} onClick={() => onSetDefault(fieldset.id)}>
                      По умолчанию
                    </Button>
                    <Tooltip title="Переименовать">
                      <IconButton
                        size="small"
                        aria-label={`Переименовать набор ${fieldset.name}`}
                        onClick={() => {
                          setEditingId(fieldset.id);
                          setEditingName(fieldset.name);
                        }}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Удалить">
                      <IconButton size="small" aria-label={`Удалить набор ${fieldset.name}`} onClick={() => onDelete(fieldset.id)}>
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
          <Button onClick={() => setOpen(false)}>Закрыть</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

function createFieldsetId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `fieldset-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
