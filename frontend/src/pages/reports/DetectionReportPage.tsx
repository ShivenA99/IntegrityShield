import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { usePipeline } from "@hooks/usePipeline";

const encodeRelativePath = (relativePath: string) =>
  relativePath.split(/[\\/]+/).filter(Boolean).map(encodeURIComponent).join("/");

const DetectionReportPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { status, activeRunId, setActiveRunId, refreshStatus, generateDetectionReport } = usePipeline();
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [regenMessage, setRegenMessage] = useState<string | null>(null);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);

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
  const manipulationResults = (structured?.manipulation_results as Record<string, any>) ?? {};
  const detectionPayload = (manipulationResults?.detection_report as Record<string, any>) ?? null;
  const reports = (structured?.reports as Record<string, any>) ?? {};
  const detectionMeta = (reports?.detection as Record<string, any>) ?? {};

  const artifactPath =
    detectionMeta?.artifact ||
    detectionPayload?.relative_path ||
    detectionPayload?.output_files?.json ||
    detectionPayload?.file_path ||
    null;
  const artifactUrl =
    runId && artifactPath ? `/api/files/${runId}/${encodeRelativePath(artifactPath)}` : undefined;

  const summary = detectionPayload?.summary || detectionMeta?.summary || null;
  const questions = (detectionPayload?.questions as any[]) || [];

  const riskLabel = useCallback((level?: string) => {
    return (level || "low").toUpperCase();
  }, []);

  const formattedTimestamp = useMemo(() => {
    const ts = detectionPayload?.generated_at || detectionMeta?.generated_at;
    if (!ts) return null;
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  }, [detectionMeta?.generated_at, detectionPayload?.generated_at]);

  const handleDownload = useCallback(async () => {
    if (!artifactUrl) return;
    setDownloadError(null);
    try {
      const response = await fetch(artifactUrl);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status} ${response.statusText}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `detection-report-${runId}.json`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setDownloadError(message);
    }
  }, [artifactUrl, runId]);

  const handleRegenerate = useCallback(async () => {
    if (!runId || isRegenerating) return;
    setIsRegenerating(true);
    setRegenError(null);
    setRegenMessage(null);
    try {
      await generateDetectionReport(runId);
      setRegenMessage("Detection report refreshed.");
      await refreshStatus(runId, { quiet: true }).catch(() => undefined);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRegenError(`Failed to regenerate detection report: ${message}`);
    } finally {
      setIsRegenerating(false);
    }
  }, [generateDetectionReport, isRegenerating, refreshStatus, runId]);

  return (
    <div className="page report-page">
      <div className="panel">
        <header className="panel-header panel-header--tight">
          <div>
            <h1>Detection Report</h1>
            <p className="muted">
              Run {runId} · {formattedTimestamp ? `Generated ${formattedTimestamp}` : "Not generated"}
            </p>
          </div>
          <div className="panel-actions">
            <button type="button" className="ghost-button" onClick={() => navigate(-1)}>
              Back
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={handleRegenerate}
              disabled={isRegenerating}
            >
              {isRegenerating ? "Regenerating…" : "Regenerate"}
            </button>
            <button type="button" className="ghost-button" onClick={handleDownload} disabled={!artifactUrl}>
              Download JSON
            </button>
          </div>
        </header>

        {!detectionPayload ? (
          <p className="empty-state">
            No detection report is available yet. Generate one from the PDF Creation panel.
          </p>
        ) : (
          <>
            <section className="report-toolbar">
              <span className="report-tag report-tag--status">
                Status: {detectionMeta?.status ?? detectionPayload?.status ?? "completed"}
              </span>
              {formattedTimestamp ? <span className="report-tag">Generated {formattedTimestamp}</span> : null}
            </section>
            {summary ? (
              <section className="report-summary-grid">
                <div>
                  <span>Total questions</span>
                  <strong>{summary.total_questions ?? questions.length}</strong>
                </div>
                <div>
                  <span>With mappings</span>
                  <strong>{summary.questions_with_mappings ?? "—"}</strong>
                </div>
                <div>
                  <span>Missing mappings</span>
                  <strong>{summary.questions_missing_mappings ?? "—"}</strong>
                </div>
                <div>
                  <span>High risk</span>
                  <strong>{summary.high_risk_questions ?? "—"}</strong>
                </div>
              </section>
            ) : null}
            {regenMessage ? <p className="panel-flash panel-flash--success">{regenMessage}</p> : null}
            {regenError ? <p className="panel-flash panel-flash--error">{regenError}</p> : null}

            <section className="report-question-list">
              {questions.length ? (
                questions.map((question) => {
                  const mappings = Array.isArray(question.mappings) ? question.mappings : [];
                  const limitedMappings = mappings.slice(0, 3);
                  return (
                    <article
                      key={question.question_number}
                      className={`report-question-card risk-${question.risk_level ?? "low"}`}
                    >
                      <div className="report-question-card__header">
                        <div>
                          <strong>Q{question.question_number}</strong> · {question.question_type ?? "Unknown"}
                        </div>
                        <span className={`risk-badge risk-${question.risk_level ?? "low"}`}>
                          {riskLabel(question.risk_level)}
                        </span>
                      </div>
                      <p className="report-question-card__stem">{question.stem_text}</p>
                      <div className="report-question-card__chips">
                        <span className="report-tag report-tag--gold">
                          Gold {question.gold_answer?.label ?? "—"}
                        </span>
                        {question.target_answer?.labels?.length ? (
                          question.target_answer.labels.map((label: string) => (
                            <span key={label} className="report-tag report-tag--target">
                              Target {label}
                            </span>
                          ))
                        ) : (
                          <span className="report-tag report-tag--muted">No target</span>
                        )}
                      </div>
                      <div className="report-question-card__meta">
                        <span>Gold: {question.gold_answer?.label ?? "—"}</span>
                        <span>
                          Target:{" "}
                          {question.target_answer?.labels?.length
                            ? question.target_answer.labels.join(", ")
                            : "—"}
                        </span>
                        <span>Mappings: {mappings.length}</span>
                      </div>
                      {limitedMappings.length ? (
                        <div className="report-question-card__answers">
                          {limitedMappings.map((mapping, index) => (
                            <div
                              key={mapping.id ?? index}
                              className={`report-answer-chip ${
                                mapping.validated
                                  ? "report-answer-chip--validated"
                                  : "report-answer-chip--pending"
                              }`}
                            >
                              <div className="report-answer-chip__header">
                                <span>{mapping.context ?? "stem"}</span>
                                <strong>{mapping.deviation_score != null ? mapping.deviation_score.toFixed(2) : "—"}</strong>
                              </div>
                              <small className="muted">
                                {mapping.original ?? "—"} → {mapping.replacement ?? "—"}
                              </small>
                              {mapping.validation_reason ? (
                                <p>{mapping.validation_reason}</p>
                              ) : mapping.reasoning ? (
                                <p>{mapping.reasoning}</p>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="muted">No mappings recorded for this question.</p>
                      )}
                      {mappings.length > limitedMappings.length ? (
                        <small className="muted">
                          +{mappings.length - limitedMappings.length} additional mapping
                          {mappings.length - limitedMappings.length === 1 ? "" : "s"} in JSON export
                        </small>
                      ) : null}
                    </article>
                  );
                })
              ) : (
                <p className="muted">No question-level details available.</p>
              )}
            </section>

            <section className="report-json">
              <header>
                <h2>Raw Summary</h2>
              </header>
              <pre>{JSON.stringify(summary ?? {}, null, 2)}</pre>
            </section>
          </>
        )}
        {downloadError ? <p className="panel-flash panel-flash--error">{downloadError}</p> : null}
      </div>
    </div>
  );
};

export default DetectionReportPage;

