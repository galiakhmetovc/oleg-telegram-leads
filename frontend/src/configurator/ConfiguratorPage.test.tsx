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

  test("shows a domain workspace with dependent facts, signals, and dictionary aliases", () => {
    render(
      <ConfiguratorPage
        settings={sampleSettingsSnapshot()}
        loading={false}
        loadError={null}
        loadSettings={vi.fn()}
        onSettingsSnapshotChange={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "Конфигуратор правил" })).toBeInTheDocument();
    expect(screen.getByText("NLP-ревизия #1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Умный дом 1 сигнал 0 фактов/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Умный дом" })).toBeInTheDocument();
    expect(screen.getByText("Умный дом / автоматизация")).toBeInTheDocument();
    expect(screen.getAllByText("alias:devices:smart_home_hub").length).toBeGreaterThan(0);
    expect(screen.getByText("Хаб умного дома")).toBeInTheDocument();
    expect(screen.getByText("zigbee шлюз")).toBeInTheDocument();
  });

  test("saves selected signal edits through the active NLP settings endpoint", async () => {
    const snapshot = sampleSettingsSnapshot();
    const onSettingsSnapshotChange = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/v1/settings/nlp" && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as NlpSettings;
        return jsonResponse({
          ...body,
          source: { type: "postgres", path: "nlp_config_revisions.config", editable: true, revision: 2 }
        });
      }
      throw new Error(`Unhandled fetch: ${String(input)}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ConfiguratorPage
        settings={snapshot}
        loading={false}
        loadError={null}
        loadSettings={vi.fn()}
        onSettingsSnapshotChange={onSettingsSnapshotChange}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Умный дом \/ автоматизация/i }));
    fireEvent.change(screen.getByLabelText("Название"), {
      target: { value: "Умный дом / проектирование" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить ревизию" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/settings/nlp",
        expect.objectContaining({
          method: "PUT",
          body: expect.stringContaining("Умный дом / проектирование")
        })
      )
    );
    expect(await screen.findByText("Сохранено как NLP-ревизия #2")).toBeInTheDocument();
    expect(onSettingsSnapshotChange).toHaveBeenCalledWith(
      expect.objectContaining({
        nlp: expect.objectContaining({
          source: expect.objectContaining({ revision: 2 }),
          signals: expect.arrayContaining([
            expect.objectContaining({ type: "smart_home_automation", label: "Умный дом / проектирование" })
          ])
        })
      })
    );
  });

  test("opens detailed settings through a real settings hash deeplink", () => {
    render(
      <ConfiguratorPage
        settings={sampleSettingsSnapshot()}
        loading={false}
        loadError={null}
        loadSettings={vi.fn()}
        onSettingsSnapshotChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Умный дом \/ автоматизация/i }));
    fireEvent.click(screen.getByRole("button", { name: "Детально в настройках" }));

    expect(window.location.hash).toBe("#/settings/signals/smart_home_automation");
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
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
      signals: [
        {
          type: "smart_home_automation",
          label: "Умный дом / автоматизация",
          group: "Умный дом",
          color: "#0b57d0",
          confidence: 0.9,
          phrases: [],
          patterns: [],
          match: { facts: [{ types: ["alias:devices:smart_home_hub"] }] }
        },
        {
          type: "video_surveillance",
          label: "Видеонаблюдение",
          group: "Безопасность",
          color: null,
          confidence: 0.8,
          phrases: [],
          patterns: [],
          match: { facts: [{ types: ["object_camera"] }] }
        }
      ],
      facts: [
        {
          type: "controlled_device",
          label: "Управляемое устройство",
          group: "Устройства",
          color: null,
          confidence: 0.8,
          phrases: [],
          patterns: [],
          match: { facts: [] }
        }
      ],
      vendors: [],
      protocols: [],
      devices: [
        {
          key: "smart_home_hub",
          canonical: "Хаб умного дома",
          type: "device",
          aliases: ["zigbee шлюз"],
          fact_types: ["controlled_device"]
        }
      ],
      software: [],
      lead_scoring: {
        lead_threshold: 35,
        warm_threshold: 60,
        hot_threshold: 90,
        signal_weights: { smart_home_automation: 35, video_surveillance: 35 },
        fact_weights: { controlled_device: 10 },
        solution_areas: {
          automation: {
            label: "Умный дом / автоматизация",
            signal_types: ["smart_home_automation"],
            fact_types: ["controlled_device"]
          }
        },
        customer_segments: {
          project_selection: {
            label: "Подбор решений для проекта",
            signal_types: ["smart_home_automation"],
            fact_types: []
          }
        },
        intent_signal_types: ["smart_home_automation"],
        noise_signal_types: [],
        lead_veto_signal_types: [],
        score_caps: [],
        review_lanes: [
          {
            key: "direct_pur_lead",
            label: "Прямой лид ПУР",
            description: "Есть домен ПУР и активное намерение.",
            priority: 200,
            min_score: 35,
            max_score: null,
            temperatures: ["warm", "hot"],
            match_groups: [
              {
                signal_types: ["smart_home_automation"],
                fact_types: [],
                reason_keys: [],
                solution_area_types: ["automation"],
                customer_segment_types: [],
                intent_signal_types: [],
                noise_signal_types: []
              }
            ],
            excluded_signal_types: [],
            excluded_fact_types: [],
            excluded_reason_keys: [],
            excluded_solution_area_types: [],
            excluded_customer_segment_types: [],
            excluded_intent_signal_types: [],
            excluded_noise_signal_types: []
          }
        ]
      },
      source: {
        type: "postgres",
        path: "nlp_config_revisions.config",
        editable: true,
        revision: 1
      }
    },
    notifications: { bots: [], chats: [], routes: [], updated_at: null },
    telegram_ingestion: { accounts: [], chats: [] },
    system: []
  };
}
