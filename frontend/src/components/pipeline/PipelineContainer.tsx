import * as React from "react";
import { useEffect, useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { PipelineStageName } from "@services/types/pipeline";
import ProgressTracker from "@components/shared/ProgressTracker";
import SmartReadingPanel from "./SmartReadingPanel";
import ContentDiscoveryPanel from "./ContentDiscoveryPanel";
import SmartSubstitutionPanel from "./SmartSubstitutionPanel";
import EffectivenessTestPanel from "./EffectivenessTestPanel";
import EnhancementMethodPanel from "./EnhancementMethodPanel";
import PdfCreationPanel from "./PdfCreationPanel";
import ResultsPanel from "./ResultsPanel";

const stageComponentMap: Record<PipelineStageName, React.ComponentType> = {
  smart_reading: SmartReadingPanel,
  content_discovery: ContentDiscoveryPanel,
  smart_substitution: SmartSubstitutionPanel,
  effectiveness_testing: EffectivenessTestPanel,
  document_enhancement: EnhancementMethodPanel,
  pdf_creation: PdfCreationPanel,
  results_generation: ResultsPanel,
};

const PipelineContainer: React.FC = () => {
  const { status, isLoading } = usePipeline();

  const activeStage = status?.status === "paused_for_mapping"
    ? "smart_substitution"
    : (status?.current_stage ?? "smart_reading");
  const [selectedStage, setSelectedStage] = useState<PipelineStageName>(activeStage as PipelineStageName);
  const [autoFollow, setAutoFollow] = useState(true);

  useEffect(() => {
    // Only auto-follow if stage is actively running, not when completed
    const currentStageData = status?.stages.find(s => s.name === activeStage);
    const isRunning = currentStageData?.status === 'running';
    const isPending = status?.status === 'pending';

    // Auto-navigate to the active stage when running OR when freshly created (pending)
    if (autoFollow && (isRunning || isPending)) {
      setSelectedStage(activeStage as PipelineStageName);
    }

    // Disable autoFollow when stage completes to prevent auto-advance
    if (currentStageData?.status === 'completed') {
      setAutoFollow(false);
    }
  }, [activeStage, autoFollow, status?.stages, status?.status]);

  useEffect(() => {
    if (!status) {
      setSelectedStage("content_discovery");
      setAutoFollow(true);
    }
  }, [status]);

  useEffect(() => {
    const runStatus = status?.status;
    if (!runStatus) {
      return;
    }
    if (runStatus === "paused_for_mapping") {
      setAutoFollow(false);
    } else if (runStatus !== "paused_for_mapping") {
      setAutoFollow(true);
    }
  }, [status?.status]);

  const ActiveStageComponent = useMemo(() => {
    return stageComponentMap[selectedStage] ?? SmartReadingPanel;
  }, [selectedStage]);

  return (
    <div className="pipeline-container">
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
      <div className="pipeline-stage-panel">
        <ActiveStageComponent />
      </div>
    </div>
  );
};

export default PipelineContainer;
