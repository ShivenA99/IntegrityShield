# Unified Question Schema (Fixed)

This document specifies the fixed schema every question must conform to after fusion. All fields are present for every question; when unknown, use null, empty list, or default values as specified.

Top-level array in `structured.json` → `questions: Question[]`.

## Question

```
Question {
  question_id: string,                    // UUIDv4 (stable per run)
  section_id: string | null,              // Link to parent section (see Section), null if none
  group_id: string | null,                // Grouping (e.g., multipart questions), null if none
  page_numbers: number[],                 // One or more pages where content appears
  reading_order: number,                  // Global reading order index across the document
  question_number: string,                // Visual label (e.g., "1", "1a", "Q2")
  question_type: "mcq_single" | "mcq_multi" | "true_false" | "short_answer" | "fill_blank" | "matching" | "ordering" | "matrix" | "numeric" | "hotspot" | "essay",
  language: string | null,                // ISO 639-1 (e.g., "en"); null if unknown
  script: string | null,                  // e.g., Latin, Cyrillic; null if unknown
  stem: RichTextSpan,                     // Required
  options: Option[],                      // For MCQ-like; empty otherwise
  true_false: {
    answer: boolean | null
  },
  short_answer: {
    expected_answer: string | null,
    keywords: string[]
  },
  fill_blank: {
    blanks: Blank[]                       // Each blank with local context
  },
  matching: {
    left: MatchingItem[],
    right: MatchingItem[],
    pairs: { left_id: string, right_id: string }[]
  },
  ordering: {
    items: OrderedItem[],
    correct_sequence: string[]            // Ordered list of item ids
  },
  matrix: {
    rows: MatrixAxisItem[],
    columns: MatrixAxisItem[],
    selections: { row_id: string, col_id: string }[]
  },
  numeric: {
    value: number | null,
    tolerance: number | null,
    units: string | null
  },
  hotspot: {
    image_ref: string | null,             // Asset path if any
    regions: Region[],
    answer_region_ids: string[]
  },
  references: ReferenceBlock[],           // Instructions, footnotes, figure/table captions linked to this question
  visual_elements: ("equation" | "table" | "diagram" | "image")[],
  media: MediaRef[],
  provenance: ProvenanceEntry[],          // Source confidence per field-level fusion (see notes)
  layout: LayoutContext,                  // Page-level layout context
  manipulation: ManipulationState,        // Filled by substitution/rendering stages
  render_hints: RenderHints,
  validation: Validation,
  raw_sources: RawSources                 // Original vendor/AST snippets used for fusion
}
```

## Sub-structures

```
RichTextSpan {
  text: string,                           // Canonical plain text
  latex: string | null,                   // If derived from equation regions
  bbox: BBox | null,                      // Union bounding box of content
  line_boxes: BBox[],                     // Line-level boxes in reading order
  fonts: FontRun[],                       // Font/style runs
  glyph_metrics: GlyphRun[] | null,       // Optional detailed metrics for precision overlays
  tokens: TokenSpan[] | null              // Optional tokenization map (char index spans)
}

Option {
  id: string,                             // Stable per question
  label: string | null,                   // "A"|"B"|... (null if not applicable)
  content: RichTextSpan,
  is_correct: boolean | null,
  rationale: RichTextSpan | null
}

Blank {
  index: number,
  prompt_fragment_before: string | null,
  prompt_fragment_after: string | null,
  answer: string | null,
  bbox: BBox | null,
  tolerance: number | null
}

MatchingItem {
  id: string,
  content: RichTextSpan
}

OrderedItem {
  id: string,
  content: RichTextSpan
}

MatrixAxisItem {
  id: string,
  content: RichTextSpan
}

Region {
  id: string,
  polygon: [number, number][],            // PDF points, page coordinate space
  page: number
}

ReferenceBlock {
  ref_type: "instruction" | "footnote" | "figure_caption" | "table_caption" | "sidebar" | "header" | "footer",
  content: RichTextSpan,
  anchors: { page: number, bbox: BBox }[] // Where found on page(s)
}

MediaRef {
  type: "image" | "table" | "equation" | "audio" | "video",
  page: number,
  bbox: BBox | null,
  ref: string | null                      // path or logical id e.g., assets/images/img-0.jpeg
}

ProvenanceEntry {
  source: "pymupdf" | "openai_vision" | "mistral_ocr" | "fusion",
  field: string,                          // e.g., "stem.text", "options[0].content.text"
  confidence: number,                     // 0..1
  notes: string | null
}

LayoutContext {
  page_size: { width_pt: number, height_pt: number, dpi: number | null },
  coordinate_space: "pdf_points",         // Always pdf_points internally
  regions: ("header" | "footer" | "main" | "sidebar")[],
  reading_adjacent_ids: string[]          // Neighbor question_ids by reading adjacency
}

ManipulationState {
  status: "unmodified" | "mapped" | "rendered",
  character_map_version: string | null,
  applied_mappings: { from: string, to: string, count: number }[],
  overlay_instructions: OverlayInstruction[]
}

OverlayInstruction {
  type: "invisible_text_overlay" | "glyph_substitution" | "image_overlay" | "content_stream_patch",
  page: number,
  bbox: BBox | null,
  font: { name: string, size: number } | null,
  opacity: number | null,
  payload: any | null                     // Method-specific details
}

RenderHints {
  dpi: number | null,
  page_width_px: number | null,
  page_height_px: number | null,
  color_space: "RGB" | "CMYK" | "Gray" | null,
  baseline_shift: number | null
}

Validation {
  consistency_checks: { check: string, pass: boolean, details?: string }[],
  warnings: string[],
  errors: string[]
}

RawSources {
  pymupdf: {
    blocks: { text: string, bbox: BBox, font: string | null, size: number | null }[]
  },
  openai_vision: {
    json: any | null,
    markdown_pages: { page: number, markdown: string }[] | null,
    model: string | null,
    cost_cents: number | null
  },
  mistral_ocr: {
    json: any | null,
    markdown_pages: { page: number, markdown: string }[] | null,
    model: string | null,
    cost_cents: number | null
  }
}

BBox = [x0: number, y0: number, x1: number, y1: number]

FontRun { name: string, size: number, weight?: string | number, italic?: boolean, color?: string | null }

GlyphRun {
  start_char: number,                     // index into `text`
  end_char: number,                       // exclusive
  page: number,
  baseline_y: number,
  ascent: number,
  descent: number,
  advances: number[],                     // per-glyph x-advance
  boxes: BBox[]                           // per-glyph bounding boxes
}

TokenSpan { start: number, end: number, token: string }
```

## Sections (optional, top-level)

```
Section {
  section_id: string,
  title: RichTextSpan | null,
  page_numbers: number[],
  bbox: BBox | null,
  instructions: ReferenceBlock[]
}
```

Store sections under `structured.sections: Section[]` to enable question-to-section linkage.

## Notes
- Always anchor text to AST (PyMuPDF) where possible; AI sources augment missing structure or type classification.
- Maintain page coordinate space in PDF points; record DPI and pixel sizes only as hints.
- Provenance should be added per-field during fusion to enable auditing and confidence-weighted merges. 