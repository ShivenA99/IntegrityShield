# Complete Solution: Why Ligature Glyphs Get Renamed in fontTools

## TL;DR - The Problem

When you create a ligature glyph (e.g., `lig_world`) in a TrueType font using fontTools:
- The glyph is created successfully
- `addOpenTypeFeatures()` works fine
- But after saving, the glyph is renamed to `glyph01322`

## Root Cause

**The post table format determines whether glyph names are preserved.**

Most modern fonts use **post table format 3.0**, which:
- Does NOT store glyph names
- Generates names on-the-fly when needed
- Always renames custom glyphs to `glyph####` when saving

## The Complete Solution

**Convert the post table to format 2.0 BEFORE saving:**

```python
# After adding your ligature glyph
if 'post' in font:
    font['post'].formatType = 2.0

# Then save
font.save(output_path)
```

## Complete Working Code

```python
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools import ttLib
from fontTools.ttLib.tables import _g_l_y_f as glyf
import tempfile
import os

def create_ligature_font(base_font_path, visual_word, hidden_word, output_path):
    """
    Create a font with a ligature preserving custom glyph names.

    Args:
        base_font_path: Path to base TrueType font
        visual_word: Word to display (e.g., "hello")
        hidden_word: Word to type (e.g., "world")
        output_path: Path to save modified font
    """
    # Load font
    font = TTFont(base_font_path)

    # Get tables
    glyf_table = font['glyf']
    hmtx_table = font['hmtx']
    cmap = font.getBestCmap()

    # Create ligature name
    lig_name = f"lig_{hidden_word.replace(' ', '_')}"

    # STEP 1: Build ligature glyph from visual word glyphs
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

            # Transform coordinates
            for coord in coordinates:
                all_coordinates.append((coord[0] + x_offset, coord[1]))

            all_flags.extend(flags)

            # Update contour indices
            for endPt in endPtsOfContours:
                all_endPtsOfContours.append(endPt + current_point_index)

            current_point_index += len(coordinates)

        x_offset += width
        total_width += width

    # Create new glyph
    new_glyph = glyf.Glyph()
    new_glyph.numberOfContours = len(all_endPtsOfContours)

    if new_glyph.numberOfContours > 0:
        new_glyph.coordinates = ttLib.tables._g_l_y_f.GlyphCoordinates(all_coordinates)
        new_glyph.flags = all_flags
        new_glyph.endPtsOfContours = all_endPtsOfContours
        new_glyph.program = ttLib.tables._g_l_y_f.ttProgram.Program()
        new_glyph.program.fromBytecode(b'')

    # STEP 2: Add to glyf table
    # NOTE: This automatically adds the glyph to the glyph order
    glyf_table[lig_name] = new_glyph

    # STEP 3: Add metrics
    hmtx_table.metrics[lig_name] = (total_width, 0)

    # STEP 4: Verify glyph was added to order (should be automatic)
    if lig_name not in font.getGlyphOrder():
        # This shouldn't happen with modern fontTools, but just in case
        glyph_order = list(font.getGlyphOrder())
        glyph_order.append(lig_name)
        font.setGlyphOrder(glyph_order)

    # STEP 5: *** THE CRITICAL FIX *** Convert post table to format 2.0
    if 'post' in font:
        # Format 3.0 doesn't store names, format 2.0 does
        font['post'].formatType = 2.0
        print(f"Converted post table to format 2.0 to preserve glyph names")

    # STEP 6: Create OpenType liga feature
    hidden_glyphs = [cmap.get(ord(c)) for c in hidden_word if ord(c) in cmap]

    fea_code = f"""languagesystem DFLT dflt;
languagesystem latn dflt;

feature liga {{
    sub {' '.join(hidden_glyphs)} by {lig_name};
}} liga;
"""

    # STEP 7: Add feature
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fea', delete=False) as fea_file:
        fea_file.write(fea_code)
        fea_path = fea_file.name

    try:
        addOpenTypeFeatures(font, fea_path)
    finally:
        os.unlink(fea_path)

    # STEP 8: Save
    font.save(output_path)
    font.close()

    print(f"✓ Created font with ligature '{lig_name}': {output_path}")

    # STEP 9: Verify
    verify_ligature_saved(output_path, lig_name)


def verify_ligature_saved(font_path, expected_lig_name):
    """Verify the ligature glyph was saved with correct name"""
    font = TTFont(font_path)

    if expected_lig_name in font['glyf']:
        print(f"✓ SUCCESS: Glyph '{expected_lig_name}' preserved!")
        glyph = font['glyf'][expected_lig_name]
        width = font['hmtx'].metrics[expected_lig_name][0]
        print(f"  Contours: {glyph.numberOfContours}")
        print(f"  Width: {width}")

        # Verify GSUB references it
        if 'GSUB' in font:
            gsub = font['GSUB']
            for feature_record in gsub.table.FeatureList.FeatureRecord:
                if feature_record.FeatureTag == 'liga':
                    feature = feature_record.Feature
                    for lookup_index in feature.LookupListIndex:
                        lookup = gsub.table.LookupList.Lookup[lookup_index]
                        for subtable in lookup.SubTable:
                            if hasattr(subtable, 'ligatures'):
                                for first, lig_set in subtable.ligatures.items():
                                    for lig in lig_set:
                                        if lig.LigGlyph == expected_lig_name:
                                            print(f"✓ GSUB correctly references '{expected_lig_name}'")
                                        else:
                                            print(f"✗ WARNING: GSUB references '{lig.LigGlyph}' instead")
    else:
        print(f"✗ FAILURE: Glyph '{expected_lig_name}' was renamed!")

        # Try to find what it was renamed to
        if 'GSUB' in font:
            gsub = font['GSUB']
            for feature_record in gsub.table.FeatureList.FeatureRecord:
                if feature_record.FeatureTag == 'liga':
                    feature = feature_record.Feature
                    for lookup_index in feature.LookupListIndex:
                        lookup = gsub.table.LookupList.Lookup[lookup_index]
                        for subtable in lookup.SubTable:
                            if hasattr(subtable, 'ligatures'):
                                for first, lig_set in subtable.ligatures.items():
                                    for lig in lig_set:
                                        print(f"  Renamed to: {lig.LigGlyph}")

    font.close()


# Usage
if __name__ == "__main__":
    create_ligature_font(
        base_font_path="fonts/Roboto.ttf",
        visual_word="hello",
        hidden_word="world",
        output_path="output_ligature_correct.ttf"
    )
```

