import React from "react";

import type { PipelineRunSummary } from "@services/types/pipeline";

interface PipelineDebuggerProps {
  status: PipelineRunSummary | null;
}

const PipelineDebugger: React.FC<PipelineDebuggerProps> = ({ status }) => (
  <div className="pipeline-debugger">
    <h3>Pipeline Debugger</h3>
    <pre>{JSON.stringify(status, null, 2)}</pre>
  </div>
);

export default PipelineDebugger;
