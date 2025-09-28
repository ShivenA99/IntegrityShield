import * as React from "react";

import type { PipelineStageState, PipelineStageName } from "@services/types/pipeline";

interface ProgressTrackerProps {
  stages: PipelineStageState[];
  isLoading?: boolean;
  selectedStage?: string;
  onStageSelect?: (stage: string) => void;
  currentStage?: string;
}

const baseStageOrder: PipelineStageName[] = [
  "smart_reading",
  "content_discovery",
  "smart_substitution",
  "effectiveness_testing",
  "document_enhancement",
  "pdf_creation",
  "results_generation",
];

const ProgressTracker: React.FC<ProgressTrackerProps> = ({ stages, isLoading, selectedStage, onStageSelect, currentStage }) => {
  const stageMap = new Map(stages.map((stage) => [stage.name, stage]));
  const extraStages = stages
    .map((stage) => stage.name)
    .filter((name) => !baseStageOrder.includes(name));

  const orderedUnique = [...baseStageOrder, ...extraStages];
  const visibleStages: PipelineStageName[] = orderedUnique.filter((name, index) => orderedUnique.indexOf(name) === index);

  return (
    <div className="progress-tracker">
      {visibleStages.map((name) => {
        const stage = stageMap.get(name);
        const status = stage?.status ?? "pending";
        const isSelected = selectedStage === name;
        const isCurrent = currentStage === name;
        return (
          <button
            key={name}
            className={`stage ${status} ${isSelected ? "selected" : ""} ${isCurrent ? "current" : ""}`}
            onClick={() => onStageSelect?.(name)}
            type="button"
            title={isCurrent ? "Pipeline is here now" : undefined}
          >
            <div className="stage-icon">{status === "completed" ? "✔" : status === "running" || isCurrent ? "⏳" : "•"}</div>
            <div className="stage-label">{name.replace("_", " ")}</div>
          </button>
        );
      })}
      {isLoading ? <div className="tracker-loading">Updating…</div> : null}
    </div>
  );
};

export default ProgressTracker;
