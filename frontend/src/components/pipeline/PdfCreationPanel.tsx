import * as React from "react";
import { useState, useCallback } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { ENHANCEMENT_METHOD_LABELS, ENHANCEMENT_METHOD_SUMMARY } from "@constants/enhancementMethods";

interface EnhancedPDF {
  path?: string;
  file_path?: string;
  relative_path?: string;
  size_bytes?: number;
  file_size_bytes?: number;
  effectiveness_score?: number;
  visual_quality_score?: number;
  created_at?: string;
  validation_results?: any;
  render_stats?: Record<string, unknown>;
}

const stageLabels: Record<string, string> = {
  after_redaction: "After redaction",
  after_rewrite: "After rewrite",
  after_stream_rewrite: "After stream rewrite",
  final: "Final overlay",
};

const buildDownloadUrl = (runId: string, relativePath: string) => {
  const segments = relativePath.split(/[\\/]+/).filter(Boolean).map(encodeURIComponent);
  return `/api/files/${runId}/${segments.join('/')}`;
};

const PdfCreationPanel: React.FC = () => {
  const { status, activeRunId, resumeFromStage } = usePipeline();
  const [isDownloading, setIsDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const stage = status?.stages.find((item) => item.name === "pdf_creation");
  const enhanced = (status?.structured_data as any)?.manipulation_results?.enhanced_pdfs || {};
  const originalDoc = (status?.structured_data as any)?.document;

  // Derive gating from presence-only mappings per question
  const structuredQuestions = (status?.structured_data as any)?.questions || [];
  const validatedCount = React.useMemo(() => {
    return structuredQuestions.reduce((acc: number, q: any) => {
      const mappings = (q?.manipulation?.substring_mappings) || (q?.substring_mappings) || [];
      const hasMapping = Array.isArray(mappings) && mappings.length > 0;
      return acc + (hasMapping ? 1 : 0);
    }, 0);
  }, [structuredQuestions]);
  const allValidated = structuredQuestions.length > 0 && validatedCount === structuredQuestions.length;

  const entries = (Object.entries(enhanced) as [string, EnhancedPDF][])
    .filter(([method]) => method === "latex_dual_layer");

  const formatFileSize = (bytes: number) => {
    if (!bytes) return "";
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#34d399';
      case 'running': return '#007bff';
      case 'failed': return '#dc3545';
      default: return 'var(--muted)';
    }
  };

  const resolvePath = (meta: EnhancedPDF) => meta.path || meta.file_path || "";
  const resolveRelativePath = (meta: EnhancedPDF) => {
    const rawPath = meta.relative_path || meta.path || meta.file_path || "";

    // If path is absolute, extract relative part
    if (rawPath.includes('/pipeline_runs/')) {
      const parts = rawPath.split('/pipeline_runs/');
      if (parts.length > 1) {
        // Remove run_id from path since URL already has it
        const afterRunId = parts[1].split('/').slice(1).join('/');
        return afterRunId;
      }
    }

    return rawPath;
  };
  const resolveSize = (meta: EnhancedPDF) => (meta.size_bytes ?? meta.file_size_bytes ?? 0);
  const methodLabel = (method: string) =>
    (ENHANCEMENT_METHOD_LABELS as Record<string, string>)[method] || method.replace(/_/g, " ");
  const methodSummary = (method: string) =>
    (ENHANCEMENT_METHOD_SUMMARY as Record<string, string>)[method] || "";

  const handleDownload = useCallback(async (method: string, meta: EnhancedPDF, displayName?: string, overrideRelativePath?: string) => {
    if (!activeRunId) return;

    const relativeTarget = overrideRelativePath || resolveRelativePath(meta);
    if (!relativeTarget) return;

    setIsDownloading(method);
    setDownloadError(null);

    try {
      const downloadUrl = buildDownloadUrl(activeRunId, relativeTarget);
      const friendlyRaw = displayName || methodLabel(method) || method || "enhanced";
      const safeFriendly = friendlyRaw
        .toString()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');

      const response = await fetch(downloadUrl);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status} ${response.statusText}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      const filenameHint = relativeTarget.split(/[\\/]+/).pop() || method || 'enhanced';
      a.download = `${safeFriendly || method}_${filenameHint}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download error:', error);
      setDownloadError(`Failed to download ${method}: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsDownloading(null);
    }
  }, [activeRunId, methodLabel, resolveRelativePath]);

  const handleCreatePdf = useCallback(async () => {
    if (!activeRunId || !allValidated) return;
    try {
      await resumeFromStage(activeRunId, 'pdf_creation');
    } catch (error) {
      console.error('Failed to trigger PDF creation:', error);
    }
  }, [activeRunId, resumeFromStage, allValidated]);

  const onEvaluate = () => {
    if (activeRunId) {
      resumeFromStage(activeRunId, 'results_generation');
    }
  };

  return (
    <div className="panel pdf-creation">
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1rem'
      }}>
        <h2 style={{ margin: 0 }}>📑 Enhanced PDF Creation</h2>

        {stage?.status === 'pending' && allValidated && (
          <button
            onClick={handleCreatePdf}
            className="pill-button"
            style={{
              backgroundColor: 'rgba(56,189,248,0.3)',
              color: 'var(--text)',
              padding: '8px 16px'
            }}
          >
            🚀 Create Enhanced PDF
          </button>
        )}
      </div>

      <div className="info-grid" style={{ marginBottom: '1rem' }}>
        <div className="info-card">
          <span className="info-label">Stage status</span>
          <span className="info-value" style={{ color: getStatusColor(stage?.status || 'pending') }}>
            {stage?.status || 'pending'}
          </span>
        </div>
        <div className="info-card">
          <span className="info-label">Questions ready</span>
          <span className="info-value">{validatedCount}/{structuredQuestions.length}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Enhanced PDFs</span>
          <span className="info-value">{entries.length}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Duration</span>
          <span className="info-value">{stage?.duration_ms ? `${Math.round(stage.duration_ms / 1000)}s` : '—'}</span>
        </div>
      </div>

      {stage?.status === 'pending' && !allValidated && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ color: 'var(--muted)', fontSize: '0.9em' }}>
            Add at least one mapping per question to enable PDF creation.
          </p>
        </div>
      )}

      {downloadError && (
        <div style={{
          backgroundColor: 'rgba(248,113,113,0.15)',
          border: '1px solid rgba(248,113,113,0.35)',
          color: 'var(--muted)',
          padding: 12,
          borderRadius: 10,
          marginBottom: 16
        }}>
          <strong>Download Error:</strong> {downloadError}
        </div>
      )}

      {entries.length > 0 && (
        <div className="panel-card">
          <h4>Generated Files ({entries.length})</h4>
          <div style={{ display: 'grid', gap: 12 }}>
            {entries.map(([method, meta]) => {
              const relativePath = resolveRelativePath(meta);
              const size = resolveSize(meta);
              const previewUrl = activeRunId && relativePath ? buildDownloadUrl(activeRunId as string, relativePath) : "";
              const label = methodLabel(method);
              const summary = methodSummary(method);
              const stats = (meta.render_stats as Record<string, any>) || {};
              const replacements = stats.replacements ?? meta.replacements;
              const overlayApplied = stats.overlay_applied ?? meta.overlay_applied;
              const overlayTargets = stats.overlay_targets ?? meta.overlay_targets;
              const overlayPct = stats.overlay_area_pct ?? meta.overlay_area_pct;
              const stageArtifacts = (stats.artifact_rel_paths as Record<string, string>) || (stats.artifacts as Record<string, string>) || {};
              return (
                <div key={method} style={{
                  border: '1px solid rgba(148,163,184,0.18)',
                  borderRadius: '4px',
                  padding: 16,
                  backgroundColor: 'rgba(15, 23, 42, 0.45)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 8 }}>
                    <div>
                      <h5 style={{ margin: '0 0 4px 0', color: 'var(--text)' }}>{label}</h5>
                      {summary && (
                        <div style={{ fontSize: '0.8em', color: 'var(--muted)', maxWidth: 520 }}>
                          {summary}
                        </div>
                      )}
                      <div style={{ fontSize: '0.9em', color: 'var(--muted)' }}>
                        {size ? <>Size: {formatFileSize(size)}</> : null}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDownload(method, meta, label)}
                      disabled={isDownloading === method || !relativePath}
                      style={{
                        backgroundColor: isDownloading === method ? 'rgba(148,163,184,0.18)' : '#34d399',
                        color: isDownloading === method ? 'var(--muted)' : 'white',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: '4px',
                        cursor: isDownloading === method ? 'not-allowed' : 'pointer',
                        fontSize: '0.875em'
                      }}
                      title="Download the final enhanced PDF"
                    >
                      {isDownloading === method ? '⬇️ Downloading...' : '📥 Download'}
                    </button>
                    {Object.entries(stageArtifacts)
                      .filter(([stage]) => stage !== 'final')
                      .length > 0 && (
                      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {Object.entries(stageArtifacts)
                          .filter(([stage]) => stage !== 'final')
                          .map(([stage, relPath]) => (
                            <button
                              key={`${method}-${stage}`}
                              onClick={() => handleDownload(method, meta, `${label} ${stageLabels[stage] || stage}`, relPath)}
                              style={{
                                backgroundColor: 'var(--muted)',
                                color: 'var(--text)',
                                border: 'none',
                                padding: '6px 10px',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                fontSize: '0.8em'
                              }}
                              title={`Download snapshot: ${stageLabels[stage] || stage}`}
                            >
                              {stageLabels[stage] || stage}
                            </button>
                          ))}
                      </div>
                    )}
                  </div>

                  {previewUrl && (
                    <div style={{ marginTop: 8 }}>
                      <iframe title={`preview-${method}`} src={previewUrl} style={{ width: '100%', height: 420, border: 0 }} />
                    </div>
                  )}

                  {(replacements != null || overlayApplied != null) && (
                    <div style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 12,
                      marginTop: 12,
                      fontSize: '0.85em',
                      color: 'var(--text)'
                    }}>
                      {replacements != null && (
                        <div>
                          <strong>Replacements:</strong> {replacements}
                        </div>
                      )}
                      {overlayApplied != null && (
                        <div>
                          <strong>Overlays:</strong> {overlayApplied}
                          {overlayTargets != null ? ` / ${overlayTargets}` : ""}
                        </div>
                      )}
                      {overlayPct != null && typeof overlayPct === 'number' && overlayPct > 0 && (
                        <div>
                          <strong>Overlay area:</strong> {(overlayPct * 100).toFixed(2)}%
                        </div>
                      )}
                    </div>
                  )}

                  {(meta.effectiveness_score != null || meta.visual_quality_score != null) && (
                    <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                      {meta.effectiveness_score != null && (
                        <div style={{ fontSize: '0.85em' }}>
                          <span style={{ color: 'var(--muted)' }}>Effectiveness:</span>{' '}
                          <span style={{
                            color: meta.effectiveness_score > 0.7 ? '#34d399' :
                                  meta.effectiveness_score > 0.4 ? 'var(--warning)' : '#ef4444',
                            fontWeight: 'bold'
                          }}>
                            {Math.round(meta.effectiveness_score * 100)}%
                          </span>
                        </div>
                      )}
                      {meta.visual_quality_score != null && (
                        <div style={{ fontSize: '0.85em' }}>
                          <span style={{ color: 'var(--muted)' }}>Visual Quality:</span>{' '}
                          <span style={{
                            color: meta.visual_quality_score > 0.7 ? '#34d399' :
                                  meta.visual_quality_score > 0.4 ? 'var(--warning)' : '#ef4444',
                            fontWeight: 'bold'
                          }}>
                            {Math.round(meta.visual_quality_score * 100)}%
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {meta.created_at && (
                    <div style={{ fontSize: '0.8em', color: 'var(--muted)' }}>
                      Created: {new Date(meta.created_at).toLocaleString()}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            {/* Eval button disabled for now */}
            {originalDoc?.filename && activeRunId && (
              <a
                href={`/api/files/${activeRunId}/${originalDoc.filename}`}
                download
                style={{
                  backgroundColor: 'var(--muted)',
                  color: 'var(--text)',
                  textDecoration: 'none',
                  padding: '8px 16px',
                  borderRadius: '4px',
                  fontSize: '0.875em'
                }}
              >
                📄 Download Original
              </a>
            )}
          </div>
        </div>
      )}

      <style>
        {`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}
      </style>
    </div>
  );
};

export default PdfCreationPanel;
