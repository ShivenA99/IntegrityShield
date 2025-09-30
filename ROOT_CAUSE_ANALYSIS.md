# Root Cause Analysis: Spacing & Overlay Issues
## Run ID: 4bf3e702-6585-454a-add2-add388305ff1

**Date:** September 30, 2025
**Analyst:** Claude Code
**Severity:** HIGH - Visual artifacts in final PDF output

---

## Executive Summary

Analysis of run `4bf3e702-6585-454a-add2-add388305ff1` reveals **two critical spacing issues** in the Courier font injection strategy used for stream rewriting. These issues cause visible spacing gaps and text overlap in the final PDF when replacement text differs in length from the original text.

### Affected Questions:
- **Q3:** LSTM → CNN (4→3 chars): Extra spacing after replacement
- **Q5:** LSTMs → RNNs (5→4 chars): Extra spacing after replacement
- **Q7:** bidirectional → unidirectional (13→14 chars): Insufficient spacing, text cramping
- **Q8:** RNN → c (3→1 chars): Severe spacing issue causing prefix overlap

---

## Issue #1: Spacing Gaps in Q3, Q5, Q7

### Visual Symptoms
After Courier font injection, visible spacing gaps appear after the replacement text, making the PDF look unprofessional and potentially revealing the manipulation.

### Root Cause Location
**File:** `backend/app/services/pipeline/enhancement_methods/base_renderer.py`
**Method:** `_execute_precision_width_replacement`
**Lines:** 2458-2476 (calculation), 2538-2547 (application)

### Technical Analysis

#### Q3 Example: LSTM → CNN

**Original text:**
```
"What differentiates an LSTM cell from..."
```

**After replacement:**
```
"What differentiates an CNN  cell from..."  <-- Extra space!
```

#### Data Flow:

1. **Smart Substitution Stage** (structured.json):
   ```json
   {
     "original": "LSTM",
     "replacement": "CNN",
     "start_pos": 23,
     "end_pos": 27,
     "selection_bbox": [168.73, 290.78, 194.71, 299.74]
   }
   ```
   - Original "LSTM" occupies bbox width: 25.98 pts
   - Width per char: 6.49 pts

2. **Stream Rewrite Stage** (base_renderer.py:2458-2476):
   ```python
   # Step 2: Calculate spacing adjustment
   actual_replacement_width = self.calculate_text_width_courier(replacement_text, courier_font_size)
   width_difference = original_width - actual_replacement_width

   # For Q3:
   # original_width = 25.98 pts (LSTM in CMR9)
   # actual_replacement_width = ~18 pts (CNN in Courier @ 8pt)
   # width_difference = 25.98 - 18 = 7.98 pts

   spacing_adjustment = (width_difference * 1000) / courier_font_size
   # spacing_adjustment = (7.98 * 1000) / 8 = 997.5
   ```

3. **TJ Array Construction** (base_renderer.py:2538-2547):
   ```python
   suffix_elements = []

   # Add spacing adjustment BEFORE suffix text
   if abs(spacing_adjustment) > 0.1:
       suffix_elements.append(NumberObject(spacing_adjustment))

   if suffix_text:
       suffix_elements.append(TextStringObject(suffix_text))
   ```

#### The Bug

The spacing_adjustment IS calculated correctly and IS added to the suffix_elements array. However, there's a subtle but critical issue:

**The bug is NOT in the spacing calculation or application logic itself.**

Looking at the debug output from `after_reconstruction.json`:
```json
{
  "operations": [
    {"operator": "TJ", "operands": ["['Consider', -342, 'a', -343, 'v', 57, 'anilla', -342]"]},
    {"operator": "Tf", "operands": ["/Courier", "8"]},
    {"operator": "TJ", "operands": ["['c']"]},
    {"operator": "Tf", "operands": ["/F50", "8"]},
    {"operator": "TJ", "operands": ["[1699, -343, 'with', ...]"]}
  ]
}
```

