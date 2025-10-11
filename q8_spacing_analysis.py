"""
Detailed Q8 spacing analysis with actual measurements
"""

def analyze_q8_spacing():
    print("=" * 80)
    print("Q8 DETAILED SPACING ANALYSIS")
    print("=" * 80)

    # From structured.json:
    original = "50"
    replacement = "500"
    selection_bbox = [398.9591979980469, 593.6425170898438, 408.1766662597656, 602.60888671875]

    # Calculate bbox dimensions
    bbox_width = selection_bbox[2] - selection_bbox[0]
    bbox_height = selection_bbox[3] - selection_bbox[1]

    print(f"MAPPING CONFIGURATION:")
    print(f"  Original: '{original}' (length: {len(original)})")
    print(f"  Replacement: '{replacement}' (length: {len(replacement)})")
    print(f"  Selection bbox: {selection_bbox}")
    print(f"  Bbox width: {bbox_width:.2f} pts")
    print(f"  Bbox height: {bbox_height:.2f} pts")
    print(f"  Width per original char: {bbox_width / len(original):.2f} pts/char")
    print()

    # From debug JSON - Courier font size is 5pt
    courier_font_size = 5.0

    print(f"FONT ANALYSIS:")
    print(f"  Courier font size used: {courier_font_size} pts")
    print(f"  Context: Math equation (smaller than body text)")
    print()

    # Current width calculation (what the code likely does)
    courier_char_width_em = 0.6  # Standard monospace em ratio
    calculated_replacement_width = len(replacement) * courier_char_width_em * courier_font_size
    calculated_original_width = bbox_width  # What the code should use

    print(f"CURRENT CALCULATION (likely what code does):")
    print(f"  Original width (from bbox): {calculated_original_width:.2f} pts")
    print(f"  Replacement width (Courier estimate): {calculated_replacement_width:.2f} pts")
    print(f"  Width difference: {calculated_original_width - calculated_replacement_width:.2f} pts")

    width_diff = calculated_original_width - calculated_replacement_width
    if abs(width_diff) > 0.1:
        current_spacing = -(width_diff * 1000) / courier_font_size
        print(f"  Current spacing calculation: {current_spacing:.2f}")
    else:
        print(f"  No spacing calculated (diff < 0.1)")
    print()

    # PROBLEM: Courier 0.6em might be wrong at small sizes
    print(f"PROBLEM ANALYSIS:")
    print(f"  Issue: 0.6em ratio might be inaccurate for 5pt font")
    print(f"  Issue: Original math font width != estimated width")
    print()

    # Visual evidence suggests '500' is taking MORE space than allocated
    print(f"VISUAL EVIDENCE:")
    print(f"  Observation: '500' appears wider than the '50' space")
    print(f"  Conclusion: Need MORE negative spacing to push suffix right")
    print()

    # Better estimation
    print(f"IMPROVED ANALYSIS:")

    # Original '50' in math context (likely CMMI or CMR at 5pt)
    # Math fonts are typically narrower than text fonts
    # Let's estimate original took about 8 pts for '50'
    estimated_original_math_width = 8.0

    # Courier '500' at 5pt with better estimation
    # Courier is wider than math fonts, especially for numbers
    # At 5pt, each char might be closer to 3.5pts rather than 3.0pts
    better_courier_char_width = 3.5
    better_replacement_width = len(replacement) * better_courier_char_width

    print(f"  Better original estimate: {estimated_original_math_width:.2f} pts")
    print(f"  Better replacement estimate: {better_replacement_width:.2f} pts")
    print(f"  Better width difference: {estimated_original_math_width - better_replacement_width:.2f} pts")

    better_width_diff = estimated_original_math_width - better_replacement_width
    better_spacing = -(better_width_diff * 1000) / courier_font_size
    print(f"  Better spacing needed: {better_spacing:.2f}")
    print()

    # What was actually applied?
    print(f"WHAT WAS APPLIED:")
    print(f"  From debug JSON: NO spacing value found")
    print(f"  This suggests spacing calculation was skipped or failed")
    print()

def propose_fixes():
    print("=" * 80)
    print("PROPOSED FIXES")
    print("=" * 80)

    print("FIX 1: IMPROVE COURIER WIDTH CALCULATION")
    print("  Problem: Hardcoded 0.6em ratio inaccurate for small fonts")
    print("  Solution: Use actual font metrics or size-dependent formula")
    print("  Code location: calculate_text_width_courier() method")
    print()

    print("FIX 2: DEBUG SPACING CALCULATION TRIGGER")
    print("  Problem: Q8 replacement might not trigger spacing logic")
    print("  Solution: Add debug logging to verify code path")
    print("  Check: Does width_difference calculation happen for Q8?")
    print()

    print("FIX 3: ENHANCED SPACING MULTIPLIER")
    print("  Problem: Even correct width diff might need scaling factor")
    print("  Solution: Add visual adjustment factor based on context")
    print("  Example: math_context_multiplier = 1.2")
    print()

    print("IMMEDIATE TEST:")
    print("  1. Add debug log to show calculated spacing for Q8")
    print("  2. If spacing is calculated, increase magnitude by 20-30%")
    print("  3. If spacing not calculated, fix trigger condition")
    print()

def fix_plan():
    print("=" * 80)
    print("IMPLEMENTATION PLAN")
    print("=" * 80)

    print("STEP 1: DIAGNOSTICS")
    print("""
    Add debug logging in _execute_precision_width_replacement:

    if run_id:
        self.logger.info(
            f"Q{ctx.get('q_number', '?')}: '{original_text}' -> '{replacement_text}' "
            f"original_width={original_width:.2f}, replacement_width={actual_replacement_width:.2f}, "
            f"width_diff={width_difference:.2f}, spacing={spacing_adjustment:.2f}",
            extra={"run_id": run_id}
        )
    """)

    print("\nSTEP 2: ENHANCE WIDTH CALCULATION")
    print("""
    Modify calculate_text_width_courier to be more accurate:

    def calculate_text_width_courier(self, text: str, font_size: float) -> float:
        # Better estimation for small font sizes
        if font_size < 7:
            char_width_ratio = 0.7  # Wider ratio for small fonts
        else:
            char_width_ratio = 0.6  # Original ratio for larger fonts

        return len(text) * char_width_ratio * font_size
    """)

    print("\nSTEP 3: CONTEXT-AWARE ADJUSTMENT")
    print("""
    Add context multiplier in spacing calculation:

    # After calculating spacing_adjustment
    if segment_font_context.get('fontsize', 8) < 7:
        # Math context needs more spacing
        spacing_adjustment *= 1.3
    """)

    print("\nSTEP 4: VERIFICATION")
    print("  1. Run new test with same Q8 replacement")
    print("  2. Check debug logs show calculated values")
    print("  3. Verify visual positioning improved")

if __name__ == "__main__":
    analyze_q8_spacing()
    propose_fixes()
    fix_plan()