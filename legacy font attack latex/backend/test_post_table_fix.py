#!/usr/bin/env python3
"""
Test script demonstrating the post table fix for ligature glyph names
"""

from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools import ttLib
from fontTools.ttLib.tables import _g_l_y_f as glyf
import tempfile
import os
from pathlib import Path

def test_without_fix():
    """Test WITHOUT updating post table - glyph name will be lost"""
    print("="*80)
    print("TEST 1: WITHOUT post table fix")
    print("="*80)

    base_font_path = Path("/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/fonts/Roboto.ttf")
    font = TTFont(str(base_font_path))

    lig_name = "lig_test_broken"
    create_simple_ligature(font, lig_name, ["w", "x", "y", "z"], ["a", "b", "c", "d"])

    # MISSING: font['post'].glyphOrder = font.getGlyphOrder()

    add_liga_feature(font, lig_name, ["w", "x", "y", "z"])

    temp_path = tempfile.mktemp(suffix='_broken.ttf')
    font.save(temp_path)
    font.close()

    # Verify
    saved_font = TTFont(temp_path)
    found = lig_name in saved_font['glyf']

    print(f"\nResult:")
    print(f"  Glyph '{lig_name}' in saved font: {found}")

    if not found:
        print(f"  ✗ FAILED: Glyph was renamed")
        # Find what it was renamed to
        if 'GSUB' in saved_font:
            actual_name = find_ligature_glyph_in_gsub(saved_font)
            if actual_name:
                print(f"  → Renamed to: {actual_name}")
    else:
        print(f"  ✓ UNEXPECTED: Glyph name was preserved (maybe post table was auto-updated?)")

    saved_font.close()
    os.unlink(temp_path)

def test_with_fix():
    """Test WITH post table update - glyph name will be preserved"""
    print("\n" + "="*80)
    print("TEST 2: WITH post table fix")
    print("="*80)

    base_font_path = Path("/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/fonts/Roboto.ttf")
    font = TTFont(str(base_font_path))

    lig_name = "lig_test_fixed"
    create_simple_ligature(font, lig_name, ["h", "e", "l", "l", "o"], ["w", "o", "r", "l", "d"])

    # *** THE FIX ***
    print(f"\nApplying fix: Updating post table...")
    if 'post' in font:
        font['post'].glyphOrder = font.getGlyphOrder()
        print(f"  ✓ post.glyphOrder updated")
    else:
        print(f"  ✗ No post table found!")

    add_liga_feature(font, lig_name, ["w", "o", "r", "l", "d"])

    temp_path = tempfile.mktemp(suffix='_fixed.ttf')
    font.save(temp_path)
    font.close()

    # Verify
    saved_font = TTFont(temp_path)
    found = lig_name in saved_font['glyf']

    print(f"\nResult:")
    print(f"  Glyph '{lig_name}' in saved font: {found}")

    if found:
        print(f"  ✓ SUCCESS: Glyph name was preserved!")
        glyph = saved_font['glyf'][lig_name]
        width = saved_font['hmtx'].metrics[lig_name][0]
        print(f"    Contours: {glyph.numberOfContours}")
        print(f"    Width: {width}")

        # Verify GSUB references correct name
        if 'GSUB' in saved_font:
            actual_name = find_ligature_glyph_in_gsub(saved_font)
            if actual_name == lig_name:
                print(f"  ✓ GSUB correctly references '{lig_name}'")
            else:
                print(f"  ✗ GSUB references wrong name: {actual_name}")
    else:
        print(f"  ✗ FAILED: Glyph was renamed")
        # Find what it was renamed to
        if 'GSUB' in saved_font:
            actual_name = find_ligature_glyph_in_gsub(saved_font)
            if actual_name:
                print(f"  → Renamed to: {actual_name}")

    saved_font.close()
    os.unlink(temp_path)

def create_simple_ligature(font, lig_name, visual_glyphs, component_glyphs):
    """Create a simple ligature glyph"""
    print(f"\nCreating ligature: {lig_name}")

    glyf_table = font['glyf']
    hmtx_table = font['hmtx']

    # Create empty glyph for simplicity
    new_glyph = glyf.Glyph()
    new_glyph.numberOfContours = 0

    # Add to tables
    glyf_table[lig_name] = new_glyph
    hmtx_table.metrics[lig_name] = (500, 0)

    # Update glyph order
    glyph_order = list(font.getGlyphOrder())
    if lig_name not in glyph_order:
        glyph_order.append(lig_name)
        font.setGlyphOrder(glyph_order)

    print(f"  Added to glyf, hmtx, and glyph order")
    print(f"  Total glyphs: {len(font.getGlyphOrder())}")

def add_liga_feature(font, lig_name, component_glyphs):
    """Add liga feature to font"""
    fea_code = f"""languagesystem DFLT dflt;
languagesystem latn dflt;

feature liga {{
    sub {' '.join(component_glyphs)} by {lig_name};
}} liga;
"""

    print(f"\nAdding OpenType liga feature:")
    print(f"  sub {' '.join(component_glyphs)} by {lig_name};")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.fea', delete=False) as f:
        f.write(fea_code)
        fea_path = f.name

    try:
        addOpenTypeFeatures(font, fea_path)
        print(f"  ✓ Feature added successfully")
    except Exception as e:
        print(f"  ✗ Failed to add feature: {e}")
    finally:
        os.unlink(fea_path)

def find_ligature_glyph_in_gsub(font):
    """Extract the ligature glyph name from GSUB table"""
    if 'GSUB' not in font:
        return None

    gsub = font['GSUB']
    for feature_record in gsub.table.FeatureList.FeatureRecord:
        if feature_record.FeatureTag == 'liga':
            feature = feature_record.Feature
            for lookup_index in feature.LookupListIndex:
                lookup = gsub.table.LookupList.Lookup[lookup_index]
                for subtable in lookup.SubTable:
                    if hasattr(subtable, 'ligatures'):
                        for first_glyph, lig_set in subtable.ligatures.items():
                            for lig in lig_set:
                                return lig.LigGlyph
    return None

if __name__ == "__main__":
    print("\n" + "="*80)
    print("LIGATURE GLYPH NAME PRESERVATION TEST")
    print("Comparing: WITH vs WITHOUT post table fix")
    print("="*80 + "\n")

    test_without_fix()
    test_with_fix()

    print("\n" + "="*80)
    print("CONCLUSION:")
    print("="*80)
    print("""
Without the fix: font['post'].glyphOrder = font.getGlyphOrder()
  → Custom glyph names are lost
  → Glyphs are renamed to glyph####

With the fix: font['post'].glyphOrder = font.getGlyphOrder()
  → Custom glyph names are preserved
  → Ligature glyphs keep their intended names
""")
