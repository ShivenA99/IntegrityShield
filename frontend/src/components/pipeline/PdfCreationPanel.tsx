import * as React from "react";
import { useState, useCallback, useMemo, useEffect } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { ENHANCEMENT_METHOD_LABELS, ENHANCEMENT_METHOD_SUMMARY } from "@constants/enhancementMethods";
import type { AnswerSheetGenerationResult, DetectionReportResult } from "@services/types/pipeline";

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
  const { status, activeRunId, resumeFromStage, generateAnswerSheets, generateDetectionReport } = usePipeline();
  const [isDownloading, setIsDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isGeneratingSheets, setIsGeneratingSheets] = useState(false);
  const [showConfigPanel, setShowConfigPanel] = useState(false);
  const [generationResult, setGenerationResult] = useState<AnswerSheetGenerationResult | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [isGeneratingDetection, setIsGeneratingDetection] = useState(false);
  const [detectionResult, setDetectionResult] = useState<DetectionReportResult | null>(null);
  const [detectionError, setDetectionError] = useState<string | null>(null);

  type AnswerConfigState = {
    totalStudents: number;
    cheatingRatePercent: number;
    llmSharePercent: number;
    partialCopyMinPercent: number;
    partialCopyMaxPercent: number;
    fullCopyProbabilityPercent: number;
    paraphraseProbabilityPercent: number;
    writeParquet: boolean;
  };

  const [answerConfig, setAnswerConfig] = useState<AnswerConfigState>({
    totalStudents: 100,
    cheatingRatePercent: 35,
    llmSharePercent: 60,
    partialCopyMinPercent: 40,
    partialCopyMaxPercent: 75,
    fullCopyProbabilityPercent: 45,
    paraphraseProbabilityPercent: 65,
    writeParquet: false
  });

  const stage = status?.stages.find((item) => item.name === "pdf_creation");
  const runStatus = status?.status ?? "unknown";
  const parentRunId = (status as any)?.parent_run_id as string | undefined;
  const resumeTarget = (status as any)?.resume_target as string | undefined;
  const enhanced = (status?.structured_data as any)?.manipulation_results?.enhanced_pdfs || {};
  const originalDoc = (status?.structured_data as any)?.document;
  const detectionReportStructured = (status?.structured_data as any)?.manipulation_results?.detection_report;

  // Derive gating from presence-only mappings per question
  const structuredQuestions = (status?.structured_data as any)?.questions || [];
  const mappingSummary = useMemo(() => {
    return structuredQuestions.reduce(
      (acc: { ready: number; missing: number }, q: any) => {
        const mappings = (q?.manipulation?.substring_mappings) || (q?.substring_mappings) || [];
        const hasMapping = Array.isArray(mappings) && mappings.length > 0;
        if (hasMapping) {
          acc.ready += 1;
        } else {
          acc.missing += 1;
        }
        return acc;
      },
      { ready: 0, missing: 0 }
    );
  }, [structuredQuestions]);
  const readyCount = mappingSummary.ready;
  const hasReadyMappings = readyCount > 0;
  const allReady = structuredQuestions.length > 0 && readyCount === structuredQuestions.length;

  const entries = (Object.entries(enhanced) as [string, EnhancedPDF][])
    .filter(([method]) => method === "latex_dual_layer");

  const stageStatusMap = useMemo(() => {
    const map: Record<string, string> = {};
    (status?.stages ?? []).forEach((item) => {
      map[item.name] = item.status;
    });
    return map;
  }, [status?.stages]);

  const answerSheetPrereqsMet = ["smart_reading", "content_discovery", "smart_substitution"].every(
    (stageName) => stageStatusMap[stageName] === "completed"
  );

  const showAnswerSheetButton = Boolean(activeRunId && answerSheetPrereqsMet);
  const showDetectionReportButton = Boolean(activeRunId && answerSheetPrereqsMet);
  const detectionDownloadPath = normalizeReportPath(detectionResult?.output_files?.json || "");
  const detectionDownloadUrl =
    activeRunId && detectionDownloadPath ? buildDownloadUrl(activeRunId, detectionDownloadPath) : "";

  useEffect(() => {
    if (!detectionReportStructured) {
      if (!isGeneratingDetection) {
        setDetectionResult(null);
      }
      return;
    }

    const summary = detectionReportStructured.summary || {};
    const normalizedSummary = {
      total_questions: summary.total_questions ?? 0,
      questions_with_mappings: summary.questions_with_mappings ?? 0,
      questions_missing_mappings: summary.questions_missing_mappings ?? 0,
      validated_mappings: summary.validated_mappings ?? 0,
      total_mappings: summary.total_mappings ?? 0,
      high_risk_questions: summary.high_risk_questions ?? 0,
      target_label_distribution: Array.isArray(summary.target_label_distribution)
        ? summary.target_label_distribution
        : [],
    };

    const normalized: DetectionReportResult = {
      run_id: detectionReportStructured.run_id || activeRunId || "",
      generated_at:
        detectionReportStructured.generated_at ||
        detectionReportStructured.created_at ||
        "",
      summary: normalizedSummary,
      questions: Array.isArray(detectionReportStructured.questions)
        ? detectionReportStructured.questions
        : [],
      output_files: {
        json:
          detectionReportStructured.output_files?.json ||
          detectionReportStructured.relative_path ||
          (typeof detectionReportStructured.file_path === "string"
            ? detectionReportStructured.file_path
            : ""),
      },
    };

    setDetectionResult((prev) => {
      if (
        prev &&
        prev.generated_at === normalized.generated_at &&
        prev.output_files.json === normalized.output_files.json &&
        prev.questions.length === normalized.questions.length
      ) {
        return prev;
      }
      return normalized;
    });
    setDetectionError(null);
  }, [detectionReportStructured, activeRunId, isGeneratingDetection]);

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
  function normalizeReportPath(rawPath: string): string {
    if (!rawPath) return "";
    const unified = rawPath.replace(/\\/g, "/");
    if (unified.includes("/pipeline_runs/")) {
      const parts = unified.split("/pipeline_runs/");
      if (parts.length > 1) {
        return parts[1].split("/").slice(1).join("/");
      }
    }
    return unified;
  }
  const formatRiskLevel = (risk: string) =>
    (risk || "unknown")
      .replace(/[-_]/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  const getRiskColor = (risk: string) => {
    switch (risk) {
      case "critical":
        return "#ef4444";
      case "high":
        return "#f97316";
      case "medium":
        return "#facc15";
      case "needs-review":
        return "#fb923c";
      case "insufficient-data":
        return "var(--muted)";
      default:
        return "#38bdf8";
    }
  };
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
    if (!activeRunId || !hasReadyMappings) return;
    try {
      await resumeFromStage(activeRunId, 'pdf_creation', {
        targetStages: ['document_enhancement', 'pdf_creation', 'results_generation'],
      });
    } catch (error) {
      console.error('Failed to trigger PDF creation:', error);
    }
  }, [activeRunId, resumeFromStage, hasReadyMappings]);

  const updateConfig = useCallback(
    (patch: Partial<AnswerConfigState>) => {
      setAnswerConfig((prev) => ({ ...prev, ...patch }));
    },
    []
  );

  const handleGenerateSheets = useCallback(async () => {
    if (!activeRunId) return;
    setIsGeneratingSheets(true);
    setGenerationError(null);
    try {
      const clampPercent = (value: number) => Math.min(100, Math.max(0, value));
      const toFraction = (value: number) => clampPercent(value) / 100;

      const cheatingRate = toFraction(answerConfig.cheatingRatePercent);
      const llmRatio = toFraction(answerConfig.llmSharePercent);
      const peerRatio = Math.max(0, 1 - llmRatio);
      const partialMin = toFraction(answerConfig.partialCopyMinPercent);
      const partialMax = Math.max(partialMin, toFraction(answerConfig.partialCopyMaxPercent));
      const fullCopyProbability = toFraction(answerConfig.fullCopyProbabilityPercent);
      const paraphraseProbability = toFraction(answerConfig.paraphraseProbabilityPercent);

      const payload = {
        total_students: Math.max(1, Math.round(answerConfig.totalStudents)),
        cheating_rate: cheatingRate,
        cheating_breakdown: {
          llm: llmRatio,
          peer: peerRatio
        },
        copy_profile: {
          full_copy_probability: fullCopyProbability,
          partial_copy_min: partialMin,
          partial_copy_max: partialMax
        },
        paraphrase_probability: paraphraseProbability,
        write_parquet: answerConfig.writeParquet
      };

      const result = await generateAnswerSheets(activeRunId, payload);
      setGenerationResult(result);
      setShowConfigPanel(false);
    } catch (error: any) {
      console.error('Failed to generate answer sheets:', error);
      setGenerationError(error?.message || "Failed to generate answer sheets");
    } finally {
      setIsGeneratingSheets(false);
    }
  }, [activeRunId, answerConfig, generateAnswerSheets]);

  const handleGenerateDetectionReport = useCallback(async () => {
    if (!activeRunId) return;
    setIsGeneratingDetection(true);
    setDetectionError(null);
    try {
      const result = await generateDetectionReport(activeRunId);
      setDetectionResult(result);
    } catch (error: any) {
      console.error("Failed to generate detection report:", error);
      setDetectionError(error?.message || "Failed to generate detection report");
    } finally {
      setIsGeneratingDetection(false);
    }
  }, [activeRunId, generateDetectionReport]);

  const handleConfigSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void handleGenerateSheets();
    },
    [handleGenerateSheets]
  );

  return (
    <div className="panel pdf-creation">
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1rem'
      }}>
        <h2 style={{ margin: 0 }}>📑 Enhanced PDF Creation</h2>

        {stage?.status === 'pending' && hasReadyMappings && (
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
          <span className="info-label">Run status</span>
          <span className="info-value">{runStatus}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Stage status</span>
          <span className="info-value" style={{ color: getStatusColor(stage?.status || 'pending') }}>
            {stage?.status || 'pending'}
          </span>
        </div>
        <div className="info-card">
          <span className="info-label">Questions ready</span>
          <span className="info-value">{readyCount}/{structuredQuestions.length}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Enhanced PDFs</span>
          <span className="info-value">{entries.length}</span>
        </div>
        <div className="info-card">
          <span className="info-label">Duration</span>
          <span className="info-value">{stage?.duration_ms ? `${Math.round(stage.duration_ms / 1000)}s` : '—'}</span>
        </div>
        {showAnswerSheetButton ? (
          <div className="info-card" style={{ alignItems: 'flex-end', gap: 8 }}>
            <span className="info-label">Answer Sheets</span>
            <button
              onClick={() => setShowConfigPanel((prev) => !prev)}
              className="pill-button"
              style={{
                backgroundColor: 'rgba(52,211,153,0.25)',
                color: 'var(--text)',
                padding: '8px 16px',
                border: 'none',
                fontWeight: 600,
                cursor: 'pointer'
              }}
              disabled={isGeneratingSheets}
              title="Configure distributions and generate simulated answer sheets"
            >
              {isGeneratingSheets ? 'Generating…' : showConfigPanel ? 'Close Answer Sheet Config' : 'Generate Answer Sheets'}
            </button>
            {generationResult && !showConfigPanel && !isGeneratingSheets && (
              <span style={{ fontSize: '0.8em', color: 'var(--muted)', textAlign: 'right' }}>
                Answer sheets generated • {generationResult.students} students
              </span>
            )}
          </div>
        ) : null}
        {showDetectionReportButton ? (
          <div className="info-card" style={{ alignItems: 'flex-end', gap: 8 }}>
            <span className="info-label">Detection Report</span>
            <button
              onClick={handleGenerateDetectionReport}
              className="pill-button"
              style={{
                backgroundColor: 'rgba(59,130,246,0.25)',
                color: 'var(--text)',
                padding: '8px 16px',
                border: 'none',
                fontWeight: 600,
                cursor: 'pointer'
              }}
              disabled={isGeneratingDetection}
              title="Generate the per-question cheating detection report"
            >
              {isGeneratingDetection ? 'Generating…' : detectionResult ? 'Regenerate Detection Report' : 'Generate Detection Report'}
            </button>
            {detectionResult && !isGeneratingDetection && (
              <span style={{ fontSize: '0.8em', color: 'var(--muted)', textAlign: 'right' }}>
                High risk questions: {detectionResult.summary.high_risk_questions}/{detectionResult.summary.total_questions}
              </span>
            )}
          </div>
        ) : null}
        {parentRunId ? (
          <div className="info-card">
            <span className="info-label">Parent run</span>
            <span className="info-value" style={{ fontFamily: 'monospace' }}>
              {parentRunId.slice(0, 8)}
            </span>
          </div>
        ) : null}
        {resumeTarget ? (
          <div className="info-card">
            <span className="info-label">Resume target</span>
            <span className="info-value">{resumeTarget}</span>
          </div>
        ) : null}
      </div>

      {runStatus === 'paused' && resumeTarget === 'pdf_creation' && (
        <div className="panel-card" style={{ marginBottom: '1rem', background: 'rgba(56,189,248,0.08)' }}>
          <p style={{ margin: 0 }}>
            This run is paused and ready for PDF creation. Validate any remaining mappings, then launch the dual-layer render.
          </p>
        </div>
      )}

      {stage?.status === 'pending' && hasReadyMappings && !allReady && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ color: '#facc15', fontSize: '0.9em', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span role="img" aria-label="warning">⚠️</span>
            {mappingSummary.missing} question{mappingSummary.missing === 1 ? '' : 's'} have no validated mapping and will be skipped in the dual-layer attack.
          </p>
        </div>
      )}

      {stage?.status === 'pending' && !hasReadyMappings && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ color: 'var(--muted)', fontSize: '0.9em' }}>
            Generate mappings with GPT-5 and validate at least one question before creating the enhanced PDF.
          </p>
        </div>
      )}

      {showConfigPanel && (
        <div className="panel-card" style={{ marginBottom: '1rem', background: 'rgba(52,211,153,0.12)' }}>
          <h4 style={{ marginTop: 0 }}>Answer Sheet Simulation</h4>
          <p style={{ marginTop: 0, color: 'var(--muted)' }}>
            Adjust how simulated students behave. Percentages should be provided on a 0-100 scale.
          </p>
          <form onSubmit={handleConfigSubmit} style={{ display: 'grid', gap: 16 }}>
            <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Total students</span>
                <input
                  type="number"
                  min={10}
                  max={1000}
                  step={10}
                  value={answerConfig.totalStudents}
                  onChange={(event) => updateConfig({ totalStudents: Number(event.target.value) || 100 })}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Cheating students (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={answerConfig.cheatingRatePercent}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    updateConfig({ cheatingRatePercent: Number.isNaN(value) ? answerConfig.cheatingRatePercent : value });
                  }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Cheaters using LLM (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={answerConfig.llmSharePercent}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    updateConfig({ llmSharePercent: Number.isNaN(value) ? answerConfig.llmSharePercent : value });
                  }}
                />
                <span style={{ fontSize: '0.75em', color: 'var(--muted)' }}>
                  Peer copying share: {Math.max(0, Math.min(100, 100 - answerConfig.llmSharePercent))}%
                </span>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Partial copy minimum (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={answerConfig.partialCopyMinPercent}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    updateConfig({
                      partialCopyMinPercent: Number.isNaN(value) ? answerConfig.partialCopyMinPercent : value
                    });
                  }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Partial copy maximum (%)</span>
                <input
                  type="number"
                  min={answerConfig.partialCopyMinPercent}
                  max={100}
                  step={5}
                  value={answerConfig.partialCopyMaxPercent}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    updateConfig({
                      partialCopyMaxPercent: Number.isNaN(value) ? answerConfig.partialCopyMaxPercent : value
                    });
                  }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Full-copy probability (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={answerConfig.fullCopyProbabilityPercent}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    updateConfig({
                      fullCopyProbabilityPercent: Number.isNaN(value) ? answerConfig.fullCopyProbabilityPercent : value
                    });
                  }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span>Paraphrasing probability (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={answerConfig.paraphraseProbabilityPercent}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    updateConfig({
                      paraphraseProbabilityPercent: Number.isNaN(value)
                        ? answerConfig.paraphraseProbabilityPercent
                        : value
                    });
                  }}
                />
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 22 }}>
                <input
                  type="checkbox"
                  checked={answerConfig.writeParquet}
                  onChange={(event) => updateConfig({ writeParquet: event.target.checked })}
                />
                <span>Write Parquet artifact</span>
              </label>
            </div>
            {generationError && (
              <div
                style={{
                  background: 'rgba(239,68,68,0.2)',
                  border: '1px solid rgba(239,68,68,0.35)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  color: '#fca5a5'
                }}
              >
                {generationError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                type="submit"
                className="pill-button"
                style={{ backgroundColor: '#34d399', color: 'white', padding: '8px 18px' }}
                disabled={isGeneratingSheets}
              >
                {isGeneratingSheets ? 'Generating…' : 'Generate Answer Sheets'}
              </button>
              <button
                type="button"
                className="pill-button"
                style={{ backgroundColor: 'transparent', color: 'var(--muted)', border: '1px solid rgba(148,163,184,0.3)' }}
                onClick={() => setShowConfigPanel(false)}
                disabled={isGeneratingSheets}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {generationResult && !showConfigPanel && (
        <div
          className="panel-card"
          style={{
            marginBottom: '1rem',
            background: 'rgba(34,197,94,0.12)',
            border: '1px solid rgba(34,197,94,0.35)'
          }}
        >
          <strong>Answer sheets generated.</strong>{" "}
          {generationResult.students} students, {generationResult.cheating_counts.total} flagged as cheating (LLM{" "}
          {generationResult.cheating_counts.llm}, Peer {generationResult.cheating_counts.peer}).
          <div style={{ marginTop: 8, fontFamily: 'monospace', fontSize: '0.85em', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span>JSON: {generationResult.output_files.json}</span>
            <span>Summary: {generationResult.output_files.summary}</span>
            {generationResult.output_files.parquet ? (
              <span>Parquet: {generationResult.output_files.parquet}</span>
            ) : (
              <span style={{ color: 'var(--muted)' }}>Parquet: not generated</span>
            )}
          </div>
        </div>
      )}

      {detectionError && (
        <div
          style={{
            background: "rgba(239,68,68,0.2)",
            border: "1px solid rgba(239,68,68,0.35)",
            borderRadius: 8,
            padding: "8px 12px",
            color: "#fecaca",
            marginBottom: "1rem",
          }}
        >
          {detectionError}
        </div>
      )}

      {detectionResult && (
        <div
          className="panel-card"
          style={{
            marginBottom: "1rem",
            background: "rgba(59,130,246,0.12)",
            border: "1px solid rgba(59,130,246,0.35)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
            }}
          >
            <div>
              <strong>Detection report generated.</strong>{" "}
              {detectionResult.summary.total_questions} questions analyzed.
              <div style={{ fontSize: "0.8em", color: "var(--muted)" }}>
                Generated:{" "}
                {detectionResult.generated_at
                  ? new Date(detectionResult.generated_at).toLocaleString()
                  : "—"}
              </div>
            </div>
            {detectionDownloadUrl ? (
              <a
                href={detectionDownloadUrl}
                download
                style={{
                  backgroundColor: "#3b82f6",
                  color: "white",
                  textDecoration: "none",
                  padding: "8px 16px",
                  borderRadius: "4px",
                  fontSize: "0.85em",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                📄 Download JSON
              </a>
            ) : null}
          </div>

          <div
            style={{
              marginTop: 12,
              display: "flex",
              flexWrap: "wrap",
              gap: 16,
              fontSize: "0.85em",
              color: "var(--text)",
            }}
          >
            <div>
              <strong>Validated mappings:</strong>{" "}
              {detectionResult.summary.validated_mappings}/
              {detectionResult.summary.total_mappings}
            </div>
            <div>
              <strong>Questions w/ mappings:</strong>{" "}
              {detectionResult.summary.questions_with_mappings}/
              {detectionResult.summary.total_questions}
            </div>
            <div>
              <strong>High risk:</strong>{" "}
              {detectionResult.summary.high_risk_questions}
            </div>
          </div>

          {detectionResult.summary.target_label_distribution.length ? (
            <div style={{ marginTop: 8, fontSize: "0.8em", color: "var(--muted)" }}>
              Target labels:&nbsp;
              {detectionResult.summary.target_label_distribution
                .map((item) => `${item.label} (${item.count})`)
                .join(", ")}
            </div>
          ) : null}

          <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
            {detectionResult.questions.map((question) => {
              const targetLabels = question.target_answer.labels.filter(Boolean).join(", ");
              const targetTexts = question.target_answer.texts.filter(Boolean).join("; ");
              const replacementFallback = (question.target_answer.raw_replacements || []).filter(Boolean).join(", ");
              const riskLevelLabel = formatRiskLevel(question.risk_level);
              const riskColor = getRiskColor(question.risk_level);
              const riskTextColor = question.risk_level === "insufficient-data" ? "var(--text)" : "#0f172a";
              return (
                <details
                  key={question.question_number}
                  style={{
                    background: "rgba(15,23,42,0.45)",
                    border: "1px solid rgba(148,163,184,0.18)",
                    borderRadius: 6,
                    padding: 12,
                  }}
                >
                  <summary
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 12,
                      cursor: "pointer",
                      listStyle: "none",
                    }}
                  >
                    <span style={{ fontWeight: 600, color: "var(--text)" }}>
                      Q{question.question_number}: {question.stem_text}
                    </span>
                    <span
                      style={{
                        backgroundColor: riskColor,
                        color: riskTextColor,
                        padding: "2px 10px",
                        borderRadius: 999,
                        fontSize: "0.75em",
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                      }}
                    >
                      {riskLevelLabel}
                    </span>
                  </summary>

                  <div style={{ marginTop: 10, display: "grid", gap: 8, fontSize: "0.85em" }}>
                    {question.options && question.options.length > 0 ? (
                      <div>
                        <strong>Options:</strong>
                        <ul style={{ margin: "6px 0 0 18px", padding: 0, listStyle: "disc" }}>
                          {question.options.map((option) => (
                            <li key={`${question.question_number}-${option.label}`}>
                              <span style={{ fontFamily: "monospace" }}>{option.label}</span>
                              {option.text ? ` — ${option.text}` : ""}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {question.is_subjective ? (
                      <div>
                        <strong>Subjective reference:</strong>{" "}
                        {question.subjective_reference_answer || "—"}
                      </div>
                    ) : null}

                    <div>
                      <strong>Gold answer:</strong>{" "}
                      {question.gold_answer.label
                        ? `${question.gold_answer.label}${question.gold_answer.text ? ` — ${question.gold_answer.text}` : ""}`
                        : question.gold_answer.text || "—"}
                    </div>

                    <div>
                      <strong>Target answer:</strong>{" "}
                      {targetLabels || targetTexts
                        ? [targetLabels, targetTexts && `(${targetTexts})`].filter(Boolean).join(" ")
                        : replacementFallback || "—"}
                    </div>

                    <div>
                      <strong>Mappings:</strong>
                      {question.mappings.length ? (
                        <ul style={{ margin: "6px 0 0 18px", padding: 0, listStyle: "disc" }}>
                          {question.mappings.map((mapping, index) => (
                            <li key={`${question.question_number}-mapping-${index}`}>
                              <code>{mapping.original || "—"}</code> →{" "}
                              <code>{mapping.replacement || "—"}</code>
                              {mapping.validated ? (
                                <span style={{ color: "#34d399", marginLeft: 8 }}>validated</span>
                              ) : (
                                <span style={{ color: "#facc15", marginLeft: 8 }}>needs review</span>
                              )}
                              {mapping.context ? ` · ${mapping.context}` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span style={{ color: "var(--muted)" }}>No mappings recorded</span>
                      )}
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
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
