import * as React from "react";
import { useMemo, useState, useRef } from "react";

import type { QuestionManipulation, SubstringMapping } from "@services/types/questions";
import { updateQuestionManipulation, validateQuestion, autoGenerateMappings } from "@services/api/questionApi";

interface QuestionViewerProps {
  runId: string;
  question: QuestionManipulation;
  onUpdated?: (q: QuestionManipulation) => void;
}

const rangesOverlap = (a: { start_pos: number; end_pos: number }, b: { start_pos: number; end_pos: number }) =>
  Math.max(a.start_pos, b.start_pos) < Math.min(a.end_pos, b.end_pos);

const QuestionViewer: React.FC<QuestionViewerProps> = ({ runId, question, onUpdated }) => {
  const [mappings, setMappings] = useState<SubstringMapping[]>(question.substring_mappings || []);
  const [modelName, setModelName] = useState("openai:gpt-4o-mini");
  const [validError, setValidError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [lastValidation, setLastValidation] = useState<any>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const stemRef = useRef<HTMLDivElement | null>(null);

  const validateNoOverlap = (items: SubstringMapping[]) => {
    const sorted = [...items].sort((x, y) => x.start_pos - y.start_pos);
    for (let i = 1; i < sorted.length; i++) {
      if (rangesOverlap(sorted[i - 1], sorted[i])) return false;
    }
    return true;
  };

  const addMapping = (m: SubstringMapping) => {
    const next = [...mappings, { ...m, id: Math.random().toString(36).substr(2, 9) }];
    if (!validateNoOverlap(next)) {
      setValidError("Mappings cannot overlap");
      return;
    }
    setValidError(null);
    setMappings(next);
  };

  const removeMapping = (idx: number) => {
    const next = mappings.filter((_, i) => i !== idx);
    setMappings(next);
  };

  const saveMappings = async () => {
    const response = await updateQuestionManipulation(runId, question.id, {
      method: question.manipulation_method || "smart_substitution",
      substring_mappings: mappings
    });
    const serverMappings = response?.substring_mappings ?? mappings;
    setMappings(serverMappings);
    onUpdated?.({ ...question, substring_mappings: serverMappings });
  };

  const onValidate = async () => {
    try {
      const res = await validateQuestion(runId, question.id, { substring_mappings: mappings, model: modelName });
      const serverMappings = res?.substring_mappings ?? mappings;
      setMappings(serverMappings);
      setLastValidation(res);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
    } catch (e: any) {
      setValidError(e?.response?.data?.error || String(e));
    }
  };

  const onAutoGenerate = async () => {
    setGenerateError(null);
    setValidError(null);
    setIsGenerating(true);
    try {
      const res = await autoGenerateMappings(runId, question.id, { model: modelName });
      const serverMappings = res?.substring_mappings ?? [];
      setMappings(serverMappings);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
      setSuccessMessage("Generated mappings via GPT-5");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (e: any) {
      setGenerateError(e?.response?.data?.error || String(e));
    } finally {
      setIsGenerating(false);
    }
  };

  const validateMapping = async (mappingIndex: number) => {
    try {
      const res = await validateQuestion(runId, question.id, {
        substring_mappings: mappings,
        model: modelName,
      });

      const serverMappings = res?.substring_mappings ?? mappings;
      setMappings(serverMappings);
      onUpdated?.({ ...question, substring_mappings: serverMappings });
    } catch (e: any) {
      setValidError(e?.response?.data?.error || String(e));
    }
  };

  // Get the full question text, preferring stem_text over original_text
  const fullQuestionText = question.stem_text || question.original_text || "";

  const renderPreview = useMemo(() => {
    const buf = fullQuestionText;
    const sorted = [...mappings].sort((a, b) => a.start_pos - b.start_pos);
    let offset = 0;
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    sorted.forEach((m, i) => {
      parts.push(<span key={`t-${i}-a`}>{buf.slice(cursor, m.start_pos + offset)}</span>);

      // Determine validation status styling
      let markStyle: React.CSSProperties = {};
      let badge = '';
      let title = `${m.original} → ${m.replacement}`;

      if (m.validated === true) {
        markStyle = { backgroundColor: '#d4edda', borderLeft: '3px solid #28a745' };
        badge = ' ✓';
        title += ` (Validated: ${m.validation?.response || 'N/A'})`;
      } else if (m.validated === false) {
        markStyle = { backgroundColor: '#fff3cd', borderLeft: '3px solid #ffc107' };
        badge = ' ⚠';
        title += ` (Invalid: ${m.validation?.response || 'N/A'})`;
      } else {
        markStyle = { backgroundColor: '#f8f9fa', borderLeft: '3px solid #6c757d' };
        badge = ' ⏳';
        title += ' (Pending validation)';
      }

      parts.push(
        <mark
          key={`t-${i}-b`}
          style={markStyle}
          title={title}
        >
          {m.replacement}{badge}
        </mark>
      );
      cursor = m.end_pos + offset;
      offset += m.replacement.length - (m.end_pos - m.start_pos);
    });
    parts.push(<span key="t-end">{buf.slice(cursor)}</span>);
    return parts;
  }, [mappings, fullQuestionText]);

  const onStemMouseUp = () => {
    const node = stemRef.current;
    if (!node) return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    const range = selection.getRangeAt(0);
    if (!node.contains(range.commonAncestorContainer)) return;

    const text = fullQuestionText;
    const selectedText = selection.toString().trim();
    if (!selectedText) return;

    // Find first occurrence indices in the stem text
    const start = text.indexOf(selectedText);
    if (start < 0) {
      setValidError("Selected text not found in question stem");
      return;
    }
    const end = start + selectedText.length;

    // Check for overlap with existing mappings
    const hasOverlap = mappings.some(m =>
      !(end <= m.start_pos || start >= m.end_pos)
    );

    if (hasOverlap) {
      setValidError("Selection overlaps with existing mapping");
      selection.removeAllRanges();
      return;
    }

    const newMap: SubstringMapping = {
      original: selectedText,
      replacement: selectedText,
      start_pos: start,
      end_pos: end,
      context: "question_stem"
    };
    addMapping(newMap);
    selection.removeAllRanges();
    setValidError(null);
    setSuccessMessage(`Added mapping: "${selectedText}"`);

    // Clear success message after 3 seconds
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  const qTypeHint = useMemo(() => {
    switch (question.question_type) {
      case "mcq_single":
        return "Click-drag on stem to add mappings. Keep option letters intact unless intended.";
      case "true_false":
        return "Target subtle negations or qualifiers in the stem.";
      default:
        return "Select substrings in the stem to create replacements.";
    }
  }, [question.question_type]);

  return (
    <div className="question-viewer">
      <h3>Question {question.question_number}</h3>
      <p>Type: {question.question_type}</p>
      {question.gold_answer && (
        <p>
          <strong>Gold Answer:</strong> {question.gold_answer}
          {question.gold_confidence && <span style={{ color: "#666" }}> (confidence: {Math.round(question.gold_confidence * 100)}%)</span>}
        </p>
      )}
      <p style={{ color: "#666" }}>{qTypeHint}</p>

      <div>
        <h4>Stem</h4>
        <div style={{ marginBottom: 8 }}>
          <em style={{ color: "#666", fontSize: "0.9em" }}>
            Click and drag to select text for mapping
          </em>
          {successMessage && (
            <div style={{ color: "green", fontSize: "0.9em", marginTop: 4 }}>
              ✓ {successMessage}
            </div>
          )}
        </div>
        <div
          ref={stemRef}
          onMouseUp={onStemMouseUp}
          style={{
            whiteSpace: "pre-wrap",
            cursor: "text",
            userSelect: "text",
            border: "2px dashed #007bff",
            borderRadius: "4px",
            padding: 12,
            minHeight: "3em",
            backgroundColor: "#f8f9fa",
            lineHeight: "1.5",
            transition: "border-color 0.2s ease"
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "#0056b3";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "#007bff";
          }}
        >
          {fullQuestionText || "No question text available"}
        </div>
      </div>

      {question.options_data && (
        <div>
          <h4>Options</h4>
          <ul>
            {Object.entries(question.options_data as Record<string, unknown>).map(([k, v]) => (
              <li key={k}><strong>{k}.</strong> {String(v)}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h4>Substring mappings</h4>
        <button onClick={() => addMapping({ original: "", replacement: "", start_pos: 0, end_pos: 0, context: "question_stem" })}>Add</button>
        {validError && <p style={{ color: "red" }}>{validError}</p>}
        {generateError && <p style={{ color: "red" }}>{generateError}</p>}
        <table>
          <thead>
            <tr>
              <th>start</th>
              <th>end</th>
              <th>original</th>
              <th>replacement</th>
              <th>status</th>
              <th>actions</th>
            </tr>
          </thead>
          <tbody>
            {mappings.map((m, i) => (
              <tr key={i}>
                <td><input type="number" value={m.start_pos} onChange={(e) => {
                  const next = [...mappings];
                  next[i] = { ...next[i], start_pos: Number(e.target.value) } as SubstringMapping;
                  setMappings(next);
                }} /></td>
                <td><input type="number" value={m.end_pos} onChange={(e) => {
                  const next = [...mappings];
                  next[i] = { ...next[i], end_pos: Number(e.target.value) } as SubstringMapping;
                  setMappings(next);
                }} /></td>
                <td><input type="text" value={m.original} onChange={(e) => {
                  const next = [...mappings];
                  next[i] = { ...next[i], original: e.target.value } as SubstringMapping;
                  setMappings(next);
                }} /></td>
                <td><input type="text" value={m.replacement} onChange={(e) => {
                  const next = [...mappings];
                  next[i] = { ...next[i], replacement: e.target.value } as SubstringMapping;
                  setMappings(next);
                }} /></td>
                <td>
                  {m.validated === true ? (
                    <span style={{ color: "green", fontWeight: "bold" }} title={`Model response: ${m.validation?.response || 'N/A'}`}>
                      ✓ Validated
                    </span>
                  ) : m.validated === false ? (
                    <span style={{ color: "orange", fontWeight: "bold" }} title={`Model response: ${m.validation?.response || 'N/A'}`}>
                      ⚠ Invalid
                    </span>
                  ) : (
                    <span style={{ color: "gray" }}>Pending</span>
                  )}
                </td>
                <td style={{ display: "flex", gap: 4 }}>
                  <button onClick={() => validateMapping(i)} disabled={!m.original || !m.replacement} title="Validate this mapping">
                    Test
                  </button>
                  <button onClick={() => removeMapping(i)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onAutoGenerate} disabled={isGenerating} title="Use GPT-5 to generate mappings">
            {isGenerating ? "Generating..." : "Auto-generate"}
          </button>
          <button onClick={saveMappings}>Save</button>
          <button onClick={onValidate} disabled={(mappings?.length ?? 0) === 0}>Validate</button>
        </div>
      </div>

      <div>
        <h4>Preview (applied)</h4>
        <div style={{ marginBottom: 8, fontSize: "0.85em", color: "#666" }}>
          <span style={{ marginRight: 16 }}>
            <span style={{ color: "#28a745" }}>✓ Validated</span>
          </span>
          <span style={{ marginRight: 16 }}>
            <span style={{ color: "#ffc107" }}>⚠ Invalid</span>
          </span>
          <span>
            <span style={{ color: "#6c757d" }}>⏳ Pending</span>
          </span>
        </div>
        <div
          style={{
            whiteSpace: "pre-wrap",
            border: "1px solid #dee2e6",
            borderRadius: "4px",
            padding: 12,
            backgroundColor: "#ffffff",
            lineHeight: "1.6",
            minHeight: "2em"
          }}
        >
          {renderPreview}
        </div>
      </div>

      {lastValidation && (
        <div>
          <h4>Validation result</h4>
          <p>Gold: {lastValidation.gold_answer ?? "(none)"}</p>
          <p>Model: {lastValidation.model_response?.response ?? "(no response)"}</p>
        </div>
      )}
    </div>
  );
};

export default QuestionViewer;
