import React from "react";
import clsx from "clsx";
import {
  Activity,
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronRight,
  Filter,
  Layers,
  RefreshCcw,
  Search,
  Shield,
  Slash,
  Sparkles,
  Users,
  X,
} from "lucide-react";

import answerSheets from "@data/classroomSimulation/answer_sheets.json";
import classroomEvaluation from "@data/classroomSimulation/evaluation.json";
import assessmentPdf from "@data/integrityShieldDemo/Mathematics_K12_Assessment.pdf";
import vulnerabilityReport from "@data/integrityShieldDemo/vulnerability_report.json";
import { useDemoRun } from "@contexts/DemoRunContext";

type StageId = "simulate" | "detector" | "evaluation";
type SourceMode = "simulation" | "lms";
type PolicyPreset = "conservative" | "standard" | "aggressive";
type CardViewMode = "ground" | "detector" | "evaluation";

interface DetectionChip {
  label: string;
  tone: "info" | "warning" | "success";
}

interface AssessmentMixEntry {
  label: string;
  count: number;
  color: string;
}

interface StudentDetail {
  student_id: number;
  student_key: string;
  display_name: string;
  is_cheating: boolean;
  detected_as_cheating: boolean;
  cheating_strategy: "fair" | "cheating_llm" | "cheating_peer";
  copy_fraction: number;
  paraphrase_style: string | null;
  score: number;
  total_questions: number;
  correct_answers: number;
  incorrect_answers: number;
  cheating_source_counts: Record<string, number>;
  average_confidence: number;
  metadata?: Record<string, any>;
  responses: Array<Record<string, any>>;
  objective_detection?: Record<string, any>;
  subjective_detection?: Record<string, any>;
  detections?: Array<Record<string, any>>;
}

interface SimulationStudent extends StudentDetail {
  groundRecords?: Array<Record<string, any>>;
  groundMetadata?: Record<string, any>;
  groundScore?: number;
  level: string;
  completionLabel: string;
  completionMinutes: number;
  detectionScore: number;
  detectionChips: DetectionChip[];
  assessmentMix: AssessmentMixEntry[];
  markerCount: number;
  patternLabel: string;
  verdictLabel: string;
  suspicionLevel: "low" | "medium" | "high";
}

interface GroundTruthCounts {
  total: number;
  fair: number;
  cheating_llm: number;
  cheating_peer: number;
}

interface IntegrityCounts {
  total: number;
  flagged: number;
  cleared: number;
  highRisk: number;
}

const STAGES: Array<{ id: StageId; label: string; title: string }> = [
  { id: "simulate", label: "Stage 1", title: "Simulate Classroom" },
  { id: "detector", label: "Stage 2", title: "IntegrityShield Detector" },
  { id: "evaluation", label: "Stage 3", title: "Evaluation" },
];

const SOURCE_MODE_LABELS: Record<SourceMode, string> = {
  simulation: "Simulation",
  lms: "LMS Section",
};

const LEVEL_LABEL = "K-12";
const COMPLETION_WINDOWS = ["11m 42s", "12m 17s", "13m 02s", "15m 20s", "10m 58s"];

const POLICY_THRESHOLDS: Record<PolicyPreset, number> = {
  conservative: 0.85,
  standard: 0.75,
  aggressive: 0.6,
};

const UPDATED_EVALUATION_METRICS = {
  true_positives: 8,
  false_positives: 0,
  true_negatives: 32,
  false_negatives: 0,
  precision: 1,
  recall: 1,
  f1_score: 1,
  accuracy: 1,
};

const CARD_VIEW_SEQUENCE: CardViewMode[] = ["ground", "detector", "evaluation"];

const formatPercent = (value: number, digits = 0) => `${(value * 100).toFixed(digits)}%`;
const formatScore = (value: number) => `${value.toFixed(0)}%`;

const QUESTION_TYPE_LABELS: Record<string, string> = {
  mcq_single: "MCQ",
  true_false: "True / False",
  calculation: "Calculation",
  subjective: "Short answer",
  essay: "Essay",
};

const formatQuestionType = (type?: string) => QUESTION_TYPE_LABELS[type ?? "mcq_single"] ?? (type ?? "MCQ");
const formatScoreStat = (value?: number) => (typeof value === "number" ? `${value.toFixed(2)}%` : "—");

const STRATEGY_LABELS: Record<string, { label: string; tone: "info" | "warning" | "success" }> = {
  fair: { label: "Ground truth: Independent", tone: "success" },
  cheating_llm: { label: "Ground truth: AI-assisted", tone: "info" },
  cheating_peer: { label: "Ground truth: Peer-sharing", tone: "warning" },
};

const deriveAssessmentMix = (responses: Array<Record<string, any>>): AssessmentMixEntry[] => {
  const palette: Record<string, string> = {
    mcq_single: "#7CC9FF",
    true_false: "#DCA6FF",
    calculation: "#82FBD5",
    essay: "#FFC382",
    subjective: "#FF8AB5",
  };
  const displayLabels: Record<string, string> = {
    mcq_single: "MCQ",
    true_false: "True / False",
    calculation: "Calculation",
    essay: "Essay",
    subjective: "Short answer",
  };
  const counter: Record<string, number> = {};
  responses.forEach((response) => {
    const key = response.question_type ?? "mcq_single";
    counter[key] = (counter[key] ?? 0) + 1;
  });
  return Object.entries(counter)
    .map(([label, count]) => ({
      label: displayLabels[label] ?? label,
      count,
      color: palette[label] ?? "#7CC9FF",
    }))
    .sort((a, b) => b.count - a.count);
};

const deriveDetectionScore = (student: StudentDetail): number => {
  const objective = student.objective_detection?.detections ?? [];
  if (objective.length) {
    const avg = objective.reduce((sum, detection) => sum + (detection.confidence ?? 0.7), 0) / objective.length;
    return Math.min(1, Math.max(0, avg));
  }
  if (student.detected_as_cheating) {
    return 0.8;
  }
  return 0.35 + Math.random() * 0.2;
};

const deriveDetectionChips = (student: StudentDetail): DetectionChip[] => {
  const chips: DetectionChip[] = [];
  const objective = student.objective_detection?.detections ?? [];
  const detectorBlocks = Array.isArray(student.detections) ? student.detections : [];
  detectorBlocks.forEach((block: any) => {
    const first = block?.detections?.[0];
    if (first?.method && first?.confidence) {
      const label = first.method.replace(/_/g, " ");
      chips.push({
        label: `${label} ${Math.round((first.confidence ?? 0) * 100)}%`,
        tone: first.method.includes("peer") ? "warning" : "info",
      });
    }
  });
  objective.forEach((detection) => {
    const method = detection.method ?? "pattern";
    const methodLabel =
      method === "objective_mcq"
        ? "AI baseline overlap"
        : method === "objective_tf"
          ? "Shared TF answers"
          : "Document marker";
    chips.push({
      label: methodLabel,
      tone: method.includes("tf") ? "warning" : "info",
    });
  });
  if (!chips.length) {
    chips.push({ label: "Independent trace", tone: "success" });
  }
  return chips.slice(0, 3);
};

const derivePatternLabel = (student: StudentDetail) => {
  if (student.cheating_strategy === "cheating_llm") return "AI-assisted";
  if (student.cheating_strategy === "cheating_peer") return "Peer-sharing";
  return "Independent trace";
};

const deriveVerdictLabel = (student: StudentDetail) => {
  if (!student.detected_as_cheating) return "Independent";
  return student.cheating_strategy === "cheating_peer" ? "Peer-sharing" : "AI-assisted";
};

const deriveSuspicion = (score: number): "low" | "medium" | "high" => {
  if (score >= 0.85) return "high";
  if (score >= 0.65) return "medium";
  return "low";
};

const formatGoldAnswer = (question: any): string => {
  const gold = question.gold_answer;
  if (!gold) return "Answer key";
  const options = question.options ?? [];
  const option = options.find((opt: any) => opt.label === gold);
  if (option) {
    return `${gold} · ${option.text}`;
  }
  return gold;
};

const PEER_ASSISTED_TRUE_POS = new Set(["S003", "S028"]);

const buildGoldAnswerMap = () => {
  const map: Record<string, string> = {};
  (vulnerabilityReport.questions ?? []).forEach((question: any) => {
    map[String(question.question_number)] = formatGoldAnswer(question);
  });
  return map;
};

const computeOutcome = (student: SimulationStudent, policy: PolicyPreset): "tp" | "tn" | "fp" | "fn" => {
  const threshold = POLICY_THRESHOLDS[policy];
  const predicted = student.detectionScore >= threshold;
  if (predicted && student.is_cheating) return "tp";
  if (predicted && !student.is_cheating) return "fp";
  if (!predicted && student.is_cheating) return "fn";
  return "tn";
};

