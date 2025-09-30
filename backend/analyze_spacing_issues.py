"""
Deep analysis of spacing issues in run 4bf3e702-6585-454a-add2-add388305ff1.
This script analyzes Q3, Q5, Q7, and Q8 to understand why courier injection causes spacing issues.
"""

import json
import sys
from pathlib import Path

RUN_ID = "4bf3e702-6585-454a-add2-add388305ff1"
RUN_DIR = Path(f"backend/data/pipeline_runs/{RUN_ID}")

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def analyze_mapping(question, q_num):
    """Analyze a single question's mapping"""
    print(f"\n{'=' * 80}")
    print(f"Q{q_num}: {question['stem_text'][:60]}...")
    print(f"{'=' * 80}")

    if 'manipulation' not in question or 'substring_mappings' not in question['manipulation']:
        print(f"⚠️  No substring mappings found for Q{q_num}")
        return

    mappings = question['manipulation']['substring_mappings']
    print(f"\n📋 Found {len(mappings)} substring mapping(s)")

    for i, mapping in enumerate(mappings, 1):
        print(f"\n  Mapping {i}:")
        print(f"    ID:          {mapping['id']}")
        print(f"    Original:    '{mapping['original']}' (len={len(mapping['original'])})")
        print(f"    Replacement: '{mapping['replacement']}' (len={len(mapping['replacement'])})")
        print(f"    Position:    {mapping['start_pos']} → {mapping['end_pos']}")
        print(f"    Context:     {mapping['context']}")

        # Extract the surrounding context from the stem text
        stem = question['stem_text']
        start = mapping['start_pos']
        end = mapping['end_pos']

        # Show 20 chars before and after
        ctx_start = max(0, start - 20)
        ctx_end = min(len(stem), end + 20)

        prefix = stem[ctx_start:start]
        target = stem[start:end]
        suffix = stem[end:ctx_end]

        print(f"\n    Text Context:")
        print(f"      Prefix:  ...'{prefix}'")
        print(f"      Target:  「{target}」")
        print(f"      Suffix:  '{suffix}'...")

        # Calculate length difference
        len_diff = len(mapping['replacement']) - len(mapping['original'])
        if len_diff > 0:
            print(f"\n    ⚠️  LENGTH MISMATCH: Replacement is {len_diff} chars LONGER")
            print(f"        This means we need {len_diff} extra chars of space")
        elif len_diff < 0:
            print(f"\n    ⚠️  LENGTH MISMATCH: Replacement is {abs(len_diff)} chars SHORTER")
            print(f"        This creates {abs(len_diff)} chars of extra space")
        else:
            print(f"\n    ✓ Length match: Replacement is same length as original")

        # Analyze the bbox
        if 'selection_bbox' in mapping:
            bbox = mapping['selection_bbox']
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            print(f"\n    Bounding Box:")
            print(f"      Position: ({bbox[0]:.2f}, {bbox[1]:.2f}) → ({bbox[2]:.2f}, {bbox[3]:.2f})")
            print(f"      Size:     {width:.2f} x {height:.2f}")
            print(f"      Width per char (original): {width / len(mapping['original']):.2f}")

            if len_diff != 0:
                print(f"\n    🔍 SPACING ISSUE ANALYSIS:")
                print(f"      - Original text '{mapping['original']}' fits in {width:.2f} pts")
                print(f"      - Replacement text '{mapping['replacement']}' must also fit in {width:.2f} pts")
                print(f"      - But Courier is a monospace font with different metrics than CMR9")
                print(f"      - This causes visual misalignment!")

def analyze_debug_json():
    """Analyze the debug JSON to see how stream rewrite handled the transformations"""
    debug_file = RUN_DIR / "artifacts/stream_rewrite-overlay/debug.pdf/page_0_rewrite_enhanced.json"

    if not debug_file.exists():
        print("\n⚠️  Debug JSON not found")
        return

    print(f"\n\n{'#' * 80}")
    print("STREAM REWRITE DEBUG ANALYSIS")
    print(f"{'#' * 80}")

    debug_data = load_json(debug_file)

    if 'replacements_applied' in debug_data:
        print(f"\n✓ Found {len(debug_data['replacements_applied'])} replacements applied")

        for repl in debug_data['replacements_applied']:
            print(f"\n  Replacement:")
            print(f"    Original:    '{repl.get('original', '?')}'")
            print(f"    Replacement: '{repl.get('replacement', '?')}'")
            print(f"    Token Index: {repl.get('token_index', '?')}")

            if 'kerning_adjustments' in repl:
                print(f"    Kerning:     {repl['kerning_adjustments']}")

            if 'font_switch' in repl:
                print(f"    Font:        {repl['font_switch']}")

