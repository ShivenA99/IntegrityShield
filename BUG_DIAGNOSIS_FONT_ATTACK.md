# Bug Diagnosis: LaTeX Font Attack - Absolute vs Relative Search

## Problem Description

The `_locate_fragment` method in `latex_font_attack_service.py` uses **absolute search** to find target text in LaTeX files during font attack detection, instead of **relative search** within the known stem context.

## Location

**File**: `backend/app/services/pipeline/latex_font_attack_service.py`  
**Method**: `_locate_fragment` (lines 828-848)

## Current Implementation (Buggy)

```python
def _locate_fragment(
    self,
    tex_content: str,
    mapping: Dict[str, Any],
    original: str,
) -> Optional[Tuple[int, int]]:
    stem = mapping.get("latex_stem_text") or ""
    start_pos = mapping.get("start_pos")
    end_pos = mapping.get("end_pos")

    if stem and isinstance(start_pos, int) and isinstance(end_pos, int):
        stem_index = tex_content.find(stem)  # ❌ ABSOLUTE SEARCH - finds FIRST occurrence
        if stem_index != -1:
            local_segment = stem[start_pos:end_pos]
            if local_segment == original:
                return stem_index + start_pos, stem_index + end_pos  # ❌ Uses absolute position

    direct_index = tex_content.find(original)  # ❌ ABSOLUTE SEARCH fallback
    if direct_index != -1:
        return direct_index, direct_index + len(original)
    return None
```

## The Bug

### Issue 1: Absolute Search Finds Wrong Occurrence

**Problem**: `tex_content.find(stem)` searches the **entire document** and returns the **first occurrence** of the stem text.

**Why this is wrong**:
- If the same question stem appears multiple times in the document, it will always find the first one
- If previous replacements have modified the document, the stem might appear in a different location
- The `start_pos` and `end_pos` are **relative to the stem**, but we're applying them to the wrong stem occurrence

### Issue 2: No Context-Aware Search

**Problem**: The method doesn't know which question/segment it's working on, so it can't search within the correct context.

**Why this matters**:
- Mappings are generated per-question with positions relative to that question's stem
- But the search doesn't restrict itself to that question's context
- This can cause mismatches when multiple questions have similar stems

### Issue 3: Fallback Also Uses Absolute Search

**Problem**: The fallback `tex_content.find(original)` also searches the entire document absolutely.

**Why this is wrong**:
- If the original substring appears multiple times, it finds the first occurrence
- This might not be the correct occurrence for the current mapping

## Expected Behavior

The method should:
1. **Search relatively** within the known stem context
2. **Track which occurrence** of the stem to use (if stems appear multiple times)
3. **Handle modified documents** where previous replacements may have changed positions
4. **Use context information** from the mapping to narrow the search scope

## Suggested Fix

### Option 1: Search Within Question Context (Recommended)

Use the question number or sequence index to narrow the search scope:

```python
def _locate_fragment(
    self,
    tex_content: str,
    mapping: Dict[str, Any],
    original: str,
    question_context: Optional[Dict[str, Any]] = None,  # NEW: Add context
) -> Optional[Tuple[int, int]]:
    stem = mapping.get("latex_stem_text") or ""
    start_pos = mapping.get("start_pos")
    end_pos = mapping.get("end_pos")
    question_number = mapping.get("question_number") or question_context.get("question_number")

    if stem and isinstance(start_pos, int) and isinstance(end_pos, int):
        # Search for stem within question context (if available)
        search_start = 0
        search_end = len(tex_content)
        
        # If we have question context, try to narrow search scope
        if question_context:
            # Try to find question markers (e.g., \item, \question, etc.)
            # This would require additional logic to identify question boundaries
            pass
        
        # Search for stem starting from search_start
        stem_index = tex_content.find(stem, search_start, search_end)
        
        # If found, verify it's the correct occurrence
        if stem_index != -1:
            # Verify the segment at relative positions matches original
            local_segment = stem[start_pos:end_pos]
            if local_segment == original:
                # Verify the actual text in tex_content matches
                absolute_start = stem_index + start_pos
                absolute_end = stem_index + end_pos
                if absolute_end <= len(tex_content):
                    actual_segment = tex_content[absolute_start:absolute_end]
                    if actual_segment == original:
                        return absolute_start, absolute_end
        
        # If first occurrence doesn't match, try next occurrences
        search_pos = stem_index + 1 if stem_index != -1 else 0
        while search_pos < len(tex_content):
            stem_index = tex_content.find(stem, search_pos)
            if stem_index == -1:
                break
            absolute_start = stem_index + start_pos
            absolute_end = stem_index + end_pos
            if absolute_end <= len(tex_content):
                actual_segment = tex_content[absolute_start:absolute_end]
                if actual_segment == original:
                    return absolute_start, absolute_end
            search_pos = stem_index + 1

    # Fallback: search for original within a limited scope
    # (not shown here, but should also be relative)
    return None
```

### Option 2: Use Occurrence Index

Track which occurrence of the stem to use:

