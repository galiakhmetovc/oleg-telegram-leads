import { routeParts } from "../routes";

export type AliasCatalogName = "vendors" | "protocols" | "devices" | "software";

export type SettingsSection =
  | "pipeline"
  | "signals"
  | "facts"
  | "aliases"
  | "lead_scoring"
  | "solution_areas"
  | "review_lanes"
  | "dependency_graph"
  | "llm"
  | "notifications"
  | "telegram_ingestion"
  | "system";

export type SettingsTarget =
  | { kind: "signal"; key: string }
  | { kind: "fact"; key: string }
  | { kind: "alias"; catalog: AliasCatalogName; key: string }
  | { kind: "lead_signal_weight"; key: string }
  | { kind: "lead_fact_weight"; key: string }
  | { kind: "solution_area"; key: string }
  | { kind: "customer_segment"; key: string }
  | { kind: "review_lane"; key: string };

export const openSettingsTargetEvent = "pur-open-settings-target";

export function isAliasCatalogName(value: string | null | undefined): value is AliasCatalogName {
  return value === "vendors" || value === "protocols" || value === "devices" || value === "software";
}

export function settingsTargetHash(target: SettingsTarget | null): string {
  if (!target) {
    return "";
  }
  if (target.kind === "signal") {
    return `/settings/signals/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "fact") {
    return `/settings/facts/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "alias") {
    return `/settings/aliases/${target.catalog}/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "lead_signal_weight") {
    return `/settings/lead-scoring/signal-weight/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "lead_fact_weight") {
    return `/settings/lead-scoring/fact-weight/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "solution_area") {
    return `/settings/solution-areas/${encodeURIComponent(target.key)}`;
  }
  if (target.kind === "customer_segment") {
    return `/settings/lead-scoring/customer-segment/${encodeURIComponent(target.key)}`;
  }
  return `/settings/review-lanes/${encodeURIComponent(target.key)}`;
}

export function settingsTargetElementId(target: SettingsTarget): string {
  if (target.kind === "signal") {
    return `settings-target-signals-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "fact") {
    return `settings-target-facts-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "alias") {
    return `settings-target-aliases-${target.catalog}-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "lead_signal_weight") {
    return `settings-target-lead-scoring-signal-weight-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "lead_fact_weight") {
    return `settings-target-lead-scoring-fact-weight-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "solution_area") {
    return `settings-target-lead-scoring-solution-area-${settingsTargetIdPart(target.key)}`;
  }
  if (target.kind === "customer_segment") {
    return `settings-target-lead-scoring-customer-segment-${settingsTargetIdPart(target.key)}`;
  }
  return `settings-target-lead-scoring-review-lane-${settingsTargetIdPart(target.key)}`;
}

export function settingsTargetIdPart(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_");
}

export function parseSettingsTargetHash(route: string): SettingsTarget | null {
  const parts = routeParts(route);
  if (parts[0] !== "settings") {
    return null;
  }
  if (parts[1] === "signals" && parts[2]) {
    return { kind: "signal", key: parts[2] };
  }
  if (parts[1] === "facts" && parts[2]) {
    return { kind: "fact", key: parts[2] };
  }
  if (parts[1] === "aliases" && isAliasCatalogName(parts[2]) && parts[3]) {
    return { kind: "alias", catalog: parts[2], key: parts[3] };
  }
  if (parts[1] === "solution-areas" && parts[2]) {
    return { kind: "solution_area", key: parts[2] };
  }
  if (parts[1] === "review-lanes" && parts[2]) {
    return { kind: "review_lane", key: parts[2] };
  }
  if (parts[1] === "lead-scoring" && parts[3]) {
    if (parts[2] === "signal-weight") {
      return { kind: "lead_signal_weight", key: parts[3] };
    }
    if (parts[2] === "fact-weight") {
      return { kind: "lead_fact_weight", key: parts[3] };
    }
    if (parts[2] === "solution-area") {
      return { kind: "solution_area", key: parts[3] };
    }
    if (parts[2] === "customer-segment") {
      return { kind: "customer_segment", key: parts[3] };
    }
    if (parts[2] === "review-lane") {
      return { kind: "review_lane", key: parts[3] };
    }
  }
  return null;
}
