import React, { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Loader2, RefreshCcw, Shield, UploadCloud } from "lucide-react";

import LTIShell from "@layout/LTIShell";
import ArtifactPreviewModal, { ArtifactPreview } from "@components/shared/ArtifactPreviewModal";
import { Button } from "@instructure/ui-buttons";
import { Table } from "@instructure/ui-table";
import { ScreenReaderContent } from "@instructure/ui-a11y-content";
import { usePipeline } from "@hooks/usePipeline";
import { useNotifications } from "@contexts/NotificationContext";
import { validatePdfFile } from "@services/utils/validators";
import { listRuns, updatePipelineConfig } from "@services/api/pipelineApi";
import type { CorePipelineStageName } from "@services/types/pipeline";
import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";

type ModeOption = "detection" | "prevention";

const MODE_PRESETS: Record<ModeOption, { label: string; methods: string[] }> = {
  detection: { label: "Detection", methods: ["latex_dual_layer", "latex_font_attack", "pymupdf_overlay"] },
  prevention: { label: "Prevention", methods: ["latex_icw", "latex_icw_dual_layer", "latex_icw_font_attack", "pymupdf_overlay"] },
};

const STAGE_FLOW: { key: string; label: string; sources: CorePipelineStageName[] }[] = [
  { key: "extraction", label: "Extraction", sources: ["smart_reading"] },
  { key: "vulnerability", label: "Vulnerability generation", sources: ["content_discovery"] },
  { key: "manipulation", label: "Manipulation engine", sources: ["smart_substitution"] },
  { key: "detection", label: "Detection", sources: ["results_generation"] },
  { key: "evaluation", label: "Evaluation", sources: ["effectiveness_testing"] },
  { key: "output", label: "Shielded output", sources: ["document_enhancement", "pdf_creation"] },
];

type ArtifactGroup = {
  key: string;
  label: string;
  rows: ArtifactPreview[];
};

const TARGET_STAGES: CorePipelineStageName[] = ["smart_reading", "content_discovery", "smart_substitution", "effectiveness_testing", "document_enhancement", "pdf_creation", "results_generation"];