```python
def _locate_fragment(
    self,
    tex_content: str,
    mapping: Dict[str, Any],
    original: str,
) -> Optional[Tuple[int, int]]:
    stem = mapping.get("latex_stem_text") or ""
    start_pos = mapping.get("start_pos")
    end_pos = mapping.get("end_pos")
    occurrence_index = mapping.get("stem_occurrence_index", 0)  # NEW: Which occurrence to use

    if stem and isinstance(start_pos, int) and isinstance(end_pos, int):
        # Find the Nth occurrence of the stem
        search_pos = 0
        for i in range(occurrence_index + 1):
            stem_index = tex_content.find(stem, search_pos)
            if stem_index == -1:
                break
            if i == occurrence_index:
                # This is the occurrence we want
                local_segment = stem[start_pos:end_pos]
                if local_segment == original:
                    absolute_start = stem_index + start_pos
                    absolute_end = stem_index + end_pos
                    # Verify actual text matches
                    if absolute_end <= len(tex_content):
                        actual_segment = tex_content[absolute_start:absolute_end]
                        if actual_segment == original:
                            return absolute_start, absolute_end
            search_pos = stem_index + 1

    # Fallback with relative search
    return None
```

### Option 3: Search Within Known Segment (Best for Current Architecture)

Since mappings are processed per-question, search within the question's segment:

```python
def _locate_fragment(
    self,
    tex_content: str,
    mapping: Dict[str, Any],
    original: str,
    segment_start: Optional[int] = None,  # NEW: Start of question segment
    segment_end: Optional[int] = None,   # NEW: End of question segment
) -> Optional[Tuple[int, int]]:
    stem = mapping.get("latex_stem_text") or ""
    start_pos = mapping.get("start_pos")
    end_pos = mapping.get("end_pos")

    if stem and isinstance(start_pos, int) and isinstance(end_pos, int):
        # Search RELATIVELY within the segment
        if segment_start is not None and segment_end is not None:
            segment_text = tex_content[segment_start:segment_end]
            relative_stem_index = segment_text.find(stem)
            if relative_stem_index != -1:
                # Convert relative position to absolute
                absolute_stem_index = segment_start + relative_stem_index
                local_segment = stem[start_pos:end_pos]
                if local_segment == original:
                    absolute_start = absolute_stem_index + start_pos
                    absolute_end = absolute_stem_index + end_pos
                    # Verify bounds and content
                    if absolute_end <= len(tex_content):
                        actual_segment = tex_content[absolute_start:absolute_end]
                        if actual_segment == original:
                            return absolute_start, absolute_end
        
        # Fallback: search entire document (current behavior)
        stem_index = tex_content.find(stem)
        if stem_index != -1:
            local_segment = stem[start_pos:end_pos]
            if local_segment == original:
                absolute_start = stem_index + start_pos
                absolute_end = stem_index + end_pos
                if absolute_end <= len(tex_content):
                    actual_segment = tex_content[absolute_start:absolute_end]
                    if actual_segment == original:
                        return absolute_start, absolute_end

    # Fallback: search for original within segment (if available)
    if segment_start is not None and segment_end is not None:
        segment_text = tex_content[segment_start:segment_end]
        relative_index = segment_text.find(original)
        if relative_index != -1:
            return segment_start + relative_index, segment_start + relative_index + len(original)
    
    # Last resort: absolute search (current fallback)
    direct_index = tex_content.find(original)
    if direct_index != -1:
        return direct_index, direct_index + len(original)
    return None
```

## ✅ Solution: Use the Dual Layer Service Pattern

**The dual layer service already solves this correctly!** Here's how:

### Dual Layer Service (CORRECT Implementation)

1. **Segments the document by question** (line 903: `_build_question_segments`)
2. **Processes each question in its segment** (line 921-930: iterates over segments)
3. **Searches within the segment** (line 1002: `_locate_substring_by_position(tex_content=updated_segment, ...)`)
   - `updated_segment` is the segment text for that specific question, NOT the full document
4. **Converts local to absolute positions** (line 1030-1031: `absolute_start = segment_start + local_start`)

**Key Code**:
```python
# latex_dual_layer_service.py line 1002-1009
local_match = self._locate_substring_by_position(
    tex_content=updated_segment,  # ✅ Segment, not full text!
    latex_stem_text=latex_stem_text,
    original=original_raw,
    start_pos=start_pos,
    end_pos=end_pos,
    occupied=occupied
)
```

When `_locate_substring_by_position` does `tex_content.find(latex_stem_text)` at line 1272, it's searching **within the segment**, not the entire document!

### Font Attack Service (BUGGY Implementation)

1. **Processes all questions against full document** (line 370: `_apply_font_attack`)
2. **Searches entire document** (line 400: `_locate_fragment(tex_content, mapping, original)`)
   - `tex_content` is the **full document**, not a segment
3. **Uses absolute search** (line 839: `tex_content.find(stem)` searches entire document)

## Recommended Fix

**Adopt the dual layer service's segment-based approach:**

1. **Add segment building** (like `_build_question_segments` in dual layer)
2. **Process questions within their segments** (like `_apply_mappings_for_segment`)
3. **Pass segment text to `_locate_fragment`** instead of full `tex_content`
4. **Convert local positions to absolute** (like `absolute_start = segment_start + local_start`)

This is the **proven pattern** that already works correctly in the dual layer service.

## Implementation Steps

1. **Identify where `_locate_fragment` is called** (line 400 in `_apply_detection_font_attack`)
2. **Determine if segment boundaries are available** in the calling context
3. **Modify the method signature** to accept optional segment boundaries
4. **Update the search logic** to use relative search within the segment
5. **Add verification** to ensure the found text actually matches
6. **Update the fallback** to also search relatively when possible

## Testing Considerations

After fixing, test with:
- Documents where the same stem appears multiple times
- Documents with multiple questions
- Documents where previous replacements have modified positions
- Edge cases where stem is at document boundaries

## Related Code

- `latex_dual_layer_service.py` has a similar method `_locate_substring_by_position` (lines 1249-1321) that may have the same issue
- Both methods should be updated consistently

