import type { CandidateFilters } from "./types";
import {
  candidateQuery,
  defaultCandidateGridState,
  initialCandidateQueueStateFromSearchParams,
  type CandidateGridQueryState
} from "./candidateQueueState";
import { currentRoute, replaceRoute, routeParts, routeQuery, routeWithoutQuery } from "../routes";

export const candidatePageSize = 50;

export type AnalyticsSection = "candidates" | "overview" | "quality" | "llm";
export type AnalyticsSectionScope = "workspace" | "reports" | undefined;

export type AnalyticsUrlState = {
  runId: string;
  offset: number;
  filters: CandidateFilters;
  grid: CandidateGridQueryState;
};

export function parseAnalyticsUrlState(route: string): AnalyticsUrlState {
  const params = routeQuery(route);
  const initialQueueState = initialCandidateQueueStateFromSearchParams(params);
  return {
    runId: params.get("run")?.trim() ?? "",
    offset: Math.max(0, Number(params.get("offset") ?? "0") || 0),
    filters: initialQueueState.filters,
    grid: initialQueueState.grid
  };
}

export function parseAnalyticsSection(route: string): AnalyticsSection {
  const parts = routeParts(route);
  if (parts[0] !== "analytics") {
    return "candidates";
  }
  if (parts[1] === "overview") {
    return "overview";
  }
  if (parts[1] === "quality") {
    return "quality";
  }
  if (parts[1] === "llm") {
    return "llm";
  }
  return "candidates";
}

export function effectiveAnalyticsSection(
  section: AnalyticsSection,
  scope: AnalyticsSectionScope
): AnalyticsSection {
  if (scope === "workspace") {
    return "candidates";
  }
  if (scope === "reports" && section === "candidates") {
    return "overview";
  }
  return section;
}

export function analyticsSectionHash(
  section: AnalyticsSection,
  filters: CandidateFilters,
  offset: number,
  runId: string,
  gridState: CandidateGridQueryState = defaultCandidateGridState
): string {
  if (section === "candidates") {
    return analyticsListHash(filters, offset, runId, gridState);
  }
  const params = new URLSearchParams();
  if (runId) {
    params.set("run", runId);
  }
  const route = section === "overview" ? "overview" : section === "quality" ? "quality" : "llm";
  return `/analytics/${route}${params.toString() ? `?${params.toString()}` : ""}`;
}

export function analyticsListHash(
  filters: CandidateFilters,
  offset: number,
  runId: string,
  gridState: CandidateGridQueryState = defaultCandidateGridState
): string {
  const query = candidateQuery(filters, candidatePageSize, offset, gridState);
  const params = new URLSearchParams(query);
  if (runId) {
    params.set("run", runId);
  }
  return `/analytics${params.toString() ? `?${params.toString()}` : ""}`;
}

export function replaceAnalyticsSectionHash(
  section: AnalyticsSection,
  filters: CandidateFilters,
  offset: number,
  runId: string,
  gridState: CandidateGridQueryState = defaultCandidateGridState
) {
  if (!routeWithoutQuery(currentRoute()).startsWith("/analytics")) {
    return;
  }
  replaceRoute(analyticsSectionHash(section, filters, offset, runId, gridState));
}

export function replaceAnalyticsListHash(
  filters: CandidateFilters,
  offset: number,
  runId: string,
  gridState: CandidateGridQueryState = defaultCandidateGridState
) {
  if (!routeWithoutQuery(currentRoute()).startsWith("/analytics")) {
    return;
  }
  replaceRoute(analyticsListHash(filters, offset, runId, gridState));
}

export function analyticsReviewHash(messageId: string, returnHash: string) {
  return `/review/${encodeURIComponent(messageId)}?return=${encodeURIComponent(returnHash)}`;
}
