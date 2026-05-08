import type { ReactNode } from "react";

export type AnalyticsRun = {
  id: string;
  name: string;
  source: string;
  input_path: string;
  run_dir: string;
  processed: number;
  skipped: number;
  failed: number;
  leads: number;
  candidate_rate: number;
  started_at?: string | null;
  finished_at?: string | null;
  imported_at: string;
  summary: Record<string, unknown>;
};

export type AnalyticsAggregate = {
  kind: string;
  key: string;
  label: string;
  count: number;
  payload: {
    examples?: string[];
    matched_types?: string[];
    weight?: number;
    [key: string]: unknown;
  };
};

export type AnalyticsSummary = {
  run: AnalyticsRun;
  aggregates: Record<string, AnalyticsAggregate[]>;
};

export type AnalyticsCandidate = {
  message_id: string;
  text: string;
  score: number;
  temperature: string;
  review_lane: string;
  solution_areas: AnalyticsCategory[];
  customer_segments: AnalyticsCategory[];
  intent_signals: AnalyticsCategory[];
  noise_signals: AnalyticsCategory[];
  reasons: AnalyticsReason[];
  domain_signals: AnalyticsSpan[];
  facts: AnalyticsSpan[];
  is_lead?: boolean;
  auto_is_lead?: boolean;
  effective_is_lead?: boolean;
  lead_status_source?: "auto" | "review";
  received_at?: string | null;
  source_chat_id?: string | null;
  source_chat_title?: string | null;
  telegram_message_id?: number | null;
  telegram_message_url?: string | null;
  app_message_url?: string | null;
  testing_url?: string | null;
  enrichment_job_id?: string | null;
  review?: AnalyticsMessageReview | null;
};

export type AnalyticsReviewVerdict = "lead" | "not_lead" | "uncertain" | "noise";

export type AnalyticsMessageReview = {
  source_message_id: string;
  verdict: AnalyticsReviewVerdict | null;
  comment: string;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type AnalyticsCategory = {
  type: string;
  label?: string;
  matched_types?: string[];
};

export type AnalyticsReason = {
  source: string;
  key: string;
  label?: string;
  weight: number;
  matched_texts: string[];
};

export type AnalyticsSpan = {
  type: string;
  label?: string;
  text?: string;
  range?: TextRange | null;
  source?: string;
  color?: string | null;
  confidence?: number | null;
  settings_refs?: SettingReference[];
};

export type SettingReference = {
  section: string;
  key: string;
  label: string;
  catalog?: string | null;
  kind?: string;
};

export type TextRange = {
  start: number;
  stop: number;
};

export type CandidatePage = {
  total: number;
  limit: number;
  offset: number;
  items: AnalyticsCandidate[];
};

export type CandidateFilters = {
  scoreMin: string;
  temperature: string;
  signal: string;
  reason: string;
  solutionArea: string;
  customerSegment: string;
  lane: string;
  sourceChatId: string;
  receivedFrom: string;
  receivedTo: string;
  reviewStatus: string;
  verdict: string;
  q: string;
};

export type AnalyticsSummaryBlockKey = "score" | "signals" | "reasons" | "segments" | "lanes";
export type AliasCatalogName = "vendors" | "protocols" | "devices" | "software";

export type AnalyticsSettingsTarget =
  | { kind: "signal"; key: string }
  | { kind: "fact"; key: string }
  | { kind: "alias"; catalog: AliasCatalogName; key: string }
  | { kind: "lead_signal_weight"; key: string }
  | { kind: "lead_fact_weight"; key: string }
  | { kind: "solution_area"; key: string }
  | { kind: "customer_segment"; key: string }
  | { kind: "review_lane"; key: string };

export type AnalyticsSettingsLink = {
  label: ReactNode;
  target: AnalyticsSettingsTarget | null;
};
