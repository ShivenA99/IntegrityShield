import * as React from "react";
import { useEffect } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import { formatDuration } from "@services/utils/formatters";

const ContentDiscoveryPanel: React.FC = () => {
  const { status, activeRunId, resumeFromStage } = usePipeline();
  const { questions } = useQuestions(activeRunId);
  const stage = status?.stages.find((item) => item.name === "content_discovery");

  useEffect(() => {
    if (!activeRunId) return;
    if (stage?.status === "completed") {
      // Auto-advance to smart_substitution once discovery is done
      resumeFromStage(activeRunId, "smart_substitution").catch(() => {});
    }
  }, [activeRunId, stage?.status, resumeFromStage]);

  return (
    <div className="panel content-discovery">
      <h2>🎯 Content Discovery</h2>
      <p>Review detected questions, answer choices, and key document regions.</p>
      <div className="panel-card">
        <p>Status: {stage?.status ?? "pending"}</p>
        <p>Duration: {formatDuration(stage?.duration_ms)}</p>
      </div>
      <div className="panel-card">
        <h4>Detected Questions</h4>
        <ul>
          {questions.slice(0, 5).map((question) => (
            <li key={question.id}>
              Q{question.question_number}: {question.question_type}
            </li>
          ))}
        </ul>
        {questions.length === 0 ? <p>No questions detected yet.</p> : null}
      </div>
    </div>
  );
};

export default ContentDiscoveryPanel;
