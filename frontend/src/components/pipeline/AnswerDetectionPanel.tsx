import React from "react";

import { usePipeline } from "@hooks/usePipeline";
import { formatDuration } from "@services/utils/formatters";

const AnswerDetectionPanel: React.FC = () => {
  const { status } = usePipeline();
  const stage = status?.stages.find((item) => item.name === "answer_detection");

  return (
    <div className="panel answer-detection">
      <h2>✅ Answer Detection</h2>
      <p>Monitor AI-assisted identification of correct answers for each question.</p>
      <div className="panel-card">
        <p>Status: {stage?.status ?? "pending"}</p>
        <p>Duration: {formatDuration(stage?.duration_ms)}</p>
      </div>
    </div>
  );
};

export default AnswerDetectionPanel;
