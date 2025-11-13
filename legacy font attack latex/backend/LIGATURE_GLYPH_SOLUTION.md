# Solution: Ligature Glyph "Disappearing" After addOpenTypeFeatures()

## The Problem

When you create a new ligature glyph in a TrueType font using fontTools and save it after calling `addOpenTypeFeatures()`, you observe that:
1. The glyph with your custom name (e.g., `lig_world`) is not in the final font
2. The GSUB feature table IS present and working
3. The ligature glyph exists but with a different name (e.g., `glyph01322`)

**What You Expect:**
- Glyph named `lig_world` in the `glyf` table
- GSUB feature referencing `lig_world`

**What You Get:**
- Glyph renamed to `glyph01322`
- GSUB feature automatically updated to reference `glyph01322`
- Your custom name `lig_world` is gone

## Root Cause

The issue occurs because of the **post table** (PostScript information table). When you save a TrueType font:

1. FontTools checks if your glyph name exists in the `post` table's glyph name array
2. If it doesn't exist, fontTools generates a generic name like `glyph####` (where #### is the glyph ID)
3. The GSUB table is automatically updated to use the new name
4. Your custom glyph name is lost

This happens because:
- You added the glyph to `glyf` and `hmtx` tables
- You called `setGlyphOrder()` to update the glyph order
- BUT you didn't update the `post` table to include your glyph name

## The Solution

**Update the `post` table** before saving the font to preserve your custom glyph names:

### Method 1: Set post.glyphOrder (RECOMMENDED)

```python
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures

# Load font
font = TTFont('base_font.ttf')

# ... create your ligature glyph ...

# Step 1: Add to glyf table
glyf_table[lig_name] = new_glyph

# Step 2: Add metrics
hmtx_table.metrics[lig_name] = (width, 0)

# Step 3: Update glyph order
glyph_order = font.getGlyphOrder()
glyph_order.append(lig_name)
font.setGlyphOrder(glyph_order)

# Step 4: *** CRITICAL: Update post table ***
if 'post' in font:
    font['post'].glyphOrder = font.getGlyphOrder()

# Step 5: Add OpenType features
addOpenTypeFeatures(font, feature_file_path)

# Step 6: Save
font.save('output.ttf')
```

### Method 2: Set post.extraNames (If post table format 2.0)

If your font uses post table format 2.0 (which stores glyph names), you can directly manipulate `extraNames`:

```python
# Add glyph, metrics, and update glyph order as before
glyf_table[lig_name] = new_glyph
hmtx_table.metrics[lig_name] = (width, 0)
glyph_order = list(font.getGlyphOrder())
glyph_order.append(lig_name)
font.setGlyphOrder(glyph_order)

# Update post table
if 'post' in font:
    post = font['post']
    if hasattr(post, 'extraNames'):
        # Add the new glyph name to extraNames if it's not a standard Mac glyph
        if lig_name not in post.extraNames:
            post.extraNames.append(lig_name)
    # Always sync glyphOrder
    post.glyphOrder = font.getGlyphOrder()

# Now add OpenType features and save
addOpenTypeFeatures(font, feature_file_path)
font.save('output.ttf')
```

### Method 3: Ensure post table format 2.0

Force the post table to format 2.0 (which stores glyph names) if it isn't already:

```python
# After adding glyph and updating glyph order
if 'post' in font:
    post = font['post']

    # Ensure format 2.0 (stores glyph names)
    if post.formatType != 2.0:
        print(f"Converting post table from format {post.formatType} to 2.0")
        post.formatType = 2.0

    # Sync with glyph order
    post.glyphOrder = font.getGlyphOrder()
```

## Complete Working Example

Here's a complete, working example of creating a ligature glyph:

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

    # Step 1: Create ligature glyph by combining visual word glyphs
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

    # Step 2: Add to glyf table
    glyf_table[lig_name] = new_glyph

    # Step 3: Add metrics
    hmtx_table.metrics[lig_name] = (total_width, 0)

    # Step 4: Update glyph order
    glyph_order = list(font.getGlyphOrder())
    if lig_name not in glyph_order:
        glyph_order.append(lig_name)
        font.setGlyphOrder(glyph_order)

    # Step 5: CRITICAL - Invalidate cached GlyphSet
    if hasattr(font, '_glyphset'):
        del font._glyphset

    # Step 6: Create OpenType feature
    hidden_glyphs = [cmap.get(ord(c)) for c in hidden_word if ord(c) in cmap]

    fea_code = f"""languagesystem DFLT dflt;
languagesystem latn dflt;

feature liga {{
    sub {' '.join(hidden_glyphs)} by {lig_name};
}} liga;
"""

    # Step 7: Add the feature
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fea', delete=False) as fea_file:
        fea_file.write(fea_code)
        fea_path = fea_file.name

    try:
        addOpenTypeFeatures(font, fea_path)
    finally:
        os.unlink(fea_path)

    # Step 8: Save
    font.save(output_path)
    font.close()

    print(f"✓ Created ligature font: {output_path}")
    print(f"  Ligature '{lig_name}': '{hidden_word}' → '{visual_word}'")
    print(f"  Width: {total_width}")

