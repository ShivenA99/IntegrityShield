import * as React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";

import { usePipeline } from "@hooks/usePipeline";
import { PipelineStageName } from "@services/types/pipeline";
import ProgressTracker from "@components/shared/ProgressTracker";
import { updatePipelineConfig } from "@services/api/pipelineApi";
import AttackVariantPalette from "./AttackVariantPalette";
import SmartReadingPanel from "./SmartReadingPanel";
import ContentDiscoveryPanel from "./ContentDiscoveryPanel";
import SmartSubstitutionPanel from "./SmartSubstitutionPanel";
import PdfCreationPanel from "./PdfCreationPanel";
import ClassroomManagerPanel from "./ClassroomManagerPanel";
import ClassroomEvaluationPanel from "./ClassroomEvaluationPanel";

const LATEX_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
] as const;

const LATEX_METHOD_SET = new Set<string>(LATEX_METHODS);

const stageComponentMap: Partial<Record<PipelineStageName, React.ComponentType>> = {
  smart_reading: SmartReadingPanel,
  content_discovery: ContentDiscoveryPanel,
  smart_substitution: SmartSubstitutionPanel,
  pdf_creation: PdfCreationPanel,
  classroom_dataset: ClassroomManagerPanel,
  classroom_evaluation: ClassroomEvaluationPanel,
};

const PipelineContainer: React.FC = () => {
  const {
    status,
    isLoading,
    preferredStage,
    setPreferredStage,
    activeRunId,
    refreshStatus,
  } = usePipeline();

  const [selectedStage, setSelectedStage] = useState<PipelineStageName>("smart_reading");
  const [autoFollow, setAutoFollow] = useState(true);
  const [isUpdatingAttacks, setIsUpdatingAttacks] = useState(false);
  const [attackMessage, setAttackMessage] = useState<string | null>(null);
  const [attackError, setAttackError] = useState<string | null>(null);
  const [hasInitializedStage, setHasInitializedStage] = useState(false);
  const messageTimerRef = useRef<number | null>(null);

  const runId = status?.run_id ?? activeRunId ?? null;

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
  const attacksLocked =
    Boolean((status?.pipeline_config as Record<string, unknown> | undefined)?.attacks_locked) ||
    Boolean(pdfStage && pdfStage.status && pdfStage.status !== "pending");

  const classrooms = status?.classrooms ?? [];
  const enhancedCount = useMemo(() => {
    const structured = status?.structured_data as Record<string, any> | undefined;
    const manipulation = structured?.manipulation_results;
    const enhanced = manipulation?.enhanced_pdfs;
    if (enhanced && typeof enhanced === "object") {
      return Object.keys(enhanced).length;
    }
    return 0;
  }, [status?.structured_data]);

  const hasAttackedPdf = Boolean(status?.classroom_progress?.has_attacked_pdf || enhancedCount > 0);

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

    if (!autoFollow) {
      return;
    }

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
    if (!preferredStage) {
      return;
    }
    setSelectedStage(preferredStage);
    setAutoFollow(false);
    setPreferredStage(null);
  }, [preferredStage, setPreferredStage]);

  useEffect(() => {
    if (!status) {
      return;
    }
    if (status.status === "completed" && status.current_stage === "results_generation") {
      setSelectedStage("pdf_creation");
      setAutoFollow(false);
    }
  }, [status?.status, status?.current_stage]);

  const trackerStages = useMemo(() => status?.stages ?? [], [status?.stages]);

  const datasetStageStatus: "locked" | "pending" | "completed" = !hasAttackedPdf
    ? "locked"
    : classrooms.length > 0
      ? "completed"
      : "pending";

  const completedEvaluations = classrooms.filter(
    (classroom) => classroom.evaluation && classroom.evaluation.status === "completed"
  );
  const pendingEvaluations = classrooms.filter(
    (classroom) => classroom.evaluation && classroom.evaluation.status !== "completed"
  );

  const evaluationStageStatus: "locked" | "pending" | "completed" =
    datasetStageStatus === "locked"
      ? "locked"
      : completedEvaluations.length > 0
        ? "completed"
        : classrooms.length > 0
          ? "pending"
          : "locked";

  const classroomCards = useMemo(
    () => [
      {
        key: "classroom_dataset" as PipelineStageName,
        label: "Classroom Datasets",
        status: datasetStageStatus,
        caption:
          datasetStageStatus === "locked"
            ? "Generate an attacked PDF first"
            : classrooms.length
              ? `${classrooms.length} dataset${classrooms.length === 1 ? "" : "s"} ready`
              : "No classroom datasets yet",
        tooltip:
          datasetStageStatus === "locked"
            ? "Create at least one attacked PDF variant before seeding classrooms."
            : "Review and manage synthetic or imported classroom data sets.",
      },
      {
        key: "classroom_evaluation" as PipelineStageName,
        label: "Classroom Evaluation",
        status: evaluationStageStatus,
        caption:
          evaluationStageStatus === "locked"
            ? "Generate a classroom dataset first"
            : completedEvaluations.length
              ? `${completedEvaluations.length} evaluation${completedEvaluations.length === 1 ? "" : "s"} completed`
              : pendingEvaluations.length
                ? `${pendingEvaluations.length} evaluation${pendingEvaluations.length === 1 ? "" : "s"} in progress`
                : "Run analysis for a classroom to view results",
        tooltip:
          evaluationStageStatus === "locked"
            ? "Set up a classroom dataset before running evaluation."
            : "Run and review cheating analytics per classroom.",
      },
    ],
    [classrooms, datasetStageStatus, evaluationStageStatus, completedEvaluations.length, pendingEvaluations.length]
  );

  const ActiveStageComponent = useMemo(() => {
    return (stageComponentMap[selectedStage] as React.ComponentType) ?? SmartReadingPanel;
  }, [selectedStage]);

  return (
    <div className="pipeline-container">
      <div className="pipeline-stage-strip">
        <div className="pipeline-stage-strip__tracker">
          <ProgressTracker
            stages={trackerStages}
            isLoading={isLoading}
            onStageSelect={(stage) => {
              handleStageSelect(stage as PipelineStageName);
            }}
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

      <div className="classroom-stage-strip">
        {classroomCards.map((card) => (
          <button
            key={card.key}
            type="button"
            className={clsx(
              "classroom-stage",
              `is-${card.status}`,
              card.key === "classroom_evaluation" && "classroom-stage--evaluation",
              selectedStage === card.key && "is-active"
            )}
            onClick={() => handleStageSelect(card.key)}
            disabled={card.status === "locked"}
            title={card.tooltip}
          >
            <span className="classroom-stage__label">{card.label}</span>
            <span className="classroom-stage__caption">{card.caption}</span>
          </button>
        ))}
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
