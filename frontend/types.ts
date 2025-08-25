export enum AssessmentType {
  MCQ = 'Multiple Choice Question',
  FILL_IN_BLANKS = 'Fill in the Blanks',
  SHORT_ANSWER = 'Short Answer',
}

export enum AttackType {
  NONE = 'No Attack (Baseline)',
  HIDDEN_MALICIOUS_INSTRUCTION_TOP = 'Hidden Malicious Instruction (Detection)',
  HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION = 'Hidden Malicious Instruction (Prevention)',
  CODE_GLYPH = 'Code Glyph (Detection)',
}

// This interface might be useful if you plan to parse structured grounding metadata
export interface GroundingSource {
  uri: string;
  title: string;
  text?: string; // Optional text snippet from the source
}

export interface AttackAnalysis {
  successRate: string;
  vulnerabilityAnalysis: string;
}