import * as React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";
import type { ClassroomDataset, ClassroomEvaluationResponse, ClassroomStudentMetric } from "@services/types/pipeline";

const formatPercent = (value: number | null | undefined, fallback = "—") => {
  if (value == null || Number.isNaN(value)) {
    return fallback;
  }
  return `${Math.round(value * 100)}%`;
};

const formatScore = (value: number | null | undefined) => {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value)}%`;
};

const ClassroomEvaluationPanel: React.FC = () => {
  const {
    status,
    activeRunId,
    selectedClassroomId,
    setSelectedClassroomId,
    evaluateClassroom,
    fetchClassroomEvaluation,
    setPreferredStage,
  } = usePipeline();

  const classrooms = useMemo<ClassroomDataset[]>(() => status?.classrooms ?? [], [status?.classrooms]);
  const [evaluation, setEvaluation] = useState<ClassroomEvaluationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  const selectedClassroom = useMemo(() => {
    if (!selectedClassroomId) return null;
    return classrooms.find((classroom) => classroom.id === selectedClassroomId) ?? null;
  }, [classrooms, selectedClassroomId]);

  useEffect(() => {
    if (!classrooms.length) {
      setSelectedClassroomId(null);
      setEvaluation(null);
      return;
    }
    if (!selectedClassroomId) {
      setSelectedClassroomId(classrooms[0].id);
    }
  }, [classrooms, selectedClassroomId, setSelectedClassroomId]);

  const loadEvaluation = useCallback(
    async (classroom: ClassroomDataset) => {
      if (!activeRunId) return;
      if (!classroom.evaluation) {
        setEvaluation(null);
        return;
      }
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const result = await fetchClassroomEvaluation(activeRunId, classroom.id);
        setEvaluation(result);
      } catch (err: any) {
        setErrorMessage(err?.message || "Failed to load classroom evaluation.");
        setEvaluation(null);
      } finally {
        setIsLoading(false);
      }
    },
    [activeRunId, fetchClassroomEvaluation]
  );

  useEffect(() => {
    if (!selectedClassroom) {
      setEvaluation(null);
      return;
    }
    void loadEvaluation(selectedClassroom);
  }, [selectedClassroom?.id, selectedClassroom?.evaluation?.updated_at, loadEvaluation, selectedClassroom]);

  const handleEvaluate = useCallback(async () => {
    if (!activeRunId || !selectedClassroom) return;
    setIsEvaluating(true);
    setErrorMessage(null);
    try {
      const result = await evaluateClassroom(activeRunId, selectedClassroom.id);
      setEvaluation(result);
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to run evaluation.");
    } finally {
      setIsEvaluating(false);
    }
  }, [activeRunId, selectedClassroom, evaluateClassroom]);

  if (!classrooms.length) {
    return (
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>📊 Classroom Evaluation</h2>
        <p style={{ color: "var(--muted)" }}>
          Generate a classroom dataset first, then launch the evaluation to see cheating insights for each student.
        </p>
        <button type="button" className="primary-button" onClick={() => setPreferredStage("classroom_dataset")}>
          Go to classroom datasets
        </button>
      </div>
    );
  }

  if (!selectedClassroom) {
    return (
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>📊 Classroom Evaluation</h2>
        <p style={{ color: "var(--muted)" }}>Select a classroom dataset to view evaluation results.</p>
      </div>
    );
  }

  const summary = (evaluation?.summary ?? {}) as Record<string, any>;
  const students: ClassroomStudentMetric[] = evaluation?.students ?? [];
  const methodLabel = selectedClassroom.attacked_pdf_method
    ? ENHANCEMENT_METHOD_LABELS[selectedClassroom.attacked_pdf_method] ??
      selectedClassroom.attacked_pdf_method.replace(/_/g, " ")
    : "Unknown variant";

  const strategyBreakdown = summary.strategy_breakdown as Record<string, number> | undefined;
  const scoreDistribution = summary.score_distribution as Array<Record<string, unknown>> | undefined;

  return (
    <div className="panel classroom-evaluation" style={{ display: "grid", gap: "1.5rem" }}>
      <header className="classroom-eval__header">
        <div>
          <h2>
            📊 Evaluation — {selectedClassroom.classroom_label ?? selectedClassroom.classroom_key ?? `Classroom ${selectedClassroom.id}`}
          </h2>
          <p>
            Variant: <strong>{methodLabel}</strong> · Students: {selectedClassroom.total_students ?? "—"}
          </p>
        </div>
        <div className="classroom-eval__header-actions">
          <label className="form-field" title="Choose a classroom dataset to review">
            <span className="form-label">Dataset</span>
            <select value={selectedClassroom.id} onChange={(event) => setSelectedClassroomId(Number(event.target.value))}>
              {classrooms.map((classroom) => (
                <option key={classroom.id} value={classroom.id}>
                  {classroom.classroom_label ?? classroom.classroom_key ?? `Classroom ${classroom.id}`}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ghost-button" onClick={() => setPreferredStage("classroom_dataset")}>Back</button>
          <button type="button" className="primary-button" onClick={() => void handleEvaluate()} disabled={isEvaluating}>
            {isEvaluating ? "Evaluating…" : "Run evaluation"}
          </button>
        </div>
      </header>

      {errorMessage ? <div className="panel-flash panel-flash--error">{errorMessage}</div> : null}

      <section className="classroom-eval__summary">
        <div className="classroom-eval__stat">
          <span>Total students</span>
          <strong>{summary.total_students ?? selectedClassroom.total_students ?? "—"}</strong>
        </div>
        <div className="classroom-eval__stat">
          <span>Cheating students</span>
          <strong>{summary.cheating_students ?? "—"}</strong>
        </div>
        <div className="classroom-eval__stat">
          <span>Cheating rate</span>
          <strong>{formatPercent(summary.cheating_rate)}</strong>
        </div>
        <div className="classroom-eval__stat">
          <span>Average score</span>
          <strong>{formatScore(summary.average_score)}</strong>
        </div>
        <div className="classroom-eval__stat">
          <span>Median score</span>
          <strong>{formatScore(summary.median_score)}</strong>
        </div>
      </section>

      {strategyBreakdown ? (
        <section className="classroom-eval__strategies">
          <h3>Cheating strategies</h3>
          <div className="strategy-pills">
            {Object.entries(strategyBreakdown).map(([strategy, count]) => (
              <span key={strategy} className="strategy-pill" title={`${strategy.replace(/_/g, " ")} cheaters`}>
                {strategy.replace(/_/g, " ")} · {count}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {scoreDistribution && scoreDistribution.length ? (
        <section className="classroom-eval__scores">
          <h3>Score distribution</h3>
          <div className="score-pills">
            {scoreDistribution.map((bucket, index) => (
              <span key={index} className="score-pill" title={`Students scoring between ${bucket.label}`}>
                {bucket.label ?? "—"} · {bucket.count ?? 0}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="classroom-eval__students">
        <header>
          <h3>Student breakdown</h3>
          {evaluation?.artifacts?.json && activeRunId ? (
            <a
              className="ghost-button"
              href={`/api/files/${activeRunId}/${evaluation.artifacts.json}`}
              download
              title="Download evaluation JSON"
            >
              Download JSON
            </a>
          ) : null}
        </header>
        {isLoading ? (
          <p style={{ color: "var(--muted)" }}>Loading evaluation…</p>
        ) : students.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>
            {evaluation ? "No students met the evaluation criteria." : "Run the evaluation to populate student insights."}
          </p>
        ) : (
          <div className="table-wrapper">
            <table className="data-table classroom-eval__table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Score</th>
                  <th>Cheating strategy</th>
                  <th>Copy fraction</th>
                  <th>Avg confidence</th>
                  <th>Cheating sources</th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => {
                  const sources = Object.entries(student.cheating_source_counts ?? {}).map(
                    ([source, count]) => `${source}: ${count}`
                  );
                  return (
                    <tr key={student.student_id}>
                      <td>
                        <div className="classroom-cell__label">
                          <span>{student.display_name}</span>
                          <span className="classroom-cell__notes" title="Internal identifier">
                            {student.student_key}
                          </span>
                        </div>
                      </td>
                      <td>{formatScore(student.score)}</td>
                      <td>{student.cheating_strategy ?? "fair"}</td>
                      <td>{student.copy_fraction != null ? formatPercent(student.copy_fraction, "—") : "—"}</td>
                      <td>
                        {student.average_confidence != null
                          ? `${Math.round(student.average_confidence * 100)}%`
                          : "—"}
                      </td>
                      <td>{sources.length ? sources.join(", ") : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

export default ClassroomEvaluationPanel;
