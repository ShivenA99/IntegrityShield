import * as React from "react";
import { useState, useRef, useCallback, useMemo, useEffect } from "react";

import type { QuestionManipulation, SubstringMapping } from "@services/types/questions";
import { updateQuestionManipulation, validateQuestion } from "@services/api/questionApi";

interface EnhancedQuestionViewerProps {
  runId: string;
  question: QuestionManipulation;
  onUpdated?: (q: QuestionManipulation) => void;
}

const EnhancedQuestionViewer: React.FC<EnhancedQuestionViewerProps> = ({
  runId,
  question,
  onUpdated
}) => {
  const [mappings, setMappings] = useState<SubstringMapping[]>(question.substring_mappings || []);

  // Sync local state with prop changes to fix state persistence
  useEffect(() => {
    if (question.substring_mappings) {
      setMappings(question.substring_mappings);
    }
  }, [question.substring_mappings]);
  const [activeMappingIndex, setActiveMappingIndex] = useState<number | null>(null);
  const [selectedText, setSelectedText] = useState<string>("");
  const [replacementText, setReplacementText] = useState<string>("");
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [showMappingForm, setShowMappingForm] = useState<boolean>(false);
  const [pendingSelection, setPendingSelection] = useState<{start: number, end: number, text: string} | null>(null);

  const stemRef = useRef<HTMLDivElement | null>(null);
  const fullQuestionText = question.stem_text || question.original_text || "";
  const defaultReplacementSuffix = " [altered]";

  const rangesOverlap = (a: { start_pos: number; end_pos: number }, b: { start_pos: number; end_pos: number }) =>
    Math.max(a.start_pos, b.start_pos) < Math.min(a.end_pos, b.end_pos);

  const validateNoOverlap = (items: SubstringMapping[]) => {
    const sorted = [...items].sort((x, y) => x.start_pos - y.start_pos);
    for (let i = 1; i < sorted.length; i++) {
      if (rangesOverlap(sorted[i - 1], sorted[i])) return false;
    }
    return true;
  };

  const handleTextSelection = useCallback(() => {
    const node = stemRef.current;
    if (!node) return;

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    if (!node.contains(range.commonAncestorContainer)) return;

    const selectedText = selection.toString().trim();
    if (!selectedText) return;

    // Find first occurrence indices in the stem text
    const start = fullQuestionText.indexOf(selectedText);
    if (start < 0) {
      setValidationError("Selected text not found in question stem");
      return;
    }
    const end = start + selectedText.length;

    // Check for overlap with existing mappings
    const hasOverlap = mappings.some(m =>
      !(end <= m.start_pos || start >= m.end_pos)
    );

    if (hasOverlap) {
      setValidationError("Selection overlaps with existing mapping");
      selection.removeAllRanges();
      return;
    }

    setPendingSelection({ start, end, text: selectedText });
    setSelectedText(selectedText);
    setReplacementText(selectedText);
    setShowMappingForm(true);
    setValidationError(null);
    selection.removeAllRanges();
  }, [fullQuestionText, mappings]);

  const addMapping = useCallback(async () => {
    if (!pendingSelection || !replacementText.trim()) return;

    const newMapping: SubstringMapping = {
      id: Math.random().toString(36).substr(2, 9),
      original: pendingSelection.text,
      replacement: replacementText.trim(),
      start_pos: pendingSelection.start,
      end_pos: pendingSelection.end,
      context: "question_stem"
    };

    const updatedMappings = [...mappings, newMapping];
    if (!validateNoOverlap(updatedMappings)) {
      setValidationError("Mappings cannot overlap");
      return;
    }

    try {
      const response = await updateQuestionManipulation(runId, question.id, {
        method: question.manipulation_method || "smart_substitution",
        substring_mappings: updatedMappings
      });
      const serverMappings = response?.substring_mappings ?? updatedMappings;
      setMappings(serverMappings);
      setActiveMappingIndex(serverMappings.length - 1);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
    } catch (error) {
      setValidationError("Failed to save mapping");
      console.error("Save error:", error);
      return;
    }

    // Reset form
    setShowMappingForm(false);
    setPendingSelection(null);
    setSelectedText("");
    setReplacementText("");
    setValidationError(null);
  }, [pendingSelection, replacementText, mappings, runId, question, onUpdated]);

  const removeMapping = useCallback(async (index: number) => {
    const updatedMappings = mappings.filter((_, i) => i !== index);

    try {
      const response = await updateQuestionManipulation(runId, question.id, {
        method: question.manipulation_method || "smart_substitution",
        substring_mappings: updatedMappings
      });
      const serverMappings = response?.substring_mappings ?? updatedMappings;
      setMappings(serverMappings);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
    } catch (error) {
      setValidationError("Failed to remove mapping");
      console.error("Remove error:", error);
      return;
    }

    if (activeMappingIndex === index) {
      setActiveMappingIndex(null);
    }
  }, [mappings, runId, question, onUpdated, activeMappingIndex]);

  const autoMapFullStem = useCallback(async () => {
    if (!fullQuestionText.trim()) {
      setValidationError("Question stem is empty");
      return;
    }

    const newMapping: SubstringMapping = {
      id: Math.random().toString(36).substr(2, 9),
      original: fullQuestionText,
      replacement: `${fullQuestionText}${defaultReplacementSuffix}`,
      start_pos: 0,
      end_pos: fullQuestionText.length,
      context: "question_stem",
    };

    try {
      const response = await updateQuestionManipulation(runId, question.id, {
        method: question.manipulation_method || "smart_substitution",
        substring_mappings: [newMapping],
      });
      const serverMappings = response?.substring_mappings ?? [newMapping];
      setMappings(serverMappings);
      setActiveMappingIndex(serverMappings.length ? 0 : null);
      setShowMappingForm(false);
      setPendingSelection(null);
      setSelectedText("");
      setReplacementText("");
      setValidationError(null);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
    } catch (error) {
      console.error("Auto-map error", error);
      setValidationError("Failed to auto-map question stem");
    }
  }, [
    fullQuestionText,
    defaultReplacementSuffix,
    question,
    runId,
    onUpdated,
  ]);

  const validateMapping = useCallback(async (mappingIndex: number) => {
    const mapping = mappings[mappingIndex];
    if (!mapping.id) return;

    setIsValidating(true);
    setValidationError(null);

    try {
      const res = await validateQuestion(runId, question.id, {
        substring_mappings: [mapping],
        model: "openai:gpt-4o-mini",
        mapping_id: mapping.id
      });

      // Update the mapping with enhanced GPT-5 validation results
      const gpt5Validation = res.gpt5_validation || {};
      const updatedMappings = [...mappings];
      updatedMappings[mappingIndex] = {
        ...updatedMappings[mappingIndex],
        validated: gpt5Validation.is_valid || false,
        confidence: gpt5Validation.confidence || 0,
        deviation_score: gpt5Validation.deviation_score || 0,
        validation: {
          model: "openai:gpt-4o-mini",
          response: res.model_response?.response || '',
          gold: question.gold_answer || '',
          prompt_len: res.modified_question?.length || 0,
          gpt5_validation: gpt5Validation
        }
      };

      setMappings(updatedMappings);

      // Save the updated mappings
      const response = await updateQuestionManipulation(runId, question.id, {
        method: question.manipulation_method || "smart_substitution",
        substring_mappings: updatedMappings
      });
      const serverMappings = response?.substring_mappings ?? updatedMappings;
      setMappings(serverMappings);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
    } catch (error: any) {
      setValidationError(error?.response?.data?.error || String(error));
    } finally {
      setIsValidating(false);
    }
  }, [mappings, runId, question, onUpdated]);

  const renderQuestionWithHighlights = useMemo(() => {
    if (!fullQuestionText) return "No question text available";

    const sorted = [...mappings].sort((a, b) => a.start_pos - b.start_pos);
    const parts: React.ReactNode[] = [];
    let cursor = 0;

    sorted.forEach((mapping, index) => {
      // Add text before this mapping
      if (cursor < mapping.start_pos) {
        parts.push(
          <span key={`text-${index}`}>
            {fullQuestionText.slice(cursor, mapping.start_pos)}
          </span>
        );
      }

      // Add highlighted mapping
      const isActive = activeMappingIndex === mappings.indexOf(mapping);
      let bgColor = '#f8f9fa';
      let borderColor = '#dee2e6';
      let textColor = '#495057';

      if (mapping.validated === true) {
        bgColor = '#d4edda';
        borderColor = '#28a745';
        textColor = '#155724';
      } else if (mapping.validated === false) {
        bgColor = '#fff3cd';
        borderColor = '#ffc107';
        textColor = '#856404';
      }

      if (isActive) {
        bgColor = '#e3f2fd';
        borderColor = '#2196f3';
      }

      parts.push(
        <mark
          key={`mapping-${index}`}
          onClick={() => setActiveMappingIndex(mappings.indexOf(mapping))}
          style={{
            backgroundColor: bgColor,
            border: `2px solid ${borderColor}`,
            borderRadius: '4px',
            padding: '2px 4px',
            margin: '0 1px',
            cursor: 'pointer',
            color: textColor,
            fontWeight: 'bold',
            transition: 'all 0.2s ease'
          }}
          title={`${mapping.original} → ${mapping.replacement}`}
        >
          {mapping.replacement}
          {mapping.validated === true && ' ✓'}
          {mapping.validated === false && ' ⚠'}
          {mapping.validated === undefined && ' ⏳'}
        </mark>
      );

      cursor = mapping.end_pos;
    });

    // Add remaining text
    if (cursor < fullQuestionText.length) {
      parts.push(
        <span key="text-end">
          {fullQuestionText.slice(cursor)}
        </span>
      );
    }

    return parts;
  }, [fullQuestionText, mappings, activeMappingIndex]);

  return (
    <div style={{ padding: '0' }}>
      {/* Question Content Section */}
      <div style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e9ecef',
        borderRadius: '8px',
        marginBottom: '20px'
      }}>
        <div style={{
          padding: '16px',
          borderBottom: '1px solid #e9ecef',
          backgroundColor: '#f8f9fa'
        }}>
          <h4 style={{ margin: 0, color: '#495057', fontSize: '16px', fontWeight: 'bold' }}>
            📝 Question Content
          </h4>
        </div>

        <div style={{ padding: '20px' }}>
          <div style={{ marginBottom: '16px' }}>
            <div style={{
              fontSize: '14px',
              color: '#333333',
              marginBottom: '8px',
              fontWeight: 'bold'
            }}>
              Click and drag to select text for mapping, or
              <button
                onClick={autoMapFullStem}
                style={{
                  marginLeft: '8px',
                  padding: '4px 10px',
                  border: 'none',
                  borderRadius: '4px',
                  backgroundColor: '#17a2b8',
                  color: '#fff',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                ⚡ Auto-map full stem
              </button>
            </div>
            <div
              ref={stemRef}
              onMouseUp={handleTextSelection}
              style={{
                border: '3px dashed #007bff',
                borderRadius: '8px',
                padding: '20px',
                backgroundColor: '#ffffff',
                lineHeight: '1.6',
                fontSize: '16px',
                cursor: 'text',
                userSelect: 'text',
                minHeight: '100px',
                transition: 'border-color 0.2s ease',
                color: '#000000',
                fontWeight: '500'
              }}
            >
              {renderQuestionWithHighlights}
            </div>
          </div>

          {/* Question Options */}
          {question.options_data && (
            <div style={{
              padding: '16px',
              backgroundColor: '#ffffff',
              border: '2px solid #e9ecef',
              borderRadius: '6px',
              marginBottom: '16px'
            }}>
              <div style={{ fontWeight: 'bold', marginBottom: '12px', color: '#000000', fontSize: '16px' }}>Options:</div>
              <div style={{ display: 'grid', gap: '8px' }}>
                {Object.entries(question.options_data as Record<string, unknown>).map(([key, value]) => (
                  <div key={key} style={{ fontSize: '15px', color: '#000000', fontWeight: '500' }}>
                    <strong style={{ color: '#007bff', fontSize: '16px', marginRight: '8px' }}>{key}.</strong> {String(value)}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Mapping Form */}
      {showMappingForm && pendingSelection && (
        <div style={{
          backgroundColor: '#e3f2fd',
          border: '2px solid #2196f3',
          borderRadius: '8px',
          padding: '20px',
          marginBottom: '20px'
        }}>
          <h4 style={{ margin: '0 0 16px 0', color: '#1976d2' }}>
            ➕ Add New Mapping
          </h4>
          <div style={{ marginBottom: '12px' }}>
            <strong>Selected text:</strong> "{pendingSelection.text}"
          </div>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
              Replace with:
            </label>
            <input
              type="text"
              value={replacementText}
              onChange={(e) => setReplacementText(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #ddd',
                borderRadius: '4px',
                fontSize: '14px'
              }}
              placeholder="Enter replacement text..."
              autoFocus
            />
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={addMapping}
              disabled={!replacementText.trim()}
              style={{
                padding: '8px 16px',
                backgroundColor: '#28a745',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              ✓ Add Mapping
            </button>
            <button
              onClick={() => {
                setShowMappingForm(false);
                setPendingSelection(null);
                setSelectedText("");
                setReplacementText("");
              }}
              style={{
                padding: '8px 16px',
                backgroundColor: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Error Display */}
      {validationError && (
        <div style={{
          backgroundColor: '#f8d7da',
          border: '1px solid #f5c6cb',
          color: '#721c24',
          padding: '12px',
          borderRadius: '4px',
          marginBottom: '16px'
        }}>
          <strong>Error:</strong> {validationError}
        </div>
      )}

      {/* Mappings List */}
      {mappings.length > 0 && (
        <div style={{
          backgroundColor: '#ffffff',
          border: '1px solid #e9ecef',
          borderRadius: '8px'
        }}>
          <div style={{
            padding: '16px',
            borderBottom: '1px solid #e9ecef',
            backgroundColor: '#f8f9fa'
          }}>
            <h4 style={{ margin: 0, color: '#495057', fontSize: '16px', fontWeight: 'bold' }}>
              🔄 Active Mappings ({mappings.length})
            </h4>
          </div>

          <div style={{ padding: '16px' }}>
            {mappings.map((mapping, index) => {
              const isActive = activeMappingIndex === index;
              return (
                <div
                  key={index}
                  onClick={() => setActiveMappingIndex(isActive ? null : index)}
                  style={{
                    border: `2px solid ${isActive ? '#007bff' : mapping.validated === true ? '#28a745' : mapping.validated === false ? '#ffc107' : '#dee2e6'}`,
                    borderRadius: '8px',
                    padding: '16px',
                    marginBottom: '12px',
                    backgroundColor: isActive ? '#f8f9ff' : '#ffffff',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ marginBottom: '8px' }}>
                        <span style={{ fontWeight: 'bold', color: '#dc3545' }}>"{mapping.original}"</span>
                        <span style={{ margin: '0 8px', color: '#6c757d' }}>→</span>
                        <span style={{ fontWeight: 'bold', color: '#28a745' }}>"{mapping.replacement}"</span>
                      </div>

                      <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '8px' }}>
                        Position: {mapping.start_pos} - {mapping.end_pos}
                      </div>

                      {/* Enhanced Validation Status */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          {mapping.validated === true && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ color: '#28a745', fontWeight: 'bold', fontSize: '14px' }}>
                                ✓ Manipulation Successful
                              </span>
                              {mapping.confidence !== undefined && (
                                <span style={{
                                  padding: '2px 6px',
                                  backgroundColor: '#d4edda',
                                  border: '1px solid #c3e6cb',
                                  borderRadius: '3px',
                                  fontSize: '11px',
                                  fontWeight: 'bold',
                                  color: '#155724'
                                }}>
                                  {Math.round(mapping.confidence * 100)}% confidence
                                </span>
                              )}
                            </div>
                          )}
                          {mapping.validated === false && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ color: '#ffc107', fontWeight: 'bold', fontSize: '14px' }}>
                                ⚠ Insufficient Deviation
                              </span>
                              {mapping.confidence !== undefined && (
                                <span style={{
                                  padding: '2px 6px',
                                  backgroundColor: '#fff3cd',
                                  border: '1px solid #ffeaa7',
                                  borderRadius: '3px',
                                  fontSize: '11px',
                                  fontWeight: 'bold',
                                  color: '#856404'
                                }}>
                                  {Math.round(mapping.confidence * 100)}% confidence
                                </span>
                              )}
                            </div>
                          )}
                          {mapping.validated === undefined && (
                            <span style={{ color: '#6c757d', fontSize: '14px' }}>
                              ⏳ Pending GPT-5 Validation
                            </span>
                          )}
                        </div>

                        {/* Detailed Validation Metrics */}
                        {mapping.validation?.gpt5_validation && (
                          <div style={{
                            fontSize: '11px',
                            color: '#6c757d',
                            backgroundColor: '#f8f9fa',
                            padding: '8px',
                            borderRadius: '4px',
                            border: '1px solid #e9ecef'
                          }}>
                            <div style={{ marginBottom: '4px' }}>
                              <strong>GPT-5 Analysis:</strong>
                            </div>
                            {mapping.deviation_score !== undefined && (
                              <div>
                                Deviation: {Math.round(mapping.deviation_score * 100)}% |
                                Semantic Similarity: {Math.round((mapping.validation.gpt5_validation.semantic_similarity || 0) * 100)}%
                              </div>
                            )}
                            {mapping.validation.gpt5_validation.threshold && (
                              <div>
                                Threshold: {Math.round(mapping.validation.gpt5_validation.threshold * 100)}% |
                                Question Type: {question.question_type}
                              </div>
                            )}
                            {mapping.validation.response && (
                              <div style={{ marginTop: '4px' }}>
                                <strong>Model Response:</strong> "{mapping.validation.response}"
                              </div>
                            )}
                            {mapping.validation.gpt5_validation.reasoning && (
                              <div style={{ marginTop: '4px', fontStyle: 'italic' }}>
                                <strong>AI Reasoning:</strong> {mapping.validation.gpt5_validation.reasoning.substring(0, 150)}
                                {mapping.validation.gpt5_validation.reasoning.length > 150 && '...'}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Fallback for legacy validation */}
                        {mapping.validation?.response && !mapping.validation?.gpt5_validation && (
                          <span style={{ fontSize: '12px', color: '#6c757d' }}>
                            Model Response: "{mapping.validation.response}"
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', marginLeft: '16px' }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          validateMapping(index);
                        }}
                        disabled={isValidating}
                        style={{
                          padding: '6px 12px',
                          backgroundColor: '#17a2b8',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '12px',
                          fontWeight: 'bold'
                        }}
                      >
                        {isValidating ? '⏳' : '🧪'} Test
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeMapping(index);
                        }}
                        style={{
                          padding: '6px 12px',
                          backgroundColor: '#dc3545',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '12px',
                          fontWeight: 'bold'
                        }}
                      >
                        🗑️ Remove
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {mappings.length === 0 && (
        <div style={{
          textAlign: 'center',
          padding: '40px',
          color: '#6c757d',
          backgroundColor: '#f8f9fa',
          borderRadius: '8px'
        }}>
          <div style={{ fontSize: '24px', marginBottom: '8px' }}>📝</div>
          <div style={{ fontSize: '16px' }}>No mappings yet</div>
          <div style={{ fontSize: '14px' }}>Select text in the question above to create your first mapping</div>
        </div>
      )}
    </div>
  );
};

export default EnhancedQuestionViewer;
