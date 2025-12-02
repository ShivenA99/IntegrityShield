import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { Loader2, RefreshCcw, Shield, Eye, X, CheckCircle2, AlertTriangle, Clock } from "lucide-react";

import LTIShell from "@layout/LTIShell";
import ArtifactPreviewModal, { ArtifactPreview } from "@components/shared/ArtifactPreviewModal";
import { PageSection } from "@components/layout/PageSection";
import { StatusPill } from "@components/shared/StatusPill";
import { ProgressBar } from "@components/shared/ProgressBar";
import { FileUploadField } from "@components/shared/FileUploadField";
import { Button } from "@instructure/ui-buttons";
import { Table } from "@instructure/ui-table";
import { ScreenReaderContent } from "@instructure/ui-a11y-content";
import { Grid } from "@instructure/ui-grid";
import { Flex } from "@instructure/ui-flex";
import { View } from "@instructure/ui-view";
import { Text } from "@instructure/ui-text";
import { usePipeline } from "@hooks/usePipeline";
import { usePipelineContext } from "@contexts/PipelineContext";
import { useNotifications } from "@contexts/NotificationContext";
import { validatePdfFile } from "@services/utils/validators";
import { updatePipelineConfig } from "@services/api/pipelineApi";
import type { CorePipelineStageName } from "@services/types/pipeline";
import { ENHANCEMENT_METHOD_LABELS, getMethodDisplayLabel } from "@constants/enhancementMethods";

type ModeOption = "detection" | "prevention";

const MODE_PRESETS: Record<ModeOption, { label: string; description: string }> = {
  detection: {
    label: "Detection",
    description: "5 LaTeX-based detection variants to test mapping effectiveness",
  },
  prevention: {
    label: "Prevention",
    description: "3 prevention attacks: fixed watermark, font gibberish, and hybrid",
  },
};

const DETECTION_STAGE_FLOW: { key: string; label: string; sources: CorePipelineStageName[] }[] = [
  { key: "extraction", label: "Extraction", sources: ["smart_reading"] },
  { key: "vulnerability", label: "Vulnerability Analysis", sources: ["content_discovery"] },
  { key: "manipulation", label: "Mapping Generation", sources: ["smart_substitution", "effectiveness_testing"] },
  { key: "output", label: "Shielded PDFs & Evaluation", sources: ["document_enhancement", "pdf_creation"] },
  { key: "detection", label: "Detection Report", sources: ["results_generation"] },
];

const PREVENTION_STAGE_FLOW: { key: string; label: string; sources: CorePipelineStageName[] }[] = [
  { key: "extraction", label: "Extraction", sources: ["smart_reading"] },
  { key: "vulnerability", label: "Vulnerability Analysis", sources: ["content_discovery"] },
  { key: "output", label: "Shielded PDFs & Evaluation", sources: ["document_enhancement", "pdf_creation"] },
];

type ArtifactGroup = {
  key: string;
  label: string;
  rows: ArtifactPreview[];
};

const TARGET_STAGES: CorePipelineStageName[] = ["smart_reading", "content_discovery", "smart_substitution", "effectiveness_testing", "document_enhancement", "pdf_creation", "results_generation"];

