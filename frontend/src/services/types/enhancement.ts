export interface EnhancementMethodSummary {
  method: string;
  effectiveness_score: number;
  visual_quality_score?: number;
  path?: string;
}

export interface EnhancedPdfRecord {
  method_name: string;
  file_path: string;
  file_size_bytes?: number;
  effectiveness_stats?: Record<string, unknown>;
  validation_results?: Record<string, unknown>;
  visual_quality_score?: number;
}
