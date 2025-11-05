export interface SubstringMapping {
  id?: string;
  original: string;
  replacement: string;
  start_pos: number;
  end_pos: number;
  context: string;
  selection_page?: number;
  selection_bbox?: number[];
  selection_quads?: number[][];
  character_mappings?: Record<string, string>;
  effectiveness_score?: number;
  visual_similarity?: number;
  semantic_impact?: "low" | "medium" | "high";
  validated?: boolean;
  confidence?: number;
  deviation_score?: number;
  validation?: {
    model: string;
    response: string;
    gold: string;
    prompt_len: number;
    gpt5_validation?: {
      is_valid: boolean;
      confidence: number;
      deviation_score: number;
      reasoning: string;
      semantic_similarity: number;
      factual_accuracy: boolean;
      question_type_notes: string;
      model_used: string;
      threshold: number;
    };
  };
}

export interface QuestionManipulation {
  id: number;
  question_number: string;
  question_type: string;
  question_id?: string;
  original_text?: string;
  stem_text?: string; // Full question stem text from AI extraction
  options_data?: Record<string, unknown>;
  gold_answer?: string;
  gold_confidence?: number;
  marks?: number;
  answer_explanation?: string;
  has_image?: boolean;
  image_path?: string;
  manipulation_method?: string;
  effectiveness_score?: number;
  substring_mappings: SubstringMapping[];
  ai_model_results: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  // Additional fields that might be available
  positioning?: {
    page: number;
    bbox: number[];
    source: string;
  };
  confidence?: number;
}

export interface QuestionListResponse {
  run_id: string;
  total: number;
  questions: QuestionManipulation[];
}
