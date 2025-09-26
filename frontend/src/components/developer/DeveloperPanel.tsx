import * as React from "react";

import { useDeveloperContext } from "@contexts/DeveloperContext";
import { usePipeline } from "@hooks/usePipeline";
import { useDeveloperTools } from "@hooks/useDeveloperTools";
import { fetchStructuredData, fetchSystemHealth } from "@services/api/developerApi";
import LiveLogViewer from "./LiveLogViewer";
import PipelineDebugger from "./PipelineDebugger";
import StructuredDataViewer from "./StructuredDataViewer";
import PerformanceMetrics from "./PerformanceMetrics";
import DatabaseInspector from "./DatabaseInspector";

const DeveloperPanel: React.FC = () => {
  const { isDeveloperMode } = useDeveloperContext();
  const { status, activeRunId } = usePipeline();
  const { logs, metrics, isStreaming } = useDeveloperTools(activeRunId);
  const [structured, setStructured] = React.useState<Record<string, unknown> | null>(null);
  const [health, setHealth] = React.useState<Record<string, unknown> | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        if (activeRunId) {
          const [s, h] = await Promise.all([
            fetchStructuredData(activeRunId),
            fetchSystemHealth(),
          ]);
          if (!cancelled) {
            setStructured(s.data ?? {});
            setHealth(h ?? {});
          }
        }
      } catch (e) {
        // no-op
      }
    }
    if (isDeveloperMode && activeRunId) load();
    return () => { cancelled = true; };
  }, [isDeveloperMode, activeRunId]);

  if (!isDeveloperMode) return null;

  return (
    <div className="developer-panel">
      <LiveLogViewer logs={logs} isStreaming={isStreaming} />
      <PerformanceMetrics metrics={metrics} />
      <PipelineDebugger status={status} />
      <StructuredDataViewer data={structured ?? (status?.structured_data as Record<string, unknown>)} />
      <DatabaseInspector />
    </div>
  );
};

export default DeveloperPanel;
