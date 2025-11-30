import React, { useMemo, useState } from "react";
import { Button } from "@instructure/ui-buttons";
import { Table } from "@instructure/ui-table";
import { ScreenReaderContent } from "@instructure/ui-a11y-content";

import LTIShell from "@layout/LTIShell";
import ArtifactPreviewModal, { ArtifactPreview } from "@components/shared/ArtifactPreviewModal";
import { usePipeline } from "@hooks/usePipeline";
import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";

const ReportsPage: React.FC = () => {
  const { status } = usePipeline();
  const structured = (status?.structured_data as Record<string, any>) ?? {};
  const manipulation = (structured.manipulation_results as Record<string, any>) ?? {};
  const reports = (structured.reports as Record<string, any>) ?? {};
  const [selected, setSelected] = useState<ArtifactPreview | null>(null);

  const reportRows = useMemo<ArtifactPreview[]>(() => {
    const rows: ArtifactPreview[] = [];
    const vulnerabilityPath = reports.vulnerability?.artifact ?? null;
    rows.push({
      key: "vulnerability",
      label: "Vulnerability",
      kind: "report",
      status: vulnerabilityPath ? "completed" : "pending",
      relativePath: vulnerabilityPath,
      generatedAt: reports.vulnerability?.generated_at,
    });

    const detectionMeta = manipulation.detection_report ?? reports.detection ?? null;
    const detectionPath =
      detectionMeta?.relative_path || detectionMeta?.artifact || detectionMeta?.output_files?.json || detectionMeta?.file_path || null;
    rows.push({
      key: "detection",
      label: "Detection",
      kind: "report",
      status: detectionPath ? "completed" : "pending",
      relativePath: detectionPath,
      generatedAt: detectionMeta?.generated_at,
    });

    const evaluationEntries = (reports.evaluation as Record<string, any>) ?? {};
    let bestMethod: string | null = null;
    let bestMeta: any = null;
    let bestScore = -Infinity;
    Object.entries(evaluationEntries).forEach(([method, meta]) => {
      const candidate =
        typeof meta?.metrics?.overall_score === "number"
          ? meta.metrics.overall_score
          : typeof meta?.score === "number"
            ? meta.score
            : typeof meta?.success_rate === "number"
              ? meta.success_rate
              : 0;
      if (candidate >= bestScore) {
        bestScore = candidate;
        bestMethod = method;
        bestMeta = meta;
      }
    });
    rows.push({
      key: "evaluation",
      label: "Evaluation",
      kind: "report",
      status: bestMeta?.artifact ? "completed" : "pending",
      relativePath: bestMeta?.artifact ?? null,
      variant: bestMethod ? ENHANCEMENT_METHOD_LABELS[bestMethod as keyof typeof ENHANCEMENT_METHOD_LABELS] ?? bestMethod.replace(/_/g, " ") : null,
      method: bestMethod
        ? ENHANCEMENT_METHOD_LABELS[bestMethod as keyof typeof ENHANCEMENT_METHOD_LABELS] ?? bestMethod.replace(/_/g, " ")
        : null,
      generatedAt: bestMeta?.generated_at,
      notes: bestMeta && typeof bestScore === "number" ? `Best evaluation score: ${bestScore.toFixed(2)}` : undefined,
    });

    return rows;
  }, [manipulation, reports]);

  const readyReports = reportRows.filter((row) => row.relativePath);

  return (
    <LTIShell title="Reports" subtitle="Review vulnerability, detection, and evaluation packs.">
      <div className="canvas-card">
        <div className="table-header">
          <div>
            <h2>Current run reports</h2>
            <p>{readyReports.length ? `${readyReports.length} ready • ${reportRows.length - readyReports.length} pending.` : "No report artifacts yet."}</p>
          </div>
        </div>
        <Table hover caption={<ScreenReaderContent>Current run reports</ScreenReaderContent>}>
          <Table.Head>
            <Table.Row>
              <Table.ColHeader id="report-name">Name</Table.ColHeader>
              <Table.ColHeader id="report-variant">Variant</Table.ColHeader>
              <Table.ColHeader id="report-status">Status</Table.ColHeader>
              <Table.ColHeader id="report-generated">Generated</Table.ColHeader>
              <Table.ColHeader id="report-actions">Actions</Table.ColHeader>
            </Table.Row>
          </Table.Head>
          <Table.Body>
            {reportRows.map((row) => (
              <Table.Row key={row.key}>
                <Table.Cell>{row.label}</Table.Cell>
                <Table.Cell>{row.variant ?? "—"}</Table.Cell>
                <Table.Cell>
                  <span className={["status-pill", row.status === "completed" ? "completed" : "pending"].join(" ")}>{row.status}</span>
                </Table.Cell>
                <Table.Cell>{row.generatedAt ? new Date(row.generatedAt).toLocaleString() : "—"}</Table.Cell>
                <Table.Cell>
                  <div className="table-actions">
                    <Button color="secondary" withBackground={false} onClick={() => setSelected(row)} interaction={!row.relativePath ? "disabled" : "enabled"}>
                      Preview
                    </Button>
                    <Button
                      color="secondary"
                      href={row.relativePath ? `/api/files/${status?.run_id}/${row.relativePath}` : undefined}
                      interaction={!row.relativePath ? "disabled" : "enabled"}
                      download
                    >
                      Download
                    </Button>
                  </div>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
        {!readyReports.length ? <p className="table-empty">No reports generated yet. Start a run to produce vulnerability, detection, and evaluation packs.</p> : null}
      </div>
      <ArtifactPreviewModal artifact={selected} runId={status?.run_id} onClose={() => setSelected(null)} />
    </LTIShell>
  );
};

export default ReportsPage;
