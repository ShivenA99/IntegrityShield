import * as React from "react";
import { useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useNotifications } from "@contexts/NotificationContext";
import { validatePdfFile } from "@services/utils/validators";
import type { PipelineStageName } from "@services/types/pipeline";

const ENHANCEMENT_OPTIONS = [
  {
    key: "latex-dual-layer" as const,
    label: "LaTeX Dual Layer",
    description: "Replace LaTeX spans and overlay the original glyphs for layered attacks.",
    method: "latex_dual_layer",
    icon: "🧬",
  },
];

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
    const enhancementMethods = ENHANCEMENT_OPTIONS.map((option) => option.method);
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
    <div className="panel smart-reading" style={{ display: 'grid', gap: '1.5rem' }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', margin: 0 }}>
          <span role="img" aria-hidden="true">📄</span>
          Start a New Run
        </h2>
        <p style={{ margin: 0, color: 'var(--muted)' }}>
          Upload a PDF and launch the LaTeX-first pipeline. The flow extracts questions, stages manipulations,
          and prepares the Latex dual-layer attack for PDF creation.
        </p>
      </header>

      <section className="panel-card" style={{ display: 'grid', gap: '1rem' }}>
        <div>
          <h4 style={{ marginBottom: '0.5rem' }}>Enhancement Method</h4>
          <div className="enhancement-toggle-row">
            {ENHANCEMENT_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                className="enhancement-toggle active"
                title={option.description}
                disabled
              >
                <span aria-hidden="true">{option.icon}</span>
                {option.label}
              </button>
            ))}
          </div>
          <p style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: 'var(--muted)' }}>
            The Latex dual-layer renderer keeps the original glyphs while injecting manipulated spans,
            providing a resilient attack path for downstream PDF viewers.
          </p>
        </div>
      </section>

      <section className="panel-card" style={{ display: 'grid', gap: '1rem' }}>
        <h4 style={{ margin: 0 }}>Upload PDF</h4>
        <label
          onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`upload-dropzone ${isDragging ? 'dragging' : ''}`}
        >
          <input type="file" accept="application/pdf" onChange={handleFileInput} hidden />
          <div>
            <span role="img" aria-hidden="true" style={{ fontSize: '2rem' }}>📁</span>
            <p style={{ margin: '0.35rem 0 0', fontWeight: 600 }}>Drag & drop a PDF, or <span style={{ color: 'var(--accent)' }}>browse</span></p>
            <p style={{ margin: '0.15rem 0 0', fontSize: '0.85rem', color: 'var(--muted)' }}>Maximum size 20 MB. Original remains unchanged.</p>
          </div>
        </label>

        {file ? (
          <div className="file-summary">
            <div>
              <strong>{file.name}</strong>
              <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
            </div>
            <button type="button" className="pill-button" onClick={() => setFile(null)} title="Remove file">✖ Clear</button>
          </div>
        ) : null}

        {previewUrl ? (
          <div className="pdf-preview">
            <iframe title="pdf-preview" src={previewUrl} style={{ width: '100%', height: 420, border: 0, borderRadius: '12px' }} />
          </div>
        ) : null}
      </section>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button onClick={handleStart} disabled={isStarting} className="pill-button" title="Begin processing the uploaded PDF or use fixed inputs">
          {isStarting ? "Starting…" : "Start Pipeline"}
        </button>
        {status?.run_id ? (
          <span className="badge tag-muted">Last run: {status.run_id}</span>
        ) : null}
      </div>

      {error ? <p className="error" style={{ color: 'var(--danger)' }}>{error}</p> : null}
    </div>
  );
};

export default SmartReadingPanel;
