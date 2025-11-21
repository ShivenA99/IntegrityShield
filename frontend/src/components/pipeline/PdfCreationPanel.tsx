import * as React from "react";
import { useState, useCallback, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FileBarChart2, LineChart } from "lucide-react";

import { usePipeline } from "@hooks/usePipeline";
import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";

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
  replacements?: number;
  overlay_applied?: number;
  overlay_targets?: number;
  overlay_area_pct?: number;
  prompt_count?: number;
}

const LATEX_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
] as const;
const LATEX_METHOD_SET = new Set<string>(LATEX_METHODS);
const HIDDEN_METHODS = new Set<string>(["redaction_rewrite_overlay", "pymupdf_overlay"]);

const stageLabels: Record<string, string> = {
  after_redaction: "After redaction",
  after_rewrite: "After rewrite",
  after_stream_rewrite: "After stream rewrite",
  final: "Final overlay",
};

const buildDownloadUrl = (runId: string, relativePath: string) => {
  const segments = relativePath.split(/[\\/]+/).filter(Boolean).map(encodeURIComponent);
  return `/api/files/${runId}/${segments.join("/")}`;
};

const PdfCreationPanel: React.FC = () => {
  const {
    status,
    activeRunId,
    resumeFromStage,
    refreshStatus,
    setPreferredStage,
    generateDetectionReport,
    generateEvaluationReport
  } = usePipeline();
  const navigate = useNavigate();
  const [isDownloading, setIsDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isQueuing, setIsQueuing] = useState(false);
  const [queueMessage, setQueueMessage] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [hasQueuedPdf, setHasQueuedPdf] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [reportMessage, setReportMessage] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportDownloadPath, setReportDownloadPath] = useState<string | null>(null);
  const [reportGeneratedAt, setReportGeneratedAt] = useState<string | null>(null);
  const [evaluationState, setEvaluationState] = useState<
    Record<string, { isLoading: boolean; message?: string | null; error?: string | null }>
  >({});
  const [autoDetectionRequested, setAutoDetectionRequested] = useState(false);

  const stage = status?.stages.find((item) => item.name === "pdf_creation");
  const substitutionStage = status?.stages.find((item) => item.name === "smart_substitution");
  const runStatus = status?.status ?? "unknown";
  const enhanced = (status?.structured_data as any)?.manipulation_results?.enhanced_pdfs || {};
  const structuredData = (status?.structured_data as Record<string, any>) || null;
  const structuredQuestions = (structuredData?.questions as any[]) || [];
  const reports = (structuredData?.reports as Record<string, any>) || {};
  const evaluationReports = (reports?.evaluation as Record<string, any>) || {};
  const runId = status?.run_id ?? activeRunId ?? null;
  const detectionReportInfo = useMemo(() => {
    if (!structuredData) return null;
    const manipulationResults = (structuredData.manipulation_results as Record<string, any>) || {};
    const detectionReport = (manipulationResults?.detection_report as Record<string, any>) || null;
    const artifacts = (manipulationResults?.artifacts as Record<string, any>) || {};
    const artifactPath =
      (artifacts?.detection_report?.json as string) ||
      (detectionReport?.relative_path as string) ||
      (detectionReport?.output_files?.json as string) ||
      null;
    const generatedAt = (detectionReport?.generated_at as string) || null;
    if (!artifactPath && !generatedAt) {
      return null;
    }
    return {
      relativePath: artifactPath,
      generatedAt,
    };
  }, [structuredData]);
  const latestReportPath = reportDownloadPath || detectionReportInfo?.relativePath || null;
  const latestReportTimestamp = reportGeneratedAt || detectionReportInfo?.generatedAt || null;
  const formattedReportTimestamp = useMemo(() => {
    if (!latestReportTimestamp) return null;
    try {
      return new Date(latestReportTimestamp).toLocaleString();
    } catch {
      return latestReportTimestamp;
    }
  }, [latestReportTimestamp]);

  const configuredEnhancements = useMemo(() => {
    const raw = status?.pipeline_config?.enhancement_methods;
    if (Array.isArray(raw)) {
      return raw.map((entry) => String(entry));
    }
    return [];
  }, [status?.pipeline_config]);

  const selectedLatexMethods = useMemo(() => {
    const selected = configuredEnhancements.filter((method) => LATEX_METHOD_SET.has(method));
    return selected.length ? selected : ["latex_dual_layer"];
  }, [configuredEnhancements]);

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

  const entries = useMemo(() => {
    const available = new Map(
      (Object.entries(enhanced) as [string, EnhancedPDF][])
        .filter(([method]) => !HIDDEN_METHODS.has(method))
    );
    const order: string[] = [];
    selectedLatexMethods.forEach((method) => {
      if (!order.includes(method)) {
        order.push(method);
      }
    });
    configuredEnhancements.forEach((method) => {
      if (!order.includes(method) && !HIDDEN_METHODS.has(method)) {
        order.push(method);
      }
    });
    for (const method of available.keys()) {
      if (!order.includes(method)) {
        order.push(method);
      }
    }
    return order.map((method) => ({
      method,
      meta: available.get(method) ?? null,
      isPrimary: selectedLatexMethods.includes(method),
    }));
  }, [configuredEnhancements, enhanced, selectedLatexMethods]);

  const formatFileSize = (bytes: number) => {
    if (!bytes) return "—";
    const k = 1024;
    const units = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${units[i]}`;
  };

  const resolveRelativePath = (meta: EnhancedPDF) => {
    const rawPath = meta.relative_path || meta.path || meta.file_path || "";
    if (!rawPath) return "";
    if (rawPath.includes("/pipeline_runs/")) {
      const parts = rawPath.split("/pipeline_runs/");
      if (parts.length > 1) {
        return parts[1].split("/").slice(1).join("/");
      }
    }
    return rawPath;
  };

  const resolveSize = (meta: EnhancedPDF) => meta.size_bytes ?? meta.file_size_bytes ?? 0;

  const methodLabel = useCallback(
    (method: string) => (ENHANCEMENT_METHOD_LABELS as Record<string, string>)[method] || method.replace(/_/g, " "),
    []
  );

  const downloadRelativeArtifact = useCallback(
    async (relativeTarget: string, friendlyName?: string) => {
      if (!activeRunId) {
        throw new Error("No active run selected.");
      }
      if (!relativeTarget) {
        throw new Error("Artifact path unavailable.");
      }

      const downloadUrl = buildDownloadUrl(activeRunId, relativeTarget);
      const friendlyRaw = friendlyName || "artifact";
      const safeFriendly = friendlyRaw
        .toString()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
      const normalizedName = safeFriendly || "artifact";

      const response = await fetch(downloadUrl);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status} ${response.statusText}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      const filenameHint = relativeTarget.split(/[\\/]+/).pop() || normalizedName;
      a.download = `${normalizedName}_${filenameHint}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    },
    [activeRunId]
  );

  const handleDownload = useCallback(
    async (method: string, meta: EnhancedPDF, displayName?: string, overrideRelativePath?: string) => {
      if (!activeRunId) return;

      const relativeTarget = overrideRelativePath || resolveRelativePath(meta);
      if (!relativeTarget) return;

      setIsDownloading(method);
      setDownloadError(null);

      try {
        const friendlyRaw = displayName || methodLabel(method) || method || "enhanced";
        await downloadRelativeArtifact(relativeTarget, friendlyRaw);
      } catch (error) {
        console.error("Download error:", error);
        setDownloadError(
          `Failed to download ${method}: ${error instanceof Error ? error.message : "Unknown error"}`
        );
      } finally {
        setIsDownloading(null);
      }
    },
    [activeRunId, downloadRelativeArtifact, methodLabel]
  );

  useEffect(() => {
    if (stage?.status === "pending") {
      setHasQueuedPdf(false);
    }
  }, [stage?.status]);

  useEffect(() => {
    setReportMessage(null);
    setReportError(null);
    setReportDownloadPath(null);
    setReportGeneratedAt(null);
  }, [activeRunId]);

  useEffect(() => {
    setEvaluationState({});
  }, [activeRunId]);

