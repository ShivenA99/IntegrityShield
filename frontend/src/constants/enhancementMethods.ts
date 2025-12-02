export const KNOWN_ENHANCEMENT_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
  "pymupdf_overlay"
] as const;

export type EnhancementMethod = (typeof KNOWN_ENHANCEMENT_METHODS)[number];

// Internal labels (not displayed to users)
const INTERNAL_LABELS: Record<string, string> = {
  latex_dual_layer: "LaTeX Dual Layer",
  latex_font_attack: "LaTeX Font Attack",
  latex_icw: "ICW Watermark",
  latex_icw_dual_layer: "ICW + Dual Layer",
  latex_icw_font_attack: "ICW + Font Attack",
  pymupdf_overlay: "PyMuPDF Overlay"
};

// Prevention mode variant labels (alphabetical order by method name)
const PREVENTION_VARIANT_LABELS: Record<string, string> = {
  latex_font_attack: "Variant Prevention 2",
  latex_icw: "Variant Prevention 1",
  latex_icw_font_attack: "Variant Prevention 3",
};

// Detection mode variant labels (alphabetical order by method name)
const DETECTION_VARIANT_LABELS: Record<string, string> = {
  latex_dual_layer: "Variant Detection 1",
  latex_font_attack: "Variant Detection 2",
  latex_icw: "Variant Detection 3",
  latex_icw_dual_layer: "Variant Detection 4",
  latex_icw_font_attack: "Variant Detection 5",
  pymupdf_overlay: "Variant Detection 6"
};

/**
 * Get the display label for an enhancement method based on pipeline mode
 * @param method - The enhancement method name
 * @param mode - The pipeline mode ("prevention" or "detection")
 * @returns The variant label to display
 */
export function getMethodDisplayLabel(method: string, mode?: string): string {
  if (mode === "prevention" && method in PREVENTION_VARIANT_LABELS) {
    return PREVENTION_VARIANT_LABELS[method];
  }
  if (mode === "detection" && method in DETECTION_VARIANT_LABELS) {
    return DETECTION_VARIANT_LABELS[method];
  }
  // Fallback to internal label if mode unknown or method not mapped
  return INTERNAL_LABELS[method] || method;
}

// Public export for legacy compatibility - returns variant labels when possible
export const ENHANCEMENT_METHOD_LABELS: Record<string, string> = {
  ...PREVENTION_VARIANT_LABELS,
  ...DETECTION_VARIANT_LABELS
};

export const ENHANCEMENT_METHOD_SUMMARY: Record<string, string> = {
  latex_dual_layer: "Replace LaTeX tokens and overlay original spans for a dual-layer attack pipeline.",
  latex_font_attack: "Rebuilds the LaTeX with manipulated fonts so copied text reports the replacement answers.",
  latex_icw: "Inject hidden prompts into the LaTeX source to steer downstream LLMs toward selected answers.",
  latex_icw_dual_layer: "Combine hidden ICW prompts with the dual-layer overlay for both covert and visual manipulation.",
  latex_icw_font_attack: "Combine hidden ICW prompts with the font attack for covert instructions and mismatched copy text.",
  pymupdf_overlay: "Regenerate manipulated vector spans on top of the PDF using PyMuPDF.",
};
