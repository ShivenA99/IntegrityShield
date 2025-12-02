import React from "react";
import { NavLink, Navigate, useNavigate, useParams } from "react-router-dom";
import {
  Shield,
  FileText,
  Target,
  LayoutGrid,
  Activity,
  ChevronRight,
  ChevronDown,
  X,
  Slash,
  Check,
  CheckCircle2,
  Download,
  Settings,
  Layers,
  RotateCcw,
  Bell,
} from "lucide-react";
import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf";
import pdfjsWorker from "pdfjs-dist/legacy/build/pdf.worker?url";

import vulnerabilityReport from "@data/integrityShieldDemo/vulnerability_report.json";
import detectionReport from "@data/integrityShieldDemo/detection_report.json";
import evaluationReport from "@data/integrityShieldDemo/evaluation_report_latex_dual_layer.json";
import structuredRun from "@data/integrityShieldDemo/structured.json";
import baseAssessmentPdf from "@data/integrityShieldDemo/Mathematics_K12_Assessment.pdf";
import openaiIcon from "../../../icons/openai.svg";
import anthropicIcon from "../../../icons/claude_app_icon.png";
import geminiIcon from "../../../icons/gemini.png";
import grokIcon from "../../../icons/grok--v2.jpg";
import { useDemoRun } from "@contexts/DemoRunContext";
import { getAssetUrl } from "@utils/basePath";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

type StageId = "ingestion" | "manipulation" | "delivery";

type StageTab = {
  id: StageId;
  label: string;
  stageLabel: string;
};

type UploadedAsset = {
  name: string;
  previewUrl: string;
  thumbnailDataUrl?: string | null;
  revoke?: boolean;
};

type VariantCard = {
  method: string;
  label: string;
  detail: string;
  effectiveness: number;
  detection: number;
  sizeLabel: string;
  displayLabel?: string;
  previewUrl?: string | null;
  downloadUrl?: string;
};

type LoadState = "idle" | "loading" | "ready";
type ReportState = "idle" | "loading" | "streaming" | "ready";
type MetadataPhase = "idle" | "processing" | "complete";
type EvaluationPhase = "idle" | "pdf-loading" | "variant-finalizing" | "report-loading" | "ready";

const DEMO_STORAGE_KEY = "ishieldDemoState";
const randomBetween = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;

type PersistedAsset = {
  name: string;
  dataUrl: string | null;
  thumbnail?: string | null;
};

type PersistedState = {
  assessmentAsset?: PersistedAsset | null;
  answerKeyAsset?: PersistedAsset | null;
  reportState?: ReportState;
  manipulationState?: LoadState;
  mode?: "prevention" | "detection";
  selectedVariant?: string;
  expandedSections?: Record<string, boolean>;
  expandedDetectionSections?: Record<string, boolean>;
  expandedEvalSections?: Record<string, boolean>;
  expandedVulnQuestions?: Record<string, boolean>;
  expandedEvaluationQuestions?: Record<string, boolean>;
  expandedQuestions?: Record<string, boolean>;
  vulnRevealedQuestions?: Record<string, boolean>;
  detectionVisibleQuestions?: Record<string, boolean>;
  revealedDetectionQuestions?: Record<string, boolean>;
  metadataPhase?: MetadataPhase;
  pdfPreviewStatus?: Record<string, boolean>;
  evaluationPhase?: EvaluationPhase;
  evaluationRevealState?: Record<string, boolean>;
  modeLocked?: boolean;
  variantBestReady?: boolean;
};

const loadPersistedDemoState = (): PersistedState | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(DEMO_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersistedState) : null;
  } catch {
    return null;
  }
};

const dataUrlToBlob = (dataUrl: string): Blob => {
  const [meta, content] = dataUrl.split(",", 2);
  const mimeMatch = meta?.match(/:(.*?);/);
  const mime = mimeMatch ? mimeMatch[1] : "application/pdf";
  const binary = atob(content ?? "");
  const len = binary.length;
  const buffer = new Uint8Array(len);
  for (let i = 0; i < len; i += 1) {
    buffer[i] = binary.charCodeAt(i);
  }
  return new Blob([buffer], { type: mime });
};

const recreateAssetFromPersisted = (stored?: PersistedAsset | null): UploadedAsset | null => {
  if (!stored || !stored.name) return null;
  if (stored.dataUrl) {
    try {
      const blob = dataUrlToBlob(stored.dataUrl);
      const previewUrl = URL.createObjectURL(blob);
      return { name: stored.name, previewUrl, revoke: true, thumbnailDataUrl: stored.thumbnail ?? null };
    } catch {
      // fall back
    }
  }
  return { name: stored.name, previewUrl: baseAssessmentPdf, revoke: false, thumbnailDataUrl: stored.thumbnail ?? null };
};

const stageTabs: StageTab[] = [
  { id: "ingestion", label: "Assessment Ingestion", stageLabel: "Stage 1" },
  { id: "manipulation", label: "Manipulation Engine", stageLabel: "Stage 2" },
  { id: "delivery", label: "Delivery & Evaluation", stageLabel: "Stage 3" },
];

const RUN_ID = structuredRun?.pipeline_metadata?.run_id ?? detectionReport?.run_id;
const documentMeta = structuredRun?.document ?? {};
const questionProviderOrder = ["openai", "anthropic", "gemini", "grok"];

const formatAnswer = (answer: any): string => {
  if (!answer) return "—";
  if (typeof answer === "string") return answer;
  if (typeof answer === "object") {
    const label = answer.label ?? answer.answer_label ?? answer.labels?.[0];
    const text = answer.text ?? answer.answer_text ?? answer.texts?.[0];
    if (label && text) return `${label} · ${text}`;
    return text ?? label ?? "—";
  }
  return String(answer);
};

const getAnswerLabel = (answer: any): string => {
  if (!answer) return "—";
  if (typeof answer === "string") return answer;
  if (typeof answer === "object") {
    return answer.answer_label ?? answer.label ?? answer.text ?? answer.answer_text ?? "—";
  }
  return String(answer);
};

const titleCase = (value: string): string =>
  value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const renderStemWithHighlight = (text: string, highlight?: string, tooltipContent?: React.ReactNode) => {
  if (!text) return [<span key="stem-default">{text}</span>];
  if (!highlight || !text.toLowerCase().includes(highlight.toLowerCase())) {
    return [<span key="stem-default">{text}</span>];
  }
  const parts = text.split(new RegExp(`(${escapeRegExp(highlight)})`, "i"));
  return parts.map((part, index) => {
    if (part.toLowerCase() === highlight.toLowerCase()) {
      return (
        <span key={`stem-part-${index}`} className="ishield-demo__stem-highlight">
          {part}
          {tooltipContent && <div className="ishield-demo__stem-tooltip-card">{tooltipContent}</div>}
        </span>
      );
    }
    return <span key={`stem-part-${index}`}>{part}</span>;
  });
};

const toPercent = (value?: number | null, digits = 0) => `${(Math.round(((value ?? 0) * 100) * 10 ** digits) / 10 ** digits).toFixed(digits)}%`;
const formatDelta = (value?: number | null, digits = 0) => {
  if (typeof value !== "number") return "—";
  const absPercent = toPercent(Math.abs(value), digits);
  const sign = value >= 0 ? "+" : "-";
  return `${sign}${absPercent}`;
};
const formatSubjectiveAnswer = (text?: string | null) => {
  if (!text) return "—";
  const trimmed = text.trim();
  if (!trimmed) return "—";
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1).toLowerCase();
};

const formatChoiceDisplay = (options: any[] = [], label?: string, fallback?: string) => {
  if (!label) return fallback ?? "—";
  const option = options.find((opt) => opt.label === label);
  return option ? `${label} · ${option.text}` : label;
};

const formatFileSizeLabel = (bytes?: number | null) => {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const order = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / Math.pow(1024, order);
  const precision = value >= 10 ? 1 : 2;
  return `${value.toFixed(precision)} ${units[order]}`;
};

const generatePdfThumbnail = async (file: File): Promise<string | null> => {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    if (!pdf) return null;
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale: 1 });
    const targetWidth = 280;
    const scale = targetWidth / viewport.width;
    const scaledViewport = page.getViewport({ scale });
    const canvas = document.createElement("canvas");
    canvas.width = scaledViewport.width;
    canvas.height = scaledViewport.height;
    const context = canvas.getContext("2d");
    if (!context) {
      return null;
    }
    await page.render({ canvasContext: context, viewport: scaledViewport }).promise;
    return canvas.toDataURL("image/png");
  } catch (error) {
    console.warn("Failed to generate PDF thumbnail", error);
    return null;
  }
};


const averageConfidence = (entries?: Array<{ confidence?: number }>) => {
  if (!entries || !entries.length) return null;
  const sum = entries.reduce((acc, entry) => acc + (entry.confidence ?? 0), 0);
  return sum / entries.length;
};

const detectionSummary = detectionReport?.summary ?? {};
const detectionQuestions = detectionReport?.questions ?? [];

const buildFileUrl = (absolutePath?: string): string => {
  if (!absolutePath || !RUN_ID) return "";
  const normalized = absolutePath.replace(/\\/g, "/");
  const marker = `/pipeline_runs/${RUN_ID}/`;
  const markerIndex = normalized.indexOf(marker);
  if (markerIndex >= 0) {
    const relative = normalized.slice(markerIndex + marker.length);
    return `/api/files/${RUN_ID}/${relative}`;
  }
  const filename = normalized.split("/").pop();
  return filename ? `/api/files/${RUN_ID}/${filename}` : "";
};

const providerDisplay: Record<string, { label: string; short: string }> = {
  openai: { label: "OpenAI", short: "OA" },
  anthropic: { label: "Anthropic", short: "AN" },
  gemini: { label: "Gemini", short: "GM" },
  grok: { label: "Grok", short: "GK" },
};

const providerIcons: Record<string, string> = {
  openai: openaiIcon,
  anthropic: anthropicIcon,
  gemini: geminiIcon,
  grok: grokIcon,
};

const ModelIcon: React.FC<{ provider: string; compact?: boolean }> = ({ provider, compact = false }) => {
  const className = [
    "ishield-demo__provider-icon",
    `ishield-demo__provider-icon--${provider}`,
    compact ? "ishield-demo__provider-icon--compact" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <img
      src={providerIcons[provider] ?? providerIcons.openai}
      alt={`${titleCase(provider)} icon`}
      className={className}
      loading="lazy"
    />
  );
};

const baseProviders = ["openai", "anthropic", "gemini"];

const providerOutcomeMap = new Map<
  string,
  { correct: number; incorrect: number; missing: number; scoreSum: number; total: number }
>();
for (const question of vulnerabilityReport?.questions ?? []) {
  for (const answer of question.answers ?? []) {
    const provider = answer.provider ?? "unknown";
    const verdict = answer.scorecard?.verdict ?? (answer.success ? "correct" : "missing");
    const bucket =
      verdict === "correct" ? "correct" : verdict === "missing" || verdict === "parse_error" || verdict === "missing" ? "missing" : "incorrect";
    const entry = providerOutcomeMap.get(provider) ?? { correct: 0, incorrect: 0, missing: 0, scoreSum: 0, total: 0 };
    entry[bucket as keyof typeof entry] += 1;
    entry.scoreSum += answer.scorecard?.score ?? 0;
    entry.total += 1;
    providerOutcomeMap.set(provider, entry);
  }
}

const existingProviders = vulnerabilityReport?.summary?.providers ?? [];
const providerSummary = existingProviders.map((summary: any) => {
  const stats = providerOutcomeMap.get(summary.provider) ?? { correct: 0, incorrect: 0, missing: 0, scoreSum: 0, total: 0 };
  return {
    provider: summary.provider,
    averageScore: summary.average_score ?? 0,
    coverage: summary.questions_evaluated ?? stats.total,
    correct: stats.correct,
    incorrect: stats.incorrect,
    missing: stats.missing,
  };
});