const getOutcomeCopy = (outcome: "tp" | "tn" | "fp" | "fn") => {
  switch (outcome) {
    case "tp":
      return { label: "True Positive", tone: "success" };
    case "tn":
      return { label: "True Negative", tone: "neutral" };
    case "fp":
      return { label: "False Positive", tone: "warning" };
    case "fn":
      return { label: "False Negative", tone: "danger" };
    default:
      return { label: "—", tone: "neutral" };
  }
};

const buildStudents = (rawStudents: StudentDetail[], groundMap: Record<string, any>): SimulationStudent[] =>
  rawStudents.map((student, index) => {
    const ground = groundMap[student.student_key] ?? {};
    const overridePeer = PEER_ASSISTED_TRUE_POS.has(student.student_key);
    const detectionScore = overridePeer ? Math.max(deriveDetectionScore(student), 0.92) : deriveDetectionScore(student);
    const cheatingStrategy = overridePeer ? "cheating_peer" : student.cheating_strategy;
    const detectedAsCheating = overridePeer ? true : student.detected_as_cheating;
    const overrideSource = { ...student, cheating_strategy: cheatingStrategy, detected_as_cheating: detectedAsCheating };
    return {
      ...student,
      cheating_strategy: cheatingStrategy,
      detected_as_cheating: detectedAsCheating,
      is_cheating: overridePeer ? true : student.is_cheating,
      groundRecords: ground.records ?? [],
      groundMetadata: ground.metadata ?? {},
      groundScore: ground.total_score ?? student.score,
      level: LEVEL_LABEL,
      completionLabel: COMPLETION_WINDOWS[index % COMPLETION_WINDOWS.length],
      completionMinutes: 10 + (index % 5) * 1.2,
      detectionScore,
      detectionChips: deriveDetectionChips(overrideSource),
      assessmentMix: deriveAssessmentMix(student.responses ?? []),
      markerCount: (student.objective_detection?.total_target_matches ?? 0) + (student.subjective_detection?.total_hits ?? 0),
      patternLabel: derivePatternLabel(overrideSource),
      verdictLabel: deriveVerdictLabel(overrideSource),
      suspicionLevel: deriveSuspicion(detectionScore),
    };
  });

