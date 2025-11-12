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
