import * as React from "react";
import { useState, useCallback, useEffect, useMemo } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { updateQuestionManipulation } from "@services/api/questionApi";
import { formatDuration } from "@services/utils/formatters";
import EnhancedQuestionViewer from "@components/question-level/EnhancedQuestionViewer";

const SmartSubstitutionPanel: React.FC = () => {
  const { activeRunId, resumeFromStage, status } = usePipeline();
  const { questions, isLoading, refresh, mutate } = useQuestions(activeRunId);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [isAddingRandomMappings, setIsAddingRandomMappings] = useState(false);
  const stage = status?.stages.find((item) => item.name === "smart_substitution");
  const totalMappings = useMemo(() => questions.reduce((acc, q) => acc + (q.substring_mappings?.length ?? 0), 0), [questions]);
  const validatedMappings = useMemo(() => questions.reduce((acc, q) => acc + ((q.substring_mappings || []).filter((m) => m.validated === true).length ?? 0), 0), [questions]);

  // Generate random mapping for testing purposes
  const generateRandomMapping = (questionText: string) => {
    if (!questionText) return null;

    // Common words to target for replacement (avoid articles, prepositions)
    const commonWords = ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'];
    const words = questionText.split(/\s+/);

    // Find a suitable word to replace (prefer longer words, avoid very short ones)
    const candidates = words.filter(word =>
      word.length > 2 &&
      !commonWords.includes(word.toLowerCase()) &&
      /^[a-zA-Z]+$/.test(word) // Only letters, no punctuation
    );

    if (candidates.length === 0) return null;

    // Pick a random candidate
    const targetWord = candidates[Math.floor(Math.random() * candidates.length)];
    const startPos = questionText.indexOf(targetWord);

    if (startPos === -1) return null;

    return {
      id: Math.random().toString(36).substr(2, 9),
      original: targetWord,
      replacement: "not",
      start_pos: startPos,
      end_pos: startPos + targetWord.length,
      context: "question_stem"
    };
  };

  const handleQuestionUpdated = useCallback((updated: any) => {
    // Optimistically merge into SWR cache so UI persists across collapse/expand
    mutate((current) => {
      if (!current) return current;
      const next = { ...current } as any;
      next.questions = (next.questions || []).map((q: any) => {
        if (q.id === updated.id) {
          // Deep merge to preserve validation states in substring_mappings
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

    // Also trigger a background revalidation to ensure backend sync
    setTimeout(() => mutate(), 100);
  }, [mutate]);

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

        const questionText = question.stem_text || question.original_text || "";
        const randomMapping = generateRandomMapping(questionText);

        if (randomMapping) {
          const mappings = [randomMapping];

          // Save to backend
          await updateQuestionManipulation(activeRunId, question.id, {
            method: question.manipulation_method || "smart_substitution",
            substring_mappings: mappings
          });

          // Update local cache
          handleQuestionUpdated({ ...question, substring_mappings: mappings });
        }
      }
    } catch (error) {
      console.error("Failed to add random mappings:", error);
    } finally {
      setIsAddingRandomMappings(false);
    }
  }, [activeRunId, questions, isAddingRandomMappings, handleQuestionUpdated]);

  const validatedCount = React.useMemo(() => {
    return questions.reduce((acc, q) => {
      const mappings = q.substring_mappings || [];
      // TEMP: For testing, just check if mappings exist, not if they're validated
      const hasMappings = mappings.length > 0;
      return acc + (hasMappings ? 1 : 0);
    }, 0);
  }, [questions]);

  // TEMP: For testing, allow proceeding if all questions have mappings (not necessarily validated)
  const allValidated = questions.length > 0 && validatedCount === questions.length;

  const onFinalize = async () => {
    if (!activeRunId || !allValidated) return;
    await resumeFromStage(activeRunId, "pdf_creation");
  };

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

        <div className="info-grid">
          <div className="info-card">
            <span className="info-label">Stage status</span>
            <span className="info-value">{stage?.status ?? 'pending'}</span>
          </div>
          <div className="info-card">
            <span className="info-label">Questions ready</span>
            <span className="info-value">{validatedCount}/{questions.length}</span>
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
        </div>
      </div>

      {/* Questions Grid */}
      <div style={{ display: 'grid', gap: '20px' }}>
        {questions.map((question) => {
          const mappings = question.substring_mappings || [];
          // TEMP: For testing, just check if mappings exist
          const hasMappings = mappings.length > 0;
          const isSelected = selectedQuestionId === question.id;

          return (
            <div key={question.id} style={{
              border: `2px solid ${isSelected ? 'rgba(56,189,248,0.65)' : hasMappings ? 'rgba(52,211,153,0.65)' : 'rgba(148,163,184,0.22)'}`,
              borderRadius: '12px',
              backgroundColor: isSelected ? 'rgba(15,23,42,0.35)' : 'rgba(15,23,42,0.45)',
              boxShadow: isSelected ? '0 4px 12px rgba(0,123,255,0.15)' : '0 2px 10px rgba(8,12,24,0.25)',
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
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
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
                          backgroundColor: 'rgba(52,211,153,0.18)',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          color: '#34d399'
                        }}>
                          ✓ HAS MAPPINGS
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
                      {mappings.length} mapping{mappings.length !== 1 ? 's' : ''} configured
                    </div>
                  </div>

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
          disabled={!allValidated}
          className="pill-button"
          style={{
            backgroundColor: allValidated ? '#34d399' : 'rgba(148,163,184,0.18)',
            color: allValidated ? '#0f172a' : 'var(--muted)'
          }}
          title={allValidated ? 'Advance to PDF creation' : 'Add mappings for each question to continue'}
        >
          ➡️ Proceed to PDF Creation
        </button>
      </div>
    </div>
  );
};

export default SmartSubstitutionPanel;
