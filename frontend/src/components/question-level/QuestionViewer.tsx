import * as React from "react";
import { useMemo, useState, useRef } from "react";

import type { QuestionManipulation, SubstringMapping } from "@services/types/questions";
import { updateQuestionManipulation, validateQuestion } from "@services/api/questionApi";

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
  const [lastValidation, setLastValidation] = useState<any>(null);
  const stemRef = useRef<HTMLDivElement | null>(null);

  const validateNoOverlap = (items: SubstringMapping[]) => {
    const sorted = [...items].sort((x, y) => x.start_pos - y.start_pos);
    for (let i = 1; i < sorted.length; i++) {
      if (rangesOverlap(sorted[i - 1], sorted[i])) return false;
    }
    return true;
  };

  const addMapping = (m: SubstringMapping) => {
    const next = [...mappings, m];
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
    await updateQuestionManipulation(runId, question.id, {
      method: question.manipulation_method || "smart_substitution",
      substring_mappings: mappings
    });
    onUpdated?.({ ...question, substring_mappings: mappings });
  };

  const onValidate = async () => {
    try {
      const res = await validateQuestion(runId, question.id, { substring_mappings: mappings, model: modelName });
      setLastValidation(res);
    } catch (e: any) {
      setValidError(e?.response?.data?.error || String(e));
    }
  };

  const renderPreview = useMemo(() => {
    const buf = question.original_text as unknown as string;
    const sorted = [...mappings].sort((a, b) => a.start_pos - b.start_pos);
    let offset = 0;
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    sorted.forEach((m, i) => {
      parts.push(<span key={`t-${i}-a`}>{buf.slice(cursor, m.start_pos + offset)}</span>);
      parts.push(<mark key={`t-${i}-b`} title={`${m.original} → ${m.replacement}`}>{m.replacement}</mark>);
      cursor = m.end_pos + offset;
      offset += m.replacement.length - (m.end_pos - m.start_pos);
    });
    parts.push(<span key="t-end">{buf.slice(cursor)}</span>);
    return parts;
  }, [mappings, question.original_text]);

  const onStemMouseUp = () => {
    const node = stemRef.current;
    if (!node) return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    const range = selection.getRangeAt(0);
    if (!node.contains(range.commonAncestorContainer)) return;

    const text = (question.original_text || "").toString();
    const selectedText = selection.toString();
    if (!selectedText) return;

    // Find first occurrence indices in the stem text
    const start = text.indexOf(selectedText);
    if (start < 0) return;
    const end = start + selectedText.length;

    const newMap: SubstringMapping = {
      original: selectedText,
      replacement: selectedText,
      start_pos: start,
      end_pos: end,
      context: "question_stem"
    };
    addMapping(newMap);
    selection.removeAllRanges();
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
      {question.gold_answer && <p>Gold (GPT‑5): {question.gold_answer}</p>}
      <p style={{ color: "#666" }}>{qTypeHint}</p>

      <div>
        <h4>Stem</h4>
        <div ref={stemRef} onMouseUp={onStemMouseUp} style={{ whiteSpace: "pre-wrap", cursor: "text", userSelect: "text", border: "1px dashed #ccc", padding: 8 }}>
          {question.original_text}
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
        <table>
          <thead>
            <tr>
              <th>start</th>
              <th>end</th>
              <th>original</th>
              <th>replacement</th>
              <th></th>
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
                <td><button onClick={() => removeMapping(i)}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={saveMappings}>Save</button>
          <button onClick={onValidate} disabled={(mappings?.length ?? 0) === 0}>Validate</button>
        </div>
      </div>

      <div>
        <h4>Preview (applied)</h4>
        <div style={{ whiteSpace: "pre-wrap" }}>{renderPreview}</div>
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
