import { beforeEach, describe, expect, it } from "vitest";

import {
  candidateQuery,
  candidateRouteHasExplicitFilters,
  deleteCandidateFieldset,
  defaultCandidateFilters,
  deleteCandidateSavedFilter,
  initialCandidateQueueStateFromSearchParams,
  loadCandidateFieldsets,
  loadCandidateSavedFilters,
  saveCandidateFieldsets,
  saveCandidateSavedFilters,
  upsertCandidateFieldset,
  type CandidateColumnFieldset,
  upsertCandidateSavedFilter,
  type CandidateQueueSavedFilter
} from "./candidateQueueState";
import { parseAnalyticsUrlState } from "./analyticsRoutes";

const savedFiltersStorageKey = "pur-leads.analytics.saved-filters.v1";
const fieldsetsStorageKey = "pur-leads.analytics.fieldsets.v1";

beforeEach(() => {
  window.localStorage.clear();
});

describe("candidateQuery", () => {
  it("serializes DataGrid sort, column filters, and quick search", () => {
    const filters = {
      ...defaultCandidateFilters(),
      receivedFrom: "",
      reviewStatus: "",
      q: ""
    };

    const query = candidateQuery(filters, 50, 100, {
      sort: { field: "score", direction: "asc" },
      columnFilters: [
        { field: "sourceChat", operator: "contains", value: "дизайнер" },
        { field: "sender", operator: "contains", value: "@ivan" },
        { field: "telegramMessageId", operator: "equals", value: "12345" },
        { field: "llmConfidence", operator: ">=", value: "0.7" },
        { field: "enrichmentStatus", operator: "equals", value: "completed" }
      ],
      quickFilter: "домофон"
    });
    const params = new URLSearchParams(query);

    expect(params.get("limit")).toBe("50");
    expect(params.get("offset")).toBe("100");
    expect(params.get("sort_by")).toBe("score");
    expect(params.get("sort_direction")).toBe("asc");
    expect(params.get("source_chat")).toBe("дизайнер");
    expect(params.get("sender")).toBe("@ivan");
    expect(params.get("telegram_message_id")).toBe("12345");
    expect(params.get("llm_confidence_min")).toBe("0.7");
    expect(params.get("enrichment_status")).toBe("completed");
    expect(params.get("q")).toBe("домофон");
    expect(params.getAll("grid_filter").map((value) => JSON.parse(value))).toContainEqual({
      field: "llmConfidence",
      operator: ">=",
      value: "0.7"
    });
  });

  it("serializes negative grid filters without legacy positive params", () => {
    const filters = {
      ...defaultCandidateFilters(),
      receivedFrom: "",
      reviewStatus: "",
      q: ""
    };

    const query = candidateQuery(filters, 50, 0, {
      sort: null,
      columnFilters: [{ field: "sourceChat", operator: "notEquals", value: "spam" }],
      quickFilter: ""
    });
    const params = new URLSearchParams(query);

    expect(params.get("source_chat")).toBeNull();
    expect(params.getAll("grid_filter").map((value) => JSON.parse(value))).toEqual([
      { field: "sourceChat", operator: "notEquals", value: "spam" }
    ]);
  });

  it("keeps the advanced text filter ahead of the DataGrid quick search", () => {
    const filters = {
      ...defaultCandidateFilters(),
      receivedFrom: "",
      reviewStatus: "",
      q: "электрика"
    };

    const query = candidateQuery(filters, 50, 0, {
      sort: null,
      columnFilters: [],
      quickFilter: "домофон"
    });
    const params = new URLSearchParams(query);

    expect(params.get("q")).toBe("электрика");
  });
});