## Understanding post Table Formats

### Format 1.0
- Uses standard Macintosh glyph names only (258 glyphs)
- Rarely used in modern fonts

### Format 2.0
- Stores custom glyph names
- **This is what you need for custom ligature names**
- Most compatible with font editing tools

### Format 3.0
- Does NOT store glyph names
- Generates names on-the-fly
- **This is why your ligature glyphs get renamed!**
- Common in web fonts to save file size

## Key Insights

1. **Adding to glyf table automatically updates glyph order**
   ```python
   font['glyf'][lig_name] = new_glyph
   # lig_name is now in font.getGlyphOrder()
   ```

2. **post format 3.0 is the culprit**
   - Many modern fonts use format 3.0 for smaller file size
   - Format 3.0 does not preserve custom glyph names
   - Converting to 2.0 preserves names

3. **The fix is simple**
   ```python
   if 'post' in font:
       font['post'].formatType = 2.0
   ```

4. **This must be done BEFORE saving**
   - After you've added all glyphs
   - Before calling `font.save()`

## Common Mistakes

### ❌ Forgetting to convert post table
```python
font['glyf'][lig_name] = new_glyph
addOpenTypeFeatures(font, fea_path)
font.save(output)  # Glyph renamed to glyph####!
```

### ❌ Converting post table but not adding glyph properly
```python
# Forgot to add to glyf table
font['post'].formatType = 2.0
font.save(output)  # No glyph at all!
```

### ✅ Correct approach
```python
font['glyf'][lig_name] = new_glyph
font['hmtx'].metrics[lig_name] = (width, 0)
font['post'].formatType = 2.0  # THE FIX
addOpenTypeFeatures(font, fea_path)
font.save(output)  # Glyph name preserved!
```

## Testing Your Implementation

```python
from fontTools.ttLib import TTFont

# After creating your font
font = TTFont('your_output.ttf')

# Check post table format
print(f"post format: {font['post'].formatType}")
# Should be 2.0

# Check if ligature exists with correct name
lig_name = "lig_world"
print(f"{lig_name} exists: {lig_name in font['glyf']}")
# Should be True

# Check glyph order doesn't have glyph#### names
glyph_order = font.getGlyphOrder()
generic_glyphs = [g for g in glyph_order if g.startswith('glyph') and g[5:].isdigit()]
print(f"Generic glyph names: {len(generic_glyphs)}")
# Should not include your ligature
```

## File Size Considerations

Converting from format 3.0 to 2.0 will increase font file size because:
- Format 3.0: No glyph names stored
- Format 2.0: All glyph names stored as strings

For a font with 1300+ glyphs:
- Format 3.0: ~200-300 bytes for post table
- Format 2.0: ~5-10 KB for post table (depending on name lengths)

This is usually acceptable for desktop fonts, but may matter for web fonts.

## Alternative: Accept the Generic Names

If file size is critical, you can accept the generic glyph names:

```python
# Don't convert post table format
# Glyph will be renamed to glyph####
# But it will still work! The GSUB table is automatically updated.

font.save(output)

# The ligature works, just with a different name
# This is fine if you don't need to edit the font later
```

## Summary

**The problem:** Ligature glyphs get renamed from `lig_world` to `glyph01322`

**The cause:** post table format 3.0 doesn't store custom glyph names

**The fix:** Convert post table to format 2.0 before saving

```python
if 'post' in font:
    font['post'].formatType = 2.0
```

**Result:** Your custom ligature glyph names are preserved!
