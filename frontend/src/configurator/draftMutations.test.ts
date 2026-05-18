import { describe, expect, test } from "vitest";

import {
  applyAliasDraft,
  applyFactDraft,
  applyNoiseDraft,
  applySignalDraft,
  exactPhraseTokens
} from "./draftMutations";
import type { NlpSettings, RulePatternSetting } from "../settings/types";

describe("draftMutations", () => {
  test("tokenizes exact phrases the same way as the constructor backend", () => {
    expect(exactPhraseTokens("Wi-Fi для дома, + монтаж")).toEqual(["wi-fi", "для", "дома", "монтаж"]);
  });

  test("adds a new alias and appends the selected text to its aliases", () => {
    const next = applyAliasDraft(sampleNlpSettings(), {
      text: "Aqara Hub M3",
      catalog: "devices",
      key: "aqara_hub_m3",
      canonical: "Aqara Hub M3",
      alias_type: "device",
      fact_types: ["smart_home_hub", "vendor_aqara"],
      confidence: 0.8,
      color: null
    });

    expect(next.devices).toEqual([
      expect.objectContaining({
        key: "aqara_hub_m3",
        canonical: "Aqara Hub M3",
        type: "device",
        aliases: ["Aqara Hub M3"],
        fact_types: ["smart_home_hub", "vendor_aqara"],
        confidence: 0.8
      })
    ]);
  });

  test("adds a semantic pattern to a fact rule", () => {
    const semanticPattern: RulePatternSetting = {
      source_text: "Нужна консультация",
      tokens: [
        { predicate: "normalized", value: "нужный" },
        { predicate: "normalized", value: "консультация" }
      ]
    };

    const next = applyFactDraft(sampleNlpSettings(), {
      text: "Нужна консультация",
      target_type: "intent_consultation",
      target_label: "Нужна консультация",
      group: "Интент",
      phrase_kind: "semantic",
      confidence: 0.7,
      color: null,
      semantic_pattern: semanticPattern
    });

    expect(next.facts).toEqual([
      expect.objectContaining({
        type: "intent_consultation",
        label: "Нужна консультация",
        group: "Интент",
        patterns: [semanticPattern]
      })
    ]);
  });

  test("creates operator noise fact, signal, veto flags, and score cap", () => {
    const next = applyNoiseDraft(sampleNlpSettings(), "Это операторский тест");

    expect(next.facts).toEqual([
      expect.objectContaining({
        type: "operator_noise_fact",
        label: "Факт: операторский шум",
        phrases: [["это", "операторский", "тест"]]
      })
    ]);
    expect(next.signals).toEqual([
      expect.objectContaining({
        type: "operator_noise",
        label: "Операторский шум",
        match: { facts: [{ types: ["operator_noise_fact"] }] }
      })
    ]);
    expect(next.lead_scoring.signal_weights.operator_noise).toBe(-50);
    expect(next.lead_scoring.noise_signal_types).toContain("operator_noise");
    expect(next.lead_scoring.lead_veto_signal_types).toContain("operator_noise");
    expect(next.lead_scoring.score_caps).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: "hard_noise",
          noise_signal_types: ["operator_noise"]
        })
      ])
    );
  });

  test("creates a domain signal from selected fact types and assigns score weight", () => {
    const next = applySignalDraft(sampleNlpSettings(), {
      type: "pur_smart_home",
      label: "PUR / умный дом",
      group: "PUR",
      fact_types: ["intent_install_connect", "domain_smart_home"],
      confidence: 0.9,
      color: "#0b57d0",
      score_weight: 35
    });

    expect(next.signals).toEqual([
      expect.objectContaining({
        type: "pur_smart_home",
        label: "PUR / умный дом",
        group: "PUR",
        match: {
          facts: [{ types: ["intent_install_connect"] }, { types: ["domain_smart_home"] }]
        }
      })
    ]);
    expect(next.lead_scoring.signal_weights.pur_smart_home).toBe(35);
  });
});

function sampleNlpSettings(): NlpSettings {
  return {
    pipeline: { stages: [{ name: "segmentation", enabled: true }] },
    alias_matching: {
      normalize_separators: true,
      normalize_yo: true,
      normalize_latin_confusables: true,
      fuzzy_enabled: true,
      fuzzy_min_length: 5,
      fuzzy_max_distance: 1,
      fuzzy_long_min_length: 10,
      fuzzy_long_max_distance: 2,
      fuzzy_excluded_aliases: []
    },
    signals: [],
    facts: [],
    vendors: [],
    protocols: [],
    devices: [],
    software: [],
    lead_scoring: {
      lead_threshold: 35,
      warm_threshold: 60,
      hot_threshold: 90,
      signal_weights: {},
      fact_weights: {},
      solution_areas: {},
      customer_segments: {},
      intent_signal_types: [],
      noise_signal_types: [],
      lead_veto_signal_types: [],
      score_caps: [],
      review_lanes: []
    },
    source: {
      type: "postgres",
      path: "nlp_config_revisions.config",
      editable: true,
      revision: 1
    }
  };
}