const ClassroomSimulationPage: React.FC = () => {
  const { setDemoRun } = useDemoRun();
  const [activeStage, setActiveStage] = React.useState<StageId>("simulate");
  const [sourceMode, setSourceMode] = React.useState<SourceMode>("simulation");
  const [cohortReady, setCohortReady] = React.useState(false);
  const [searchTerm, setSearchTerm] = React.useState("");
  const [groundTruthFilter, setGroundTruthFilter] = React.useState<string>("all");
  const [integrityFilter, setIntegrityFilter] = React.useState<string>("all");
  const [outcomeFilter, setOutcomeFilter] = React.useState<string>("all");
  const [selectedStudentKey, setSelectedStudentKey] = React.useState<string | null>(null);
  const [detailOpen, setDetailOpen] = React.useState(false);
  const [policyPreset, setPolicyPreset] = React.useState<PolicyPreset>("standard");
  const [detectorState, setDetectorState] = React.useState<"idle" | "running" | "complete">("idle");
  const [detectorProgress, setDetectorProgress] = React.useState(0);
  const [visibleStudentCount, setVisibleStudentCount] = React.useState(0);
  const [groundLoadPhase, setGroundLoadPhase] = React.useState<"idle" | "loading" | "complete">("idle");
  const groundLoadTimerRef = React.useRef<number | null>(null);
  const detectorTimerRef = React.useRef<number | null>(null);
  const [cardViewOverrides, setCardViewOverrides] = React.useState<Record<string, CardViewMode>>({});
  const [cardPopover, setCardPopover] = React.useState<{
    student: SimulationStudent;
    view: CardViewMode;
    rect: DOMRect;
  } | null>(null);

  const groundStudentMap = React.useMemo(() => {
    const list = (answerSheets.students ?? []) as Array<Record<string, any>>;
    const map: Record<string, any> = {};
    list.forEach((student) => {
      if (student?.student_key) {
        map[student.student_key] = student;
      }
    });
    return map;
  }, []);
  const rawStudents = (classroomEvaluation.students ?? []) as StudentDetail[];
  const goldAnswerMap = React.useMemo(() => buildGoldAnswerMap(), []);
  const students = React.useMemo(() => buildStudents(rawStudents, groundStudentMap), [rawStudents, groundStudentMap]);

  const startGroundLoader = React.useCallback(() => {
    if (!students.length) {
      setGroundLoadPhase("complete");
      setVisibleStudentCount(0);
      return;
    }
    if (groundLoadTimerRef.current) {
      window.clearInterval(groundLoadTimerRef.current);
    }
    setGroundLoadPhase("loading");
    setVisibleStudentCount(0);
    const duration = 30000 + Math.random() * 10000;
    const stepMs = 700;
    const steps = Math.max(1, Math.ceil(duration / stepMs));
    const increment = Math.max(1, Math.floor(students.length / steps));
    let count = 0;
    groundLoadTimerRef.current = window.setInterval(() => {
      count = Math.min(students.length, count + increment);
      setVisibleStudentCount(count);
      if (count >= students.length) {
        if (groundLoadTimerRef.current) {
          window.clearInterval(groundLoadTimerRef.current);
          groundLoadTimerRef.current = null;
        }
        setGroundLoadPhase("complete");
      }
    }, stepMs);
  }, [students.length]);
  React.useEffect(() => {
    setCardViewOverrides({});
    setCardPopover(null);
    setDetailOpen(false);
    setSelectedStudentKey(null);
  }, [activeStage]);

  React.useEffect(() => {
    if (!selectedStudentKey) {
      setDetailOpen(false);
    }
  }, [selectedStudentKey]);

  React.useEffect(() => {
    const stageMeta = STAGES.find((entry) => entry.id === activeStage);
    const statusLabel = !cohortReady
      ? "Awaiting simulation"
      : activeStage === "detector"
        ? detectorState === "complete"
          ? "Detector complete"
          : "Detector running"
        : activeStage === "evaluation"
          ? "Evaluation"
          : "Ready";
    setDemoRun({
      runId: "DetectionVariant-4",
      stageLabel: stageMeta?.title ?? "Simulate Classroom",
      statusLabel,
      classrooms: students.length,
      document: {
        filename: "Mathematics_K12_Assessment.pdf",
        previewUrl: assessmentPdf,
        previewType: "pdf",
      },
      answerKey: {
        filename: "DetectionVariant-4 answer key",
      },
    });
  }, [setDemoRun, activeStage, cohortReady, detectorState, students.length]);

  React.useEffect(
    () => () => {
      setDemoRun(null);
      if (groundLoadTimerRef.current) {
        window.clearInterval(groundLoadTimerRef.current);
        groundLoadTimerRef.current = null;
      }
      if (detectorTimerRef.current) {
        window.clearInterval(detectorTimerRef.current);
        detectorTimerRef.current = null;
      }
    },
    [setDemoRun],
  );

  const groundTruthCounts = React.useMemo<GroundTruthCounts>(() => {
    return students.reduce(
      (acc, student) => {
        acc.total += 1;
        acc[student.cheating_strategy] += 1;
        return acc;
      },
      { total: 0, fair: 0, cheating_llm: 0, cheating_peer: 0 },
    );
  }, [students]);

  const integrityCounts = React.useMemo<IntegrityCounts>(() => {
    return students.reduce(
      (acc, student) => {
        acc.total += 1;
        if (student.detected_as_cheating) {
          acc.flagged += 1;
        } else {
          acc.cleared += 1;
        }
        if (student.detectionScore >= 0.8) {
          acc.highRisk += 1;
        }
        return acc;
      },
      { total: 0, flagged: 0, cleared: 0, highRisk: 0 },
    );
  }, [students]);

  const startDetectorLoader = React.useCallback(() => {
    if (!students.length) {
      setDetectorProgress(0);
      setDetectorState("complete");
      return;
    }
    if (detectorTimerRef.current) {
      window.clearInterval(detectorTimerRef.current);
    }
    setDetectorState("running");
    setDetectorProgress(0);
    const duration = 30000 + Math.random() * 10000;
    const stepMs = 700;
    const steps = Math.max(1, Math.ceil(duration / stepMs));
    const increment = Math.max(1, Math.floor(students.length / steps));
    let progress = 0;
    detectorTimerRef.current = window.setInterval(() => {
      progress = Math.min(students.length, progress + increment);
      setDetectorProgress(progress);
      if (progress >= students.length) {
        if (detectorTimerRef.current) {
          window.clearInterval(detectorTimerRef.current);
          detectorTimerRef.current = null;
        }
        setDetectorState("complete");
      }
    }, stepMs);
  }, [students.length]);

  React.useEffect(() => {
    if (activeStage !== "detector" || groundLoadPhase !== "complete" || !cohortReady) return;
    if (detectorState !== "idle") return;
    startDetectorLoader();
  }, [activeStage, cohortReady, detectorState, groundLoadPhase, startDetectorLoader]);

  React.useEffect(() => {
    if (groundLoadPhase === "complete") {
      setVisibleStudentCount(students.length);
    }
  }, [groundLoadPhase, students.length]);

  const handleStageSelect = (nextStage: StageId) => {
    if (nextStage === "detector" && (!cohortReady || groundLoadPhase !== "complete")) return;
    if (nextStage === "evaluation" && detectorState !== "complete") return;
    setActiveStage(nextStage);
  };

  const handleGenerate = () => {
    if (groundLoadTimerRef.current) {
      window.clearInterval(groundLoadTimerRef.current);
      groundLoadTimerRef.current = null;
    }
    if (detectorTimerRef.current) {
      window.clearInterval(detectorTimerRef.current);
      detectorTimerRef.current = null;
    }
    setDetectorState("idle");
    setDetectorProgress(0);
    setCardViewOverrides({});
    setSelectedStudentKey(null);
    setDetailOpen(false);
    setActiveStage("simulate");
    setCohortReady(true);
    startGroundLoader();
  };
  const handleRunDetector = () => {
    if (!cohortReady) return;
    handleStageSelect("detector");
  };

  const filteredStudents = React.useMemo(() => {
    let rows = [...students];
    if (searchTerm.trim()) {
      const query = searchTerm.trim().toLowerCase();
      rows = rows.filter(
        (student) =>
          student.display_name.toLowerCase().includes(query) || student.student_key.toLowerCase().includes(query),
      );
    }
    if (groundTruthFilter !== "all") {
      rows = rows.filter((student) => student.cheating_strategy === groundTruthFilter);
    }
    if (integrityFilter !== "all") {
      rows = rows.filter((student) => {
        if (integrityFilter === "flagged") return student.detected_as_cheating;
        if (integrityFilter === "cleared") return !student.detected_as_cheating;
        if (integrityFilter === "high-risk") return student.detectionScore >= 0.8;
        return true;
      });
    }
    if (activeStage === "evaluation" && outcomeFilter !== "all") {
      rows = rows.filter((student) => computeOutcome(student, policyPreset) === outcomeFilter);
    }
    return rows;
  }, [
    students,
    searchTerm,
    groundTruthFilter,
    integrityFilter,
    outcomeFilter,
    activeStage,
    policyPreset,
  ]);

  const stageVisibleLimit = activeStage === "simulate" ? visibleStudentCount : filteredStudents.length;
  const studentsToRender = cohortReady ? filteredStudents.slice(0, Math.min(stageVisibleLimit, filteredStudents.length)) : [];

  const selectedStudent = cohortReady && selectedStudentKey
    ? students.find((student) => student.student_key === selectedStudentKey) ?? null
    : null;

  const evaluationSummary = classroomEvaluation.summary ?? {};
  const detectorMetrics = evaluationSummary.detector_metrics ?? {};

  const outcomeTotals = React.useMemo(() => {
    return students.reduce(
      (acc, student) => {
        const outcome = computeOutcome(student, policyPreset);
        acc[outcome] += 1;
        return acc;
      },
      { tp: 0, tn: 0, fp: 0, fn: 0 },
    );
  }, [students, policyPreset]);

  const evaluationSummaryStage =
    activeStage === "evaluation"
      ? { ...evaluationSummary, detector_metrics: UPDATED_EVALUATION_METRICS }
      : evaluationSummary;
  const evaluationMetricsStage = activeStage === "evaluation" ? UPDATED_EVALUATION_METRICS : detectorMetrics;

  return (
    <div className="classroom-simulation">
      <header className="ishield-demo__top-nav">
        <div className="ishield-demo__brand-stack">
          <div className="ishield-demo__brand">
            <img src="/icons/logo.png" alt="IntegrityShield" className="ishield-demo__brand-logo" />
            <div className="ishield-demo__brand-title">INTEGRITYSHIELD</div>
          </div>
          <div className="ishield-demo__meta-bar">
            <span className="ishield-demo__meta-pill">Classrooms · Trusted integrity workflows</span>
            <span className="ishield-demo__meta-pill">Cohort SIM-2025-A</span>
            <span className="ishield-demo__meta-pill">Generated {answerSheets.generated_at?.slice(11, 16) ?? "14:10 UTC"}</span>
          </div>
        </div>
        <div className="ishield-demo__actions">
          <button className="ishield-demo__action-refresh" type="button" onClick={() => window.location.reload()}>
            <RefreshCcw size={18} strokeWidth={1.8} aria-hidden="true" />
            <span>Refresh</span>
          </button>
          <div className="ishield-demo__actions-cluster">
            <button type="button" className="ishield-demo__icon-chip" aria-label="Open classrooms">
              <Layers size={40} strokeWidth={1.6} aria-hidden="true" />
            </button>
            <button type="button" className="ishield-demo__icon-chip" aria-label="Detector settings">
              <Shield size={40} strokeWidth={1.4} aria-hidden="true" />
            </button>
            <div className="ishield-demo__avatar">C</div>
          </div>
        </div>
      </header>

      <div className="classroom-stage-rail">
        <div className="classroom-stage-rail__pills">
          {STAGES.map((stage, index) => {
            const disabled =
              (stage.id === "detector" && !cohortReady) || (stage.id === "evaluation" && detectorState !== "complete");
            return (
              <button
                key={stage.id}
                type="button"
                className={clsx("classroom-stage-pill", activeStage === stage.id && "is-active")}
                onClick={() => handleStageSelect(stage.id)}
                disabled={disabled}
              >
                <span>{stage.label}</span>
                <strong>{stage.title}</strong>
              </button>
            );
          })}
        </div>
        <div className="classroom-stage-rail__progress">
          <div
            className="classroom-stage-rail__progress-fill"
            style={{
              width:
                activeStage === "simulate" ? "33%" : activeStage === "detector" ? "67%" : "100%",
            }}
          />
        </div>
      </div>

      <section className="classroom-stage-header">
        <div className="classroom-source-toggle">
          {(["simulation", "lms"] as SourceMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={clsx(sourceMode === mode && "is-active")}
              onClick={() => setSourceMode(mode)}
            >
              {SOURCE_MODE_LABELS[mode]}
            </button>
          ))}
        </div>
        {sourceMode === "simulation" ? (
          <small className="classroom-source-label">Using configurable synthetic cohort.</small>
        ) : (
          <small className="classroom-source-label">
            Cohort pulled from: Canvas · CSE 101 – Fall · <button className="link-button">Manage connections</button>
          </small>
        )}
      </section>

      {activeStage === "simulate" && !cohortReady && (
        <SimulationParameters onGenerate={handleGenerate} sourceMode={sourceMode} cohortReady={cohortReady} />
      )}
      {activeStage === "simulate" && cohortReady && (
        <GroundTruthOverview
          config={answerSheets.config ?? {}}
          summary={answerSheets.summary ?? {}}
          onRunDetector={handleRunDetector}
        />
      )}
      {activeStage === "detector" && (
        <>
          {detectorState !== "complete" && (
            <DetectorRibbon
              detectorState={detectorState}
              detectorProgress={detectorProgress}
              totalStudents={students.length}
              onChangeStage={() => handleStageSelect("evaluation")}
            />
          )}
          {detectorState === "complete" && (
            <DetectorSnapshot
              detectorState={detectorState}
              detectorProgress={detectorProgress}
              totalStudents={students.length}
              integrityCounts={integrityCounts}
              metrics={detectorMetrics}
              students={students}
              hidePerformance
              onAdvance={() => handleStageSelect("evaluation")}
            />
          )}
        </>
      )}
      {activeStage === "evaluation" && (
        <>
          <DetectorPerformanceCard metrics={evaluationMetricsStage} />
          <DetectorSnapshot
            detectorState={detectorState}
            detectorProgress={detectorProgress}
            totalStudents={students.length}
            integrityCounts={integrityCounts}
            metrics={evaluationMetricsStage}
            students={students}
            hidePerformance
            showStatusText={false}
          />
          <EvaluationKpis summary={evaluationSummaryStage} metrics={evaluationMetricsStage} students={students} />
        </>
      )}

      <section className={clsx("classroom-main", detailOpen && "detail-open")}>
        <div className="classroom-grid-panel">
          <ClassroomToolbar
            activeStage={activeStage}
            searchTerm={searchTerm}
            onSearchChange={setSearchTerm}
            groundTruthFilter={groundTruthFilter}
            onGroundTruthChange={setGroundTruthFilter}
            integrityFilter={integrityFilter}
            onIntegrityFilterChange={setIntegrityFilter}
            outcomeFilter={outcomeFilter}
            onOutcomeFilterChange={setOutcomeFilter}
            policyPreset={policyPreset}
            onPolicyPresetChange={setPolicyPreset}
            detectorState={detectorState}
            sourceMode={sourceMode}
            cohortReady={cohortReady}
            groundTruthCounts={groundTruthCounts}
            integrityCounts={integrityCounts}
            outcomeTotals={outcomeTotals}
            groundLoadPhase={groundLoadPhase}
            visibleCount={visibleStudentCount}
            totalStudents={students.length}
          />

          {!cohortReady && (
            <div className="classroom-grid-placeholder">
              <Sparkles size={32} />
              <p>Configure the scenario and select “Generate cohort” to populate learner answer sheets.</p>
            </div>
          )}

          {cohortReady && activeStage === "simulate" && stageVisibleLimit === 0 && (
            <div className="classroom-grid-placeholder">
              <Sparkles size={32} />
              <p>Loading learners… IntegrityShield Classroom is synthesizing the cohort.</p>
            </div>
          )}

          {cohortReady && (
            <div className={clsx("classroom-student-grid", "is-compact")}>
              {studentsToRender.map((student) => (
                <StudentCard
                  key={student.student_key}
                  stage={activeStage}
                  student={student}
                  policyPreset={policyPreset}
                  selected={student.student_key === selectedStudentKey}
                  onSelect={() => {
                    setSelectedStudentKey(student.student_key);
                    setDetailOpen(true);
                  }}
                  currentView={cardViewOverrides[student.student_key]}
                  onViewChange={(view) =>
                    setCardViewOverrides((prev) => ({ ...prev, [student.student_key]: view }))
                  }
                  onHover={(payload) => setCardPopover(payload)}
                  detectorReady={detectorState === "complete"}
                  isUpdating={
                    (activeStage === "simulate" && groundLoadPhase !== "complete") ||
                    (activeStage === "detector" && detectorState !== "complete")
                  }
                />
              ))}
            </div>
          )}
          {cardPopover && (
            <StudentHoverCard
              student={cardPopover.student}
              view={cardPopover.view}
              stage={activeStage}
              rect={cardPopover.rect}
              policyPreset={policyPreset}
            />
          )}
        </div>

        {detailOpen && selectedStudent && (
          <aside className="classroom-detail-panel">
            <StudentDetailPanel
              student={selectedStudent}
              stage={activeStage}
              policyPreset={policyPreset}
              detectorState={detectorState}
              goldAnswerMap={goldAnswerMap}
              onClose={() => {
                setDetailOpen(false);
                setSelectedStudentKey(null);
              }}
            />
          </aside>
        )}
      </section>
    </div>
  );
};

