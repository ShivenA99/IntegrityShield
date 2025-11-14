import * as React from "react";
import { useState, useCallback, useEffect, useMemo } from "react";
import clsx from "clsx";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { updateQuestionManipulation, generateMappingsForAll, generateMappingsForQuestion, getGenerationStatus } from "@services/api/questionApi";
import type { QuestionManipulation } from "@services/types/questions";
import { formatDuration } from "@services/utils/formatters";
import EnhancedQuestionViewer from "@components/question-level/EnhancedQuestionViewer";
import { ArrowRight, FileSpreadsheet, ListChecks, ScrollText } from "lucide-react";

const LATEX_ATTACK_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
] as const;

type LatexAttackMethod = (typeof LATEX_ATTACK_METHODS)[number];

const LATEX_ATTACK_SET = new Set<LatexAttackMethod>(LATEX_ATTACK_METHODS);

const isLatexAttackMethod = (value: string): value is LatexAttackMethod =>
  LATEX_ATTACK_SET.has(value as LatexAttackMethod);

const SmartSubstitutionPanel: React.FC = () => {
  const { activeRunId, resumeFromStage, status, refreshStatus, setPreferredStage } = usePipeline();
  const { questions, isLoading, refresh, mutate } = useQuestions(activeRunId);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [generatingQuestionId, setGeneratingQuestionId] = useState<number | null>(null);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [isGeneratingMappings, setIsGeneratingMappings] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<Record<number, any>>({});
  const [generationLogs, setGenerationLogs] = useState<any[]>([]);
  const [stagedMappings, setStagedMappings] = useState<Record<number, any>>({});
  const [showLogs, setShowLogs] = useState(false);
  const stage = status?.stages.find((item) => item.name === "smart_substitution");
  const runId = status?.run_id ?? activeRunId ?? null;
  const structuredData = (status?.structured_data ?? {}) as Record<string, any>;
  const enhancementMethods = useMemo(() => {
    const raw = status?.pipeline_config?.["enhancement_methods"] as unknown;
    if (Array.isArray(raw)) {
      return raw.map((entry) => String(entry));
    }
    return [];
  }, [status?.pipeline_config]);
  const manipulationResults = (structuredData?.manipulation_results ?? {}) as Record<string, any>;
  const enhancedPdfs = (manipulationResults.enhanced_pdfs ?? {}) as Record<string, any>;
  const overlayKey = useMemo(() => {
    const preference = [
      "latex_dual_layer",
      "latex_icw_dual_layer",
      "latex_icw_font_attack",
      "latex_font_attack",
      "latex_icw",
    ];
    for (const candidate of preference) {
      if (enhancedPdfs[candidate]) {
        return candidate;
      }
    }
    const fallback = Object.keys(enhancedPdfs)[0];
    return fallback || "latex_dual_layer";
  }, [enhancedPdfs]);
  const overlayRenderStats = (enhancedPdfs[overlayKey]?.render_stats ?? {}) as Record<string, any>;
  const artifactsMap = (manipulationResults.artifacts ?? {}) as Record<string, any>;
  const overlayArtifactsKey = useMemo(() => {
    if (artifactsMap[overlayKey]) {
      return overlayKey;
    }
    if (artifactsMap.latex_dual_layer) {
      return "latex_dual_layer";
    }
    const keys = Object.keys(artifactsMap);
    return keys.length ? keys[0] : overlayKey;
  }, [artifactsMap, overlayKey]);
  const debugMap = (manipulationResults.debug ?? {}) as Record<string, any>;
  const overlayDebugKey = useMemo(() => {
    if (debugMap[overlayKey]) {
      return overlayKey;
    }
    if (debugMap.latex_dual_layer) {
      return "latex_dual_layer";
    }
    const keys = Object.keys(debugMap);
    return keys.length ? keys[0] : overlayKey;
  }, [debugMap, overlayKey]);
  const logsByQuestion = useMemo(() => {
    const grouped = new Map<string, any[]>();
    generationLogs.forEach((entry) => {
      const key = String(entry?.question_number ?? entry?.question_id ?? entry?.question ?? "unknown");
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key)!.push(entry);
    });
    grouped.forEach((entries) =>
      entries.sort((a, b) => {
        const aTime = a?.timestamp ? new Date(a.timestamp).getTime() : 0;
        const bTime = b?.timestamp ? new Date(b.timestamp).getTime() : 0;
        return aTime - bTime;
      })
    );
    return grouped;
  }, [generationLogs]);

  const orderedQuestions = useMemo(() => {
    return [...questions].sort((a, b) => {
      const aIndex = typeof a.sequence_index === "number" ? a.sequence_index : 0;
      const bIndex = typeof b.sequence_index === "number" ? b.sequence_index : 0;
      if (aIndex !== bIndex) {
        return aIndex - bIndex;
      }
      return a.id - b.id;
    });
  }, [questions]);

  const logKeyOrder = useMemo(() => {
    const orderedNumbers = orderedQuestions.map((question) => String(question.question_number ?? question.id));
    const extraKeys = Array.from(logsByQuestion.keys()).filter((key) => !orderedNumbers.includes(key));
    return [...orderedNumbers, ...extraKeys];
  }, [orderedQuestions, logsByQuestion]);

  const resolveRelativePath = useMemo(() => {
    if (!runId) {
      return (raw: string | undefined) => raw ?? "";
    }
    const marker = `/pipeline_runs/${runId}/`;
    return (raw: string | undefined) => {
      if (!raw) return "";
      const normalized = raw.replace(/\\/g, "/");
      const idx = normalized.indexOf(marker);
      if (idx !== -1) {
        return normalized.slice(idx + marker.length);
      }
      const parts = normalized.split("/pipeline_runs/");
      if (parts.length > 1) {
        return parts[1].split("/").slice(1).join("/");
      }
      return normalized.startsWith("/") ? normalized.slice(1) : normalized;
    };
  }, [runId]);

  const spanPlanRelativePath = useMemo(() => {
    const artifacts = overlayRenderStats.artifact_rel_paths ?? overlayRenderStats.artifacts ?? {};
    const artifactSection = artifactsMap[overlayArtifactsKey] ?? {};
    const rawPath: string | undefined = artifacts.span_plan ?? artifactSection?.span_plan ?? artifactSection?.span_plan_path;
    return resolveRelativePath(rawPath);
  }, [artifactsMap, overlayArtifactsKey, overlayRenderStats, resolveRelativePath]);

  const spanPlanUrl = runId && spanPlanRelativePath ? `/api/files/${runId}/${spanPlanRelativePath}` : null;

  const spanPlanStatsByQuestion = useMemo(() => {
    const stats: Record<number, { spans: number }> = {};
    const spanPlanSource = debugMap[overlayDebugKey]?.span_plan ?? overlayRenderStats.span_plan ?? {};
    if (spanPlanSource && typeof spanPlanSource === "object") {
      Object.values(spanPlanSource).forEach((entryList: any) => {
        if (!Array.isArray(entryList)) return;
        entryList.forEach((entry: any) => {
          const mappings: any[] = Array.isArray(entry?.mappings) ? entry.mappings : [];
          if (!mappings.length) return;
          const seen = new Set<number>();
          mappings.forEach((mapping) => {
            const manipulationId = typeof mapping?.manipulation_id === "number" ? mapping.manipulation_id : null;
            if (manipulationId == null || seen.has(manipulationId)) return;
            seen.add(manipulationId);
            stats[manipulationId] = stats[manipulationId] || { spans: 0 };
            stats[manipulationId].spans += 1;
          });
        });
      });
    }
    return stats;
  }, [debugMap, overlayDebugKey, overlayRenderStats]);

  const spanSummary = useMemo(() => {
    const summary = overlayRenderStats.span_plan_summary || {};
    const totalEntries = typeof summary.entries === "number" ? summary.entries : null;
    const scaledEntries =
      typeof summary.scaled_entries === "number"
        ? summary.scaled_entries
        : typeof overlayRenderStats.scaled_spans === "number"
        ? overlayRenderStats.scaled_spans
        : null;
    const pageCount = typeof summary.pages === "number" ? summary.pages : null;
    return { totalEntries, scaledEntries, pageCount };
  }, [overlayRenderStats]);

  const getEffectiveMappingStats = useCallback((question: QuestionManipulation) => {
    const stagedEntry = stagedMappings[question.id];
    if (stagedEntry?.status === "validated" && stagedEntry.staged_mapping) {
      return {
        mappings: [stagedEntry.staged_mapping],
        total: 1,
        validated: 1,
        staged: stagedEntry,
        status: stagedEntry.status,
      };
    }

    const mappings = question.substring_mappings || [];
    const validated = mappings.filter((m) => m.validated === true).length;
    return {
      mappings,
      total: mappings.length,
      validated,
      staged: stagedEntry,
      status: stagedEntry?.status,
    };
  }, [stagedMappings]);

  const questionMappingStats = useMemo(() => {
    return questions.reduce<Record<number, ReturnType<typeof getEffectiveMappingStats>>>((acc, q) => {
      acc[q.id] = getEffectiveMappingStats(q);
      return acc;
    }, {});
  }, [questions, getEffectiveMappingStats]);

  const aggregateStats = useMemo(() => {
    return questions.reduce(
      (acc, question) => {
        const stats = getEffectiveMappingStats(question);
        acc.totalMappings += stats.total;
        acc.validatedMappings += stats.validated;
        if (stats.total > 0 || stats.status === "validated") {
          acc.questionsWithMappings += 1;
        }
        if (stats.validated > 0 || stats.status === "validated") {
          acc.questionsWithValidated += 1;
        }
        if (stats.status === "no_valid_mapping") {
          acc.questionsSkipped += 1;
        }
        return acc;
      },
      { totalMappings: 0, validatedMappings: 0, questionsWithMappings: 0, questionsWithValidated: 0, questionsSkipped: 0 }
    );
  }, [questions, getEffectiveMappingStats]);

  const { totalMappings, validatedMappings, questionsWithMappings, questionsWithValidated, questionsSkipped } = aggregateStats;

  const applyGenerationSnapshot = useCallback((snapshot: any) => {
    const rawSummary = snapshot?.status_summary || {};
    const normalizedSummary: Record<number, any> = {};
    Object.entries(rawSummary).forEach(([key, value]) => {
      normalizedSummary[Number(key)] = value;
    });
    setGenerationStatus(normalizedSummary);

    setGenerationLogs(snapshot?.logs || []);

    const rawStaged = snapshot?.staged || {};
    const normalizedStaged: Record<number, any> = {};
    Object.entries(rawStaged).forEach(([key, value]) => {
      normalizedStaged[Number(key)] = value;
    });
    setStagedMappings(normalizedStaged);
  }, []);

  const pollGenerationStatus = useCallback(
    (options?: { questionId?: number; onComplete?: () => void }) => {
      if (!activeRunId) {
        options?.onComplete?.();
        return () => undefined;
      }

      let cancelled = false;
      let timeoutRef: number | undefined;
      const doneStatuses = new Set(["success", "failed", "no_valid_mapping"]);

      const poll = async () => {
        if (cancelled || !activeRunId) {
          return;
        }

        try {
          const status = await getGenerationStatus(activeRunId);
          applyGenerationSnapshot(status);

          const normalizedSummary = Object.entries(status.status_summary || {}).reduce<Record<number, any>>((acc, [key, value]) => {
            acc[Number(key)] = value;
            return acc;
          }, {});

          const checkQuestionId = options?.questionId;
          const isComplete = checkQuestionId != null
            ? doneStatuses.has(normalizedSummary[checkQuestionId]?.status)
            : Object.values(normalizedSummary).every((entry: any) => doneStatuses.has(entry?.status));

          if (!isComplete && !cancelled) {
            timeoutRef = window.setTimeout(poll, 2000);
          } else if (!cancelled) {
            options?.onComplete?.();
          }
        } catch (err) {
          console.error("Failed to poll generation status:", err);
          options?.onComplete?.();
        }
      };

      poll();

      return () => {
        cancelled = true;
        if (timeoutRef) {
          window.clearTimeout(timeoutRef);
        }
      };
    },
    [activeRunId, applyGenerationSnapshot]
  );

  const handleQuestionUpdated = useCallback((updated: any, options?: { revalidate?: boolean }) => {
    mutate((current) => {
      if (!current) return current;
      const next = { ...current } as any;
      next.questions = (next.questions || []).map((q: any) => {
        if (q.id === updated.id) {
          return {
            ...q,
            ...updated,
            substring_mappings: updated.substring_mappings || q.substring_mappings || []
          };
        }
        return q;
      });
      return next;
    }, { revalidate: false });

    if (options?.revalidate !== false) {
      setTimeout(() => mutate(), 100);
    }
  }, [mutate]);

  const readyForPdf = questionsWithValidated > 0;

  const onFinalize = async () => {
    if (!activeRunId || !readyForPdf || isFinalizing) return;
    setIsFinalizing(true);
    setBulkError(null);
    try {
      const result = await resumeFromStage(activeRunId, "pdf_creation", {
        targetStages: ["document_enhancement", "pdf_creation", "results_generation"],
      });
      await refresh();
      await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      setPreferredStage("pdf_creation");

      const promoted = result?.promotion_summary?.promoted?.length ?? 0;
      const skipped = result?.promotion_summary?.skipped?.length ?? 0;
      const messageParts: string[] = [];
      if (promoted > 0) {
        messageParts.push(`${promoted} question${promoted === 1 ? "" : "s"} promoted`);
      }
      if (skipped > 0) {
        messageParts.push(`${skipped} skipped`);
      }
      setBulkMessage(messageParts.length ? `PDF creation queued (${messageParts.join(", ")})` : "PDF creation queued.");
      setTimeout(() => setBulkMessage(null), 5000);
    } catch (err: any) {
      const message = err?.response?.data?.error || err?.message || String(err);
      setBulkError(`Failed to proceed to PDF creation: ${message}`);
    } finally {
      setIsFinalizing(false);
    }
  };

  const handleGenerateQuestion = useCallback(async (question: QuestionManipulation) => {
    if (!activeRunId || generatingQuestionId === question.id || isGeneratingMappings) return;
    setBulkError(null);
    setBulkMessage(null);
    setGeneratingQuestionId(question.id);
    try {
      await generateMappingsForQuestion(activeRunId, question.id, { k: 1, strategy: "replacement" });

      pollGenerationStatus({
        questionId: question.id,
        onComplete: async () => {
          setGeneratingQuestionId(null);
          await refresh();
          if (activeRunId) {
            await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
          }
          setBulkMessage(`Mapping job finished for question ${question.question_number}.`);
          setTimeout(() => setBulkMessage(null), 4000);
        },
      });
    } catch (err: any) {
      console.error("generateMappingsForQuestion", err);
      const message = err?.response?.data?.error || err?.message || String(err);
      setBulkError(`Failed to generate mappings for question ${question.question_number}: ${message}`);
      setGeneratingQuestionId(null);
    }
  }, [activeRunId, generatingQuestionId, isGeneratingMappings, pollGenerationStatus, refresh, refreshStatus]);

  const handleGenerateMappings = useCallback(async () => {
    if (!activeRunId || isGeneratingMappings || generatingQuestionId !== null) return;
    
    setIsGeneratingMappings(true);
    setBulkError(null);
    setBulkMessage(null);
    
    try {
      await generateMappingsForAll(activeRunId, { k: 1, strategy: "replacement" });

      pollGenerationStatus({
        onComplete: async () => {
          setIsGeneratingMappings(false);
          await refresh();
          if (activeRunId) {
            await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
          }
          setBulkMessage("Mapping generation completed for all questions.");
          setTimeout(() => setBulkMessage(null), 5000);
        },
      });
    } catch (err: any) {
      console.error("Failed to generate mappings:", err);
      const message = err?.response?.data?.error || err?.message || String(err);
      setBulkError(`Failed to generate mappings: ${message}`);
      setIsGeneratingMappings(false);
    }
  }, [activeRunId, generatingQuestionId, isGeneratingMappings, pollGenerationStatus, refresh, refreshStatus]);
  const handleQuestionSelect = useCallback((questionId: number) => {
    setSelectedQuestionId(prev => prev === questionId ? null : questionId);
  }, []);

  React.useEffect(() => {
    if (status?.current_stage === "pdf_creation") {
      // no-op here; PipelineContainer reacts to status
    }
  }, [status?.current_stage]);

  useEffect(() => {
    if (!activeRunId) {
      setGenerationStatus({});
      setStagedMappings({});
      setGenerationLogs([]);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const snapshot = await getGenerationStatus(activeRunId);
        if (!cancelled) {
          applyGenerationSnapshot(snapshot);
        }
      } catch (err) {
        console.warn("Failed to load generation status", err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeRunId, applyGenerationSnapshot]);

  if (isLoading) {
    return (
      <div className="panel smart-substitution">
        <div className="panel-loading">
          <div className="panel-loading__indicator" aria-hidden="true" />
          <span>Loading questions…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="panel smart-substitution">
      <header className="panel-header panel-header--tight">
        <div className="panel-title">
          <h1>Strategy</h1>
          <p>Generate, review, and validate manipulations before PDF creation.</p>
        </div>
        <div className="panel-actions">
          <button
            className="ghost-button button-with-icon"
            onClick={handleGenerateMappings}
            disabled={!questions.length || isGeneratingMappings || generatingQuestionId !== null}
            title="Generate mappings for all questions"
          >
            <ListChecks size={16} aria-hidden="true" />
            <span>{isGeneratingMappings ? "Generating…" : "Generate"}</span>
          </button>
          {spanPlanUrl ? (
            <a className="ghost-button button-with-icon" href={spanPlanUrl} target="_blank" rel="noopener noreferrer">
              <FileSpreadsheet size={16} aria-hidden="true" />
              <span>Span Plan</span>
            </a>
          ) : null}
          {runId ? (
            <button
              className="ghost-button button-with-icon"
              onClick={() => setShowLogs(!showLogs)}
              disabled={isGeneratingMappings}
            >
              <ScrollText size={16} aria-hidden="true" />
              <span>{showLogs ? "Hide Logs" : "Show Logs"}</span>
            </button>
          ) : null}
          <button
            onClick={onFinalize}
            disabled={!readyForPdf || generatingQuestionId !== null || isGeneratingMappings || isFinalizing}
            className={clsx("primary-button button-with-icon", isFinalizing && "is-loading")}
            aria-busy={isFinalizing}
            title={readyForPdf ? "Promote staged mappings and continue" : "Validate a mapping to continue"}
          >
            <ArrowRight size={16} aria-hidden="true" />
            <span>{isFinalizing ? "Continuing…" : "Create PDFs"}</span>
          </button>
        </div>
      </header>
      {bulkMessage ? <div className="panel-flash panel-flash--success">{bulkMessage}</div> : null}
      {bulkError ? <div className="panel-flash panel-flash--error">{bulkError}</div> : null}

      {isGeneratingMappings && Object.keys(generationStatus).length > 0 ? (
        <section className="strategy-progress">
          <header>
            <span>Generation progress</span>
          </header>
          <div className="strategy-progress__grid">
            {Object.entries(generationStatus).map(([questionId, progress]: [string, any]) => {
              const question = questions.find((q) => q.id === parseInt(questionId, 10));
              if (!question) return null;
              const statusValue = progress?.status ?? "pending";
              const questionKey = String(progress.question_number ?? question.question_number ?? question.id);
              const questionLogs = logsByQuestion.get(questionKey) ?? [];
              const generationLoops =
                questionLogs.filter((entry) => entry?.stage === "generation").length ||
                Math.max(progress?.mappings_generated ?? 0, statusValue === "success" ? 1 : 0);
              const validationLogs = questionLogs.filter((entry) => entry?.stage === "validation");
              const hasValidationFailure =
                statusValue === "failed" || validationLogs.some((entry) => entry?.status === "failed");
              const hasValidationSuccess =
                progress?.mappings_validated > 0 || validationLogs.some((entry) => entry?.status === "success");

              const stateClass = hasValidationFailure
                ? "is-error"
                : hasValidationSuccess
                ? "is-success"
                : statusValue === "running"
                ? "is-running"
                : "is-pending";

              return (
                <div key={questionId} className={clsx("strategy-progress__row", stateClass)}>
                  <span className="strategy-progress__id" title={`Question ${questionKey}`}>
                    Q{questionKey}
                  </span>
                  <span className="strategy-progress__meta">
                    <span className="status-chip status-chip--generation" title="Generation attempts">
                      Gen {Math.max(0, generationLoops)}×
                    </span>
                    <span
                      className={clsx(
                        "status-chip",
                        "status-chip--validation",
                        hasValidationFailure ? "is-error" : hasValidationSuccess ? "is-success" : "is-pending"
                      )}
                      title={
                        hasValidationFailure
                          ? "Latest validation failed"
                          : hasValidationSuccess
                          ? "Validation succeeded"
                          : "Awaiting validation results"
                      }
                    >
                      {hasValidationFailure
                        ? "Validation ✕"
                        : hasValidationSuccess
                        ? "Validation ✓"
                        : "Validation …"}
                    </span>
                    <span className="status-chip status-chip--totals" title="Generated vs validated mappings">
                      {progress.mappings_generated || 0} gen · {progress.mappings_validated || 0} val
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {/* Generation Logs Viewer */}
        {showLogs && (
          <div style={{ 
            padding: '1rem', 
            backgroundColor: 'var(--bg-secondary)', 
            borderRadius: '8px',
            border: '1px solid var(--border)',
            maxHeight: '420px',
            overflowY: 'auto'
          }}>
            <h3 style={{ fontSize: '16px', margin: '0 0 0.75rem 0' }}>Mapping Logs</h3>
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              {logKeyOrder.length === 0 ? (
                <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>No questions available.</div>
              ) : logKeyOrder.map((key) => {
                const logs = logsByQuestion.get(key) ?? [];
                const question = orderedQuestions.find((q) => String(q.question_number ?? q.id) === key)
                  ?? questions.find((q) => String(q.question_number ?? q.id) === key);
                const heading = question ? `Question ${question.question_number}` : `Question ${key}`;
                const snippet = question?.stem_text
                  ? `${question.stem_text.slice(0, 110)}${question.stem_text.length > 110 ? '...' : ''}`
                  : null;
                return (
                  <div key={key} style={{ 
                    padding: '0.75rem',
                    backgroundColor: 'var(--bg)',
                    borderRadius: '6px',
                    border: '1px solid rgba(148,163,184,0.2)',
                    display: 'grid',
                    gap: '0.5rem'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center' }}>
                      <div style={{ fontWeight: 600 }}>{heading}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>{logs.length ? `${logs.length} event${logs.length === 1 ? '' : 's'}` : 'No events'}</div>
                    </div>
                    {snippet ? <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>{snippet}</div> : null}
                    <div style={{ display: 'grid', gap: '0.45rem' }}>
                      {logs.length ? logs.map((log, idx) => {
                        const stageLabel = log.stage === 'generation' ? 'Generate' : log.stage === 'validation' ? 'Validate' : String(log.stage || 'Stage');
                        const statusText = (log.status ?? 'unknown').toString();
                        const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';
                        const statusColor = (statusText === 'success'
                          ? 'rgba(52,211,153,0.85)'
                          : statusText === 'failed'
                            ? 'rgba(248,113,113,0.85)'
                            : 'rgba(250,204,21,0.85)');
                        return (
                          <div key={`${key}-${idx}`} style={{
                            padding: '0.65rem',
                            borderRadius: '6px',
                            border: '1px solid rgba(148,163,184,0.2)',
                            backgroundColor: 'rgba(15,23,42,0.45)',
                            display: 'grid',
                            gap: '0.35rem'
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                              <span style={{ fontWeight: 600 }}>{stageLabel}</span>
                              <span style={{ color: statusColor, fontSize: '0.85rem' }}>{statusText}{timestamp ? ` · ${timestamp}` : ''}</span>
                            </div>
                            <div style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'grid', gap: '0.25rem' }}>
                              {log.mappings_generated != null && <span>Generated: {log.mappings_generated}</span>}
                              {log.mappings_validated != null && <span>Validated: {log.mappings_validated}</span>}
                              {log.details?.strategy && <span>Strategy: {log.details.strategy}</span>}
                              {log.details?.job_id && <span style={{ fontSize: '0.75rem' }}>Job ID: {log.details.job_id}</span>}
                            </div>
                            {Array.isArray(log.validation_logs) && log.validation_logs.length > 0 && (
                              <div style={{ display: 'grid', gap: '0.35rem' }}>
                                {log.validation_logs.map((validation: any, validationIdx: number) => {
                                  const validationStatus = validation?.status ?? 'unknown';
                                  const reason = validation?.details?.validation_result?.reasoning;
                                  return (
                                    <div key={validationIdx} style={{
                                      padding: '0.55rem',
                                      borderRadius: '6px',
                                      backgroundColor: 'rgba(22, 33, 58, 0.7)',
                                      border: '1px solid rgba(148,163,184,0.15)',
                                      fontSize: '0.8rem'
                                    }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                                        <strong>Validation #{(validation?.mapping_index ?? validationIdx) + 1}</strong>
                                        <span>{validationStatus}</span>
                                      </div>
                                      {reason ? (
                                        <div style={{ marginTop: '0.25rem', color: 'var(--muted)' }}>
                                          {reason.slice(0, 160)}{reason.length > 160 ? '...' : ''}
                                        </div>
                                      ) : null}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      }) : (
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>No log entries captured yet.</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="info-grid">
          <div className="info-card">
            <span className="info-label">Stage status</span>
            <span className="info-value">{stage?.status ?? 'pending'}</span>
          </div>
          <div className="info-card">
            <span className="info-label">Questions mapped</span>
            <span className="info-value">{questionsWithMappings}/{questions.length}</span>
          </div>
          <div className="info-card">
            <span className="info-label">Questions validated</span>
            <span className="info-value">{questionsWithValidated}/{questions.length}</span>
          </div>
        <div className="info-card">
          <span className="info-label">Questions skipped</span>
          <span className="info-value">{questionsSkipped}</span>
        </div>
          <div className="info-card">
            <span className="info-label">Mappings</span>
            <span className="info-value">{totalMappings}</span>
          </div>
          <div className="info-card">
            <span className="info-label">Validated mappings</span>
            <span className="info-value">{validatedMappings}</span>
          </div>
          <div className="info-card">
            <span className="info-label">Duration</span>
            <span className="info-value">{formatDuration(stage?.duration_ms)}</span>
          </div>
          {(spanSummary.totalEntries != null || spanSummary.scaledEntries != null) && (
            <div className="info-card">
              <span className="info-label">Span rewrites</span>
              <span className="info-value">
                {spanSummary.scaledEntries != null ? `${spanSummary.scaledEntries} scaled` : '–'}
                {spanSummary.totalEntries != null ? ` / ${spanSummary.totalEntries} total` : ''}
                {spanSummary.pageCount != null ? ` · ${spanSummary.pageCount} page${spanSummary.pageCount === 1 ? '' : 's'}` : ''}
              </span>
            </div>
          )}
        </div>

      {/* Questions Grid */}
      <div style={{ display: 'grid', gap: '20px' }}>
        {orderedQuestions.map((question) => {
          const stats = questionMappingStats[question.id] ?? getEffectiveMappingStats(question);
          const stagedEntry = stats.staged;
          const mappings = stats.mappings;
          const hasMappings = stats.total > 0 || stagedEntry?.status === "validated";
          const isSelected = selectedQuestionId === question.id;
          const isGeneratingThis = generatingQuestionId === question.id;
          const spanInfo = spanPlanStatsByQuestion[question.id];

          const allValidatedForQuestion = stats.validated > 0 || stagedEntry?.status === "validated";
          const hasSkip = stagedEntry?.status === "no_valid_mapping";
          const hasFailure = stagedEntry?.status === "failed";

          const effectiveQuestion = stagedEntry?.status === "validated" && stagedEntry.staged_mapping
            ? { ...question, substring_mappings: mappings }
            : question;

          const validationBadgeStyle = allValidatedForQuestion
            ? { backgroundColor: 'rgba(52,211,153,0.18)', color: '#34d399' }
            : { backgroundColor: 'rgba(250,204,21,0.22)', color: '#fbbf24' };

          const cardBorderColor = isGeneratingThis
            ? 'rgba(56,189,248,0.7)'
            : hasFailure
              ? 'rgba(248,113,113,0.65)'
              : hasSkip
                ? 'rgba(250,204,21,0.45)'
                : hasMappings
                  ? 'rgba(52,211,153,0.65)'
                  : 'rgba(148,163,184,0.22)';

          const cardBackground = isSelected
            ? 'rgba(15,23,42,0.35)'
            : isGeneratingThis
              ? 'rgba(15,23,42,0.55)'
              : hasFailure
                ? 'rgba(127,29,29,0.35)'
                : hasSkip
                  ? 'rgba(120,53,15,0.35)'
                  : 'rgba(15,23,42,0.45)';

          return (
            <div key={question.id} style={{
              border: `2px solid ${isSelected && !isGeneratingThis ? 'rgba(56,189,248,0.65)' : cardBorderColor}`,
              borderRadius: '12px',
              backgroundColor: cardBackground,
              boxShadow: isSelected
                ? '0 4px 12px rgba(0,123,255,0.15)'
                : isGeneratingThis
                  ? '0 8px 20px rgba(56,189,248,0.18)'
                  : hasFailure
                    ? '0 6px 16px rgba(248,113,113,0.2)'
                    : hasSkip
                      ? '0 6px 16px rgba(251,191,36,0.2)'
                  : '0 2px 10px rgba(8,12,24,0.25)',
              transition: 'all 0.2s ease',
              overflow: 'hidden'
            }}>
              {/* Question Header */}
              <div
                onClick={() => handleQuestionSelect(question.id)}
                style={{
                  padding: '20px',
                  cursor: 'pointer',
                  borderBottom: isSelected ? '1px solid rgba(148,163,184,0.18)' : 'none',
                  backgroundColor: isSelected ? 'rgba(15,23,42,0.45)' : 'transparent'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                  <div style={{ flex: 1 }}>
                    {isGeneratingThis && (
                      <div style={{
                        alignSelf: 'flex-start',
                        fontSize: '12px',
                        marginBottom: '6px',
                        padding: '2px 8px',
                        borderRadius: '9999px',
                        backgroundColor: 'rgba(56,189,248,0.22)',
                        border: '1px solid rgba(56,189,248,0.35)',
                        color: '#bae6fd',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <span role="img" aria-label="sparkles">✨</span>
                        Mapping in progress...
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                      <h3 style={{
                        fontSize: '20px',
                        fontWeight: 'bold',
                        color: 'var(--text)',
                        margin: 0
                      }}>
                        Question {question.question_number}
                      </h3>
                      <span style={{
                        padding: '4px 8px',
                        backgroundColor: 'rgba(148,163,184,0.18)',
                        borderRadius: '4px',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        color: 'var(--text)',
                        textTransform: 'uppercase'
                      }}>
                        {question.question_type?.replace('_', ' ')}
                      </span>
                      {allValidatedForQuestion && (
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          ...validationBadgeStyle
                        }}>
                          ✅ {stats.validated || 1}/{stats.total || 1} validated
                        </span>
                      )}
                      {hasSkip && (
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          backgroundColor: 'rgba(250,204,21,0.22)',
                          color: '#fbbf24'
                        }}>
                          ⚠️ No valid mapping
                        </span>
                      )}
                      {hasFailure && (
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          backgroundColor: 'rgba(248,113,113,0.22)',
                          color: '#f87171'
                        }}>
                          ❌ Generation error
                        </span>
                      )}
                      {spanInfo && (
                        <span style={{
                          padding: '4px 8px',
                          backgroundColor: 'rgba(56,189,248,0.18)',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          color: '#38bdf8'
                        }}>
                          🖼️ {spanInfo.spans} span{spanInfo.spans === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>

                    {/* Gold Answer Display */}
                    {question.gold_answer && (
                      <div style={{
                        padding: '8px 12px',
                        backgroundColor: 'rgba(250,204,21,0.15)',
                        border: '1px solid #ffeaa7',
                        borderRadius: '6px',
                        marginBottom: '12px'
                      }}>
                        <div style={{ fontSize: '12px', fontWeight: 'bold', color: 'var(--muted)', marginBottom: '4px' }}>
                          🏆 GPT-5 Gold Answer
                        </div>
                        <div style={{ color: 'var(--muted)', fontWeight: 'bold' }}>
                          {question.gold_answer}
                          {question.gold_confidence && (
                            <span style={{ fontSize: '12px', marginLeft: '8px', opacity: 0.8 }}>
                              (Confidence: {Math.round(question.gold_confidence * 100)}%)
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Question Preview */}
                    <div style={{
                      fontSize: '16px',
                      lineHeight: '1.5',
                      color: 'var(--text)',
                      marginBottom: '8px'
                    }}>
                      {(question.stem_text || question.original_text || 'No question text available').substring(0, 200)}
                      {(question.stem_text || question.original_text || '').length > 200 && '...'}
                    </div>

                    {/* Mapping Count */}
                    <div style={{ fontSize: '14px', color: 'var(--muted)' }}>
                      {stats.total} mapping{stats.total !== 1 ? 's' : ''} configured
                      {stats.total > 0 && (
                        <span style={{ marginLeft: '6px' }}>
                          · {stats.validated} validated
                        </span>
                      )}
                      {hasSkip && (
                        <span style={{ marginLeft: '6px', color: '#fbbf24' }}>
                          · awaiting new target
                        </span>
                      )}
                      {hasFailure && (
                        <span style={{ marginLeft: '6px', color: '#f87171' }}>
                          · error
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '10px' }}>
                    <button
                      className="pill-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleGenerateQuestion(question);
                      }}
                      disabled={generatingQuestionId === question.id || isGeneratingMappings}
                      style={{
                        fontSize: '12px',
                        padding: '4px 10px',
                        backgroundColor: 'rgba(59,130,246,0.25)',
                        border: '1px solid rgba(59,130,246,0.35)',
                        color: '#bfdbfe'
                      }}
                      title="Queue GPT-5 generation for this question"
                    >
                      {generatingQuestionId === question.id ? 'Generating...' : 'Generate'}
                    </button>
                    <div style={{
                      fontSize: '24px',
                      transform: isSelected ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease',
                      color: 'var(--muted)'
                    }}>
                      ▼
                    </div>
                  </div>
                </div>
              </div>

              {/* Expanded Question Editor */}
              {isSelected && (
                <div style={{ padding: '0 20px 20px 20px' }}>
                  {hasSkip && stagedEntry?.skip_reason && (
                    <div style={{
                      marginBottom: '12px',
                      padding: '10px 12px',
                      backgroundColor: 'rgba(250,204,21,0.18)',
                      border: '1px solid rgba(250,204,21,0.35)',
                      borderRadius: '8px',
                      color: '#fbbf24',
                      fontSize: '13px'
                    }}>
                      ⚠️ {stagedEntry.skip_reason}
                    </div>
                  )}
                  {hasFailure && stagedEntry?.error && (
                    <div style={{
                      marginBottom: '12px',
                      padding: '10px 12px',
                      backgroundColor: 'rgba(248,113,113,0.18)',
                      border: '1px solid rgba(248,113,113,0.35)',
                      borderRadius: '8px',
                      color: '#f87171',
                      fontSize: '13px'
                    }}>
                      ❌ {stagedEntry.error}
                    </div>
                  )}

                  {stagedEntry?.validation_summary && (
                    <div style={{
                      marginBottom: '12px',
                      padding: '10px 12px',
                      backgroundColor: 'rgba(52,211,153,0.12)',
                      border: '1px solid rgba(52,211,153,0.3)',
                      borderRadius: '8px',
                      color: '#34d399',
                      fontSize: '13px'
                    }}>
                      ✅ Confidence {Math.round((stagedEntry.validation_summary.confidence ?? 0) * 100)}% · Deviation {Math.round((stagedEntry.validation_summary.deviation_score ?? 0) * 100) / 100}
                    </div>
                  )}
                  <EnhancedQuestionViewer
                    runId={activeRunId!}
                    question={effectiveQuestion}
                    onUpdated={handleQuestionUpdated}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default SmartSubstitutionPanel;
