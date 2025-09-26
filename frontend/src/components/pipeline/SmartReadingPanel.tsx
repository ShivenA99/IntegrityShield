import * as React from "react";
import { useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useNotifications } from "@contexts/NotificationContext";
import { validatePdfFile } from "@services/utils/validators";
import type { PipelineStageName } from "@services/types/pipeline";

const SmartReadingPanel: React.FC = () => {
  const { startPipeline, isLoading, error, status } = usePipeline();
  const { push } = useNotifications();
  const [file, setFile] = useState<File | null>(null);

  const previewUrl = useMemo(() => {
    if (!file) return null;
    const url = URL.createObjectURL(file);
    return url;
  }, [file]);

  React.useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // UI slider stages (single-select). Only show visible panels.
  const uiStageOrder = useMemo<PipelineStageName[]>(
    () => [
      "smart_reading",
      "content_discovery",
      "smart_substitution",
      "pdf_creation",
      "results_generation",
    ],
    []
  );

  const [selectedStage, setSelectedStage] = useState<PipelineStageName>(uiStageOrder[0]);

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0];
    if (!nextFile) return;
    const validationError = validatePdfFile(nextFile);
    if (validationError) {
      push({ title: "Upload failed", description: validationError, intent: "error" });
      return;
    }
    setFile(nextFile);
  };

  const computeTargetStages = (stopAt: PipelineStageName) => {
    const fullBackendOrder: PipelineStageName[] = [
      "smart_reading",
      "content_discovery",
      "answer_detection", // backend-only
      "smart_substitution",
      "document_enhancement", // backend-only
      "pdf_creation",
      "results_generation",
    ];
    const stopIndex = fullBackendOrder.indexOf(stopAt);
    return stopIndex >= 0 ? fullBackendOrder.slice(0, stopIndex + 1) : fullBackendOrder;
  };

  const handleStart = async () => {
    if (!file) {
      push({ title: "No file selected", intent: "warning" });
      return;
    }
    const runId = await startPipeline({
      file,
      config: {
        targetStages: computeTargetStages(selectedStage),
        aiModels: [],
        enhancementMethods: ["content_stream"],
        skipIfExists: true,
        parallelProcessing: true,
      },
    });
    if (runId) {
      push({ title: "Pipeline started", description: `Run ${runId} is in progress`, intent: "success" });
    }
  };

  return (
    <div className="panel smart-reading">
      <h2>📄 Smart Reading</h2>

      <div className="panel-card">
        <h4>Upload PDF</h4>
        <input type="file" accept="application/pdf" onChange={handleFile} />
        {previewUrl ? (
          <div style={{ marginTop: 12 }}>
            <iframe title="pdf-preview" src={previewUrl} style={{ width: "100%", height: 400, border: 0 }} />
          </div>
        ) : null}
      </div>

      <div className="controls-grid">
        <div>
          <h4>Pipeline Stages</h4>
          <div className="control-list" role="radiogroup" aria-label="Pipeline stage">
            {uiStageOrder.map((stage) => (
              <label key={stage} style={{ opacity: stage === "results_generation" ? 0.5 : 1 }}>
                <input
                  type="radio"
                  name="pipeline-stage"
                  checked={selectedStage === stage}
                  disabled={stage === "results_generation"}
                  onChange={() => setSelectedStage(stage)}
                />
                {stage.replace("_", " ")}
              </label>
            ))}
          </div>
        </div>

        <div>
          <h4>Enhancement Method</h4>
          <div className="control-list">
            {["content_stream"].map((method) => (
              <label key={method}>
                <input type="radio" name="enhancement" checked={method === "content_stream"} readOnly />
                {method.replace("_", " ")}
              </label>
            ))}
          </div>
        </div>
      </div>

      <button onClick={handleStart} disabled={isLoading || !file} className="primary">
        {isLoading ? "Starting…" : "Start Pipeline"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
};

export default SmartReadingPanel;