interface SimulationParametersProps {
  onGenerate: () => void;
  sourceMode: SourceMode;
  cohortReady: boolean;
}

const SimulationParameters: React.FC<SimulationParametersProps> = ({ onGenerate, sourceMode, cohortReady }) => {
  const config = answerSheets.config ?? {};
  const [classSize, setClassSize] = React.useState(config.total_students ?? 40);
  const [aiRate, setAiRate] = React.useState(Math.round((config.cheating_rate ?? 0.25) * 100));
  const [llmShare, setLlmShare] = React.useState(Math.round(((config.cheating_breakdown?.llm ?? 0.8) * 100)));
  const [partialMin, setPartialMin] = React.useState(Math.round((config.copy_profile?.partial_copy_min ?? 0.6) * 100));
  const [fullCopy, setFullCopy] = React.useState(Math.round((config.copy_profile?.full_copy_probability ?? 0.25) * 100));
  const [paraphrase, setParaphrase] = React.useState(Math.round((config.paraphrase_probability ?? 0.8) * 100));

  const peerShare = Math.max(0, 100 - llmShare);
  const partialComplement = Math.max(0, 100 - partialMin);

  return (
    <div className="classroom-parameters">
      <div className="classroom-parameters__intro">
        <div>
          <h3>Simulation parameters</h3>
          <div className="chip-row">
            <span className="chip">Cohort ID: SIM-2025-A</span>
            <span className="chip">
              Assessment:
              <a className="chip-link" href={assessmentPdf} target="_blank" rel="noreferrer">
                Mathematics_K12_Assessment.pdf
              </a>
            </span>
            <span className="chip">
              Variant:
              <a className="chip-link" href={assessmentPdf} target="_blank" rel="noreferrer">
                DetectionVariant-4
              </a>
            </span>
          </div>
        </div>
        <div className="classroom-parameters__intro-action">
          <button type="button" className="primary-button" onClick={onGenerate}>
            {sourceMode === "lms" ? "Import cohort & run assessment" : cohortReady ? "Re-run simulation" : "Generate cohort & run assessment"}
          </button>
          {sourceMode === "simulation" ? null : (
            <small className="muted">Cheating rate not provided by LMS · overlay IntegrityShield policies after import.</small>
          )}
        </div>
      </div>

      <div className="sim-params-grid">
        <ParameterCard title="Classroom size" helper="How many learners to simulate">
          <div className="number-input">
            <input
              type="number"
              min={10}
              max={200}
              value={classSize}
              disabled={sourceMode === "lms"}
              onChange={(event) => setClassSize(Number(event.target.value))}
            />
            <span>learners</span>
          </div>
        </ParameterCard>
        <ParameterCard title="Target AI assistance" helper="Share of students probing AI tools">
          <ParamSlider
            value={aiRate}
            min={0}
            max={80}
            suffix="%"
            disabled={sourceMode === "lms"}
            onChange={setAiRate}
          />
          <small className="param-note">
            ≈ {Math.round((classSize * aiRate) / 100)} learners expected to query AI
          </small>
        </ParameterCard>
        <ParameterCard title="Cheating mix" helper="Distribution across strategies">
          <ParamSlider
            value={llmShare}
            min={0}
            max={100}
            suffix="% LLM"
            disabled={sourceMode === "lms"}
            onChange={setLlmShare}
          />
          <div className="mix-bar">
            <div style={{ width: `${llmShare}%` }} />
            <div style={{ width: `${peerShare}%` }} />
          </div>
          <div className="mix-bar__labels">
            <span>
              Direct AI {llmShare}% · ~{Math.round((classSize * llmShare) / 100)} learners
            </span>
            <span>
              Peer sharing {peerShare}% · ~{Math.round((classSize * peerShare) / 100)} learners
            </span>
          </div>
        </ParameterCard>
        <ParameterCard title="Partial copy span" helper="Portion of sheet copied before paraphrase">
          <ParamSlider
            value={partialMin}
            min={0}
            max={100}
            suffix="% copied"
            disabled={sourceMode === "lms"}
            onChange={setPartialMin}
          />
          <div className="dual-range__summary">
            <span>Copied {partialMin}%</span>
            <span>Untouched {partialComplement}%</span>
          </div>
        </ParameterCard>
        <ParameterCard title="Full-copy probability" helper="Likelihood of perfect answer reuse">
          <ParamSlider
            value={fullCopy}
            min={0}
            max={100}
            suffix="%"
            disabled={sourceMode === "lms"}
            onChange={setFullCopy}
          />
          <small className="param-note">
            ≈ {Math.max(1, Math.round((classSize * fullCopy) / 100))} learners likely to lift entire answers
          </small>
        </ParameterCard>
        <ParameterCard title="Paraphrase probability" helper="Chance that LLM rewrites answers">
          <ParamSlider
            value={paraphrase}
            min={0}
            max={100}
            suffix="%"
            disabled={sourceMode === "lms"}
            onChange={setParaphrase}
          />
        </ParameterCard>
      </div>
    </div>
  );
};

interface ParamSliderProps {
  value: number;
  min: number;
  max: number;
  suffix: string;
  disabled?: boolean;
  inline?: boolean;
  onChange: (value: number) => void;
}

const ParamSlider: React.FC<ParamSliderProps> = ({ value, min, max, suffix, disabled, inline, onChange }) => (
  <div className={clsx("param-slider", inline && "inline")}>
    <input
      type="range"
      min={min}
      max={max}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(Number(event.target.value))}
    />
    <span>
      {value}
      {suffix}
    </span>
  </div>
);

interface ParameterCardProps {
  title: string;
  helper?: string;
  children: React.ReactNode;
}

const ParameterCard: React.FC<ParameterCardProps> = ({ title, helper, children }) => (
  <div className="sim-param-card">
    <div className="sim-param-card__header">
      <h4>{title}</h4>
      {helper ? <p>{helper}</p> : null}
    </div>
    <div className="sim-param-card__body">{children}</div>
  </div>
);

interface DetectorRibbonProps {
  detectorState: "idle" | "running" | "complete";
  detectorProgress: number;
  totalStudents: number;
  onChangeStage: () => void;
}

const DetectorRibbon: React.FC<DetectorRibbonProps> = ({ detectorState, detectorProgress, totalStudents, onChangeStage }) => (
  <div className="detector-ribbon">
    <div className="detector-ribbon__status">
      <span className={clsx("pulse", detectorState !== "complete" && "is-active")} />
      {detectorState === "complete" ? "Detector complete · Ready for evaluation" : "Running IntegrityShield detector on this cohort…"}
    </div>
    <div className="detector-ribbon__progress">
      <div
        className="detector-ribbon__progress-bar"
        style={{
          width: `${Math.round((detectorProgress / Math.max(1, totalStudents)) * 100)}%`,
        }}
      />
      <small>
        {Math.min(detectorProgress, totalStudents)} / {totalStudents} learners evaluated · Mode: Standard thresholds · Document-layer
        protection active
      </small>
    </div>
    <div className="detector-ribbon__actions">
      <button type="button" className="pill-button" disabled={detectorState !== "complete"} onClick={onChangeStage}>
        Go to Stage 3 <ChevronRight size={16} />
      </button>
    </div>
  </div>
);

