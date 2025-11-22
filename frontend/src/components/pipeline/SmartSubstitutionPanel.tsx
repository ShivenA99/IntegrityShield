import * as React from "react";
import { useState, useCallback, useEffect, useMemo } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { autoGenerateMappings, updateQuestionManipulation, validateQuestion } from "@services/api/questionApi";
import type { QuestionManipulation, SubstringMapping } from "@services/types/questions";
import { formatDuration } from "@services/utils/formatters";
import EnhancedQuestionViewer from "@components/question-level/EnhancedQuestionViewer";

const SmartSubstitutionPanel: React.FC = () => {
  const { activeRunId, resumeFromStage, status, refreshStatus } = usePipeline();
  const { questions, isLoading, refresh, mutate } = useQuestions(activeRunId);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [isAddingRandomMappings, setIsAddingRandomMappings] = useState(false);
  const [generatingQuestionId, setGeneratingQuestionId] = useState<number | null>(null);
  const [isBulkValidating, setIsBulkValidating] = useState(false);
  const [validatingQuestionId, setValidatingQuestionId] = useState<number | null>(null);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const stage = status?.stages.find((item) => item.name === "smart_substitution");
  const totalMappings = useMemo(() => questions.reduce((acc, q) => acc + (q.substring_mappings?.length ?? 0), 0), [questions]);
  const validatedMappings = useMemo(() => questions.reduce((acc, q) => acc + ((q.substring_mappings || []).filter((m) => m.validated === true).length ?? 0), 0), [questions]);

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
    const renderStats = structuredData?.manipulation_results?.enhanced_pdfs?.content_stream_span_overlay?.render_stats ?? {};
    const artifacts = renderStats.artifact_rel_paths ?? renderStats.artifacts ?? {};
    const rawPath: string | undefined = artifacts.span_plan ?? structuredData?.manipulation_results?.artifacts?.content_stream_span_overlay?.span_plan;
    return resolveRelativePath(rawPath);
  }, [resolveRelativePath, structuredData]);

  const spanPlanUrl = runId && spanPlanRelativePath ? `/api/files/${runId}/${spanPlanRelativePath}` : null;

  const spanPlanStatsByQuestion = useMemo(() => {
    const stats: Record<string, { spans: number }> = {};
    const debugPlan = structuredData?.manipulation_results?.debug?.content_stream_span_overlay?.span_plan ?? null;
    const renderStats = structuredData?.manipulation_results?.enhanced_pdfs?.content_stream_span_overlay?.render_stats ?? {};
    const spanPlan = debugPlan || renderStats.span_plan || {};
    if (spanPlan && typeof spanPlan === "object") {
      Object.values(spanPlan).forEach((entryList: any) => {
        if (!Array.isArray(entryList)) return;
        entryList.forEach((entry: any) => {
          const mappings: any[] = Array.isArray(entry?.mappings) ? entry.mappings : [];
          if (!mappings.length) return;
          const seen = new Set<string>();
          mappings.forEach((mapping) => {
            const qNumber = mapping?.q_number != null ? String(mapping.q_number) : null;
            if (!qNumber || seen.has(qNumber)) return;
            seen.add(qNumber);
            stats[qNumber] = stats[qNumber] || { spans: 0 };
            stats[qNumber].spans += 1;
          });
        });
      });
    }
    return stats;
  }, [structuredData]);

  const spanSummary = useMemo(() => {
    const renderStats = structuredData?.manipulation_results?.enhanced_pdfs?.content_stream_span_overlay?.render_stats ?? {};
    const summary = renderStats.span_plan_summary || {};
    const totalEntries = typeof summary.entries === "number" ? summary.entries : null;
    const scaledEntries = typeof summary.scaled_entries === "number"
      ? summary.scaled_entries
      : (typeof renderStats.scaled_spans === "number" ? renderStats.scaled_spans : null);
    const pageCount = typeof summary.pages === "number" ? summary.pages : null;
    return { totalEntries, scaledEntries, pageCount };
  }, [structuredData]);

  const questionMappingStats = useMemo(() => {
    return questions.reduce<Record<number, { total: number; validated: number }>>((acc, q) => {
      const mappings = q.substring_mappings || [];
      const validated = mappings.filter((m) => m.validated === true).length;
      acc[q.id] = { total: mappings.length, validated };
      return acc;
    }, {});
  }, [questions]);

  const questionsWithMappings = useMemo(() => questions.filter((q) => (q.substring_mappings || []).length > 0).length, [questions]);
  const questionsWithValidated = useMemo(
    () => questions.filter((q) => (q.substring_mappings || []).some((m) => m.validated)).length,
    [questions]
  );

  const handleQuestionUpdated = useCallback((updated: any) => {
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

    setTimeout(() => mutate(), 100);
  }, [mutate]);

  const handleValidateQuestionMappings = useCallback(async (questionId: number) => {
    if (!activeRunId) return;
    const question = questions.find((q) => q.id === questionId);
    if (!question) return;
    const mappings = question.substring_mappings || [];
    if (mappings.length === 0) {
      setBulkError(`Question ${question.question_number} has no mappings to validate.`);
      setTimeout(() => setBulkError(null), 3000);
      return;
    }
    setValidatingQuestionId(questionId);
    setBulkError(null);
    try {
      const res = await validateQuestion(activeRunId, questionId, { substring_mappings: mappings });
      const serverMappings = res?.substring_mappings ?? mappings;
      handleQuestionUpdated({ ...question, substring_mappings: serverMappings });
      await refresh();
      if (activeRunId) {
        await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      }
      setBulkMessage(`Validated question ${question.question_number}.`);
      setTimeout(() => setBulkMessage(null), 3000);
    } catch (err: any) {
      const message = err?.response?.data?.error || err?.message || String(err);
      setBulkError(message);
    } finally {
      setValidatingQuestionId(null);
    }
  }, [activeRunId, handleQuestionUpdated, questions, refresh, refreshStatus]);

  const DEFAULT_CANONICAL_MAPPINGS: Record<string, Array<{ original: string; replacement: string }>> = {
    "1": [{ original: "the", replacement: "not" }],
    "2": [{ original: "the", replacement: "not" }],
    "3": [{ original: "LSTM", replacement: "CNN" }],
    "4": [{ original: "LSTM", replacement: "RNN" }],
    "5": [{ original: "LSTMs", replacement: "RNNs" }],
    "6": [{ original: "RNNs", replacement: "CNNs" }],
    "7": [{ original: "bidirectional", replacement: "unidirectional" }],
    "8": [{ original: "RNN", replacement: "CNN" }],
  };

  const buildCanonicalMappings = (question: QuestionManipulation) => {
    const questionText = question.stem_text || question.original_text || "";
    const entries = DEFAULT_CANONICAL_MAPPINGS[question.question_number];
    if (!entries || !questionText) return null;

    const selectionPage = typeof question.positioning?.page === "number"
      ? Math.max(0, question.positioning!.page - 1)
      : undefined;
    const selectionBbox = Array.isArray(question.positioning?.bbox) && question.positioning!.bbox.length === 4
      ? question.positioning!.bbox
      : undefined;

    const result = entries.map((entry) => {
      const start = questionText.indexOf(entry.original);
      if (start === -1) return null;
      return {
        id: Math.random().toString(36).substr(2, 9),
        original: entry.original,
        replacement: entry.replacement,
        start_pos: start,
        end_pos: start + entry.original.length,
        context: "question_stem",
        selection_page: selectionPage,
        selection_bbox: selectionBbox,
      };
    }).filter((val): val is SubstringMapping => Boolean(val));

    return result.length ? result : null;
  };

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

        const canonicalMappings = buildCanonicalMappings(question);
        const fallbackMappings = canonicalMappings ?? generateFallbackMapping(question);

        if (fallbackMappings && fallbackMappings.length) {
          const mappings = fallbackMappings;

          // Save to backend
          const response = await updateQuestionManipulation(activeRunId, question.id, {
            method: question.manipulation_method || "smart_substitution",
            substring_mappings: mappings
          });

          // Update local cache
          const serverMappings = response?.substring_mappings ?? mappings;
          handleQuestionUpdated({ ...question, substring_mappings: serverMappings });
        }
      }
    } catch (error) {
      console.error("Failed to add random mappings:", error);
    } finally {
      setIsAddingRandomMappings(false);
    }
  }, [activeRunId, questions, isAddingRandomMappings, handleQuestionUpdated]);

  const canValidateAll = questions.length > 0 && questionsWithMappings === questions.length;
  const readyForPdf = questions.length > 0 && questionsWithMappings === questions.length;

  const onFinalize = async () => {
    if (!activeRunId || !readyForPdf) return;
    await resumeFromStage(activeRunId, "pdf_creation");
  };

  const handleGenerateQuestion = useCallback(async (question: QuestionManipulation) => {
    if (!activeRunId || generatingQuestionId === question.id) return;
    setBulkError(null);
    setBulkMessage(null);
    setGeneratingQuestionId(question.id);
    try {
      const res = await autoGenerateMappings(activeRunId, question.id, { force: true });
      const serverMappings = res?.substring_mappings ?? [];
      handleQuestionUpdated({ ...question, substring_mappings: serverMappings });
      await refresh();
      if (activeRunId) {
        await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      }
      setBulkMessage(`Generated mappings for question ${question.question_number}.`);
      setTimeout(() => setBulkMessage(null), 4000);
    } catch (err) {
      console.error("autoGenerate", err);
      setBulkError(`Failed to generate mappings for question ${question.question_number}.`);
    } finally {
      setGeneratingQuestionId(null);
    }
  }, [activeRunId, generatingQuestionId, handleQuestionUpdated, refresh, refreshStatus]);

  const validateAll = useCallback(async () => {
    if (!activeRunId || isBulkValidating) return;
    setBulkError(null);
    setBulkMessage(null);
    setIsBulkValidating(true);
    const defaultModel = "openai:gpt-4o-mini";
    let success = 0;
    let skipped = 0;
    let failed = 0;
    for (const question of questions) {
      const mappings = question.substring_mappings || [];
      if (mappings.length === 0) {
        skipped += 1;
        continue;
      }
      try {
        const res = await validateQuestion(activeRunId, question.id, {
          substring_mappings: mappings,
          model: defaultModel,
        });
        const serverMappings = res?.substring_mappings ?? mappings;
        handleQuestionUpdated({ ...question, substring_mappings: serverMappings });
        success += 1;
      } catch (err) {
        console.error("validateAll", err);
        failed += 1;
      }
    }
    await refresh();
    if (activeRunId) {
      await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
    }
    setIsBulkValidating(false);
    if (failed > 0) {
      setBulkError(`Validation completed with ${failed} failure${failed === 1 ? "" : "s"}.`);
    }
    setBulkMessage(`Validated ${success} question${success === 1 ? "" : "s"}${skipped ? `, ${skipped} skipped` : ""}.`);
    setTimeout(() => setBulkMessage(null), 4000);
  }, [activeRunId, handleQuestionUpdated, isBulkValidating, questions, refresh, refreshStatus]);

  const handleQuestionSelect = useCallback((questionId: number) => {
    setSelectedQuestionId(prev => prev === questionId ? null : questionId);
  }, []);

  React.useEffect(() => {
    if (status?.current_stage === "pdf_creation") {
      // no-op here; PipelineContainer reacts to status
    }
  }, [status?.current_stage]);

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

        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <button
            className="pill-button"
            onClick={validateAll}
            disabled={!questions.length || isBulkValidating || !canValidateAll || generatingQuestionId !== null}
            title={!canValidateAll && !isBulkValidating ? 'Add mappings for every question before validating all.' : undefined}
          >
            {isBulkValidating ? 'Validating…' : 'Validate all'}
          </button>
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
        {questions.map((question) => {
          const mappings = question.substring_mappings || [];
          const computedStats = questionMappingStats[question.id] ?? {
            total: mappings.length,
            validated: mappings.filter((m) => m.validated === true).length,
          };
          const hasMappings = computedStats.total > 0;
          const isSelected = selectedQuestionId === question.id;
          const isGeneratingThis = generatingQuestionId === question.id;
          const spanInfo = spanPlanStatsByQuestion[String(question.question_number ?? question.id)];

          const allValidatedForQuestion = computedStats.total > 0 && computedStats.validated === computedStats.total;
          const validationBadgeStyle = allValidatedForQuestion
            ? { backgroundColor: 'rgba(52,211,153,0.18)', color: '#34d399' }
            : { backgroundColor: 'rgba(250,204,21,0.22)', color: '#fbbf24' };

          return (
            <div key={question.id} style={{
              border: `2px solid ${isGeneratingThis
                ? 'rgba(56,189,248,0.7)'
                : isSelected
                  ? 'rgba(56,189,248,0.65)'
                  : hasMappings
                    ? 'rgba(52,211,153,0.65)'
                    : 'rgba(148,163,184,0.22)'}`,
              borderRadius: '12px',
              backgroundColor: isSelected
                ? 'rgba(15,23,42,0.35)'
                : isGeneratingThis
                  ? 'rgba(15,23,42,0.55)'
                  : 'rgba(15,23,42,0.45)',
              boxShadow: isSelected
                ? '0 4px 12px rgba(0,123,255,0.15)'
                : isGeneratingThis
                  ? '0 8px 20px rgba(56,189,248,0.18)'
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
                      {hasMappings && (
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
                          ✅ {computedStats.validated}/{computedStats.total} validated
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
                      {computedStats.total} mapping{computedStats.total !== 1 ? 's' : ''} configured
                      {computedStats.total > 0 && (
                        <span style={{ marginLeft: '6px' }}>
                          · {computedStats.validated} validated
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
                      disabled={generatingQuestionId === question.id}
                      style={{
                        fontSize: '12px',
                        padding: '4px 10px',
                        backgroundColor: 'rgba(59,130,246,0.25)',
                        border: '1px solid rgba(59,130,246,0.35)',
                        color: '#bfdbfe'
                      }}
                      title="Generate mappings with GPT-5"
                    >
                      {generatingQuestionId === question.id ? 'Generating…' : 'Generate'}
                    </button>
                    {hasMappings && (
                      <button
                        className="pill-button"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleValidateQuestionMappings(question.id);
                        }}
                        disabled={validatingQuestionId === question.id || generatingQuestionId === question.id}
                        style={{
                          fontSize: '12px',
                          padding: '4px 10px',
                          backgroundColor: 'rgba(56,189,248,0.25)',
                          border: '1px solid rgba(56,189,248,0.35)',
                          color: '#e0f2fe'
                        }}
                        title="Validate all mappings for this question"
                      >
                        {validatingQuestionId === question.id ? 'Validating…' : 'Validate question'}
                      </button>
                    )}
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
                  <EnhancedQuestionViewer
                    runId={activeRunId!}
                    question={question}
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
          disabled={!readyForPdf || generatingQuestionId !== null || isBulkValidating}
          className="pill-button"
          style={{
            backgroundColor: readyForPdf ? '#34d399' : 'rgba(148,163,184,0.18)',
            color: readyForPdf ? '#0f172a' : 'var(--muted)'
          }}
          title={readyForPdf ? 'Advance to PDF creation' : 'Add mappings for each question to continue'}
        >
          ➡️ Proceed to PDF Creation
        </button>
      </div>
    </div>
  );
};

export default SmartSubstitutionPanel;