const Dashboard: React.FC = () => {
  const location = useLocation();
  const { status, activeRunId, startPipeline, refreshStatus, isLoading, viewMode, setViewMode, setActiveRunId, resetActiveRun } = usePipeline();
  const { push } = useNotifications();

  const [mode, setMode] = useState<ModeOption>("detection");
  const [questionFile, setQuestionFile] = useState<File | null>(null);
  const [answerKeyFile, setAnswerKeyFile] = useState<File | null>(null);
  const [assessmentName, setAssessmentName] = useState<string>("");
  const [isStarting, setIsStarting] = useState(false);
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactPreview | null>(null);
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [fileFilter, setFileFilter] = useState<"all" | "assessments" | "shielded" | "reports">("all");

  const structured = (status?.structured_data as Record<string, any>) ?? {};
  const manipulationBucket = (structured.manipulation_results as Record<string, any>) ?? {};
  const reports = (structured.reports as Record<string, any>) ?? {};

  useEffect(() => {
    const methods = Array.isArray(status?.pipeline_config?.enhancement_methods) ? (status?.pipeline_config?.enhancement_methods as string[]) : [];
    if (methods.some((method) => method.includes("icw"))) {
      setMode("prevention");
    }
  }, [status?.pipeline_config]);

  // Handle readonly mode from URL params
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const runParam = params.get("run");
    const modeParam = params.get("mode");

    // Only update if the runParam is different from current activeRunId
    if (runParam && runParam !== activeRunId) {
      if (modeParam === "readonly") {
        setViewMode("readonly");
      } else {
        setViewMode("edit");
      }
      setActiveRunId(runParam);
      refreshStatus(runParam).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  useEffect(() => {
    if (!activeRunId) return;
    const interval = setInterval(() => {
      refreshStatus(activeRunId, { quiet: true }).catch(() => undefined);
    }, 10000);
    return () => clearInterval(interval);
  }, [activeRunId, refreshStatus]);

  // Check if mode toggle should be disabled (only allow on fresh runs)
  const isModeDisabled = useMemo(() => {
    return !!activeRunId && !!status && (status.status === 'running' || status.status === 'completed' || status.status === 'failed');
  }, [activeRunId, status]);

  const handleToggleMode = (nextMode: ModeOption) => {
    if (isModeDisabled) return; // Don't allow mode change during active run
    setMode(nextMode);
    // Mode selection only affects new pipeline runs, not existing ones
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
        assessmentName: assessmentName || undefined,
        mode,
        config: {
          targetStages: TARGET_STAGES,
          aiModels: [],
          skipIfExists: true,
          parallelProcessing: true,
        },
      });
      // Keep files in state so they can be previewed anytime
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
    // Use mode-specific stage flow
    const stageFlow = mode === "prevention" ? PREVENTION_STAGE_FLOW : DETECTION_STAGE_FLOW;
    return stageFlow.map((entry, index) => ({
      ...entry,
      index,
      status: deriveStatus(entry.sources),
    }));
  }, [status?.stages, mode]);

  const completedStages = stageTimeline.filter((stage) => stage.status === "completed").length;
  const progressPercent = stageTimeline.length ? Math.round((completedStages / stageTimeline.length) * 100) : 0;

  // Map detection methods to variant numbers
  const DETECTION_VARIANT_MAP: Record<string, number> = {
    latex_icw: 1,
    latex_font_attack: 2,
    latex_dual_layer: 3,
    latex_icw_font_attack: 4,
    latex_icw_dual_layer: 5,
  };

  const formatMethodLabel = (key?: string | null) => {
    if (!key) return null;

    // Use the centralized label function which handles mode-specific labels
    const displayLabel = getMethodDisplayLabel(key, mode);
    if (displayLabel && displayLabel !== key) {
      return displayLabel;
    }

    // Fallback: In detection mode, show "Detection Variant N" for mapped methods
    if (mode === "detection" && key in DETECTION_VARIANT_MAP) {
      return `Detection Variant ${DETECTION_VARIANT_MAP[key]}`;
    }

    // Final fallback to existing label mapping
    return ENHANCEMENT_METHOD_LABELS[key as keyof typeof ENHANCEMENT_METHOD_LABELS] ?? key.replace(/_/g, " ");
  };

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
    // Show evaluation reports for all configured enhancement methods
    // Check both evaluation and prevention_evaluation for backward compatibility
    const evaluationEntries = (reports.evaluation as Record<string, any>) ?? {};
    const preventionEvaluationEntries = (reports.prevention_evaluation as Record<string, any>) ?? {};
    // Merge both, with evaluation taking precedence
    const allEvaluationEntries = { ...preventionEvaluationEntries, ...evaluationEntries };
    const configuredMethods = (status?.pipeline_config?.enhancement_methods as string[]) ?? [];

    // Create a set of methods we should show evaluation reports for
    const methodsToShow = new Set(configuredMethods);

    // Also include any methods that already have evaluation reports
    Object.keys(allEvaluationEntries).forEach(method => methodsToShow.add(method));

    // Show evaluation report for each method
    methodsToShow.forEach((method) => {
      const meta = allEvaluationEntries[method];
      reportRows.push({
        key: `evaluation-${method}`,
        label: "Evaluation",
        kind: "report",
        method: formatMethodLabel(method),
        status: meta?.artifact ? "completed" : "pending",
        relativePath: meta?.artifact,
      });
    });
    return [
      { key: "assessments", label: "Assessments", rows: assessments },
      { key: "reports", label: "Reports", rows: reportRows },
    ];
  }, [reports, structured, manipulationBucket]);

  // Filter artifacts based on selected filter
  const filteredArtifacts = useMemo(() => {
    const allRows = artifactGroups.flatMap(g => g.rows);
    switch (fileFilter) {
      case "assessments":
        return allRows.filter(r => r.kind === "assessment" && r.label === "Original");
      case "shielded":
        return allRows.filter(r => r.kind === "assessment" && r.label === "Shielded");
      case "reports":
        return allRows.filter(r => r.kind === "report");
      default:
        return allRows;
    }
  }, [artifactGroups, fileFilter]);

  // Create blob URL for local file preview
  const previewUrl = useMemo(() => {
    if (!previewFile) return null;
    return URL.createObjectURL(previewFile);
  }, [previewFile]);

  // Cleanup blob URL when modal closes
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  return (
    <LTIShell title="Dashboard">
      {/* Local File Preview Modal */}
      {previewFile && previewUrl && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem'
          }}
          onClick={() => setPreviewFile(null)}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '0.5rem',
              maxWidth: '90vw',
              maxHeight: '90vh',
              width: '900px',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '1rem 1.5rem',
              borderBottom: '1px solid #e0e0e0'
            }}>
              <div>
                <Text size="large" weight="bold">{previewFile.name}</Text>
                <div style={{ marginTop: '0.25rem' }}>
                  <Text size="small" color="secondary">
                    {(previewFile.size / (1024 * 1024)).toFixed(2)} MB
                  </Text>
                </div>
              </div>
              <Button
                color="secondary"
                withBackground={false}
                onClick={() => setPreviewFile(null)}
              >
                <X size={20} />
              </Button>
            </div>

            {/* PDF Preview */}
            <div style={{ flex: 1, overflow: 'auto', padding: '1rem' }}>
              <iframe
                src={previewUrl}
                style={{
                  width: '100%',
                  height: '600px',
                  border: 'none',
                  borderRadius: '0.375rem'
                }}
                title={`Preview of ${previewFile.name}`}
              />
            </div>
          </div>
        </div>
      )}

      {/* Readonly Mode Banner */}
      {viewMode === "readonly" && (
        <div style={{
          backgroundColor: '#e8f4fd',
          border: '1px solid #b3d9f2',
          borderRadius: '0.5rem',
          padding: '1rem',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div>
            <Text weight="bold" size="medium" style={{ color: '#1a5490' }}>
              Viewing Historical Assessment
            </Text>
            <div style={{ marginTop: '0.25rem' }}>
              <Text size="small" style={{ color: '#1a5490' }}>
                This is a read-only view. To run a new assessment, click "Start New Assessment".
              </Text>
            </div>
          </div>
          <Button
            color="primary"
            size="medium"
            onClick={() => {
              resetActiveRun();
              window.history.pushState({}, '', '/dashboard');
            }}
          >
            Start New Assessment
          </Button>
        </div>
      )}

      <Grid colSpacing="small" rowSpacing="small">
        <Grid.Row>
          {viewMode !== "readonly" && (
            <Grid.Col width={{ small: 12, medium: 12, large: 6, xlarge: 6 }}>
            <PageSection
              title="Start"
            >
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ marginBottom: '0.5rem' }}>
                  <Text size="small" weight="normal" color="secondary">Mode</Text>
                </div>
                <div style={{
                  display: 'inline-flex',
                  backgroundColor: '#f5f5f5',
                  borderRadius: '0.5rem',
                  padding: '0.25rem',
                  gap: '0.25rem'
                }}>
                  <button
                    onClick={() => handleToggleMode("detection")}
                    disabled={isLoading || isModeDisabled}
                    style={{
                      padding: '0.5rem 1.25rem',
                      border: 'none',
                      borderRadius: '0.375rem',
                      backgroundColor: mode === "detection" ? '#FF7F32' : 'transparent',
                      color: mode === "detection" ? '#ffffff' : '#666666',
                      fontWeight: mode === "detection" ? '600' : '400',
                      fontSize: '0.875rem',
                      cursor: (isLoading || isModeDisabled) ? 'not-allowed' : 'pointer',
                      opacity: (isLoading || isModeDisabled) ? 0.6 : 1,
                      transition: 'all 0.2s ease',
                      fontFamily: 'inherit'
                    }}
                  >
                    Detection
                  </button>
                  <button
                    onClick={() => handleToggleMode("prevention")}
                    disabled={isLoading || isModeDisabled}
                    style={{
                      padding: '0.5rem 1.25rem',
                      border: 'none',
                      borderRadius: '0.375rem',
                      backgroundColor: mode === "prevention" ? '#FF7F32' : 'transparent',
                      color: mode === "prevention" ? '#ffffff' : '#666666',
                      fontWeight: mode === "prevention" ? '600' : '400',
                      fontSize: '0.875rem',
                      cursor: (isLoading || isModeDisabled) ? 'not-allowed' : 'pointer',
                      opacity: (isLoading || isModeDisabled) ? 0.6 : 1,
                      transition: 'all 0.2s ease',
                      fontFamily: 'inherit'
                    }}
                  >
                    Prevention
                  </button>
                </div>
              </div>

              {/* Assessment Name Field */}
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ marginBottom: '0.5rem' }}>
                  <Text size="small" weight="normal" color="secondary">
                    Assessment Name <span style={{ fontWeight: 'normal', opacity: 0.7 }}>(Optional)</span>
                  </Text>
                </div>
                <input
                  type="text"
                  value={assessmentName}
                  onChange={(e) => setAssessmentName(e.target.value)}
                  placeholder={questionFile?.name || "Enter assessment name or leave empty to use filename"}
                  style={{
                    width: '100%',
                    padding: '0.5rem 0.75rem',
                    border: '1px solid #e0e0e0',
                    borderRadius: '0.375rem',
                    fontSize: '0.875rem',
                    fontFamily: 'inherit',
                    transition: 'border-color 0.2s ease'
                  }}
                  onFocus={(e) => e.target.style.borderColor = '#FF7F32'}
                  onBlur={(e) => e.target.style.borderColor = '#e0e0e0'}
                />
              </div>

              {/* Side-by-side Upload Fields */}
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                {/* Assessment PDF Upload */}
                <div style={{ flex: 1, minWidth: '250px' }}>
                  <FileUploadField
                    label="Assessment PDF"
                    description="Upload the assessment document to process"
                    accept="application/pdf"
                    file={questionFile}
                    onFileSelect={(file) => handleFileSelect(file, setQuestionFile)}
                    required
                  />
                  {questionFile && (
                    <div style={{ marginTop: '0.5rem' }}>
                      <Button
                        color="secondary"
                        size="small"
                        withBackground={false}
                        onClick={() => setPreviewFile(questionFile)}
                      >
                        <Eye size={14} /> Preview
                      </Button>
                    </div>
                  )}
                </div>

                {/* Answer Key PDF Upload */}
                <div style={{ flex: 1, minWidth: '250px' }}>
                  <FileUploadField
                    label="Answer key PDF"
                    description="Upload the answer key document"
                    accept="application/pdf"
                    file={answerKeyFile}
                    onFileSelect={(file) => handleFileSelect(file, setAnswerKeyFile)}
                    required
                  />
                  {answerKeyFile && (
                    <div style={{ marginTop: '0.5rem' }}>
                      <Button
                        color="secondary"
                        size="small"
                        withBackground={false}
                        onClick={() => setPreviewFile(answerKeyFile)}
                      >
                        <Eye size={14} /> Preview
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              <Flex gap="small">
                <Button
                  color="primary"
                  onClick={handleRun}
                  interaction={!questionFile || !answerKeyFile || isStarting ? "disabled" : "enabled"}
                >
                  {isStarting ? <Loader2 className="spin" size={16} /> : <Shield size={16} />}
                  {isStarting ? " Starting…" : " Run Assessment"}
                </Button>
                <Button
                  color="secondary"
                  onClick={() => {
                    setQuestionFile(null);
                    setAnswerKeyFile(null);
                  }}
                >
                  Clear
                </Button>
              </Flex>
            </PageSection>
          </Grid.Col>
          )}

          <Grid.Col width={viewMode === "readonly" ? 12 : { small: 12, medium: 12, large: 6, xlarge: 6 }}>
            <PageSection
              title="Progress"
              subtitle={`${completedStages} of ${stageTimeline.length} stages`}
              actions={
                <Button
                  color="secondary"
                  withBackground={false}
                  onClick={() => activeRunId && refreshStatus(activeRunId)}
                >
                  <RefreshCcw size={16} /> Refresh
                </Button>
              }
            >
              <View margin="0 0 large">
                <ProgressBar
                  label="Overall progress"
                  valueNow={completedStages}
                  valueMax={stageTimeline.length}
                  formatDisplayedValue={(now, max) => `${now}/${max} stages (${progressPercent}%)`}
                  color="brand"
                  size="small"
                />
              </View>

              <View as="div">
                {stageTimeline.map((stage) => (
                  <View
                    key={stage.key}
                    as="div"
                    padding="x-small small"
                    margin="0 0 xx-small"
                    background="primary"
                    borderRadius="small"
                    borderWidth="small"
                  >
                    <Flex alignItems="center" justifyItems="space-between">
                      <Flex alignItems="center" gap="x-small">
                        <div
                          style={{
                            minWidth: '1.5rem',
                            height: '1.5rem',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                          }}
                        >
                          {stage.status === "running" ? (
                            <Loader2
                              size={18}
                              style={{
                                animation: 'spin 1s linear infinite',
                                color: '#FF7F32'
                              }}
                            />
                          ) : stage.status === "completed" ? (
                            <CheckCircle2 size={18} color="#22c55e" />
                          ) : stage.status === "failed" ? (
                            <AlertTriangle size={18} color="#ef4444" />
                          ) : (
                            <Clock size={18} color="#94a3b8" />
                          )}
                        </div>
                        <View>
                          <Text weight="normal" size="small">{stage.label}</Text>
                          <br />
                          <Text size="x-small" color="secondary">
                            {stage.status === "running"
                              ? "In progress"
                              : stage.status === "completed"
                              ? "Complete"
                              : stage.status === "failed"
                              ? "Check logs"
                              : "Queued"}
                          </Text>
                        </View>
                      </Flex>
                      <StatusPill status={stage.status as any} />
                    </Flex>
                  </View>
                ))}
              </View>
            </PageSection>

            <div style={{ marginTop: '1rem' }}>
              <PageSection title="Files">
                {/* File Filters */}
                <div style={{
                  display: 'inline-flex',
                  backgroundColor: '#f5f5f5',
                  borderRadius: '0.5rem',
                  padding: '0.25rem',
                  gap: '0.25rem',
                  marginBottom: '1.5rem'
                }}>
                  {[
                    { id: 'all', label: 'All files' },
                    { id: 'assessments', label: 'Assessments' },
                    { id: 'shielded', label: 'Shielded' },
                    { id: 'reports', label: 'Reports' }
                  ].map((option) => (
                    <button
                      key={option.id}
                      onClick={() => setFileFilter(option.id as typeof fileFilter)}
                      style={{
                        padding: '0.5rem 1.25rem',
                        border: 'none',
                        borderRadius: '0.375rem',
                        backgroundColor: fileFilter === option.id ? '#FF7F32' : 'transparent',
                        color: fileFilter === option.id ? '#ffffff' : '#666666',
                        fontWeight: fileFilter === option.id ? '600' : '400',
                        fontSize: '0.875rem',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        fontFamily: 'inherit'
                      }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>

                {filteredArtifacts.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {filteredArtifacts.map((row) => (
                      <div
                        key={row.key}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.75rem 1rem',
                          backgroundColor: '#f9f9f9',
                          borderRadius: '0.5rem',
                          border: '1px solid #e0e0e0',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <Text weight="normal" size="small" style={{ color: '#333333' }}>
                              {row.label}
                            </Text>
                            {row.method && (
                              <span style={{
                                fontSize: '0.75rem',
                                color: '#666666',
                                backgroundColor: '#e0e0e0',
                                padding: '0.125rem 0.5rem',
                                borderRadius: '0.25rem'
                              }}>
                                {row.method}
                              </span>
                            )}
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          <StatusPill status={row.status as any} />
                          <Button
                            color="secondary"
                            size="small"
                            withBackground={false}
                            onClick={() => setSelectedArtifact(row)}
                            interaction={!row.relativePath ? "disabled" : "enabled"}
                          >
                            Preview
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ padding: '2rem', textAlign: 'center' }}>
                    <Text color="secondary" size="small">No files available yet</Text>
                  </div>
                )}
              </PageSection>
            </div>
          </Grid.Col>
        </Grid.Row>
      </Grid>

      <ArtifactPreviewModal artifact={selectedArtifact} runId={activeRunId ?? undefined} onClose={() => setSelectedArtifact(null)} />
    </LTIShell>
  );
};

export default Dashboard;
