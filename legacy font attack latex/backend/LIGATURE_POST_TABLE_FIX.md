# Complete Solution: Ligature Glyph Names and the post Table

## The Problem

When creating a ligature glyph in a TrueType font using fontTools:

1. You create a glyph named `lig_world`
2. You add it to `glyf`, `hmtx`, and glyph order
3. You call `addOpenTypeFeatures()` - it works!
4. You save the font
5. **Result**: Glyph is renamed to `glyph01322`, your custom name is lost

## Why This Happens

The **post table** (PostScript information) stores glyph names in TrueType fonts. When fontTools saves a font:

1. It checks if each glyph name exists in the `post` table
2. If the name is missing, it generates a generic name like `glyph####`
3. All tables (including GSUB) are updated with the new name
4. Your custom ligature name disappears

## The Fix

**Update the `post` table before saving:**

```python
if 'post' in font:
    font['post'].glyphOrder = font.getGlyphOrder()
```

## Complete Working Example

```python
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools import ttLib
from fontTools.ttLib.tables import _g_l_y_f as glyf
import tempfile
import os

def create_ligature_font(base_font_path, visual_word, hidden_word, output_path):
    """
    Create a font with a ligature that displays visual_word when typing hidden_word.

    Args:
        base_font_path: Path to base TrueType font
        visual_word: Word to display (e.g., "hello")
        hidden_word: Word to type (e.g., "world")
        output_path: Path to save the modified font
    """
    # Load font
    font = TTFont(base_font_path)

    # Get tables
    glyf_table = font['glyf']
    hmtx_table = font['hmtx']
    cmap = font.getBestCmap()

    # Create ligature name
    lig_name = f"lig_{hidden_word.replace(' ', '_')}"

    print(f"Creating ligature: {lig_name}")

    # STEP 1: Create ligature glyph by combining visual word glyphs
    all_coordinates = []
    all_flags = []
    all_endPtsOfContours = []
    x_offset = 0
    total_width = 0
    current_point_index = 0

    for visual_char in visual_word:
        visual_glyph_name = cmap.get(ord(visual_char))
        if not visual_glyph_name:
            raise ValueError(f"Character '{visual_char}' not in font")

        source_glyph = glyf_table[visual_glyph_name]
        width = hmtx_table.metrics[visual_glyph_name][0]

        # Only process simple glyphs (not composite)
        if source_glyph.numberOfContours > 0:
            coordinates = source_glyph.coordinates
            flags = source_glyph.flags
            endPtsOfContours = source_glyph.endPtsOfContours

            # Transform coordinates by x_offset
            for coord in coordinates:
                all_coordinates.append((coord[0] + x_offset, coord[1]))

            all_flags.extend(flags)

            # Update endPtsOfContours indices
            for endPt in endPtsOfContours:
                all_endPtsOfContours.append(endPt + current_point_index)

            current_point_index += len(coordinates)

        x_offset += width
        total_width += width

    # Create the new glyph
    new_glyph = glyf.Glyph()
    new_glyph.numberOfContours = len(all_endPtsOfContours)

    if new_glyph.numberOfContours > 0:
        new_glyph.coordinates = ttLib.tables._g_l_y_f.GlyphCoordinates(all_coordinates)
        new_glyph.flags = all_flags
        new_glyph.endPtsOfContours = all_endPtsOfContours
        new_glyph.program = ttLib.tables._g_l_y_f.ttProgram.Program()
        new_glyph.program.fromBytecode(b'')

    # STEP 2: Add to glyf table
    glyf_table[lig_name] = new_glyph
    print(f"  Added to glyf table: {lig_name}")

    # STEP 3: Add metrics
    hmtx_table.metrics[lig_name] = (total_width, 0)
    print(f"  Added to hmtx table: width={total_width}")

    # STEP 4: Update glyph order
    glyph_order = list(font.getGlyphOrder())
    if lig_name not in glyph_order:
        glyph_order.append(lig_name)
        font.setGlyphOrder(glyph_order)
        print(f"  Updated glyph order: {len(glyph_order)} glyphs")

    # STEP 5: *** CRITICAL FIX *** Update post table
    if 'post' in font:
        font['post'].glyphOrder = font.getGlyphOrder()
        print(f"  ✓ Updated post table with new glyph order")
    else:
        print(f"  ⚠ Warning: No post table in font")

    # STEP 6: Create OpenType feature
    hidden_glyphs = [cmap.get(ord(c)) for c in hidden_word if ord(c) in cmap]

    fea_code = f"""languagesystem DFLT dflt;
languagesystem latn dflt;

feature liga {{
    sub {' '.join(hidden_glyphs)} by {lig_name};
}} liga;
"""

    print(f"\n  Feature code:")
    for line in fea_code.strip().split('\n'):
        print(f"    {line}")

    # STEP 7: Add the feature
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fea', delete=False) as fea_file:
        fea_file.write(fea_code)
        fea_path = fea_file.name

    try:
        addOpenTypeFeatures(font, fea_path)
        print(f"\n  ✓ Added OpenType liga feature")
    finally:
        os.unlink(fea_path)

    # STEP 8: Save
    font.save(output_path)
    font.close()

    print(f"\n✓ Created ligature font: {output_path}")

    # STEP 9: Verify
    print(f"\nVerifying saved font...")
    verify_font = TTFont(output_path)

    if lig_name in verify_font['glyf']:
        print(f"  ✓ Glyph '{lig_name}' PRESERVED in saved font")
        glyph = verify_font['glyf'][lig_name]
        width = verify_font['hmtx'].metrics[lig_name][0]
        print(f"    Contours: {glyph.numberOfContours}")
        print(f"    Width: {width}")
    else:
        # Check if it was renamed
        print(f"  ✗ Glyph '{lig_name}' NOT found")
        print(f"  Checking for renamed glyphs...")

        if 'GSUB' in verify_font:
            gsub = verify_font['GSUB']
            for feature_record in gsub.table.FeatureList.FeatureRecord:
                if feature_record.FeatureTag == 'liga':
                    feature = feature_record.Feature
                    for lookup_index in feature.LookupListIndex:
                        lookup = gsub.table.LookupList.Lookup[lookup_index]
                        for subtable in lookup.SubTable:
                            if hasattr(subtable, 'ligatures'):
                                for first_glyph, lig_set in subtable.ligatures.items():
                                    for lig in lig_set:
                                        print(f"  Found ligature: {lig.LigGlyph}")
                                        print(f"    → This should have been '{lig_name}'")

    verify_font.close()

# Usage
if __name__ == "__main__":
    create_ligature_font(
        base_font_path="fonts/Roboto.ttf",
        visual_word="hello",
        hidden_word="world",
        output_path="output_ligature_fixed.ttf"
    )
```

