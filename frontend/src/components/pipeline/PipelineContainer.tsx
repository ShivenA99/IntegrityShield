import * as React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { FileText, Layers, RefreshCcw, RotateCcw, BarChart2 } from "lucide-react";

import { usePipeline } from "@hooks/usePipeline";
import { PipelineStageName } from "@services/types/pipeline";
import ProgressTracker from "@components/shared/ProgressTracker";
import { updatePipelineConfig } from "@services/api/pipelineApi";
import DeveloperToggle from "@components/layout/DeveloperToggle";
import AttackVariantPalette from "./AttackVariantPalette";
import SmartReadingPanel from "./SmartReadingPanel";
import ContentDiscoveryPanel from "./ContentDiscoveryPanel";
import SmartSubstitutionPanel from "./SmartSubstitutionPanel";
import PdfCreationPanel from "./PdfCreationPanel";

const LATEX_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
] as const;

const LATEX_METHOD_SET = new Set<string>(LATEX_METHODS);

const CORE_STAGE_LABELS: Record<string, string> = {
  smart_reading: "Smart Reading",
  content_discovery: "Content Discovery",
  smart_substitution: "Strategy",
  pdf_creation: "Download PDFs",
};

const stageComponentMap: Partial<Record<PipelineStageName, React.ComponentType>> = {
  smart_reading: SmartReadingPanel,
  content_discovery: ContentDiscoveryPanel,
  smart_substitution: SmartSubstitutionPanel,
  pdf_creation: PdfCreationPanel,
};

