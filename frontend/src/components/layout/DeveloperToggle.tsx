import React from "react";

import { useDeveloperContext } from "@contexts/DeveloperContext";

const DeveloperToggle: React.FC = () => {
  const { isDeveloperMode, toggleDeveloperMode } = useDeveloperContext();

  return (
    <button
      type="button"
      className="pill-button"
      onClick={toggleDeveloperMode}
      title={isDeveloperMode ? "Hide developer utilities" : "Show developer utilities"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.45rem",
        background: isDeveloperMode ? "rgba(96, 165, 250, 0.25)" : "rgba(55, 65, 81, 0.65)",
        color: "#f8fafc",
        border: "1px solid rgba(148, 163, 184, 0.35)",
      }}
    >
      <span role="img" aria-hidden="true">🛠️</span>
      {isDeveloperMode ? "Developer On" : "Developer Off"}
    </button>
  );
};

export default DeveloperToggle;
