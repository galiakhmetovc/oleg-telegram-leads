import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import { Divider, ListItemIcon, ListItemText, Menu, MenuItem } from "@mui/material";

import type { CandidateGridColumnFilter, CandidateValueFilterRequest } from "./candidateQueueState";

export function CandidateValueFilterMenu({
  anchorEl,
  request,
  onApply,
  onClose
}: {
  anchorEl: HTMLElement | null;
  request: CandidateValueFilterRequest | null;
  onApply: (filter: CandidateGridColumnFilter) => void;
  onClose: () => void;
}) {
  const open = Boolean(anchorEl && request);
  const label = request?.label || request?.value || "";

  function apply(operator: string) {
    if (!request) {
      return;
    }
    onApply({ field: request.field, operator, value: request.value });
    onClose();
  }

  async function copyValue() {
    if (request?.value && navigator.clipboard) {
      await navigator.clipboard.writeText(request.value);
    }
    onClose();
  }

  const operators = request?.numeric
    ? [
        { operator: "equals", primary: "Фильтровать по этому значению", secondary: `= ${label}` },
        { operator: "notEquals", primary: "Не равно", secondary: `!= ${label}` },
        { operator: ">", primary: "Больше", secondary: `> ${label}` },
        { operator: ">=", primary: "Больше или равно", secondary: `>= ${label}` },
        { operator: "<", primary: "Меньше", secondary: `< ${label}` },
        { operator: "<=", primary: "Меньше или равно", secondary: `<= ${label}` }
      ]
    : [
        { operator: "equals", primary: "Фильтровать по этому значению", secondary: `= ${label}` },
        { operator: "notEquals", primary: "Не равно", secondary: `!= ${label}` },
        { operator: "contains", primary: "Содержит", secondary: label },
        { operator: "notContains", primary: "Не содержит", secondary: label }
      ];

  return (
    <Menu anchorEl={anchorEl} open={open} onClose={onClose}>
      {operators.map((item) => (
        <MenuItem key={item.operator} dense onClick={() => apply(item.operator)}>
          <ListItemIcon>
            <FilterAltIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={item.primary} secondary={item.secondary} />
        </MenuItem>
      ))}
      <Divider />
      <MenuItem dense onClick={() => void copyValue()}>
        <ListItemIcon>
          <ContentCopyIcon fontSize="small" />
        </ListItemIcon>
        <ListItemText primary="Скопировать" secondary={label} />
      </MenuItem>
    </Menu>
  );
}