## Key Points

### 1. The Order Matters

Always follow this exact sequence:

```python
# 1. Add glyph to glyf table
font['glyf'][lig_name] = new_glyph

# 2. Add metrics to hmtx table
font['hmtx'].metrics[lig_name] = (width, 0)

# 3. Update glyph order
glyph_order = list(font.getGlyphOrder())
glyph_order.append(lig_name)
font.setGlyphOrder(glyph_order)

# 4. *** CRITICAL *** Update post table
if 'post' in font:
    font['post'].glyphOrder = font.getGlyphOrder()

# 5. Add OpenType features
addOpenTypeFeatures(font, feature_file_path)

# 6. Save
font.save(output_path)
```

### 2. Understanding the post Table

The post table has different formats:

- **Format 1.0**: Uses standard Mac glyph names only (258 glyphs)
- **Format 2.0**: Stores custom glyph names (most common for fonts with > 258 glyphs)
- **Format 3.0**: No glyph names stored (generates names on the fly)

When you set `post.glyphOrder`, fontTools automatically:
1. Updates the format to 2.0 if needed
2. Stores your custom glyph names
3. Preserves them during save

### 3. Common Mistakes

❌ **Don't do this:**
```python
# Adding glyph but forgetting to update post table
font['glyf'][lig_name] = new_glyph
font.setGlyphOrder(glyph_order + [lig_name])
addOpenTypeFeatures(font, fea_path)
font.save(output)  # Glyph will be renamed!
```

✅ **Do this:**
```python
# Always update post table before saving
font['glyf'][lig_name] = new_glyph
font.setGlyphOrder(glyph_order + [lig_name])
font['post'].glyphOrder = font.getGlyphOrder()  # ← THE FIX
addOpenTypeFeatures(font, fea_path)
font.save(output)  # Glyph name preserved!
```

### 4. Verification

Always verify your ligature glyph was saved correctly:

```python
# After saving
saved_font = TTFont(output_path)

# Check if glyph exists with correct name
assert lig_name in saved_font['glyf'], f"Glyph {lig_name} not found!"
assert lig_name in saved_font['hmtx'].metrics, f"Metrics for {lig_name} not found!"
assert lig_name in saved_font.getGlyphOrder(), f"Glyph {lig_name} not in order!"

# Check GSUB references correct name
if 'GSUB' in saved_font:
    # Extract ligature glyph name from GSUB
    # It should match lig_name, not glyph####
    pass
```

## What Happens Without the Fix

### Before Fix (post table not updated):

```
1. Create lig_world glyph
2. Add to glyf, hmtx, glyph order
3. addOpenTypeFeatures() creates GSUB:
   sub w o r l d by lig_world;
4. Save font
   → Post table doesn't know "lig_world"
   → Glyph renamed to "glyph01322"
   → GSUB auto-updated to: sub w o r l d by glyph01322;
5. Result: Glyph exists but name is wrong
```

### After Fix (post table updated):

```
1. Create lig_world glyph
2. Add to glyf, hmtx, glyph order
3. Update post.glyphOrder ← THE FIX
4. addOpenTypeFeatures() creates GSUB:
   sub w o r l d by lig_world;
5. Save font
   → Post table knows "lig_world"
   → Name preserved
6. Result: Glyph exists with correct name ✓
```

## Testing the Fix

Run this test to see the difference:

```python
from fontTools.ttLib import TTFont

# Load your saved font
font = TTFont('output_ligature_fixed.ttf')

# Check glyph names
glyph_order = font.getGlyphOrder()

# Look for your ligature
lig_glyphs = [g for g in glyph_order if g.startswith('lig_')]
print(f"Ligature glyphs found: {lig_glyphs}")

# Should print: ['lig_world'] if fixed
# Would print: [] if broken (and you'd find 'glyph01322' instead)
```

## Additional Resources

- [fontTools Documentation - post table](https://fonttools.readthedocs.io/en/latest/ttLib/tables/_p_o_s_t.html)
- [OpenType Specification - post table](https://docs.microsoft.com/en-us/typography/opentype/spec/post)
- [fontTools feaLib](https://fonttools.readthedocs.io/en/latest/feaLib/)

## Summary

**The ligature glyph doesn't "disappear" - it gets renamed.**

**The fix is simple: Update the post table before saving:**

```python
if 'post' in font:
    font['post'].glyphOrder = font.getGlyphOrder()
```

This one line ensures your custom glyph names (like `lig_world`) are preserved in the final font file.
