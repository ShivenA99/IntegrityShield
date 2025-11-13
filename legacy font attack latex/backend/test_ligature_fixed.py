#!/usr/bin/env python3
"""
Demonstration: Fixed version showing the ligature glyph DOES persist
when the cached GlyphSet is properly invalidated
"""

from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools import ttLib
import tempfile
import os
from pathlib import Path

def test_ligature_creation_fixed():
    """Test creating a ligature glyph WITH the cache invalidation fix"""

    # Use an existing font
    base_font_path = Path("/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/fonts/Roboto.ttf")

    if not base_font_path.exists():
        print(f"ERROR: Font not found: {base_font_path}")
        return

    print("="*80)
    print("TEST: Ligature Glyph Creation - WITH FIX")
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
        glyph_order_new = list(glyph_order_before)  # Make a copy
        glyph_order_new.append(lig_name)
        font.setGlyphOrder(glyph_order_new)
        print(f"  ✓ Added '{lig_name}' to glyph order")
        print(f"  Glyphs after: {len(font.getGlyphOrder())}")

    # Verify glyph exists before addOpenTypeFeatures
    print("\n[STEP 3] Verifying glyph exists in tables...")
    print(f"  Glyph in glyf table: {lig_name in font['glyf']}")
    print(f"  Glyph in hmtx table: {lig_name in font['hmtx'].metrics}")
    print(f"  Glyph in glyph order: {lig_name in font.getGlyphOrder()}")

    # *** THE FIX: Invalidate cached GlyphSet ***
    print("\n[STEP 4] *** APPLYING FIX: Invalidating cached GlyphSet ***")
    if hasattr(font, '_glyphset'):
        print("  Found cached _glyphset, deleting it...")
        del font._glyphset
    else:
        print("  No cached _glyphset found (this is unusual)")

    # Verify the glyph is now in the glyph set
    print("\n[STEP 5] Verifying glyph in fresh GlyphSet...")
    fresh_glyph_set = font.getGlyphSet()
    if lig_name in fresh_glyph_set:
        print(f"  ✓ Glyph '{lig_name}' IS in fresh GlyphSet")
    else:
        print(f"  ✗ ERROR: Glyph '{lig_name}' NOT in fresh GlyphSet")
        return

    # Step 6: Create and add OpenType feature
    print("\n[STEP 6] Adding OpenType feature...")
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

    # Step 7: Check if glyph still exists after addOpenTypeFeatures
    print("\n[STEP 7] Checking glyph after addOpenTypeFeatures...")
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

    # Step 8: Save and reload to verify
    print("\n[STEP 8] Saving and reloading font...")
    temp_font_path = tempfile.mktemp(suffix='.ttf')

    try:
        font.save(temp_font_path)
        print(f"  ✓ Saved to: {temp_font_path}")

        # Reload
        reloaded_font = TTFont(temp_font_path)

        print("\n[STEP 9] Checking reloaded font...")
        glyph_in_glyf = lig_name in reloaded_font['glyf']
        glyph_in_hmtx = lig_name in reloaded_font['hmtx'].metrics
        glyph_in_order = lig_name in reloaded_font.getGlyphOrder()

        print(f"  Glyph in glyf table: {glyph_in_glyf}")
        print(f"  Glyph in hmtx table: {glyph_in_hmtx}")
        print(f"  Glyph in glyph order: {glyph_in_order}")
        print(f"  Total glyphs in order: {len(reloaded_font.getGlyphOrder())}")

        # Check the actual glyph
        if glyph_in_glyf:
            lig_glyph = reloaded_font['glyf'][lig_name]
            print(f"\n  Ligature glyph details:")
            print(f"    Number of contours: {lig_glyph.numberOfContours}")
            print(f"    Width: {reloaded_font['hmtx'].metrics[lig_name][0]}")

        # Check GSUB
        if 'GSUB' in reloaded_font:
            print(f"\n  ✓ GSUB table exists in reloaded font")
            gsub = reloaded_font['GSUB']
            if hasattr(gsub, 'table') and hasattr(gsub.table, 'FeatureList'):
                features = [f.FeatureTag for f in gsub.table.FeatureList.FeatureRecord]
                print(f"  Features: {features}")

        print("\n" + "="*80)
        if glyph_in_glyf and glyph_in_hmtx and glyph_in_order:
            print("✓✓✓ SUCCESS: Ligature glyph PERSISTED CORRECTLY! ✓✓✓")
        else:
            print("✗✗✗ FAILURE: Ligature glyph disappeared! ✗✗✗")
        print("="*80)

        reloaded_font.close()

    finally:
        if os.path.exists(temp_font_path):
            os.unlink(temp_font_path)

    font.close()

    print("\n" + "="*80)
    print("SUMMARY OF THE FIX:")
    print("="*80)
    print("""
The key fix is to DELETE the cached GlyphSet before calling addOpenTypeFeatures():

    if hasattr(font, '_glyphset'):
        del font._glyphset

This forces fontTools to rebuild the GlyphSet with your newly added glyphs,
allowing addOpenTypeFeatures() to properly validate and reference them.

Without this fix, addOpenTypeFeatures() sees the OLD cached GlyphSet that
doesn't include your new ligature glyph, resulting in the error:
"glyph names are referenced but are missing from the glyph set"
""")

if __name__ == "__main__":
    test_ligature_creation_fixed()
