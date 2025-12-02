import React from "react";

import { usePipeline } from "@hooks/usePipeline";

const EffectivenessTestPanel: React.FC = () => {
  const { status } = usePipeline();
  const structuredData = status?.structured_data as Record<string, any> | undefined;
  const globalStats = structuredData?.manipulation_results?.effectiveness_summary as Record<string, any> | undefined;

  return (
    <div className="panel effectiveness-testing">
      <h2>📊 Effectiveness Testing</h2>
      <p>Track multi-model validation to understand manipulation success.</p>
      <div className="panel-card">
        <p>Overall success rate: {globalStats?.overall_success_rate ? `${(globalStats.overall_success_rate * 100).toFixed(0)}%` : "—"}</p>
        <p>Models tested: {globalStats?.models_tested ?? "—"}</p>
      </div>
    </div>
  );
};

export default EffectivenessTestPanel;
