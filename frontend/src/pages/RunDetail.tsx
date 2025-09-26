import * as React from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import QuestionViewer from "@components/question-level/QuestionViewer";
import EffectivenessIndicator from "@components/question-level/EffectivenessIndicator";
import MappingControls from "@components/question-level/MappingControls";

const RunDetail: React.FC = () => {
  const { activeRunId } = usePipeline();
  const { questions } = useQuestions(activeRunId);
  const runId = String(activeRunId || "");

  return (
    <div className="page run-detail">
      <h2>Run Detail</h2>
      {questions.map((question) => (
        <div key={question.id} className="question-card">
          <QuestionViewer runId={runId} question={question} />
          <div className="question-meta">
            <span>Effectiveness: <EffectivenessIndicator value={question.effectiveness_score} /></span>
            <MappingControls />
          </div>
        </div>
      ))}
      {questions.length === 0 ? <p>No questions discovered yet.</p> : null}
    </div>
  );
};

export default RunDetail;
