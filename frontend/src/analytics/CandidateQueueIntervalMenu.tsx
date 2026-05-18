import AccessTimeIcon from "@mui/icons-material/AccessTime";
import { Box, Button, Divider, Menu, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";

import type { CandidateFilters } from "./types";
import { isActivePeriod, periodQuickFilters, periodStartDatetimeLocal } from "./candidateQueueState";

export function CandidateQueueIntervalMenu({
  filters,
  onApply
}: {
  filters: CandidateFilters;
  onApply: (nextFilters: CandidateFilters) => void;
}) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [draftFrom, setDraftFrom] = useState(filters.receivedFrom);
  const [draftTo, setDraftTo] = useState(filters.receivedTo);
  const open = Boolean(anchorEl);

  function openMenu(anchor: HTMLElement) {
    setDraftFrom(filters.receivedFrom);
    setDraftTo(filters.receivedTo);
    setAnchorEl(anchor);
  }

  function applyQuick(hours: number) {
    onApply({
      ...filters,
      receivedFrom: periodStartDatetimeLocal(hours),
      receivedTo: ""
    });
    setAnchorEl(null);
  }

  function applyCustom() {
    onApply({
      ...filters,
      receivedFrom: draftFrom,
      receivedTo: draftTo
    });
    setAnchorEl(null);
  }

  return (
    <>
      <Button
        aria-label={`Интервал времени: ${candidateIntervalButtonLabel(filters)}`}
        size="small"
        variant="outlined"
        startIcon={<AccessTimeIcon fontSize="small" />}
        onClick={(event) => openMenu(event.currentTarget)}
      >
        Интервал: {candidateIntervalButtonLabel(filters)}
      </Button>
      <Menu anchorEl={anchorEl} open={open} onClose={() => setAnchorEl(null)}>
        {periodQuickFilters.map((period) => (
          <MenuItem
            key={period.hours}
            selected={isActivePeriod(filters, period.hours)}
            onClick={() => applyQuick(period.hours)}
          >
            {period.label}
          </MenuItem>
        ))}
        <Divider />
        <Box className="candidate-interval-custom">
          <Stack spacing={1}>
            <TextField
              size="small"
              type="datetime-local"
              label="От"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              size="small"
              type="datetime-local"
              label="До"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <Button size="small" variant="outlined" onClick={applyCustom}>
              Применить интервал
            </Button>
          </Stack>
        </Box>
      </Menu>
    </>
  );
}

export function candidateIntervalChipLabel(filters: CandidateFilters): string {
  const activePeriod = periodQuickFilters.find((period) => isActivePeriod(filters, period.hours));
  if (activePeriod) {
    return activePeriod.chipLabel;
  }
  const from = filters.receivedFrom.trim();
  const to = filters.receivedTo.trim();
  if (from && to) {
    return `${formatDatetimeLocal(from)} - ${formatDatetimeLocal(to)}`;
  }
  if (from) {
    return `с ${formatDatetimeLocal(from)}`;
  }
  if (to) {
    return `до ${formatDatetimeLocal(to)}`;
  }
  return "за все время";
}

function candidateIntervalButtonLabel(filters: CandidateFilters): string {
  const activePeriod = periodQuickFilters.find((period) => isActivePeriod(filters, period.hours));
  if (activePeriod) {
    return activePeriod.label;
  }
  return candidateIntervalChipLabel(filters);
}

function formatDatetimeLocal(value: string): string {
  if (!value.trim()) {
    return "";
  }
  return value.replace("T", " ");
}
