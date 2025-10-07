# Stream Rewrite Fix Plan: Surgical Span Reconstruction

## Executive Summary

**Problem**: Method 2 (Content Stream Rewrite) rewrites entire TJ/Tj operators, destroying original kerning/spacing and causing overlay misalignment.

**Solution**: Implement surgical, byte-level substring replacement within PDF content streams while preserving surrounding operator structure.

---

## 1. Root Cause Analysis

### Current Implementation Issues

The current `_rebuild_operations()` method in `base_renderer.py:1475-1540` has a fundamental flaw:

**IT REWRITES THE ENTIRE TJ/Tj OPERATOR** even when only a small substring needs replacement.

#### Why This Fails:

1. **Decoding Loss**: 
   - Original PDF bytes use font-specific character codes
   - Unicode decoding/re-encoding loses original glyph mappings
   - Custom fonts, ligatures, and special glyphs get mangled

2. **Kerning Destruction**:
   - System tries to preserve kerning via `kern_map`
   - Only captures explicit NumberObjects in TJ arrays
   - Misses implicit spacing from font metrics and glyph advances
   - Cannot preserve original micro-adjustments

3. **Complete Reconstruction**:
   - To replace "the"→"not" (3 chars), system rebuilds entire text operator
   - All surrounding text loses its original encoding
   - Spacing changes propagate throughout the line

### Evidence from Run 32edc5f7

**Q1**: "the" → "not" at position [8:11] in "What is the primary benefit..."
- **Input PDF**: Perfect spacing
- **after_stream_rewrite.pdf**: Shows "n o t" with broken spacing
- **final.pdf**: Overlay covers wrong area due to drift

**Q3**: "LSTM" → "CNN" shows similar char-level spacing issues

---

## 2. PDF Content Stream Structure (Deep Dive)

### TJ Operator Anatomy

A typical TJ operator with kerning:

```
[(W) -14 (hat is ) 3 (the) -18 ( primary)] TJ
```

**Components**:
- Text strings: `(W)`, `(hat is )`, `(the)`, `( primary)`
- Kerning values: `-14`, `3`, `-18` (in 1/1000 ems)
- Operator: `TJ` (show text with positioning)

### Current Processing Flow

1. **Extract** (`_extract_text_segments`):
   ```
   {
     "text": "What is the primary",
     "kern_map": {0: 0, 1: -14.0, 8: 3.0, 11: -18.0},
     "operator": b"TJ",
     ...
   }
   ```

2. **Match & Plan** (`_plan_replacements`):
   - Finds "the" at string positions [8:11]
   - Creates replacement plan with kerning adjustments

3. **Apply Edit** (`_apply_segment_edits`):
   - Modifies segment text: "What is the primary" → "What is not primary"
   - Adjusts kern_map positions after shift

4. **Rebuild** (`_rebuild_operations`) - **WHERE IT BREAKS**:
   ```python
   # Builds NEW array from scratch
   array = ArrayObject()
   array.append(TextStringObject("What is "))
   array.append(NumberObject(-14.0))
   array.append(TextStringObject("not primary"))
   # ^^^ LOST: Original byte encoding of all chars
   ```

### What Gets Lost:

- **Original byte sequences**: Font `/F1` might use `<57>` for 'W', but TextStringObject uses PDFDocEncoding
- **Glyph-specific kerning**: Font has built-in kerning pairs (e.g., "Wa" pair kern)
- **Subpixel positioning**: Original might have micro-adjustments we don't capture

---

## 3. Solution: Surgical Byte-Level Replacement

### Core Principle

**NEVER decode/re-encode more bytes than absolutely necessary.**

Instead of:
```
Original TJ array → Decode to Unicode → Modify → Re-encode → New TJ array
```

Do:
```
Original TJ array → Find target bytes → Replace bytes in-place → Keep rest intact
```

### Implementation Strategy

#### Phase 1: Byte-Level Targeting

New method: `_find_byte_range_in_tj_operator()`

```python
def _find_byte_range_in_tj_operator(
    self,
    tj_array: ArrayObject,
    target_unicode: str,
    context: Dict[str, object],
    font_cmaps: Dict[str, Dict[str, str]],
    current_font: Optional[str],
) -> Optional[Tuple[int, int, int, int]]:
    """
    Find exact byte range within a TJ array for replacement.
    
    Returns: (array_index, byte_offset_start, byte_offset_end, array_index_end)
    
    Example:
      TJ array: [(W) -14 (hat is ) 3 (the) -18 ( primary)]
      Target: "the"
      Returns: (3, 0, 3, 3)  # array[3] = "(the)", bytes [0:3]
    """
    # Decode TJ array while tracking byte positions
    decoded_parts = []
    for i, item in enumerate(tj_array):
        if isinstance(item, (TextStringObject, ByteStringObject)):
            raw_bytes = bytes(item)
            decoded = self._decode_with_cmap(raw_bytes, current_font, font_cmaps)
            decoded_parts.append({
                "array_idx": i,
                "raw_bytes": raw_bytes,
                "decoded": decoded,
                "byte_positions": list(range(len(raw_bytes))),
            })
    
    # Find target string in decoded text
    full_text = "".join(p["decoded"] for p in decoded_parts)
    match_idx = self._find_match_position_in_combined_text(
        full_text, target_unicode, context, []
    )
    if not match_idx:
        return None
    
    char_start, char_end = match_idx
    
    # Map character positions back to byte positions
    # ... (complex logic to handle multi-byte chars and array boundaries)
    
    return (array_idx_start, byte_start, byte_end, array_idx_end)
```

