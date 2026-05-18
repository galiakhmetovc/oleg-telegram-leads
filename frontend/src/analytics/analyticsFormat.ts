import type { AnalyticsAggregate } from "./types";

const numberFormatter = new Intl.NumberFormat("ru-RU");

export function formatInteger(value: number) {
  return numberFormatter.format(value);
}

export function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

export function formatRatioPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function aggregateDetail(item: AnalyticsAggregate) {
  const parts: string[] = [];
  if (item.label && item.label !== item.key) {
    parts.push(item.key);
  }
  if (item.payload.examples && item.payload.examples.length > 0) {
    parts.push(item.payload.examples.slice(0, 3).join(", "));
  }
  return parts.join(" · ");
}

export function prettyJson(value: unknown): string {
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}

export function parseJsonObject(value: unknown): Record<string, unknown> | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function formatLlmTimeout(timeoutSeconds?: number): string {
  if (typeof timeoutSeconds !== "number" || Number.isNaN(timeoutSeconds)) {
    return "неизвестен";
  }
  return `${timeoutSeconds}s`;
}