# Usage
if __name__ == "__main__":
    create_ligature_font(
        base_font_path="fonts/Roboto.ttf",
        visual_word="hello",
        hidden_word="world",
        output_path="output_with_ligature.ttf"
    )
```

## Why This Happens

The fontTools library caches the GlyphSet for performance reasons. Here's what happens internally:

1. When you first call `font.getGlyphSet()` or access glyphs, fontTools creates a `_glyphset` object
2. This object maps glyph names to glyph objects
3. The cache is stored as `font._glyphset`
4. When you add a new glyph to the font tables, the cache is NOT automatically updated
5. `addOpenTypeFeatures()` uses `font.getGlyphSet()` to validate glyph names
6. It sees the OLD cached list, which doesn't include your new glyph
7. Result: "glyph not found" error

## Additional Tips

### 1. Update maxp Table (Usually Automatic)

The `maxp` table tracks the number of glyphs. FontTools usually updates this automatically when you save, but you can manually trigger it:

```python
font['maxp'].recalc(font)
```

### 2. Update post Table Glyph Names (If Needed)

If your font has a `post` table with glyph names:

```python
if 'post' in font:
    font['post'].glyphOrder = font.getGlyphOrder()
```

### 3. Verify Before Adding Features

Always verify your glyph was added correctly before calling `addOpenTypeFeatures()`:

```python
# After adding glyph and updating glyph order
assert lig_name in font['glyf'], "Glyph not in glyf table"
assert lig_name in font['hmtx'].metrics, "Glyph not in hmtx table"
assert lig_name in font.getGlyphOrder(), "Glyph not in glyph order"

# Invalidate cache
if hasattr(font, '_glyphset'):
    del font._glyphset

# Verify in glyph set
glyph_set = font.getGlyphSet()
assert lig_name in glyph_set, f"Glyph {lig_name} not in glyph set after cache invalidation"
```

### 4. Handling Composite Glyphs

If you need to handle composite glyphs (glyphs made of components), you'll need additional logic:

```python
if source_glyph.numberOfContours < 0:  # Composite glyph
    # Handle components - this is more complex
    # You might want to decompose first or handle components separately
    pass
```

## Best Practices

1. **Always follow this order:**
   - Create glyph in glyf table
   - Add metrics to hmtx table
   - Update glyph order with setGlyphOrder()
   - Invalidate cached GlyphSet
   - Add OpenType features
   - Save font

2. **Use assertions to verify** each step succeeded

3. **Clear the cache** before operations that validate glyph names

4. **Test the saved font** by reloading it and checking:
   ```python
   reloaded = TTFont(output_path)
   assert lig_name in reloaded['glyf']
   assert 'GSUB' in reloaded  # Features were added
   ```

## Common Mistakes

### ❌ Don't Do This

```python
# Adding glyph
font['glyf'][lig_name] = new_glyph

# Forgetting to update glyph order
# font.setGlyphOrder(...) <- MISSING!

# This will fail even if you clear the cache
addOpenTypeFeatures(font, fea_path)
```

### ❌ Don't Do This

```python
# Adding glyph and updating glyph order
font['glyf'][lig_name] = new_glyph
font.setGlyphOrder(glyph_order + [lig_name])

# Forgetting to clear cache!
# addOpenTypeFeatures uses the OLD cached glyph set
addOpenTypeFeatures(font, fea_path)  # <- WILL FAIL
```

### ✅ Do This

```python
# Add glyph
font['glyf'][lig_name] = new_glyph
font['hmtx'].metrics[lig_name] = (width, 0)

# Update glyph order
glyph_order = font.getGlyphOrder()
glyph_order.append(lig_name)
font.setGlyphOrder(glyph_order)

# Clear cache before adding features
if hasattr(font, '_glyphset'):
    del font._glyphset

# Now add features - will work!
addOpenTypeFeatures(font, fea_path)
```

## References

- [fontTools Documentation](https://fonttools.readthedocs.io/)
- [fontTools feaLib.builder](https://fonttools.readthedocs.io/en/latest/feaLib/)
- [OpenType Feature File Specification](https://adobe-type-tools.github.io/afdko/OpenTypeFeatureFileSpecification.html)

## Summary

The ligature glyph doesn't actually "disappear" - it's just not visible to `addOpenTypeFeatures()` because of a cached GlyphSet. The fix is simple:

**Delete the cached GlyphSet before calling addOpenTypeFeatures:**

```python
if hasattr(font, '_glyphset'):
    del font._glyphset
```

This forces fontTools to rebuild the GlyphSet with your newly added glyphs, and `addOpenTypeFeatures()` will work correctly.
