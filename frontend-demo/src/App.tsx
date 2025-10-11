import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactElement,
  type TouchEvent as ReactTouchEvent,
} from "react";
import "./App.css";

interface DemoRun {
  id: string;
  display_name: string;
  input_filename?: string | null;
  attacked_filename?: string | null;
  files: Record<string, boolean>;
}

interface TableRow {
  AI?: string;
  Correct?: string | number;
  Incorrect?: string | number;
  Total?: string | number;
  Accuracy?: string | number;
  [key: string]: unknown;
}

interface QuestionOption {
  label: string;
  text: string;
}

interface DetectionTarget {
  type?: string;
  option?: string;
  text?: string;
}

interface DetectionInfo {
  target?: DetectionTarget;
  signal?: string;
  notes?: string;
}

interface AiEvaluation {
  model: string;
  status: string;
  similarity?: number;
  score?: number;
  resultSymbol?: string;
  answer?: string;
  summary?: string;
  bulletPoints?: string[];
}

interface QuestionReport {
  questionNumber: string;
  stem: string;
  questionType?: string;
  options: QuestionOption[];
  goldAnswer?: string;
  modification?: string;
  detection?: DetectionInfo;
  aiEvaluations: AiEvaluation[];
}

type StageKey = 1 | 2 | 3;
type StageState = "idle" | "loading" | "ready" | "complete";

const API_BASE = import.meta.env.VITE_DEMO_API_BASE ?? "http://localhost:8000/api/demo";
const ANTI_CHEAT_MESSAGES = [
  "Generating AntiCheat PDF…",
  "Locking replacements…",
  "Embedding overlays…",
  "Finalizing secure draft…",
];

const RESULT_SYMBOL_STATUS: Record<string, "correct" | "incorrect"> = {
  "✓": "correct",
  "✔": "correct",
  "✗": "incorrect",
  "✘": "incorrect",
};

function randomDelay(minMs: number, maxMs: number): number {
  return Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
}

function formatQuestionSectionLabel(questionType?: string): string {
  if (!questionType) {
    return "Questions";
  }
  const normalized = questionType.toLowerCase();
  switch (normalized) {
    case "mcq_single":
      return "Multiple Choice";
    case "mcq_multi":
      return "Multiple Choice (Multi)";
    case "true_false":
      return "True / False";
    case "solve":
      return "Solve";
    case "short_answer":
      return "Short Answer";
    default:
      return "Questions";
  }
}

function createInitialStageStates(): Record<StageKey, StageState> {
  return { 1: "idle", 2: "idle", 3: "idle" };
}

function normalizeAiEvaluation(value: unknown): AiEvaluation {
  const record = (typeof value === "object" && value !== null ? value : {}) as Record<string, unknown>;
  const model = typeof record.model === "string" && record.model.trim() ? record.model : "Unknown";
  let statusRaw = typeof record.status === "string" ? record.status.toLowerCase().trim() : undefined;
  if (!statusRaw && typeof record.result === "string") {
    statusRaw = record.result.toLowerCase().trim();
  }
  const resultSymbol = typeof record.resultSymbol === "string" && record.resultSymbol.trim()
    ? record.resultSymbol.trim()
    : typeof record.result_symbol === "string" && record.result_symbol.trim()
      ? record.result_symbol.trim()
      : undefined;

  let status: string = statusRaw ?? "pending";
  if (statusRaw && !["correct", "incorrect", "pending"].includes(statusRaw)) {
    status = RESULT_SYMBOL_STATUS[resultSymbol ?? ""] ?? "pending";
  } else if (!statusRaw && resultSymbol) {
    status = RESULT_SYMBOL_STATUS[resultSymbol] ?? "pending";
  }

  const score = typeof record.score === "number"
    ? record.score
    : typeof record.similarity === "number"
      ? record.similarity
      : undefined;
  const similarity = typeof record.similarity === "number" ? record.similarity : undefined;
  const answer = typeof record.answer === "string" ? record.answer : undefined;
  const summary = typeof record.summary === "string" ? record.summary : undefined;
  const bulletPoints = Array.isArray(record.bulletPoints)
    ? record.bulletPoints.filter((point): point is string => typeof point === "string")
    : undefined;

  return {
    model,
    status,
    similarity,
    score,
    resultSymbol,
    answer,
    summary,
    bulletPoints,
  };
}

