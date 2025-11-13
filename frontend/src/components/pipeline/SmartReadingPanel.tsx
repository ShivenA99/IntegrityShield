import * as React from "react";
import { useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useNotifications } from "@contexts/NotificationContext";
import { validatePdfFile } from "@services/utils/validators";
import type { PipelineStageName } from "@services/types/pipeline";

const SmartReadingPanel: React.FC = () => {
  const { startPipeline, error, status } = usePipeline();
  const { push } = useNotifications();
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isStarting, setIsStarting] = useState(false);

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

  const handleFileInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(event.target.files);
  };

  const handleDrop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  };

  const handleStart = async () => {
    if (isStarting) return;
    setIsStarting(true);
    const enhancementMethods = ["latex_dual_layer", "pymupdf_overlay"];
    const targetStages: PipelineStageName[] = ["smart_reading", "content_discovery", "smart_substitution"];

    const runId = await startPipeline({
      file: file ?? undefined,
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

  return (
    <div className="panel smart-reading">
      <header className="panel-header panel-header--tight">
        <h1>Source Document</h1>
        <div className="panel-actions">
          {status?.run_id ? <span className="badge tag-muted">Last run: {status.run_id}</span> : null}
          <button
            type="button"
            onClick={handleStart}
            disabled={isStarting}
            className="primary-button"
            title={file ? "Begin processing the uploaded PDF" : "Start with current inputs"}
          >
            {isStarting ? "Starting…" : "Start"}
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

      {error ? <p className="panel-error">{error}</p> : null}
    </div>
  );
};

export default SmartReadingPanel;