**ROOT CAUSE:** The spacing adjustment (1699 in Q8's case) IS being added, but it's being added as a KERNING VALUE IN THE WRONG DIRECTION!

In PDF TJ operators:
- **Positive** numbers move the cursor **LEFT** (reduce spacing)
- **Negative** numbers move the cursor **RIGHT** (add spacing)

The current code adds `spacing_adjustment` as a positive number when `width_difference` is positive (replacement is narrower), which moves the cursor LEFT instead of keeping it in place!

### The Fix

**Line 2469 in base_renderer.py needs to be inverted:**

```python
# CURRENT (WRONG):
spacing_adjustment = (width_difference * 1000) / courier_font_size

# SHOULD BE:
spacing_adjustment = -(width_difference * 1000) / courier_font_size
```

The negative sign is crucial because:
- When `width_difference > 0` (replacement is narrower), we need to **add space** (negative value in TJ)
- When `width_difference < 0` (replacement is wider), we need to **reduce space** (positive value in TJ)

---

## Issue #2: Prefix Overlap in Q8

### Visual Symptoms
The replacement text "c" overlaps with the prefix text "vanilla", creating a visible rendering artifact.

### Root Cause
Same as Issue #1, but more severe due to the large length mismatch:

**Q8 Specific:**
```
Original: "RNN" (3 chars)
Replacement: "c" (1 char)
Width difference: ~20.61 - ~4.8 = ~15.81 pts
Spacing adjustment calculated: (15.81 * 1000) / 8 = 1976.25
```

With the current bug, this large positive value moves the cursor significantly LEFT, causing the suffix " with" to overlap with the prefix "vanilla".

---

## Impact Assessment

### Severity Matrix

| Question | Length Δ | Width Δ | Visual Impact | Severity |
|----------|----------|---------|---------------|----------|
| Q3       | -1 char  | ~8 pts  | Moderate gap  | MEDIUM   |
| Q5       | -1 char  | ~6 pts  | Small gap     | LOW      |
| Q7       | +1 char  | ~-4 pts | Slight cramp  | LOW      |
| Q8       | -2 chars | ~16 pts | OVERLAP       | HIGH     |

### User Impact
- **Detectability:** HIGH - Spacing issues are immediately visible
- **Trust:** Users may question the validity of manipulated PDFs
- **Usability:** Overlapping text is unreadable in Q8

---

## Verification Method

To verify the fix works:

1. Negate the spacing_adjustment calculation
2. Rerun the pipeline on the same input PDF
3. Check the `after_stream_rewrite.pdf` artifact
4. Verify no spacing gaps or overlaps in Q3, Q5, Q7, Q8

Expected result after fix:
```
Q3: "What differentiates an CNN cell from..." (no extra space)
Q5: "...in RNNs often initialized..." (no extra space)
Q7: "...Make it unidirectional? Justify..." (proper fit)
Q8: "Consider a vanilla c with recurrent..." (no overlap)
```

---

## Related Issues

### Why Overlay Doesn't Cover Some Questions

Based on logs:
```
ERROR [pdf_creation] dual-layer: pymupdf_overlay renderer failed
INFO [pdf_creation] ✓ Overlay applied: page 0 'bidirectional' → 'unidirectional'
...
```

The pymupdf_overlay renderer is failing because it's searching for the replacement text in the final PDF, but due to the spacing bug, the text isn't positioned where expected, causing the text search to fail.

**Expected fix:** Once spacing is corrected, pymupdf_overlay should succeed in finding and overlaying all targets.

---

## Code References

### Primary Bug Location
**File:** `backend/app/services/pipeline/enhancement_methods/base_renderer.py:2469`

```python
# BEFORE (BUG):
spacing_adjustment = (width_difference * 1000) / courier_font_size

# AFTER (FIX):
spacing_adjustment = -(width_difference * 1000) / courier_font_size
```

### Call Chain
1. `content_stream_renderer.py:47` → `rewrite_content_streams_structured()`
2. `base_renderer.py:1774` → `_rebuild_operations_with_courier_font()`
3. `base_renderer.py:2320` → `_process_tj_replacements()`
4. `base_renderer.py:2402` → `_execute_precision_width_replacement()`
5. **`base_renderer.py:2469`** → **BUG: Spacing calculation with wrong sign**

---

## Testing Requirements

### Unit Tests Needed
1. Test `_execute_precision_width_replacement` with various length mismatches
2. Verify spacing_adjustment sign is correct for both narrower and wider replacements
3. Test edge cases: single char replacements, multi-word replacements

### Integration Tests Needed
1. Full pipeline test with Quiz6.pdf
2. Verify visual output has no spacing artifacts
3. Verify overlay renderer succeeds for all questions

---

## Conclusion

The root cause is a **sign inversion bug** in the spacing adjustment calculation. The code correctly calculates the width difference and converts it to PDF text space units, but applies it with the wrong polarity, causing the cursor to move in the opposite direction of what's needed.

**One-line fix:** Negate the `spacing_adjustment` calculation in line 2469.

**Estimated effort:** 5 minutes to fix, 30 minutes to test and verify.

**Risk:** LOW - The fix is localized and well-understood.
