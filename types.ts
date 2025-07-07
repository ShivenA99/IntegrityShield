export enum AssessmentType {
  MCQ = 'Multiple Choice Question',
  FILL_IN_BLANKS = 'Fill in the Blanks',
  SHORT_ANSWER = 'Short Answer',
}

export enum AttackType {
  NONE = 'No Attack (Baseline)',
  ZERO_WIDTH_SPACES_OBFUSCATION = 'Zero-Width Spaces (Obfuscation)',
  HIDDEN_MALICIOUS_INSTRUCTION_TOP = 'Hidden Malicious Instruction (Prepended)',
  HIDDEN_MALICIOUS_INSTRUCTION_BOTTOM = 'Hidden Malicious Instruction (Appended)',
  RANDOM_INVISIBLE_CHARS = 'Random Invisible Characters',
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