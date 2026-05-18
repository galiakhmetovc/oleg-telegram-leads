import { Box, Paper, Stack } from "@mui/material";
import { useEffect, useRef, useState } from "react";

import { SectionTitle } from "./AnalyticsShared";
import { ReviewReasonSummary } from "./CandidateEvidence";
import {
  ReviewCandidateSummaryPanel,
  ReviewMarkupPanel,
  ReviewPipelineCheckPanel,
  ReviewPageHeader,
  ReviewSourceConstructorPanel,
  reviewVerdictOptions
} from "./AnalyticsReviewPanels";
import {
  ConstructorDialog,
  createConstructorDialog,
  saveConstructorDialogRequest,
  saveNoiseConstructorRequest
} from "./ReviewConstructor";
import type { ConstructorDialogState, ReviewNlpSettings } from "./ReviewConstructor";
import {
  LlmVerificationPanel,
  type LlmVerificationConfig,
  type LlmVerificationPage,
  type LlmVerificationRun
} from "./LlmVerificationPanels";
import type { EnrichmentEvent, EnrichmentJob, TextEnrichmentResult } from "../enrichment/types";
import {
  analyticsListHash,
  analyticsReviewHash,
  candidatePageSize,
  parseAnalyticsUrlState
} from "./analyticsRoutes";
import { candidateQuery, type CandidateGridQueryState } from "./candidateQueueState";
import type { AnalyticsCandidate, AnalyticsReviewVerdict, CandidateFilters, CandidatePage } from "./types";
import { navigateRoute } from "../routes";

type AnalyticsReviewPageProps = {
  apiBaseUrl: string;
  messageId: string;
  returnHash?: string | null;
  nlpSettings?: ReviewNlpSettings | null;
  onBack?: () => void;
  onNlpSettingsChange?: (nlpSettings: unknown) => void;
};