describe("candidate saved filters", () => {
  it("returns no saved filters for empty or malformed localStorage", () => {
    expect(loadCandidateSavedFilters()).toEqual([]);

    window.localStorage.setItem(savedFiltersStorageKey, "{\"not\":\"a list\"}");

    expect(loadCandidateSavedFilters()).toEqual([]);
  });

  it("upserts saved filters and keeps only the new default", () => {
    const existing = [savedFilter("cold", "Холодные", true, { temperature: "cold" })];

    const next = upsertCandidateSavedFilter(
      existing,
      savedFilter("llm", "LLM lead", true, { llmVerdict: "lead" })
    );

    expect(next).toHaveLength(2);
    expect(next.find((item) => item.id === "cold")?.isDefault).toBe(false);
    expect(next.find((item) => item.id === "llm")?.isDefault).toBe(true);
  });

  it("deleting the default saved filter leaves no custom default", () => {
    const next = deleteCandidateSavedFilter(
      [
        savedFilter("cold", "Холодные", true, { temperature: "cold" }),
        savedFilter("hot", "Горячие", false, { temperature: "hot" })
      ],
      "cold"
    );

    expect(next).toHaveLength(1);
    expect(next[0].id).toBe("hot");
    expect(next[0].isDefault).toBe(false);
  });

  it("applies the local default only when the route has no explicit queue filters", () => {
    saveCandidateSavedFilters([
      savedFilter("default-cold", "Холодные LLM lead", true, {
        receivedFrom: "2026-05-08T10:00",
        temperature: "cold",
        llmVerdict: "lead",
        reviewStatus: "unreviewed"
      }, {
        sort: { field: "receivedAt", direction: "desc" },
        columnFilters: [{ field: "llmVerdict", operator: "equals", value: "lead" }],
        quickFilter: "домофон"
      })
    ]);

    const defaultState = initialCandidateQueueStateFromSearchParams(new URLSearchParams("run=live"));

    expect(candidateRouteHasExplicitFilters(new URLSearchParams("run=live"))).toBe(false);
    expect(defaultState.filters.temperature).toBe("cold");
    expect(defaultState.filters.llmVerdict).toBe("lead");
    expect(defaultState.grid.quickFilter).toBe("домофон");
    expect(defaultState.grid.sort).toEqual({ field: "receivedAt", direction: "desc" });

    const explicitState = initialCandidateQueueStateFromSearchParams(
      new URLSearchParams("run=live&temperature=hot")
    );

    expect(candidateRouteHasExplicitFilters(new URLSearchParams("run=live&temperature=hot"))).toBe(true);
    expect(explicitState.filters.temperature).toBe("hot");
    expect(explicitState.filters.llmVerdict).toBe("");
    expect(explicitState.grid.quickFilter).toBe("");
  });

  it("uses the saved default from analytics route parsing unless the route has filters", () => {
    saveCandidateSavedFilters([
      savedFilter("default-cold", "Холодные LLM lead", true, {
        temperature: "cold",
        llmVerdict: "lead"
      })
    ]);

    const defaultRouteState = parseAnalyticsUrlState("/analytics?run=live");
    const explicitRouteState = parseAnalyticsUrlState("/analytics?run=live&temperature=hot");

    expect(defaultRouteState.filters.temperature).toBe("cold");
    expect(defaultRouteState.filters.llmVerdict).toBe("lead");
    expect(explicitRouteState.filters.temperature).toBe("hot");
    expect(explicitRouteState.filters.llmVerdict).toBe("");
  });
});

describe("candidate fieldsets", () => {
  it("stores column visibility presets and keeps only one default", () => {
    const compact = fieldset("compact", "Компактный", true, [
      { key: "sourceType", visible: true, width: 120 },
      { key: "text", visible: true, width: 420 }
    ]);
    const llm = fieldset("llm", "LLM", true, [
      { key: "sourceType", visible: true, width: 120 },
      { key: "llmVerdict", visible: true, width: 140 },
      { key: "llmConfidence", visible: true, width: 140 },
      { key: "text", visible: true, width: 420 }
    ]);

    saveCandidateFieldsets(upsertCandidateFieldset([compact], llm));

    const saved = loadCandidateFieldsets();
    expect(saved).toHaveLength(2);
    expect(saved.find((item) => item.id === "compact")?.isDefault).toBe(false);
    expect(saved.find((item) => item.id === "llm")?.isDefault).toBe(true);
    expect(saved.find((item) => item.id === "llm")?.columns.map((column) => column.key)).toContain("llmVerdict");
  });

  it("deletes fieldsets without touching column defaults", () => {
    saveCandidateFieldsets([
      fieldset("compact", "Компактный", true, [{ key: "sourceType", visible: true, width: 120 }]),
      fieldset("wide", "Широкий", false, [{ key: "text", visible: true, width: 500 }])
    ]);

    const next = deleteCandidateFieldset(loadCandidateFieldsets(), "compact");

    expect(next).toHaveLength(1);
    expect(next[0].id).toBe("wide");
    expect(next[0].isDefault).toBe(false);
  });
});

function savedFilter(
  id: string,
  name: string,
  isDefault: boolean,
  filterPatch: Partial<ReturnType<typeof defaultCandidateFilters>>,
  gridState: CandidateQueueSavedFilter["gridState"] = {
    sort: null,
    columnFilters: [],
    quickFilter: ""
  }
): CandidateQueueSavedFilter {
  return {
    id,
    name,
    filters: {
      ...defaultCandidateFilters(),
      receivedFrom: "",
      reviewStatus: "",
      ...filterPatch
    },
    gridState,
    isDefault,
    createdAt: "2026-05-15T09:00:00.000Z",
    updatedAt: "2026-05-15T09:00:00.000Z"
  };
}

function fieldset(
  id: string,
  name: string,
  isDefault: boolean,
  columns: CandidateColumnFieldset["columns"]
): CandidateColumnFieldset {
  return {
    id,
    name,
    columns,
    isDefault,
    createdAt: "2026-05-15T09:00:00.000Z",
    updatedAt: "2026-05-15T09:00:00.000Z"
  };
}
