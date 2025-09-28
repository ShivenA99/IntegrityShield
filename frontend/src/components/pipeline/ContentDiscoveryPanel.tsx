import * as React from "react";
import { useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { formatDuration } from "@services/utils/formatters";

const ContentDiscoveryPanel: React.FC = () => {
  const { status, activeRunId, resumeFromStage } = usePipeline();
  const { questions } = useQuestions(activeRunId);
  const stage = status?.stages.find((item) => item.name === "content_discovery");
  const structured = (status?.structured_data as Record<string, unknown> | undefined) ?? {};
  const [isAdvancing, setIsAdvancing] = useState(false);
  const totalQuestions = questions.length;
  const discoveredSources = Array.isArray((structured as any)?.content_elements)
    ? ((structured as any).content_elements as unknown[]).length
    : 0;
  const lastUpdated = (structured as any)?.pipeline_metadata?.last_updated;

  const handleAdvance = async () => {
    if (!activeRunId) return;
    setIsAdvancing(true);
    try {
      await resumeFromStage(activeRunId, "smart_substitution");
    } finally {
      setIsAdvancing(false);
    }
  };

  return (
    <div className="panel content-discovery" style={{ display: 'grid', gap: '1.25rem' }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', margin: 0 }}>
        <span role="img" aria-hidden="true">🎯</span> Content Discovery
      </h2>
      <p style={{ margin: 0, color: 'var(--muted)' }}>Review detected questions, answer choices, and structural anchors.</p>

      <div className="info-grid">
        <div className="info-card">
          <span className="info-label">Stage status</span>
          <span className="info-value">{stage?.status ?? 'pending'}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Duration</span>
          <span className="info-value">{formatDuration(stage?.duration_ms)}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Questions detected</span>
          <span className="info-value">{totalQuestions}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Sources indexed</span>
          <span className="info-value">{discoveredSources}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Last updated</span>
          <span className="info-value">{lastUpdated ? new Date(lastUpdated).toLocaleString() : '—'}</span>
        </div>
      </div>

      {stage?.status === 'completed' ? (
        <div className="panel-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
          <div>
            <h4 style={{ margin: '0 0 0.4rem' }}>Next step</h4>
            <p style={{ margin: 0, color: 'var(--muted)' }}>Review question stems and configure mappings before continuing.</p>
          </div>
          <button
            type="button"
            className="pill-button"
            onClick={handleAdvance}
            disabled={isAdvancing}
            title="Continue to Smart Substitution"
          >
            {isAdvancing ? 'Advancing…' : 'Continue to Smart Substitution'}
          </button>
        </div>
      ) : null}

      <div className="panel-card">
        <h4 style={{ marginBottom: '0.5rem' }}>Detected Questions</h4>
        <p style={{ marginTop: 0, color: 'var(--muted)' }}>Preview of the first few questions for quick validation.</p>
        <ul className="content-list">
          {questions.slice(0, 6).map((question) => (
            <li key={question.id}>
              <strong>Q{question.question_number}</strong> — {question.question_type}{' '}
              {question.stem_text ? (
                <span style={{ color: 'var(--muted)' }}>
                  • {question.stem_text.slice(0, 90)}{question.stem_text.length > 90 ? '…' : ''}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
        {questions.length === 0 ? <p style={{ color: 'var(--muted)' }}>No questions detected yet.</p> : null}
      </div>
    </div>
  );
};

export default ContentDiscoveryPanel;
