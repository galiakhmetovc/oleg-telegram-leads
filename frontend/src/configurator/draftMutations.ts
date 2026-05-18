import type { AliasCatalogName } from "../settings/navigation";
import type { AliasSetting, NlpSettings, RulePatternSetting, RuleSetting } from "../settings/types";

export type ConstructorPhraseKind = "exact" | "semantic";

export type AliasDraftInput = {
  text: string;
  catalog: AliasCatalogName;
  key: string;
  canonical: string;
  alias_type: AliasSetting["type"];
  fact_types: string[];
  confidence: number | null;
  color: string | null;
};

export type FactDraftInput = {
  text: string;
  target_type: string;
  target_label: string;
  group: string;
  phrase_kind: ConstructorPhraseKind;
  confidence: number | null;
  color: string | null;
  semantic_pattern?: RulePatternSetting | null;
};

export type SignalDraftInput = {
  type: string;
  label: string;
  group: string;
  fact_types: string[];
  confidence: number | null;
  color: string | null;
  score_weight: number;
};

const OPERATOR_NOISE_SIGNAL_TYPE = "operator_noise";
const OPERATOR_NOISE_SIGNAL_LABEL = "Операторский шум";
const OPERATOR_NOISE_FACT_TYPE = "operator_noise_fact";
const OPERATOR_NOISE_FACT_LABEL = "Факт: операторский шум";
const OPERATOR_NOISE_SIGNAL_GROUP = "Шум / ручная разметка";
const OPERATOR_NOISE_SIGNAL_WEIGHT = -50;
const HARD_NOISE_SCORE_CAP_KEY = "hard_noise";
const HARD_NOISE_SCORE_CAP_LABEL = "Явный шум / нецелевой запрос";

export function constructorKeyFromText(text: string): string {
  const normalized = text
    .trim()
    .toLocaleLowerCase("ru-RU")
    .replace(/[^\p{L}\p{N}]+/gu, "_")
    .replace(/^_+|_+$/g, "");
  return normalized || "operator_rule";
}

export function defaultAliasTypeForCatalog(catalog: AliasCatalogName): Exclude<AliasSetting["type"], "model"> {
  if (catalog === "protocols") {
    return "protocol";
  }
  if (catalog === "devices") {
    return "device";
  }
  if (catalog === "software") {
    return "software";
  }
  return "vendor";
}

export function exactPhraseTokens(text: string): string[] {
  const matches = text.match(/[\p{L}\p{N}._+-]+/gu) ?? [];
  const tokens = matches
    .map((token) => token.replace(/^[._+-]+|[._+-]+$/g, "").toLocaleLowerCase("ru-RU"))
    .filter(Boolean);
  if (tokens.length === 0) {
    throw new Error("Выделенный текст должен содержать хотя бы одно слово или число");
  }
  return tokens;
}

export function factDependencyTypes(rule: RuleSetting): string[] {
  return uniqueStrings((rule.match?.facts ?? []).flatMap((dependency) => dependency.types ?? []));
}

export function applyAliasDraft(current: NlpSettings, input: AliasDraftInput): NlpSettings {
  const aliasText = requireText(input.text, "Выделенный текст не должен быть пустым");
  const key = requireKey(input.key, "key не должен быть пустым");
  const catalogItems = [...current[input.catalog]];
  const existingIndex = catalogItems.findIndex((alias) => alias.key === key);
  const existing = existingIndex >= 0 ? catalogItems[existingIndex] : null;
  const nextAlias: AliasSetting = {
    key,
    canonical: input.canonical.trim() || aliasText,
    type: input.alias_type,
    aliases: uniqueCasefold([...(existing?.aliases ?? []), aliasText]),
    fact_types: uniqueStrings(input.fact_types.map((item) => item.trim()).filter(Boolean)),
    color: input.color ?? existing?.color ?? null,
    confidence: input.confidence ?? existing?.confidence ?? null
  };

  if (existingIndex >= 0) {
    catalogItems[existingIndex] = nextAlias;
  } else {
    catalogItems.push(nextAlias);
  }

  return {
    ...current,
    [input.catalog]: catalogItems
  };
}

