# Prevention Font Library Integration Guide

## Integration Points

### 1. Import the Library

Add to `app/services/pipeline/latex_font_attack_service.py`:

```python
from app.services.pipeline.font_attack.prevention_font_library import (
    get_prevention_font_library,
    PreventionFontLibrary
)
```

### 2. Modify `_apply_prevention_font_attack` Method

**CURRENT CODE** (lines 503-575):
```python
# OLD APPROACH: Create character variant mapping
MAX_VARIANTS = 5
char_variant_map: Dict[str, List[str]] = {}
for char in available_chars:
    random.seed(ord(char))
    other_chars = [c for c in available_chars if c != char]
    random.shuffle(other_chars)
    char_variant_map[char] = other_chars[:MAX_VARIANTS]
random.seed()

# ... later in loop ...
if char not in char_variant_map:
    char_offset += 1
    continue
variants = char_variant_map[char]
random_replacement = variants[counter % len(variants)]

# Plan font attack
plan = planner.plan(random_replacement, char)  # hidden=random, visual=char
```

**NEW CODE** (with library):
```python
# NEW APPROACH: Use pre-generated font library
library = get_prevention_font_library()

if not library.is_loaded():
    # Fallback to old approach or raise error
    raise RuntimeError(
        "Prevention font library not loaded. "
        "Run: python backend/scripts/generate_prevention_font_library.py"
    )

UNIVERSAL_HIDDEN_CHAR = library.get_hidden_char()  # Always 'a'

# ... later in loop ...
# Check if library has a font for this visual character
font_path = library.get_font_for_char(char)
if font_path is None:
    # Character not in library, skip
    diagnostics.append(MappingDiagnostic(
        mapping_id=None,
        question_number=question_number,
        status="char_not_in_library",
        original=char,
        replacement="",
        notes=f"No pre-generated font for character: {char}"
    ))
    char_offset += 1
    continue

# Plan font attack using universal hidden character
# Hidden layer: 'a' (universal)
# Visual layer: original character
plan = planner.plan(UNIVERSAL_HIDDEN_CHAR, char)  # hidden='a', visual=char
```

### 3. Use Pre-generated Fonts Instead of Building

**CURRENT CODE** (in font building section):
```python
# Builds fonts at runtime using FontBuilder
build_results = builder.build_fonts(plan, fonts_dir, cache_lookup=cache)
```

**NEW CODE** (copy from library):
```python
# Copy pre-generated font from library instead of building
from shutil import copy2

build_results = []
for position in plan:
    if not position.requires_font:
        continue

    # Get pre-generated font from library
    font_path_in_library = library.get_font_for_char(position.visual_text)

    if font_path_in_library is None:
        # Fallback: build at runtime
        # (or raise error if you want strict library-only mode)
        runtime_results = builder.build_fonts([position], fonts_dir, cache_lookup=cache)
        build_results.extend(runtime_results)
        continue

    # Copy from library to runtime fonts directory
    target_font_path = fonts_dir / f"attack_pos{position.index}.ttf"
    copy2(font_path_in_library, target_font_path)

    build_results.append(FontBuildResult(
        index=position.index,
        hidden_char=position.hidden_char,
        visual_text=position.visual_text,
        font_path=target_font_path,
        used_cache=True  # Technically library, but similar to cache
    ))
```

## Complete Modified Method

Here's the complete refactored `_apply_prevention_font_attack` method:

