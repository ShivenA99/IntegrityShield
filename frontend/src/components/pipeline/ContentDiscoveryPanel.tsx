import * as React from "react";
import { useState, useMemo, useCallback } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { formatDuration } from "@services/utils/formatters";

const ContentDiscoveryPanel: React.FC = () => {
  const { status, activeRunId, resumeFromStage, setPreferredStage } = usePipeline();
  const { questions } = useQuestions(activeRunId);
  const stage = status?.stages.find((item) => item.name === "content_discovery");
  const structured = (status?.structured_data as Record<string, any> | undefined) ?? {};
  const [isAdvancing, setIsAdvancing] = useState(false);

  const totalQuestions = questions.length;
  const discoveredSources = Array.isArray(structured?.content_elements)
    ? (structured.content_elements as unknown[]).length
    : 0;
  const lastUpdated = structured?.pipeline_metadata?.last_updated;

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
      })),
    [questions]
  );

  return (
    <div className="panel content-discovery">
      <header className="panel-header panel-header--tight">
        <h1>Content Discovery</h1>
        {stage?.status === "completed" && (
          <button type="button" className="primary-button" onClick={handleAdvance} disabled={isAdvancing}>
            {isAdvancing ? "Advancing…" : "Next"}
          </button>
        )}
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
      </div>

      <section className="content-discovery__body">
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
