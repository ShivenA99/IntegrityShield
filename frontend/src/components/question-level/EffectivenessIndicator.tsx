import React from "react";

interface EffectivenessIndicatorProps {
  value?: number;
}

const EffectivenessIndicator: React.FC<EffectivenessIndicatorProps> = ({ value }) => {
  if (value === undefined) {
    return <span className="effectiveness-indicator">—</span>;
  }
  const percentage = Math.round(value * 100);
  const intent = percentage >= 80 ? "success" : percentage >= 50 ? "warning" : "error";
  return <span className={`effectiveness-indicator ${intent}`}>{percentage}%</span>;
};

export default EffectivenessIndicator;