useEffect(() => {
  if (!activeRunId) {
    setAutoDetectionRequested(false);
    return;
  }
  const stageComplete = stage?.status === "completed";
  const hasExistingReport = Boolean(detectionReportInfo?.relativePath || reportDownloadPath);
  if (!stageComplete) {
    setAutoDetectionRequested(false);
    return;
  }
  if (!hasExistingReport && !autoDetectionRequested && !isGeneratingReport) {
    setAutoDetectionRequested(true);
    (async () => {
      try {
        await generateDetectionReport(activeRunId);
        await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
        setReportMessage("Detection report generated after PDF creation.");
      } catch (error) {
        console.warn("Automatic detection report generation failed:", error);
        setAutoDetectionRequested(false);
      }
    })();
  }
}, [
  activeRunId,
  autoDetectionRequested,
  detectionReportInfo?.relativePath,
  generateDetectionReport,
  isGeneratingReport,
  refreshStatus,
  reportDownloadPath,
  stage?.status,
]);

  const detectionReportButtonDisabled =
    !activeRunId || isGeneratingReport;

  const handleGenerateReport = useCallback(async () => {
    if (!activeRunId || isGeneratingReport) return;
    setIsGeneratingReport(true);
    setReportError(null);
    setReportMessage(null);
    try {
      const result = await generateDetectionReport(activeRunId);
      const relativePath = result.output_files?.json || null;
      const generatedAt = result.generated_at || null;
      setReportDownloadPath(relativePath);
      setReportGeneratedAt(generatedAt);
      setReportMessage("Detection report generated successfully.");
      await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      if (relativePath) {
        try {
          await downloadRelativeArtifact(relativePath, "detection-report");
        } catch (downloadErr) {
          const message = downloadErr instanceof Error ? downloadErr.message : String(downloadErr);
          setReportError(`Detection report ready but download failed: ${message}`);
        }
      }
    } catch (error) {
      console.error("Failed to generate detection report:", error);
      const message = error instanceof Error ? error.message : String(error);
      setReportError(`Failed to generate detection report: ${message}`);
    } finally {
      setIsGeneratingReport(false);
    }
  }, [
    activeRunId,
    downloadRelativeArtifact,
    generateDetectionReport,
    isGeneratingReport,
    refreshStatus,
  ]);

  const handleDownloadReport = useCallback(async () => {
    if (!latestReportPath) return;
    try {
      setReportError(null);
      await downloadRelativeArtifact(latestReportPath, "detection-report");
    } catch (error) {
      console.error("Failed to download detection report:", error);
      const message = error instanceof Error ? error.message : String(error);
      setReportError(`Failed to download detection report: ${message}`);
    }
  }, [downloadRelativeArtifact, latestReportPath]);

  const handleOpenDetectionReport = useCallback(() => {
    if (!runId || !latestReportPath) return;
    navigate(`/runs/${runId}/reports/detection`);
  }, [navigate, latestReportPath, runId]);

  const handleEvaluationReportNav = useCallback(() => {
    if (!runId) return;
    navigate(`/runs/${runId}/reports/evaluation`);
  }, [navigate, runId]);

  const handleEvaluateVariant = useCallback(
    async (method: string) => {
      if (!activeRunId) return;
      setEvaluationState((prev) => ({
        ...prev,
        [method]: { isLoading: true, message: null, error: null },
      }));
      try {
        await generateEvaluationReport(activeRunId, { method });
        setEvaluationState((prev) => ({
          ...prev,
          [method]: { isLoading: false, message: "Evaluation complete.", error: null },
        }));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setEvaluationState((prev) => ({
          ...prev,
          [method]: { isLoading: false, message: null, error: `Evaluation failed: ${message}` },
        }));
      } finally {
        await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      }
    },
    [activeRunId, generateEvaluationReport, refreshStatus]
  );

  const handleCreatePdf = useCallback(async () => {
    if (!activeRunId || !hasReadyMappings || isQueuing || hasQueuedPdf) return;
    setIsQueuing(true);
    setQueueError(null);
    setQueueMessage(null);
    try {
      await resumeFromStage(activeRunId, "pdf_creation", {
        targetStages: ["document_enhancement", "pdf_creation", "results_generation"],
      });
      await refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
      setQueueMessage("PDF rendering started.");
      setHasQueuedPdf(true);
      setPreferredStage("pdf_creation");
    } catch (error) {
      console.error("Failed to trigger PDF creation:", error);
      const message = error instanceof Error ? error.message : String(error);
      setQueueError(`Failed to queue PDF creation: ${message}`);
    } finally {
      setIsQueuing(false);
    }
  }, [activeRunId, resumeFromStage, hasReadyMappings, refreshStatus, isQueuing, hasQueuedPdf, setPreferredStage]);

  const stageRunning = stage?.status === "running";
  const detectionStatusLabel = useMemo(() => {
    if (isGeneratingReport) {
      return "Generating...";
    }
    if (latestReportPath) {
      return formattedReportTimestamp ? `Ready (${formattedReportTimestamp})` : "Ready";
    }
    return "Not generated";
  }, [formattedReportTimestamp, isGeneratingReport, latestReportPath]);
  const createDisabled =
    !hasReadyMappings ||
    isQueuing ||
    hasQueuedPdf ||
    (stage && stage.status !== "pending");

  return (
    <div className="panel pdf-creation">
      <header className="panel-header panel-header--tight">
        <h1>PDF Creation</h1>
        <div className="panel-actions">
          <div className="panel-actions__inline">
            <button
              type="button"
              className="ghost-button"
              onClick={handleGenerateReport}
              disabled={detectionReportButtonDisabled}
              aria-busy={isGeneratingReport}
              title={
                substitutionStage?.status !== "completed"
                  ? "Detection reports are available once Smart Substitution completes."
                  : "Generate a question-level detection summary for this run."
              }
            >
              {isGeneratingReport ? "Generating..." : "Generate Detection Report"}
            </button>
            {latestReportPath ? (
              <button
                type="button"
                className="ghost-button"
                onClick={handleDownloadReport}
                title="Download the latest detection report."
              >
                Download Report
              </button>
            ) : null}
            <button
              type="button"
              className="icon-button"
              onClick={handleOpenDetectionReport}
              disabled={!latestReportPath || !runId}
              title={
                latestReportPath
                  ? "Open the detection report dashboard."
                  : "Generate a detection report to view details."
              }
            >
              <FileBarChart2 size={16} />
            </button>
            <button
              type="button"
              className="icon-button"
              onClick={handleEvaluationReportNav}
              disabled={!runId}
              title="Open evaluation reports for attacked PDFs."
            >
              <LineChart size={16} />
            </button>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={handleCreatePdf}
            disabled={createDisabled}
            aria-busy={isQueuing}
            title={
              !hasReadyMappings
                ? "Validate at least one mapping before generating PDFs."
                : stage?.status === "running"
                ? "PDF rendering in progress."
                : stage?.status === "completed"
                ? "PDF creation finished for this run."
                : "Queue PDF rendering with the selected variants"
            }
          >
            {isQueuing ? "Queuing..." : hasQueuedPdf || stage?.status === "running" ? "Rendering..." : "Create PDFs"}
          </button>
        </div>
      </header>

      <div className="stage-overview stage-overview--spread">
        <div className="stage-overview__item">
          <span>Run</span>
          <strong>{runStatus}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Stage</span>
          <strong className={`status-tag status-${stage?.status ?? "pending"}`}>{stage?.status ?? "pending"}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Ready</span>
          <strong>
            {readyCount}/{structuredQuestions.length || 0}
          </strong>
        </div>
        <div className="stage-overview__item">
          <span>Variants</span>
          <strong>{entries.filter((entry) => entry.meta).length}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Detection Report</span>
          <strong>{detectionStatusLabel}</strong>
        </div>
        <div className="stage-overview__item">
          <span>Elapsed</span>
          <strong>{stage?.duration_ms ? `${Math.round(stage.duration_ms / 1000)}s` : "—"}</strong>
        </div>
      </div>

      {queueMessage ? <div className="panel-flash panel-flash--info">{queueMessage}</div> : null}
      {queueError ? <div className="panel-flash panel-flash--error">{queueError}</div> : null}
      {reportMessage ? (
        <div className="panel-flash panel-flash--info panel-flash--with-actions">
          <div className="panel-flash__content">
            <strong>{reportMessage}</strong>
            {formattedReportTimestamp ? <span>Generated {formattedReportTimestamp}</span> : null}
          </div>
          <div className="panel-flash__actions">
            <button type="button" className="ghost-button" onClick={handleDownloadReport} disabled={!latestReportPath}>
              Download report
            </button>
          </div>
        </div>
      ) : null}
      {reportError ? <div className="panel-flash panel-flash--error">{reportError}</div> : null}
      {downloadError ? (
        <div className="panel-banner panel-banner--error">{downloadError}</div>
      ) : null}

      <section className="pdf-card-grid">
        {entries.map(({ method, meta, isPrimary }) => {
          const metaData = (meta ?? null) as EnhancedPDF | null;
          const hasMeta = Boolean(metaData);
          const label = methodLabel(method);
          const relativePath = hasMeta ? resolveRelativePath(metaData!) : "";
          const size = hasMeta ? resolveSize(metaData!) : 0;
          const previewUrl =
            activeRunId && relativePath ? buildDownloadUrl(activeRunId as string, relativePath) : "";
          const stats = hasMeta ? ((metaData!.render_stats as Record<string, any>) || {}) : {};
          const artifactMap = hasMeta
            ? ((stats.artifact_rel_paths as Record<string, string>) ||
                (stats.artifacts as Record<string, string>) ||
                {})
            : {};
          const artifactEntries = Object.entries(artifactMap);
          const promptCount =
            stats.prompt_count ??
            stats.replacements ??
            metaData?.prompt_count ??
            metaData?.replacements ??
            null;
          const compileSummary = (stats.compile_summary as Record<string, any>) || {};
          const compileStatus =
            compileSummary.success === true ? "Success" : compileSummary.success === false ? "Failed" : null;

          const evaluationMeta = evaluationReports[method] as Record<string, any> | undefined;
          const evaluationTimestamp = evaluationMeta?.generated_at
            ? new Date(evaluationMeta.generated_at).toLocaleString()
            : null;
          const evaluationStatus = evaluationState[method];
          const evaluationDisabled = 
            !hasMeta || 
            Boolean(evaluationStatus?.isLoading) ||
            stage?.status !== "completed" ||
            !detectionReportInfo;

          return (
            <article
              key={method}
              className={[
                "pdf-card",
                isPrimary ? "pdf-card--primary" : "",
                hasMeta ? "pdf-card--ready" : "pdf-card--pending",
              ]
                .join(" ")
                .trim()}
            >
              <header className="pdf-card__header">
                <h3>{label}</h3>
                {isPrimary ? <span className="badge">Selected</span> : null}
              </header>

              <div className="pdf-card__progress">
                <div className={`progress-bar ${!hasMeta ? "is-active" : ""}`}>
                  <span className="progress-bar__fill" />
                </div>
                <span>{hasMeta ? "Ready" : stageRunning ? "Rendering…" : "Queued"}</span>
              </div>

              <div className="pdf-card__preview">
                {hasMeta && previewUrl ? (
                  <object data={previewUrl} type="application/pdf" aria-label={`${label} preview`}>
                    <a href={previewUrl} target="_blank" rel="noopener noreferrer">
                      Open preview
                    </a>
                  </object>
                ) : (
                  <div className="pdf-card__placeholder">Preview unavailable</div>
                )}
              </div>

              <div className="pdf-card__body">
                <div className="pdf-card__stat">
                  <span>Size</span>
                  <strong>{size ? formatFileSize(size) : "—"}</strong>
                </div>
                {promptCount != null ? (
                  <div className="pdf-card__stat">
                    <span>Prompts</span>
                    <strong>{promptCount}</strong>
                  </div>
                ) : null}
                {compileStatus ? (
                  <div className="pdf-card__stat">
                    <span>Compile</span>
                    <strong>{compileStatus}</strong>
                  </div>
                ) : null}
              </div>

              <div className="pdf-card__actions">
                <button
                  type="button"
                  className="pdf-card__download"
                  disabled={!hasMeta || !relativePath || isDownloading === method}
                  onClick={() => {
                    if (!metaData || !relativePath) return;
                    handleDownload(method, metaData, label);
                  }}
                >
                  {isDownloading === method ? "Downloading…" : "Download"}
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => handleEvaluateVariant(method)}
                  disabled={evaluationDisabled}
                  aria-busy={evaluationStatus?.isLoading}
                  title={
                    !hasMeta
                      ? "Render this variant before evaluating."
                      : stage?.status !== "completed"
                      ? "Wait for all PDFs to finish rendering."
                      : !detectionReportInfo
                      ? "Generate a detection report before evaluating."
                      : "Run multi-model evaluation for this attacked PDF."
                  }
                >
                  {evaluationStatus?.isLoading ? "Evaluating…" : "Evaluate"}
                </button>

                {hasMeta && artifactEntries.length ? (
                  <div className="pdf-card__artifact-buttons">
                    {artifactEntries.map(([stageKey, artifactPath]) => (
                      <button
                        key={`${method}-${stageKey}`}
                        type="button"
                        onClick={() => {
                          if (!metaData) return;
                          handleDownload(
                            method,
                            metaData,
                            `${label} ${stageLabels[stageKey] ?? stageKey}`,
                            artifactPath
                          );
                        }}
                      >
                        {stageLabels[stageKey] ?? stageKey.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              {evaluationStatus?.error ? (
                <p className="pdf-card__notice pdf-card__notice--error">{evaluationStatus.error}</p>
              ) : null}
              {evaluationStatus?.message || evaluationTimestamp ? (
                <p className="pdf-card__notice">
                  {evaluationStatus?.message ?? `Last evaluated ${evaluationTimestamp}`}
                </p>
              ) : null}
            </article>
          );
        })}
      </section>
    </div>
  );
};

export default PdfCreationPanel;