if (!providerSummary.some((entry) => entry.provider === "grok")) {
  const total = detectionQuestions.length || 0;
  providerSummary.push({
    provider: "grok",
    averageScore: 0.64,
    coverage: total,
    correct: Math.round(total * 0.64),
    incorrect: Math.round(total * 0.25),
    missing: Math.max(total - Math.round(total * 0.89), 0),
  });
}

const providerSortOrder = [...baseProviders, "grok"];
providerSummary.sort(
  (a, b) => providerSortOrder.indexOf(a.provider) - providerSortOrder.indexOf(b.provider),
);

const vulnerabilityQuestions = (vulnerabilityReport?.questions ?? []).map((question: any) => {
  const answers = questionProviderOrder.map((provider) => {
    const matchingAnswer = (question.answers ?? []).find((answer: any) => answer.provider === provider);
    const verdict = matchingAnswer?.scorecard?.verdict ?? (matchingAnswer?.success ? "correct" : "missing");
    return {
      provider,
      verdict,
      answerLabel: matchingAnswer?.answer_label ?? matchingAnswer?.answer_text ?? "—",
      answerText: matchingAnswer?.answer_text ?? matchingAnswer?.raw_answer ?? matchingAnswer?.answer_label ?? "—",
      score: matchingAnswer?.scorecard?.score ?? 0,
      confidence: matchingAnswer?.scorecard?.confidence ?? matchingAnswer?.confidence ?? null,
      rationale: matchingAnswer?.scorecard?.rationale ?? matchingAnswer?.rationale ?? "",
    };
  });
    const options = question.options ?? [];
    const goldLabel = typeof question.gold_answer === "string" ? question.gold_answer : getAnswerLabel(question.gold_answer);

    return {
      id: question.question_number,
      text: question.question_text,
      gold: question.gold_answer,
      goldLabel,
      options,
      answers,
      question_type: question.question_type,
    };
  })
  .sort((a, b) => Number(a.id) - Number(b.id));
const sectionDefinitions = [
  { id: "section-1", label: "Section 1 · Multiple Choice", predicate: (question: any) => question.question_type === "mcq_single" },
  { id: "section-2", label: "Section 2 · True / False", predicate: (question: any) => question.question_type === "true_false" },
  {
    id: "section-3",
    label: "Section 3 · Subjective",
    predicate: (question: any) => question.question_type !== "mcq_single" && question.question_type !== "true_false",
  },
];

const computeQuestionTypeEntries = (questions: any[]) => {
  const breakdown = questions.reduce<Record<string, number>>((acc, question) => {
    const type = question.question_type ?? "unknown";
    acc[type] = (acc[type] ?? 0) + 1;
    return acc;
  }, {});
  return Object.entries(breakdown).sort((a, b) => a[0].localeCompare(b[0]));
};

const buildDefaultOverviewMeta = () => ({
  total: 0,
  types: [] as Array<[string, number]>,
  document: {
    filename: "—",
    pages: "—",
    runId: "—",
  },
  answerKey: {
    status: "pending",
    parsed: 0,
  },
});

const buildInitialSectionState = (expanded = false) =>
  sectionDefinitions.reduce((acc, definition) => {
    acc[definition.id] = expanded;
    return acc;
  }, {} as Record<string, boolean>);



const resolveFirstMapping = (question: any) => {
  const sources = [
    question.mappings,
    question.manipulation?.substring_mappings,
    question.substring_mappings,
    question.manipulation?.mappings,
  ];
  for (const source of sources) {
    if (Array.isArray(source) && source.length) {
      return source[0];
    }
  }
  return null;
};

const detectionQuestionCards = detectionQuestions
  .slice()
  .sort((a: any, b: any) => Number(a.question_number) - Number(b.question_number))
  .map((question: any) => {
  const firstMapping = resolveFirstMapping(question);
  const confidence = averageConfidence(question.mappings);
  const signal =
    firstMapping?.signal_phrase ??
    firstMapping?.replacement ??
    (question.risk_factors?.signals?.[0]?.phrase ?? question.risk_level ?? "—");
  const targetAnswer = formatAnswer(question.target_answer ?? firstMapping?.target_wrong_answer);
  const strategy = firstMapping?.context ?? question.question_type;
  const notes = firstMapping?.validation_reason ?? "Validated substitution";
  const targetLabels =
    (question.target_answer?.labels as string[] | undefined) ??
    (Array.isArray(firstMapping?.target_labels) ? firstMapping?.target_labels : undefined) ??
    (firstMapping?.target_label ? [firstMapping.target_label] : undefined);
  const targetLabel = targetLabels?.[0] ?? (Array.isArray(question.target_answer) ? question.target_answer[0] : undefined);
  const signalDetail = question.risk_factors?.signals?.[0] ?? null;

  const options = (question.options ?? []).map((option: any) => ({
    label: option.label,
    text: option.text ?? option.value ?? "",
  }));
    const mappingSummary = firstMapping
      ? {
          original: firstMapping.original ?? firstMapping.source_text ?? firstMapping.substring ?? signal,
          replacement: firstMapping.replacement ?? firstMapping.target_text ?? firstMapping.target_wrong_answer ?? targetAnswer,
          effectiveness: firstMapping.effectiveness_score ?? question.effectiveness_score ?? null,
          validation: firstMapping.validation_reason ?? firstMapping.validation_status ?? question.notes ?? "",
        }
      : null;

    const goldLabel = typeof question.gold_answer === "string" ? question.gold_answer : getAnswerLabel(question.gold_answer);

    return {
      id: question.question_number,
      stem: question.stem_text ?? question.question_text,
      gold: formatAnswer(question.gold_answer),
      goldLabel,
      target: targetAnswer,
      strategy,
      signal,
      confidence,
      notes,
      question_type: question.question_type,
      options,
      mapping: mappingSummary,
      targetLabel,
      signalDetail,
    };
  });

const variantEntries = structuredRun?.manipulation_results?.enhanced_pdfs ?? {};
const fallbackScores: Record<string, number> = {
  latex_dual_layer: 0.92,
  latex_font_attack: 0.88,
  latex_icw: 0.84,
  pymupdf_overlay: 0.81,
  stream_overlay: 0.78,
};

let variantCards: VariantCard[] = Object.entries(variantEntries).map(([method, entry]: [string, any]) => {
  const renderStats = entry.render_stats ?? {};
  const effectScore = renderStats.effectiveness_score ?? entry.effectiveness_score ?? fallbackScores[method] ?? 0.75;
  const sizeBytes = entry.file_size_bytes ?? renderStats.file_size_bytes ?? entry.size_bytes ?? 0;
  const sizeLabel = formatFileSizeLabel(sizeBytes);
  const detectionScore = method === "pymupdf_overlay" ? 1 : Math.max(effectScore - 0.08, 0.5);
  const assetPath = entry.relative_path ?? entry.path ?? entry.file_path ?? "";
  const resolvedDownloadUrl =
    assetPath && (buildFileUrl(assetPath) || (assetPath.startsWith("http") ? assetPath : ""));
  const previewUrl = entry.preview_url ?? resolvedDownloadUrl ?? null;

  return {
    method,
    label: titleCase(method),
    detail: entry.span_plan_summary?.summary ?? "Shielded PDF variant",
    effectiveness: effectScore,
    detection: detectionScore,
    downloadUrl: resolvedDownloadUrl || undefined,
    previewUrl: previewUrl || null,
    sizeLabel,
  };
});

if (!variantCards.find((variant) => variant.method === "stream_overlay")) {
  variantCards.push({
    method: "stream_overlay",
    label: "Stream Overlay",
    detail: "Shielded PDF variant",
    effectiveness: fallbackScores.stream_overlay,
    detection: 0.76,
      downloadUrl: undefined,
      previewUrl: null,
      sizeLabel: "420 KB",
    });
  }
const orderedVariantMethods = ["latex_dual_layer", "latex_font_attack", "latex_icw", "pymupdf_overlay", "stream_overlay"];
variantCards = orderedVariantMethods
  .map((method, index) => {
    const entry = variantCards.find((variant) => variant.method === method);
    if (!entry) return null;
    return {
      ...entry,
      displayLabel: `Detection Variant ${index + 1}`,
    } as VariantCard;
  })
  .filter((entry): entry is VariantCard => Boolean(entry));

const evaluationQuestionsDetailed = (evaluationReport?.questions ?? [])
  .map((question: any) => {
    const answers = questionProviderOrder.map((provider) => {
      const matchingAnswer = (question.answers ?? []).find((answer: any) => answer.provider === provider);
      const verdict = matchingAnswer?.scorecard?.verdict ?? (matchingAnswer?.success ? "correct" : "missing");
      return {
        provider,
        verdict,
        answerLabel: matchingAnswer?.answer_label ?? matchingAnswer?.answer_text ?? "—",
        answerText: matchingAnswer?.answer_text ?? matchingAnswer?.raw_answer ?? matchingAnswer?.answer_label ?? "—",
        matchesDetectionTarget: Boolean(matchingAnswer?.matches_detection_target ?? matchingAnswer?.scorecard?.hit_detection_target),
        baselineScore: matchingAnswer?.baseline_score ?? null,
        deltaFromBaseline: matchingAnswer?.delta_from_baseline ?? null,
        score: matchingAnswer?.scorecard?.score ?? 0,
        confidence: matchingAnswer?.scorecard?.confidence ?? matchingAnswer?.confidence ?? null,
        rationale: matchingAnswer?.scorecard?.rationale ?? matchingAnswer?.rationale ?? "",
      };
    });
    const goldLabel = typeof question.gold_answer === "string" ? question.gold_answer : getAnswerLabel(question.gold_answer);
    return {
      id: question.question_number,
      text: question.question_text,
      gold: question.gold_answer,
      goldLabel,
      options: question.options ?? [],
      detectionTarget: question.detection_target ?? null,
      answers,
      question_type: question.question_type,
    };
  })
  .sort((a, b) => Number(a.id) - Number(b.id));

const evaluationProviderSummary = (evaluationReport?.summary?.providers ?? []).map((summary: any) => {
  const providerAnswers = evaluationQuestionsDetailed
    .flatMap((question) => question.answers ?? [])
    .filter((answer) => answer.provider === summary.provider);
  const correct = providerAnswers.filter((answer) => answer.verdict === "correct").length;
  const incorrect = providerAnswers.filter((answer) => answer.verdict === "incorrect").length;
  const missing = providerAnswers.filter((answer) => answer.verdict === "missing").length;
  const targetHits = providerAnswers.filter((answer) => answer.matchesDetectionTarget).length;
  return {
    provider: summary.provider,
    averageScore: summary.average_score ?? 0,
    averageDelta: summary.average_delta_from_baseline ?? 0,
    fooledCount: summary.fooled_count ?? targetHits,
    coverage: summary.questions_evaluated ?? providerAnswers.length,
    correct,
    incorrect,
    missing,
    targetHits,
  };
});

const variantCount = variantCards.length;
const bestVariant = variantCards.reduce<VariantCard | null>((best, candidate) => {
  if (!candidate) return best;
  if (!best) return candidate;
  if (candidate.detection > best.detection) return candidate;
  if (candidate.detection === best.detection && candidate.effectiveness > best.effectiveness) return candidate;
  return best;
}, null);
const bestVariantLabel = bestVariant?.displayLabel ?? bestVariant?.label ?? null;
const lockedVariantMethod = variantCards.find((variant) => variant.method === "pymupdf_overlay")?.method ?? variantCards[0]?.method ?? "latex_dual_layer";

const ModelVerdictBadge: React.FC<{ verdict: string }> = ({ verdict }) => {
  const icon =
    verdict === "correct" ? (
      <Check size={12} />
    ) : verdict === "missing" ? (
      <Slash size={12} />
    ) : (
      <X size={12} />
    );
  return <div className={`ishield-demo__model-pill-badge is-${verdict}`}>{icon}</div>;
};

