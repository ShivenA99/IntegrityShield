import * as React from "react";

import type { QuestionManipulation } from "@services/types/questions";
import QuestionViewer from "./QuestionViewer";

interface Props {
  runId: string;
  question: QuestionManipulation;
  onUpdated?: () => void;
}

const QuestionTypeSpecializer: React.FC<Props> = ({ runId, question, onUpdated }) => {
  // For now, we reuse QuestionViewer and in the future can branch by question.question_type
  return <QuestionViewer runId={runId} question={question} onUpdated={(q) => onUpdated?.()} />;
};

export default QuestionTypeSpecializer;
