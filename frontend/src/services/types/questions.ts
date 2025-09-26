export interface SubstringMapping {
  id?: string;
  original: string;
  replacement: string;
  start_pos: number;
  end_pos: number;
  context: string;
  character_mappings?: Record<string, string>;
  effectiveness_score?: number;
  visual_similarity?: number;
  semantic_impact?: "low" | "medium" | "high";
}

export interface QuestionManipulation {
  id: number;
  question_number: string;
  question_type: string;
  original_text?: string;
  options_data?: Record<string, unknown>;
  gold_answer?: string;
  manipulation_method?: string;
  effectiveness_score?: number;
  substring_mappings: SubstringMapping[];
  ai_model_results: Record<string, unknown>;
}

export interface QuestionListResponse {
  run_id: string;
  total: number;
  questions: QuestionManipulation[];
}
