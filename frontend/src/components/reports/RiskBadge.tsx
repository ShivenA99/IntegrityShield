import * as React from "react";

interface RiskBadgeProps {
  risk: "high" | "medium" | "low" | string;
}

const RiskBadge: React.FC<RiskBadgeProps> = ({ risk }) => {
  const normalizedRisk = risk.toLowerCase();

  return (
    <span className="risk-badge" data-risk={normalizedRisk}>
      {risk.toUpperCase()}
    </span>
  );
};

export default RiskBadge;