#### Phase 2: Surgical Replacement

New method: `_replace_bytes_in_tj_operator()`

```python
def _replace_bytes_in_tj_operator(
    self,
    original_array: ArrayObject,
    array_idx: int,
    byte_start: int,
    byte_end: int,
    replacement_unicode: str,
    font_cmaps: Dict[str, Dict[str, str]],
    current_font: Optional[str],
) -> ArrayObject:
    """
    Replace bytes within a TJ array, preserving everything else.
    
    This is the SURGICAL approach - only touch what needs to change.
    """
    # Clone the array
    new_array = ArrayObject(original_array)
    
    # Get the target ByteStringObject
    target_item = new_array[array_idx]
    original_bytes = bytes(target_item)
    
    # Encode replacement using same font encoding
    replacement_bytes = self._encode_like_original(
        replacement_unicode,
        original_bytes[byte_start:byte_end],
        font_cmaps,
        current_font
    )
    
    # Case 1: Replacement fits within single array element
    if array_idx == array_idx_end:
        new_bytes = (
            original_bytes[:byte_start] +
            replacement_bytes +
            original_bytes[byte_end:]
        )
        new_array[array_idx] = ByteStringObject(new_bytes)
        return new_array
    
    # Case 2: Spans multiple array elements (rare but handle it)
    # ... merge elements, replace bytes, potentially re-split
    
    return new_array
```

#### Phase 3: Minimal Kerning Adjustment

Only add kerning adjustments AROUND the replacement, not throughout:

```python
def _adjust_kerning_for_replacement(
    self,
    array: ArrayObject,
    array_idx: int,
    original_width: float,
    replacement_width: float,
    fontsize: float,
) -> ArrayObject:
    """
    Add minimal kerning adjustment AFTER the replaced bytes.
    
    Formula: adjustment_ts = (original_width - replacement_width) * 1000 / fontsize
    """
    if abs(original_width - replacement_width) < 0.1:
        return array  # No adjustment needed
    
    adjustment = (original_width - replacement_width) * 1000.0 / fontsize
    
    # Insert NumberObject AFTER the replacement
    new_array = ArrayObject()
    for i, item in enumerate(array):
        new_array.append(item)
        if i == array_idx:
            new_array.append(NumberObject(adjustment))
    
    return new_array
```

---

## 4. Comprehensive Implementation Plan

### Step 1: Add New Methods to BaseRenderer

**File**: `backend/app/services/pipeline/enhancement_methods/base_renderer.py`

**New Methods to Add**:

1. `_find_byte_range_in_tj_operator()` - Lines ~1856-1950
2. `_encode_like_original()` - Lines ~1951-2000  
3. `_replace_bytes_in_tj_operator()` - Lines ~2001-2100
4. `_adjust_kerning_for_replacement()` - Lines ~2101-2150
5. `_surgical_rebuild_operations()` - Lines ~2151-2300 (replacement for current `_rebuild_operations`)

### Step 2: Modify rewrite_content_streams_structured()

**Current flow**:
```python
segments = self._extract_text_segments(content, page)
replacements = self._plan_replacements(segments, ...)
self._apply_segment_edits(segments, replacements, ...)
content.operations = self._rebuild_operations(content.operations, segments)
```

**New flow**:
```python
# NEW: Work directly with operations, not decoded segments
font_cmaps = self._build_font_cmaps(page)
current_font = None

for op_index, (operands, operator) in enumerate(content.operations):
    if operator == b"Tf":
        current_font = str(operands[0])
        continue
    
    if operator in (b"TJ", b"Tj")and operator in (b"TJ", b"Tj"):
        # Check if this operator contains any of our target substrings
        for context in matched_contexts:
            target = context.get("original")
            replacement = context.get("replacement")
            
            byte_range = self._find_byte_range_in_tj_operator(
                operands[0] if operator == b"TJ" else operands,
                target,
                context,
                font_cmaps,
                current_font
            )
            
            if byte_range:
                # SURGICAL replacement
                new_array = self._replace_bytes_in_tj_operator(
                    operands[0],
                    *byte_range,
                    replacement,
                    font_cmaps,
                    current_font
                )
                
                # Minimal kerning adjustment if needed
                new_array = self._adjust_kerning_for_replacement(
                    new_array,
                    byte_range[0],
                    context.get("matched_width", 0),
                    context.get("replacement_width", 0),
                    context.get("matched_fontsize", 12)
                )
                
                # Replace the operation
                content.operations[op_index] = ([new_array], operator)
```

### Step 3: Testing and Validation

