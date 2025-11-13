import * as React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { PipelineStageName } from "@services/types/pipeline";
import ProgressTracker from "@components/shared/ProgressTracker";
import { updatePipelineConfig } from "@services/api/pipelineApi";
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

const stageComponentMap: Partial<Record<PipelineStageName, React.ComponentType>> = {
  smart_reading: SmartReadingPanel,
  content_discovery: ContentDiscoveryPanel,
  smart_substitution: SmartSubstitutionPanel,
  pdf_creation: PdfCreationPanel,
};

const PipelineContainer: React.FC = () => {
  const { status, isLoading, preferredStage, setPreferredStage, activeRunId, refreshStatus } = usePipeline();

  const [selectedStage, setSelectedStage] = useState<PipelineStageName>("smart_reading");
  const [autoFollow, setAutoFollow] = useState(true);
  const [isUpdatingAttacks, setIsUpdatingAttacks] = useState(false);
  const [attackMessage, setAttackMessage] = useState<string | null>(null);
  const [attackError, setAttackError] = useState<string | null>(null);
  const messageTimerRef = useRef<number | null>(null);
  const [hasInitializedStage, setHasInitializedStage] = useState(false);

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

  const ActiveStageComponent = useMemo(() => {
    return (stageComponentMap[selectedStage] as React.ComponentType) ?? SmartReadingPanel;
  }, [selectedStage]);

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

  useEffect(() => {
    if (!status) {
      setSelectedStage("smart_reading");
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
    if (preferredStage) {
      setSelectedStage(preferredStage);
      setAutoFollow(false);
      setPreferredStage(null);
    }
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

  return (
    <div className="pipeline-container">
      <div className="pipeline-stage-strip">
        <div className="pipeline-stage-strip__tracker">
          <ProgressTracker
            stages={status?.stages ?? []}
            isLoading={isLoading}
            onStageSelect={(stage) => {
              setSelectedStage(stage as PipelineStageName);
              setAutoFollow(false);
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

      <div className="pipeline-stage-panel">
        <div key={selectedStage} className="stage-transition">
          <ActiveStageComponent />
        </div>
      </div>
    </div>
  );
};

export default PipelineContainer;
