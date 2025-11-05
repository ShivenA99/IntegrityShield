export const DEFAULT_ENHANCEMENT_METHODS = [
  "latex_dual_layer",
] as const;

export type EnhancementMethod = (typeof DEFAULT_ENHANCEMENT_METHODS)[number];

export const ENHANCEMENT_METHOD_LABELS: Record<EnhancementMethod, string> = {
  latex_dual_layer: "LaTeX Dual Layer",
};

export const ENHANCEMENT_METHOD_SUMMARY: Record<EnhancementMethod, string> = {
  latex_dual_layer: "Replace LaTeX tokens and overlay original spans for a dual-layer attack pipeline.",
};