function LoadingIndicator({ label }: { label: string }): ReactElement {
  return (
    <div className="loading-indicator" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function App(): ReactElement {
  const [runs, setRuns] = useState<DemoRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [paneLocked, setPaneLocked] = useState(false);
  const [activeStage, setActiveStage] = useState<StageKey>(1);
  const [stageStates, setStageStates] = useState<Record<StageKey, StageState>>(createInitialStageStates);

  const [vulnerabilityOverview, setVulnerabilityOverview] = useState<TableRow[]>([]);
  const [referenceOverview, setReferenceOverview] = useState<TableRow[]>([]);
  const [vulnerabilityQuestions, setVulnerabilityQuestions] = useState<QuestionReport[]>([]);
  const [referenceQuestions, setReferenceQuestions] = useState<QuestionReport[]>([]);
  const [queuedVulnerabilityQuestions, setQueuedVulnerabilityQuestions] = useState<QuestionReport[]>([]);
  const [queuedReferenceQuestions, setQueuedReferenceQuestions] = useState<QuestionReport[]>([]);
  const [activeVulnerabilityIndex, setActiveVulnerabilityIndex] = useState<number>(-1);
  const [activeReferenceIndex, setActiveReferenceIndex] = useState<number>(-1);
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [runInProgress, setRunInProgress] = useState(false);
  const [createButtonVisible, setCreateButtonVisible] = useState(false);
  const [hasGeneratedAntiCheat, setHasGeneratedAntiCheat] = useState(false);

  const [showInputPdf, setShowInputPdf] = useState(false);
  const [showAttackedPdf, setShowAttackedPdf] = useState(false);
  const [inputPdfLoaded, setInputPdfLoaded] = useState(false);
  const [attackedPdfLoaded, setAttackedPdfLoaded] = useState(false);
  const [stageOneFetchStarted, setStageOneFetchStarted] = useState(false);
  const [stageTwoFetchStarted, setStageTwoFetchStarted] = useState(false);
  const [antiCheatMessageIndex, setAntiCheatMessageIndex] = useState(0);
  const [vulnerabilitySlideDirection, setVulnerabilitySlideDirection] = useState<"" | "forward" | "backward">("");
  const [referenceSlideDirection, setReferenceSlideDirection] = useState<"" | "forward" | "backward">("");

  const timerHandlesRef = useRef<number[]>([]);
  const antiCheatTimerRef = useRef<number | null>(null);
  const vulnerabilityPrevIndexRef = useRef(-1);
  const referencePrevIndexRef = useRef(-1);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  useEffect(() => {
    fetch(`${API_BASE}/runs`)
      .then((res) => res.json())
      .then((data) => setRuns(data.runs ?? []))
      .catch((err) => {
        console.error("Failed to load runs", err);
        setRuns([]);
      });
  }, []);

  const clearTimers = useCallback(() => {
    timerHandlesRef.current.forEach((handle) => window.clearTimeout(handle));
    timerHandlesRef.current = [];
  }, []);

  const hydrateQuestion = useCallback((raw: unknown): QuestionReport => {
    const base = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;

    const rawQuestionNumber = typeof base.questionNumber === "string" && base.questionNumber.trim()
      ? base.questionNumber.trim()
      : typeof base.question_id === "string" && base.question_id.trim()
        ? base.question_id.trim()
        : typeof base.questionId === "string" && base.questionId.trim()
          ? base.questionId.trim()
          : "Question";
    const questionNumber = /^Q0*\d+$/i.test(rawQuestionNumber)
      ? `Q${rawQuestionNumber.replace(/^Q0*/i, "")}`
      : rawQuestionNumber;

    const stem = typeof base.stem === "string" && base.stem.trim()
      ? base.stem
      : typeof base.prompt === "string" && base.prompt.trim()
        ? base.prompt
        : typeof base.questionStem === "string" && base.questionStem.trim()
          ? base.questionStem
          : "";

    const questionType = typeof base.questionType === "string"
      ? base.questionType
      : typeof base.question_type === "string"
        ? base.question_type
        : undefined;

    const optionsInput = Array.isArray(base.options) ? base.options : [];
    const options: QuestionOption[] = optionsInput
      .map((item) => (typeof item === "object" && item !== null ? item : null))
      .filter((item): item is Record<string, unknown> => item !== null)
      .map((item) => ({
        label: typeof item.label === "string" ? item.label : "",
        text: typeof item.text === "string" ? item.text : "",
      }))
      .filter((opt) => opt.label && opt.text)
      .sort((a, b) => a.label.localeCompare(b.label));

    const goldAnswer = typeof base.goldAnswer === "string" && base.goldAnswer.trim()
      ? base.goldAnswer
      : typeof base.gold_answer === "string"
        ? base.gold_answer
        : undefined;
    const modification = typeof base.modification === "string"
      ? base.modification
      : typeof base.mappingSummary === "string"
        ? base.mappingSummary
        : undefined;

    const targetValue = base.target;
    let fallbackTarget: DetectionTarget | undefined;
    if (typeof targetValue === "object" && targetValue !== null) {
      const targetRecord = targetValue as Record<string, unknown>;
      fallbackTarget = {
        type: typeof targetRecord.type === "string" ? targetRecord.type : undefined,
        option: typeof targetRecord.option === "string" ? targetRecord.option : undefined,
        text: typeof targetRecord.text === "string" ? targetRecord.text : undefined,
      };
    }

    const targetSignal = typeof base.target_signal === "string" && base.target_signal.trim()
      ? base.target_signal.trim()
      : undefined;
    const detectionNotes = typeof base.detection_notes === "string" && base.detection_notes.trim()
      ? base.detection_notes.trim()
      : undefined;

    if (!fallbackTarget && targetSignal) {
      const optionMatch = targetSignal.match(/option\s+([A-Z])/i);
      if (optionMatch) {
        fallbackTarget = {
          option: optionMatch[1].toUpperCase(),
          text: targetSignal,
        };
      }
    }

    const detectionValue = base.detection;
    let detection: DetectionInfo | undefined;
    if (typeof detectionValue === "object" && detectionValue !== null) {
      const detectionRecord = detectionValue as Record<string, unknown>;
      const signal = typeof detectionRecord.signal === "string" ? detectionRecord.signal : undefined;
      const notes = typeof detectionRecord.notes === "string" ? detectionRecord.notes : undefined;
      const detectionTargetValue = detectionRecord.target;
      let detectionTarget = fallbackTarget;
      if (typeof detectionTargetValue === "object" && detectionTargetValue !== null) {
        const targetRecord = detectionTargetValue as Record<string, unknown>;
        detectionTarget = {
          type: typeof targetRecord.type === "string" ? targetRecord.type : undefined,
          option: typeof targetRecord.option === "string" ? targetRecord.option : undefined,
          text: typeof targetRecord.text === "string" ? targetRecord.text : undefined,
        };
      }
      detection = {
        target: detectionTarget,
        signal,
        notes,
      };
    } else if (fallbackTarget || targetSignal || detectionNotes) {
      detection = {
        target: fallbackTarget,
        signal: targetSignal,
        notes: detectionNotes,
      };
    }

    const aiEvaluationsRaw = Array.isArray(base.aiEvaluations)
      ? base.aiEvaluations
      : Array.isArray((base as Record<string, unknown>).llmAnswers)
        ? ((base as Record<string, unknown>).llmAnswers as unknown[])
        : Array.isArray((base as Record<string, unknown>).llm_answers)
          ? ((base as Record<string, unknown>).llm_answers as unknown[])
          : [];
    const aiEvaluations = aiEvaluationsRaw.map((entry) => normalizeAiEvaluation(entry));

    return {
      questionNumber,
      stem,
      questionType,
      options,
      goldAnswer,
      modification,
      detection,
      aiEvaluations,
    };
  }, []);

  const resetSessionState = useCallback(() => {
    clearTimers();
    setActiveStage(1);
    setStageStates(createInitialStageStates());
    setPaneLocked(false);
    setShowInputPdf(false);
    setShowAttackedPdf(false);
    setInputPdfLoaded(false);
    setAttackedPdfLoaded(false);
    setStageOneFetchStarted(false);
    setStageTwoFetchStarted(false);
    setVulnerabilityOverview([]);
    setReferenceOverview([]);
    setVulnerabilityQuestions([]);
    setReferenceQuestions([]);
    setQueuedVulnerabilityQuestions([]);
    setQueuedReferenceQuestions([]);
    setActiveVulnerabilityIndex(-1);
    setActiveReferenceIndex(-1);
    setSidebarCollapsed(false);
    setAntiCheatMessageIndex(0);
    setRunInProgress(false);
    setCreateButtonVisible(false);
    setHasGeneratedAntiCheat(false);
    if (antiCheatTimerRef.current !== null) {
      window.clearInterval(antiCheatTimerRef.current);
      antiCheatTimerRef.current = null;
    }
  }, [clearTimers]);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const streamRows = useCallback(
    (rows: TableRow[], onAppend: (row: TableRow) => void, onComplete: () => void) => {
      if (rows.length === 0) {
        onComplete();
        return;
      }

      let index = 0;
      const scheduleNext = (delayMs: number) => {
        const timeoutId = window.setTimeout(() => {
          onAppend(rows[index]);
          index += 1;
          if (index < rows.length) {
            scheduleNext(randomDelay(1000, 1250));
          } else {
            onComplete();
          }
        }, delayMs);
        timerHandlesRef.current.push(timeoutId);
      };

      scheduleNext(2500);
    },
    []
  );

  const stageOneState = stageStates[1];
  const stageTwoState = stageStates[2];
  const antiCheatMessage = ANTI_CHEAT_MESSAGES[antiCheatMessageIndex % ANTI_CHEAT_MESSAGES.length];

  useEffect(() => {
    const prev = vulnerabilityPrevIndexRef.current;
    if (activeVulnerabilityIndex === prev) {
      return;
    }
    let direction: "" | "forward" | "backward" = "";
    if (activeVulnerabilityIndex !== -1 && prev !== -1) {
      direction = activeVulnerabilityIndex > prev ? "forward" : "backward";
    }
    vulnerabilityPrevIndexRef.current = activeVulnerabilityIndex;
    if (!direction) {
      setVulnerabilitySlideDirection("");
      return;
    }
    setVulnerabilitySlideDirection(direction);
    const timeout = window.setTimeout(() => setVulnerabilitySlideDirection(""), 350);
    return () => window.clearTimeout(timeout);
  }, [activeVulnerabilityIndex]);

  useEffect(() => {
    const prev = referencePrevIndexRef.current;
    if (activeReferenceIndex === prev) {
      return;
    }
    let direction: "" | "forward" | "backward" = "";
    if (activeReferenceIndex !== -1 && prev !== -1) {
      direction = activeReferenceIndex > prev ? "forward" : "backward";
    }
    referencePrevIndexRef.current = activeReferenceIndex;
    if (!direction) {
      setReferenceSlideDirection("");
      return;
    }
    setReferenceSlideDirection(direction);
    const timeout = window.setTimeout(() => setReferenceSlideDirection(""), 350);
    return () => window.clearTimeout(timeout);
  }, [activeReferenceIndex]);

  useEffect(() => {
    if (!runInProgress || hasGeneratedAntiCheat) {
      setCreateButtonVisible(false);
      return;
    }
    if (activeStage === 1 && stageOneState === "complete") {
      setCreateButtonVisible(true);
    } else if (activeStage !== 1) {
      setCreateButtonVisible(false);
    }
  }, [runInProgress, hasGeneratedAntiCheat, activeStage, stageOneState]);

  useEffect(() => {
    if (!selectedRunId || stageOneState !== "loading" || stageOneFetchStarted) {
      return;
    }
    setStageOneFetchStarted(true);

    fetch(`${API_BASE}/runs/${selectedRunId}/vulnerability`)
      .then((res) => res.json())
      .then((payload) => {
        const overviewRows: TableRow[] = Array.isArray(payload.overview) ? payload.overview : [];
        const questionsRaw = Array.isArray(payload.questions) ? payload.questions : [];
        const questions = questionsRaw.map(hydrateQuestion);
        setQueuedVulnerabilityQuestions(questions);
        setVulnerabilityOverview([]);
        setActiveVulnerabilityIndex(-1);
        setVulnerabilityQuestions([]);
        streamRows(
          overviewRows,
          (row) => {
            setVulnerabilityOverview((prev) => [...prev, row]);
          },
          () => {
            setVulnerabilityQuestions(questions);
            setStageStates((prev) => ({ ...prev, 1: "complete" }));
          }
        );
      })
      .catch((error) => {
        console.error("Failed to load vulnerability report", error);
        setQueuedVulnerabilityQuestions([]);
        setVulnerabilityOverview([]);
        setVulnerabilityQuestions([]);
        setStageStates((prev) => ({ ...prev, 1: "complete" }));
      });
  }, [selectedRunId, stageOneState, stageOneFetchStarted, hydrateQuestion, streamRows]);

  useEffect(() => {
    if (!selectedRunId || stageTwoState !== "loading" || stageTwoFetchStarted || !attackedPdfLoaded) {
      return;
    }
    setStageTwoFetchStarted(true);

    fetch(`${API_BASE}/runs/${selectedRunId}/reference`)
      .then((res) => res.json())
      .then((payload) => {
        const overviewRows: TableRow[] = Array.isArray(payload.overview) ? payload.overview : [];
        const questionsRaw = Array.isArray(payload.questions) ? payload.questions : [];
        const questions = questionsRaw.map(hydrateQuestion);
        setQueuedReferenceQuestions(questions);
        setReferenceOverview([]);
        setActiveReferenceIndex(-1);
        setReferenceQuestions([]);
        streamRows(
          overviewRows,
          (row) => {
            setReferenceOverview((prev) => [...prev, row]);
          },
          () => {
            setReferenceQuestions(questions);
            setStageStates((prev) => ({ ...prev, 2: "complete", 3: "ready" }));
          }
        );
      })
      .catch((error) => {
        console.error("Failed to load reference report", error);
        setQueuedReferenceQuestions([]);
        setReferenceOverview([]);
        setReferenceQuestions([]);
        setStageStates((prev) => ({ ...prev, 2: "complete", 3: "ready" }));
      });
  }, [selectedRunId, stageTwoState, stageTwoFetchStarted, attackedPdfLoaded, hydrateQuestion, streamRows]);

  const startSession = useCallback(() => {
    if (!selectedRunId) {
      return;
    }
    resetSessionState();
    setPaneLocked(true);
    setSidebarCollapsed(true);
    setActiveStage(1);
    setStageStates({ 1: "loading", 2: "idle", 3: "idle" });
    setShowInputPdf(true);
    setInputPdfLoaded(false);
    setStageOneFetchStarted(false);
    setStageTwoFetchStarted(false);
    setRunInProgress(true);
    setCreateButtonVisible(false);
    setHasGeneratedAntiCheat(false);
  }, [resetSessionState, selectedRunId]);

  const proceedToStageTwo = useCallback(() => {
    if (!selectedRunId) {
      return;
    }
    setActiveStage(2);
    setStageStates((prev) => ({ ...prev, 2: "loading", 3: "idle" }));
    setShowAttackedPdf(false);
    setAttackedPdfLoaded(false);
    setStageTwoFetchStarted(false);
    setActiveReferenceIndex(-1);
    setCreateButtonVisible(false);
    setHasGeneratedAntiCheat(true);

    const revealTimer = window.setTimeout(() => {
      setShowAttackedPdf(true);
    }, 2000);
    timerHandlesRef.current.push(revealTimer);
  }, [selectedRunId]);

  const handleRefresh = useCallback(() => {
    resetSessionState();
  }, [resetSessionState]);

  useEffect(() => {
    if (stageTwoState === "loading" && !attackedPdfLoaded) {
      setAntiCheatMessageIndex(0);
      if (antiCheatTimerRef.current !== null) {
        window.clearInterval(antiCheatTimerRef.current);
      }
      antiCheatTimerRef.current = window.setInterval(() => {
        setAntiCheatMessageIndex((prev) => (prev + 1) % ANTI_CHEAT_MESSAGES.length);
      }, 2500);
      return () => {
        if (antiCheatTimerRef.current !== null) {
          window.clearInterval(antiCheatTimerRef.current);
          antiCheatTimerRef.current = null;
        }
      };
    }
    if (antiCheatTimerRef.current !== null) {
      window.clearInterval(antiCheatTimerRef.current);
      antiCheatTimerRef.current = null;
    }
  }, [stageTwoState, attackedPdfLoaded]);

  const renderOverviewTable = (rows: TableRow[]) => (
    <table className="data-table">
      <thead>
        <tr>
          <th>AI</th>
          <th>Correct</th>
          <th>Incorrect</th>
          <th>Total</th>
          <th>Accuracy</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, idx) => (
          <tr key={`${row.AI ?? idx}`}>
            <td>{row.AI ?? "—"}</td>
            <td>{row.Correct ?? "—"}</td>
            <td>{row.Incorrect ?? "—"}</td>
            <td>{row.Total ?? "—"}</td>
            <td>{row.Accuracy ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderQuestionReport = (
    report: QuestionReport | undefined,
    variant: "vulnerability" | "reference",
    slideDirection: "" | "forward" | "backward"
  ) => {
    if (!report) {
      return <div className="placeholder">Select a question to review its analysis.</div>;
    }

    const detection = variant === "reference" ? report.detection : undefined;
    const slideClass = slideDirection ? `slide-${slideDirection}` : "";

    return (
      <div className={`question-report ${slideClass}`}>
        <header className="question-header">
          <div className="question-meta">
            <span className="question-id">{report.questionNumber}</span>
            {report.questionType && <span className="question-type">{report.questionType}</span>}
          </div>
          <p className="question-stem">{report.stem}</p>
          {report.options.length > 0 && (
            <div className="question-options">
              <h4>Options</h4>
              <ul className="options-list">
                {report.options.map((option) => (
                  <li key={option.label}>
                    <span className="option-label">{option.label}.</span>
                    <span>{option.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.goldAnswer && (
            <p className="question-gold">
              <strong>Gold Answer:</strong> {report.goldAnswer}
            </p>
          )}
          {variant === "reference" && detection && (
            <div className="question-detection">
              <strong>Detection Cue:</strong>
              <div className="detection-body">
                {report.goldAnswer && (
                  <p className="detection-gold">Gold Answer: {report.goldAnswer}</p>
                )}
                {detection.signal && <p className="detection-signal">Signal: {detection.signal}</p>}
                {detection.notes && <p className="detection-notes">{detection.notes}</p>}
              </div>
            </div>
          )}
        </header>
        <div className="evaluation-grid">
          {report.aiEvaluations.length === 0 && (
            <div className="evaluation-card empty">
              No AI evaluations have been recorded yet.
            </div>
          )}
          {report.aiEvaluations.map((evaluation, idx) => (
            <article key={`${evaluation.model}-${idx}`} className="evaluation-card">
              <header>
                <div className="evaluation-status-row">
                  <span className={`status-badge status-${evaluation.status}`}>
                    {evaluation.status.toUpperCase()}
                  </span>
                  {evaluation.resultSymbol && (
                    <span className={`result-symbol result-symbol--${evaluation.status}`}>
                      {evaluation.resultSymbol}
                    </span>
                  )}
                </div>
                <h4>{evaluation.model}</h4>
                {typeof evaluation.score === "number" ? (
                  <span className="similarity">Score: {evaluation.score.toFixed(3)}</span>
                ) : typeof evaluation.similarity === "number" ? (
                  <span className="similarity">Score: {evaluation.similarity.toFixed(3)}</span>
                ) : null}
              </header>
              {evaluation.answer && (
                <p className="evaluation-answer">
                  <strong>Answer:</strong> {evaluation.answer}
                </p>
              )}
              {evaluation.summary && <p className="evaluation-summary">{evaluation.summary}</p>}
              {evaluation.bulletPoints && evaluation.bulletPoints.length > 0 && (
                <ul>
                  {evaluation.bulletPoints.map((point, bulletIdx) => (
                    <li key={bulletIdx}>{point}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="brand">AntiCheatAI</div>
        <div className="header-actions">
          <button
            type="button"
            className="icon-button"
            onClick={handleRefresh}
            title="Reset session"
            disabled={stageStates[1] === "idle" && stageStates[2] === "idle" && stageStates[3] === "idle"}
          >
            ↻
          </button>
          {!runInProgress && (
            <button
              type="button"
              className="primary start-top"
              disabled={!selectedRun || paneLocked}
              onClick={startSession}
            >
              Start
            </button>
          )}
          {createButtonVisible && (
            <button
              type="button"
              className="primary secondary"
              onClick={proceedToStageTwo}
            >
              Create AntiCheat PDF
            </button>
          )}
        </div>
      </header>
      <div className="app-body">
        <aside
          className={[
            "sidebar",
            paneLocked ? "sidebar--locked" : "",
            isSidebarCollapsed ? "sidebar--collapsed" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <h2 className="sidebar-title">Uploaded PDFs</h2>
          <ul>
            {runs.map((run) => {
              const primaryName = run.display_name;
              const subtitle =
                run.input_filename && run.input_filename !== primaryName
                  ? run.input_filename
                  : undefined;
              return (
                <li key={run.id} className={run.id === selectedRunId ? "run-item active" : "run-item"}>
                  <button
                    type="button"
                    className={run.id === selectedRunId ? "selected" : ""}
                    onClick={() => !paneLocked && setSelectedRunId(run.id)}
                    disabled={paneLocked}
                  >
                    <span className="run-title">{primaryName}</span>
                    {subtitle && <span className="run-subtitle">{subtitle}</span>}
                  </button>
                  {run.id === selectedRunId && !isSidebarCollapsed && (
                    <RunThumbnails runId={run.id} inputLabel={primaryName} />
                  )}
                </li>
              );
            })}
          </ul>
        </aside>
        <button
          type="button"
          className={`sidebar-toggle ${isSidebarCollapsed ? "sidebar-toggle--collapsed" : ""}`}
          onClick={() => setSidebarCollapsed((prev) => !prev)}
          title={isSidebarCollapsed ? "Expand panel" : "Collapse panel"}
          aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!isSidebarCollapsed}
          style={{ left: isSidebarCollapsed ? "16px" : "284px" }}
        >
          {isSidebarCollapsed ? "›" : "‹"}
        </button>

        <main className="content">
          <nav className="stage-tabs">
            {[1, 2, 3].map((stage) => (
              <button
                key={stage}
                type="button"
                className={`stage-tab ${activeStage === stage ? "active" : ""}`}
                onClick={() => setActiveStage(stage as StageKey)}
                disabled={stageStates[stage as StageKey] === "idle"}
              >
                {stage === 1 && "Vulnerability"}
                {stage === 2 && "AntiCheat PDF"}
                {stage === 3 && "Resources"}
              </button>
            ))}
          </nav>

          {activeStage === 1 && (
            <section className="stage stage--split">
              <div className="stage-pane">
                {!showInputPdf && (
                  <div className="placeholder">
                    Select a run and press Start to preview the input PDF.
                  </div>
                )}
                {showInputPdf && selectedRun && (
                  <div className="pdf-container">
                    <iframe
                      key={`${selectedRun.id}-input`}
                      title="Input PDF"
                      src={`${API_BASE}/runs/${selectedRun.id}/pdf/input`}
                      className="pdf-frame"
                      onLoad={() => setInputPdfLoaded(true)}
                    />
                    {!inputPdfLoaded && (
                      <div className="pdf-overlay">
                        <LoadingIndicator label="Loading original PDF…" />
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="stage-pane">
                <h3>Vulnerability Report</h3>
                <QuestionNavigation
                  label={formatQuestionSectionLabel(queuedVulnerabilityQuestions[0]?.questionType)}
                  disabled={stageStates[1] !== "complete"}
                  questionLabels={queuedVulnerabilityQuestions.map((q) => q.questionNumber)}
                  activeIndex={activeVulnerabilityIndex}
                  onSelect={setActiveVulnerabilityIndex}
                />
                {activeVulnerabilityIndex === -1 && (
                  <div className="table-wrapper">
                    {stageOneState === "idle" && vulnerabilityOverview.length === 0 ? (
                      <div className="waiting-block">
                        Press Start to begin the vulnerability analysis.
                      </div>
                    ) : vulnerabilityOverview.length === 0 && stageOneState === "loading" ? (
                      <div className="loading-block">
                        <LoadingIndicator label="Analyzing vulnerability data…" />
                      </div>
                    ) : (
                      renderOverviewTable(vulnerabilityOverview)
                    )}
                    {stageOneState === "loading" && vulnerabilityOverview.length > 0 && (
                      <div className="table-overlay">
                        <LoadingIndicator label="Analyzing vulnerability data…" />
                      </div>
                    )}
                  </div>
                )}
                {activeVulnerabilityIndex !== -1 &&
                  renderQuestionReport(
                    vulnerabilityQuestions[activeVulnerabilityIndex],
                    "vulnerability",
                    vulnerabilitySlideDirection
                  )}
              </div>
            </section>
          )}

          {activeStage === 2 && (
            <section className="stage stage--split">
              <div className="stage-pane">
                {!showAttackedPdf && (
                  <div className="placeholder">{antiCheatMessage}</div>
                )}
                {showAttackedPdf && selectedRun && (
                  <div className="pdf-container">
                    <iframe
                      key={`${selectedRun.id}-attacked`}
                      title="AntiCheat PDF"
                      src={`${API_BASE}/runs/${selectedRun.id}/pdf/attacked`}
                      className="pdf-frame"
                      onLoad={() => setAttackedPdfLoaded(true)}
                    />
                    {!attackedPdfLoaded && (
                      <div className="pdf-overlay">
                        <LoadingIndicator label={antiCheatMessage} />
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="stage-pane">
                <h3>Reference Report</h3>
                <QuestionNavigation
                  label={formatQuestionSectionLabel(queuedReferenceQuestions[0]?.questionType)}
                  disabled={stageStates[2] !== "complete"}
                  questionLabels={queuedReferenceQuestions.map((q) => q.questionNumber)}
                  activeIndex={activeReferenceIndex}
                  onSelect={setActiveReferenceIndex}
                />
                {activeReferenceIndex === -1 && (
                  <div className="table-wrapper">
                    {referenceOverview.length === 0 && stageStates[2] !== "complete" ? (
                      <div className="loading-block">
                        <LoadingIndicator label="Compiling reference insights…" />
                      </div>
                    ) : (
                      renderOverviewTable(referenceOverview)
                    )}
                    {stageStates[2] !== "complete" && referenceOverview.length > 0 && (
                      <div className="table-overlay">
                        <LoadingIndicator label="Compiling reference insights…" />
                      </div>
                    )}
                  </div>
                )}
                {activeReferenceIndex !== -1 &&
                  renderQuestionReport(
                    referenceQuestions[activeReferenceIndex],
                    "reference",
                    referenceSlideDirection
                  )}
              </div>
            </section>
          )}

          {activeStage === 3 && (
            <section className="stage">
              <div className="summary-grid">
                {selectedRun && (
                  <>
                    <SummaryCard
                      title="Input PDF"
                      description="Original assessment"
                      href={`${API_BASE}/runs/${selectedRun.id}/pdf/input`}
                    />
                    <SummaryCard
                      title="AntiCheat PDF"
                      description="Hardened output"
                      href={`${API_BASE}/runs/${selectedRun.id}/pdf/attacked`}
                    />
                    <SummaryCard
                      title="Vulnerability Report"
                      description="Stage 1 analysis (JSON)"
                      href={`${API_BASE}/runs/${selectedRun.id}/vulnerability`}
                      downloadName={`${selectedRun.id}-vulnerability.json`}
                    />
                    <SummaryCard
                      title="Reference Report"
                      description="Stage 2 analysis (JSON)"
                      href={`${API_BASE}/runs/${selectedRun.id}/reference`}
                      downloadName={`${selectedRun.id}-reference.json`}
                    />
                  </>
                )}
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

function QuestionNavigation({
  label,
  questionLabels,
  activeIndex,
  onSelect,
  disabled = false,
}: {
  label: string;
  questionLabels: string[];
  activeIndex: number;
  onSelect: (index: number) => void;
  disabled?: boolean;
}) {
  const displayLabel = label || "Questions";
  const safeLabels = Array.isArray(questionLabels)
    ? questionLabels.map((item, idx) => {
        if (typeof item !== "string" || !item.trim()) {
          return `Q${idx + 1}`;
        }
        return item.trim();
      })
    : [];
  const safeCount = safeLabels.length;
  const canNavigate = !disabled && safeCount > 0;

  const trackRef = useRef<HTMLDivElement | null>(null);
  const touchStartRef = useRef<number | null>(null);

  const cycleIndex = useCallback(
    (delta: number) => {
      if (!canNavigate || safeCount === 0) {
        return;
      }
      const baseIndex = activeIndex === -1 ? (delta > 0 ? 0 : safeCount - 1) : activeIndex;
      const nextIndex = (baseIndex + delta + safeCount) % safeCount;
      onSelect(nextIndex);
    },
    [activeIndex, canNavigate, onSelect, safeCount]
  );

  const handlePrev = useCallback(() => {
    cycleIndex(-1);
  }, [cycleIndex]);

  const handleNext = useCallback(() => {
    cycleIndex(1);
  }, [cycleIndex]);

  useEffect(() => {
    if (!trackRef.current || activeIndex < 0) {
      return;
    }
    const chips = trackRef.current.querySelectorAll<HTMLButtonElement>(".question-chip");
    const target = chips[activeIndex];
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
  }, [activeIndex]);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!canNavigate) {
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      cycleIndex(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      cycleIndex(-1);
    }
  };

  const handleTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
    touchStartRef.current = event.touches[0]?.clientX ?? null;
  };

  const handleTouchEnd = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (!canNavigate) {
      touchStartRef.current = null;
      return;
    }
    const startX = touchStartRef.current;
    touchStartRef.current = null;
    const endX = event.changedTouches[0]?.clientX;
    if (startX === null || endX === undefined) {
      return;
    }
    const delta = startX - endX;
    if (Math.abs(delta) > 40) {
      cycleIndex(delta > 0 ? 1 : -1);
    }
  };

  return (
    <div className="question-navigation">
      <div className="question-navigation__label">
        {displayLabel}
        <span className="question-navigation__count">{safeCount} items</span>
      </div>
      <div className="question-navigation__controls">
        <button
          type="button"
          className="question-nav-btn"
          onClick={() => onSelect(-1)}
          disabled={disabled}
          role="tab"
          aria-selected={activeIndex === -1}
        >
          Overview
        </button>
        <div
          className="question-carousel"
          role="tablist"
          aria-orientation="horizontal"
          tabIndex={disabled ? -1 : 0}
          onKeyDown={handleKeyDown}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          <div className="question-carousel__track" ref={trackRef}>
            {safeLabels.map((questionLabel, idx) => (
              <button
                type="button"
                key={`${questionLabel}-${idx}`}
                className={`question-chip ${idx === activeIndex ? "active" : ""}`}
                onClick={() => onSelect(idx)}
                disabled={!canNavigate}
                aria-selected={idx === activeIndex}
                role="tab"
              >
                {questionLabel || `Q${idx + 1}`}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="question-navigation__pager">
        <button
          type="button"
          className="question-carousel__arrow"
          onClick={handlePrev}
          disabled={!canNavigate}
          aria-label="Previous question"
        >
          ‹
        </button>
        <span className="pager-label">
          {safeCount === 0
            ? "No questions"
            : activeIndex === -1
              ? `Overview · ${safeCount} questions`
              : `${safeLabels[activeIndex] ?? `Q${activeIndex + 1}`} • ${activeIndex + 1}/${safeCount}`}
        </span>
        <button
          type="button"
          className="question-carousel__arrow"
          onClick={handleNext}
          disabled={!canNavigate}
          aria-label="Next question"
        >
          ›
        </button>
      </div>
    </div>
  );
}

interface SummaryCardProps {
  title: string;
  description: string;
  href: string;
  downloadName?: string;
}

function SummaryCard({ title, description, href, downloadName }: SummaryCardProps) {
  return (
    <article className="summary-card">
      <div className="thumbnail" aria-hidden="true" />
      <h4>{title}</h4>
      <p>{description}</p>
      <a className="download" href={href} download={downloadName} target="_blank" rel="noreferrer">
        Download
      </a>
    </article>
  );
}

interface RunThumbnailsProps {
  runId: string;
  inputLabel: string;
}

function RunThumbnails({ runId, inputLabel }: RunThumbnailsProps) {
  const [showInput, setShowInput] = useState(true);
  const [cacheBuster] = useState(() => Date.now());
  const thumbSuffix = `?v=${cacheBuster}`;

  if (!showInput) {
    return null;
  }

  return (
    <div className="run-thumbnails">
      <figure className="run-thumbnail" aria-label={`${inputLabel} preview`}>
        <img
          src={`${API_BASE}/runs/${runId}/pdf/input/thumbnail${thumbSuffix}`}
          alt={`${inputLabel} preview`}
          onError={() => setShowInput(false)}
        />
      </figure>
    </div>
  );
}

export default App;
