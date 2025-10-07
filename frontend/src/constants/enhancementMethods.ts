export const DEFAULT_ENHANCEMENT_METHODS = [
  "content_stream_span_overlay",
] as const;

export type EnhancementMethod = (typeof DEFAULT_ENHANCEMENT_METHODS)[number];

export const ENHANCEMENT_METHOD_LABELS: Record<EnhancementMethod, string> = {
  content_stream_span_overlay: "Stream Rewrite",
};

export const ENHANCEMENT_METHOD_SUMMARY: Record<EnhancementMethod, string> = {
  content_stream_span_overlay: "Rewrite text with deterministic span overlays for perfect visual fidelity.",
};
