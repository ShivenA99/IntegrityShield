import * as React from "react";
import { useState, useMemo, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldAlert } from "lucide-react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { formatDuration } from "@services/utils/formatters";
import PageTitle from "@components/common/PageTitle";

const ContentDiscoveryPanel: React.FC = () => {
  const { status, activeRunId, resumeFromStage, setPreferredStage, generateVulnerabilityReport } = usePipeline();
  const { questions, refresh: refreshQuestions } = useQuestions(activeRunId);
  const navigate = useNavigate();
  const stage = status?.stages.find((item) => item.name === "content_discovery");
  const structured = (status?.structured_data as Record<string, any> | undefined) ?? {};
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [isGeneratingVulnerability, setIsGeneratingVulnerability] = useState(false);
  const [vulnerabilityMessage, setVulnerabilityMessage] = useState<string | null>(null);
  const [vulnerabilityError, setVulnerabilityError] = useState<string | null>(null);
  const reports = (structured?.reports as Record<string, any> | undefined) ?? {};
  const vulnerabilityReport = reports?.vulnerability ?? null;
  const vulnerabilityTimestamp = vulnerabilityReport?.generated_at
    ? new Date(vulnerabilityReport.generated_at).toLocaleString()
    : null;

  const totalQuestions = questions.length;
  const discoveredSources = Array.isArray(structured?.content_elements)
    ? (structured.content_elements as unknown[]).length
    : 0;
  const lastUpdated = structured?.pipeline_metadata?.last_updated;
  const goldGeneration = structured?.pipeline_metadata?.gold_generation as
    | { status?: string; total?: number; completed?: number; pending?: number }
    | undefined;

  const goldStatus = useMemo(() => {
    const total = goldGeneration?.total ?? totalQuestions;
    const completed = goldGeneration?.completed ?? questions.filter((question) => Boolean(question.gold_answer)).length;
    const statusValue = goldGeneration?.status ?? (completed >= total && total > 0 ? "completed" : total === 0 ? "completed" : "running");
    const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 100;
    return {
      status: statusValue,
      total,
      completed,
      percent,
    };
  }, [goldGeneration, questions, totalQuestions]);

  const goldReady = goldStatus.total === 0 || (goldStatus.status === "completed" && goldStatus.completed >= goldStatus.total);

  const resolveRelativePath = useCallback(
    (raw?: string | null) => {
      if (!status?.run_id || !raw) return null;
      const normalized = raw.replace(/\\/g, "/");
      const marker = `/pipeline_runs/${status.run_id}/`;
      const markerIdx = normalized.indexOf(marker);
      if (markerIdx !== -1) {
        return normalized.slice(markerIdx + marker.length);
      }
      const parts = normalized.split("/pipeline_runs/");
      if (parts.length > 1) {
        return parts[1].split("/").slice(1).join("/");
      }
      return normalized.startsWith("/") ? normalized.slice(1) : normalized;
    },
    [status?.run_id]
  );

  const reconstructedInfo = useMemo(() => {
    const raw = structured?.pipeline_metadata?.data_extraction_outputs?.pdf as string | undefined;
    const relative = resolveRelativePath(raw);
    if (!relative || !status?.run_id) {
      return null;
    }
    const url = `/api/files/${status.run_id}/${relative.split("/").map(encodeURIComponent).join("/")}`;
    const filename = raw?.split(/[\\/]/).pop() ?? "reconstructed.pdf";
    return { url, filename };
  }, [structured, resolveRelativePath, status?.run_id]);

  const handleAdvance = async () => {
    if (!activeRunId) return;
    setIsAdvancing(true);
    try {
      await resumeFromStage(activeRunId, "smart_substitution");
      setPreferredStage("smart_substitution");
    } finally {
      setIsAdvancing(false);
    }
  };

  const questionCards = useMemo(
    () =>
      questions.map((question) => ({
        id: question.id,
        number: question.question_number ?? question.id,
        type: question.question_type ?? "Unknown",
        stem: question.stem_text || question.original_text || "",
        goldAnswer: question.gold_answer ?? null,
      })),
    [questions]
  );

  const handleGenerateVulnerabilityReport = useCallback(async () => {
    if (!activeRunId) return;
    setIsGeneratingVulnerability(true);
    setVulnerabilityMessage(null);
    setVulnerabilityError(null);
    try {
      await generateVulnerabilityReport(activeRunId);
      setVulnerabilityMessage("Vulnerability report generated.");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setVulnerabilityError(`Failed to generate vulnerability report: ${message}`);
    } finally {
      setIsGeneratingVulnerability(false);
    }
  }, [activeRunId, generateVulnerabilityReport]);

  const handleOpenVulnerabilityReport = useCallback(() => {
    if (!status?.run_id || !vulnerabilityReport?.artifact) return;
    navigate(`/runs/${status.run_id}/reports/vulnerability`);
  }, [navigate, status?.run_id, vulnerabilityReport?.artifact]);

  const vulnerabilityButtonDisabled =
    !activeRunId || isGeneratingVulnerability || stage?.status !== "completed" || !goldReady;

  useEffect(() => {
    if (!activeRunId) return;
    if (goldStatus.status !== "running") return;
    const interval = window.setInterval(() => {
      refreshQuestions();
    }, 2500);
    return () => {
      window.clearInterval(interval);
    };
  }, [activeRunId, goldStatus.status, refreshQuestions]);

  useEffect(() => {
    if (goldStatus.status !== "completed") return;
    refreshQuestions();
  }, [goldStatus.status, refreshQuestions]);

  return (
    <div className="panel content-discovery">
      <header className="panel-header panel-header--tight">
        <PageTitle>Content Discovery</PageTitle>
        <div className="panel-actions">
          <div className="panel-actions__inline">
            <button
              type="button"
              className="ghost-button"
              onClick={handleGenerateVulnerabilityReport}
              disabled={vulnerabilityButtonDisabled}
              aria-busy={isGeneratingVulnerability}
              title={
                !goldReady
                  ? "Gold answers are still being generated. Please wait for completion."
                  : stage?.status !== "completed"
                  ? "Complete Content Discovery before generating vulnerability reports."
                  : "Generate a multi-model accuracy baseline for the original PDF."
              }
            >
              {isGeneratingVulnerability ? "Generating…" : "Generate Vulnerability Report"}
            </button>
            <button
              type="button"
              className="icon-button"
              disabled={!vulnerabilityReport?.artifact}
              onClick={handleOpenVulnerabilityReport}
              title={
                vulnerabilityReport?.artifact
                  ? `Open vulnerability report${vulnerabilityTimestamp ? ` (${vulnerabilityTimestamp})` : ""}`
                  : "Generate a vulnerability report to view results."
              }
            >
              <ShieldAlert size={16} />
            </button>
          </div>
          {stage?.status === "completed" && (
            <button type="button" className="primary-button" onClick={handleAdvance} disabled={isAdvancing}>
              {isAdvancing ? "Advancing…" : "Next"}
            </button>
          )}
        </div>
      </header>

      <div className="stage-overview">
        <div className="stage-overview__item">
          <span>Status</span>
          <strong className={`status-tag status-${stage?.status ?? "pending"}`}>{stage?.status ?? "pending"}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Duration</span>
          <strong>{formatDuration(stage?.duration_ms) || "—"}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Questions</span>
          <strong>{totalQuestions}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Sources</span>
          <strong>{discoveredSources}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Updated</span>
          <strong>{lastUpdated ? new Date(lastUpdated).toLocaleString() : "—"}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Gold answers</span>
          <strong>
            {goldStatus.completed}/{goldStatus.total || 0}
          </strong>
        </div>
      </div>

      {vulnerabilityMessage ? (
        <div className="panel-flash panel-flash--info">{vulnerabilityMessage}</div>
      ) : null}
      {vulnerabilityError ? <div className="panel-flash panel-flash--error">{vulnerabilityError}</div> : null}

      <section className="content-discovery__body">
        <div className={`gold-progress gold-progress--${goldStatus.status}`}>
          <div className="gold-progress__header">
            <span>Gold answers</span>
            <span className="gold-progress__status">
              {goldStatus.status === "completed"
                ? "Ready"
                : goldStatus.status === "partial"
                ? "Needs review"
                : "Generating…"}
            </span>
          </div>
          <div className="gold-progress__bar">
            <span style={{ width: `${goldStatus.percent}%` }} />
          </div>
          <div className="gold-progress__meta">
            <span>
              {goldStatus.completed}/{goldStatus.total || 0} completed
            </span>
            {!goldReady && <span className="gold-progress__hint">New answers populate automatically as soon as GPT-5 responds.</span>}
          </div>
        </div>

        {reconstructedInfo ? (
          <aside className="document-preview-card">
            <header>
              <span>Reconstructed PDF</span>
              <span className="document-preview-card__filename">{reconstructedInfo.filename}</span>
            </header>
            <div className="document-preview-card__frame">
              <object data={reconstructedInfo.url} type="application/pdf" aria-label="Reconstructed PDF preview">
                <a href={reconstructedInfo.url} target="_blank" rel="noopener noreferrer">
                  Open reconstructed PDF
                </a>
              </object>
            </div>
            <div className="document-preview-card__actions">
              <a href={reconstructedInfo.url} target="_blank" rel="noopener noreferrer">
                View
              </a>
              <a href={reconstructedInfo.url} download={reconstructedInfo.filename}>
                Download
              </a>
            </div>
          </aside>
        ) : null}

        <div className="question-panel">
          <header className="question-panel__header">
            <h2>Detected Questions</h2>
            <span>{totalQuestions}</span>
          </header>

          {questionCards.length ? (
            <div className="question-panel__grid">
              {questionCards.map((entry) => (
                <article key={entry.id} className="question-card">
                  <div className="question-card__meta">
                    <span className="question-card__id">Q{entry.number}</span>
                    <span className="question-card__type">{entry.type}</span>
                  </div>
                  {entry.stem ? (
                    <p>{entry.stem.slice(0, 140)}{entry.stem.length > 140 ? "…" : ""}</p>
                  ) : (
                    <p className="muted">No prompt text detected</p>
                  )}
                  {entry.goldAnswer ? (
                    <div className="question-card__gold">
                      <span>Gold answer</span>
                      <strong>{entry.goldAnswer}</strong>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="empty-state">No questions detected yet.</p>
          )}
        </div>
      </section>
    </div>
  );
};

export default ContentDiscoveryPanel;
