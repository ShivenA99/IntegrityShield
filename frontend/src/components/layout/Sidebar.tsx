import React, { useCallback, useState } from "react";
import clsx from "clsx";
import { NavLink } from "react-router-dom";

import {
  History,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  RefreshCcw,
  RotateCcw,
  Layers,
  ShieldCheck,
} from "lucide-react";
import { usePipeline } from "@hooks/usePipeline";
import DeveloperToggle from "@components/layout/DeveloperToggle";

const links = [
  { to: "/dashboard", label: "Active Run", shortLabel: "Run", icon: LayoutDashboard },
  { to: "/runs", label: "Previous Runs", shortLabel: "History", icon: History },
  { to: "/classrooms", label: "Classrooms", shortLabel: "Class", icon: Layers },
  { to: "/settings", label: "Settings", shortLabel: "Prefs", icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle }) => {
  const { activeRunId, status, refreshStatus, resetActiveRun } = usePipeline();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const documentInfo = (status?.structured_data as Record<string, any> | undefined)?.document;
  const runLabel = activeRunId ? `${activeRunId.slice(0, 6)}…${activeRunId.slice(-4)}` : "No active run";
  const stageLabel = status?.current_stage ? status.current_stage.replace(/_/g, " ") : "—";
  const pipelineStatusLabel = status?.status ? status.status.replace(/_/g, " ") : "idle";
  const classroomCount = status?.classrooms ? status.classrooms.length : 0;
  const manipulationResults = ((status?.structured_data as Record<string, any> | undefined)?.manipulation_results ??
    {}) as Record<string, any>;
  const enhancedPdfs = (manipulationResults?.enhanced_pdfs ?? {}) as Record<string, any>;
  const downloadCount = Object.values(enhancedPdfs).filter((entry: any) => {
    if (!entry) return false;
    const candidate = entry.relative_path || entry.path || entry.file_path;
    return Boolean(candidate);
  }).length;

  const handleRefresh = useCallback(async () => {
    if (!activeRunId || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await refreshStatus(activeRunId, { quiet: true });
    } finally {
      setIsRefreshing(false);
    }
  }, [activeRunId, isRefreshing, refreshStatus]);

  const handleReset = useCallback(async () => {
    if (!activeRunId) return;
    await resetActiveRun();
  }, [activeRunId, resetActiveRun]);

  return (
    <aside className={["app-sidebar", collapsed ? "app-sidebar--collapsed" : ""].join(" ").trim()}>
      <div className="app-sidebar__inner">
        <div className="app-sidebar__top">
          <span className="app-sidebar__brand" title="AntiCheat AI">
            <ShieldCheck size={18} aria-hidden="true" />
            {!collapsed && <span>AntiCheat&nbsp;AI</span>}
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

        {!collapsed ? (
          <div className="app-sidebar__run-card">
            <div className="app-sidebar__run-heading">
              <span className="app-sidebar__run-title">Active run</span>
              <span
                className={clsx("app-sidebar__run-status", status?.status && `status-${status.status}`)}
                title={`Pipeline status: ${pipelineStatusLabel}`}
              >
                {pipelineStatusLabel}
              </span>
            </div>
            <div className="app-sidebar__run-label" title={activeRunId ?? "No active run"}>
              <RotateCcw size={14} aria-hidden="true" />
              <span>{runLabel}</span>
            </div>
            <div className="app-sidebar__run-meta">
              <span className="app-sidebar__run-file" title={documentInfo?.filename ?? "No source loaded"}>
                {documentInfo?.filename ?? "No source"}
              </span>
              <span className="app-sidebar__run-stage" title={`Current stage: ${stageLabel}`}>
                Stage · {stageLabel}
              </span>
            </div>
            <div className="app-sidebar__run-stats">
              <span
                className={clsx("app-sidebar__run-chip", downloadCount > 0 && "is-ready")}
                title={
                  downloadCount
                    ? `${downloadCount} downloadable asset${downloadCount === 1 ? "" : "s"}`
                    : "No downloads generated yet"
                }
              >
                Downloads · {downloadCount || "—"}
              </span>
              <span
                className="app-sidebar__run-chip"
                title={`${classroomCount} classroom dataset${classroomCount === 1 ? "" : "s"}`}
              >
                Classrooms · {classroomCount || "—"}
              </span>
            </div>
            <div className="app-sidebar__run-actions">
            <span className="icon-button__wrapper" data-tooltip="Refresh status">
              <button
                type="button"
                className="icon-button"
                onClick={handleRefresh}
                disabled={!activeRunId || isRefreshing}
                aria-label="Refresh status"
              >
                <RefreshCcw size={14} aria-hidden="true" />
              </button>
            </span>
            <span className="icon-button__wrapper" data-tooltip="Reset active run">
              <button
                type="button"
                className="icon-button"
                onClick={handleReset}
                disabled={!activeRunId}
                aria-label="Reset active run"
              >
                <RotateCcw size={14} aria-hidden="true" />
              </button>
            </span>
            <DeveloperToggle />
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
        {collapsed ? (
          <div className="app-sidebar__collapsed-controls">
            <DeveloperToggle />
          </div>
        ) : null}
      </div>
    </aside>
  );
};

export default Sidebar;
