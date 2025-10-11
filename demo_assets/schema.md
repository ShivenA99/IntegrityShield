# Demo Table Schema (Placeholder)

## Overview CSV (`vulnerability_report.csv`, `reference_report.csv`)

```
AI,Correct,Incorrect,Total,Accuracy
ChatGPT,18,2,20,0.90
...
```

Accuracy can be numeric or string (e.g., `90%`).

## Question JSON (`vulnerability_questions.json`, `reference_questions.json`)

```ts
interface QuestionReport {
  questionNumber: string;        // e.g., "Q1"
  stem: string;                  // question prompt
  goldAnswer?: string;           // optional target answer text
  mappingSummary?: string;       // optional manipulated span summary
  target?: Record<string, unknown>; // optional metadata (signal/target info)
  aiEvaluations: AiEvaluation[];
}

interface AiEvaluation {
  model: string;                 // model name (e.g., "ChatGPT")
  status: 'correct' | 'incorrect' | string;
  similarity?: number;           // similarity score (0-1)
  summary?: string;              // descriptive text
  bulletPoints?: string[];       // optional bullet list of key points
}
```

The demo UI renders tabs for each question plus an "Overall" tab that shows the CSV overview.
