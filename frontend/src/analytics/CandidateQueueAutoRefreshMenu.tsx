import AutorenewIcon from "@mui/icons-material/Autorenew";
import { Button, Menu, MenuItem } from "@mui/material";
import { useState } from "react";

export const autoRefreshOptions = [
  { label: "выкл", seconds: 0 },
  { label: "30 сек", seconds: 30 },
  { label: "1 мин", seconds: 60 },
  { label: "5 мин", seconds: 300 },
  { label: "15 мин", seconds: 900 }
];

export function CandidateQueueAutoRefreshMenu({
  value,
  onChange
}: {
  value: number;
  onChange: (seconds: number) => void;
}) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const active = autoRefreshOptions.find((option) => option.seconds === value) ?? autoRefreshOptions[0];

  return (
    <>
      <Button
        aria-label={`Автообновление: ${active.label}`}
        size="small"
        variant="outlined"
        startIcon={<AutorenewIcon fontSize="small" />}
        onClick={(event) => setAnchorEl(event.currentTarget)}
      >
        Авто: {active.label}
      </Button>
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
        {autoRefreshOptions.map((option) => (
          <MenuItem
            key={option.seconds}
            selected={option.seconds === value}
            onClick={() => {
              onChange(option.seconds);
              setAnchorEl(null);
            }}
          >
            {option.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

export function autoRefreshLabel(seconds: number): string {
  return autoRefreshOptions.find((option) => option.seconds === seconds)?.label ?? `${seconds} сек`;
}
