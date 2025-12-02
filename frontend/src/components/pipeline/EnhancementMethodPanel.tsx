import React from "react";

import { usePipeline } from "@hooks/usePipeline";
import {
  ENHANCEMENT_METHOD_LABELS,
  ENHANCEMENT_METHOD_SUMMARY,
} from "@constants/enhancementMethods";

const EnhancementMethodPanel: React.FC = () => {
  const { status } = usePipeline();
  const structuredData = status?.structured_data as Record<string, any> | undefined;
  const results = structuredData?.manipulation_results?.enhanced_pdfs ?? {};

  const cards = Object.entries(results).map(([method, details]) => {
    const label = (ENHANCEMENT_METHOD_LABELS as Record<string, string>)[method] || method;
    const summary = (ENHANCEMENT_METHOD_SUMMARY as Record<string, string>)[method] || "";
    const stats = (details as any)?.render_stats || {};
    const replacements = stats.replacements ?? (details as any)?.replacements;
    const overlays = stats.overlay_applied ?? (details as any)?.overlay_applied;
    const overlayTargets = stats.overlay_targets ?? (details as any)?.overlay_targets;

    return (
      <div key={method} className="panel-card">
        <h3>{label}</h3>
        {summary ? <p style={{ color: "#6c757d", fontSize: "0.85em" }}>{summary}</p> : null}
        <p>Effectiveness: {(details as any)?.effectiveness_score ?? "—"}</p>
        <p>Visual quality: {(details as any)?.visual_quality_score ?? "—"}</p>
        {replacements != null ? <p>Replacements: {replacements}</p> : null}
        {overlays != null ? (
          <p>
            Overlays: {overlays}
            {overlayTargets != null ? ` / ${overlayTargets}` : ""}
          </p>
        ) : null}
      </div>
    );
  });

  return (
    <div className="panel enhancement-methods">
      <h2>⚡ Document Enhancement</h2>
      <p>Select and configure PDF rendering approaches.</p>
      <div className="method-grid">
        {cards}
        {cards.length === 0 ? <p>No enhancements generated yet.</p> : null}
      </div>
    </div>
  );
};

export default EnhancementMethodPanel;
