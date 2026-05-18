import {
  DataGrid,
  type DataGridProps,
  type GridLocaleText,
  type GridValidRowModel
} from "@mui/x-data-grid";

import { formatInteger } from "../analytics/analyticsFormat";

export const appDataGridLocaleText: Partial<GridLocaleText> = {
  noRowsLabel: "Нет строк.",
  noResultsOverlayLabel: "Ничего не найдено.",
  toolbarColumns: "Столбцы",
  toolbarFilters: "Фильтры",
  toolbarDensity: "Плотность",
  toolbarExport: "Экспорт",
  toolbarQuickFilterPlaceholder: "Поиск...",
  toolbarQuickFilterLabel: "Поиск",
  columnsManagementSearchTitle: "Найти столбец",
  columnsManagementNoColumns: "Столбцы не найдены",
  columnsManagementShowHideAllText: "Показать/скрыть все",
  columnsManagementReset: "Сбросить",
  filterPanelColumn: "Столбец",
  filterPanelOperator: "Оператор",
  filterPanelInputLabel: "Значение",
  filterPanelInputPlaceholder: "Введите значение",
  filterOperatorContains: "содержит",
  filterOperatorEquals: "равно",
  filterOperatorStartsWith: "начинается с",
  filterOperatorEndsWith: "заканчивается на",
  filterOperatorIs: "равно",
  filterOperatorNot: "не равно",
  filterOperatorAfter: "после",
  filterOperatorOnOrAfter: "после или равно",
  filterOperatorBefore: "до",
  filterOperatorOnOrBefore: "до или равно",
  filterOperatorIsEmpty: "пусто",
  filterOperatorIsNotEmpty: "не пусто",
  filterOperatorIsAnyOf: "любой из",
  columnMenuLabel: "Меню",
  columnMenuSortAsc: "Сортировать по возрастанию",
  columnMenuSortDesc: "Сортировать по убыванию",
  columnMenuFilter: "Фильтр",
  columnMenuHideColumn: "Скрыть",
  columnMenuManageColumns: "Управлять столбцами",
  columnHeaderSortIconLabel: "Сортировка",
  footerRowSelected: (count) => `${formatInteger(count)} выбрано`,
  paginationRowsPerPage: "Строк на странице",
  paginationDisplayedRows: ({ from, to, count }) =>
    `${formatInteger(from)}-${formatInteger(to)} из ${formatInteger(count)}`
};

export function AppDataGrid<R extends GridValidRowModel>({
  className,
  localeText,
  slotProps,
  ...props
}: DataGridProps<R>) {
  return (
    <DataGrid
      disableRowSelectionOnClick
      hideFooterSelectedRowCount
      showToolbar
      {...props}
      className={["app-data-grid", className].filter(Boolean).join(" ")}
      localeText={{ ...appDataGridLocaleText, ...localeText }}
      slotProps={{
        ...slotProps,
        toolbar: {
          showQuickFilter: true,
          quickFilterProps: {
            debounceMs: 450,
            slotProps: {
              root: {
                size: "small"
              }
            }
          },
          ...slotProps?.toolbar
        }
      }}
    />
  );
}
