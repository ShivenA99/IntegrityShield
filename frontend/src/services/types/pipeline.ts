export type CorePipelineStageName =
  | "smart_reading"
  | "content_discovery"
  | "smart_substitution"
  | "effectiveness_testing"
  | "document_enhancement"
  | "pdf_creation"
  | "results_generation";

export type PipelineStageName = CorePipelineStageName | "classroom_dataset" | "classroom_evaluation";

export interface PipelineStageState {
  id: number;
  name: PipelineStageName;
  status: "pending" | "running" | "completed" | "failed";
  duration_ms?: number | null;
  error?: string | null;
}

export interface PipelineRunSummary {
  run_id: string;
  status: string;
  current_stage: CorePipelineStageName;
  parent_run_id?: string | null;
  resume_target?: PipelineStageName | null;
  updated_at?: string | null;
  pipeline_config: Record<string, unknown>;
  structured_data?: Record<string, unknown>;
  stages: PipelineStageState[];
  processing_stats?: Record<string, unknown>;
  classrooms?: ClassroomDataset[];
  classroom_progress?: ClassroomProgress;
}

export interface PipelineConfigPayload {
  ai_models: string[];
  enhancement_methods: string[];
  target_stages: CorePipelineStageName[];
  skip_if_exists: boolean;
  parallel_processing: boolean;
}

export interface AnswerSheetGenerationConfig {
  total_students?: number;
  cheating_rate?: number;
  cheating_breakdown?: {
    llm?: number;
    peer?: number;
  };
  copy_profile?: {
    full_copy_probability?: number;
    partial_copy_min?: number;
    partial_copy_max?: number;
  };
  paraphrase_probability?: number;
  write_parquet?: boolean;
}

export interface AnswerSheetGenerationResult {
  run_id: string;
  students: number;
  cheating_counts: {
    total: number;
    llm: number;
    peer: number;
    fair: number;
  };
  output_files: {
    json: string;
    summary: string;
    parquet: string | null;
  };
  classroom?: ClassroomDataset;
}

export interface DetectionReportMappingInsight {
  original: string | null;
  replacement: string | null;
  context: string | null;
  validated: boolean;
  target_wrong_answer: string | null;
  deviation_score: number | null;
  confidence: number | null;
  validation_reason: string | null;
}

export interface DetectionReportRiskFactors {
  total: number;
  validated: number;
  target_labels: string[];
  replacements: string[];
  average_deviation_score: number | null;
  average_confidence: number | null;
}

export interface DetectionReportQuestion {
  question_number: string;
  question_type: string;
  stem_text: string;
  options: { label: string; text: string }[];
  is_subjective: boolean;
  subjective_reference_answer: string | null;
  gold_answer: {
    label: string | null;
    text: string | null;
  };
  target_answer: {
    labels: string[];
    texts: string[];
    raw_replacements: string[];
  };
  mappings: DetectionReportMappingInsight[];
  risk_level: string;
  risk_factors: DetectionReportRiskFactors;
}

export interface DetectionReportSummary {
  total_questions: number;
  questions_with_mappings: number;
  questions_missing_mappings: number;
  validated_mappings: number;
  total_mappings: number;
  high_risk_questions: number;
  target_label_distribution: { label: string; count: number }[];
}

export interface BaseReportResult {
  run_id: string;
  report_type?: string;
  generated_at: string;
  summary: Record<string, unknown>;
  questions: Record<string, unknown>[];
  output_files: {
    json: string;
  };
}

export interface DetectionReportResult extends BaseReportResult {
  report_type: "detection";
  summary: DetectionReportSummary;
  questions: DetectionReportQuestion[];
}

export interface VulnerabilityReportResult extends BaseReportResult {
  report_type: "vulnerability";
  questions: {
    question_number: string;
    question_text: string;
    answers: any[];
  }[];
}

export interface EvaluationReportContext {
  detection?: {
    generated_at?: string;
    summary?: DetectionReportSummary;
  };
  vulnerability?: {
    generated_at?: string;
    summary?: Record<string, unknown>;
  };
}

export interface EvaluationReportAnswer {
  provider: string;
  answer_label?: string | null;
  answer_text?: string | null;
  scorecard?: {
    provider?: string;
    score?: number;
    verdict?: string;
    confidence?: number;
    rationale?: string;
    source?: string;
    hit_detection_target?: boolean | null;
  };
  matches_detection_target?: boolean | null;
  baseline_score?: number | null;
  delta_from_baseline?: number | null;
  error?: string | null;
}

export interface EvaluationReportResult extends BaseReportResult {
  report_type: "evaluation";
  method: string;
  context?: EvaluationReportContext;
  questions: {
    question_number: string;
    question_text: string;
    question_type?: string;
    options?: { label: string; text: string }[];
    detection_target?: {
      labels?: string[];
      texts?: string[];
    };
    answers: EvaluationReportAnswer[];
  }[];
}

export interface ClassroomProgress {
  has_attacked_pdf: boolean;
  classrooms: number;
  evaluations_completed: number;
}

export interface ClassroomEvaluation {
  id: number;
  status: string;
  summary: Record<string, unknown>;
  artifacts: Record<string, string>;
  evaluation_config: Record<string, unknown>;
  completed_at?: string | null;
  updated_at?: string | null;
}

export interface ClassroomDataset {
  id: number;
  classroom_key: string | null;
  classroom_label: string | null;
  notes?: string | null;
  attacked_pdf_method: string | null;
  attacked_pdf_path?: string | null;
  origin: string;
  status: string;
  total_students: number;
  summary: Record<string, unknown>;
  artifacts: Record<string, string | null>;
  created_at?: string | null;
  updated_at?: string | null;
  last_evaluated_at?: string | null;
  evaluation?: ClassroomEvaluation | null;
}

export interface ClassroomCreationPayload {
  classroom: {
    id?: number;
    classroom_key?: string;
    label: string;
    notes?: string;
    attacked_pdf_method: string;
    origin?: string;
  };
  config?: AnswerSheetGenerationConfig;
}

export interface ClassroomEvaluatePayload {
  config?: Record<string, unknown>;
}

export interface ClassroomEvaluationResponse {
  id: number;
  status: string;
  summary: Record<string, unknown>;
  artifacts: Record<string, string>;
  evaluation_config: Record<string, unknown>;
  completed_at?: string | null;
  updated_at?: string | null;
  students?: ClassroomStudentMetric[];
}

export interface ClassroomStudentMetric {
  student_id: number;
  student_key: string;
  display_name: string;
  is_cheating: boolean;
  cheating_strategy?: string | null;
  copy_fraction?: number | null;
  paraphrase_style?: string | null;
  score: number;
  total_questions: number;
  correct_answers: number;
  incorrect_answers: number;
  cheating_source_counts: Record<string, number>;
  average_confidence?: number | null;
  metadata?: Record<string, unknown>;
}
