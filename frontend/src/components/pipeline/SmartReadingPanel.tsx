import * as React from "react";
import { useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useNotifications } from "@contexts/NotificationContext";
import { validatePdfFile } from "@services/utils/validators";
import type { CorePipelineStageName } from "@services/types/pipeline";
import PageTitle from "@components/common/PageTitle";

const SmartReadingPanel: React.FC = () => {
  const { startPipeline, error, status } = usePipeline();
  const { push } = useNotifications();
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [answerKeyDragging, setAnswerKeyDragging] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [answerKeyFile, setAnswerKeyFile] = useState<File | null>(null);

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

  const handleFiles = (files: FileList | null) => {
    const nextFile = files?.[0];
    if (!nextFile) return;
    const validationError = validatePdfFile(nextFile);
    if (validationError) {
      push({ title: "Upload failed", description: validationError, intent: "error" });
      return;
    }
    setFile(nextFile);
  };

  const handleAnswerKeyFiles = (files: FileList | null) => {
    const nextFile = files?.[0];
    if (!nextFile) return;
    const validationError = validatePdfFile(nextFile);
    if (validationError) {
      push({ title: "Answer key upload failed", description: validationError, intent: "error" });
      return;
    }
    setAnswerKeyFile(nextFile);
  };

  const handleFileInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(event.target.files);
  };

  const handleAnswerKeyInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    handleAnswerKeyFiles(event.target.files);
  };

  const handleDrop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  };

  const handleAnswerKeyDrop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setAnswerKeyDragging(false);
    handleAnswerKeyFiles(event.dataTransfer.files);
  };

  const handleStart = async () => {
    if (isStarting) return;
    setIsStarting(true);
    const enhancementMethods = ["latex_dual_layer", "pymupdf_overlay"];
    const targetStages: CorePipelineStageName[] = ["smart_reading", "content_discovery", "smart_substitution"];

    const runId = await startPipeline({
      file: file ?? undefined,
      answerKeyFile: answerKeyFile ?? undefined,
      config: {
        targetStages,
        aiModels: [],
        enhancementMethods,
        skipIfExists: true,
        parallelProcessing: true,
      },
    });
    if (runId) {
      push({ title: "Pipeline started", description: `Run ${runId} is in progress`, intent: "success" });
    }
    setIsStarting(false);
  };

  const smartStage = status?.stages.find((item) => item.name === "smart_reading");
  const startDisabled = isStarting || smartStage?.status === "completed";
  const startLabel = smartStage?.status === "completed" ? "Completed" : isStarting ? "Starting…" : "Start";

  return (
    <div className="panel smart-reading">
      <header className="panel-header panel-header--tight">
        <PageTitle>Source Document</PageTitle>
        <div className="panel-actions">
          {status?.run_id ? <span className="badge tag-muted">Last run: {status.run_id}</span> : null}
          <button
            type="button"
            onClick={handleStart}
            disabled={startDisabled}
            className="primary-button"
            title={
              smartStage?.status === "completed"
                ? "Smart Reading has already finished for this run."
                : file
                ? "Begin processing the uploaded PDF"
                : "Start with current inputs"
            }
          >
            {startLabel}
          </button>
        </div>
      </header>

      <section className="panel-card upload-panel">
        <label
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`upload-panel__dropzone ${isDragging ? "is-dragging" : ""}`}
        >
          <input type="file" accept="application/pdf" onChange={handleFileInput} hidden />
          <span className="upload-panel__cta">Select PDF</span>
          <span className="upload-panel__hint">Drag & drop or browse from files</span>
        </label>

        {file ? (
          <div className="upload-panel__summary">
            <div>
              <strong>{file.name}</strong>
              <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
            </div>
            <button type="button" className="ghost-button" onClick={() => setFile(null)} title="Remove file">
              Clear
            </button>
          </div>
        ) : null}

        {previewUrl ? (
          <div className="upload-panel__preview">
            <iframe title="pdf-preview" src={previewUrl} />
          </div>
        ) : null}
      </section>

      <section className="panel-card upload-panel upload-panel--secondary">
        <header className="upload-panel__header">
          <h2>Answer Key (optional)</h2>
          <p>Provide an answer key PDF to populate gold answers directly from the source.</p>
        </header>
        <label
          onDragOver={(event) => {
            event.preventDefault();
            setAnswerKeyDragging(true);
          }}
          onDragLeave={() => setAnswerKeyDragging(false)}
          onDrop={handleAnswerKeyDrop}
          className={`upload-panel__dropzone ${answerKeyDragging ? "is-dragging" : ""}`}
        >
          <input type="file" accept="application/pdf" onChange={handleAnswerKeyInput} hidden />
          <span className="upload-panel__cta">Select Answer Key PDF</span>
          <span className="upload-panel__hint">Optional but recommended for demos</span>
        </label>

        {answerKeyFile ? (
          <div className="upload-panel__summary">
            <div>
              <strong>{answerKeyFile.name}</strong>
              <span>{(answerKeyFile.size / (1024 * 1024)).toFixed(2)} MB</span>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => setAnswerKeyFile(null)}
              title="Remove answer key"
            >
              Clear
            </button>
          </div>
        ) : null}
      </section>

      {error ? <p className="panel-error">{error}</p> : null}
    </div>
  );
};

export default SmartReadingPanel;
