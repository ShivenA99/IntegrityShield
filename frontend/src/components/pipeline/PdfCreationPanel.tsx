import * as React from "react";
import { useState, useCallback, useMemo, useEffect } from "react";

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
  const { status, activeRunId, resumeFromStage, refreshStatus, setPreferredStage } = usePipeline();
  const [isDownloading, setIsDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isQueuing, setIsQueuing] = useState(false);
  const [queueMessage, setQueueMessage] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [hasQueuedPdf, setHasQueuedPdf] = useState(false);

  const stage = status?.stages.find((item) => item.name === "pdf_creation");
  const runStatus = status?.status ?? "unknown";
  const enhanced = (status?.structured_data as any)?.manipulation_results?.enhanced_pdfs || {};
  const structuredQuestions = (status?.structured_data as any)?.questions || [];

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

  const methodLabel = (method: string) =>
    (ENHANCEMENT_METHOD_LABELS as Record<string, string>)[method] || method.replace(/_/g, " ");

const handleDownload = useCallback(
    async (method: string, meta: EnhancedPDF, displayName?: string, overrideRelativePath?: string) => {
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
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "");

        const response = await fetch(downloadUrl);
        if (!response.ok) {
          throw new Error(`Download failed: ${response.status} ${response.statusText}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        const filenameHint = relativeTarget.split(/[\\/]+/).pop() || method || "enhanced";
        a.download = `${safeFriendly || method}_${filenameHint}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } catch (error) {
        console.error("Download error:", error);
        setDownloadError(
          `Failed to download ${method}: ${error instanceof Error ? error.message : "Unknown error"}`
        );
      } finally {
        setIsDownloading(null);
      }
    },
    [activeRunId]
  );

  useEffect(() => {
    if (stage?.status === "pending") {
      setHasQueuedPdf(false);
    }
  }, [stage?.status]);

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
  const createDisabled =
    !hasReadyMappings ||
    isQueuing ||
    hasQueuedPdf ||
    (stage && stage.status !== "pending");

  return (
    <div className="panel pdf-creation">
      <header className="panel-header panel-header--tight">
        <h1>Download PDFs</h1>
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
          {isQueuing ? "Queuing…" : hasQueuedPdf || stage?.status === "running" ? "Rendering…" : "Create PDFs"}
        </button>
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
          <span>Elapsed</span>
          <strong>{stage?.duration_ms ? `${Math.round(stage.duration_ms / 1000)}s` : "—"}</strong>
        </div>
      </div>

      {queueMessage ? <div className="panel-flash panel-flash--info">{queueMessage}</div> : null}
      {queueError ? <div className="panel-flash panel-flash--error">{queueError}</div> : null}
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
            </article>
          );
        })}
      </section>
    </div>
  );
};

export default PdfCreationPanel;
