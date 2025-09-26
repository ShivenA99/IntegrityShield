import * as React from "react";

import { usePipeline } from "@hooks/usePipeline";
import { useQuestions } from "@hooks/useQuestions";
import QuestionViewer from "@components/question-level/QuestionTypeSpecializer";

const SmartSubstitutionPanel: React.FC = () => {
  const { activeRunId, resumeFromStage, status } = usePipeline();
  const { questions, isLoading, refresh } = useQuestions(activeRunId);

  const validatedCount = React.useMemo(() => {
    return questions.reduce((acc, q) => acc + ((q.substring_mappings?.length ?? 0) > 0 ? 1 : 0), 0);
  }, [questions]);

  const allValidated = questions.length > 0 && validatedCount === questions.length;

  const onFinalize = async () => {
    if (!activeRunId || !allValidated) return;
    await resumeFromStage(activeRunId, "pdf_creation");
  };

  React.useEffect(() => {
    if (status?.current_stage === "pdf_creation") {
      // no-op here; PipelineContainer reacts to status
    }
  }, [status?.current_stage]);

  return (
    <div className="panel smart-substitution">
      <h2>🔄 Smart Substitution</h2>
      <p>Pick multiple non-overlapping substring mappings per question. Progress: {validatedCount}/{questions.length}</p>
      {isLoading ? <p>Loading substitution data…</p> : null}

      <div className="panel-card" style={{ display: "grid", gap: 12 }}>
        {questions.map((q) => (
          <QuestionViewer key={q.id} runId={activeRunId!} question={q} onUpdated={refresh} />
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
        <button onClick={refresh} type="button">Refresh</button>
        <button onClick={onFinalize} disabled={!allValidated} title={!allValidated ? "Validate mappings for all questions first" : "Proceed to PDF creation"}>
          Finalize and proceed to PDF creation
        </button>
      </div>
    </div>
  );
};

export default SmartSubstitutionPanel;
