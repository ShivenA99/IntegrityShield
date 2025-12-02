import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, RefreshCcw, RotateCcw } from "lucide-react";
import { ShieldCheckIcon } from "@heroicons/react/24/outline";

import { usePipeline } from "@hooks/usePipeline";
import DeveloperToggle from "@components/layout/DeveloperToggle";

const Header: React.FC = () => {
  const navigate = useNavigate();
  const { activeRunId, resetActiveRun, status, refreshStatus } = usePipeline();
  const documentInfo = (status?.structured_data as any)?.document;
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleReset = async () => {
    if (!activeRunId) {
      navigate("/dashboard");
      return;
    }

    const runLabel = documentInfo?.filename || activeRunId;
    const message = `Reset current run${runLabel ? ` (${runLabel})` : ""}? This clears the active session so you can start fresh.`;
    if (!window.confirm(message)) return;

    await resetActiveRun();
    navigate("/dashboard");
  };

  const handleRefresh = async () => {
    if (!activeRunId || isRefreshing) {
      return;
    }
    setIsRefreshing(true);
    try {
      await refreshStatus(activeRunId, { quiet: true });
    } finally {
      setIsRefreshing(false);
    }
  };

  const runLabel = activeRunId ? `${activeRunId.slice(0, 6)}…${activeRunId.slice(-4)}` : "No active run";

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <span className="app-header__logo">
          <img src="/IS_logo.png?v=3" alt="IntegrityShield" className="app-header__logo-image" />
          INTEGRITYSHIELD
        </span>
        <div className="app-header__run">
          <RotateCcw size={16} aria-hidden="true" />
          <span>{runLabel}</span>
        </div>
      </div>

      <div className="app-header__meta">
        {documentInfo?.filename ? (
          <span className="app-header__file">
            <FileText size={15} aria-hidden="true" />
            {documentInfo.filename}
          </span>
        ) : (
          <span className="app-header__file muted">No source loaded</span>
        )}
        {status?.current_stage ? (
          <span className="app-header__stage">Stage: {status.current_stage.replace(/_/g, " ")}</span>
        ) : null}
      </div>

      <div className="app-header__actions">
        <button
          type="button"
          className="icon-button"
          onClick={handleRefresh}
          disabled={!activeRunId}
          aria-busy={isRefreshing}
          title="Refresh pipeline status"
        >
          <RefreshCcw size={17} aria-hidden="true" />
        </button>
        <DeveloperToggle />
        <button
          type="button"
          onClick={handleReset}
          className="header-reset"
          title={activeRunId ? "Clear the active run and return to dashboard" : "Return to dashboard"}
        >
          {activeRunId ? "Reset Run" : "Back to Dashboard"}
        </button>
      </div>
    </header>
  );
};

export default Header;