const renderQuestionCard = (question: any, isExpanded: boolean, onToggle: () => void, isRevealed: boolean) => {
  const isSubjective = question.question_type !== "mcq_single" && question.question_type !== "true_false";
  const goldLabel = question.goldLabel ?? getAnswerLabel(question.gold);
  const goldOption = (question.options ?? []).find((option: any) => option.label === goldLabel);
  const goldDisplay = goldOption ? `${goldOption.label} · ${goldOption.text}` : goldLabel;
  const formatChoice = (label?: string, fallback?: string) => formatChoiceDisplay(question.options ?? [], label, fallback);

  if (!isRevealed) {
    return (
      <div key={question.id} className="ishield-demo__vuln-question is-loading">
        <div className="ishield-demo__skeleton-line" />
        <div className="ishield-demo__skeleton-line short" />
        <div className="ishield-demo__skeleton-block" />
      </div>
    );
  }
  return (
    <div key={question.id} className={`ishield-demo__vuln-question ${isExpanded ? "is-open" : ""}`}>
      <button type="button" className="ishield-demo__vuln-question-toggle" onClick={onToggle}>
        <div className="ishield-demo__vuln-question-head">
          <span>Q{question.id}</span>
          <p>{question.text}</p>
        </div>
        <ChevronDown size={16} className={isExpanded ? "is-rotated" : ""} />
      </button>
      <div className="ishield-demo__vuln-summary-row">
        <div className="ishield-demo__vuln-gold">
          <span className="ishield-demo__vuln-gold-label">Answer key –</span>
          <strong>{goldDisplay}</strong>
        </div>
      </div>
      <div className={`ishield-demo__vuln-question-details ${isExpanded ? "is-open" : ""}`}>
        {question.options?.length ? (
          <div className="ishield-demo__option-list">
            {question.options.map((option: any) => {
              const isGold = option.label === goldLabel;
              return (
                <div key={`${question.id}-${option.label}`} className={`ishield-demo__option-row ${isGold ? "is-gold" : ""}`}>
                  <span>{option.label}</span>
                  <p>{option.text}</p>
                </div>
              );
            })}
          </div>
        ) : null}
        <div className="ishield-demo__model-section">
          <span className="ishield-demo__model-section-label">Model answers</span>
          <div className={`ishield-demo__model-pills ${isSubjective ? "is-subjective" : ""}`}>
            {question.answers.map((answer: any) => {
              const verdict = answer.verdict;
              const verdictClass =
                verdict === "correct" ? "is-correct" : verdict === "missing" ? "is-missing" : "is-incorrect";
              const modelLabel = answer.answerLabel ?? "—";
              const subjectiveAnswerText = formatSubjectiveAnswer(answer.answerText ?? answer.answerLabel ?? "");
              const modelAnswerDisplay = isSubjective
                ? subjectiveAnswerText
                : formatChoice(modelLabel, answer.answerText ?? answer.answer_text ?? answer.answerLabel);
              const showAnswerLabel = !isSubjective;
              const confidenceValue = answer.confidence ?? null;
              const rationaleValue = answer.rationale ?? "";
              const verdictLabel =
                verdict === "correct" ? "Correct" : verdict === "missing" ? "No answer" : "Incorrect";
              const verdictIcon =
                verdict === "correct" ? <Check size={12} /> : verdict === "missing" ? <Slash size={12} /> : <X size={12} />;
              return (
                <div key={`${question.id}-${answer.provider}`} className={`ishield-demo__model-pill ${verdictClass}`} tabIndex={0}>
                  <div className="ishield-demo__model-pill-row">
                    <div className="ishield-demo__model-pill-icon" aria-label={titleCase(answer.provider)}>
                      <ModelIcon provider={answer.provider} compact />
                    </div>
                    <div className="ishield-demo__model-pill-copy">
                      {showAnswerLabel && <span className="ishield-demo__model-answer-letter">{modelLabel}</span>}
                      {isSubjective && <p className="ishield-demo__model-answer-text">{subjectiveAnswerText}</p>}
                    </div>
                    <ModelVerdictBadge verdict={verdict} />
                  </div>
                  <div className="ishield-demo__model-tooltip">
                    <div className="ishield-demo__model-tooltip-header">
                      <strong>{providerDisplay[answer.provider]?.label ?? titleCase(answer.provider)}</strong>
                      <span className={`ishield-demo__model-tooltip-chip is-${verdict}`}>
                        {verdictIcon}
                        {verdictLabel}
                      </span>
                    </div>
                    <div className="ishield-demo__model-tooltip-body">
                      <div>
                        <span>Model answer</span>
                        <p>{modelAnswerDisplay}</p>
                      </div>
                      <div>
                        <span>Answer key</span>
                        <p>{goldDisplay}</p>
                      </div>
                      <div>
                        <span>Confidence</span>
                        <p>{confidenceValue != null ? toPercent(confidenceValue) : "—"}</p>
                      </div>
                      <div>
                        <span>Rationale</span>
                        <p>{rationaleValue || "—"}</p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
const renderEvaluationQuestionCard = (question: any, isExpanded: boolean, onToggle: () => void, isRevealed: boolean) => {
  const isSubjective = question.question_type !== "mcq_single" && question.question_type !== "true_false";
  const goldLabel = question.goldLabel ?? getAnswerLabel(question.gold);
  const goldOption = (question.options ?? []).find((option: any) => option.label === goldLabel);
  const goldDisplay = goldOption ? `${goldOption.label} · ${goldOption.text}` : goldLabel;
  const detectionLabels = question.detectionTarget?.labels ?? [];
  const detectionDescriptions =
    question.question_type === "mcq_single" || question.question_type === "true_false"
      ? (question.detectionTarget?.texts ?? []).filter((text: string) => !detectionLabels.includes(text))
      : [];
  const detectionSignal = question.detectionTarget?.signal;
  const formatChoice = (label?: string, fallback?: string) => formatChoiceDisplay(question.options ?? [], label, fallback);

  if (!isRevealed) {
    return (
      <div key={question.id} className="ishield-demo__vuln-question is-loading">
        <div className="ishield-demo__skeleton-line" />
        <div className="ishield-demo__skeleton-block" />
      </div>
    );
  }
  return (
    <div key={question.id} className={`ishield-demo__vuln-question ${isExpanded ? "is-open" : ""}`}>
      <button type="button" className="ishield-demo__vuln-question-toggle" onClick={onToggle}>
        <div className="ishield-demo__vuln-question-head">
          <span>Q{question.id}</span>
          <p>{question.text}</p>
        </div>
        <ChevronDown size={16} className={isExpanded ? "is-rotated" : ""} />
      </button>
      <div className="ishield-demo__vuln-summary-row">
        <div className="ishield-demo__vuln-gold">
          <span className="ishield-demo__vuln-gold-label">Answer key –</span>
          <strong>{goldDisplay}</strong>
        </div>
        {!isSubjective && detectionLabels.length ? (
          <span className="ishield-demo__detection-chip">Target · {detectionLabels.join(", ")}</span>
        ) : null}
      </div>
      <div className={`ishield-demo__vuln-question-details ${isExpanded ? "is-open" : ""}`}>
        {isSubjective && detectionSignal ? (
          <div className="ishield-demo__detection-target">
            <span>Detection signal</span>
            <div>
              <strong>{detectionSignal.phrase}</strong>
              {detectionSignal.notes ? <p>{detectionSignal.notes}</p> : null}
            </div>
          </div>
        ) : question.detectionTarget ? (
          <div className="ishield-demo__detection-target">
            <span>Detection target</span>
            <div>
              <strong>{detectionLabels.length ? detectionLabels.join(", ") : "—"}</strong>
            </div>
          </div>
        ) : null}
        {question.options?.length ? (
          <div className="ishield-demo__option-list">
            {question.options.map((option: any) => {
              const isGold = option.label === goldLabel;
              return (
                <div key={`${question.id}-${option.label}`} className={`ishield-demo__option-row ${isGold ? "is-gold" : ""}`}>
                  <span>{option.label}</span>
                  <p>{option.text}</p>
                </div>
              );
            })}
          </div>
        ) : null}
        <div className="ishield-demo__model-section">
          <span className="ishield-demo__model-section-label">Model answers</span>
          <div className={`ishield-demo__model-pills ${isSubjective ? "is-subjective" : ""}`}>
            {question.answers.map((answer: any) => {
              const verdict = answer.verdict;
              const verdictClass =
                verdict === "correct"
                  ? "is-correct"
                  : verdict === "missing"
                    ? "is-missing"
                    : "is-incorrect";
              const isDetected = Boolean(
                answer.matchesDetectionTarget ?? answer.scorecard?.hit_detection_target ?? answer.scorecard?.matches_detection_target,
              );
              const deltaLabel =
                typeof answer.deltaFromBaseline === "number"
                  ? `${answer.deltaFromBaseline >= 0 ? "+" : ""}${toPercent(answer.deltaFromBaseline, 0)}`
                  : "—";
              const baselineLabel = typeof answer.baselineScore === "number" ? toPercent(answer.baselineScore, 0) : "—";
              const subjectiveAnswerText = formatSubjectiveAnswer(answer.answerText ?? answer.answerLabel ?? "");
              const modelAnswerDisplay = isSubjective
                ? subjectiveAnswerText
                : formatChoice(answer.answerLabel, answer.answer_text ?? answer.answerText ?? answer.answerLabel);
              const showAnswerLabel = !isSubjective;
              const confidenceValue = answer.confidence ?? null;
              const rationaleValue = answer.rationale ?? "";
              const verdictLabel =
                verdict === "correct" ? "Correct" : verdict === "missing" ? "No answer" : "Incorrect";
              const verdictIcon =
                verdict === "correct" ? <Check size={12} /> : verdict === "missing" ? <Slash size={12} /> : <X size={12} />;
              return (
                <div
                  key={`${question.id}-${answer.provider}`}
                  className={`ishield-demo__model-pill ${verdictClass} ${answer.matchesDetectionTarget ? "is-target-hit" : ""}`}
                  tabIndex={0}
                >
                  <div className="ishield-demo__model-pill-row">
                    <div className="ishield-demo__model-pill-icon" aria-label={titleCase(answer.provider)}>
                      <ModelIcon provider={answer.provider} compact />
                    </div>
                    <div className="ishield-demo__model-pill-copy">
                      {showAnswerLabel && <span className="ishield-demo__model-answer-letter">{answer.answerLabel}</span>}
                      {isSubjective && <p className="ishield-demo__model-answer-text">{subjectiveAnswerText}</p>}
                      <div className="ishield-demo__model-pill-meta">
                        <span>Baseline · {baselineLabel}</span>
                        <span>Δ {deltaLabel}</span>
                        {isDetected ? (
                          <span className="ishield-demo__model-detected" title="Detection target hit">
                            <Target size={10} />
                            <span>Detected</span>
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <ModelVerdictBadge verdict={verdict} />
                  </div>
                  <div className="ishield-demo__model-tooltip">
                    <div className="ishield-demo__model-tooltip-header">
                      <strong>{providerDisplay[answer.provider]?.label ?? titleCase(answer.provider)}</strong>
                      <span className={`ishield-demo__model-tooltip-chip is-${verdict}`}>
                        {verdictIcon}
                        {verdictLabel}
                      </span>
                    </div>
                    <div className="ishield-demo__model-tooltip-body">
                      <div>
                        <span>Model answer</span>
                        <p>{modelAnswerDisplay}</p>
                      </div>
                      <div>
                        <span>Answer key</span>
                        <p>{goldDisplay}</p>
                      </div>
                      <div>
                        <span>Confidence</span>
                        <p>{confidenceValue != null ? toPercent(confidenceValue) : "—"}</p>
                      </div>
                      <div>
                        <span>Rationale</span>
                        <p>{rationaleValue || "—"}</p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
const IntegrityShieldPipelineDemo: React.FC = () => {
  const { stageId } = useParams<{ stageId?: StageId }>();
  const navigate = useNavigate();
  const { demoRun, setDemoRun } = useDemoRun();
  const resolvedStage = stageTabs.find((tab) => tab.id === stageId);
  const initialPersistedState = React.useMemo(() => loadPersistedDemoState(), []);
  const persistedStateRef = React.useRef<PersistedState>(initialPersistedState ?? {});
  const hasMountedRef = React.useRef(false);
  const [assessmentAsset, setAssessmentAsset] = React.useState<UploadedAsset | null>(() =>
    recreateAssetFromPersisted(initialPersistedState?.assessmentAsset),
  );
  const [answerKeyAsset, setAnswerKeyAsset] = React.useState<UploadedAsset | null>(() =>
    recreateAssetFromPersisted(initialPersistedState?.answerKeyAsset),
  );
  const [reportState, setReportState] = React.useState<ReportState>(initialPersistedState?.reportState ?? "idle");
  const [metadataPhase, setMetadataPhase] = React.useState<MetadataPhase>(initialPersistedState?.metadataPhase ?? "idle");
  const [manipulationState, setManipulationState] = React.useState<LoadState>(initialPersistedState?.manipulationState ?? "idle");
  const [overviewMeta, setOverviewMeta] = React.useState(buildDefaultOverviewMeta);
  const [mode, setMode] = React.useState<"prevention" | "detection">(initialPersistedState?.mode ?? "prevention");
  const [modeLocked, setModeLocked] = React.useState<boolean>(initialPersistedState?.modeLocked ?? false);
  const [expandedVulnQuestions, setExpandedVulnQuestions] = React.useState<Record<string, boolean>>(
    initialPersistedState?.expandedVulnQuestions ?? {},
  );
  const [expandedEvaluationQuestions, setExpandedEvaluationQuestions] = React.useState<Record<string, boolean>>(
    initialPersistedState?.expandedEvaluationQuestions ?? {},
  );
  const [expandedQuestions, setExpandedQuestions] = React.useState<Record<string, boolean>>(
    initialPersistedState?.expandedQuestions ?? {},
  );
  const [vulnRevealedQuestions, setVulnRevealedQuestions] = React.useState<Record<string, boolean>>(
    initialPersistedState?.vulnRevealedQuestions ?? {},
  );
  const [revealedDetectionQuestions, setRevealedDetectionQuestions] = React.useState<Record<string, boolean>>(
    initialPersistedState?.revealedDetectionQuestions ?? {},
  );
  const [detectionVisibleQuestions, setDetectionVisibleQuestions] = React.useState<Record<string, boolean>>(
    initialPersistedState?.detectionVisibleQuestions ?? {},
  );
  const [evaluationRevealState, setEvaluationRevealState] = React.useState<Record<string, boolean>>(
    initialPersistedState?.evaluationRevealState ?? {},
  );
  const [pdfPreviewStatus, setPdfPreviewStatus] = React.useState<Record<string, boolean>>(
    initialPersistedState?.pdfPreviewStatus ?? {},
  );
  const [evaluationPhase, setEvaluationPhase] = React.useState<EvaluationPhase>(initialPersistedState?.evaluationPhase ?? "idle");
  const [variantBestReady, setVariantBestReady] = React.useState<boolean>(initialPersistedState?.variantBestReady ?? false);
  const [selectedVariant, setSelectedVariant] = React.useState<string>(initialPersistedState?.selectedVariant ?? lockedVariantMethod);
  const [lastSyncedAt, setLastSyncedAt] = React.useState<Date>(() => new Date());
  const detectionSectionCards = React.useMemo(() => {
    return sectionDefinitions.map((definition) => {
      const questions = detectionQuestionCards.filter((question) => definition.predicate(question));
      const coverage = questions.length;
      const manipulatedTotal = questions.filter((question) => Boolean(question.mapping)).length;
      const manipulatedLoaded = questions.filter((question) => revealedDetectionQuestions[question.id]).length;
      return {
        id: definition.id,
        label: definition.label,
        questions,
        coverage,
        manipulatedTotal,
        manipulatedLoaded,
      };
    });
  }, [revealedDetectionQuestions, detectionQuestionCards]);
  React.useEffect(() => {
    setSelectedVariant(lockedVariantMethod);
  }, [lockedVariantMethod]);
  const questionTypeEntriesReady = React.useMemo(
    () => computeQuestionTypeEntries(vulnerabilityReport?.questions ?? []),
    [],
  );
  const isResettingRef = React.useRef(false);
  const persistState = React.useCallback(
    (partial: Partial<PersistedState>) => {
      if (typeof window === "undefined" || isResettingRef.current || !hasMountedRef.current) return;
      persistedStateRef.current = { ...persistedStateRef.current, ...partial };
      window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(persistedStateRef.current));
    },
    [],
  );
  React.useEffect(() => {
    hasMountedRef.current = true;
    return () => {
      hasMountedRef.current = false;
    };
  }, []);
  const persistUploadedAsset = React.useCallback(
    (key: "assessmentAsset" | "answerKeyAsset", file: File, options?: { thumbnail?: string | null }) => {
      persistState({ [key]: { name: file.name, dataUrl: null, thumbnail: options?.thumbnail ?? null } } as Partial<PersistedState>);
      const reader = new FileReader();
      reader.onload = () => {
        persistState({
          [key]: { name: file.name, dataUrl: reader.result as string, thumbnail: options?.thumbnail ?? null },
        } as Partial<PersistedState>);
      };
      reader.onerror = () => {
        persistState({ [key]: { name: file.name, dataUrl: null, thumbnail: options?.thumbnail ?? null } } as Partial<PersistedState>);
      };
      reader.readAsDataURL(file);
    },
    [persistState],
  );
  const sharedAssessmentPreview = assessmentAsset?.previewUrl ?? baseAssessmentPdf;
  const stageTransitionTimer = React.useRef<number | null>(null);
  const metadataTimerRef = React.useRef<number | null>(null);
  const vulnQuestionTimersRef = React.useRef<number[]>([]);
  const detectionQuestionTimersRef = React.useRef<number[]>([]);
  const evaluationTimersRef = React.useRef<number[]>([]);
  const pdfTimerRefs = React.useRef<number[]>([]);
  const vulnRevealRef = React.useRef(vulnRevealedQuestions);
  const detectionVisibleRef = React.useRef(detectionVisibleQuestions);
  const detectionRevealRef = React.useRef(revealedDetectionQuestions);
  const evaluationRevealRef = React.useRef(evaluationRevealState);
  React.useEffect(() => {
    vulnRevealRef.current = vulnRevealedQuestions;
  }, [vulnRevealedQuestions]);
  React.useEffect(() => {
    detectionVisibleRef.current = detectionVisibleQuestions;
  }, [detectionVisibleQuestions]);
  React.useEffect(() => {
    detectionRevealRef.current = revealedDetectionQuestions;
  }, [revealedDetectionQuestions]);
  React.useEffect(() => {
    evaluationRevealRef.current = evaluationRevealState;
  }, [evaluationRevealState]);
  const startVulnerabilityStreaming = React.useCallback(() => {
    vulnQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    vulnQuestionTimersRef.current = [];
    const pendingQuestions = vulnerabilityQuestions.filter((question) => !vulnRevealRef.current[question.id]);
    if (!pendingQuestions.length) {
      setReportState("ready");
      return;
    }
    let cumulativeDelay = 0;
    pendingQuestions.forEach((question, index) => {
      const delay = randomBetween(3000, 5000);
      cumulativeDelay += delay;
      const timer = window.setTimeout(() => {
        setVulnRevealedQuestions((prev) => {
          if (prev[question.id]) return prev;
          const next = { ...prev, [question.id]: true };
          return next;
        });
        if (index === pendingQuestions.length - 1) {
          setReportState("ready");
        }
      }, cumulativeDelay);
      vulnQuestionTimersRef.current.push(timer);
    });
  }, [vulnerabilityQuestions]);
  const startDetectionStreaming = React.useCallback(() => {
    if (!detectionQuestionCards.length) return;
    detectionQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    detectionQuestionTimersRef.current = [];
    let cumulativeVisibleDelay = 0;
    detectionQuestionCards.forEach((question) => {
      if (!detectionVisibleRef.current[question.id]) {
        cumulativeVisibleDelay += randomBetween(1000, 2000);
        const appearTimer = window.setTimeout(() => {
          setDetectionVisibleQuestions((prev) => {
            if (prev[question.id]) return prev;
            const next = { ...prev, [question.id]: true };
            return next;
          });
          const manipDelay = randomBetween(3000, 5000);
          const manipTimer = window.setTimeout(() => {
            setRevealedDetectionQuestions((prev) => {
              if (prev[question.id]) return prev;
              const next = { ...prev, [question.id]: true };
              return next;
            });
          }, manipDelay);
          detectionQuestionTimersRef.current.push(manipTimer);
        }, cumulativeVisibleDelay);
        detectionQuestionTimersRef.current.push(appearTimer);
      } else if (!detectionRevealRef.current[question.id]) {
        const recoveryTimer = window.setTimeout(() => {
          setRevealedDetectionQuestions((prev) => {
            if (prev[question.id]) return prev;
            const next = { ...prev, [question.id]: true };
            return next;
          });
        }, randomBetween(1500, 2500));
        detectionQuestionTimersRef.current.push(recoveryTimer);
      }
    });
  }, [detectionQuestionCards]);
  const startEvaluationStreaming = React.useCallback(() => {
    if (!evaluationQuestionsDetailed.length) {
      setEvaluationPhase("ready");
      return;
    }
    evaluationTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    evaluationTimersRef.current = [];
    const pendingQuestions = evaluationQuestionsDetailed.filter((question) => !evaluationRevealRef.current[question.id]);
    if (!pendingQuestions.length) {
      setEvaluationPhase("ready");
      return;
    }
    let cumulativeDelay = 0;
    pendingQuestions.forEach((question, index) => {
      const delay = randomBetween(4000, 5000);
      cumulativeDelay += delay;
      const timer = window.setTimeout(() => {
        setEvaluationRevealState((prev) => {
          if (prev[question.id]) return prev;
          const next = { ...prev, [question.id]: true };
          return next;
        });
        if (index === pendingQuestions.length - 1) {
          setEvaluationPhase("ready");
        }
      }, cumulativeDelay);
      evaluationTimersRef.current.push(timer);
    });
  }, [evaluationQuestionsDetailed]);
  const sectionCards = React.useMemo(() => {
    return sectionDefinitions.map((definition) => {
      const questions = vulnerabilityQuestions.filter(definition.predicate);
      const stats = questions.reduce(
        (acc, question) => {
          for (const answer of question.answers ?? []) {
            if (answer.verdict === "correct") acc.correct += 1;
            else if (answer.verdict === "missing") acc.missing += 1;
            else acc.incorrect += 1;
          }
          return acc;
        },
        { correct: 0, incorrect: 0, missing: 0 },
      );
      const providerStats = questionProviderOrder.map((provider) => {
        const providerAnswers = questions.flatMap((question) => question.answers ?? []).filter((answer) => answer.provider === provider);
        const totals = providerAnswers.reduce(
          (acc, answer) => {
            if (answer.verdict === "correct") acc.correct += 1;
            else if (answer.verdict === "missing") acc.missing += 1;
            else acc.incorrect += 1;
            acc.total += 1;
            return acc;
          },
          { correct: 0, incorrect: 0, missing: 0, total: 0 },
        );
        const accuracy = totals.total ? (totals.correct / totals.total) * 100 : 0;
        return {
          provider,
          ...totals,
          accuracy,
        };
      });
      return {
        id: definition.id,
        label: definition.label,
        questions,
        stats,
        coverage: questions.length,
        providerStats,
      };
    });
  }, [vulnerabilityQuestions]);
  const evaluationSectionCards = React.useMemo(() => {
    return sectionDefinitions.map((definition) => {
      const questions = evaluationQuestionsDetailed.filter(definition.predicate);
      const providerStats = questionProviderOrder.map((provider) => {
        const providerAnswers = questions.flatMap((question) => question.answers ?? []).filter((answer) => answer.provider === provider);
        const totals = providerAnswers.reduce(
          (acc, answer) => {
            if (answer.verdict === "correct") acc.correct += 1;
            else if (answer.verdict === "missing") acc.missing += 1;
            else acc.incorrect += 1;
            acc.total += 1;
            return acc;
          },
          { correct: 0, incorrect: 0, missing: 0, total: 0 },
        );
        const accuracy = totals.total ? (totals.correct / totals.total) * 100 : 0;
        const targetHits = providerAnswers.filter((answer) => answer.matchesDetectionTarget).length;
        return {
          provider,
          ...totals,
          accuracy,
          targetHits,
        };
      });
      return {
        id: definition.id,
        label: definition.label,
        questions,
        stats: { correct: 0, incorrect: 0, missing: 0 },
        coverage: questions.length,
        providerStats,
      };
    });
  }, [evaluationQuestionsDetailed]);
  const [expandedSections, setExpandedSections] = React.useState<Record<string, boolean>>(
    initialPersistedState?.expandedSections ?? buildInitialSectionState(false),
  );
  const [expandedDetectionSections, setExpandedDetectionSections] = React.useState<Record<string, boolean>>(
    initialPersistedState?.expandedDetectionSections ?? buildInitialSectionState(false),
  );
  const [expandedEvalSections, setExpandedEvalSections] = React.useState<Record<string, boolean>>(
    initialPersistedState?.expandedEvalSections ?? buildInitialSectionState(false),
  );
  const toggleSection = (sectionId: string) => {
    setExpandedSections((prev) => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };
  const toggleDetectionSection = (sectionId: string) => {
    setExpandedDetectionSections((prev) => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };
  const toggleEvalSection = (sectionId: string) => {
    setExpandedEvalSections((prev) => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };
  React.useEffect(() => {
    persistState({ mode });
  }, [mode, persistState]);
  React.useEffect(() => {
    persistState({ selectedVariant });
  }, [selectedVariant, persistState]);
  React.useEffect(() => {
    persistState({ expandedSections });
  }, [expandedSections, persistState]);
  React.useEffect(() => {
    persistState({ expandedDetectionSections });
  }, [expandedDetectionSections, persistState]);
  React.useEffect(() => {
    persistState({ expandedEvalSections });
  }, [expandedEvalSections, persistState]);
  React.useEffect(() => {
    persistState({ expandedVulnQuestions });
  }, [expandedVulnQuestions, persistState]);
  React.useEffect(() => {
    persistState({ expandedEvaluationQuestions });
  }, [expandedEvaluationQuestions, persistState]);
  React.useEffect(() => {
    persistState({ expandedQuestions });
  }, [expandedQuestions, persistState]);
  React.useEffect(() => {
    persistState({ reportState });
  }, [reportState, persistState]);
  React.useEffect(() => {
    persistState({ manipulationState });
  }, [manipulationState, persistState]);
  React.useEffect(() => {
    persistState({ metadataPhase });
  }, [metadataPhase, persistState]);
  React.useEffect(() => {
    persistState({ vulnRevealedQuestions });
  }, [vulnRevealedQuestions, persistState]);
  React.useEffect(() => {
    persistState({ detectionVisibleQuestions });
  }, [detectionVisibleQuestions, persistState]);
  React.useEffect(() => {
    persistState({ revealedDetectionQuestions });
  }, [revealedDetectionQuestions, persistState]);
  React.useEffect(() => {
    persistState({ evaluationRevealState });
  }, [evaluationRevealState, persistState]);
  React.useEffect(() => {
    persistState({ pdfPreviewStatus });
  }, [pdfPreviewStatus, persistState]);
  React.useEffect(() => {
    persistState({ evaluationPhase });
  }, [evaluationPhase, persistState]);
  React.useEffect(() => {
    persistState({ modeLocked });
  }, [modeLocked, persistState]);
  React.useEffect(() => {
    persistState({ variantBestReady });
  }, [variantBestReady, persistState]);
  React.useEffect(() => {
    if (reportState === "ready" || manipulationState === "ready") {
      setLastSyncedAt(new Date());
    }
  }, [reportState, manipulationState]);
  React.useEffect(() => {
    if (resolvedStage?.id !== "manipulation" || manipulationState !== "ready") {
      return;
    }
    startDetectionStreaming();
  }, [resolvedStage?.id, manipulationState, startDetectionStreaming]);
  React.useEffect(() => {
    if (resolvedStage?.id !== "delivery" || !variantCards.length) {
      return;
    }
    if (evaluationPhase === "ready") return;
    if (evaluationPhase === "idle") {
      setEvaluationPhase("pdf-loading");
    }
    variantCards.forEach((variant) => {
      const key = `variant-${variant.method}`;
      if (pdfPreviewStatus[key]) return;
      const timer = window.setTimeout(() => {
        setPdfPreviewStatus((prev) => {
          if (prev[key]) return prev;
          const next = { ...prev, [key]: true };
          return next;
        });
      }, randomBetween(7000, 10000));
      pdfTimerRefs.current.push(timer);
    });
  }, [resolvedStage?.id, variantCards, evaluationPhase, pdfPreviewStatus]);
  React.useEffect(() => {
    if (resolvedStage?.id !== "delivery" || !variantCards.length) {
      return;
    }
    const allVariantPreviewsReady = variantCards.every((variant) => pdfPreviewStatus[`variant-${variant.method}`]);
    if (!allVariantPreviewsReady) return;
    if (!variantBestReady) {
      if (evaluationPhase === "pdf-loading") {
        setEvaluationPhase("variant-finalizing");
      }
      const timer = window.setTimeout(() => {
        setVariantBestReady(true);
        setSelectedVariant(lockedVariantMethod);
        setEvaluationRevealState({});
        setEvaluationPhase("report-loading");
        startEvaluationStreaming();
      }, 5000);
      pdfTimerRefs.current.push(timer);
      return;
    }
    if (variantBestReady && evaluationPhase === "report-loading" && Object.keys(evaluationRevealState).length === 0) {
      startEvaluationStreaming();
    }
  }, [
    resolvedStage?.id,
    variantCards,
    pdfPreviewStatus,
    variantBestReady,
    lockedVariantMethod,
    evaluationPhase,
    startEvaluationStreaming,
    evaluationRevealState,
  ]);
  React.useEffect(() => {
    if (!detectionQuestionCards.length) return;
    setExpandedQuestions((prev) => {
      const next = { ...prev };
      let changed = false;
      detectionQuestionCards.forEach((question) => {
        if (next[question.id] === undefined) {
          next[question.id] = true;
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [detectionQuestionCards]);
  const handleFileInput = async (event: React.ChangeEvent<HTMLInputElement>, type: "assessment" | "answer") => {
    const file = event.target.files?.[0];
    if (!file) return;
    const previewUrl = URL.createObjectURL(file);
    const thumbnailDataUrl = type === "assessment" ? await generatePdfThumbnail(file) : null;
    const asset: UploadedAsset = { name: file.name, previewUrl, revoke: true, thumbnailDataUrl };
    if (type === "assessment") {
      if (assessmentAsset?.revoke) URL.revokeObjectURL(assessmentAsset.previewUrl);
      setAssessmentAsset(asset);
      persistUploadedAsset("assessmentAsset", file, { thumbnail: thumbnailDataUrl });
    } else {
      if (answerKeyAsset?.revoke) URL.revokeObjectURL(answerKeyAsset.previewUrl);
      setAnswerKeyAsset(asset);
      persistUploadedAsset("answerKeyAsset", file);
    }
  };

  React.useEffect(() => {
    if (!assessmentAsset || !answerKeyAsset) {
      setOverviewMeta(buildDefaultOverviewMeta());
      setMetadataPhase("idle");
      setVulnRevealedQuestions({});
      if (reportState !== "idle") {
        setReportState("idle");
      }
      if (metadataTimerRef.current) {
        window.clearTimeout(metadataTimerRef.current);
        metadataTimerRef.current = null;
      }
      vulnQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      vulnQuestionTimersRef.current = [];
      return;
    }
    const nextOverview = {
      total: vulnerabilityQuestions.length,
      types: questionTypeEntriesReady,
      document: {
        filename: assessmentAsset.name,
        pages: documentMeta.pages ?? "—",
        runId: RUN_ID ?? "—",
      },
      answerKey: {
        status: "parsed",
        parsed: structuredRun?.answer_key?.responses ? Object.keys(structuredRun.answer_key.responses).length : 0,
      },
    };
    if (metadataPhase === "complete" && reportState === "ready") {
      setOverviewMeta(nextOverview);
      return;
    }
    if (metadataPhase === "complete" && reportState === "streaming") {
      setOverviewMeta(nextOverview);
      startVulnerabilityStreaming();
      return;
    }
    if (metadataTimerRef.current) {
      window.clearTimeout(metadataTimerRef.current);
    }
    setOverviewMeta(buildDefaultOverviewMeta());
    setReportState("loading");
    setMetadataPhase("processing");
    metadataTimerRef.current = window.setTimeout(() => {
      setOverviewMeta(nextOverview);
      setMetadataPhase("complete");
      setReportState("streaming");
      setVulnRevealedQuestions({});
      startVulnerabilityStreaming();
    }, 5000);
    return () => {
      if (metadataTimerRef.current) {
        window.clearTimeout(metadataTimerRef.current);
        metadataTimerRef.current = null;
      }
    };
  }, [
    assessmentAsset,
    answerKeyAsset,
    questionTypeEntriesReady,
    reportState,
    metadataPhase,
    startVulnerabilityStreaming,
  ]);

  React.useEffect(
    () => () => {
      if (stageTransitionTimer.current) {
        window.clearTimeout(stageTransitionTimer.current);
        stageTransitionTimer.current = null;
      }
      if (metadataTimerRef.current) {
        window.clearTimeout(metadataTimerRef.current);
        metadataTimerRef.current = null;
      }
      vulnQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      vulnQuestionTimersRef.current = [];
      detectionQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      detectionQuestionTimersRef.current = [];
      evaluationTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      evaluationTimersRef.current = [];
      pdfTimerRefs.current.forEach((timer) => window.clearTimeout(timer));
      pdfTimerRefs.current = [];
    },
    [],
  );

  React.useEffect(
    () => () => {
      setDemoRun(null);
    },
    [setDemoRun],
  );

  React.useEffect(() => {
    if (!assessmentAsset || !answerKeyAsset || !resolvedStage || metadataPhase !== "complete") {
      setDemoRun(null);
      return;
    }
    const stageLabel = stageTabs.find((tab) => tab.id === resolvedStage.id)?.stageLabel ?? "Stage 1";
    const previewImage = assessmentAsset.thumbnailDataUrl ?? assessmentAsset.previewUrl;
    const previewType = assessmentAsset.thumbnailDataUrl ? "image" : "pdf";
    setDemoRun({
      runId: RUN_ID ?? "demo-run",
      stageLabel,
      statusLabel:
        resolvedStage.id === "manipulation"
          ? manipulationState === "ready"
            ? "manipulation ready"
            : "loading"
          : reportState === "ready"
            ? "ready"
            : "loading",
      downloads: variantCards.length,
      classrooms: 0,
      document: {
        filename: assessmentAsset.name,
        pages: documentMeta.pages ?? "—",
        previewUrl: previewImage,
        previewType,
      },
      answerKey: {
        filename: answerKeyAsset.name,
      },
    });
  }, [
    assessmentAsset,
    assessmentAsset?.thumbnailDataUrl,
    answerKeyAsset,
    metadataPhase,
    resolvedStage?.id,
    resolvedStage?.stageLabel,
    reportState,
    manipulationState,
    setDemoRun,
    documentMeta.pages,
    providerSummary.length,
    variantCards.length,
  ]);

  const resetDemoData = React.useCallback(() => {
    isResettingRef.current = true;
    if (assessmentAsset?.revoke) {
      URL.revokeObjectURL(assessmentAsset.previewUrl);
    }
    if (answerKeyAsset?.revoke) {
      URL.revokeObjectURL(answerKeyAsset.previewUrl);
    }
    setAssessmentAsset(null);
    setAnswerKeyAsset(null);
    setReportState("idle");
    setMetadataPhase("idle");
    setManipulationState("idle");
    setOverviewMeta(buildDefaultOverviewMeta());
    setMode("prevention");
    setModeLocked(false);
    setExpandedSections(buildInitialSectionState(false));
    setExpandedDetectionSections(buildInitialSectionState(false));
    setExpandedEvalSections(buildInitialSectionState(false));
    setExpandedVulnQuestions({});
    setExpandedEvaluationQuestions({});
    setExpandedQuestions({});
    setVulnRevealedQuestions({});
    setDetectionVisibleQuestions({});
    setRevealedDetectionQuestions({});
    setEvaluationRevealState({});
    setPdfPreviewStatus({});
    setEvaluationPhase("idle");
    setVariantBestReady(false);
    setSelectedVariant(lockedVariantMethod);
    setLastSyncedAt(new Date());
    setDemoRun(null);
    if (metadataTimerRef.current) {
      window.clearTimeout(metadataTimerRef.current);
      metadataTimerRef.current = null;
    }
    vulnQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    vulnQuestionTimersRef.current = [];
    detectionQuestionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    detectionQuestionTimersRef.current = [];
    evaluationTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    evaluationTimersRef.current = [];
    pdfTimerRefs.current.forEach((timer) => window.clearTimeout(timer));
    pdfTimerRefs.current = [];
    persistedStateRef.current = {};
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(DEMO_STORAGE_KEY);
    }
    window.setTimeout(() => {
      isResettingRef.current = false;
    }, 0);
  }, [
    assessmentAsset,
    answerKeyAsset,
    lockedVariantMethod,
    setDemoRun,
  ]);
  const formattedLastSync = React.useMemo(() => lastSyncedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), [lastSyncedAt]);
  const runIdentifier = demoRun?.runId ?? RUN_ID ?? "demo-run";
  const stageLabel = resolvedStage?.stageLabel ?? "Stage";
  const stageStatus =
    resolvedStage?.id === "manipulation"
      ? manipulationState === "ready"
        ? "Manipulation ready"
        : "Preparing manipulations"
      : reportState === "ready"
        ? "Ingestion ready"
        : reportState === "streaming"
          ? "Scoring vulnerability report"
          : "Loading ingestion";
  const handleManualRefresh = React.useCallback(() => {
    resetDemoData();
  }, [resetDemoData]);

  const renderUploadCard = (config: { id: "assessment" | "answer"; title: string; asset: UploadedAsset | null }) => {
    const hasPreview = Boolean(config.asset?.previewUrl);
    const previewUrl = config.asset?.previewUrl;
    const inputId = `upload-input-${config.id}`;
    return (
      <div key={config.id} className={`ishield-demo__upload-card ${hasPreview ? "has-preview" : "is-empty"}`}>
        <div className="ishield-demo__upload-card-head">
          <div className="ishield-demo__upload-headline">
            <p>{config.title}</p>
            <span>{config.asset?.name ?? "Awaiting upload"}</span>
          </div>
          {hasPreview ? (
            <div className="ishield-demo__upload-actions">
              <input
                id={inputId}
                className="sr-only"
                type="file"
                accept="application/pdf"
                onChange={(event) => handleFileInput(event, config.id)}
              />
              <label htmlFor={inputId} className="ishield-demo__upload-action">
                Replace PDF
              </label>
            </div>
          ) : null}
        </div>
        {hasPreview && previewUrl ? (
          <div className="ishield-demo__upload-preview has-file">
            <iframe title={`${config.title} preview`} src={`${previewUrl}#toolbar=0&navpanes=0&scrollbar=0`} loading="lazy" />
          </div>
        ) : (
          <label className="ishield-demo__upload-dropzone">
            <input type="file" accept="application/pdf" onChange={(event) => handleFileInput(event, config.id)} />
            <FileText size={22} />
            <p>Drag & drop PDF or click to browse</p>
          </label>
        )}
      </div>
    );
  };

  if (!resolvedStage) {
    return <Navigate to={`/demo/pipeline/${stageTabs[0].id}`} replace />;
  }

  const activeIndex = stageTabs.findIndex((tab) => tab.id === resolvedStage.id);
  const nextStage = activeIndex >= 0 ? stageTabs[activeIndex + 1] : undefined;
  const canAdvanceStage =
    resolvedStage.id === "ingestion"
      ? reportState === "ready"
      : resolvedStage.id === "manipulation"
        ? manipulationState === "ready"
        : false;

  const handleToggleQuestion = (id: string) => {
    setExpandedQuestions((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleToggleVulnQuestion = (id: string) => {
    setExpandedVulnQuestions((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleToggleEvaluationQuestion = (id: string) => {
    setExpandedEvaluationQuestions((prev) => ({ ...prev, [id]: !prev[id] }));
  };
  const handleVariantDownload = React.useCallback(
    (event: React.MouseEvent<HTMLButtonElement>, variant: VariantCard) => {
      event.stopPropagation();
      if (!variant.downloadUrl) return;
      if (typeof window !== "undefined") {
        window.open(variant.downloadUrl, "_blank", "noopener,noreferrer");
      }
    },
    []
  );
  const handleAdvanceStage = React.useCallback(() => {
    if (!resolvedStage) return;
    const currentIndex = stageTabs.findIndex((tab) => tab.id === resolvedStage.id);
    const upcomingStage = stageTabs[currentIndex + 1];
    if (!upcomingStage) return;
    if (resolvedStage.id === "ingestion" && reportState !== "ready") return;
    if (resolvedStage.id === "manipulation" && manipulationState !== "ready") return;
    if (resolvedStage.id === "ingestion" && manipulationState !== "ready") {
      setManipulationState("loading");
      if (stageTransitionTimer.current) {
        window.clearTimeout(stageTransitionTimer.current);
      }
      stageTransitionTimer.current = window.setTimeout(() => {
        setManipulationState("ready");
        stageTransitionTimer.current = null;
      }, 900);
    }
    if (resolvedStage.id === "ingestion") {
      setMode("detection");
      setModeLocked(true);
    }
    if (upcomingStage.id === "delivery") {
      setEvaluationPhase("idle");
      setVariantBestReady(false);
      setPdfPreviewStatus({});
      setEvaluationRevealState({});
    }
    navigate(`/demo/pipeline/${upcomingStage.id}`);
  }, [manipulationState, navigate, reportState, resolvedStage]);
  const handleProceedToClassrooms = React.useCallback(() => {
    navigate("/classrooms");
  }, [navigate]);

  const renderStageContent = () => {
    if (resolvedStage.id === "ingestion") {
      const uploadCardConfigs = [
        { id: "assessment" as const, title: "Assessment PDF", asset: assessmentAsset },
        { id: "answer" as const, title: "Answer key PDF", asset: answerKeyAsset },
      ];
      const metadataReady = metadataPhase === "complete";
      const showVulnerabilityContent = reportState === "streaming" || reportState === "ready";
      const vulnProgressLoaded = Object.keys(vulnRevealedQuestions).length;
      const vulnProgressTotal = vulnerabilityQuestions.length;
      const vulnReportComplete = vulnProgressTotal > 0 && vulnProgressLoaded === vulnProgressTotal;
      const isVulnStreaming = reportState === "streaming";
      const overviewTotalDisplay = metadataReady ? overviewMeta.total : "—";
      return (
        <section className="ishield-demo__stage">
          <div className="ishield-demo__overview-card">
            <div className="ishield-demo__overview-section">
              <p className="ishield-demo__overview-label">Questions detected</p>
              <h4 className={!metadataReady ? "is-muted" : ""}>{overviewTotalDisplay}</h4>
              <div className="ishield-demo__pill-row">
                {overviewMeta.types.length ? (
                  overviewMeta.types.map(([type, count]) => (
                    <span key={type} className="ishield-demo__pill is-ghost">
                      {count} · {titleCase(type)}
                    </span>
                  ))
                ) : (
                  <span className="ishield-demo__pill is-ghost">Awaiting upload</span>
                )}
              </div>
              {isVulnStreaming && (
                <small className="ishield-demo__progress-note">
                  Scoring {vulnProgressLoaded}/{vulnProgressTotal} questions…
                </small>
              )}
            </div>
            <div className="ishield-demo__overview-section">
              <p className="ishield-demo__overview-label">Document metadata</p>
              <div className="ishield-demo__overview-meta">
                <div>
                  <span>Filename</span>
                  <strong className={!metadataReady ? "is-muted" : ""}>
                    {metadataReady ? overviewMeta.document.filename : "Processing…"}
                  </strong>
                </div>
                <div>
                  <span>Pages</span>
                  <strong className={!metadataReady ? "is-muted" : ""}>
                    {metadataReady ? overviewMeta.document.pages : "—"}
                  </strong>
                </div>
                <div>
                  <span>Assessment ID</span>
                  <strong className={!metadataReady ? "is-muted" : ""}>
                    {metadataReady ? overviewMeta.document.runId : "—"}
                  </strong>
                </div>
                <div>
                  <span>Answer key</span>
                  <strong>
                    {metadataReady && overviewMeta.answerKey.status === "parsed"
                      ? `Parsed · ${overviewMeta.answerKey.parsed}`
                      : "Pending"}
                  </strong>
                </div>
              </div>
            </div>
          </div>

          <div className="ishield-demo__split ishield-demo__split--ingestion">
            <div className="ishield-demo__upload-stack">{uploadCardConfigs.map((config) => renderUploadCard(config))}</div>

            <div className="ishield-demo__vuln-panel">
              <div className="ishield-demo__vuln-header">
                <div className="ishield-demo__vuln-title ishield-demo__vuln-title--centered">
                  <span>VULNERABILITY REPORT</span>
                  {reportState === "ready" ? (
                    <>
                      <span className="ishield-demo__vuln-divider">—</span>
                      <span className="ishield-demo__risk-callout">
                        <strong>High</strong> vulnerability
                      </span>
                    </>
                  ) : null}
                </div>
                <div className="ishield-demo__vuln-actions">
                  <button type="button" className="pill-button ghost">
                    <Download size={14} />
                    <span>Download</span>
                  </button>
                  <div className="ishield-demo__vuln-icon">
                    <Target size={18} />
                  </div>
                </div>
              </div>

              {showVulnerabilityContent ? (
                <>
                  {vulnReportComplete ? (
                    <div className="ishield-demo__provider-grid">
                      {providerSummary.map((provider) => (
                        <div key={provider.provider} className="ishield-demo__provider-card">
                          <div className="ishield-demo__provider-head">
                            <div className="ishield-demo__provider-chip">
                              <ModelIcon provider={provider.provider} />
                              <span>{providerDisplay[provider.provider]?.label ?? titleCase(provider.provider)}</span>
                            </div>
                            <strong>{toPercent(provider.averageScore, 0)}</strong>
                          </div>
                          <div className="ishield-demo__provider-metrics">
                            <span className="ishield-demo__metric-badge is-correct">
                              <Check size={10} /> {provider.correct}
                            </span>
                            <span className="ishield-demo__metric-badge is-incorrect">
                              <X size={10} /> {provider.incorrect}
                            </span>
                            <span className="ishield-demo__metric-badge is-missing">
                              <Slash size={10} /> {provider.missing}
                            </span>
                            <span className="ishield-demo__provider-total">Total · {provider.coverage}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="ishield-demo__provider-placeholder">Scoring models…</div>
                  )}

                  <div className="ishield-demo__vuln-body">
                    <div className="ishield-demo__section-stack">
                      {sectionCards.map((section) => (
                        <div key={section.id} className={`ishield-demo__section-card ${expandedSections[section.id] ? "is-open" : ""}`}>
                          <button type="button" className="ishield-demo__section-card-toggle" onClick={() => toggleSection(section.id)}>
                            <div className="ishield-demo__section-card-head">
                              <span className="ishield-demo__section-card-label">{section.label}</span>
                              <span className="ishield-demo__section-card-count">
                                {section.coverage} question{section.coverage === 1 ? "" : "s"}
                              </span>
                            </div>
                            <ChevronDown size={16} className={expandedSections[section.id] ? "is-rotated" : ""} />
                          </button>
                          {section.questions.every((question) => vulnRevealedQuestions[question.id]) ? (
                            <div className="ishield-demo__section-provider-bar">
                              {section.providerStats.map((provider) => {
                                const providerLabel = providerDisplay[provider.provider]?.label ?? titleCase(provider.provider);
                                return (
                                  <div key={`${section.id}-${provider.provider}`} className="ishield-demo__section-provider-chip">
                                    <div className="ishield-demo__section-provider-row">
                                      <span className="ishield-demo__section-provider-icon">
                                        <ModelIcon provider={provider.provider} compact />
                                      </span>
                                      <span className="ishield-demo__section-provider-name">{providerLabel}</span>
                                      <strong>{provider.total ? `${Math.round(provider.accuracy)}%` : "—"}</strong>
                                    </div>
                                    <span className="ishield-demo__section-provider-counts">
                                      <span className="ishield-demo__metric-badge is-correct">
                                        <Check size={10} /> {provider.correct}
                                      </span>
                                      <span className="ishield-demo__metric-badge is-incorrect">
                                        <X size={10} /> {provider.incorrect}
                                      </span>
                                      <span className="ishield-demo__metric-badge is-missing">
                                        <Slash size={10} /> {provider.missing}
                                      </span>
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="ishield-demo__provider-placeholder">Finishing section scoring…</div>
                          )}
                          <div className={`ishield-demo__section-questions ${expandedSections[section.id] ? "is-open" : ""}`}>
                            {section.questions.length ? (
                              section.questions.map((question) =>
                                renderQuestionCard(
                                  question,
                                  Boolean(expandedVulnQuestions[question.id]),
                                  () => handleToggleVulnQuestion(question.id),
                                  Boolean(vulnRevealedQuestions[question.id]),
                                ),
                              )
                            ) : (
                              <p className="ishield-demo__section-empty">No questions assigned to this section.</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className={`ishield-demo__report-placeholder ${reportState === "loading" ? "is-loading" : ""}`}>
                  {reportState === "loading" ? (
                    <>
                      <div className="ishield-demo__spinner" aria-hidden="true" />
                      <p>Parsing uploads and extracting metadata…</p>
                    </>
                  ) : (
                    <p>Upload the assessment and answer key to generate a vulnerability report.</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      );
    }

    if (resolvedStage.id === "manipulation") {
      if (manipulationState !== "ready") {
        return (
          <section className="ishield-demo__stage">
            <div className={`ishield-demo__report-placeholder ${manipulationState === "loading" ? "is-loading" : ""}`}>
              {manipulationState === "loading" ? (
                <>
                  <div className="ishield-demo__spinner" aria-hidden="true" />
                  <p>Preparing manipulation insights…</p>
                </>
              ) : (
                <p>Complete Stage 1 and use "Next stage" to load manipulation analytics.</p>
              )}
            </div>
          </section>
        );
      }
      const detectionVisibleCount = Object.keys(detectionVisibleQuestions).length;
      const detectionTotal = detectionQuestionCards.length;
      const detectionManipulatedCount = Object.keys(revealedDetectionQuestions).length;
      const detectionStreaming =
        detectionVisibleCount < detectionTotal || detectionManipulatedCount < detectionTotal;
      return (
        <section className="ishield-demo__stage">
          {detectionStreaming && (
            <div className="ishield-demo__progress-note">
              Mapping manipulations {detectionManipulatedCount}/{detectionTotal} · Loading questions {detectionVisibleCount}/{detectionTotal}
            </div>
          )}
          <div className="ishield-demo__section-stack">
            {detectionSectionCards.map((section) => (
              <div key={section.id} className={`ishield-demo__section-card ${expandedDetectionSections[section.id] ? "is-open" : ""}`}>
                <button type="button" className="ishield-demo__section-card-toggle" onClick={() => toggleDetectionSection(section.id)}>
                  <div className="ishield-demo__section-card-head">
                    <span className="ishield-demo__section-card-label">{section.label}</span>
                    <span className="ishield-demo__section-card-count">
                      {section.coverage} question{section.coverage === 1 ? "" : "s"} · {section.manipulatedLoaded}/{section.manipulatedTotal} manipulated
                    </span>
                  </div>
                  <ChevronDown size={16} className={expandedDetectionSections[section.id] ? "is-rotated" : ""} />
                </button>
                <div className={`ishield-demo__section-questions ${expandedDetectionSections[section.id] ? "is-open" : ""}`}>
                  {section.questions.length ? (
                    section.questions.map((question) => {
                      const isExpanded = Boolean(expandedQuestions[question.id]);
                      const isQuestionVisible = Boolean(detectionVisibleQuestions[question.id]);
                      if (!isQuestionVisible) {
                        return (
                          <div key={question.id} className="ishield-demo__question-card is-loading">
                            <div className="ishield-demo__skeleton-line" />
                            <div className="ishield-demo__skeleton-line short" />
                            <div className="ishield-demo__skeleton-block" />
                          </div>
                        );
                      }
                      const showManipulation = Boolean(revealedDetectionQuestions[question.id] && question.mapping);
                      const effectivenessLabel =
                        showManipulation && question.mapping?.effectiveness != null ? toPercent(question.mapping.effectiveness) : null;
  const highlightTooltip = showManipulation
    ? (
        <div className="ishield-demo__stem-tooltip-content">
          <div className="ishield-demo__tooltip-mapping">
            <span>Mapping</span>
            <div className="ishield-demo__mapping-display">
              <span className="ishield-demo__mapping-chip">{question.mapping?.original}</span>
              <span className="ishield-demo__mapping-arrow">→</span>
              <span className="ishield-demo__mapping-chip">{question.mapping?.replacement}</span>
            </div>
          </div>
          <div className="ishield-demo__tooltip-row">
            <span>{question.question_type === "mcq_single" ? "Target" : "Signal"}</span>
            <p>
              {question.question_type === "mcq_single"
                ? question.target
                : `${question.signalDetail?.type ?? "concept"} · ${question.signalDetail?.notes ?? "—"}`}
            </p>
          </div>
          {effectivenessLabel && (
            <div className="ishield-demo__tooltip-row">
              <span>Effectiveness</span>
              <strong>{effectivenessLabel}</strong>
            </div>
          )}
        </div>
      )
    : undefined;
                      return (
                        <div
                          key={question.id}
                          className={`ishield-demo__question-card ${expandedQuestions[question.id] ? "is-open" : ""} ${
                            revealedDetectionQuestions[question.id] ? "is-revealed" : ""
                          }`}
                        >
                          <button type="button" className="ishield-demo__question-toggle" onClick={() => handleToggleQuestion(question.id)}>
                            <div className="ishield-demo__question-heading">
                              <span className="ishield-demo__question-id">Q{question.id}</span>
                              {!isExpanded && <p>{question.stem}</p>}
                            </div>
                            <div className="ishield-demo__question-meta">
                              {question.confidence && <span className="ishield-demo__confidence">{question.confidence.toFixed(2)}</span>}
                              {effectivenessLabel && <span className="ishield-demo__effectiveness-pill">{effectivenessLabel}</span>}
                              <ChevronDown size={16} className={isExpanded ? "is-rotated" : ""} />
                            </div>
                          </button>
                          {isExpanded ? (
                            <div className="ishield-demo__question-body">
                              <div className="ishield-demo__question-stem">
                                <p>{renderStemWithHighlight(question.stem, showManipulation ? question.mapping?.original : undefined, highlightTooltip)}</p>
                                {question.options?.length ? (
                                  <ul className="ishield-demo__question-options">
                                    {question.options.map((option) => (
                                      <li
                                        key={`${question.id}-${option.label}`}
                                        className={[
                                          option.label === question.goldLabel ? "is-gold-option" : "",
                                          showManipulation && option.label === question.targetLabel ? "is-target-option" : "",
                                        ]
                                          .filter(Boolean)
                                          .join(" ")}
                                      >
                                        <span>{option.label}</span>
                                        <p>{option.text}</p>
                                      </li>
                                    ))}
                                  </ul>
                                ) : null}
                              </div>
                              <div className="ishield-demo__question-pair">
                                <span>Answer key</span>
                                <span className="ishield-demo__answer-value">{question.gold}</span>
                              </div>
                              {question.mapping ? (
                                showManipulation ? (
                                  <div className="ishield-demo__manipulation-block">
                                    <div className="ishield-demo__manipulation-title">Manipulation</div>
                                    <div className="ishield-demo__manipulation-row">
                                      <span>Mapping</span>
                                      <div className="ishield-demo__mapping-display">
                                        <span className="ishield-demo__mapping-chip">{question.mapping.original}</span>
                                        <span className="ishield-demo__mapping-arrow">→</span>
                                        <span className="ishield-demo__mapping-chip">{question.mapping.replacement}</span>
                                      </div>
                                    </div>
                                    <div className="ishield-demo__manipulation-row">
                                      <span>{question.question_type === "mcq_single" ? "Target" : "Signal"}</span>
                                      <div className="ishield-demo__manipulation-target">
                                        <span className="ishield-demo__answer-value">
                                          {question.question_type === "mcq_single"
                                            ? question.target
                                            : `${question.signalDetail?.type ?? "concept"} · ${question.signalDetail?.notes ?? "—"}`}
                                        </span>
                                        {effectivenessLabel && (
                                          <div className="ishield-demo__manipulation-effectiveness">
                                            <strong>{effectivenessLabel}</strong>
                                            <small>Effectiveness</small>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                    {question.mapping.validation && (
                                      <div className="ishield-demo__manipulation-row">
                                        <span>Strategy</span>
                                        <p className="ishield-demo__question-notes">{question.mapping.validation}</p>
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <div className="ishield-demo__manipulation-placeholder">Updating manipulation…</div>
                                )
                              ) : (
                                <p className="ishield-demo__question-notes">{question.notes}</p>
                              )}
                            </div>
                          ) : null}
                        </div>
                      );
                    })
                  ) : (
                    <p className="ishield-demo__section-empty">No questions assigned to this section.</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      );
    }

    const selectedVariantMeta = variantCards.find((variant) => variant.method === selectedVariant);
    const selectedVariantDisplay = selectedVariantMeta?.displayLabel ?? titleCase(selectedVariant.replace(/_/g, " "));
    const variantCountLabel = `${variantCount} detection variant${variantCount === 1 ? "" : "s"}`;
    const bestVariantSummary =
      variantBestReady && bestVariantLabel ? `${bestVariantLabel} · ${toPercent(bestVariant?.detection ?? 0)}` : null;
    const variantSelectionFinalized = variantBestReady && selectedVariant === lockedVariantMethod;
    const evaluationRevealCount = Object.keys(evaluationRevealState).length;
    const evaluationTotal = evaluationQuestionsDetailed.length;
    const evaluationComplete = evaluationRevealCount === evaluationTotal && evaluationTotal > 0;
    const evaluationRendering =
      variantSelectionFinalized && (evaluationPhase === "report-loading" || evaluationPhase === "ready");
    const evaluationReady = variantSelectionFinalized && evaluationPhase === "ready";
    const evaluationPlaceholderMessage =
      evaluationPhase === "pdf-loading"
        ? "Preparing detection variants…"
        : evaluationPhase === "variant-finalizing"
          ? "Finalizing best detection variant…"
          : "Evaluation results are only available once the optimal detection variant is selected.";

    return (
      <section className="ishield-demo__stage">
        <div className="ishield-demo__top-actions">
          <div className="ishield-demo__top-actions-left">
            <button className="pill-button">
              Export package <ChevronRight size={14} />
            </button>
          </div>
          <div className="ishield-demo__top-actions-right">
            <button className="pill-button ishield-demo__classroom-btn" onClick={handleProceedToClassrooms}>
              <Layers size={14} />
              <span>Proceed to classroom</span>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        <div className="ishield-demo__split ishield-demo__split--delivery">
          <div className="ishield-demo__variant-panel">
            <div className="ishield-demo__variant-summary">
              <span className="ishield-demo__variant-summary-count">{variantCountLabel}</span>
              {bestVariantSummary && <span className="ishield-demo__variant-summary-best">Best · {bestVariantSummary}</span>}
            </div>

            <div className="ishield-demo__variant-column">
            {variantCards.map((variant) => {
              const previewSource = sharedAssessmentPreview;
              const previewReady = pdfPreviewStatus[`variant-${variant.method}`];
              const isLockedVariant = variant.method === lockedVariantMethod;
              const isSelectable = isLockedVariant && variantBestReady;
              const isSelected = variantBestReady && selectedVariant === variant.method;
              return (
                <div
                  key={variant.method}
                  role="button"
                  tabIndex={isSelectable ? 0 : -1}
                  className={`ishield-demo__variant-card ${isSelected ? "is-selected" : ""} ${
                    isLockedVariant ? "" : "is-readonly"
                  }`}
                  onClick={() => {
                      if (isSelectable) {
                      setSelectedVariant(variant.method);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (!isSelectable) return;
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedVariant(variant.method);
                    }
                  }}
                >
                  <div className="ishield-demo__variant-row">
                    <div className="ishield-demo__variant-labels">
                      <span className="ishield-demo__variant-icon">
                        <LayoutGrid size={16} />
                      </span>
                      <div>
                        <p>{variant.displayLabel ?? variant.label}</p>
                        {variantBestReady && isSelected && (
                          <span className="ishield-demo__selected-pill">
                            <CheckCircle2 size={12} /> Selected
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="ishield-demo__variant-download"
                      disabled={!variant.downloadUrl || !previewReady}
                      onClick={(event) => handleVariantDownload(event, variant)}
                    >
                      Download PDF
                    </button>
                  </div>
                  <div className={`ishield-demo__variant-preview ${previewReady ? "" : "is-loading"}`}>
                    {previewSource && previewReady ? (
                      <iframe
                        title={`${variant.displayLabel ?? variant.label} preview`}
                        src={`${previewSource}#toolbar=0&navpanes=0&scrollbar=0`}
                        loading="lazy"
                      />
                    ) : (
                      <div className="ishield-demo__variant-preview-placeholder">
                        {previewReady ? "Preview unavailable" : "Rendering PDF…"}
                      </div>
                    )}
                  </div>
                  <div className="ishield-demo__variant-meta">
                    <span>{variant.detail}</span>
                    <span className="ishield-demo__variant-size">File size · {variant.sizeLabel}</span>
                  </div>
                  <div className="ishield-demo__variant-stats">
                    <div className="ishield-demo__variant-stat">
                      <span>Effectiveness</span>
                      <strong>{toPercent(variant.effectiveness)}</strong>
                    </div>
                    <div className="ishield-demo__variant-stat is-detection">
                      <span>Detection</span>
                      <strong>{toPercent(variant.detection)}</strong>
                    </div>
                  </div>
                </div>
              );
            })}
            </div>
          </div>

          <div className="ishield-demo__evaluation-panel">
            <div className="ishield-demo__vuln-header">
              <div className="ishield-demo__vuln-title ishield-demo__vuln-title--centered">
                <span>EVALUATION REPORT</span>
                <span className="ishield-demo__risk-callout">
                  <span className="ishield-demo__risk-divider">—</span>
                  <strong className="is-safe">NO</strong> vulnerability
                </span>
                {variantBestReady && selectedVariantDisplay && (
                  <span className="ishield-demo__variant-link-chip">Linked to {selectedVariantDisplay}</span>
                )}
              </div>
              <div className="ishield-demo__vuln-actions">
                <button type="button" className="pill-button ghost">
                  <Download size={14} />
                  <span>Download</span>
                </button>
                <div className="ishield-demo__vuln-icon">
                  <Activity size={18} />
                </div>
              </div>
            </div>

            {evaluationRendering ? (
              <>
                <div className="ishield-demo__provider-grid">
                  {evaluationComplete ? (
                    evaluationProviderSummary.map((provider) => (
                      <div key={provider.provider} className="ishield-demo__provider-card">
                        <div className="ishield-demo__provider-head">
                          <div className="ishield-demo__provider-chip">
                            <ModelIcon provider={provider.provider} />
                            <span>{providerDisplay[provider.provider]?.label ?? titleCase(provider.provider)}</span>
                          </div>
                          <strong>{toPercent(provider.averageScore, 0)}</strong>
                        </div>
                        <div className="ishield-demo__provider-metrics">
                          <span>Δ {formatDelta(provider.averageDelta, 0)}</span>
                          <span className="ishield-demo__metric-badge is-correct">
                            <Check size={10} /> {provider.correct}
                          </span>
                          <span className="ishield-demo__metric-badge is-incorrect">
                            <X size={10} /> {provider.incorrect}
                          </span>
                          <span className="ishield-demo__metric-badge is-missing">
                            <Slash size={10} /> {provider.missing}
                          </span>
                          <span className="ishield-demo__metric-badge is-target-count">
                            <Target size={10} /> {provider.targetHits}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="ishield-demo__provider-placeholder">Waiting for evaluation scores…</div>
                  )}
                </div>
                {evaluationPhase === "report-loading" && (
                  <div className="ishield-demo__progress-note">
                    Scoring {evaluationRevealCount}/{evaluationTotal} questions…
                  </div>
                )}

                <div className="ishield-demo__section-stack">
                  {evaluationSectionCards.map((section) => (
                    <div key={section.id} className={`ishield-demo__section-card ${expandedEvalSections[section.id] ? "is-open" : ""}`}>
                      <button type="button" className="ishield-demo__section-card-toggle" onClick={() => toggleEvalSection(section.id)}>
                        <div className="ishield-demo__section-card-head">
                          <span className="ishield-demo__section-card-label">{section.label}</span>
                          <span className="ishield-demo__section-card-count">
                            {section.coverage} question{section.coverage === 1 ? "" : "s"}
                          </span>
                        </div>
                        <ChevronDown size={16} className={expandedEvalSections[section.id] ? "is-rotated" : ""} />
                      </button>
                      {section.questions.every((question) => evaluationRevealState[question.id]) ? (
                        <div className="ishield-demo__section-provider-bar">
                          {section.providerStats.map((provider) => {
                            const providerLabel = providerDisplay[provider.provider]?.label ?? titleCase(provider.provider);
                            return (
                              <div key={`${section.id}-${provider.provider}`} className="ishield-demo__section-provider-chip">
                                <div className="ishield-demo__section-provider-row">
                                  <span className="ishield-demo__section-provider-icon">
                                    <ModelIcon provider={provider.provider} compact />
                                  </span>
                                  <span className="ishield-demo__section-provider-name">{providerLabel}</span>
                                  <strong>{provider.total ? `${Math.round(provider.accuracy)}%` : "—"}</strong>
                                </div>
                                <span className="ishield-demo__section-provider-counts">
                                  <span className="ishield-demo__metric-badge is-correct">
                                    <Check size={10} /> {provider.correct}
                                  </span>
                                  <span className="ishield-demo__metric-badge is-incorrect">
                                    <X size={10} /> {provider.incorrect}
                                  </span>
                                  <span className="ishield-demo__metric-badge is-missing">
                                    <Slash size={10} /> {provider.missing}
                                  </span>
                                  <span className="ishield-demo__metric-badge is-target">
                                    <Target size={10} /> {provider.targetHits}
                                  </span>
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="ishield-demo__provider-placeholder">Scoring section…</div>
                      )}
                      <div className={`ishield-demo__section-questions ${expandedEvalSections[section.id] ? "is-open" : ""}`}>
                        {section.questions.length ? (
                          section.questions.map((question) =>
                            renderEvaluationQuestionCard(
                              question,
                              Boolean(expandedEvaluationQuestions[question.id]),
                              () => handleToggleEvaluationQuestion(question.id),
                              Boolean(evaluationRevealState[question.id]),
                            ),
                          )
                        ) : (
                          <p className="ishield-demo__section-empty">No questions assigned to this section.</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="ishield-demo__evaluation-placeholder">{evaluationPlaceholderMessage}</p>
            )}
          </div>
        </div>
      </section>
    );
  };

  return (
    <div className="ishield-demo">
      <header className="ishield-demo__top-nav">
        <div className="ishield-demo__brand-stack">
          <div className="ishield-demo__brand">
            <img src={getAssetUrl("/icons/logo.png")} alt="IntegrityShield" className="ishield-demo__brand-logo" />
            <div className="ishield-demo__brand-title">INTEGRITYSHIELD</div>
          </div>
          <div className="ishield-demo__meta-bar">
            <span className="ishield-demo__meta-pill">{stageLabel} · {stageStatus}</span>
            <span className="ishield-demo__meta-pill">Assessment {runIdentifier}</span>
            {modeLocked && <span className="ishield-demo__meta-pill is-detection">Detection run</span>}
            <span className="ishield-demo__meta-pill">Last sync {formattedLastSync}</span>
          </div>
        </div>
        <div className="ishield-demo__actions">
          <button className="ishield-demo__action-refresh" type="button" onClick={handleManualRefresh}>
            <RotateCcw size={18} strokeWidth={1.8} aria-hidden="true" />
            <span>Refresh</span>
          </button>
          <div className="ishield-demo__actions-cluster">
            <button type="button" className="ishield-demo__icon-chip" aria-label="Notifications" data-tooltip="Notifications">
              <Bell size={40} strokeWidth={1.6} aria-hidden="true" />
            </button>
            <button type="button" className="ishield-demo__icon-chip" aria-label="Open settings" data-tooltip="Settings">
              <Settings size={40} strokeWidth={1.4} aria-hidden="true" />
            </button>
            <div className="ishield-demo__avatar">P</div>
          </div>
        </div>
      </header>

      <div className="ishield-demo__stage-bar">
        <div className="ishield-demo__subnav">
          {stageTabs.map((tab, index) => {
            const tabState = index < activeIndex ? "is-complete" : index === activeIndex ? "is-active" : "is-pending";
            return (
              <NavLink
                key={tab.id}
                to={`/demo/pipeline/${tab.id}`}
                className={({ isActive }) => `ishield-demo__subnav-link ${tabState} ${isActive ? "is-active" : ""}`}
              >
                <span className="ishield-demo__stage-pill">{tab.stageLabel}</span>
                <strong>{tab.label}</strong>
              </NavLink>
            );
          })}
        </div>

        <div className="ishield-demo__stage-controls">
          <div className="ishield-demo__mode-toggle">
            <span className="ishield-demo__mode-label">Mode</span>
            <div className="ishield-demo__mode-buttons">
              <button
                type="button"
                className={mode === "prevention" ? "is-active" : ""}
                disabled={modeLocked}
                onClick={() => {
                  if (modeLocked) return;
                  setMode("prevention");
                }}
              >
                Prevention
              </button>
              <button
                type="button"
                className={mode === "detection" ? "is-active" : ""}
                disabled={modeLocked}
                onClick={() => {
                  if (modeLocked) return;
                  setMode("detection");
                }}
              >
                Detection
              </button>
            </div>
          </div>
          <button
            type="button"
            className="pill-button ishield-demo__next-stage-btn"
            onClick={handleAdvanceStage}
            disabled={!nextStage || !canAdvanceStage}
          >
            Next stage <ChevronRight size={14} />
          </button>
        </div>
      </div>

      {renderStageContent()}
    </div>
  );
};

export default IntegrityShieldPipelineDemo;