export function applyFactDraft(current: NlpSettings, input: FactDraftInput): NlpSettings {
  const selectedText = requireText(input.text, "Выделенный текст не должен быть пустым");
  const type = requireKey(input.target_type, "type не должен быть пустым");
  const existingIndex = current.facts.findIndex((rule) => rule.type === type);
  const existing = existingIndex >= 0 ? current.facts[existingIndex] : null;
  const nextRule: RuleSetting = {
    type,
    label: input.target_label.trim() || selectedText,
    group: input.group.trim() || "Операторские факты",
    confidence: input.confidence ?? existing?.confidence ?? 0.5,
    color: input.color ?? existing?.color ?? null,
    phrases: [...(existing?.phrases ?? [])],
    patterns: [...(existing?.patterns ?? [])],
    match: existing?.match ?? { facts: [] }
  };

  if (input.phrase_kind === "exact") {
    const phrase = exactPhraseTokens(selectedText);
    if (!nextRule.phrases.some((candidate) => sameStringList(candidate, phrase))) {
      nextRule.phrases = [...nextRule.phrases, phrase];
    }
  } else {
    if (!input.semantic_pattern) {
      throw new Error("Для лемматического правила нужен semantic pattern");
    }
    const exists = nextRule.patterns.some((candidate) => JSON.stringify(candidate) === JSON.stringify(input.semantic_pattern));
    if (!exists) {
      nextRule.patterns = [...nextRule.patterns, input.semantic_pattern];
    }
  }

  const facts = [...current.facts];
  if (existingIndex >= 0) {
    facts[existingIndex] = nextRule;
  } else {
    facts.push(nextRule);
  }

  return {
    ...current,
    facts
  };
}

export function applyNoiseDraft(current: NlpSettings, text: string): NlpSettings {
  const phrase = exactPhraseTokens(text);

  const facts = [...current.facts];
  const factIndex = facts.findIndex((rule) => rule.type === OPERATOR_NOISE_FACT_TYPE);
  const existingFact = factIndex >= 0 ? facts[factIndex] : null;
  const noiseFact: RuleSetting = {
    type: OPERATOR_NOISE_FACT_TYPE,
    label: existingFact?.label ?? OPERATOR_NOISE_FACT_LABEL,
    group: existingFact?.group ?? OPERATOR_NOISE_SIGNAL_GROUP,
    confidence: existingFact?.confidence ?? 0.95,
    color: existingFact?.color ?? null,
    phrases: [...(existingFact?.phrases ?? [])],
    patterns: [],
    match: existingFact?.match ?? { facts: [] }
  };
  if (!noiseFact.phrases.some((candidate) => sameStringList(candidate, phrase))) {
    noiseFact.phrases = [...noiseFact.phrases, phrase];
  }
  if (factIndex >= 0) {
    facts[factIndex] = noiseFact;
  } else {
    facts.push(noiseFact);
  }

  const signals = [...current.signals];
  const signalIndex = signals.findIndex((rule) => rule.type === OPERATOR_NOISE_SIGNAL_TYPE);
  const existingSignal = signalIndex >= 0 ? signals[signalIndex] : null;
  const nextSignal: RuleSetting = {
    type: OPERATOR_NOISE_SIGNAL_TYPE,
    label: existingSignal?.label ?? OPERATOR_NOISE_SIGNAL_LABEL,
    group: existingSignal?.group ?? OPERATOR_NOISE_SIGNAL_GROUP,
    confidence: existingSignal?.confidence ?? 0.95,
    color: existingSignal?.color ?? "#5f6368",
    phrases: [],
    patterns: [],
    match: {
      facts: uniqueStrings([OPERATOR_NOISE_FACT_TYPE, ...factDependencyTypes(existingSignal ?? emptyRule())]).map((factType) => ({
        types: [factType]
      }))
    }
  };
  if (signalIndex >= 0) {
    signals[signalIndex] = nextSignal;
  } else {
    signals.push(nextSignal);
  }

  const signalWeights = { ...current.lead_scoring.signal_weights };
  if (signalWeights[OPERATOR_NOISE_SIGNAL_TYPE] === undefined) {
    signalWeights[OPERATOR_NOISE_SIGNAL_TYPE] = OPERATOR_NOISE_SIGNAL_WEIGHT;
  }

  const nextLeadScoring = {
    ...current.lead_scoring,
    signal_weights: signalWeights,
    noise_signal_types: uniqueStrings([...current.lead_scoring.noise_signal_types, OPERATOR_NOISE_SIGNAL_TYPE]),
    lead_veto_signal_types: uniqueStrings([...current.lead_scoring.lead_veto_signal_types, OPERATOR_NOISE_SIGNAL_TYPE]),
    score_caps: ensureNoiseScoreCap(current.lead_scoring.score_caps),
    review_lanes: current.lead_scoring.review_lanes.map((lane) => {
      if (lane.key === "noise") {
        return {
          ...lane,
          match_groups: lane.match_groups.map((group) => ({
            ...group,
            signal_types: uniqueStrings([...(group.signal_types ?? []), OPERATOR_NOISE_SIGNAL_TYPE]),
            noise_signal_types: uniqueStrings([...(group.noise_signal_types ?? []), OPERATOR_NOISE_SIGNAL_TYPE])
          }))
        };
      }
      return {
        ...lane,
        excluded_noise_signal_types: uniqueStrings([
          ...(lane.excluded_noise_signal_types ?? []),
          OPERATOR_NOISE_SIGNAL_TYPE
        ])
      };
    })
  };

  return {
    ...current,
    facts,
    signals,
    lead_scoring: nextLeadScoring
  };
}

