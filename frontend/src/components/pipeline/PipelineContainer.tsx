import * as React from "react";
import { useEffect, useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { PipelineStageName } from "@services/types/pipeline";
import ProgressTracker from "@components/shared/ProgressTracker";
import SmartReadingPanel from "./SmartReadingPanel";
import ContentDiscoveryPanel from "./ContentDiscoveryPanel";
import SmartSubstitutionPanel from "./SmartSubstitutionPanel";
import PdfCreationPanel from "./PdfCreationPanel";

const stageComponentMap: Partial<Record<PipelineStageName, React.ComponentType>> = {
  smart_reading: SmartReadingPanel,
  content_discovery: ContentDiscoveryPanel,
  smart_substitution: SmartSubstitutionPanel,
  pdf_creation: PdfCreationPanel,
};

const PipelineContainer: React.FC = () => {
  const { status, isLoading } = usePipeline();

  const [selectedStage, setSelectedStage] = useState<PipelineStageName>("smart_reading");
  const [autoFollow, setAutoFollow] = useState(true);

  useEffect(() => {
    if (!status) {
      setSelectedStage("smart_reading");
      setAutoFollow(true);
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
    // Keep focus on the most recent completed stage that the UI can render.
    const latestCompleted = [...status.stages]
      .reverse()
      .find((stage) => stage.status === "completed" && stageComponentMap[stage.name as PipelineStageName]);
    if (latestCompleted) {
      setSelectedStage(latestCompleted.name as PipelineStageName);
    }
  }, [status, autoFollow, selectedStage]);

  useEffect(() => {
    if (!status) {
      setSelectedStage("smart_reading");
      setAutoFollow(true);
    }
  }, [status]);

  useEffect(() => {
    if (!status) {
      return;
    }
    if (status.status === "completed" && status.current_stage === "results_generation") {
      setSelectedStage("pdf_creation");
      setAutoFollow(false);
    }
  }, [status?.status, status?.current_stage]);

  const ActiveStageComponent = useMemo(() => {
    return (stageComponentMap[selectedStage] as React.ComponentType) ?? SmartReadingPanel;
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