def analyze_content_stream_operations():
    """Analyze the actual PDF content stream operations"""
    reconstruction_file = RUN_DIR / "artifacts/stream_rewrite-overlay/debug.pdf/after_reconstruction.json"

    if not reconstruction_file.exists():
        print("\n⚠️  Reconstruction JSON not found")
        return

    print(f"\n\n{'#' * 80}")
    print("PDF CONTENT STREAM OPERATIONS")
    print(f"{'#' * 80}")

    recon_data = load_json(reconstruction_file)

    if 'operations' in recon_data:
        print(f"\n✓ Found {len(recon_data['operations'])} operations")
        print("\nOperation sequence (first 20):")

        for i, op in enumerate(recon_data['operations'][:20]):
            operator = op.get('operator', '?')
            operands = op.get('operands', [])

            if operator == 'Tf':  # Font selection
                print(f"\n  [{i}] Font: {operands[0]} at size {operands[1]}")
            elif operator == 'TJ':  # Show text with positioning
                print(f"  [{i}] Text: {operands[0][:100]}...")
            elif operator in ['Tm', 'Td']:  # Text positioning
                print(f"  [{i}] Position: {operator} {operands}")

def main():
    print("╔" + "═" * 78 + "╗")
    print("║" + " SPACING & OVERLAY ISSUE ROOT CAUSE ANALYSIS ".center(78) + "║")
    print("║" + f" Run ID: {RUN_ID} ".center(78) + "║")
    print("╚" + "═" * 78 + "╝")

    structured_file = RUN_DIR / "structured.json"

    if not structured_file.exists():
        print(f"❌ Error: structured.json not found at {structured_file}")
        sys.exit(1)

    data = load_json(structured_file)
    questions = data.get('questions', [])

    # Analyze the problematic questions
    problematic_questions = ['3', '5', '7', '8']

    for q_num in problematic_questions:
        question = next((q for q in questions if q['q_number'] == q_num), None)
        if question:
            analyze_mapping(question, q_num)

    # Analyze debug data
    analyze_debug_json()
    analyze_content_stream_operations()

    # Summary of issues
    print(f"\n\n{'#' * 80}")
    print("ROOT CAUSE SUMMARY")
    print(f"{'#' * 80}\n")

    print("🔍 ISSUE #1: LENGTH MISMATCH (Q3, Q5, Q7)")
    print("   - Original words and replacements have different lengths")
    print("   - LSTM → CNN (4 chars → 3 chars): Creates extra space")
    print("   - LSTMs → RNNs (5 chars → 4 chars): Creates extra space")
    print("   - bidirectional → unidirectional (13 → 14 chars): Needs more space")
    print("   - The Courier font injection doesn't account for the length difference")
    print("   - Result: Visual spacing gaps after the replacement\n")

    print("🔍 ISSUE #2: PREFIX OVERLAP (Q8)")
    print("   - RNN → c (3 chars → 1 char): Massive length reduction")
    print("   - The bbox is sized for 3 chars, but only 1 char is rendered")
    print("   - Courier 'c' is too small for the bbox, causing misalignment")
    print("   - The suffix text shifts left, overlapping with the prefix")
    print("   - Result: Visual overlap on prefix text\n")

    print("🔧 ROOT CAUSE:")
    print("   Location: backend/app/services/pipeline/enhancement_methods/content_stream_renderer.py")
    print("   Problem:  The courier_font_strategy doesn't adjust kerning/spacing")
    print("            when the replacement text length differs from original")
    print("   Specific: After injecting Courier font + replacement text,")
    print("            the code needs to add spacing adjustments to compensate")
    print("            for the length difference.\n")

    print("📝 TECHNICAL DETAILS:")
    print("   1. Stream rewrite finds token (e.g., 'LSTM')")
    print("   2. Splits TJ array: [prefix] + ['LSTM'] + [suffix]")
    print("   3. Inserts: [prefix] + [Tf /Courier 8] + ['CNN'] + [Tf /CMR9 8] + [suffix]")
    print("   4. BUT: 'CNN' in Courier takes different space than 'LSTM' in CMR9")
    print("   5. Missing: Kerning adjustment in the TJ array to compensate\n")

    print("✅ SOLUTION:")
    print("   Add a kerning value to the TJ array after the replacement text:")
    print("   [prefix] + [Tf /Courier 8] + ['CNN', <kerning>] + [Tf /CMR9 8] + [suffix]")
    print("   where <kerning> = (original_width - replacement_width) * scaling_factor\n")

if __name__ == "__main__":
    main()