**Test Cases**:

1. **Simple ASCII replacement**: "the" → "not"
2. **Different lengths**: "LSTM" → "CNN" 
3. **Cross-boundary**: Target spans multiple TJ array elements
4. **Special fonts**: Custom embedded fonts with ToUnicode CMaps
5. **Kerning-heavy text**: Text with lots of spacing adjustments

**Success Criteria**:

1. `after_stream_rewrite.pdf` should have **identical spacing** to input PDF except for the replaced words
2. Overlays in `final.pdf` should cover **exactly** the replacement text, not neighboring words
3. Text selection should return the manipulated text cleanly
4. No extra spaces or character drift

---

## 5. Key Principles for Implementation

### ★ Insight: Why Surgical Approach Works

**Traditional approach**: 
- Decode entire operator → Unicode manipulation → Re-encode everything
- **Problem**: Loses all original font-specific byte encoding

**Surgical approach**:
- Keep 99% of original bytes intact
- Only touch the exact bytes that need replacement
- **Result**: Preserves spacing, kerning, and visual fidelity

### Critical Implementation Notes

1. **Font Encoding Preservation**:
   ```python
   # DON'T: Create new TextStringObject (uses PDF standard encoding)
   new_array.append(TextStringObject(replacement))
   
   # DO: Preserve original encoding method
   original_bytes = bytes(original_item)
   replacement_bytes = self._encode_like_original(replacement, original_bytes, font_cmaps, current_font)
   ```

2. **Minimal Kerning Changes**:
   - Only add kerning adjustment **after** the replacement
   - Don't rebuild kerning for the entire operator
   - Use precise font metrics when available

3. **Boundary Handling**:
   - Target text might span multiple array elements: `[(What is ) (the) ( primary)]`
   - Handle case where "the" is in separate element vs. "is the primary" in one element
   - Preserve existing NumberObject spacing between elements

### Error Handling Strategy

**Fallback Chain**:
1. **Try surgical replacement** (new approach)
2. **If surgical fails**: Fall back to current `_rebuild_operations` method  
3. **If both fail**: Copy original operator unchanged
4. **Log detailed diagnostics** for debugging

This ensures we never break existing functionality while improving what we can.

---

## 6. Implementation Priority

### Phase 1: Core Surgical Methods (Week 1)
- Add `_find_byte_range_in_tj_operator()`
- Add `_encode_like_original()`  
- Add `_replace_bytes_in_tj_operator()`

### Phase 2: Integration (Week 2)
- Modify `rewrite_content_streams_structured()` to use surgical approach
- Add comprehensive logging for debugging
- Implement fallback mechanism

### Phase 3: Testing & Refinement (Week 3)
- Test with run `32edc5f7` and similar cases
- Verify overlay alignment in final PDFs
- Performance optimization and edge case handling

---

## 7. Expected Results

After implementing this fix:

### Before (Current Broken Behavior):
```
Input:     "What is the primary benefit"
After:     "What is n o t primary benefit" (spacing broken)
Overlay:   Covers "t prima" (wrong area)
```

### After (Fixed Behavior):
```
Input:     "What is the primary benefit"  
After:     "What is not primary benefit" (spacing preserved)
Overlay:   Covers "not" (exact area)
```

### Validation Metrics:
1. **Visual Fidelity**: 99% of text should look identical to input PDF
2. **Overlay Precision**: Overlays should cover ±2px of target text only
3. **Text Extraction**: Copy/paste should return manipulated content
4. **Performance**: <10% slower than current method

---

## 8. Follow-up: Span Alignment & Overlay Readiness

We pivoted to the span overlay pipeline to stabilise visual output while inline surgery matures. To make span-level rewrites fully reliable we still need to:

1. **Normalise Offsets** – Map `substring_mappings` (which include human-readable spacing) onto the collapsed span text we use during planning. Use `SpanRecord.normalized_to_raw_indices` and persist `matched_glyph_path` hints so the planner always starts/ends on the intended glyphs.
2. **Allow Fragment Expansion** – Update `_map_replacement_to_text_fragments` and the span-plan collector so replacements can add new `TJ` fragments (with kerning numbers) instead of truncating neighbours. Capture the expanded fragment list in `SpanRewriteEntry.fragment_rewrites`.
3. **Verify End-to-End Runs** – Regenerate sample runs (`f6b51fa3-ae29-4058-a9ad-04ed1b2412a9`, `de3d91e8-2ed9-404c-9141-b8544414f2a2`) to confirm text extraction, overlays, and span diagnostics stay consistent after the alignment fixes.

These items feed directly into the comprehensive plan (Phase B/C) and should be completed before we consider the span pipeline production-ready.

---

## Conclusion

This surgical approach addresses the fundamental issue: **we were rebuilding entire operators when we only needed to replace tiny byte sequences**. By working at the byte level and preserving original font encoding, we maintain visual fidelity while achieving precise text replacement.

The key insight is that PDF content streams are designed for incremental modifications - we just need to respect that design instead of treating them as plain text that can be arbitrarily reconstructed.
