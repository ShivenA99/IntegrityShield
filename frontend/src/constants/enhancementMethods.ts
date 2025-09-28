export const DEFAULT_ENHANCEMENT_METHODS = [
  "content_stream_overlay",
  "pymupdf_overlay",
] as const;

export type EnhancementMethod = (typeof DEFAULT_ENHANCEMENT_METHODS)[number];

export const ENHANCEMENT_METHOD_LABELS: Record<EnhancementMethod, string> = {
  content_stream_overlay: "Stream Overlay",
  pymupdf_overlay: "Stream Rewrite",
};

export const ENHANCEMENT_METHOD_SUMMARY: Record<EnhancementMethod, string> = {
  content_stream_overlay: "Rewrite content streams and reapply captured overlays for fidelity.",
  pymupdf_overlay: "Redact glyphs, insert replacement text, and re-overlay visuals for clean selections.",
};
