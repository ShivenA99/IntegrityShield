import * as React from "react";
import { useState, useCallback, useEffect, useMemo } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { updateQuestionManipulation, generateMappingsForAll, generateMappingsForQuestion, getGenerationStatus } from "@services/api/questionApi";
import type { QuestionManipulation } from "@services/types/questions";
import { formatDuration } from "@services/utils/formatters";
import EnhancedQuestionViewer from "@components/question-level/EnhancedQuestionViewer";

const SmartSubstitutionPanel: React.FC = () => {
  const { activeRunId, resumeFromStage, status, refreshStatus } = usePipeline();
  const { questions, isLoading, refresh, mutate } = useQuestions(activeRunId);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [isAddingRandomMappings, setIsAddingRandomMappings] = useState(false);
  const [generatingQuestionId, setGeneratingQuestionId] = useState<number | null>(null);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [isGeneratingMappings, setIsGeneratingMappings] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<Record<number, any>>({});
  const [generationLogs, setGenerationLogs] = useState<any[]>([]);
  const [stagedMappings, setStagedMappings] = useState<Record<number, any>>({});
  const [showLogs, setShowLogs] = useState(false);
  const stage = status?.stages.find((item) => item.name === "smart_substitution");
  const runId = status?.run_id ?? activeRunId ?? null;
  const structuredData = (status?.structured_data ?? {}) as Record<string, any>;

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
    const renderStats = structuredData?.manipulation_results?.enhanced_pdfs?.latex_dual_layer?.render_stats ?? {};
    const artifacts = renderStats.artifact_rel_paths ?? renderStats.artifacts ?? {};
    const rawPath: string | undefined = artifacts.span_plan ?? structuredData?.manipulation_results?.artifacts?.latex_dual_layer?.span_plan;
    return resolveRelativePath(rawPath);
  }, [resolveRelativePath, structuredData]);

  const spanPlanUrl = runId && spanPlanRelativePath ? `/api/files/${runId}/${spanPlanRelativePath}` : null;

  const spanPlanStatsByQuestion = useMemo(() => {
    const stats: Record<number, { spans: number }> = {};
    const debugPlan = structuredData?.manipulation_results?.debug?.latex_dual_layer?.span_plan ?? null;
    const renderStats = structuredData?.manipulation_results?.enhanced_pdfs?.latex_dual_layer?.render_stats ?? {};
    const spanPlan = debugPlan || renderStats.span_plan || {};
    if (spanPlan && typeof spanPlan === "object") {
      Object.values(spanPlan).forEach((entryList: any) => {
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
  }, [structuredData]);

  const spanSummary = useMemo(() => {
    const renderStats = structuredData?.manipulation_results?.enhanced_pdfs?.latex_dual_layer?.render_stats ?? {};
    const summary = renderStats.span_plan_summary || {};
    const totalEntries = typeof summary.entries === "number" ? summary.entries : null;
    const scaledEntries = typeof summary.scaled_entries === "number"
      ? summary.scaled_entries
      : (typeof renderStats.scaled_spans === "number" ? renderStats.scaled_spans : null);
    const pageCount = typeof summary.pages === "number" ? summary.pages : null;
    return { totalEntries, scaledEntries, pageCount };
  }, [structuredData]);

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

  const generateFallbackMapping = (question: QuestionManipulation) => {
    const questionText = question.stem_text || question.original_text || "";
    if (!questionText) return null;

    const commonWords = ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'];
    const words = questionText.split(/\s+/);
    const candidates = words.filter(word =>
      word.length > 2 &&
      !commonWords.includes(word.toLowerCase()) &&
      /^[a-zA-Z]+$/.test(word)
    );

    if (candidates.length === 0) return null;

    const targetWord = candidates[Math.floor(Math.random() * candidates.length)];
    const startPos = questionText.indexOf(targetWord);
    if (startPos === -1) return null;

    const selectionPage = typeof question.positioning?.page === "number"
      ? Math.max(0, question.positioning!.page - 1)
      : undefined;
    const selectionBbox = Array.isArray(question.positioning?.bbox) && question.positioning!.bbox.length === 4
      ? question.positioning!.bbox
      : undefined;

    return [{
      id: Math.random().toString(36).substr(2, 9),
      original: targetWord,
      replacement: "not",
      start_pos: startPos,
      end_pos: startPos + targetWord.length,
      context: "question_stem",
      selection_page: selectionPage,
      selection_bbox: selectionBbox,
    }];
  };

  // Add random mappings to all questions for testing
  const addRandomMappingsToAll = useCallback(async () => {
    if (!activeRunId || isAddingRandomMappings) return;

    setIsAddingRandomMappings(true);
    try {
      for (const question of questions) {
        // Skip if question already has mappings
        if (question.substring_mappings && question.substring_mappings.length > 0) {
          continue;
        }

        const fallbackMappings = generateFallbackMapping(question);

        if (fallbackMappings && fallbackMappings.length) {
          const mapping = { ...fallbackMappings[0], replacement: "not" };
          const mappings = [mapping];

          // Save to backend
          const response = await updateQuestionManipulation(activeRunId, question.id, {
            method: question.manipulation_method || "smart_substitution",
            substring_mappings: mappings
          });

          // Update local cache
          const serverMappings = response?.substring_mappings ?? mappings;
          handleQuestionUpdated({ ...question, substring_mappings: serverMappings }, { revalidate: false });
        }
      }
    } catch (error) {
      console.error("Failed to add random mappings:", error);
    } finally {
      setIsAddingRandomMappings(false);
      await refresh();
      if (activeRunId) {
        await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      }
    }
  }, [activeRunId, questions, isAddingRandomMappings, handleQuestionUpdated, refresh, refreshStatus]);

  const readyForPdf = questionsWithValidated > 0;

  const onFinalize = async () => {
    if (!activeRunId || !readyForPdf) return;
    setBulkError(null);
    try {
      const result = await resumeFromStage(activeRunId, "pdf_creation");
      await refresh();
      await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);

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
    }
  };

  const handleGenerateQuestion = useCallback(async (question: QuestionManipulation) => {
    if (!activeRunId || generatingQuestionId === question.id || isGeneratingMappings) return;
    setBulkError(null);
    setBulkMessage(null);
    setGeneratingQuestionId(question.id);
    try {
      await generateMappingsForQuestion(activeRunId, question.id, { k: 3, strategy: "replacement" });

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
      await generateMappingsForAll(activeRunId, { k: 3, strategy: "replacement" });

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
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <div style={{ fontSize: '18px', color: 'var(--muted)' }}>🔄 Loading questions...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="panel smart-substitution" style={{ display: 'grid', gap: '1.5rem' }}>
      {/* Header Section */}
      <div style={{ display: 'grid', gap: '0.75rem' }}>
        <h1 style={{
          fontSize: '28px',
          fontWeight: 'bold',
          color: 'var(--text)',
          margin: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          🎯 Smart Substitution
        </h1>
        <p style={{ fontSize: '16px', color: 'var(--muted)', margin: 0 }}>
          Create targeted text substitutions for each question. Click on a card to expand and edit mappings.
        </p>
        <div style={{ fontSize: '13px', color: '#93c5fd', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span role="img" aria-label="info">ℹ️</span>
          GPT-5 mappings stay staged here until you proceed to PDF creation.
        </div>

        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <button
            className="pill-button"
            onClick={handleGenerateMappings}
            disabled={!questions.length || isGeneratingMappings || generatingQuestionId !== null}
            title="Generate mappings for all questions using GPT-5"
          >
            {isGeneratingMappings ? 'Generating…' : 'Generate Mappings'}
          </button>
          {runId && (
            <button
              className="pill-button"
              onClick={() => setShowLogs(!showLogs)}
              disabled={isGeneratingMappings}
            >
              {showLogs ? 'Hide Logs' : 'Show Logs'}
            </button>
          )}
          {spanPlanUrl && (
            <a
              className="pill-button"
              href={spanPlanUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              🗂 span_plan.json
            </a>
          )}
        </div>
        {bulkMessage && <div style={{ color: 'var(--success)', fontSize: '0.9rem' }}>{bulkMessage}</div>}
        {bulkError && <div style={{ color: 'var(--danger)', fontSize: '0.9rem' }}>{bulkError}</div>}

        {/* Generation Status Indicators */}
        {isGeneratingMappings && Object.keys(generationStatus).length > 0 && (
          <div style={{ 
            padding: '1rem', 
            backgroundColor: 'var(--bg-secondary)', 
            borderRadius: '8px',
            border: '1px solid var(--border)'
          }}>
            <h3 style={{ fontSize: '16px', margin: '0 0 0.75rem 0' }}>Generation Progress</h3>
            <div style={{ display: 'grid', gap: '0.5rem' }}>
              {Object.entries(generationStatus).map(([questionId, status]: [string, any]) => {
                const question = questions.find(q => q.id === parseInt(questionId));
                if (!question) return null;
                return (
                  <div key={questionId} style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center',
                    padding: '0.5rem',
                    backgroundColor: status.status === 'success' ? 'var(--success-bg)' : 
                                     status.status === 'failed' ? 'var(--danger-bg)' : 'var(--bg)',
                    borderRadius: '4px'
                  }}>
                    <span>Question {status.question_number || question.question_number}</span>
                    <span style={{ 
                      fontSize: '0.875rem',
                      color: status.status === 'success' ? 'var(--success)' : 
                             status.status === 'failed' ? 'var(--danger)' : 'var(--muted)'
                    }}>
                      {status.status === 'success' ? '✓' : status.status === 'failed' ? '✗' : '…'} 
                      {' '}
                      {status.mappings_generated || 0} generated, {status.mappings_validated || 0} validated
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Generation Logs Viewer */}
        {showLogs && generationLogs.length > 0 && (
          <div style={{ 
            padding: '1rem', 
            backgroundColor: 'var(--bg-secondary)', 
            borderRadius: '8px',
            border: '1px solid var(--border)',
            maxHeight: '400px',
            overflowY: 'auto'
          }}>
            <h3 style={{ fontSize: '16px', margin: '0 0 0.75rem 0' }}>Generation Logs</h3>
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              {generationLogs.map((log, idx) => (
                <div key={idx} style={{ 
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg)',
                  borderRadius: '4px',
                  fontSize: '0.875rem'
                }}>
                  <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>
                    Question {log.question_number} - {log.stage} ({log.status})
                  </div>
                  {log.stage === 'generation' && (
                    <div>
                      <div>Mappings Generated: {log.mappings_generated || 0}</div>
                      {log.details?.strategy && <div>Strategy: {log.details.strategy}</div>}
                    </div>
                  )}
                  {log.stage === 'validation' && log.validation_logs && (
                    <div>
                      <div>Mappings Validated: {log.mappings_validated || 0}</div>
                      {log.first_valid_mapping_index !== null && (
                        <div>First Valid Mapping: Index {log.first_valid_mapping_index}</div>
                      )}
                      <div style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>
                        {log.validation_logs.map((vlog: any, vidx: number) => (
                          <div key={vidx} style={{ marginTop: '0.25rem' }}>
                            Mapping {vlog.mapping_index}: {vlog.status}
                            {vlog.validation_result && (
                              <div style={{ marginLeft: '1rem', color: 'var(--muted)' }}>
                                Confidence: {vlog.validation_result.confidence?.toFixed(2) || 'N/A'}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
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
                        Mapping in progress…
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
                      {generatingQuestionId === question.id ? 'Generating…' : 'Generate'}
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

      {/* Action Buttons */}
      <div style={{
        marginTop: '32px',
        padding: '20px',
        backgroundColor: 'var(--surface)' ,
        borderRadius: '12px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '16px',
        border: '1px solid rgba(148,163,184,0.18)'
      }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={refresh}
            className="pill-button"
            title="Reload questions from backend"
          >
            🔄 Refresh Questions
          </button>

          <button
            onClick={addRandomMappingsToAll}
            disabled={isAddingRandomMappings}
            className="pill-button"
            style={{
              backgroundColor: isAddingRandomMappings ? 'rgba(148,163,184,0.18)' : 'rgba(250,204,21,0.25)',
              border: '1px solid rgba(250,204,21,0.35)',
              color: isAddingRandomMappings ? 'var(--muted)' : '#0f172a'
            }}
            title="Populate sample mappings for quick experimentation"
          >
            {isAddingRandomMappings ? '⏳ Adding...' : '🎲 Add Random Mappings'}
          </button>
        </div>

        <button
          onClick={onFinalize}
          disabled={!readyForPdf || generatingQuestionId !== null || isGeneratingMappings}
          className="pill-button"
          style={{
            backgroundColor: readyForPdf ? '#34d399' : 'rgba(148,163,184,0.18)',
            color: readyForPdf ? '#0f172a' : 'var(--muted)'
          }}
          title={readyForPdf ? 'Promote staged mappings and continue to PDF creation.' : 'Generate at least one mapping before continuing.'}
        >
          ➡️ Proceed to PDF Creation
        </button>
      </div>
    </div>
  );
};

export default SmartSubstitutionPanel;