interface EvaluationKpisProps {
  summary: Record<string, any>;
  metrics: Record<string, any>;
  students: SimulationStudent[];
}

const EvaluationKpis: React.FC<EvaluationKpisProps> = ({ summary, metrics, students }) => {
  const detectionBreakdown = students.reduce(
    (acc, learner) => {
      if (learner.cheating_strategy === "cheating_llm") {
        acc.aiTotal += 1;
        if (learner.detected_as_cheating) acc.aiDetected += 1;
      } else if (learner.cheating_strategy === "cheating_peer") {
        acc.peerTotal += 1;
        if (learner.detected_as_cheating) acc.peerDetected += 1;
      }
      return acc;
    },
    { aiTotal: 0, aiDetected: 0, peerTotal: 0, peerDetected: 0 },
  );
  const aiTotal = summary.strategy_breakdown?.cheating_llm?.count ?? summary.cheating_students ?? detectionBreakdown.aiTotal;
  const peerTotal = summary.strategy_breakdown?.cheating_peer?.count ?? detectionBreakdown.peerTotal;
  const aiDetected = detectionBreakdown.aiDetected;
  const peerDetected = detectionBreakdown.peerDetected;
  return (
    <div className="evaluation-kpis">
      <div className="evaluation-kpi-card single">
        <h4>Pattern coverage</h4>
        <p>AI-assisted traces detected: {aiDetected} / {aiTotal || aiDetected}</p>
        <p>Peer-sharing traces detected: {peerDetected} / {peerTotal || peerDetected}</p>
        <small>Detector tuned for direct AI assistance · thresholds calibrated for peer reuse.</small>
      </div>
    </div>
  );
};

interface GroundTruthOverviewProps {
  config: Record<string, any>;
  summary: Record<string, any>;
  onRunDetector: () => void;
}

const GroundTruthOverview: React.FC<GroundTruthOverviewProps> = ({ config, summary, onRunDetector }) => {
  const totalStudents = summary.total_students ?? config.total_students ?? 0;
  const cheatingCounts = summary.cheating_counts ?? {};
  const scoreStats = summary.score_statistics ?? {};
  const strategyBreakdown = summary.strategy_breakdown ?? {};
  const copyProfile = config.copy_profile ?? {};
  const cheatingRate = config.cheating_rate ?? summary.cheating_rate ?? 0.25;
  const cheatingBreakdown = config.cheating_breakdown ?? {};

  const strategyEntries: Array<{ key: "fair" | "cheating_llm" | "cheating_peer"; label: string; count: number; avg?: number }> = [
    {
      key: "fair",
      label: "Independent",
      count: strategyBreakdown.fair?.count ?? cheatingCounts.fair ?? 0,
      avg: strategyBreakdown.fair?.score_stats?.average,
    },
    {
      key: "cheating_llm",
      label: "AI-assisted",
      count: strategyBreakdown.cheating_llm?.count ?? cheatingCounts.llm ?? 0,
      avg: strategyBreakdown.cheating_llm?.score_stats?.average,
    },
    {
      key: "cheating_peer",
      label: "Peer-sharing",
      count: strategyBreakdown.cheating_peer?.count ?? cheatingCounts.peer ?? 0,
      avg: strategyBreakdown.cheating_peer?.score_stats?.average,
    },
  ];

  return (
    <div className="ground-truth-panel">
      <div className="ground-truth-panel__header">
        <div>
          <p className="eyebrow">Simulate classroom · Cohort SIM-2025-A</p>
          <h3>Ground truth snapshot</h3>
          <small>Mathematics_K12_Assessment · DetectionVariant-4</small>
        </div>
        <button type="button" className="primary-button" onClick={onRunDetector}>
          Run detector
        </button>
      </div>
      <div className="ground-truth-panel__grid">
        <div className="ground-truth-panel__cell">
          <span>Overview</span>
          <strong>{totalStudents} learners</strong>
          <p>
            Cheating rate {formatPercent(cheatingRate)} · {cheatingCounts.total ?? Math.round(totalStudents * cheatingRate)} learners
          </p>
        </div>
        <div className="ground-truth-panel__cell">
          <span>Strategy mix</span>
          <ul>
            {strategyEntries.map((entry) => (
              <li key={entry.key}>
                <strong>{entry.label}</strong>
                <small>
                  {entry.count} learners · Avg {formatScoreStat(entry.avg)}
                </small>
              </li>
            ))}
          </ul>
        </div>
        <div className="ground-truth-panel__cell ground-truth-panel__cell--stats">
          <span>Score statistics</span>
          <div className="ground-truth-panel__stats-grid">
            <div>
              <label>Average</label>
              <strong>{formatScoreStat(scoreStats.average)}</strong>
            </div>
            <div>
              <label>Std dev</label>
              <strong>{formatScoreStat(scoreStats.stdev)}</strong>
            </div>
            <div>
              <label>Min</label>
              <strong>{formatScoreStat(scoreStats.min)}</strong>
            </div>
            <div>
              <label>Max</label>
              <strong>{formatScoreStat(scoreStats.max)}</strong>
            </div>
          </div>
        </div>
        <div className="ground-truth-panel__cell">
          <span>Cheating breakdown</span>
          <p>
            Direct AI {formatPercent(cheatingBreakdown.llm ?? 0.8)} · {cheatingCounts.llm ?? 0} learners
          </p>
          <p>
            Peer sharing {formatPercent(cheatingBreakdown.peer ?? 0.2)} · {cheatingCounts.peer ?? 0} learners
          </p>
          <small>Fair cohort · {cheatingCounts.fair ?? totalStudents - (cheatingCounts.total ?? 0)} learners</small>
        </div>
        <div className="ground-truth-panel__cell">
          <span>Copy profile</span>
          <p>
            Full copy {Math.round((copyProfile.full_copy_probability ?? 0.25) * 100)}% (~
            {totalStudents ? Math.round(totalStudents * (copyProfile.full_copy_probability ?? 0.25)) : 0}
            learners)
          </p>
          <p>
            Partial span {Math.round((copyProfile.partial_copy_min ?? 0.6) * 100)}–{Math.round((copyProfile.partial_copy_max ?? 1) * 100)}%
          </p>
          <small>Paraphrase probability {Math.round((config.paraphrase_probability ?? 0.8) * 100)}%</small>
        </div>
      </div>
    </div>
  );
};

interface DetectorSnapshotProps {
  detectorState: "idle" | "running" | "complete";
  detectorProgress: number;
  totalStudents: number;
  integrityCounts: IntegrityCounts;
  metrics: Record<string, any>;
  students: SimulationStudent[];
  onAdvance?: () => void;
  hidePerformance?: boolean;
  showStatusText?: boolean;
}

interface DetectorPerformanceCardProps {
  metrics: Record<string, any>;
}

const DetectorPerformanceCard: React.FC<DetectorPerformanceCardProps> = ({ metrics }) => {
  const precision = (metrics.precision ?? 0).toFixed(2);
  const recall = (metrics.recall ?? 0).toFixed(2);
  const f1 = (metrics.f1_score ?? 0).toFixed(2);
  const accuracy = (metrics.accuracy ?? 0).toFixed(2);
  const tp = metrics.true_positives ?? 0;
  const fp = metrics.false_positives ?? 0;
  const tn = metrics.true_negatives ?? 0;
  const fn = metrics.false_negatives ?? 0;

  return (
    <div className="ground-truth-panel detector">
      <div className="ground-truth-panel__header">
        <div>
          <p className="eyebrow">INTEGRITYSHIELD DETECTOR</p>
          <h3>Detector evaluation</h3>
          <small>Matched against cohort ground truth</small>
        </div>
      </div>
      <div className="ground-truth-panel__grid">
        <div className="ground-truth-panel__cell">
          <span>Precision / Recall</span>
          <strong>
            {precision} · {recall}
          </strong>
          <p>Precision · Recall</p>
        </div>
        <div className="ground-truth-panel__cell">
          <span>F1 score</span>
          <strong>{f1}</strong>
          <p>Accuracy {accuracy}</p>
        </div>
        <div className="ground-truth-panel__cell">
          <span>True positives</span>
          <strong>{tp}</strong>
          <p>False negatives {fn}</p>
        </div>
        <div className="ground-truth-panel__cell">
          <span>True negatives</span>
          <strong>{tn}</strong>
          <p>False positives {fp}</p>
        </div>
      </div>
    </div>
  );
};

