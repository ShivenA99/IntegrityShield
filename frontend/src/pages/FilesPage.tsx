import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "@instructure/ui-buttons";
import { Text } from "@instructure/ui-text";
import { Download } from "lucide-react";

import LTIShell from "@layout/LTIShell";
import { PageSection } from "@components/layout/PageSection";
import ArtifactPreviewModal, { ArtifactPreview } from "@components/shared/ArtifactPreviewModal";
import { StatusPill } from "@components/shared/StatusPill";
import { usePipeline } from "@hooks/usePipeline";
import { usePipelineContext } from "@contexts/PipelineContext";
import { getMethodDisplayLabel } from "@constants/enhancementMethods";

interface ArtifactRow extends ArtifactPreview {
  category: "original" | "shielded" | "assessment" | "report";
}

const FILTERS = [
  { id: "all", label: "All files" },
  { id: "assessments", label: "Assessments" },
  { id: "shielded", label: "Shielded" },
  { id: "reports", label: "Reports" },
] as const;

const FilesPage: React.FC = () => {
  const location = useLocation();
  const { status, activeRunId, setActiveRunId, setViewMode, refreshStatus } = usePipeline();
  const [selected, setSelected] = useState<ArtifactPreview | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");

  // Handle URL params to load specific assessment
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const runParam = params.get("run");
    const modeParam = params.get("mode");

    // Only update if the runParam is different from current activeRunId
    if (runParam && runParam !== activeRunId) {
      if (modeParam === "readonly") {
        setViewMode("readonly");
      }
      setActiveRunId(runParam);
      refreshStatus(runParam).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  const artifactRows = useMemo<ArtifactRow[]>(() => {
    if (!status?.structured_data) return [];
    const structured = status.structured_data as Record<string, any>;
    const manipulation = (structured.manipulation_results as Record<string, any>) ?? {};
    const reports = (structured.reports as Record<string, any>) ?? {};
    const documentInfo = structured.document as Record<string, any>;
    const pipelineMode = status.pipeline_config?.mode;

    const rows: ArtifactRow[] = [];
    if (documentInfo?.original_path) {
      rows.push({
        key: "original",
        label: "Original",
        kind: "assessment",
        category: "original",
        status: "completed",
        relativePath: documentInfo.original_path,
        sizeBytes: documentInfo.size_bytes,
        variant: null,
        method: null,
      });
    }
    const enhanced = (manipulation.enhanced_pdfs as Record<string, any>) ?? {};
    Object.entries(enhanced).forEach(([method, meta]) => {
      if (!meta) return;
      const displayLabel = getMethodDisplayLabel(method, pipelineMode);
      rows.push({
        key: `shielded-${method}`,
        label: "Shielded",
        kind: "assessment",
        category: "shielded",
        variant: displayLabel,
        method: displayLabel,
        status: meta.relative_path ? "completed" : "pending",
        relativePath: meta.relative_path || meta.path || meta.file_path,
        sizeBytes: meta.size_bytes ?? meta.file_size_bytes,
      });
    });
    if (reports.vulnerability) {
      rows.push({
        key: "vulnerability",
        label: "Vulnerability",
        kind: "report",
        category: "report",
        status: reports.vulnerability.artifact ? "completed" : "pending",
        relativePath: reports.vulnerability.artifact,
        sizeBytes: reports.vulnerability.output_files?.size_bytes,
        method: null,
        variant: null,
      });
    }
    if (manipulation.detection_report) {
      rows.push({
        key: "detection",
        label: "Detection",
        kind: "report",
        category: "report",
        status: manipulation.detection_report.relative_path ? "completed" : "pending",
        relativePath:
          manipulation.detection_report.relative_path ||
          manipulation.detection_report.output_files?.json ||
          manipulation.detection_report.file_path,
        sizeBytes: manipulation.detection_report.output_files?.size_bytes,
        method: null,
        variant: null,
      });
    }
    // Check both evaluation and prevention_evaluation for backward compatibility
    const evaluations = (reports.evaluation as Record<string, any>) ?? {};
    const preventionEvaluations = (reports.prevention_evaluation as Record<string, any>) ?? {};
    // Merge both, with evaluation taking precedence
    const allEvaluations = { ...preventionEvaluations, ...evaluations };
    Object.entries(allEvaluations).forEach(([method, meta]) => {
      const displayLabel = getMethodDisplayLabel(method, pipelineMode);
      rows.push({
        key: `evaluation-${method}`,
        label: "Evaluation",
        kind: "report",
        category: "report",
        variant: displayLabel,
        method: displayLabel,
        status: meta.artifact ? "completed" : "pending",
        relativePath: meta.artifact,
        sizeBytes: meta.output_files?.size_bytes,
      });
    });
    return rows;
  }, [status?.structured_data, status?.pipeline_config?.mode]);

  const filteredRows = useMemo(() => {
    switch (filter) {
      case "assessments":
        return artifactRows.filter((row) => row.kind === "assessment");
      case "shielded":
        return artifactRows.filter((row) => row.category === "shielded");
      case "reports":
        return artifactRows.filter((row) => row.kind === "report");
      default:
        return artifactRows;
    }
  }, [artifactRows, filter]);

  const formatSize = (bytes?: number | null) => {
    if (!bytes) return "—";
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <LTIShell title="Files">
      <PageSection title="Artifacts" subtitle={`${artifactRows.length} files from active assessment`}>
        {/* Filters */}
        <div style={{
          display: 'inline-flex',
          backgroundColor: '#f5f5f5',
          borderRadius: '0.5rem',
          padding: '0.25rem',
          gap: '0.25rem',
          marginBottom: '1.5rem'
        }}>
          {FILTERS.map((entry) => (
            <button
              key={entry.id}
              onClick={() => setFilter(entry.id)}
              style={{
                padding: '0.5rem 1.25rem',
                border: 'none',
                borderRadius: '0.375rem',
                backgroundColor: filter === entry.id ? '#FF7F32' : 'transparent',
                color: filter === entry.id ? '#ffffff' : '#666666',
                fontWeight: filter === entry.id ? '600' : '400',
                fontSize: '0.875rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                fontFamily: 'inherit'
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {filteredRows.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center' }}>
            <Text color="secondary" size="small">No files available yet</Text>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {filteredRows.map((row) => (
              <div
                key={row.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.75rem 1rem',
                  backgroundColor: '#f9f9f9',
                  borderRadius: '0.5rem',
                  border: '1px solid #e0e0e0',
                  transition: 'all 0.2s ease'
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
                    <Text weight="normal" size="small" style={{ color: '#333333' }}>
                      {row.label}
                    </Text>
                    <span style={{
                      fontSize: '0.75rem',
                      color: '#666666',
                      backgroundColor: '#e0e0e0',
                      padding: '0.125rem 0.5rem',
                      borderRadius: '0.25rem'
                    }}>
                      {row.kind === "assessment" ? "Assessment" : "Report"}
                    </span>
                    {row.method && (
                      <span style={{
                        fontSize: '0.75rem',
                        color: '#666666',
                        backgroundColor: '#e0e0e0',
                        padding: '0.125rem 0.5rem',
                        borderRadius: '0.25rem'
                      }}>
                        {row.method}
                      </span>
                    )}
                  </div>
                  <Text color="secondary" size="x-small">
                    {formatSize(row.sizeBytes)}
                  </Text>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <StatusPill status={row.status as any} />
                  <Button
                    color="secondary"
                    size="small"
                    withBackground={false}
                    onClick={() => setSelected(row)}
                    interaction={!row.relativePath ? "disabled" : "enabled"}
                  >
                    Preview
                  </Button>
                  <Button
                    color="secondary"
                    size="small"
                    withBackground={false}
                    href={row.relativePath ? `/api/files/${status?.run_id}/${row.relativePath}` : undefined}
                    interaction={!row.relativePath ? "disabled" : "enabled"}
                    download
                  >
                    <Download size={14} /> Download
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageSection>
      <ArtifactPreviewModal artifact={selected} runId={activeRunId ?? undefined} onClose={() => setSelected(null)} />
    </LTIShell>
  );
};

export default FilesPage;
