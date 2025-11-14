export const KNOWN_ENHANCEMENT_METHODS = [
  "latex_dual_layer",
  "latex_font_attack",
  "latex_icw",
  "latex_icw_dual_layer",
  "latex_icw_font_attack",
  "pymupdf_overlay"
] as const;

export type EnhancementMethod = (typeof KNOWN_ENHANCEMENT_METHODS)[number];

export const ENHANCEMENT_METHOD_LABELS: Record<string, string> = {
  latex_dual_layer: "LaTeX Dual Layer",
  latex_font_attack: "LaTeX Font Attack",
  latex_icw: "ICW Watermark",
  latex_icw_dual_layer: "ICW + Dual Layer",
  latex_icw_font_attack: "ICW + Font Attack",
  pymupdf_overlay: "PyMuPDF Overlay"
};

export const ENHANCEMENT_METHOD_SUMMARY: Record<string, string> = {
  latex_dual_layer: "Replace LaTeX tokens and overlay original spans for a dual-layer attack pipeline.",
  latex_font_attack: "Rebuilds the LaTeX with manipulated fonts so copied text reports the replacement answers.",
  latex_icw: "Inject hidden prompts into the LaTeX source to steer downstream LLMs toward selected answers.",
  latex_icw_dual_layer: "Combine hidden ICW prompts with the dual-layer overlay for both covert and visual manipulation.",
  latex_icw_font_attack: "Combine hidden ICW prompts with the font attack for covert instructions and mismatched copy text.",
  pymupdf_overlay: "Regenerate manipulated vector spans on top of the PDF using PyMuPDF.",
};
