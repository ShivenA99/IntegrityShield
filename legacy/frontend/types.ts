export enum AssessmentType {
  MCQ = 'Multiple Choice Question',
  FILL_IN_BLANKS = 'Fill in the Blanks',
  SHORT_ANSWER = 'Short Answer',
}

// New simplified attack modes for refactored architecture
export enum AttackMode {
  PREVENTION = 'Prevention',
  DETECTION = 'Detection'
}

// Prevention sub-types for internal strategy selection
export enum PreventionSubType {
  INVISIBLE_UNICODE = 'invisible_unicode',
  TINY_TEXT = 'tiny_text',
  ACTUALTEXT_OVERRIDE = 'actualtext_override'
}

// Attack configuration for API calls
export interface AttackConfig {
  mode: AttackMode;
  preventionSubType?: PreventionSubType;
}

// Backward compatibility - keep existing enum for migration
export enum AttackType {
  CODE_GLYPH = 'Code Glyph (Detection)',
  HIDDEN_MALICIOUS_INSTRUCTION_TOP = 'Hidden Malicious Instruction (Detection)',
  HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION = 'Hidden Malicious Instruction (Prevention)',
  NONE = 'No Attack (Baseline)'
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