export function AnalyticsReviewPage({
  apiBaseUrl,
  messageId,
  returnHash,
  nlpSettings,
  onBack,
  onNlpSettingsChange
}: AnalyticsReviewPageProps) {
  const [candidate, setCandidate] = useState<AnalyticsCandidate | null>(null);
  const [verdict, setVerdict] = useState<AnalyticsReviewVerdict | null>(null);
  const [comment, setComment] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [selectedText, setSelectedText] = useState("");
  const [constructorDraft, setConstructorDraft] = useState<string | null>(null);
  const [constructorSaving, setConstructorSaving] = useState(false);
  const [constructorMessage, setConstructorMessage] = useState<string | null>(null);
  const [constructorError, setConstructorError] = useState<string | null>(null);
  const [constructorDialog, setConstructorDialog] = useState<ConstructorDialogState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [nextStatus, setNextStatus] = useState<string | null>(null);
  const [goldenSaving, setGoldenSaving] = useState(false);
  const [goldenMessage, setGoldenMessage] = useState<string | null>(null);
  const [goldenError, setGoldenError] = useState<string | null>(null);
  const [llmConfig, setLlmConfig] = useState<LlmVerificationConfig | null>(null);
  const [llmRuns, setLlmRuns] = useState<LlmVerificationRun[]>([]);
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmRunning, setLlmRunning] = useState(false);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [expandedLlmRunId, setExpandedLlmRunId] = useState<string | null>(null);
  const [checkJob, setCheckJob] = useState<EnrichmentJob | null>(null);
  const [checkEvents, setCheckEvents] = useState<EnrichmentEvent[]>([]);
  const [checkResult, setCheckResult] = useState<TextEnrichmentResult | null>(null);
  const [checkSubmitting, setCheckSubmitting] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const checkEventSourceRef = useRef<EventSource | null>(null);
  const checkRunning = checkSubmitting || checkJob?.status === "queued" || checkJob?.status === "running";

  useEffect(() => {
    let active = true;
    async function loadCandidate() {
      setLoading(true);
      setError(null);
      setSaved(false);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}`);
        if (!response.ok) {
          throw new Error(`Backend вернул ${response.status}`);
        }
        const nextCandidate = (await response.json()) as AnalyticsCandidate;
        if (!active) {
          return;
        }
        setCandidate(nextCandidate);
        setVerdict(nextCandidate.review?.verdict ?? null);
        setComment(nextCandidate.review?.comment ?? "");
        setTags(nextCandidate.review?.tags ?? []);
        setSelectedText("");
        setConstructorDraft(null);
        setConstructorMessage(null);
        setConstructorError(null);
        setConstructorDialog(null);
        resetPipelineCheck();
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Не удалось загрузить сообщение для ревью");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadCandidate();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, messageId]);

  useEffect(() => {
    return () => {
      checkEventSourceRef.current?.close();
    };
  }, []);

  useEffect(() => {
    let active = true;
    async function loadLlmState() {
      setLlmLoading(true);
      setLlmError(null);
      try {
        const [configResponse, runsResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/api/v1/llm-verifications/config`),
          fetch(`${apiBaseUrl}/api/v1/llm-verifications/messages/${encodeURIComponent(messageId)}`)
        ]);
        if (!configResponse.ok) {
          throw new Error(`Настройки LLM: backend вернул ${configResponse.status}`);
        }
        if (!runsResponse.ok) {
          throw new Error(`Запуски LLM: backend вернул ${runsResponse.status}`);
        }
        const nextConfig = (await configResponse.json()) as LlmVerificationConfig;
        const nextRuns = (await runsResponse.json()) as LlmVerificationPage;
        if (!active) {
          return;
        }
        setLlmConfig(nextConfig);
        setLlmRuns(nextRuns.items ?? []);
        setExpandedLlmRunId((current) => current ?? nextRuns.items?.[0]?.id ?? null);
      } catch (caught) {
        if (active) {
          setLlmError(caught instanceof Error ? caught.message : "Не удалось загрузить LLM-проверки");
        }
      } finally {
        if (active) {
          setLlmLoading(false);
        }
      }
    }

    void loadLlmState();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, messageId]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editingText =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.getAttribute("contenteditable") === "true");
      if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        void saveReview();
        return;
      }
      if (editingText || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) {
        return;
      }
      const index = Number(event.key) - 1;
      const option = reviewVerdictOptions[index];
      if (option) {
        event.preventDefault();
        setVerdict(option.value);
      }
      if (event.key.toLocaleLowerCase("ru-RU") === "n" || event.key.toLocaleLowerCase("ru-RU") === "т") {
        event.preventDefault();
        void saveReview({ goNext: true });
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [apiBaseUrl, comment, messageId, returnHash, tags, verdict]);

  async function saveReview(options: { goNext?: boolean } = {}) {
    setSaving(true);
    setError(null);
    setSaved(false);
    setNextStatus(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/analytics/messages/${encodeURIComponent(messageId)}/review`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict, comment, tags })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const nextCandidate = (await response.json()) as AnalyticsCandidate;
      setCandidate(nextCandidate);
      setVerdict(nextCandidate.review?.verdict ?? verdict);
      setComment(nextCandidate.review?.comment ?? comment);
      setTags(nextCandidate.review?.tags ?? tags);
      setSaved(true);
      if (options.goNext) {
        await openNextCandidate();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить ревью");
    } finally {
      setSaving(false);
    }
  }

  async function openNextCandidate() {
    if (!returnHash) {
      setNextStatus("Нет сохраненного контекста очереди для перехода к следующему сообщению.");
      return;
    }
    const state = parseAnalyticsUrlState(returnHash);
    if (!state.runId) {
      setNextStatus("В ссылке возврата нет выбранного запуска аналитики.");
      return;
    }
    const page = await fetchCandidatePage(state.runId, state.filters, state.offset, state.grid);
    const currentIndex = page.items.findIndex((item) => item.message_id === messageId);
    const nextCandidate = currentIndex >= 0 ? page.items[currentIndex + 1] : page.items[0];
    if (nextCandidate) {
      navigateRoute(analyticsReviewHash(nextCandidate.message_id, returnHash));
      return;
    }
    if (page.total > state.offset + page.limit) {
      const nextOffset = state.offset + page.limit;
      const nextReturnHash = analyticsListHash(state.filters, nextOffset, state.runId, state.grid);
      const nextPage = await fetchCandidatePage(state.runId, state.filters, nextOffset, state.grid);
      if (nextPage.items[0]) {
        navigateRoute(analyticsReviewHash(nextPage.items[0].message_id, nextReturnHash));
        return;
      }
    }
    setNextStatus("В этой очереди больше нет сообщений.");
  }

  async function fetchCandidatePage(
    runId: string,
    filters: CandidateFilters,
    offset: number,
    gridState: CandidateGridQueryState
  ): Promise<CandidatePage> {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/analytics/runs/${encodeURIComponent(runId)}/candidates?${candidateQuery(
        filters,
        candidatePageSize,
        offset,
        gridState
      )}`
    );
    if (!response.ok) {
      throw new Error(`Backend вернул ${response.status}`);
    }
    return (await response.json()) as CandidatePage;
  }

  function rememberSelection() {
    const text = window.getSelection()?.toString().trim();
    if (text) {
      setSelectedText(text);
      setConstructorDraft(null);
      setConstructorMessage(null);
      setConstructorError(null);
    }
  }

  function toggleTag(tag: string) {
    setTags((current) => (current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]));
  }

  function openConstructorDialog(kind: "alias" | "fact") {
    if (!selectedText) {
      return;
    }
    setConstructorDraft(null);
    setConstructorMessage(null);
    setConstructorError(null);
    setConstructorDialog(createConstructorDialog(kind, selectedText));
  }

  async function saveConstructorDialog() {
    if (!constructorDialog) {
      return;
    }
    setConstructorSaving(true);
    setConstructorError(null);
    setConstructorMessage(null);
    try {
      const payload = await saveConstructorDialogRequest({
        apiBaseUrl,
        messageId,
        dialog: constructorDialog
      });
      onNlpSettingsChange?.(payload.nlp);
      setConstructorDraft(payload.draft);
      setConstructorMessage(payload.message);
      setConstructorDialog(null);
    } catch (caught) {
      setConstructorError(caught instanceof Error ? caught.message : "Не удалось сохранить настройку конструктора");
    } finally {
      setConstructorSaving(false);
    }
  }

  async function saveSelectedTextAsNoise() {
    if (!selectedText) {
      return;
    }
    setConstructorSaving(true);
    setConstructorError(null);
    setConstructorMessage(null);
    try {
      const payload = await saveNoiseConstructorRequest({
        apiBaseUrl,
        messageId,
        text: selectedText
      });
      onNlpSettingsChange?.(payload.nlp);
      setConstructorDraft(payload.draft);
      setConstructorMessage(payload.message);
    } catch (caught) {
      setConstructorError(caught instanceof Error ? caught.message : "Не удалось добавить шумовое правило");
    } finally {
      setConstructorSaving(false);
    }
  }

  async function addCurrentCandidateToGolden() {
    if (!candidate) {
      return;
    }
    setGoldenSaving(true);
    setGoldenMessage(null);
    setGoldenError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/golden-examples/from-message/${encodeURIComponent(candidate.message_id)}`,
        { method: "POST" }
      );
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      setGoldenMessage("Сообщение добавлено в golden-примеры");
    } catch (caught) {
      setGoldenError(caught instanceof Error ? caught.message : "Не удалось добавить сообщение в golden");
    } finally {
      setGoldenSaving(false);
    }
  }

  function resetPipelineCheck() {
    checkEventSourceRef.current?.close();
    checkEventSourceRef.current = null;
    setCheckJob(null);
    setCheckEvents([]);
    setCheckResult(null);
    setCheckSubmitting(false);
    setCheckError(null);
  }

  async function startPipelineCheck() {
    if (!candidate) {
      return;
    }
    checkEventSourceRef.current?.close();
    setCheckSubmitting(true);
    setCheckError(null);
    setCheckEvents([]);
    setCheckJob(null);
    setCheckResult(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/enrichments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: candidate.text })
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const createdJob = (await response.json()) as EnrichmentJob;
      setCheckJob(createdJob);
      connectPipelineCheckEvents(createdJob.id);
    } catch (caught) {
      setCheckError(caught instanceof Error ? caught.message : "Не удалось запустить проверку");
    } finally {
      setCheckSubmitting(false);
    }
  }

  function connectPipelineCheckEvents(jobId: string) {
    const source = new EventSource(`${apiBaseUrl}/api/v1/enrichments/${jobId}/events`);
    checkEventSourceRef.current = source;

    const handleEvent = (message: MessageEvent<string>) => {
      const parsed = JSON.parse(message.data) as EnrichmentEvent;
      setCheckEvents((current) => [parsed, ...current].slice(0, 12));
      setCheckJob((current) => {
        if (current === null) {
          return current;
        }
        return {
          ...current,
          status:
            parsed.event_type === "job_completed"
              ? "completed"
              : parsed.event_type === "job_failed"
                ? "failed"
                : "running",
          progress_percent: parsed.progress_percent,
          current_stage: parsed.current_stage,
          stage_index: parsed.stage_index,
          stage_count: parsed.stage_count,
          stage_progress_percent: parsed.stage_progress_percent,
          message: parsed.message,
          result: parsed.payload?.result ?? current.result,
          error: parsed.payload?.error ?? current.error
        };
      });
      if (parsed.payload?.result) {
        setCheckResult(parsed.payload.result);
      }
      if (parsed.event_type === "job_completed" || parsed.event_type === "job_failed") {
        source.close();
        void refreshPipelineCheckSnapshot(jobId);
      }
    };

    for (const eventName of [
      "job_queued",
      "job_started",
      "stage_completed",
      "job_completed",
      "job_failed"
    ]) {
      source.addEventListener(eventName, handleEvent);
    }

    source.onerror = () => {
      setCheckError("SSE-соединение проверки прервано");
      source.close();
    };
  }

  async function refreshPipelineCheckSnapshot(jobId: string) {
    const response = await fetch(`${apiBaseUrl}/api/v1/enrichments/${jobId}`);
    if (!response.ok) {
      return;
    }
    const nextJob = (await response.json()) as EnrichmentJob;
    setCheckJob(nextJob);
    setCheckResult(nextJob.result ?? null);
  }

  async function runLlmVerification() {
    setLlmRunning(true);
    setLlmError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/llm-verifications/messages/${encodeURIComponent(messageId)}`, {
        method: "POST"
      });
      if (!response.ok) {
        throw new Error(`Backend вернул ${response.status}`);
      }
      const run = (await response.json()) as LlmVerificationRun;
      setLlmRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setExpandedLlmRunId(run.id);
    } catch (caught) {
      setLlmError(caught instanceof Error ? caught.message : "Не удалось запустить LLM-проверку");
    } finally {
      setLlmRunning(false);
    }
  }

  return (
    <Box className="analytics-shell analytics-review-shell">
      <ReviewPageHeader
        candidate={candidate}
        messageId={messageId}
        loading={loading}
        error={error}
        goldenSaving={goldenSaving}
        goldenError={goldenError}
        goldenMessage={goldenMessage}
        saved={saved}
        nextStatus={nextStatus}
        onBack={onBack}
        onTestMessage={() => void startPipelineCheck()}
        onAddGolden={() => void addCurrentCandidateToGolden()}
      />

      {candidate && (
        <Box className="analytics-review-grid">
          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <Paper variant="outlined" className="analytics-section">
              <Stack spacing={1.25}>
                <SectionTitle title="Почему сработало" subtitle="Короткая сводка автоматического разбора перед решением" />
                <ReviewReasonSummary candidate={candidate} />
              </Stack>
            </Paper>

            <LlmVerificationPanel
              candidate={candidate}
              config={llmConfig}
              runs={llmRuns}
              loading={llmLoading}
              running={llmRunning}
              error={llmError}
              expandedRunId={expandedLlmRunId}
              onRun={() => void runLlmVerification()}
              onToggleRun={(runId) => setExpandedLlmRunId((current) => (current === runId ? null : runId))}
            />

            <ReviewPipelineCheckPanel
              job={checkJob}
              events={checkEvents}
              result={checkResult}
              running={checkRunning}
              error={checkError}
              onRun={() => void startPipelineCheck()}
            />

            <ReviewMarkupPanel
              verdict={verdict}
              tags={tags}
              comment={comment}
              saving={saving}
              onVerdictChange={setVerdict}
              onToggleTag={toggleTag}
              onCommentChange={setComment}
              onSave={() => void saveReview()}
              onSaveNext={() => void saveReview({ goNext: true })}
            />

            <ReviewSourceConstructorPanel
              candidate={candidate}
              selectedText={selectedText}
              constructorSaving={constructorSaving}
              constructorError={constructorError}
              constructorMessage={constructorMessage}
              constructorDraft={constructorDraft}
              onRememberSelection={rememberSelection}
              onOpenConstructorDialog={openConstructorDialog}
              onSaveNoise={() => void saveSelectedTextAsNoise()}
            />
          </Stack>

          <ReviewCandidateSummaryPanel candidate={candidate} />
        </Box>
      )}
      <ConstructorDialog
        dialog={constructorDialog}
        nlpSettings={nlpSettings}
        saving={constructorSaving}
        onChange={setConstructorDialog}
        onClose={() => {
          if (!constructorSaving) {
            setConstructorDialog(null);
          }
        }}
        onSave={() => void saveConstructorDialog()}
      />
    </Box>
  );
}
