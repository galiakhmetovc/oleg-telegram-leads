import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { ConfiguratorPage } from "./ConfiguratorPage";
import type { NlpSettings, SettingsSnapshot } from "../settings/types";

describe("ConfiguratorPage", () => {
  afterEach(() => {
    cleanup();
    window.history.replaceState(null, "", "/");
    vi.unstubAllGlobals();
  });

  test("shows a constructor workspace with message preview and signal builder", () => {
    render(
      <ConfiguratorPage
        settings={sampleSettingsSnapshot()}
        loading={false}
        loadError={null}
        loadSettings={vi.fn()}
        onSettingsSnapshotChange={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "Конструктор" })).toBeInTheDocument();
    expect(screen.getByText("Работа через draft-ревизию")).toBeInTheDocument();
    expect(screen.getByText("NLP-ревизия #1")).toBeInTheDocument();
    expect(screen.getByLabelText("Сообщение для разбора")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Разобрать" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "В словарь" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "В факт" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "В шум" })).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Конструктор сигналов" })).toBeInTheDocument();
    expect(screen.getByText("Сигналы строятся только из найденных facts.")).toBeInTheDocument();
  });

  test("adds a semantic fact from selected text and refreshes preview against the updated draft", async () => {
    const previewBodies: Array<{ text: string; nlp: NlpSettings }> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/settings/nlp/preview" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { text: string; nlp: NlpSettings };
        previewBodies.push(body);
        if (previewBodies.length === 1) {
          return jsonResponse(samplePreviewResult({ facts: [], domain_signals: [] }));
        }
        return jsonResponse(
          samplePreviewResult({
            facts: [
              previewFact({
                id: "fact-intent",
                text: "Хочу поставить",
                type: "intent_install_connect",
                label: "Намерение: установка",
                source: "semantic_pattern"
              })
            ],
            domain_signals: []
          })
        );
      }
      if (url === "/api/v1/settings/nlp/semantic-pattern" && init?.method === "POST") {
        return jsonResponse({
          source_text: "Хочу поставить",
          lemma_text: "хотеть поставить",
          tokens: [
            { predicate: "normalized", value: "хотеть" },
            { predicate: "normalized", value: "поставить" }
          ]
        });
      }
      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ConfiguratorPage
        settings={sampleSettingsSnapshot()}
        loading={false}
        loadError={null}
        loadSettings={vi.fn()}
        onSettingsSnapshotChange={vi.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText("Сообщение для разбора"), {
      target: { value: "Хочу поставить умный дом Aqara" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Разобрать" }));
    await screen.findByText("Ничего не найдено. Добавь факт, alias или сигнал в draft и повтори preview.");

    const textarea = screen.getByLabelText("Сообщение для разбора") as HTMLTextAreaElement;
    const selectionEnd = "Хочу поставить".length;
    textarea.setSelectionRange(0, selectionEnd);
    fireEvent.select(textarea);

    fireEvent.click(screen.getByRole("button", { name: "В факт" }));
    fireEvent.change(screen.getByLabelText("type"), {
      target: { value: "intent_install_connect" }
    });
    fireEvent.change(screen.getByLabelText("label"), {
      target: { value: "Намерение: установка" }
    });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Тип совпадения" }));
    fireEvent.click(await screen.findByRole("option", { name: "Лемматическая фраза" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить в draft" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/settings/nlp/semantic-pattern",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ text: "Хочу поставить" })
        })
      )
    );
    await waitFor(() => expect(previewBodies).toHaveLength(2));
    expect(await screen.findByText("Намерение: установка")).toBeInTheDocument();
    expect(previewBodies[1]?.nlp.facts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: "intent_install_connect",
          patterns: [
            {
              source_text: "Хочу поставить",
              tokens: [
                { predicate: "normalized", value: "хотеть" },
                { predicate: "normalized", value: "поставить" }
              ]
            }
          ]
        })
      ])
    );
  });

  test("builds a domain signal from preview facts and saves the updated draft revision", async () => {
    let savedBody: NlpSettings | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/settings/nlp/preview" && init?.method === "POST") {
        return jsonResponse(
          samplePreviewResult({
            facts: [
              previewFact({
                id: "fact-intent",
                text: "Хочу поставить",
                type: "intent_install_connect",
                label: "Намерение: установка",
                source: "semantic_pattern"
              }),
              previewFact({
                id: "fact-domain",
                text: "умный дом",
                type: "domain_smart_home",
                label: "Домен: умный дом",
                source: "exact_phrase"
              })
            ],
            domain_signals: []
          })
        );
      }
      if (url === "/api/v1/settings/nlp" && init?.method === "PUT") {
        savedBody = JSON.parse(String(init.body)) as NlpSettings;
        return jsonResponse({
          ...savedBody,
          source: { type: "postgres", path: "nlp_config_revisions.config", editable: true, revision: 2 }
        });
      }
      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onSettingsSnapshotChange = vi.fn();
    render(
      <ConfiguratorPage
        settings={sampleSettingsSnapshot()}
        loading={false}
        loadError={null}
        loadSettings={vi.fn()}
        onSettingsSnapshotChange={onSettingsSnapshotChange}
      />
    );

    fireEvent.change(screen.getByLabelText("Сообщение для разбора"), {
      target: { value: "Хочу поставить умный дом Aqara" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Разобрать" }));
    await screen.findByText("Намерение: установка");
    expect(screen.getByText("Домен: умный дом")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Тип сигнала"), {
      target: { value: "pur_smart_home" }
    });
    fireEvent.change(screen.getByLabelText("Название сигнала"), {
      target: { value: "PUR / умный дом" }
    });
    fireEvent.change(screen.getByLabelText("Папка сигнала"), {
      target: { value: "PUR" }
    });
    fireEvent.change(screen.getByLabelText("Вес в score"), {
      target: { value: "35" }
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Намерение: установка/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Домен: умный дом/i }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить сигнал в draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить ревизию" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/settings/nlp",
        expect.objectContaining({ method: "PUT" })
      )
    );
    expect(savedBody).not.toBeNull();
    if (savedBody === null) {
      throw new Error("Expected saved draft payload");
    }
    const persistedBody: NlpSettings = savedBody;
    expect(persistedBody.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: "pur_smart_home",
          label: "PUR / умный дом",
          group: "PUR",
          match: {
            facts: [{ types: ["intent_install_connect"] }, { types: ["domain_smart_home"] }]
          }
        })
      ])
    );
    expect(persistedBody.lead_scoring.signal_weights.pur_smart_home).toBe(35);
    expect(await screen.findByText("Сохранено как NLP-ревизия #2")).toBeInTheDocument();
    expect(onSettingsSnapshotChange).toHaveBeenCalledWith(
      expect.objectContaining({
        nlp: expect.objectContaining({
          source: expect.objectContaining({ revision: 2 })
        })
      })
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function previewFact({
  id,
  text,
  type,
  label,
  source
}: {
  id: string;
  text: string;
  type: string;
  label: string;
  source: string;
}) {
  return {
    id,
    text,
    type,
    label,
    range: { start: 0, stop: text.length },
    source,
    span_id: `span-${id}`,
    sentence_id: "sentence-1",
    settings_refs: [{ section: "facts", key: type, label, kind: "fact" }]
  };
}

function samplePreviewResult({
  facts,
  domain_signals
}: {
  facts: ReturnType<typeof previewFact>[];
  domain_signals: ReturnType<typeof previewFact>[];
}) {
  return {
    original_text: "Хочу поставить умный дом Aqara",
    normalized_text: "хочу поставить умный дом aqara",
    entities: [],
    facts,
    domain_signals,
    tokens: [],
    syntax: [],
    metrics: {},
    pipeline_trace: [],
    lead_assessment: {
      is_lead: domain_signals.length > 0,
      score: domain_signals.length > 0 ? 35 : 0,
      temperature: domain_signals.length > 0 ? "warm" : "cold",
      solution_areas: [],
      customer_segments: [],
      intent_signals: [],
      noise_signals: [],
      reasons: []
    }
  };
}

function sampleSettingsSnapshot(): SettingsSnapshot {
  return {
    nlp: {
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
    },
    notifications: {
      bots: [],
      chats: [],
      routes: [],
      updated_at: null
    },
    telegram_ingestion: {
      accounts: [],
      chats: []
    },
    system: []
  };
}
