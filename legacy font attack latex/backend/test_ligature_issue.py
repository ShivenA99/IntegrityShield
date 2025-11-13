#!/usr/bin/env python3
"""
Test script to diagnose and demonstrate the ligature glyph disappearing issue
with fontTools addOpenTypeFeatures
"""

from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools import ttLib
import tempfile
import os
from pathlib import Path

def test_ligature_creation():
    """Test creating a ligature glyph and see if it disappears after addOpenTypeFeatures"""

    # Use an existing font
    base_font_path = Path("/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/fonts/Roboto.ttf")

    if not base_font_path.exists():
        print(f"ERROR: Font not found: {base_font_path}")
        return

    print("="*80)
    print("TEST: Ligature Glyph Disappearing Issue")
    print("="*80)

    # Load font
    font = TTFont(str(base_font_path))

    # Get necessary tables
    glyf_table = font['glyf']
    hmtx_table = font['hmtx']
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()

    # Define test words
    visual_word = "hello"
    hidden_word = "world"
    lig_name = f"lig_{hidden_word}"

    print(f"\nCreating ligature: '{lig_name}' ('{hidden_word}' → '{visual_word}')")

    # Step 1: Create ligature glyph by combining visual glyphs
    print("\n[STEP 1] Creating ligature glyph...")
    from fontTools.ttLib.tables import _g_l_y_f as glyf

    all_coordinates = []
    all_flags = []
    all_endPtsOfContours = []
    x_offset = 0
    total_width = 0
    current_point_index = 0

    for visual_char in visual_word:
        visual_glyph_name = cmap.get(ord(visual_char))
        if not visual_glyph_name:
            continue

        source_glyph = font['glyf'][visual_glyph_name]
        width = font['hmtx'].metrics[visual_glyph_name][0]

        if source_glyph.numberOfContours > 0:
            coordinates = source_glyph.coordinates
            flags = source_glyph.flags
            endPtsOfContours = source_glyph.endPtsOfContours

            for coord in coordinates:
                all_coordinates.append((coord[0] + x_offset, coord[1]))

            all_flags.extend(flags)

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

    # Add to glyf table
    glyf_table[lig_name] = new_glyph
    hmtx_table.metrics[lig_name] = (total_width, 0)

    print(f"  ✓ Created glyph '{lig_name}' with {new_glyph.numberOfContours} contours")
    print(f"  ✓ Width: {total_width}")

    # Step 2: Add to glyph order
    print("\n[STEP 2] Adding to glyph order...")
    glyph_order_before = font.getGlyphOrder()
    print(f"  Glyphs before: {len(glyph_order_before)}")

    if lig_name not in glyph_order_before:
        glyph_order_new = glyph_order_before + [lig_name]
        font.setGlyphOrder(glyph_order_new)
        print(f"  ✓ Added '{lig_name}' to glyph order")
        print(f"  Glyphs after: {len(font.getGlyphOrder())}")

    # Verify glyph exists before addOpenTypeFeatures
    print("\n[STEP 3] Verifying glyph exists...")
    print(f"  Glyph in glyf table: {lig_name in font['glyf']}")
    print(f"  Glyph in hmtx table: {lig_name in font['hmtx'].metrics}")
    print(f"  Glyph in glyph order: {lig_name in font.getGlyphOrder()}")

    # Step 4: Create and add OpenType feature
    print("\n[STEP 4] Adding OpenType feature...")
    hidden_glyphs = [cmap.get(ord(c)) for c in hidden_word if ord(c) in cmap]

    fea_code = f"""languagesystem DFLT dflt;
languagesystem latn dflt;

feature liga {{
    sub {' '.join(hidden_glyphs)} by {lig_name};
}} liga;
"""

    print("  Feature code:")
    for line in fea_code.split('\n'):
        if line.strip():
            print(f"    {line}")

    # Write to temp file and add feature
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fea', delete=False) as fea_file:
        fea_file.write(fea_code)
        fea_path = fea_file.name

    try:
        addOpenTypeFeatures(font, fea_path)
        print("  ✓ Successfully added liga feature")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return
    finally:
        os.unlink(fea_path)

    # Step 5: Check if glyph still exists after addOpenTypeFeatures
    print("\n[STEP 5] Checking glyph after addOpenTypeFeatures...")
    print(f"  Glyph in glyf table: {lig_name in font['glyf']}")
    print(f"  Glyph in hmtx table: {lig_name in font['hmtx'].metrics}")
    print(f"  Glyph in glyph order: {lig_name in font.getGlyphOrder()}")
    print(f"  Total glyphs in order: {len(font.getGlyphOrder())}")

    # Check if GSUB table was created
    if 'GSUB' in font:
        print(f"  ✓ GSUB table exists")
        gsub = font['GSUB']
        if hasattr(gsub, 'table') and hasattr(gsub.table, 'FeatureList'):
            features = [f.FeatureTag for f in gsub.table.FeatureList.FeatureRecord]
            print(f"  Features in GSUB: {features}")
    else:
        print(f"  ✗ GSUB table not found")

    # Step 6: Save and reload to verify
    print("\n[STEP 6] Saving and reloading font...")
    temp_font_path = tempfile.mktemp(suffix='.ttf')

    try:
        font.save(temp_font_path)
        print(f"  ✓ Saved to: {temp_font_path}")

        # Reload
        reloaded_font = TTFont(temp_font_path)

        print("\n[STEP 7] Checking reloaded font...")
        print(f"  Glyph in glyf table: {lig_name in reloaded_font['glyf']}")
        print(f"  Glyph in hmtx table: {lig_name in reloaded_font['hmtx'].metrics}")
        print(f"  Glyph in glyph order: {lig_name in reloaded_font.getGlyphOrder()}")
        print(f"  Total glyphs in order: {len(reloaded_font.getGlyphOrder())}")

        if lig_name in reloaded_font['glyf']:
            print("\n✓ SUCCESS: Ligature glyph persisted!")
        else:
            print("\n✗ FAILURE: Ligature glyph disappeared!")

        reloaded_font.close()

    finally:
        if os.path.exists(temp_font_path):
            os.unlink(temp_font_path)

    font.close()

    print("\n" + "="*80)
    print("CONCLUSION:")
    print("="*80)
    print("""
The issue you're experiencing is likely NOT that the glyph disappears due to
addOpenTypeFeatures(), but rather one of these common issues:

1. **Glyph Order Not Set Before addOpenTypeFeatures**:
   You MUST call font.setGlyphOrder() BEFORE calling addOpenTypeFeatures().

2. **maxp Table Not Updated**:
   The maxp table tracks glyph counts. While fontTools usually handles this
   automatically on save, you can manually trigger it with:
   font['maxp'].recalc(font)

3. **post Table Glyph Names**:
   If your font has a 'post' table, make sure glyph names are synced:
   font['post'].glyphOrder = font.getGlyphOrder()

4. **Glyph Not Referenced**:
   If the glyph isn't referenced in any OpenType feature or cmap, some
   tools might skip it during subsetting or optimization.

RECOMMENDED APPROACH:
Always follow this exact order:
1. Create glyph in glyf table
2. Add metrics to hmtx table
3. Update glyph order: font.setGlyphOrder(old_order + [new_glyph])
4. THEN call addOpenTypeFeatures()
5. Save with: font.save(path)

The glyph should NOT disappear if you follow these steps correctly.
""")

if __name__ == "__main__":
    test_ligature_creation()