const Dashboard: React.FC = () => {
  const { status, startPipeline, refreshStatus, isLoading } = usePipeline();
  const { push } = useNotifications();

  const [mode, setMode] = useState<ModeOption>("detection");
  const [questionFile, setQuestionFile] = useState<File | null>(null);
  const [answerKeyFile, setAnswerKeyFile] = useState<File | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [recentRuns, setRecentRuns] = useState<any[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactPreview | null>(null);

  const runId = status?.run_id ?? null;
  const structured = (status?.structured_data as Record<string, any>) ?? {};
  const manipulationBucket = (structured.manipulation_results as Record<string, any>) ?? {};
  const reports = (structured.reports as Record<string, any>) ?? {};

  useEffect(() => {
    const methods = Array.isArray(status?.pipeline_config?.enhancement_methods) ? (status?.pipeline_config?.enhancement_methods as string[]) : [];
    if (methods.some((method) => method.includes("icw"))) {
      setMode("prevention");
    }
  }, [status?.pipeline_config]);

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const response = await listRuns({ limit: 8, sortBy: "created_at", sortDir: "desc" });
        setRecentRuns(response.runs ?? []);
      } catch (error) {
        push({ title: "Unable to load history", description: error instanceof Error ? error.message : "Unknown error", intent: "error" });
      }
    };
    fetchRuns();
  }, [push]);

  useEffect(() => {
    if (!runId) return;
    const interval = setInterval(() => {
      refreshStatus(runId, { quiet: true }).catch(() => undefined);
    }, 10000);
    return () => clearInterval(interval);
  }, [runId, refreshStatus]);

  const handleToggleMode = async (nextMode: ModeOption) => {
    setMode(nextMode);
    if (!runId) return;
    try {
      await updatePipelineConfig(runId, { enhancement_methods: MODE_PRESETS[nextMode].methods });
      await refreshStatus(runId, { quiet: true }).catch(() => undefined);
    } catch (error) {
      push({ title: "Failed to update mode", description: error instanceof Error ? error.message : "Unknown error", intent: "error" });
    }
  };

  const handleFileSelect = useCallback((file: File | null, setFile: React.Dispatch<React.SetStateAction<File | null>>) => {
    if (!file) {
      setFile(null);
      return;
    }
    const validation = validatePdfFile(file);
    if (validation) {
      push({ title: "Upload failed", description: validation, intent: "error" });
      return;
    }
    setFile(file);
  }, [push]);

  const handleRun = async () => {
    if (!questionFile || !answerKeyFile) {
      push({ title: "Missing files", description: "Both assessment and answer key are required.", intent: "warning" });
      return;
    }
    setIsStarting(true);
    try {
      await startPipeline({
        file: questionFile,
        answerKeyFile,
        config: {
          targetStages: TARGET_STAGES,
          aiModels: [],
          enhancementMethods: MODE_PRESETS[mode].methods,
          skipIfExists: true,
          parallelProcessing: true,
        },
      });
      setQuestionFile(null);
      setAnswerKeyFile(null);
    } finally {
      setIsStarting(false);
    }
  };

  const stageTimeline = useMemo(() => {
    const stageMap = new Map<string, string>();
    (status?.stages ?? []).forEach((stage) => stageMap.set(stage.name, stage.status));
    const deriveStatus = (sources: CorePipelineStageName[]) => {
      const statuses = sources.map((source) => stageMap.get(source));
      if (statuses.some((value) => value === "failed")) return "failed";
      if (statuses.some((value) => value === "running")) return "running";
      if (statuses.every((value) => value === "completed")) return "completed";
      return "pending";
    };
    return STAGE_FLOW.map((entry, index) => ({
      ...entry,
      index,
      status: deriveStatus(entry.sources),
    }));
  }, [status?.stages]);

  const completedStages = stageTimeline.filter((stage) => stage.status === "completed").length;
  const progressPercent = stageTimeline.length ? Math.round((completedStages / stageTimeline.length) * 100) : 0;

const formatMethodLabel = (key?: string | null) =>
  key ? ENHANCEMENT_METHOD_LABELS[key as keyof typeof ENHANCEMENT_METHOD_LABELS] ?? key.replace(/_/g, " ") : null;

