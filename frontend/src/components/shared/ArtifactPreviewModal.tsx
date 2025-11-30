import React, { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, Info, X } from "lucide-react";
import clsx from "clsx";
import { Button } from "@instructure/ui-buttons";

export interface ArtifactPreview {
  key: string;
  label: string;
  kind: string;
  status?: string;
  variant?: string | null;
  method?: string | null;
  relativePath?: string | null;
  generatedAt?: string | null;
  sizeBytes?: number | null;
  notes?: string | null;
}

interface ArtifactPreviewModalProps {
  artifact: ArtifactPreview | null;
  runId?: string | null;
  onClose: () => void;
}

const formatSize = (bytes?: number | null) => {
  if (!bytes || bytes <= 0) {
    return "—";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

const formatDate = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
};

type TabOption = "preview" | "metadata" | "logs";

const ArtifactPreviewModal: React.FC<ArtifactPreviewModalProps> = ({ artifact, runId, onClose }) => {
  const [activeTab, setActiveTab] = useState<TabOption>("preview");
  const fileUrl = useMemo(() => {
    if (!artifact?.relativePath || !runId) return null;
    return `/api/files/${runId}/${artifact.relativePath}`;
  }, [artifact?.relativePath, runId]);

  useEffect(() => {
    if (!artifact) return;
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEsc);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleEsc);
      document.body.style.overflow = "";
      setActiveTab("preview");
    };
  }, [artifact, onClose]);

  if (!artifact) return null;

  const metadata = [
    { label: "Type", value: artifact.kind ?? "—" },
    { label: "Variant", value: artifact.variant ?? artifact.method ?? "—" },
    { label: "Status", value: artifact.status ?? "—" },
    { label: "Generated", value: formatDate(artifact.generatedAt) },
    { label: "Size", value: formatSize(artifact.sizeBytes) },
    { label: "Path", value: artifact.relativePath ?? "—" },
  ];

  return (
    <div className="artifact-modal" role="dialog" aria-modal="true" aria-label={`${artifact.label} preview`}>
      <div className="artifact-modal__overlay" onClick={onClose} />
      <div className="artifact-modal__panel">
        <header className="artifact-modal__header">
          <div>
            <p className="artifact-modal__eyebrow">{artifact.kind}</p>
            <h2>{artifact.label}</h2>
            {artifact.variant ? <p className="artifact-modal__muted">{artifact.variant}</p> : null}
          </div>
          <div className="artifact-modal__actions">
            {fileUrl ? (
              <>
                <Button color="secondary" withBackground={false} href={fileUrl} target="_blank" rel="noreferrer">
                  <ExternalLink size={16} /> Open
                </Button>
                <Button color="secondary" href={fileUrl} download>
                  <Download size={16} /> Download
                </Button>
              </>
            ) : null}
            <Button color="secondary" withBackground={false} onClick={onClose} aria-label="Close preview">
              <X size={16} />
            </Button>
          </div>
        </header>

        <div className="artifact-tabs" role="tablist" aria-label="Artifact details">
          {(["preview", "metadata", "logs"] as TabOption[]).map((tab) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              className={clsx("artifact-tab", activeTab === tab && "is-active")}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "preview" ? "Preview" : tab === "metadata" ? "Metadata" : "Logs"}
            </button>
          ))}
        </div>

        <section className="artifact-modal__body">
          {activeTab === "preview" ? (
            fileUrl ? (
              <iframe title={`${artifact.label} preview`} src={fileUrl} className="artifact-preview__frame" />
            ) : (
              <div className="artifact-preview__empty">
                <Info size={20} />
                <p>Artifact not ready for preview.</p>
              </div>
            )
          ) : null}

          {activeTab === "metadata" ? (
            <dl className="artifact-metadata">
              {metadata.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
              {artifact.notes ? (
                <div className="artifact-notes">
                  <dt>Notes</dt>
                  <dd>{artifact.notes}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}

          {activeTab === "logs" ? (
            <div className="artifact-preview__empty">
              <Info size={20} />
              <div>
                <p>Telemetry log capture coming soon.</p>
                <small>For now, reference the backend run logs if you need execution traces.</small>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
};

export default ArtifactPreviewModal;
