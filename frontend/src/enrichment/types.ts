export type TextRange = {
  start: number;
  stop: number;
};

export type SpanItem = {
  id: string;
  text: string;
  type: string;
  label?: string;
  range: TextRange;
  source: string;
  span_id?: string | null;
  sentence_id?: string | null;
  derived_from_fact_id?: string | null;
  source_fact_ids?: string[];
  confidence?: number | null;
  color?: string | null;
  explanation?: string | null;
  settings_refs?: SettingReference[];
};

export type SettingReference = {
  section: string;
  key: string;
  label: string;
  kind: string;
  catalog?: string | null;
};

export type EnrichedToken = {
  id: string;
  text: string;
  lemma?: string | null;
  pos?: string | null;
  range: TextRange;
  features: Record<string, string>;
};

export type SyntaxDependency = {
  token_id: string;
  head_id?: string | null;
  relation?: string | null;
};

export type PipelineTraceItem = {
  stage: string;
  status: string;
  message: string;
  progress_percent: number;
};

export type LeadCategory = {
  type: string;
  label: string;
  matched_types: string[];
};

export type LeadReason = {
  source: string;
  key: string;
  label: string;
  weight: number;
  matched_texts: string[];
};

export type LeadAssessment = {
  is_lead: boolean;
  score: number;
  temperature: string;
  solution_areas: LeadCategory[];
  customer_segments: LeadCategory[];
  intent_signals: LeadCategory[];
  noise_signals: LeadCategory[];
  reasons: LeadReason[];
  review_lane?: LeadReviewLane | null;
};

export type LeadReviewLane = {
  key: string;
  label: string;
  description?: string | null;
  matched_group_indexes: number[];
};

export type TextEnrichmentResult = {
  original_text: string;
  normalized_text: string;
  entities: SpanItem[];
  facts: SpanItem[];
  domain_signals: SpanItem[];
  tokens: EnrichedToken[];
  syntax: SyntaxDependency[];
  metrics: Record<string, number>;
  pipeline_trace: PipelineTraceItem[];
  lead_assessment?: LeadAssessment | null;
};

export type EnrichmentJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress_percent: number;
  current_stage?: string | null;
  stage_index: number;
  stage_count: number;
  stage_progress_percent: number;
  message: string;
  result?: TextEnrichmentResult | null;
  error?: { type?: string; message?: string } | null;
  nlp_config_revision_id?: string | null;
  nlp_config_revision?: number | null;
};

export type EnrichmentEvent = {
  event_type: string;
  progress_percent: number;
  current_stage?: string | null;
  stage_index: number;
  stage_count: number;
  stage_progress_percent: number;
  message: string;
  payload?: {
    result?: TextEnrichmentResult;
    error?: { type?: string; message?: string };
  };
};
