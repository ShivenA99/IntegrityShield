import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { usePipeline } from "@hooks/usePipeline";
import { ReportHeader, SummaryCard, ProviderBadge, OptionCard } from "@components/reports";

import "@styles/reports.css";

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

  const mode = status?.pipeline_config?.mode;

  return (
    <div className="page report-page">
      <ReportHeader
        title="Evaluation Report"
        subtitle={`Run ${runId}${selectedMethod ? ` · Variant ${selectedMethod}` : ""}${formattedTimestamp ? ` · Generated ${formattedTimestamp}` : ""}`}
        mode={mode}
        actions={
          <>
            <button type="button" className="ghost-button" onClick={() => navigate(-1)}>
              Back
            </button>
            <button type="button" className="ghost-button" onClick={handleDownload} disabled={!artifactPath}>
              Download JSON
            </button>
          </>
        }
      />

      {!evaluationEntries.length ? (
        <div className="report-empty-state">
          <h3>No Reports Available</h3>
          <p>No evaluation reports yet. Run evaluation from PDF Creation.</p>
        </div>
      ) : (
        <>
          <section className="variant-selector-grid">
            {evaluationEntries.map(([method, meta]) => (
              <button
                key={method}
                type="button"
                className={`variant-card ${selectedMethod === method ? "active" : ""}`}
                onClick={() => setSelectedMethod(method)}
              >
                <div className="variant-header">
                  <h4>{method}</h4>
                  {selectedMethod === method && <span className="active-indicator">●</span>}
                </div>
                <div className="variant-stats">
                  <span>{meta.summary?.providers?.length ?? 0} providers</span>
                  <span>{meta.summary?.total_questions ?? 0} questions</span>
                </div>
              </button>
            ))}
          </section>
          {isLoading ? (
            <div className="report-loading">
              <p>Loading report…</p>
            </div>
          ) : error ? (
            <div className="panel-flash panel-flash--error">{error}</div>
          ) : (
            <>
              <section className="provider-performance-grid">
                {providerSummary.map((entry) => {
                  const delta = entry.average_delta_from_baseline ?? 0;
                  const deltaClass = delta >= 0 ? "positive" : "negative";
                  return (
                    <div key={entry.provider} className="provider-performance-card">
                      <div className="provider-header">
                        <ProviderBadge provider={entry.provider} />
                        <h4>{entry.provider}</h4>
                      </div>
                      <div className="performance-metrics">
                        <div className="metric">
                          <span className="metric-value">
                            {((entry.average_score ?? 0) * 100).toFixed(1)}%
                          </span>
                          <span className="metric-label">Accuracy</span>
                        </div>
                        <div className="metric">
                          <span className={`metric-value ${deltaClass}`}>
                            {delta >= 0 ? "+" : ""}
                            {(delta * 100).toFixed(1)}%
                          </span>
                          <span className="metric-label">Δ from Baseline</span>
                        </div>
                        <div className="metric">
                          <span className="metric-value">{entry.questions_evaluated ?? 0}</span>
                          <span className="metric-label">Questions</span>
                        </div>
                      </div>
                      {entry.hit_detection_target_count > 0 && (
                        <div className="detection-targets-alert">
                          ⚠️ Hit {entry.hit_detection_target_count} detection target
                          {entry.hit_detection_target_count > 1 ? "s" : ""}
                        </div>
                      )}
                    </div>
                  );
                })}
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
                    const detectionTarget = question.detection_target?.labels || [];
                    const detectionSignal = question.detection_target?.signal;
                    return (
                      <article key={question.question_number} className="report-question-card">
                        <div className="card-header">
                          <span className="question-number">Q{question.question_number}</span>
                          {detectionTarget.length > 0 && (
                            <span className="has-detection-target">
                              🎯 Detection Target
                            </span>
                          )}
                        </div>
                        <p className="question-stem">{question.question_text}</p>
                        {options.length ? (
                          <div className="options-grid">
                            {options.map((opt) => (
                              <OptionCard
                                key={`${question.question_number}-${opt.label}`}
                                label={opt.label}
                                text={opt.text}
                                isCorrect={opt.label === question.gold_answer}
                              />
                            ))}
                          </div>
                        ) : null}
                        <div className="answers-comparison">
                          {(question.answers as any[])?.map((answer) => {
                            const scorecard = answer.scorecard || {};
                            const detectionHit =
                              answer.matches_detection_target ?? scorecard.hit_detection_target;
                            const delta = answer.delta_from_baseline;
                            const deltaClass = delta && delta >= 0 ? "positive" : "negative";
                            return (
                              <div
                                key={`${question.question_number}-${answer.provider}`}
                                className="provider-answer-card"
                                data-hit-target={detectionHit}
                              >
                                <div className="provider-header">
                                  <ProviderBadge provider={answer.provider || "Unknown"} />
                                  <span className="provider-name">
                                    {answer.provider || "Unknown"}
                                  </span>
                                </div>
                                <div className="answer-info">
                                  <span className="answer-label">{answer.answer_label || "?"}</span>
                                  {scorecard.score != null && (
                                    <div className="scorecard">
                                      <span className="score">{scorecard.score.toFixed(2)}</span>
                                      {scorecard.verdict && (
                                        <span className="verdict">{scorecard.verdict}</span>
                                      )}
                                      {scorecard.confidence != null && (
                                        <span className="confidence">
                                          {(scorecard.confidence * 100).toFixed(0)}% confident
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </div>
                                {detectionHit && (
                                  <div className="detection-hit-alert">
                                    ⚠️ Hit detection target!
                                  </div>
                                )}
                                {delta != null && (
                                  <div className={`delta ${deltaClass}`}>
                                    Δ {delta >= 0 ? "+" : ""}
                                    {(delta * 100).toFixed(1)}%
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </article>
                    );
                  })
                ) : (
                  <div className="report-empty-state">
                    <h3>No Questions Found</h3>
                    <p>No question-level details were found in this artifact.</p>
                  </div>
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
  );
};

export default EvaluationReportPage;