```python
def _apply_prevention_font_attack(
    self,
    tex_content: str,
    structured: Dict[str, Any],
    planner: ChunkPlanner,
    builder: FontAttackBuilder,
    fonts_dir: Path,
    cache: FontCache,
) -> Tuple[str, Sequence[AttackJob], Sequence[MappingDiagnostic]]:
    """
    Prevention mode: Use pre-generated font library for instant font application.
    All characters use universal hidden character 'a' with pre-generated visual mappings.
    """
    # Load prevention font library
    library = get_prevention_font_library()

    if not library.is_loaded():
        raise RuntimeError(
            "Prevention font library not loaded. "
            "Run: python backend/scripts/generate_prevention_font_library.py"
        )

    # Log library stats
    stats = library.get_library_stats()
    print(f"Using prevention font library: {stats['total_fonts']} pre-generated fonts")

    UNIVERSAL_HIDDEN_CHAR = library.get_hidden_char()  # Always 'a'

    self._font_command_registry: Dict[str, set[str]] = {}
    replacements: List[Tuple[int, int, str, AttackJob]] = []
    occupied_ranges: List[Tuple[int, int, Optional[str]]] = []
    diagnostics: List[MappingDiagnostic] = []
    attack_jobs: List[AttackJob] = []
    counter = 0

    # Get all question stems from structured data
    ai_questions = structured.get("ai_questions", [])

    for question in ai_questions:
        stem_text = question.get("stem_text", "")
        if not stem_text:
            continue

        question_number = str(question.get("question_number") or question.get("q_number") or "")

        # Find the stem in the LaTeX
        stem_index = tex_content.find(stem_text)
        if stem_index == -1:
            diagnostics.append(MappingDiagnostic(
                mapping_id=None,
                question_number=question_number,
                status="stem_not_found",
                original=stem_text[:50],
                replacement="",
                notes=f"Stem text not found in LaTeX for Q{question_number}"
            ))
            continue

        # Process each alphanumeric character in the stem
        char_offset = 0
        for i, char in enumerate(stem_text):
            if not char.isalnum():
                char_offset += 1
                continue

            # Check if library has a font for this visual character
            font_path_in_library = library.get_font_for_char(char)
            if font_path_in_library is None:
                diagnostics.append(MappingDiagnostic(
                    mapping_id=None,
                    question_number=question_number,
                    status="char_not_in_library",
                    original=char,
                    replacement="",
                    notes=f"No pre-generated font for character: {char}"
                ))
                char_offset += 1
                continue

            char_start = stem_index + i
            char_end = char_start + 1

            # Check for overlaps
            overlap = self._find_range_overlap(occupied_ranges, char_start, char_end)
            if overlap:
                char_offset += 1
                continue

            try:
                # Plan font attack using universal hidden character
                # Hidden: 'a' (universal), Visual: original character
                plan = planner.plan(UNIVERSAL_HIDDEN_CHAR, char)
            except (KeyError, ValueError) as exc:
                diagnostics.append(MappingDiagnostic(
                    mapping_id=None,
                    question_number=question_number,
                    status="planning_failed",
                    original=char,
                    replacement=UNIVERSAL_HIDDEN_CHAR,
                    location=(char_start, char_end),
                    notes=str(exc)
                ))
                char_offset += 1
                continue

            # Copy pre-generated fonts from library (INSTANT - no build time!)
            from shutil import copy2
            build_results = []

            for position in plan:
                if not position.requires_font:
                    continue

                # Copy from library to runtime fonts directory
                target_font_path = fonts_dir / f"attack_pos{counter}.ttf"
                copy2(font_path_in_library, target_font_path)

                build_results.append(FontBuildResult(
                    index=position.index,
                    hidden_char=position.hidden_char,
                    visual_text=position.visual_text,
                    font_path=target_font_path,
                    used_cache=True  # Library reuse
                ))

            # Register font commands and create attack job
            font_cmds = self._register_fonts(build_results)

            if not font_cmds:
                char_offset += 1
                continue

            # Build replacement LaTeX with font command
            font_cmd = font_cmds[0]
            replacement = f"{{\\{font_cmd} {UNIVERSAL_HIDDEN_CHAR}}}"

            replacements.append((char_start, char_end, replacement, None))
            occupied_ranges.append((char_start, char_end, f"prevention_char_{counter}"))

            # Create attack job
            job = AttackJob(
                mapping_id=f"prevention_char_{counter}",
                question_number=question_number,
                original=char,
                replacement=UNIVERSAL_HIDDEN_CHAR,
                visual_rendering=char,
                location=(char_start, char_end),
                font_commands=font_cmds,
                attack_type="prevention"
            )
            attack_jobs.append(job)

            counter += 1

    # Apply all replacements
    mutated_tex = self._apply_replacements(tex_content, replacements)

    return mutated_tex, attack_jobs, diagnostics
```

## Benefits of This Approach

### Performance Gains:
- **Font Generation Time**: 0 seconds (vs. 5-10 minutes)
- **Font Count**: ~100 total (vs. 1,000+)
- **Cache Hit Rate**: 100% (all fonts pre-generated)
- **Memory**: Minimal (just file copies)
- **Disk Space**: ~10-20 MB for entire library

### Operational Benefits:
- **Consistency**: Same fonts used across all runs
- **Predictability**: Known font set, no runtime variability
- **Debugging**: Easy to inspect/verify library
- **Distribution**: Can ship library with code
- **Testing**: Fast, deterministic behavior

## Migration Steps

1. **Generate Library** (one-time):
   ```bash
   cd backend
   .venv/bin/python scripts/generate_prevention_font_library.py
   ```

2. **Verify Library**:
   ```bash
   .venv/bin/python -c "
   from app.services.pipeline.font_attack.prevention_font_library import get_prevention_font_library
   lib = get_prevention_font_library()
   print('Loaded:', lib.is_loaded())
   print('Stats:', lib.get_library_stats())
   print('Verification:', lib.verify_library())
   "
   ```

3. **Update Service**:
   - Add imports to `latex_font_attack_service.py`
   - Replace `_apply_prevention_font_attack` method with new version

4. **Test**:
   ```bash
   .venv/bin/python test_prevention_flow.py
   ```

Expected result: Prevention mode completes in ~2-3 minutes instead of 10-15 minutes!
