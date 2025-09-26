import React from "react";

import { usePipeline } from "@hooks/usePipeline";

const ResultsPanel: React.FC = () => {
  const { status } = usePipeline();
  const structuredData = status?.structured_data as Record<string, any> | undefined;
  const summary = structuredData?.manipulation_results?.effectiveness_summary as Record<string, any> | undefined;

  return (
    <div className="panel results">
      <h2>📈 Analysis Report</h2>
      <p>Review aggregated metrics and download final reports.</p>
      <ul>
        <li>Questions manipulated: {summary?.questions_successfully_manipulated ?? "—"}</li>
        <li>Total questions: {summary?.total_questions ?? "—"}</li>
        <li>Recommended method: {summary?.recommended_for_deployment ?? "—"}</li>
      </ul>
    </div>
  );
};

export default ResultsPanel;
