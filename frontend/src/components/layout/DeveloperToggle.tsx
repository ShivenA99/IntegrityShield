import React from "react";

import { useDeveloperContext } from "@contexts/DeveloperContext";

const DeveloperToggle: React.FC = () => {
  const { isDeveloperMode, toggleDeveloperMode } = useDeveloperContext();

  return (
    <button className="developer-toggle" onClick={toggleDeveloperMode}>
      {isDeveloperMode ? "Hide Developer Tools" : "Show Developer Tools"}
    </button>
  );
};

export default DeveloperToggle;
