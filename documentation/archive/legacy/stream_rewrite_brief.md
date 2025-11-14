# Stream Rewrite: Current State, Failures, and Open Questions

## 1. Goal Reminder
We need a method that, for every target substring found in the PDF content stream:

- replaces the glyphs associated with the target with a courier-style replacement whose width is scaled to fit the original footprint;
- leaves the surrounding text matrix untouched so that the suffix resumes exactly where it lived in the source stream;
- preserves the extraction order: prefix → replacement → suffix when text is copied or parsed;
- does not depend on negative kerning or other hacks that cause readers to reorder spans.

This must all happen while producing a clean `after_stream_rewrite.pdf` inside `stream_rewrite-overlay/`, and the final overlay PDF must look identical to the original except for the replaced strings.

## 2. What We Tried So Far

### 2.1 Original “Gap-Kerning” Courier Reconstruction (pre-Oct 2)
- **Mechanism:** Split the TJ array into three pieces (prefix TJ, replacement, suffix TJ). Insert the courier text with a custom font size and then restore the original font. Add a leading numeric element to the suffix array to compensate the width difference and rely on negative numbers for left shifts.
- **Outcome:** Copy/paste drifted because large negative kerning entries pushed the suffix tokens ahead of the replacement. Reader selection order became suffix → replacement → prefix. Visual layout stayed close but parsing was broken.

### 2.2 October 2 Attempt – Use `Td` to Reposition Suffix
- **Mechanism:** After courier `Tj`, restore the original font and issue a single `Td` translation equal to `original_width - replacement_width`. Then replay the suffix `TJ` elements and discard the leading numeric kerning values since the translation supposedly re-aligned the cursor.
- **Observed Regression (run `2fcb1740…` and `caa59671…`):**
  - Suffix spans sometimes jumped to column zero. The `Td` translation was applied while still inside the prefix/ courier text object sequence, and subsequent text matrix state (including previous `Td`s) combined with the new shift, causing huge offsets.
  - Many spans ended up rendered twice or in unexpected positions because the existing TJ array still contained inline numbers or implicit cursor moves we didn’t interpret.
  - Copy/paste still misordered text; some suffixes repeated at the start of the line due to the unexpected cursor resets.

### 2.3 Redaction Rewrite Overlay (PyMuPDF) Track
- **Mechanism:** Instead of editing the stream, redact the target area and draw the replacement on top using `page.insert_textbox`.
- **Problem:** Overlay text is independent from the content stream. Many PDF parsers emit overlay text at the end of the page contents, so extraction order becomes unpredictable. We want deterministic prefix → replacement → suffix order, which this approach cannot guarantee. It also introduces font and alignment issues because textboxes snap to bounding boxes rather than original baselines.

## 3. Current Diagnosis (Oct 2)
- The stream-based courier method now corrupts entire lines once `Td` interacts with existing transforms.
- Our suffix reconstruction still relies on the assumption that the original TJ array can be replayed verbatim after the `Td` shift; this breaks if the suffix spans include their own `Tj`/`Td`/`Tm` sequences or if the cursor state gets reset by earlier operations.
- We do not have a reliable way to compute the absolute matrix where the suffix should resume. We only track widths, not the actual transformation stack (e.g., nested `BT/ET` contexts, `Tm` operators, or preceding `Td`s).

## 4. Research Questions
1. **Matrix Tracking:** How do we accurately capture the active text matrix (full 6 numbers) at the start of the target substring and at the start of the suffix? Can we adopt PyPDF2’s matrix stack or parse content streams into an explicit state machine?
2. **Single `BT` Strategy:** Instead of continuing inside the same `BT`, should we `ET`, inject a new `BT`/`Tm` with explicit coordinates for the replacement, then open another `BT`/`Tm` for the suffix? Will this preserve selection order while isolating cursor math?
3. **In-Array Replacement:** Is it feasible to stay inside a single `TJ` array by editing the string contents directly (e.g., convert to text + decompress, adjust glyph codes) so we never touch kerning numbers at all? What are the risks when the array mixes text and numbers for kerning?
4. **Courier Glyph Encoding:** How do we ensure the courier string uses the same encoding as the original `TJ` entry (literal vs hexadecimal, escape sequences)? Are we losing glyphs because we emit text as standard strings while the original used hex or other encoding?
5. **Suffix Baselines:** Can we compute the suffix’s absolute baseline using the char bounding boxes from PyMuPDF and then re-create a minimal text display (e.g., `BT`/`Tm`/`Tj`) at those exact coordinates instead of reusing the original `TJ` fragments?
6. **Interaction with `TJ` Numbers:** When we remove leading numeric entries, are there cases where those numbers correspond to mid-word kerning we actually need? How to distinguish kerning for preceding prefix text vs kerning that belongs to the suffix itself?
7. **Alternative Replacement:** Should we consider editing the raw content stream tokens and reserializing the entire operator sequence from scratch, preserving all `T*` commands but swapping the literal string bytes? (This implies we need a reliable encoder/decoder that maintains the original `Tj` structure.)
8. **Redaction Overlay Issue:** If we must rely on overlay as a fallback, can we embed invisible replacement text with the correct `ActualText` tag or mark content to control extraction order? How do we guarantee readers respect it?

## 5. Next Steps
- Instrument the content-stream walker to capture full matrix state (`Tm`, `Td`, `T*`) at every token so we know exactly where the suffix should resume.
- Prototype a replacement sequence where we close the current text object, open a new `BT`, set the matrix exactly to the suffix’s baseline, and replay the suffix text as a fresh `Tj`. Compare extraction order before/after using PyMuPDF.
- Investigate the feasibility of editing the string literal in place (without array surgery) to avoid altering kerning numbers entirely.
- Document the influence of `ActualText` and marked-content sequences if overlay remains necessary.

This brief should guide a deeper refactor; the current code path needs a matrix-aware approach rather than incremental tweaks to the existing `TJ` array.
