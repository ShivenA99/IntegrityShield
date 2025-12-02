import * as React from "react";
import clsx from "clsx";

import type { PipelineStageState, PipelineStageName } from "@services/types/pipeline";

interface ProgressTrackerProps {
  stages: PipelineStageState[];
  isLoading?: boolean;
  selectedStage?: string;
  onStageSelect?: (stage: string) => void;
  currentStage?: string;
  renderStageActions?: (stage: PipelineStageName) => React.ReactNode;
  mode?: string;
}

const DETECTION_STAGE_ORDER: PipelineStageName[] = [
  "smart_reading",
  "content_discovery",
  "smart_substitution",
  "pdf_creation",
];

const PREVENTION_STAGE_ORDER: PipelineStageName[] = [
  "smart_reading",
  "content_discovery",
  "document_enhancement",
  "pdf_creation",
];

const stageLabels: Record<PipelineStageName, string> = {
  smart_reading: "Smart Reading",
  content_discovery: "Content Discovery",
  smart_substitution: "Strategy",
  effectiveness_testing: "Effectiveness Testing",
  document_enhancement: "Font Generation",
  pdf_creation: "Download PDFs",
  results_generation: "Results",
};

const ProgressTracker: React.FC<ProgressTrackerProps> = ({
  stages,
  isLoading,
  selectedStage,
  onStageSelect,
  currentStage,
  renderStageActions,
  mode = "detection",
}) => {
  const stageMap = new Map(stages.map((stage) => [stage.name, stage]));
  const isPreventionMode = mode === "prevention";
  const visibleStages: PipelineStageName[] = isPreventionMode
    ? [...PREVENTION_STAGE_ORDER]
    : [...DETECTION_STAGE_ORDER];

  return (
    <div className="progress-tracker">
      {visibleStages.map((name, index) => {
        const stage = stageMap.get(name);
        const status = stage?.status ?? "pending";
        const label = stageLabels[name] || name.replace(/_/g, " ");
        const statusLabel =
          status === "completed"
            ? "Complete"
            : status === "running"
            ? "In progress"
            : status === "failed"
            ? "Error"
            : "Pending";
        const isSelected = selectedStage === name;
        const isCurrent = currentStage === name;

        return (
          <div
            key={name}
            className={clsx(
              "progress-tracker__item",
              `state-${status}`,
              isSelected && "is-selected",
              isCurrent && "is-current"
            )}
          >
            <button
              type="button"
              className={[
                "progress-tracker__segment",
                `state-${status}`,
                isSelected ? "is-selected" : "",
                isCurrent ? "is-current" : "",
              ]
                .join(" ")
                .trim()}
              onClick={() => onStageSelect?.(name)}
              title={`${label} • ${statusLabel}`}
            >
              <span
                className="progress-tracker__circle"
                data-step={index + 1}
                data-status={status}
                aria-hidden="true"
              />
              <span className="progress-tracker__meta">
                <span className="progress-tracker__label">{label}</span>
                <span className="progress-tracker__status">{statusLabel}</span>
              </span>
            </button>
            <div className="progress-tracker__bar">
              <span className="progress-tracker__bar-fill" />
            </div>
            {renderStageActions ? (
              <div className="progress-tracker__actions">{renderStageActions(name)}</div>
            ) : null}
            {index < visibleStages.length - 1 ? <span className="progress-tracker__connector" /> : null}
          </div>
        );
      })}
      {isLoading ? <div className="progress-tracker__loading">Updating…</div> : null}
    </div>
  );
};

export default ProgressTracker;
