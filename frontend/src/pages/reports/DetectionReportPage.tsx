import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { usePipeline } from "@hooks/usePipeline";
import { ReportHeader, SummaryCard, RiskBadge, MappingCard } from "@components/reports";

import "@styles/reports.css";

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

  const mode = status?.pipeline_config?.mode;

  return (
    <div className="page report-page">
      <ReportHeader
        title="Detection Report"
        subtitle={`Run ${runId} · ${formattedTimestamp ? `Generated ${formattedTimestamp}` : "Not generated"}`}
        mode={mode}
        actions={
          <>
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
          </>
        }
      />

      {!detectionPayload ? (
        <div className="report-empty-state">
          <h3>No Report Available</h3>
          <p>No detection report is available yet. Generate one from the PDF Creation panel.</p>
        </div>
      ) : (
        <>
          {summary ? (
            <section className="detection-summary-dashboard">
              <SummaryCard
                title="Total Questions"
                value={summary.total_questions ?? questions.length}
                icon={<span style={{ fontSize: "2.5rem" }}>📊</span>}
              />
              <SummaryCard
                title="With Mappings"
                value={summary.questions_with_mappings ?? 0}
                icon={<span style={{ fontSize: "2.5rem" }}>🎯</span>}
              />
              <SummaryCard
                title="High Risk"
                value={summary.high_risk_questions ?? 0}
                variant="danger"
                icon={<span style={{ fontSize: "2.5rem" }}>⚠️</span>}
              />
            </section>
          ) : null}
            {regenMessage ? <p className="panel-flash panel-flash--success">{regenMessage}</p> : null}
            {regenError ? <p className="panel-flash panel-flash--error">{regenError}</p> : null}

          <section className="report-question-list">
            {questions.length ? (
              questions.map((question) => {
                const mappings = Array.isArray(question.mappings) ? question.mappings : [];
                const limitedMappings = mappings.slice(0, 3);
                const signalPhrase = question.target_answer?.signal?.phrase ?? null;
                return (
                  <article
                    key={question.question_number}
                    className="report-question-card"
                    data-risk={question.risk_level ?? "low"}
                  >
                    <div className="card-header">
                      <span className="question-number">Q{question.question_number}</span>
                      <RiskBadge risk={question.risk_level ?? "low"} />
                    </div>
                    <p className="question-stem">{question.stem_text}</p>
                    <div className="target-info">
                      <span className="gold-answer">
                        Gold: {question.gold_answer?.label ?? "—"}
                      </span>
                      <span className="target-answer">
                        Target: {question.target_answer?.labels?.length
                          ? question.target_answer.labels.join(", ")
                          : "—"}
                      </span>
                      {signalPhrase ? (
                        <span className="signal-phrase">
                          📡 Signal: "{signalPhrase}"
                        </span>
                      ) : null}
                    </div>
                    {limitedMappings.length ? (
                      <div className="mappings-grid">
                        {limitedMappings.map((mapping, index) => (
                          <MappingCard
                            key={mapping.id ?? index}
                            context={mapping.context ?? "stem"}
                            original={mapping.original ?? "—"}
                            replacement={mapping.replacement ?? "—"}
                            deviationScore={mapping.deviation_score}
                            validated={mapping.validated ?? false}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="muted">No mappings recorded for this question.</p>
                    )}
                    {mappings.length > limitedMappings.length ? (
                      <button className="show-more-btn">
                        +{mappings.length - limitedMappings.length} more mapping
                        {mappings.length - limitedMappings.length === 1 ? "" : "s"}
                      </button>
                    ) : null}
                  </article>
                );
              })
            ) : (
              <div className="report-empty-state">
                <h3>No Questions Found</h3>
                <p>No question-level details available.</p>
              </div>
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
      {downloadError ? <div className="panel-flash panel-flash--error">{downloadError}</div> : null}
    </div>
  );
};

export default DetectionReportPage;
