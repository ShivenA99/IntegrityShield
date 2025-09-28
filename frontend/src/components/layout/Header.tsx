import React from "react";
import { useNavigate } from "react-router-dom";

import { usePipeline } from "@hooks/usePipeline";
import DeveloperToggle from "@components/layout/DeveloperToggle";

const Header: React.FC = () => {
  const navigate = useNavigate();
  const { activeRunId, resetActiveRun, status } = usePipeline();
  const documentInfo = (status?.structured_data as any)?.document;

  const handleReset = async () => {
    if (!activeRunId) {
      navigate("/dashboard");
      return;
    }

    const runLabel = documentInfo?.filename || activeRunId;
    const message = `Reset current run${runLabel ? ` (${runLabel})` : ""}? This clears the active session so you can start fresh.`;
    if (!window.confirm(message)) return;

    await resetActiveRun({ softDelete: true });
    navigate("/dashboard");
  };

  return (
    <header className="app-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
      <h1 style={{ margin: 0 }}>FairTestAI</h1>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        {documentInfo?.filename ? (
          <span style={{ fontSize: "0.9rem", color: "var(--muted)" }}>
            Active file: <strong style={{ color: "var(--text)" }}>{documentInfo.filename}</strong>
          </span>
        ) : null}
        <DeveloperToggle />
        <button
          type="button"
          onClick={handleReset}
          className="pill-button"
          style={{
            backgroundColor: activeRunId ? '#ef4444' : 'rgba(55,65,81,0.65)',
            color: 'var(--text)',
            border: "none",
            padding: "0.5rem 1.1rem",
            fontSize: "0.85rem",
          }}
          title={activeRunId ? "Clear the active run and return to dashboard" : "Return to dashboard"}
        >
          {activeRunId ? "Reset active run" : "Back to dashboard"}
        </button>
      </div>
    </header>
  );
};

export default Header;
