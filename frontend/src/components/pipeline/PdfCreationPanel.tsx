import * as React from "react";

import { usePipeline } from "@hooks/usePipeline";

const PdfCreationPanel: React.FC = () => {
  const { status } = usePipeline();
  const stage = status?.stages.find((item) => item.name === "pdf_creation");
  const enhanced = (status?.structured_data as any)?.manipulation_results?.enhanced_pdfs || {};

  const entries = Object.entries(enhanced) as [string, { path: string; size_bytes: number; effectiveness_score?: number; visual_quality_score?: number }][];

  const onEvaluate = () => {
    // Placeholder: navigate to evaluation/testing panel if needed
    // The EffectivenessTestPanel handles actual multi-model tests.
  };

  return (
    <div className="panel pdf-creation">
      <h2>📑 Enhanced PDF Creation</h2>
      <p>Monitor rendering progress and generated artifacts.</p>
      <p>Status: {stage?.status ?? "pending"}</p>

      {entries.length > 0 && (
        <div className="panel-card">
          <h4>Generated Files</h4>
          <ul>
            {entries.map(([method, meta]) => (
              <li key={method}>
                <strong>{method}</strong>: {meta.size_bytes} bytes
                {meta.effectiveness_score != null ? `, eff: ${meta.effectiveness_score}` : ""}
                {meta.visual_quality_score != null ? `, vq: ${meta.visual_quality_score}` : ""}
                {meta.path ? (
                  <>
                    {" "}
                    <a href={meta.path} download>
                      Download
                    </a>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
          <button onClick={onEvaluate}>Evaluate</button>
        </div>
      )}
    </div>
  );
};

export default PdfCreationPanel;
