#!/usr/bin/env python3
"""
Diagnose ligature glyph creation
"""

from fontTools.ttLib import TTFont
from pathlib import Path

# Test with a recent font
font_path = Path("/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/outputs/346d6350_deceptive_lig.ttf")

if not font_path.exists():
    print(f"Font not found: {font_path}")
    exit(1)

print(f"Analyzing: {font_path.name}\n")

font = TTFont(str(font_path))

# Check if it has glyf table
if 'glyf' not in font:
    print("ERROR: No glyf table found (might be CFF font)")
    exit(1)

glyf_table = font['glyf']
hmtx_table = font['hmtx']

# Find the ligature glyph
lig_name = "lig_world"

if lig_name not in glyf_table:
    print(f"ERROR: Ligature glyph '{lig_name}' not found in font")
    print(f"Available glyphs: {list(glyf_table.keys())[:20]}...")
    exit(1)

lig_glyph = glyf_table[lig_name]

print(f"Ligature glyph: {lig_name}")
print(f"  Number of contours: {lig_glyph.numberOfContours}")
print(f"  Width: {hmtx_table.metrics[lig_name][0]}")

if lig_glyph.numberOfContours > 0:
    print(f"  End points of contours: {lig_glyph.endPtsOfContours}")
    print(f"  Total coordinates: {len(lig_glyph.coordinates)}")
    print(f"  Coordinate range:")
    print(f"    X: {min(c[0] for c in lig_glyph.coordinates)} to {max(c[0] for c in lig_glyph.coordinates)}")
    print(f"    Y: {min(c[1] for c in lig_glyph.coordinates)} to {max(c[1] for c in lig_glyph.coordinates)}")
else:
    print("  ERROR: Glyph has no contours!")

# Compare with individual characters
print("\nIndividual character glyphs:")
for char, glyph_name in [('h', 'h'), ('e', 'e'), ('l', 'l'), ('o', 'o')]:
    if glyph_name in glyf_table:
        g = glyf_table[glyph_name]
        print(f"  {char} ({glyph_name}): {g.numberOfContours} contours, {len(g.coordinates) if g.numberOfContours > 0 else 0} coords")

# Check OpenType features
print("\nOpenType features:")
if 'GSUB' in font:
    gsub = font['GSUB']
    print(f"  GSUB table present")
    if hasattr(gsub, 'table') and hasattr(gsub.table, 'FeatureList'):
        features = [f.FeatureTag for f in gsub.table.FeatureList.FeatureRecord]
        print(f"  Features: {features}")
else:
    print("  ERROR: No GSUB table found")