export function applySignalDraft(current: NlpSettings, input: SignalDraftInput): NlpSettings {
  const type = requireKey(input.type, "Тип сигнала не должен быть пустым");
  const selectedFacts = uniqueStrings(input.fact_types.map((item) => item.trim()).filter(Boolean));
  if (selectedFacts.length === 0) {
    throw new Error("Нужно выбрать хотя бы один fact для сигнала");
  }
  const signalIndex = current.signals.findIndex((rule) => rule.type === type);
  const existingSignal = signalIndex >= 0 ? current.signals[signalIndex] : null;
  const nextSignal: RuleSetting = {
    type,
    label: input.label.trim() || type,
    group: input.group.trim() || "Доменные сигналы",
    confidence: input.confidence ?? existingSignal?.confidence ?? 0.7,
    color: input.color ?? existingSignal?.color ?? "#0b57d0",
    phrases: [],
    patterns: [],
    match: {
      facts: selectedFacts.map((factType) => ({ types: [factType] }))
    }
  };

  const signals = [...current.signals];
  if (signalIndex >= 0) {
    signals[signalIndex] = nextSignal;
  } else {
    signals.push(nextSignal);
  }

  return {
    ...current,
    signals,
    lead_scoring: {
      ...current.lead_scoring,
      signal_weights: {
        ...current.lead_scoring.signal_weights,
        [type]: input.score_weight
      }
    }
  };
}

function emptyRule(): RuleSetting {
  return { type: "", label: "", phrases: [], patterns: [], match: { facts: [] } };
}

function requireText(value: string, message: string): string {
  const text = value.trim();
  if (!text) {
    throw new Error(message);
  }
  return text;
}

function requireKey(value: string, message: string): string {
  const key = value.trim();
  if (!key) {
    throw new Error(message);
  }
  return key;
}

function ensureNoiseScoreCap(scoreCaps: NlpSettings["lead_scoring"]["score_caps"]) {
  const existingIndex = scoreCaps.findIndex((cap) => cap.key === HARD_NOISE_SCORE_CAP_KEY);
  const nextCap = {
    key: HARD_NOISE_SCORE_CAP_KEY,
    label: HARD_NOISE_SCORE_CAP_LABEL,
    max_score: 0,
    signal_types: [],
    fact_types: [],
    reason_keys: [],
    noise_signal_types: [OPERATOR_NOISE_SIGNAL_TYPE],
    excluded_signal_types: [],
    excluded_fact_types: [],
    excluded_reason_keys: [],
    excluded_noise_signal_types: []
  };
  if (existingIndex === -1) {
    return [...scoreCaps, nextCap];
  }
  return scoreCaps.map((cap, index) =>
    index === existingIndex
      ? {
          ...cap,
          label: cap.label || HARD_NOISE_SCORE_CAP_LABEL,
          max_score: cap.max_score ?? 0,
          noise_signal_types: uniqueStrings([...(cap.noise_signal_types ?? []), OPERATOR_NOISE_SIGNAL_TYPE]),
          signal_types: [...(cap.signal_types ?? [])],
          fact_types: [...(cap.fact_types ?? [])],
          reason_keys: [...(cap.reason_keys ?? [])],
          excluded_signal_types: [...(cap.excluded_signal_types ?? [])],
          excluded_fact_types: [...(cap.excluded_fact_types ?? [])],
          excluded_reason_keys: [...(cap.excluded_reason_keys ?? [])],
          excluded_noise_signal_types: [...(cap.excluded_noise_signal_types ?? [])]
        }
      : cap
  );
}

function sameStringList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      result.push(value);
    }
  }
  return result;
}

function uniqueCasefold(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const folded = value.toLocaleLowerCase("ru-RU");
    if (!seen.has(folded)) {
      seen.add(folded);
      result.push(value);
    }
  }
  return result;
}