const artifactGroups = useMemo<ArtifactGroup[]>(() => {
    const assessments: ArtifactPreview[] = [];
    const reportRows: ArtifactPreview[] = [];
    const documentInfo = structured.document as Record<string, any>;
    if (documentInfo?.original_path) {
      assessments.push({
        key: "original",
        label: "Original",
        kind: "assessment",
        status: "completed",
        relativePath: documentInfo.original_path,
        sizeBytes: documentInfo.size_bytes,
      });
    }
    const enhanced = (manipulationBucket.enhanced_pdfs as Record<string, any>) ?? {};
    Object.entries(enhanced).forEach(([method, meta]) => {
      assessments.push({
        key: `shielded-${method}`,
        label: "Shielded",
        kind: "assessment",
        method: formatMethodLabel(method),
        status: meta.relative_path ? "completed" : "pending",
        relativePath: meta.relative_path || meta.path || meta.file_path,
        sizeBytes: meta.size_bytes,
      });
    });
    if (reports.vulnerability) {
      reportRows.push({
        key: "vulnerability",
        label: "Vulnerability",
        kind: "report",
        status: reports.vulnerability.artifact ? "completed" : "pending",
        relativePath: reports.vulnerability.artifact,
      });
    }
    const detectionReport = manipulationBucket.detection_report;
    if (detectionReport) {
      reportRows.push({
        key: "detection",
        label: "Detection",
        kind: "report",
        status: detectionReport.relative_path ? "completed" : "pending",
        relativePath: detectionReport.relative_path || detectionReport.output_files?.json,
      });
    }
    const evaluationEntries = (reports.evaluation as Record<string, any>) ?? {};
    Object.entries(evaluationEntries).forEach(([method, meta]) => {
      reportRows.push({
        key: `evaluation-${method}`,
        label: "Evaluation",
        kind: "report",
        method: formatMethodLabel(method),
        status: meta.artifact ? "completed" : "pending",
        relativePath: meta.artifact,
      });
    });
    return [
      { key: "assessments", label: "Assessments", rows: assessments },
      { key: "reports", label: "Reports", rows: reportRows },
    ];
  }, [reports, structured, manipulationBucket]);

  const recentRunRows = useMemo(
    () =>
      recentRuns.map((run) => ({
        run_id: run.run_id ?? run.id ?? "unknown",
        status: run.status ?? "pending",
        created_at: run.created_at ? new Date(run.created_at).toLocaleString() : "—",
      })),
    [recentRuns]
  );

  return (
    <LTIShell title="Dashboard" subtitle="Upload, configure, and monitor runs.">
      <section className="canvas-grid side">
        <div className="canvas-card run-builder">
          <h2>Run builder</h2>
          <p>Provide the required files and start the Canvas-ready Shielded workflow.</p>
          <div className="run-builder__mode">
            <label>Mode</label>
            <div className="mode-toggle">
              {(["detection", "prevention"] as ModeOption[]).map((option) => (
                <Button
                  key={option}
                  color={mode === option ? "primary" : "secondary"}
                  withBackground
                  margin="0 xx-small 0 0"
                  onClick={() => handleToggleMode(option)}
                  interaction={isLoading ? "disabled" : "enabled"}
                  aria-pressed={mode === option}
                >
                  {MODE_PRESETS[option].label}
                </Button>
              ))}
            </div>
            <p className="mode-hint">{mode === "detection" ? "Detection compares baseline vs perturbed runs to surface risk." : "Prevention generates ICW-friendly shielded assessments for LMS delivery."}</p>
          </div>
          <div className="dropzone-grid">
            <label
              className={clsx("dropzone", questionFile && "has-file")}
              onDragOver={(event) => {
                event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                handleFileSelect(event.dataTransfer.files?.[0] ?? null, setQuestionFile);
              }}
            >
              <UploadCloud size={24} />
              <span>Assessment PDF</span>
              <input type="file" accept="application/pdf" onChange={(event) => handleFileSelect(event.target.files?.[0] ?? null, setQuestionFile)} />
              {questionFile ? <small>{questionFile.name}</small> : <small>Required</small>}
            </label>
            <label
              className={clsx("dropzone", answerKeyFile && "has-file")}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                handleFileSelect(event.dataTransfer.files?.[0] ?? null, setAnswerKeyFile);
              }}
            >
              <UploadCloud size={24} />
              <span>Answer key PDF</span>
              <input type="file" accept="application/pdf" onChange={(event) => handleFileSelect(event.target.files?.[0] ?? null, setAnswerKeyFile)} />
              {answerKeyFile ? <small>{answerKeyFile.name}</small> : <small>Required</small>}
            </label>
          </div>
          <div className="run-action-row">
            <Button color="primary" onClick={handleRun} interaction={!questionFile || !answerKeyFile || isStarting ? "disabled" : "enabled"}>
              {isStarting ? <Loader2 className="spin" size={16} /> : <Shield size={16} />}
              {isStarting ? "Starting…" : "Run"}
            </Button>
            <Button color="secondary" withBackground={false} onClick={() => { setQuestionFile(null); setAnswerKeyFile(null); }}>
              Clear
            </Button>
          </div>
        </div>

        <div className="canvas-card">
          <div className="stage-progress__header">
            <div>
              <h2>Pipeline telemetry</h2>
              <p>{progressPercent}% complete • {completedStages} of {stageTimeline.length} stages</p>
            </div>
            <Button color="secondary" withBackground={false} onClick={() => runId && refreshStatus(runId)}>
              <RefreshCcw size={16} /> Refresh
            </Button>
          </div>
          <div className="stage-progress__bar">
            <div style={{ width: `${progressPercent}%` }} />
          </div>
          <ul className="stage-progress__list">
            {stageTimeline.map((stage) => (
              <li key={stage.key} className={clsx(stage.status)}>
                <div className="stage-progress__meta">
                  <span className="stage-progress__index">{stage.index + 1}</span>
                  <div>
                    <p>{stage.label}</p>
                    <small>{stage.status === "running" ? "In progress" : stage.status === "completed" ? "Complete" : stage.status === "failed" ? "Check logs" : "Queued"}</small>
                  </div>
                </div>
                <span className={clsx("status-pill", stage.status === "completed" ? "completed" : stage.status === "failed" ? "failed" : stage.status === "running" ? "running" : "pending")}>
                  {stage.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="canvas-grid two">
        <div className="canvas-card">
          <div className="table-header">
            <h2>Files</h2>
          </div>
          {artifactGroups.map((group) => (
            <div key={group.key} className="artifact-subsection">
              <div className="artifact-subsection__header">
                <h3>{group.label}</h3>
              </div>
              {group.rows.length ? (
                <Table hover layout="auto" caption={<ScreenReaderContent>{group.label} files</ScreenReaderContent>}>
                  <Table.Head>
                    <Table.Row>
                      <Table.ColHeader id={`${group.key}-name`}>Name</Table.ColHeader>
                      <Table.ColHeader id={`${group.key}-variant`}>Variant</Table.ColHeader>
                      <Table.ColHeader id={`${group.key}-status`}>Status</Table.ColHeader>
                      <Table.ColHeader id={`${group.key}-actions`}>Actions</Table.ColHeader>
                    </Table.Row>
                  </Table.Head>
                  <Table.Body>
                    {group.rows.map((row) => (
                      <Table.Row key={row.key}>
                        <Table.Cell>{row.label}</Table.Cell>
                        <Table.Cell>{row.method ?? row.variant ?? "—"}</Table.Cell>
                        <Table.Cell>
                          <span className={clsx("status-pill", row.status === "completed" ? "completed" : row.status === "failed" ? "failed" : row.status === "running" ? "running" : "pending")}>
                            {row.status}
                          </span>
                        </Table.Cell>
                        <Table.Cell>
                          <Button color="secondary" withBackground={false} onClick={() => setSelectedArtifact(row)} interaction={!row.relativePath ? "disabled" : "enabled"}>
                            Preview
                          </Button>
                        </Table.Cell>
                      </Table.Row>
                    ))}
                  </Table.Body>
                </Table>
              ) : (
                <p className="table-empty">No {group.label.toLowerCase()} available yet.</p>
              )}
            </div>
          ))}
        </div>
        <div className="canvas-card">
          <div className="table-header">
            <h2>Recent activity</h2>
          </div>
          {recentRunRows.length ? (
            <Table hover caption={<ScreenReaderContent>Recent runs</ScreenReaderContent>}>
              <Table.Head>
                <Table.Row>
                  <Table.ColHeader id="recent-run-id">Run ID</Table.ColHeader>
                  <Table.ColHeader id="recent-started">Started</Table.ColHeader>
                  <Table.ColHeader id="recent-status">Status</Table.ColHeader>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {recentRunRows.map((run) => (
                  <Table.Row key={run.run_id}>
                    <Table.Cell>{run.run_id}</Table.Cell>
                    <Table.Cell>{run.created_at}</Table.Cell>
                    <Table.Cell>
                      <span className={clsx("status-pill", run.status === "completed" ? "completed" : run.status === "failed" ? "failed" : "running")}>
                        {run.status}
                      </span>
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          ) : (
            <p>No history yet.</p>
          )}
        </div>
      </section>

      <ArtifactPreviewModal artifact={selectedArtifact} runId={runId ?? undefined} onClose={() => setSelectedArtifact(null)} />
    </LTIShell>
  );
};

export default Dashboard;