const PipelineContainer: React.FC = () => {
  const {
    status,
    isLoading,
    preferredStage,
    preferredStageToken,
    setPreferredStage,
    activeRunId,
    refreshStatus,
    resetActiveRun,
  } = usePipeline();
  const navigate = useNavigate();

  const [selectedStage, setSelectedStage] = useState<PipelineStageName>("smart_reading");
  const [autoFollow, setAutoFollow] = useState(true);
  const [isUpdatingAttacks, setIsUpdatingAttacks] = useState(false);
  const [attackMessage, setAttackMessage] = useState<string | null>(null);
  const [attackError, setAttackError] = useState<string | null>(null);
  const [hasInitializedStage, setHasInitializedStage] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const messageTimerRef = useRef<number | null>(null);

  const runId = status?.run_id ?? activeRunId ?? null;
  const documentInfo = (status?.structured_data as Record<string, any> | undefined)?.document;
  const classrooms = status?.classrooms ?? [];

  const enhancementMethods = useMemo(() => {
    const raw = status?.pipeline_config?.enhancement_methods;
    if (Array.isArray(raw)) {
      return raw.map((entry) => String(entry));
    }
    return [];
  }, [status?.pipeline_config]);

  const selectedLatexMethods = useMemo(() => {
    const selected = LATEX_METHODS.filter((method) => enhancementMethods.includes(method));
    return selected.length ? selected : ["latex_dual_layer"];
  }, [enhancementMethods]);

  const pdfStage = status?.stages.find((stage) => stage.name === "pdf_creation");
  const manipulationResults = ((status?.structured_data as Record<string, any> | undefined)?.manipulation_results ??
    {}) as Record<string, any>;
  const enhancedPdfs = (manipulationResults?.enhanced_pdfs ?? {}) as Record<string, any>;
  const availableDownloads = useMemo(() => {
    return Object.entries(enhancedPdfs)
      .filter(([, meta]) => {
        if (!meta) return false;
        const candidate = meta.relative_path || meta.path || meta.file_path;
        return Boolean(candidate);
      })
      .map(([methodKey]) => methodKey);
  }, [enhancedPdfs]);
  const downloadCount = availableDownloads.length;
  const hasDownloadableAssets = downloadCount > 0;
  const pdfStageStatus = pdfStage?.status ?? "pending";
  const classroomsReady = hasDownloadableAssets && pdfStageStatus === "completed";
  const evaluationReady = classrooms.length > 0;
  const completedEvaluations = useMemo(
    () => classrooms.filter((entry: any) => entry?.evaluation?.status === "completed").length,
    [classrooms]
  );
  const variantCountLabel = selectedLatexMethods.length ? String(selectedLatexMethods.length) : "—";
  const downloadCountLabel = hasDownloadableAssets ? String(downloadCount) : "—";
  const classroomCountLabel = classrooms.length
    ? `${classrooms.length} dataset${classrooms.length === 1 ? "" : "s"}`
    : "—";
  const evaluationCountLabel = evaluationReady
    ? `${completedEvaluations}/${classrooms.length}`
    : "—";

  const attacksLocked =
    Boolean((status?.pipeline_config as Record<string, unknown> | undefined)?.attacks_locked) ||
    Boolean(pdfStage && pdfStage.status && pdfStage.status !== "pending");

  useEffect(() => {
    return () => {
      if (messageTimerRef.current) {
        window.clearTimeout(messageTimerRef.current);
        messageTimerRef.current = null;
      }
    };
  }, []);

  const handleToggleAttack = useCallback(
    async (methodId: (typeof LATEX_METHODS)[number]) => {
      if (!runId || attacksLocked || isUpdatingAttacks) return;

      const currentSet = new Set(selectedLatexMethods);
      const alreadySelected = currentSet.has(methodId);

      if (alreadySelected && currentSet.size === 1) {
        setAttackError("Select at least one variant.");
        setAttackMessage(null);
        return;
      }

      if (alreadySelected) {
        currentSet.delete(methodId);
      } else {
        currentSet.add(methodId);
      }

      const normalized = LATEX_METHODS.filter((method) => currentSet.has(method));
      const preserved = enhancementMethods.filter((method) => !LATEX_METHOD_SET.has(method));
      const updatedList = [...normalized, ...preserved];
      if (!updatedList.includes("pymupdf_overlay")) {
        updatedList.push("pymupdf_overlay");
      }

      setIsUpdatingAttacks(true);
      setAttackError(null);
      setAttackMessage(null);
      try {
        await updatePipelineConfig(runId, { enhancement_methods: updatedList });
        await refreshStatus(runId, { quiet: true }).catch(() => undefined);
        const action = alreadySelected ? "disabled" : "enabled";
        setAttackMessage(`${methodId.replace(/_/g, " ")} ${action}.`);
        messageTimerRef.current = window.setTimeout(() => {
          setAttackMessage(null);
          messageTimerRef.current = null;
        }, 3200);
      } catch (err: any) {
        const message = err?.response?.data?.error || err?.message || String(err);
        setAttackError(`Failed to update attack selection: ${message}`);
      } finally {
        setIsUpdatingAttacks(false);
      }
    },
    [runId, attacksLocked, isUpdatingAttacks, selectedLatexMethods, enhancementMethods, refreshStatus]
  );

  const handleStageSelect = useCallback(
    (stage: PipelineStageName) => {
      if (!stageComponentMap[stage]) return;
      setSelectedStage(stage);
      setAutoFollow(false);
    },
    []
  );

  useEffect(() => {
    if (!status) {
      setSelectedStage("smart_reading");
      setAutoFollow(true);
      setHasInitializedStage(false);
      return;
    }

    if (!hasInitializedStage) {
      const currentStage = status.current_stage as PipelineStageName | undefined;
      if (currentStage && stageComponentMap[currentStage]) {
        setSelectedStage(currentStage);
      } else {
        const firstAvailable = status.stages.find((stage) =>
          Boolean(stageComponentMap[stage.name as PipelineStageName])
        );
        setSelectedStage((firstAvailable?.name as PipelineStageName) ?? "smart_reading");
      }
      setHasInitializedStage(true);
      return;
    }

    if (!autoFollow) return;

    const runningStage = status.stages.find(
      (stage) => stage.status === "running" && stageComponentMap[stage.name as PipelineStageName]
    );
    if (runningStage) {
      setSelectedStage(runningStage.name as PipelineStageName);
      return;
    }

    const currentStage = status.current_stage as PipelineStageName | undefined;
    if (currentStage && stageComponentMap[currentStage]) {
      setSelectedStage(currentStage);
      return;
    }

    const latestCompleted = [...status.stages]
      .reverse()
      .find((stage) => stage.status === "completed" && stageComponentMap[stage.name as PipelineStageName]);
    if (latestCompleted) {
      setSelectedStage(latestCompleted.name as PipelineStageName);
    }
  }, [status, autoFollow, hasInitializedStage]);

  useEffect(() => {
    if (!preferredStage) return;
    if (stageComponentMap[preferredStage]) {
      setSelectedStage(preferredStage);
      setAutoFollow(false);
    }
    setPreferredStage(null);
  }, [preferredStage, preferredStageToken, setPreferredStage]);

  useEffect(() => {
    if (!status) return;
    if (status.status === "completed" && status.current_stage === "results_generation") {
      setSelectedStage("pdf_creation");
      setAutoFollow(false);
    }
  }, [status?.status, status?.current_stage]);

  const trackerStages = useMemo(() => status?.stages ?? [], [status?.stages]);
  const runLabel = runId ? `${runId.slice(0, 6)}…${runId.slice(-4)}` : "No active run";
  const currentStageLabel = status?.current_stage
    ? CORE_STAGE_LABELS[status.current_stage] ?? status.current_stage.replace(/_/g, " ")
    : "—";
  const pipelineStatusLabel = status?.status ? status.status.replace(/_/g, " ") : "idle";
  const classroomActionTitle = classroomsReady
    ? "Manage classroom datasets"
    : hasDownloadableAssets
    ? "Complete the Download PDFs stage to unlock classrooms"
    : "Generate attacked PDFs before creating classrooms";
  const evaluationActionTitle = evaluationReady
    ? "Review classroom evaluations"
    : "Create at least one classroom dataset to enable evaluation";

  const handleRefresh = useCallback(async () => {
    if (!runId || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await refreshStatus(runId, { quiet: true });
    } finally {
      setIsRefreshing(false);
    }
  }, [isRefreshing, refreshStatus, runId]);

  const handleReset = useCallback(async () => {
    if (!runId) {
      navigate("/dashboard");
      return;
    }
    const confirmMessage = `Reset current run${documentInfo?.filename ? ` (${documentInfo.filename})` : ""}?`;
    if (!window.confirm(confirmMessage)) {
      return;
    }
    await resetActiveRun();
    navigate("/dashboard");
  }, [documentInfo?.filename, navigate, resetActiveRun, runId]);

  const ActiveStageComponent = useMemo(() => {
    return (stageComponentMap[selectedStage] as React.ComponentType) ?? SmartReadingPanel;
  }, [selectedStage]);

  return (
    <div className="pipeline-container">
      <div className="pipeline-topbar">
        <div className="pipeline-topbar__meta">
          <div className="pipeline-topbar__heading">
            <div className="pipeline-topbar__title" title={runId ?? undefined}>
              <RotateCcw size={16} aria-hidden="true" />
              <span>{runLabel}</span>
            </div>
            <span
              className={clsx("pipeline-topbar__status", status?.status && `status-${status.status}`)}
              title={`Pipeline status: ${pipelineStatusLabel}`}
            >
              {pipelineStatusLabel}
            </span>
          </div>
          <div className="pipeline-topbar__chips">
            <span
              className="pipeline-chip"
              title={documentInfo?.filename ? `Source document: ${documentInfo.filename}` : "No source loaded"}
            >
              <FileText size={14} aria-hidden="true" />
              {documentInfo?.filename ?? "No source loaded"}
            </span>
            <span className="pipeline-chip" title={`Current stage: ${currentStageLabel}`}>
              Stage · {currentStageLabel}
            </span>
            <span className="pipeline-chip" title={`${selectedLatexMethods.length || 0} latex variant(s) enabled`}>
              Variants · {variantCountLabel}
            </span>
            <span
              className={clsx("pipeline-chip", hasDownloadableAssets && "is-ready")}
              title={
                hasDownloadableAssets
                  ? `${downloadCount} downloadable asset${downloadCount === 1 ? "" : "s"} ready`
                  : "Queue Download PDFs to generate assets"
              }
            >
              Downloads · {downloadCountLabel}
            </span>
            <span
              className="pipeline-chip"
              title={`${classrooms.length} classroom dataset${classrooms.length === 1 ? "" : "s"}`}
            >
              Classrooms · {classroomCountLabel}
            </span>
            <span
              className="pipeline-chip"
              title={
                classrooms.length
                  ? `${completedEvaluations} of ${classrooms.length} evaluation${classrooms.length === 1 ? "" : "s"} completed`
                  : "No evaluations yet"
              }
            >
              Eval · {evaluationCountLabel}
            </span>
          </div>
        </div>
      <div className="pipeline-topbar__actions">
        <span className="icon-button__wrapper has-tooltip" data-tooltip="Refresh pipeline status">
          <button
            type="button"
            className="icon-button"
            onClick={handleRefresh}
            disabled={!runId || isRefreshing}
            aria-busy={isRefreshing}
            aria-label="Refresh pipeline status"
          >
            <RefreshCcw size={16} aria-hidden="true" />
          </button>
        </span>
        <DeveloperToggle />
        <span
          className="ghost-button__wrapper has-tooltip"
          data-tooltip={runId ? "Reset active run" : "No run to reset"}
        >
          <button
            type="button"
            onClick={handleReset}
            className="ghost-button"
            disabled={!runId}
            aria-label="Reset active run"
          >
            Reset Run
          </button>
        </span>
      </div>
      </div>

      <div className="pipeline-stage-strip">
        <div className="pipeline-stage-strip__tracker">
          <ProgressTracker
            stages={trackerStages}
            isLoading={isLoading}
            onStageSelect={(stage) => handleStageSelect(stage as PipelineStageName)}
            selectedStage={selectedStage}
            currentStage={status?.current_stage}
          />
        </div>
        <AttackVariantPalette
          selected={selectedLatexMethods}
          locked={attacksLocked}
          isUpdating={isUpdatingAttacks}
          onToggle={handleToggleAttack}
          message={attackMessage}
          error={attackError}
        />
      </div>

      <div className="pipeline-stage-actions">
        <div className="pipeline-stage-actions__item has-tooltip" data-tooltip={classroomActionTitle}>
          <button
            type="button"
            className="pipeline-stage-actions__button"
            onClick={() => navigate("/classrooms?view=datasets")}
            disabled={!classroomsReady}
            aria-label="Open classroom datasets"
          >
            <span className="pipeline-stage-actions__icon" aria-hidden="true">
              <Layers size={22} />
            </span>
            <div className="pipeline-stage-actions__label">
              <span>Classroom</span>
              <span className="pipeline-stage-actions__meta">{classroomCountLabel}</span>
            </div>
          </button>
        </div>
        <div className="pipeline-stage-actions__item has-tooltip" data-tooltip={evaluationActionTitle}>
          <button
            type="button"
            className="pipeline-stage-actions__button"
            onClick={() => navigate("/classrooms?view=evaluations")}
            disabled={!evaluationReady}
            aria-label="Open classroom evaluations"
          >
            <span className="pipeline-stage-actions__icon" aria-hidden="true">
              <BarChart2 size={22} />
            </span>
            <div className="pipeline-stage-actions__label">
              <span>Evaluation</span>
              <span className="pipeline-stage-actions__meta">
                {evaluationCountLabel === "—" ? "—" : `${evaluationCountLabel} complete`}
              </span>
            </div>
          </button>
        </div>
      </div>

      <div className="pipeline-stage-panel">
        <div key={selectedStage} className="stage-transition">
          <ActiveStageComponent />
        </div>
      </div>
    </div>
  );
};

export default PipelineContainer;
