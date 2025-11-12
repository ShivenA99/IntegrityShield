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
  "pdf_creation",
];

const stageLabels: Record<PipelineStageName, string> = {
  smart_reading: "Smart Reading",
  content_discovery: "Content Discovery",
  smart_substitution: "Smart Substitution",
  effectiveness_testing: "Effectiveness Testing",
  document_enhancement: "Document Enhancement",
  pdf_creation: "PDF Creation",
  results_generation: "Results",
};

const ProgressTracker: React.FC<ProgressTrackerProps> = ({ stages, isLoading, selectedStage, onStageSelect, currentStage }) => {
  const stageMap = new Map(stages.map((stage) => [stage.name, stage]));
  const hiddenStages: PipelineStageName[] = ["effectiveness_testing", "document_enhancement", "results_generation"];

  const extraStages = stages
    .map((stage) => stage.name)
    .filter((name) => !baseStageOrder.includes(name) && !hiddenStages.includes(name as PipelineStageName));

  const orderedUnique = [...baseStageOrder, ...extraStages];
  const visibleStages: PipelineStageName[] = orderedUnique.filter(
    (name, index) => orderedUnique.indexOf(name) === index
  );

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
            <div className="stage-label">{stageLabels[name] || name.replace(/_/g, " ")}</div>
          </button>
        );
      })}
      {isLoading ? <div className="tracker-loading">Updating…</div> : null}
    </div>
  );
};

export default ProgressTracker;
