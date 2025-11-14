import React from "react";
import clsx from "clsx";
import { Code } from "lucide-react";

import { useDeveloperContext } from "@contexts/DeveloperContext";

const DeveloperToggle: React.FC = () => {
  const { isDeveloperMode, toggleDeveloperMode } = useDeveloperContext();

  return (
    <button
      type="button"
      className={clsx("dev-toggle", isDeveloperMode && "is-active")}
      onClick={toggleDeveloperMode}
      role="switch"
      aria-checked={isDeveloperMode}
      title={isDeveloperMode ? "Disable developer utilities" : "Enable developer utilities"}
    >
      <Code size={16} aria-hidden="true" />
      <span className="dev-toggle__label">Developer</span>
      <span className="dev-toggle__slider" aria-hidden="true">
        <span className="dev-toggle__thumb" />
      </span>
    </button>
  );
};

export default DeveloperToggle;
