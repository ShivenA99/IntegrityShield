import React from "react";

import { usePipeline } from "@hooks/usePipeline";

const ResultsPanel: React.FC = () => {
  const { status } = usePipeline();
  const runId = status?.run_id;
  const structured = (status?.structured_data as Record<string, unknown> | undefined) ?? {};
  const manipulationResults = (structured as any).manipulation_results ?? {};
  const summary = manipulationResults.effectiveness_summary ?? {};
  const comprehensive = manipulationResults.comprehensive_metrics ?? {};
  const artifacts: Record<string, Record<string, string>> = manipulationResults.artifacts ?? {};
  const enhancedPdfs: Record<string, any> = manipulationResults.enhanced_pdfs ?? {};
  const filteredEnhancedEntries = Object.entries(enhancedPdfs).filter(
    ([method]) => method === "content_stream_span_overlay",
  );

  const reportPaths = (structured as any)?.pipeline_metadata?.report_paths || {};
  const questionCoverage = summary.total_questions ? Math.round((summary.questions_successfully_manipulated ?? 0) / summary.total_questions * 100) : null;

  return (
    <div className="panel results" style={{ display: 'grid', gap: '1.5rem' }}>
      <div>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', margin: 0 }}>
          <span role="img" aria-hidden="true">📈</span>
          Evaluation & Reports
        </h2>
        <p style={{ margin: 0, color: 'var(--muted)' }}>Review aggregated metrics and download deliverables for this run.</p>
      </div>

      <div className="info-grid">
        <div className="info-card">
          <span className="info-label">Questions manipulated</span>
          <span className="info-value">{summary.questions_successfully_manipulated ?? '—'}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Total questions</span>
          <span className="info-value">{summary.total_questions ?? '—'}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Coverage</span>
          <span className="info-value">{questionCoverage != null ? `${questionCoverage}%` : '—'}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Preferred method</span>
          <span className="info-value">{summary.recommended_for_deployment ?? '—'}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Overall duration</span>
          <span className="info-value">{comprehensive?.overall_duration_ms ? `${Math.round(comprehensive.overall_duration_ms / 1000)}s` : '—'}</span>
        </div>
      </div>

      <div className="panel-card" style={{ display: 'grid', gap: '0.75rem' }}>
        <h4 style={{ margin: 0 }}>Final Reports</h4>
        <p style={{ marginTop: 0, color: 'var(--muted)' }}>Download generated summaries and detailed analysis for archival review.</p>
        <div className="download-row">
          {runId && reportPaths?.analysis ? (
            <a className="pill-button" href={`/api/files/${runId}/analysis_report.pdf`} download title="Download the consolidated analysis report">
              📄 Analysis Report
            </a>
          ) : null}
          {runId && reportPaths?.dashboard ? (
            <a className="pill-button" href={`/api/files/${runId}/results_dashboard.pdf`} download title="Download the PDF dashboard">
              📊 Dashboard PDF
            </a>
          ) : null}
          {runId && reportPaths?.developer ? (
            <a className="pill-button" href={`/api/files/${runId}/developer_debug.json`} download title="Download JSON debug bundle">
              🧪 Developer JSON
            </a>
          ) : null}
          {!runId && <span style={{ color: 'var(--muted)' }}>Reports will appear here once generated.</span>}
        </div>
      </div>

      <div className="panel-card" style={{ display: 'grid', gap: '0.75rem' }}>
        <h4 style={{ margin: 0 }}>Enhanced PDFs</h4>
        <p style={{ marginTop: 0, color: 'var(--muted)' }}>Download final overlays and intermediate artifacts for each rendering path.</p>
        {filteredEnhancedEntries.length === 0 ? (
          <p style={{ color: 'var(--muted)' }}>No enhanced PDFs have been generated yet.</p>
        ) : (
          <div className="download-grid">
            {filteredEnhancedEntries.map(([method, meta]) => {
              const friendly = method.replace(/_/g, ' ');
              const artifactSet = artifacts[method] || {};
              return (
                <div key={method} className="download-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h5 style={{ margin: 0, color: 'var(--text)' }}>{friendly}</h5>
                    <span className="badge tag-muted">{meta.effectiveness_score != null ? `${Math.round(meta.effectiveness_score * 100)}%` : '—'}</span>
                  </div>

                  {/* PDF Preview */}
                  {artifactSet.final && runId ? (
                    <div style={{ marginTop: '0.75rem', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
                      <iframe
                        src={`/api/files/${runId}/${artifactSet.final}`}
                        style={{ width: '100%', height: '400px', border: 'none', display: 'block' }}
                        title={`${friendly} preview`}
                      />
                    </div>
                  ) : null}

                  {/* Stats */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '0.5rem', marginTop: '0.75rem' }}>
                    {meta.replacements != null && (
                      <div style={{ fontSize: '0.85rem' }}>
                        <span style={{ color: 'var(--muted)' }}>Replacements: </span>
                        <span style={{ fontWeight: 500 }}>{meta.replacements}</span>
                      </div>
                    )}
                    {meta.overlay_applied != null && (
                      <div style={{ fontSize: '0.85rem' }}>
                        <span style={{ color: 'var(--muted)' }}>Overlays: </span>
                        <span style={{ fontWeight: 500 }}>{meta.overlay_applied}/{meta.overlay_targets ?? 0}</span>
                      </div>
                    )}
                    {meta.file_size_bytes != null && (
                      <div style={{ fontSize: '0.85rem' }}>
                        <span style={{ color: 'var(--muted)' }}>Size: </span>
                        <span style={{ fontWeight: 500 }}>{Math.round(meta.file_size_bytes / 1024)}KB</span>
                      </div>
                    )}
                  </div>

                  {/* Download Buttons */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.75rem' }}>
                    {artifactSet.final && runId ? (
                      <a className="pill-button" href={`/api/files/${runId}/${artifactSet.final}`} download title="Download final overlay">
                        📄 Final PDF
                      </a>
                    ) : null}
                    {Object.entries(artifactSet)
                      .filter(([stage]) => stage !== 'final')
                      .map(([stage, relPath]) => (
                        runId ? (
                          <a
                            key={`${method}-${stage}`}
                            className="pill-button"
                            href={`/api/files/${runId}/${relPath}`}
                            download
                            title={`Download ${stage} artifact`}
                          >
                            🧩 {stage.replace(/_/g, ' ')}
                          </a>
                        ) : null
                      ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultsPanel;