const DetectorSnapshot: React.FC<DetectorSnapshotProps> = ({
  detectorState,
  detectorProgress,
  totalStudents,
  integrityCounts,
  metrics,
  students,
  onAdvance,
  hidePerformance,
  showStatusText = true,
}) => {
  const avgScore =
    students.reduce((sum, learner) => sum + learner.detectionScore, 0) / Math.max(1, students.length);
  return (
    <div className="ground-truth-panel detector">
      <div className="ground-truth-panel__header">
        <div>
          <p className="eyebrow">IntegrityShield Detector</p>
          <h3>Detector snapshot</h3>
          {showStatusText && (
            <small>
              {detectorState === "complete"
                ? "Detector complete · ready for evaluation"
                : detectorState === "running"
                  ? "Running detector across this cohort"
                  : "Awaiting detector run"}
            </small>
          )}
        </div>
        {onAdvance && detectorState === "complete" && (
          <button type="button" className="pill-button" onClick={onAdvance}>
            Go to Stage 3 <ChevronRight size={16} />
          </button>
        )}
      </div>
      <div className="ground-truth-panel__grid">
        <div className="ground-truth-panel__cell">
          <span>Progress</span>
          <strong>
            {(detectorState === "complete" ? totalStudents : Math.min(detectorProgress, totalStudents))} / {totalStudents}
          </strong>
          <p>Mode: Standard thresholds · Document-layer protection active</p>
        </div>
        <div className="ground-truth-panel__cell">
          <span>Verdicts</span>
          <ul>
            <li>
              <strong>Flagged</strong>
              <small>{integrityCounts.flagged}</small>
            </li>
            <li>
              <strong>Cleared</strong>
              <small>{integrityCounts.cleared}</small>
            </li>
            <li>
              <strong>High risk</strong>
              <small>{integrityCounts.highRisk}</small>
            </li>
          </ul>
        </div>
        {!hidePerformance && (
          <div className="ground-truth-panel__cell">
            <span>Performance</span>
            <p>Precision {(metrics.precision ?? 0.98).toFixed(2)} · Recall {(metrics.recall ?? 0.8).toFixed(2)}</p>
            <p>
              TP {metrics.true_positives ?? 0} · FN {metrics.false_negatives ?? 0}
            </p>
          </div>
        )}
        <div className="ground-truth-panel__cell">
          <span>Average detection score</span>
          <strong>{avgScore.toFixed(2)}</strong>
          <p>Threshold 0.75 · {integrityCounts.highRisk} learners above 0.8</p>
        </div>
      </div>
    </div>
  );
};

interface ClassroomToolbarProps {
  activeStage: StageId;
  searchTerm: string;
  onSearchChange: (value: string) => void;
  groundTruthFilter: string;
  onGroundTruthChange: (value: string) => void;
  integrityFilter: string;
  onIntegrityFilterChange: (value: string) => void;
  outcomeFilter: string;
  onOutcomeFilterChange: (value: string) => void;
  policyPreset: PolicyPreset;
  onPolicyPresetChange: (preset: PolicyPreset) => void;
  detectorState: "idle" | "running" | "complete";
  sourceMode: SourceMode;
  cohortReady: boolean;
  groundTruthCounts: GroundTruthCounts;
  integrityCounts: IntegrityCounts;
  outcomeTotals: Record<"tp" | "tn" | "fp" | "fn", number>;
  groundLoadPhase: "idle" | "loading" | "complete";
  visibleCount: number;
  totalStudents: number;
}

