import React from "react";

import { usePipeline } from "@hooks/usePipeline";

const EnhancementMethodPanel: React.FC = () => {
  const { status } = usePipeline();
  const structuredData = status?.structured_data as Record<string, any> | undefined;
  const results = structuredData?.manipulation_results?.enhanced_pdfs ?? {};

  return (
    <div className="panel enhancement-methods">
      <h2>⚡ Document Enhancement</h2>
      <p>Select and configure PDF rendering approaches.</p>
      <div className="method-grid">
        {Object.entries(results).map(([method, details]) => (
          <div key={method} className="panel-card">
            <h3>{method}</h3>
            <p>Effectiveness: {(details as any)?.effectiveness_score ?? "—"}</p>
            <p>Visual quality: {(details as any)?.visual_quality_score ?? "—"}</p>
          </div>
        ))}
        {Object.keys(results).length === 0 ? <p>No enhancements generated yet.</p> : null}
      </div>
    </div>
  );
};

export default EnhancementMethodPanel;
