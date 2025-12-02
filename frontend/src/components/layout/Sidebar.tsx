import React, { useEffect, useState } from "react";
import clsx from "clsx";
import { NavLink, useLocation } from "react-router-dom";

import {
  History,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  RotateCcw,
  Layers,
  ShieldCheck,
} from "lucide-react";
import { usePipeline } from "@hooks/usePipeline";
import { useDemoRun } from "@contexts/DemoRunContext";
import { getAssetUrl } from "@utils/basePath";

const links = [
  { to: "/dashboard", label: "Active Assessment", shortLabel: "Assess", icon: LayoutDashboard },
  { to: "/runs", label: "Previous Runs", shortLabel: "History", icon: History },
  { to: "/classrooms", label: "Classrooms", shortLabel: "Class", icon: Layers },
  { to: "/settings", label: "Settings", shortLabel: "Prefs", icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle }) => {
  const location = useLocation();
  const { activeRunId, status } = usePipeline();
  const { demoRun } = useDemoRun();
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [thumbnailState, setThumbnailState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  const structuredData = (status?.structured_data as Record<string, any> | undefined) ?? {};
  const documentInfo = structuredData?.document as Record<string, any> | undefined;
  const answerKeyInfo = structuredData?.answer_key as Record<string, any> | undefined;
  const hasAssessment = Boolean(documentInfo?.filename);
  const answerKeyFilenamePipeline = answerKeyInfo?.source_pdf
    ? answerKeyInfo.source_pdf.split(/[\\/]/g).pop()
    : documentInfo?.answer_key_path
      ? documentInfo.answer_key_path.split(/[\\/]/g).pop()
      : null;
  const hasAnswerKey = Boolean(answerKeyFilenamePipeline);
  const pipelineReady = hasAssessment && hasAnswerKey;

  const formatRunLabel = (id?: string | null) => {
    if (!id) return "—";
    return id.length > 14 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id;
  };

  const isDemoActive = Boolean(demoRun);
  const demoAnswerKey = demoRun?.answerKey?.filename ?? null;
  const documentFilename = isDemoActive ? demoRun?.document?.filename : documentInfo?.filename;
  const answerKeyFilename = isDemoActive ? demoAnswerKey : answerKeyFilenamePipeline;
  const documentPagesRaw = isDemoActive ? demoRun?.document?.pages : documentInfo?.pages;
  const isReady = isDemoActive ? Boolean(documentFilename && answerKeyFilename) : pipelineReady;

  const runLabel = isDemoActive ? formatRunLabel(demoRun?.runId ?? "Demo run") : formatRunLabel(activeRunId);
  const stageLabel = isDemoActive
    ? demoRun?.stageLabel ?? "Stage 1"
    : status?.current_stage
      ? status.current_stage.replace(/_/g, " ")
      : "—";
  const pipelineStatusLabel = status?.status ? status.status.replace(/_/g, " ") : "idle";
  const statusLabel = isDemoActive ? demoRun?.statusLabel ?? "demo ready" : pipelineStatusLabel;
  const classroomCount = isDemoActive ? demoRun?.classrooms ?? 0 : status?.classrooms ? status.classrooms.length : 0;
  const manipulationResults = ((status?.structured_data as Record<string, any> | undefined)?.manipulation_results ??
    {}) as Record<string, any>;
  const enhancedPdfs = (manipulationResults?.enhanced_pdfs ?? {}) as Record<string, any>;
  const downloadCount = Object.values(enhancedPdfs).filter((entry: any) => {
    if (!entry) return false;
    const candidate = entry.relative_path || entry.path || entry.file_path;
    return Boolean(candidate);
  }).length;
  const demoDownloadCount = demoRun?.downloads ?? 0;
  const effectiveDownloadCount = isDemoActive ? demoDownloadCount : downloadCount;

  const resolvedPagesLabel =
    typeof documentPagesRaw === "number"
      ? `${documentPagesRaw} page${documentPagesRaw === 1 ? "" : "s"}`
      : documentPagesRaw ?? (isReady ? "Pages unavailable" : "Waiting for files");

  useEffect(() => {
    if (isDemoActive) {
      setThumbnailUrl(null);
      setThumbnailState("idle");
      return;
    }
    let objectUrl: string | null = null;
    let isMounted = true;
    if (!activeRunId || !pipelineReady) {
      setThumbnailUrl(null);
      setThumbnailState("idle");
      return;
    }
    const controller = new AbortController();
    const fetchThumbnail = async () => {
      try {
        setThumbnailState("loading");
        const response = await fetch(`/api/pipeline/${activeRunId}/pdf/input/thumbnail`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error("thumbnail_fetch_failed");
        }
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!isMounted) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setThumbnailUrl(objectUrl);
        setThumbnailState("ready");
      } catch (error) {
        if (controller.signal.aborted) return;
        if (objectUrl) {
          URL.revokeObjectURL(objectUrl);
        }
        if (isMounted) {
          setThumbnailUrl(null);
          setThumbnailState("error");
        }
      }
    };

    fetchThumbnail();

    return () => {
      isMounted = false;
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [activeRunId, pipelineReady, status?.updated_at, isDemoActive]);

  const previewUrl = isDemoActive ? demoRun?.document?.previewUrl ?? null : thumbnailUrl;
  const previewType = isDemoActive ? demoRun?.document?.previewType ?? "pdf" : "image";
  const previewClass = clsx("app-sidebar__run-thumb", {
    "has-image": previewType === "image" && previewUrl,
    "has-preview-frame": previewType === "pdf" && previewUrl,
  });
  const documentTitle = documentFilename ?? (isReady ? "Processing assessment…" : "—");
  const runTitle = isDemoActive ? demoRun?.runId ?? "Demo assessment" : activeRunId ?? "Upload an assessment to begin";

  const hideRunCard = location.pathname.startsWith("/classrooms");

  return (
    <aside className={["app-sidebar", collapsed ? "app-sidebar--collapsed" : ""].join(" ").trim()}>
      <div className="app-sidebar__inner">
        <div className="app-sidebar__top">
          <span className="app-sidebar__brand" title="IntegrityShield">
            <img src={getAssetUrl("/icons/logo.png")} alt="IntegrityShield" className="app-sidebar__brand-logo" />
            {!collapsed && <span>INTEGRITYSHIELD</span>}
          </span>
          <button
            type="button"
            className="app-sidebar__toggle"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        {!collapsed && !hideRunCard ? (
          <div className="app-sidebar__run-card">
            <div className="app-sidebar__run-heading">
              <span className="app-sidebar__run-title">Active assessment</span>
              <span
                className={clsx("app-sidebar__run-status", !isDemoActive && status?.status && `status-${status.status}`)}
                title={`Pipeline status: ${statusLabel}`}
              >
                {statusLabel}
              </span>
            </div>
            <div className="app-sidebar__run-label" title={runTitle}>
              <RotateCcw size={14} aria-hidden="true" />
              <span>{runLabel}</span>
            </div>
            <div className="app-sidebar__run-preview" title={documentFilename ?? "Upload both PDFs to view a preview"}>
              <div className="app-sidebar__run-thumb-container">
                <div className={previewClass}>
                  {previewUrl ? (
                    previewType === "image" ? (
                      <img src={previewUrl} alt={`${documentFilename ?? "Assessment"} preview`} />
                    ) : (
                      <iframe
                        src={`${previewUrl}#toolbar=0&navpanes=0&scrollbar=0`}
                        title={`${documentFilename ?? "Assessment"} preview`}
                        loading="lazy"
                      />
                    )
                  ) : (
                    <div className="app-sidebar__run-thumb-placeholder" aria-hidden="true" />
                  )}
                </div>
              </div>
              <div className="app-sidebar__run-fileinfo">
                <strong>{documentTitle}</strong>
                <span>{resolvedPagesLabel}</span>
              </div>
            </div>
            <div className="app-sidebar__run-meta">
              <span className="app-sidebar__run-file" title={documentFilename ?? "Awaiting assessment upload"}>
                Assessment · {documentFilename ?? "—"}
              </span>
              <span className="app-sidebar__run-file" title={answerKeyFilename ?? "Awaiting answer key upload"}>
                Answer key · {answerKeyFilename ?? "—"}
              </span>
              <span className="app-sidebar__run-stage" title={`Current stage: ${stageLabel}`}>
                Stage · {stageLabel}
              </span>
            </div>
            <div className="app-sidebar__run-stats">
              <span
                className={clsx("app-sidebar__run-chip", effectiveDownloadCount > 0 && "is-ready")}
                title={
                  effectiveDownloadCount
                    ? `${effectiveDownloadCount} downloadable asset${effectiveDownloadCount === 1 ? "" : "s"}`
                    : "No downloads generated yet"
                }
              >
                Downloads · {effectiveDownloadCount || "—"}
              </span>
              <span
                className="app-sidebar__run-chip"
                title={`${classroomCount} classroom dataset${classroomCount === 1 ? "" : "s"}`}
              >
                Classrooms · {classroomCount || "—"}
              </span>
            </div>
          </div>
        ) : null}

        <nav>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => ["app-sidebar__link", isActive ? "active" : ""].join(" ").trim()}
              title={link.label}
            >
              <link.icon className="app-sidebar__icon" size={18} aria-hidden="true" />
              <span className="app-sidebar__label">{collapsed ? link.shortLabel : link.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </aside>
  );
};

export default Sidebar;