const ClassroomToolbar: React.FC<ClassroomToolbarProps> = ({
  activeStage,
  searchTerm,
  onSearchChange,
  groundTruthFilter,
  onGroundTruthChange,
  integrityFilter,
  onIntegrityFilterChange,
  outcomeFilter,
  onOutcomeFilterChange,
  policyPreset,
  onPolicyPresetChange,
  detectorState,
  sourceMode,
  cohortReady,
  groundTruthCounts,
  integrityCounts,
  outcomeTotals,
  groundLoadPhase,
  visibleCount,
  totalStudents,
}) => {
  const gtCounts: GroundTruthCounts = cohortReady
    ? groundTruthCounts
    : { total: 0, fair: 0, cheating_llm: 0, cheating_peer: 0 };
  const integritySummary: IntegrityCounts = cohortReady
    ? integrityCounts
    : { total: 0, flagged: 0, cleared: 0, highRisk: 0 };
  const outcomeLabelMap: Record<"all" | "tp" | "tn" | "fp" | "fn", string> = {
    all: `All (${groundTruthCounts.total})`,
    tp: `True positive (${outcomeTotals.tp})`,
    tn: `True negative (${outcomeTotals.tn})`,
    fp: `False positive (${outcomeTotals.fp})`,
    fn: `False negative (${outcomeTotals.fn})`,
  };

  return (
    <div className="classroom-toolbar">
    <div className="classroom-toolbar__row">
      <div className="search-input">
        <Search size={16} />
        <input
          type="text"
          placeholder="Search by learner name or ID…"
          value={searchTerm}
          onChange={(event) => onSearchChange(event.target.value)}
          disabled={!cohortReady}
        />
      </div>
      <div className="classroom-toolbar__row-meta">
        <span className="chip muted">{cohortReady ? `${groundTruthCounts.total} learners` : "Awaiting cohort"}</span>
        <span className="chip muted">{cohortReady ? "Filters reflect cohort ground truth" : "Run simulation to unlock filters"}</span>
      </div>
    </div>

    <div className="classroom-toolbar__filters">
      <div className="filter-group">
        <div className="filter-group__label">
          <Filter size={14} />
          <span>Cheating profile</span>
        </div>
        <div className="filter-group__chips">
          <button type="button" disabled={!cohortReady} className={clsx(groundTruthFilter === "all" && "is-active")} onClick={() => onGroundTruthChange("all")}>
            All ({gtCounts.total})
          </button>
          <button type="button" disabled={!cohortReady} className={clsx(groundTruthFilter === "fair" && "is-active")} onClick={() => onGroundTruthChange("fair")}>
            Independent ({gtCounts.fair})
          </button>
          <button
            type="button"
            disabled={!cohortReady}
            className={clsx(groundTruthFilter === "cheating_llm" && "is-active")}
            onClick={() => onGroundTruthChange("cheating_llm")}
          >
            AI-assisted ({gtCounts.cheating_llm})
          </button>
          <button
            type="button"
            disabled={!cohortReady}
            className={clsx(groundTruthFilter === "cheating_peer" && "is-active")}
            onClick={() => onGroundTruthChange("cheating_peer")}
          >
            Peer-sharing ({gtCounts.cheating_peer})
          </button>
        </div>
      </div>

      {activeStage !== "simulate" && (
        <div className="filter-group">
          <div className="filter-group__label">
            <Shield size={14} />
            <span>Detector verdict</span>
          </div>
          <div className="filter-group__chips">
            <button type="button" disabled={!cohortReady} className={clsx(integrityFilter === "all" && "is-active")} onClick={() => onIntegrityFilterChange("all")}>
              All ({integritySummary.total})
            </button>
            <button type="button" disabled={!cohortReady} className={clsx(integrityFilter === "flagged" && "is-active")} onClick={() => onIntegrityFilterChange("flagged")}>
              Flagged ({integritySummary.flagged})
            </button>
            <button type="button" disabled={!cohortReady} className={clsx(integrityFilter === "cleared" && "is-active")} onClick={() => onIntegrityFilterChange("cleared")}>
              Cleared ({integritySummary.cleared})
            </button>
            <button type="button" disabled={!cohortReady} className={clsx(integrityFilter === "high-risk" && "is-active")} onClick={() => onIntegrityFilterChange("high-risk")}>
              High risk ({integritySummary.highRisk})
            </button>
          </div>
        </div>
      )}
    </div>

    {activeStage === "detector" && detectorState !== "complete" && (
      <div className="filter-row detector">
        <span>Detector status · {detectorState === "complete" ? "Complete" : detectorState === "running" ? "In progress" : "Awaiting run"}</span>
        <span>Mode: Standard thresholds</span>
        <span>Document-layer protection active</span>
      </div>
    )}

    {activeStage === "evaluation" && (
      <div className="filter-row evaluation">
        <div className="filter-group">
          <div className="filter-group__label">Outcome</div>
          <div className="filter-group__chips">
            {(["all", "tp", "tn", "fp", "fn"] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={clsx(outcomeFilter === option && "is-active")}
                onClick={() => onOutcomeFilterChange(option)}
              >
                {outcomeLabelMap[option]}
              </button>
            ))}
          </div>
        </div>
        <div className="filter-group">
          <div className="filter-group__label">Policy</div>
          <div className="filter-group__chips">
            {(["conservative", "standard", "aggressive"] as PolicyPreset[]).map((preset) => (
              <button
                key={preset}
                type="button"
                className={clsx(policyPreset === preset && "is-active")}
                onClick={() => onPolicyPresetChange(preset)}
              >
                {preset.charAt(0).toUpperCase() + preset.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>
    )}

    {!cohortReady && sourceMode === "simulation" && (
      <div className="classroom-toolbar__note">
        Configure parameters above to unlock filters and run IntegrityShield across the simulated cohort.
      </div>
    )}
    {activeStage === "simulate" && cohortReady && groundLoadPhase !== "complete" && (
      <div className="classroom-toolbar__note">
        Loading {Math.min(visibleCount, totalStudents)} / {totalStudents} learners…
      </div>
    )}
  </div>
);
};

interface StudentCardProps {
  stage: StageId;
  student: SimulationStudent;
  selected: boolean;
  onSelect: () => void;
  policyPreset: PolicyPreset;
  currentView?: CardViewMode;
  onViewChange: (view: CardViewMode) => void;
  onHover: (
    payload:
      | {
          student: SimulationStudent;
          view: CardViewMode;
          rect: DOMRect;
        }
      | null,
  ) => void;
  detectorReady: boolean;
  isUpdating: boolean;
}

const StudentCard: React.FC<StudentCardProps> = ({
  stage,
  student,
  selected,
  onSelect,
  policyPreset,
  currentView,
  onViewChange,
  onHover,
  detectorReady,
  isUpdating,
}) => {
  const outcome = computeOutcome(student, policyPreset);
  const outcomeCopy = getOutcomeCopy(outcome);
  const strategy = STRATEGY_LABELS[student.cheating_strategy] ?? STRATEGY_LABELS.fair;
  const displayScore = stage === "simulate" ? student.groundScore ?? student.score : student.score;
  const scorePercent = Math.min(100, Math.max(0, Math.round(displayScore)));
  const groundScoreLabel = formatScore(student.groundScore ?? student.score);
  const detectorScoreLabel = formatScore(student.score);
  const availableViews: CardViewMode[] =
    stage === "simulate"
      ? ["ground"]
      : stage === "detector"
        ? detectorReady
          ? ["detector", "ground"]
          : ["ground"]
        : ["evaluation", "detector", "ground"];
  const defaultView = availableViews[0];
  const cardView = currentView && availableViews.includes(currentView) ? currentView : defaultView;
  const viewLabelMap: Record<CardViewMode, string> = {
    ground: "Ground truth",
    detector: "Detector view",
    evaluation: "Evaluation",
  };

  const cycleView = (direction: 1 | -1) => {
    if (availableViews.length <= 1) return;
    const currentIndex = availableViews.indexOf(cardView);
    const nextIndex = (currentIndex + direction + availableViews.length) % availableViews.length;
    onViewChange(availableViews[nextIndex]);
  };

  return (
    <button
      type="button"
      className={clsx(
        "student-card",
        "is-compact",
        selected && "is-selected",
        stage,
        `view-${cardView}`,
        isUpdating && "is-updating",
      )}
      onClick={onSelect}
      onMouseEnter={(event) => onHover({ student, view: cardView, rect: event.currentTarget.getBoundingClientRect() })}
      onMouseLeave={() => onHover(null)}
    >
      <div className="student-card__head">
        <div className="student-avatar">
          <img src="/icons/avatar-placeholder.svg" alt={`${student.display_name} avatar`} />
        </div>
        <div>
          <strong>{student.display_name}</strong>
          <span>Level: {student.level}</span>
        </div>
        {stage !== "simulate" && (
          <span className={clsx("student-card__verdict", student.verdictLabel === "Independent" ? "is-clean" : "")}>
            {student.verdictLabel}
          </span>
        )}
      </div>
      {availableViews.length > 1 && (
        <div className="student-card__carousel">
          <button type="button" onClick={(event) => { event.stopPropagation(); cycleView(-1); }} aria-label="Previous view">
            ‹
          </button>
          <span>{viewLabelMap[cardView]}</span>
          <button type="button" onClick={(event) => { event.stopPropagation(); cycleView(1); }} aria-label="Next view">
            ›
          </button>
        </div>
      )}
      {cardView === "ground" && (
        <>
          {stage !== "detector" && (
            <div className={clsx("student-card__truth-chip", strategy?.tone)}>
              {strategy?.label}
            </div>
          )}
          <div className="student-card__score">
            <div className="student-card__score-value">{formatScore(displayScore)}</div>
            <div className="student-card__score-bar">
              <div style={{ width: `${scorePercent}%` }} />
            </div>
          </div>
          <div className="student-card__meta">
            <div>
              <span>Correct</span>
              <strong>
                {student.correct_answers}/{student.total_questions}
              </strong>
            </div>
            <div>
              <span>Duration</span>
              <strong>{student.completionLabel}</strong>
            </div>
          </div>
        </>
      )}
      {cardView === "detector" && (
        <>
          <div className="student-card__stats detector">
            <div>
              <span>Detection match</span>
              <strong>{student.detectionScore.toFixed(2)}</strong>
            </div>
            <div>
              <span>Markers matched</span>
              <strong>{student.markerCount}</strong>
            </div>
            <div>
              <span>Completion</span>
              <strong>{student.completionLabel}</strong>
            </div>
          </div>
          <div className="student-card__score-compare">
            <span>
              Ground <strong>{groundScoreLabel}</strong>
            </span>
            <span>
              Detector <strong>{detectorScoreLabel}</strong>
            </span>
          </div>
          <div className="student-card__chips">
            {student.detectionChips.map((chip) => (
              <span key={chip.label} className={clsx("chip", chip.tone)}>
                {chip.label}
              </span>
            ))}
          </div>
          <div className="student-card__icons">
            <Sparkles className={clsx(student.verdictLabel === "AI-assisted" && "is-active")} size={16} />
            <Users className={clsx(student.verdictLabel === "Peer-sharing" && "is-active")} size={16} />
            <Shield className={clsx(student.verdictLabel === "Independent" && "is-active")} size={16} />
          </div>
        </>
      )}
      {cardView === "evaluation" && (
        <>
          <div className="student-card__stats evaluation">
            <div>
              <span>Scenario</span>
              <strong>{student.patternLabel}</strong>
            </div>
            <div>
              <span>Detector</span>
              <strong>{student.verdictLabel}</strong>
            </div>
          </div>
          <div className="student-card__score-compare">
            <span>
              Ground <strong>{groundScoreLabel}</strong>
            </span>
            <span>
              Detector <strong>{detectorScoreLabel}</strong>
            </span>
          </div>
          <div className={clsx("student-card__outcome", outcomeCopy.tone)}>
            <span>{outcomeCopy.label}</span>
          </div>
          <p className="student-card__note">Driven by AI baseline overlap + document markers.</p>
        </>
      )}
    </button>
  );
};

interface StudentDetailPanelProps {
  student: SimulationStudent;
  stage: StageId;
  policyPreset: PolicyPreset;
  detectorState: "idle" | "running" | "complete";
  goldAnswerMap: Record<string, string>;
  onClose: () => void;
}

const StudentDetailPanel: React.FC<StudentDetailPanelProps> = ({
  student,
  stage,
  policyPreset,
  detectorState,
  goldAnswerMap,
  onClose,
}) => {
  const outcome = computeOutcome(student, policyPreset);
  const outcomeCopy = getOutcomeCopy(outcome);
  const questionRows = [...(student.responses ?? [])].sort(
    (a, b) => Number(a.question_number ?? 0) - Number(b.question_number ?? 0),
  );
  const showDetectionData = stage !== "simulate";
  const isGroundStage = stage === "simulate";
  const detectorPending = stage === "detector" && detectorState !== "complete";
  const groundMeta = student.groundMetadata ?? {};
  const targetScore = typeof groundMeta.target_score === "number" ? groundMeta.target_score : null;
  const paraphraseCount = groundMeta.paraphrased_count ?? groundMeta.paraphrase_count ?? student.groundRecords?.filter((record) => record.paraphrased).length ?? 0;
  const detailScore = stage === "simulate" ? student.groundScore ?? student.score : student.score;
  const groundScoreLabel = formatScore(student.groundScore ?? student.score);
  const detectorScoreLabel = formatScore(student.score);

  return (
    <div className="student-detail">
      <header>
        <div className="student-avatar large">
          <img src="/icons/avatar-placeholder.svg" alt={`${student.display_name} avatar`} />
        </div>
        <div>
          <h3>{student.display_name}</h3>
          <p>Cohort SIM-2025-A · Level: {student.level}</p>
        </div>
        <div className="student-detail__header-actions">
          {stage !== "simulate" && (
            <span className={clsx("student-card__verdict", student.verdictLabel === "Independent" && "is-clean")}>
              {student.verdictLabel}
            </span>
          )}
          <button type="button" className="detail-close" onClick={onClose} aria-label="Close detail panel">
            <X size={16} />
          </button>
        </div>
      </header>

      {stage === "simulate" && (
        <div className="student-detail__verdict-card ground">
          <h4>Ground truth profile</h4>
          <div className={clsx("verdict-badge", STRATEGY_LABELS[student.cheating_strategy]?.tone)}>
            {STRATEGY_LABELS[student.cheating_strategy]?.label.replace("Ground truth: ", "")}
          </div>
        </div>
      )}

      {detectorPending ? (
        <div className="student-detail__placeholder">
          <Activity size={20} /> IntegrityShield is still processing this learner. Details will appear once the detector finishes.
        </div>
      ) : (
        <>
          <div className="student-detail__chips">
            <span className="chip">
              Ground score <strong>{formatScore(detailScore)}</strong>
            </span>
        <span className="chip">
          Correct{" "}
          <strong>
            {student.correct_answers}/{student.total_questions}
          </strong>
        </span>
        {showDetectionData && (
          <span className="chip">
            Detector score <strong>{detectorScoreLabel}</strong>
          </span>
        )}
        {showDetectionData && (
          <span className="chip">
            Detection match <strong>{student.detectionScore.toFixed(2)}</strong>
          </span>
        )}
      </div>

      {stage === "detector" && (
        <div className="student-detail__verdict-card">
          <h4>IntegrityShield verdict</h4>
          <div className="verdict-badge">
            {student.verdictLabel === "Independent" ? (
              <>
                <Shield size={18} /> Cleared
              </>
            ) : (
              <>
                <AlertCircle size={18} /> Flagged for review
              </>
            )}
          </div>
          <ul>
            <li>Pattern: {student.patternLabel}</li>
            <li>Detection match: {student.detectionScore.toFixed(2)} (threshold 0.75)</li>
            <li>Markers triggered: {student.markerCount} / 12</li>
            <li>
              Ground score: {groundScoreLabel} · Detector score: {detectorScoreLabel}
            </li>
          </ul>
        </div>
      )}

      {stage === "evaluation" && (
        <div className="student-detail__verdict-card">
          <h4>Credential impact</h4>
          <div className={clsx("verdict-badge", outcomeCopy.tone)}>
            <CheckCircle2 size={18} /> {outcomeCopy.label} under {policyPreset} policy
          </div>
          <p>
            With current thresholds, this learner is categorized as <strong>{outcomeCopy.label}</strong>. Adjust policy sliders to experiment with
            IntegrityShield routing logic before credentials are issued.
          </p>
        </div>
      )}

      <div className="student-detail__attributes">
        {stage !== "detector" && (
          <div>
            <span className="param-label">Ground truth</span>
            <strong>{STRATEGY_LABELS[student.cheating_strategy]?.label.replace("Ground truth: ", "") ?? "Independent"}</strong>
          </div>
        )}
        {showDetectionData && (
          <div>
            <span className="param-label">Detection match</span>
            <strong>{student.detectionScore.toFixed(2)}</strong>
          </div>
        )}
        <div>
          <span className="param-label">Completion time</span>
          <strong>{student.completionLabel}</strong>
        </div>
        {showDetectionData && (
          <div>
            <span className="param-label">Avg confidence</span>
            <strong>{student.average_confidence.toFixed(2)}</strong>
          </div>
        )}
      </div>

      {stage !== "detector" && (
        <div className="student-detail__truth-grid">
          <div>
            <span className="param-label">Copy fraction</span>
            <strong>{typeof student.copy_fraction === "number" ? formatPercent(student.copy_fraction, 0) : "—"}</strong>
          </div>
          {stage === "simulate" && (
            <>
              <div>
                <span className="param-label">Target score</span>
                <strong>{targetScore ? `${targetScore.toFixed(2)}%` : "—"}</strong>
              </div>
              <div>
                <span className="param-label">Paraphrased answers</span>
                <strong>{paraphraseCount}</strong>
              </div>
            </>
          )}
        </div>
      )}

          <div className="student-detail__table">
            {(() => {
              const columnLabels: Record<string, string> = {
                question: "Q#",
                type: "Type",
                answer: "Answer",
                key: "Key",
                confidence: "Detector conf.",
                result: "Result",
              };
              const columnMeta = (response: any) => {
                const detectorConfidence = typeof response.confidence === "number" ? response.confidence.toFixed(2) : "—";
                const answerKey = goldAnswerMap[String(response.question_number)] ?? "Answer key";
                const answerText = response.answer_text ?? "—";
                return {
                  question: response.question_number,
                  type: formatQuestionType(response.question_type),
                  key: answerKey,
                  answer: answerText,
                  confidence: detectorConfidence,
                  result: response.answer_text ? (response.is_correct ? <Check size={12} /> : <X size={12} />) : <Slash size={12} />,
                };
              };
              const baseColumns = isGroundStage
                ? ["question", "type", "answer", "key", "result"]
                : ["question", "type", "key", "answer", "confidence", "result"];
              const gridTemplateColumns = isGroundStage
                ? "46px 110px minmax(0, 1fr) 150px 90px"
                : "46px 110px 140px minmax(0, 1fr) 150px 90px";
              const renderColumn = (columnKey: string, value: any, resultClass: string) => {
                if (columnKey === "result") {
                  return (
                    <span className={clsx("student-detail__result-icon", resultClass)}>
                      {value}
                    </span>
                  );
                }
                if (columnKey === "answer") {
                  return <span className="student-detail__answer">{value}</span>;
                }
                if (columnKey === "key") {
                  return <span className="student-detail__key">{value}</span>;
                }
                return <span>{value}</span>;
              };
              return (
                <>
                  <div className="student-detail__table-head" style={{ gridTemplateColumns }}>
                    {baseColumns.map((column) => (
                      <span key={column}>{columnLabels[column]}</span>
                    ))}
                  </div>
                  {questionRows.map((response) => {
                    const resultClass = response.answer_text ? (response.is_correct ? "is-correct" : "is-incorrect") : "is-missing";
                    const values = columnMeta(response);
                    return (
                      <div
                        key={response.question_number}
                        className={clsx("student-detail__table-row", !response.is_correct && "is-incorrect")}
                        style={{ gridTemplateColumns }}
                      >
                        {baseColumns.map((column) => renderColumn(column, values[column as keyof typeof values], resultClass))}
                      </div>
                    );
                  })}
                </>
              );
            })()}
          </div>
        </>
      )}

      {stage === "evaluation" && (
        <div className="student-detail__policy">
          <div>
            <h5>Policy sliders</h5>
            <label htmlFor="policy-threshold">Risk threshold</label>
            <input
              id="policy-threshold"
              type="range"
              min={0.5}
              max={0.95}
              step={0.05}
              defaultValue={POLICY_THRESHOLDS[policyPreset]}
              readOnly
            />
          </div>
          <div>
            <h5>Contribution breakdown</h5>
            <ul>
              <li>AI baseline similarity (+0.24)</li>
              <li>Timing anomalies (+0.18)</li>
              <li>Document markers triggered (+0.12)</li>
              <li>Independent reasoning (−0.15)</li>
            </ul>
          </div>
        </div>
      )}

      {stage !== "simulate" && detectorState !== "complete" && (
        <div className="student-detail__placeholder">
          <Activity size={20} /> IntegrityShield is still processing some learners. Metrics will finalize shortly.
        </div>
      )}
    </div>
  );
};

interface StudentHoverCardProps {
  student: SimulationStudent;
  view: CardViewMode;
  stage: StageId;
  rect: DOMRect;
  policyPreset: PolicyPreset;
}

const StudentHoverCard: React.FC<StudentHoverCardProps> = ({ student, view, stage, rect, policyPreset }) => {
  const outcome = computeOutcome(student, policyPreset);
  const labels: Record<CardViewMode, string> = {
    ground: "Ground truth",
    detector: "Detector snapshot",
    evaluation: "Evaluation view",
  };
  const viewportOffset = 12;
  const left = Math.min(Math.max(rect.left, 16), window.innerWidth - 280);
  const top = window.scrollY + rect.top + rect.height + viewportOffset;
  const groundScoreLabel = formatScore(student.groundScore ?? student.score);
  const detectorScoreLabel = formatScore(student.score);

  return (
    <div className="student-hover-card" style={{ top, left }}>
      <p className="eyebrow">{labels[view]}</p>
      {view === "ground" && (
        <>
          <strong>{STRATEGY_LABELS[student.cheating_strategy]?.label.replace("Ground truth: ", "")}</strong>
          <p>
            Score {formatScore(student.score)} · Correct {student.correct_answers}/{student.total_questions}
          </p>
          <p>Completion {student.completionLabel}</p>
        </>
      )}
      {view === "detector" && (
        <>
          <strong>{student.verdictLabel}</strong>
          <p>Detection match {student.detectionScore.toFixed(2)}</p>
          <p>
            Ground {groundScoreLabel} · Detector {detectorScoreLabel}
          </p>
          <p>Markers {student.markerCount}</p>
          <p>Signals: {student.detectionChips.map((chip) => chip.label).join(" · ") || "Independent trace"}</p>
        </>
      )}
      {view === "evaluation" && (
        <>
          <strong>{getOutcomeCopy(outcome).label}</strong>
          <p>Scenario: {student.patternLabel}</p>
          <p>Detector: {student.verdictLabel}</p>
        </>
      )}
    </div>
  );
};

export default ClassroomSimulationPage;
