import React, { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, Info, X } from "lucide-react";
import clsx from "clsx";
import { Button } from "@instructure/ui-buttons";
import ReportPreview from "@components/reports/ReportPreview";

import "@styles/reports.css";

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
    if (!artifact?.relativePath || !runId) {
      console.log('ArtifactPreviewModal: Missing data', {
        hasArtifact: !!artifact,
        relativePath: artifact?.relativePath,
        runId
      });
      return null;
    }
    const url = `/api/files/${runId}/${artifact.relativePath}`;
    console.log('ArtifactPreviewModal: Constructed URL', url);
    return url;
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

  // Determine if this is a report that should use card-based display
  // artifact.key is "vulnerability", "detection", or "evaluation-{method}"
  const artifactKey = artifact.key?.toLowerCase() || "";
  const isReport = artifactKey === "vulnerability" || artifactKey === "detection" || artifactKey.startsWith("evaluation");
  const reportType: "vulnerability" | "detection" | "evaluation" | undefined =
    artifactKey === "vulnerability" ? "vulnerability" :
    artifactKey === "detection" ? "detection" :
    artifactKey.startsWith("evaluation") ? "evaluation" :
    undefined;

  return (
    <div className="artifact-modal" role="dialog" aria-modal="true" aria-label={`${artifact.label} preview`} style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      zIndex: 9999,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }}>
      <div className="artifact-modal__overlay" onClick={onClose} style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(4px)'
      }} />
      <div className="artifact-modal__panel" style={{
        position: 'relative',
        width: '90vw',
        maxWidth: '1400px',
        height: '90vh',
        backgroundColor: '#ffffff',
        borderRadius: '0.75rem',
        boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}>
        <header className="artifact-modal__header" style={{
          padding: '1.5rem 2rem',
          borderBottom: '1px solid #e0e0e0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0
        }}>
          <div>
            <p className="artifact-modal__eyebrow" style={{
              fontSize: '0.75rem',
              color: '#666666',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              marginBottom: '0.25rem'
            }}>{artifact.kind}</p>
            <h2 style={{
              fontSize: '1.5rem',
              fontWeight: 600,
              color: '#333333',
              margin: '0'
            }}>{artifact.label}</h2>
            {artifact.variant ? <p className="artifact-modal__muted" style={{
              fontSize: '0.875rem',
              color: '#666666',
              marginTop: '0.25rem'
            }}>{artifact.variant}</p> : null}
          </div>
          <div className="artifact-modal__actions" style={{
            display: 'flex',
            gap: '0.75rem',
            alignItems: 'center'
          }}>
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
              <X size={20} />
            </Button>
          </div>
        </header>

        <div className="artifact-tabs" role="tablist" aria-label="Artifact details" style={{
          display: 'flex',
          borderBottom: '1px solid #e0e0e0',
          padding: '0 2rem',
          gap: '0.5rem',
          flexShrink: 0
        }}>
          {(["preview", "metadata", "logs"] as TabOption[]).map((tab) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              className={clsx("artifact-tab", activeTab === tab && "is-active")}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '0.75rem 1.5rem',
                border: 'none',
                borderBottom: activeTab === tab ? '3px solid #FF7F32' : '3px solid transparent',
                backgroundColor: 'transparent',
                color: activeTab === tab ? '#FF7F32' : '#666666',
                fontWeight: activeTab === tab ? 600 : 400,
                fontSize: '0.875rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                fontFamily: 'inherit'
              }}
            >
              {tab === "preview" ? "Preview" : tab === "metadata" ? "Metadata" : "Logs"}
            </button>
          ))}
        </div>

        <section className="artifact-modal__body" style={{
          flex: 1,
          overflow: 'auto',
          padding: activeTab === "preview" ? '0' : '2rem'
        }}>
          {activeTab === "preview" ? (
            fileUrl ? (
              isReport && reportType ? (
                <ReportPreview reportType={reportType} fileUrl={fileUrl} />
              ) : (
                <iframe
                  title={`${artifact.label} preview`}
                  src={fileUrl}
                  className="artifact-preview__frame"
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none'
                  }}
                />
              )
            ) : (
              <div className="artifact-preview__empty" style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                gap: '1rem',
                color: '#666666'
              }}>
                <Info size={48} />
                <p style={{ fontSize: '1rem' }}>Artifact not ready for preview.</p>
              </div>
            )
          ) : null}

          {activeTab === "metadata" ? (
            <dl className="artifact-metadata" style={{
              display: 'grid',
              gridTemplateColumns: '200px 1fr',
              gap: '1.5rem 2rem',
              margin: 0
            }}>
              {metadata.map((item) => (
                <React.Fragment key={item.label}>
                  <dt style={{
                    fontWeight: 600,
                    color: '#666666',
                    fontSize: '0.875rem'
                  }}>{item.label}</dt>
                  <dd style={{
                    margin: 0,
                    color: '#333333',
                    fontSize: '0.875rem',
                    wordBreak: 'break-word'
                  }}>{item.value}</dd>
                </React.Fragment>
              ))}
              {artifact.notes && (
                <>
                  <dt style={{
                    fontWeight: 600,
                    color: '#666666',
                    fontSize: '0.875rem'
                  }}>Notes</dt>
                  <dd style={{
                    margin: 0,
                    color: '#333333',
                    fontSize: '0.875rem',
                    wordBreak: 'break-word'
                  }}>{artifact.notes}</dd>
                </>
              )}
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
