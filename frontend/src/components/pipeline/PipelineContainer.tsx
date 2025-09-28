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

  const activeStage = status?.current_stage ?? "smart_reading";
  const [selectedStage, setSelectedStage] = useState<PipelineStageName>(activeStage as PipelineStageName);

  useEffect(() => {
    setSelectedStage(activeStage as PipelineStageName);
  }, [activeStage]);

  const ActiveStageComponent = useMemo(() => {
    return stageComponentMap[selectedStage] ?? SmartReadingPanel;
  }, [selectedStage]);

  return (
    <div className="pipeline-container">
      <ProgressTracker
        stages={status?.stages ?? []}
        isLoading={isLoading}
        onStageSelect={(stage) => setSelectedStage(stage as PipelineStageName)}
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
