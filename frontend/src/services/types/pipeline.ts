export type PipelineStageName =
  | "smart_reading"
  | "content_discovery"
  | "smart_substitution"
  | "effectiveness_testing"
  | "document_enhancement"
  | "pdf_creation"
  | "results_generation";

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
  current_stage: PipelineStageName;
  parent_run_id?: string | null;
  resume_target?: PipelineStageName | null;
  updated_at?: string | null;
  pipeline_config: Record<string, unknown>;
  structured_data?: Record<string, unknown>;
  stages: PipelineStageState[];
  processing_stats?: Record<string, unknown>;
}

export interface PipelineConfigPayload {
  ai_models: string[];
  enhancement_methods: string[];
  target_stages: PipelineStageName[];
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

export interface DetectionReportResult {
  run_id: string;
  generated_at: string;
  summary: DetectionReportSummary;
  questions: DetectionReportQuestion[];
  output_files: {
    json: string;
  };
}