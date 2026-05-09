export type PipelineStageSetting = {
  name: string;
  enabled: boolean;
};

export type PatternTokenSetting = {
  predicate: "normalized";
  value: string;
};

export type RulePatternSetting = {
  source_text?: string | null;
  tokens: PatternTokenSetting[];
};

export type FactMatchSetting = {
  types: string[];
};

export type RuleMatchSetting = {
  facts: FactMatchSetting[];
};

export type SemanticPatternResponse = {
  source_text: string;
  lemma_text: string;
  tokens: PatternTokenSetting[];
};

export type RuleSetting = {
  type: string;
  label: string;
  group?: string | null;
  phrases: string[][];
  patterns: RulePatternSetting[];
  match?: RuleMatchSetting;
  color?: string | null;
  confidence?: number | null;
};

export type AliasSetting = {
  key: string;
  canonical: string;
  type: "vendor" | "protocol" | "device" | "software" | "model";
  aliases: string[];
  fact_types: string[];
  color?: string | null;
  confidence?: number | null;
};

export type LeadCategorySetting = {
  label: string;
  signal_types: string[];
  fact_types: string[];
};

export type ReviewLaneMatchGroupSetting = {
  signal_types: string[];
  fact_types: string[];
  reason_keys: string[];
  solution_area_types: string[];
  customer_segment_types: string[];
  intent_signal_types: string[];
  noise_signal_types: string[];
};

export type ReviewLaneSetting = {
  key: string;
  label: string;
  description?: string | null;
  priority: number;
  min_score?: number | null;
  max_score?: number | null;
  temperatures: string[];
  match_groups: ReviewLaneMatchGroupSetting[];
  excluded_signal_types: string[];
  excluded_fact_types: string[];
  excluded_reason_keys: string[];
  excluded_solution_area_types: string[];
  excluded_customer_segment_types: string[];
  excluded_intent_signal_types: string[];
  excluded_noise_signal_types: string[];
};

export type LeadScoreCapSetting = {
  key: string;
  label: string;
  max_score: number;
  signal_types: string[];
  fact_types: string[];
  reason_keys: string[];
  noise_signal_types: string[];
  excluded_signal_types: string[];
  excluded_fact_types: string[];
  excluded_reason_keys: string[];
  excluded_noise_signal_types: string[];
};

export type LeadScoringSettings = {
  lead_threshold: number;
  warm_threshold: number;
  hot_threshold: number;
  signal_weights: Record<string, number>;
  fact_weights: Record<string, number>;
  solution_areas: Record<string, LeadCategorySetting>;
  customer_segments: Record<string, LeadCategorySetting>;
  intent_signal_types: string[];
  noise_signal_types: string[];
  lead_veto_signal_types: string[];
  score_caps: LeadScoreCapSetting[];
  review_lanes: ReviewLaneSetting[];
};

export type AliasMatchingSettings = {
  normalize_separators: boolean;
  normalize_yo: boolean;
  normalize_latin_confusables: boolean;
  fuzzy_enabled: boolean;
  fuzzy_min_length: number;
  fuzzy_max_distance: number;
  fuzzy_long_min_length: number;
  fuzzy_long_max_distance: number;
  fuzzy_excluded_aliases: string[];
};

export type NlpSettings = {
  pipeline: {
    stages: PipelineStageSetting[];
  };
  alias_matching?: AliasMatchingSettings;
  signals: RuleSetting[];
  facts: RuleSetting[];
  vendors: AliasSetting[];
  protocols: AliasSetting[];
  devices: AliasSetting[];
  software: AliasSetting[];
  lead_scoring: LeadScoringSettings;
  source?: {
    type: string;
    path: string;
    editable: boolean;
    revision?: number;
  };
};

export type SystemSetting = {
  key: string;
  value: string;
  editable: boolean;
  sensitive?: boolean;
  source: string;
};

export type TelegramBotSettings = {
  id: string;
  name: string;
  enabled: boolean;
  has_token: boolean;
  token_masked?: string | null;
  token?: string;
};

export type TelegramChatSettings = {
  id: string;
  name: string;
  enabled: boolean;
  telegram_chat_id: string;
};

export type NotificationRouteConditions = {
  is_lead?: boolean | null;
  score_min?: number | null;
  score_max?: number | null;
  temperatures: string[];
  review_lanes: string[];
  solution_areas: string[];
  customer_segments: string[];
  domain_signals: string[];
  facts: string[];
  reasons: string[];
  noise_signals: string[];
};

export type NotificationRouteSettings = {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  bot_id: string;
  chat_id: string;
  match_mode: "all" | "any";
  conditions: NotificationRouteConditions;
  message_template: string;
};

export type NotificationSettings = {
  bots: TelegramBotSettings[];
  chats: TelegramChatSettings[];
  routes: NotificationRouteSettings[];
  updated_at?: string | null;
};

export type TelegramUserbotAccountSettings = {
  id: string;
  name: string;
  phone: string;
  api_id: number;
  enabled: boolean;
  status: string;
  has_api_hash: boolean;
  api_hash_masked?: string | null;
  has_session: boolean;
  last_error?: string | null;
  cooldown_until?: string | null;
  telegram_user_id?: string | null;
  telegram_username?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  api_hash?: string;
  session_string?: string;
};

export type TelegramSourceChatSettings = {
  id: string;
  account_id: string;
  title: string;
  input_ref: string;
  telegram_chat_id?: string | null;
  enabled: boolean;
  status: string;
  last_message_id?: number | null;
  last_error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type TelegramIngestionSettings = {
  accounts: TelegramUserbotAccountSettings[];
  chats: TelegramSourceChatSettings[];
};

export type SettingsSnapshot = {
  nlp: NlpSettings;
  notifications: NotificationSettings;
  telegram_ingestion: TelegramIngestionSettings;
  system: SystemSetting[];
};
