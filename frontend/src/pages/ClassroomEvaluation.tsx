import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";
import type { ClassroomDataset, ClassroomEvaluationResponse, ClassroomStudentMetric, PipelineRunSummary } from "@services/types/pipeline";
import { evaluateClassroom, getClassroomEvaluation, getPipelineStatus } from "@services/api/pipelineApi";

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

const ClassroomEvaluationPage: React.FC = () => {
  const navigate = useNavigate();
  const { runId, classroomId } = useParams();
  const [status, setStatus] = useState<PipelineRunSummary | null>(null);
  const [evaluation, setEvaluation] = useState<ClassroomEvaluationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const numericClassroomId = classroomId ? Number(classroomId) : NaN;

  const classrooms: ClassroomDataset[] = useMemo(() => status?.classrooms ?? [], [status?.classrooms]);
  const classroom = useMemo(
    () => classrooms.find((item) => item.id === numericClassroomId) ?? null,
    [classrooms, numericClassroomId]
  );

  const methodLabel = classroom?.attacked_pdf_method
    ? ENHANCEMENT_METHOD_LABELS[classroom.attacked_pdf_method] ?? classroom.attacked_pdf_method.replace(/_/g, " ")
    : "—";

  const loadStatus = useCallback(async () => {
    if (!runId) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const runStatus = await getPipelineStatus(runId);
      setStatus(runStatus);
    } catch (err: any) {
      setErrorMessage(err?.response?.data?.error || err?.message || "Failed to load run.");
    } finally {
      setIsLoading(false);
    }
  }, [runId]);

  const loadEvaluation = useCallback(
    async (targetRunId: string, targetClassroomId: number) => {
      setErrorMessage(null);
      setIsLoading(true);
      try {
        const result = await getClassroomEvaluation(targetRunId, targetClassroomId);
        setEvaluation(result);
      } catch (err: any) {
        setErrorMessage(err?.response?.data?.error || err?.message || "Failed to load classroom evaluation.");
        setEvaluation(null);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!runId || Number.isNaN(numericClassroomId)) return;
    void (async () => {
      await loadStatus();
      await loadEvaluation(runId, numericClassroomId);
    })();
  }, [loadEvaluation, loadStatus, numericClassroomId, runId]);

  const handleReEvaluate = useCallback(async () => {
    if (!runId || Number.isNaN(numericClassroomId)) return;
    setIsEvaluating(true);
    try {
      const result = await evaluateClassroom(runId, numericClassroomId);
      setEvaluation(result);
      await loadStatus();
    } catch (err: any) {
      setErrorMessage(err?.response?.data?.error || err?.message || "Failed to run classroom evaluation.");
    } finally {
      setIsEvaluating(false);
    }
  }, [loadStatus, numericClassroomId, runId]);

  const summary = (evaluation?.summary ?? {}) as Record<string, any>;
  const strategyBreakdown = summary.strategy_breakdown as Record<string, number> | undefined;
  const scoreDistribution = summary.score_distribution as Array<Record<string, any>> | undefined;
  const students: ClassroomStudentMetric[] = evaluation?.students ?? [];

  if (!runId || Number.isNaN(numericClassroomId)) {
    return (
      <div className="page classroom-evaluation-page">
        <p>Missing run or classroom identifier.</p>
      </div>
    );
  }

  if (!classroom && !isLoading) {
    return (
      <div className="page classroom-evaluation-page">
        <p>Classroom dataset was not found.</p>
        <button type="button" className="ghost-button" onClick={() => navigate("/classrooms?view=evaluations")}>
          Back to evaluations
        </button>
      </div>
    );
  }

  return (
    <div className="page classroom-evaluation-page">
      <header className="page-header">
        <div>
          <h1>Classroom evaluation</h1>
          <p>
            {classroom?.classroom_label ?? classroom?.classroom_key ?? `Classroom ${classroom?.id ?? ""}`} · Variant:{" "}
            {methodLabel} · Students: {classroom?.total_students ?? "—"}
          </p>
        </div>
        <div className="page-header__actions">
          <button type="button" className="ghost-button" onClick={() => navigate("/classrooms?view=evaluations")}>
            Back to evaluations
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => void handleReEvaluate()}
            disabled={isEvaluating}
          >
            {isEvaluating ? "Evaluating…" : "Re-run evaluation"}
          </button>
        </div>
      </header>

      {errorMessage ? <div className="panel-flash panel-flash--error">{errorMessage}</div> : null}

      <section className="panel classroom-evaluation">
        {isLoading ? <p>Loading evaluation…</p> : null}
        <div className="classroom-eval__summary">
          <div className="classroom-eval__stat">
            <span>Total students</span>
            <strong>{summary.total_students ?? classroom?.total_students ?? "—"}</strong>
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
        </div>

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
            {evaluation?.artifacts?.json ? (
              <a
                className="ghost-button"
                href={`/api/files/${runId}/${evaluation.artifacts.json}`}
                download
                title="Download evaluation JSON"
              >
                Download JSON
              </a>
            ) : null}
          </header>
          {students.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>Evaluation contains no student records.</p>
          ) : (
            <div className="table-wrapper">
              <table className="data-table classroom-eval__table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Cheating</th>
                    <th>Strategy</th>
                    <th>Score</th>
                    <th>Questions</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((student) => (
                    <tr key={student.student_id}>
                      <td>{student.display_name ?? student.student_key}</td>
                      <td>{student.is_cheating ? "Yes" : "No"}</td>
                      <td>{student.cheating_strategy ?? "—"}</td>
                      <td>{formatScore(student.score)}</td>
                      <td>
                        {student.correct_answers ?? 0} / {student.total_questions ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>
    </div>
  );
};

export default ClassroomEvaluationPage;
