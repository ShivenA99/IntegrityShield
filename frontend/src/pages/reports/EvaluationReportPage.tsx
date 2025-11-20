import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { usePipeline } from "@hooks/usePipeline";

const encodeRelativePath = (relativePath: string) =>
  relativePath.split(/[\\/]+/).filter(Boolean).map(encodeURIComponent).join("/");

const PROVIDER_META: Record<string, { label: string; glyph: string; className: string }> = {
  openai: { label: "OpenAI", glyph: "O", className: "provider-badge provider-badge--openai" },
  anthropic: { label: "Anthropic", glyph: "A", className: "provider-badge provider-badge--anthropic" },
  google: { label: "Gemini", glyph: "G", className: "provider-badge provider-badge--google" },
};

type QuestionOption = { label: string; text: string };

const normalizeOptions = (raw: any): QuestionOption[] => {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map((entry, idx) => {
        if (typeof entry !== "object" || entry === null) {
          return { label: String.fromCharCode(65 + idx), text: String(entry ?? "") };
        }
        const baseLabel =
          (entry.label ?? entry.option ?? entry.id ?? String.fromCharCode(65 + idx)) as string;
        return {
          label: baseLabel.trim().toUpperCase(),
          text: (entry.text ?? entry.value ?? entry.content ?? "").toString(),
        };
      })
      .filter((opt) => opt.label);
  }
  if (typeof raw === "object") {
    return Object.entries(raw).map(([label, text]) => ({
      label: label.toString().trim().toUpperCase(),
      text: String(text ?? ""),
    }));
  }
  return [];
};

const EvaluationReportPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { status, activeRunId, setActiveRunId, refreshStatus } = usePipeline();
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null);
  const [reportData, setReportData] = useState<Record<string, any> | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    if (runId !== activeRunId) {
      setActiveRunId(runId);
      refreshStatus(runId).catch(() => undefined);
    } else if (!status) {
      refreshStatus(runId).catch(() => undefined);
    }
  }, [runId, activeRunId, status, setActiveRunId, refreshStatus]);

  const structured = (status?.structured_data as Record<string, any> | undefined) ?? undefined;
  const reports = (structured?.reports as Record<string, any>) ?? {};
  const evaluationBucket = (reports?.evaluation as Record<string, any>) ?? {};
  const evaluationEntries = Object.entries(evaluationBucket);

  useEffect(() => {
    if (!evaluationEntries.length) {
      setSelectedMethod(null);
      return;
    }
    if (!selectedMethod || !evaluationBucket[selectedMethod]) {
      setSelectedMethod(evaluationEntries[0][0]);
    }
  }, [evaluationEntries, evaluationBucket, selectedMethod]);

  const selectedMeta = selectedMethod ? evaluationBucket[selectedMethod] : null;
  const artifactPath = selectedMeta?.artifact;

  useEffect(() => {
    if (!runId || !artifactPath) {
      setReportData(null);
      return;
    }
    const controller = new AbortController();
    const fetchReport = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/files/${runId}/${encodeRelativePath(artifactPath)}`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Fetch failed: ${response.status} ${response.statusText}`);
        }
        const json = await response.json();
        setReportData(json);
      } catch (err) {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
      } finally {
        setIsLoading(false);
      }
    };
    fetchReport();
    return () => controller.abort();
  }, [artifactPath, runId]);

  const formattedTimestamp = useMemo(() => {
    if (!selectedMeta?.generated_at) return null;
    try {
      return new Date(selectedMeta.generated_at).toLocaleString();
    } catch {
      return selectedMeta.generated_at;
    }
  }, [selectedMeta?.generated_at]);

  const providerSummary = (reportData?.summary?.providers as any[]) || [];
  const questionEntries = (reportData?.questions as any[]) || [];
  const sortedQuestions = useMemo(() => {
    return [...questionEntries].sort((a, b) => {
      const left = Number(a?.question_number ?? a?.questionNumber ?? 0);
      const right = Number(b?.question_number ?? b?.questionNumber ?? 0);
      return left - right;
    });
  }, [questionEntries]);
  const detectionContext = reportData?.context?.detection;

  const handleDownload = useCallback(async () => {
    if (!runId || !artifactPath) return;
    try {
      const response = await fetch(`/api/files/${runId}/${encodeRelativePath(artifactPath)}`);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `evaluation-report-${selectedMethod ?? "variant"}.json`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    }
  }, [artifactPath, runId, selectedMethod]);

  return (
    <div className="page report-page">
      <div className="panel">
        <header className="panel-header panel-header--tight">
          <div>
            <h1>Evaluation Report</h1>
            <p className="muted">
              Run {runId}
              {selectedMethod ? ` · Variant ${selectedMethod}` : null}
              {formattedTimestamp ? ` · Generated ${formattedTimestamp}` : null}
            </p>
          </div>
          <div className="panel-actions">
            <button type="button" className="ghost-button" onClick={() => navigate(-1)}>
              Back
            </button>
            <button type="button" className="ghost-button" onClick={handleDownload} disabled={!artifactPath}>
              Download JSON
            </button>
          </div>
        </header>

        {!evaluationEntries.length ? (
          <p className="empty-state">No evaluation reports yet. Run evaluation from PDF Creation.</p>
        ) : (
          <>
            <section className="report-variant-grid">
              {evaluationEntries.map(([method, meta]) => (
                <button
                  key={method}
                  type="button"
                  className={`report-variant ${selectedMethod === method ? "is-selected" : ""}`}
                  onClick={() => setSelectedMethod(method)}
                >
                  <strong>{method}</strong>
                  <span>{meta.summary?.providers?.length ?? 0} providers</span>
                </button>
              ))}
            </section>
            {isLoading ? (
              <p className="muted">Loading report…</p>
            ) : error ? (
              <p className="panel-flash panel-flash--error">{error}</p>
            ) : (
              <>
                <section className="report-summary-grid">
                  {providerSummary.map((entry) => (
                    <div key={entry.provider}>
                      <span>{entry.provider}</span>
                      <strong>{(entry.average_score ?? 0).toFixed(2)}</strong>
                      <small className="muted">
                        {entry.questions_evaluated ?? 0} q · Δ{" "}
                        {entry.average_delta_from_baseline != null
                          ? entry.average_delta_from_baseline.toFixed(2)
                          : "—"}
                      </small>
                    </div>
                  ))}
                </section>

                {detectionContext?.summary ? (
                  <section className="report-context-card">
                    <header>
                      <h2>Detection Reference</h2>
                      {detectionContext.generated_at ? (
                        <small className="muted">
                          Generated {new Date(detectionContext.generated_at).toLocaleString()}
                        </small>
                      ) : null}
                    </header>
                    <p className="muted">
                      {detectionContext.summary.high_risk_questions ?? 0} high-risk questions ·{" "}
                      {detectionContext.summary.total_questions ?? 0} total
                    </p>
                  </section>
                ) : null}

                <section className="report-question-list">
                  {sortedQuestions.length ? (
                    sortedQuestions.map((question) => {
                      const options = normalizeOptions(question.options);
                      const optionLookup = options.reduce<Record<string, string>>((acc, opt) => {
                        acc[opt.label] = opt.text;
                        return acc;
                      }, {});
                      const detectionTarget = question.detection_target?.labels || [];
                      return (
                        <article
                          key={question.question_number}
                          className={`report-question-card risk-${question.risk_level ?? "low"}`}
                        >
                          <div className="report-question-card__header">
                            <div>
                              <strong>Q{question.question_number}</strong> ·{" "}
                              {question.question_type ?? "Unknown"}
                            </div>
                          </div>
                          <p className="report-question-card__stem">{question.question_text}</p>
                          <div className="report-question-card__chips">
                            <span className="report-tag report-tag--gold">
                              Gold {question.gold_answer ?? "—"}
                            </span>
                            {detectionTarget.length ? (
                              detectionTarget.map((label: string) => (
                                <span key={label} className="report-tag report-tag--target">
                                  Target {label}
                                </span>
                              ))
                            ) : (
                              <span className="report-tag report-tag--muted">No detection target</span>
                            )}
                          </div>
                          {options.length ? (
                            <ul className="report-question-card__options">
                              {options.map((opt) => (
                                <li key={`${question.question_number}-${opt.label}`}>
                                  <span className="report-question-card__option-label">
                                    {opt.label}
                                  </span>
                                  <span>{opt.text}</span>
                                </li>
                              ))}
                            </ul>
                          ) : null}
                          <div className="report-question-card__answers">
                            {(question.answers as any[])?.map((answer) => {
                              const providerKey = (answer.provider || "").toLowerCase();
                              const providerMeta = PROVIDER_META[providerKey];
                              const scorecard = answer.scorecard || {};
                              const detectionHit =
                                answer.matches_detection_target ?? scorecard.hit_detection_target;
                              const baselineScore = answer.baseline_score;
                              const delta = answer.delta_from_baseline;
                              return (
                                <div
                                  key={`${question.question_number}-${answer.provider}`}
                                  className="report-answer-chip"
                                >
                                  <div className="report-answer-chip__header">
                                    <div className="provider-chip">
                                      <span className={providerMeta?.className ?? "provider-badge"}>
                                        {providerMeta?.glyph ??
                                          answer.provider?.charAt(0)?.toUpperCase() ??
                                          "?"}
                                      </span>
                                      <span>{providerMeta?.label ?? answer.provider ?? "Unknown"}</span>
                                    </div>
                                    <strong>
                                      {scorecard.score != null ? scorecard.score.toFixed(2) : "—"}
                                    </strong>
                                  </div>
                                  <div className="report-answer-chip__meta">
                                    <span
                                      className={`score-source score-source--${
                                        (scorecard.source || "llm").toLowerCase()
                                      }`}
                                    >
                                      {scorecard.source === "heuristic" ? "Heuristic" : "LLM scorer"}
                                    </span>
                                    {detectionHit ? (
                                      <span className="report-tag report-tag--target">
                                        Target hit
                                      </span>
                                    ) : null}
                                  </div>
                                  <small className="report-answer-chip__label">
                                    {answer.answer_label
                                      ? `${answer.answer_label}${
                                          optionLookup[answer.answer_label]
                                            ? ` · ${optionLookup[answer.answer_label]}`
                                            : ""
                                        }`
                                      : "Answer label unknown"}
                                  </small>
                                  <small className="muted">
                                    {baselineScore != null
                                      ? `Δ ${
                                          delta != null ? delta.toFixed(2) : "0.00"
                                        } vs baseline ${baselineScore.toFixed(2)}`
                                      : "No baseline"}
                                  </small>
                                  <p>{answer.answer_text || answer.error || "No answer returned."}</p>
                                </div>
                              );
                            })}
                          </div>
                        </article>
                      );
                    })
                  ) : (
                    <p className="muted">No question-level details were found in this artifact.</p>
                  )}
                </section>
                <section className="report-json">
                  <header>
                    <h2>Summary JSON</h2>
                  </header>
                  <pre>{JSON.stringify(reportData?.summary ?? {}, null, 2)}</pre>
                </section>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default EvaluationReportPage;

