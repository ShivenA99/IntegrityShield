"""
Fine-tuning analysis for run e3f47955-ebd1-412d-b0e5-0090b8f6066d
Analyzing suffix positioning accuracy after the negative sign fix.
"""

import json
import re
from pathlib import Path

RUN_ID = "e3f47955-ebd1-412d-b0e5-0090b8f6066d"
RUN_DIR = Path(f"data/pipeline_runs/{RUN_ID}")

def analyze_q8_positioning():
    print("=" * 80)
    print("Q8 SUFFIX POSITIONING FINE-TUNING ANALYSIS")
    print("=" * 80)

    # From the debug JSON, Q8 shows:
    # Operation 0: ['and', -343, 'sequen', 1, 'ce', -343, 'length', -343]
    # Operation 1: Tf /Courier 5  <- Note: size 5, not 8!
    # Operation 2: ['500']
    # Operation 3: Tf /F50 8
    # Operation 4: ['.', -456, 'Analyze', -343, 'gradien', 29, 't', -343, 'b', -28, 'eha', 28, 'vior:']

    print("From debug reconstruction JSON:")
    print("  Original text: 'and sequence length'")
    print("  Replacement: '500' (in Courier at size 5)")
    print("  Suffix: '. Analyze gradient behavior:'")
    print("  NO SPACING VALUE found in operation 4!")
    print()

    # Analysis of what should happen:
    print("ROOT CAUSE ANALYSIS:")
    print("1. The replacement is happening for a NUMBER ('50' -> '500')")
    print("2. Courier font size is 5pt, not 8pt (math formula context)")
    print("3. No spacing adjustment was calculated/applied")
    print("4. This suggests the replacement might not have triggered our spacing logic")
    print()

    # Calculate what SHOULD have been done:
    original_text = "50"  # The "50" in "sequence length 50"
    replacement_text = "500"

    # For size 5 font in math context
    courier_char_width = 0.6  # Monospace em ratio
    font_size = 5.0

    original_width_est = len(original_text) * courier_char_width * font_size  # Rough estimate
    replacement_width = len(replacement_text) * courier_char_width * font_size

    print(f"MISSING CALCULATIONS:")
    print(f"  Original '{original_text}' estimated width: {original_width_est:.2f} pts")
    print(f"  Replacement '{replacement_text}' width: {replacement_width:.2f} pts")
    print(f"  Width difference: {original_width_est - replacement_width:.2f} pts")

    width_diff = original_width_est - replacement_width
    if abs(width_diff) > 0.1:
        spacing_needed = -(width_diff * 1000) / font_size
        print(f"  Spacing needed: {spacing_needed:.2f}")
        print(f"  But NO spacing was applied!")
    else:
        print(f"  No spacing needed (difference < 0.1)")

    print()

def analyze_visual_evidence():
    print("VISUAL EVIDENCE FROM IMAGE:")
    print("Looking at Q8 in the screenshot:")
    print("  Text shows: 'Consider a vanilla RNN with recurrent weight matrix Wₕ and sequence length 500.'")
    print("  The '.' appears to be too close to '500'")
    print("  This suggests '500' is wider than the original '50' it replaced")
    print("  The suffix '. Analyze...' is starting too early (leftward shift)")
    print()

def analyze_other_questions():
    print("CROSS-REFERENCE WITH OTHER QUESTIONS:")
    print("From the image:")
    print("  Q1: 'What is not primary...' - 'not' looks properly positioned")
    print("  Q2: 'long-term' - looks good")
    print("  Q3: 'CNN cell' - spacing looks correct now")
    print("  Q5: 'CNNs often' - looks correct")
    print("  Q6: 'Unidirectional RNNs' - looks good")
    print("  Q7: 'unidirectional?' - could be slightly tight")
    print()
    print("CONCLUSION: Most questions look good, Q8 has the positioning issue")
    print()

def identify_root_causes():
    print("ROOT CAUSES IDENTIFIED:")
    print()

    print("1. MATH CONTEXT DIFFERENT HANDLING:")
    print("   - Q8 replacement happens in math/equation context")
    print("   - Font size is 5pt instead of regular 8pt text")
    print("   - This might trigger different code paths")
    print()

    print("2. MISSING BBOX INFORMATION:")
    print("   - Unlike text replacements, math numbers might not have precise bbox data")
    print("   - Width calculation might be using defaults instead of actual measurements")
    print()

    print("3. INSUFFICIENT SPACING CALCULATION:")
    print("   - Even if spacing is calculated, the Courier width estimation might be off")
    print("   - Need to measure actual Courier width vs. original math font width")
    print()

def calculate_fix_requirements():
    print("FIX REQUIREMENTS:")
    print()

    print("IMMEDIATE ISSUES TO ADDRESS:")
    print("1. Ensure math context replacements trigger spacing calculations")
    print("2. Improve Courier width estimation for small font sizes")
    print("3. Account for math font vs. text font width differences")
    print()

    print("POTENTIAL FIXES:")
    print("A. Enhanced Width Calculation:")
    print("   - Use actual font metrics instead of 0.6em estimation")
    print("   - Account for math font baseline and spacing")
    print()

    print("B. Context-Aware Spacing:")
    print("   - Different spacing logic for math vs. text context")
    print("   - Consider surrounding characters (like subscripts)")
    print()

    print("C. Iterative Refinement:")
    print("   - Add debug logging to see actual vs. expected positions")
    print("   - Fine-tune the spacing multiplier based on visual results")
    print()

def specific_q8_analysis():
    print("SPECIFIC Q8 DETAILED ANALYSIS:")
    print()

    print("Original sequence (estimated):")
    print("  'and sequence length 50. Analyze gradient behavior'")
    print()

    print("After replacement:")
    print("  'and sequence length' + [Courier 5pt] + '500' + [F50 8pt] + '. Analyze gradient behavior'")
    print()

    print("VISUAL ISSUE:")
    print("  The period '.' appears too close to '500'")
    print("  Suggesting '500' in Courier 5pt is WIDER than '50' in original math font")
    print()

    print("SPACING NEEDED:")
    print("  Need to push the suffix '. Analyze...' further RIGHT")
    print("  This means we need MORE NEGATIVE spacing value")
    print("  Current: No spacing applied")
    print("  Needed: Negative spacing proportional to the width increase")
    print()

def proposed_fix_plan():
    print("=" * 80)
    print("PROPOSED FIX PLAN")
    print("=" * 80)

    print("PHASE 1: DEBUG CURRENT CALCULATION")
    print("1. Add debug logging to see if Q8 replacement triggers spacing calculation")
    print("2. Check if bbox/width information is available for math context")
    print("3. Verify the calculate_text_width_courier function for small font sizes")
    print()

    print("PHASE 2: IMPROVE WIDTH ESTIMATION")
    print("1. Use actual font metrics instead of hardcoded 0.6em")
    print("2. Account for math font characteristics (CMR vs. CMMI)")
    print("3. Test spacing calculation with various font sizes")
    print()

    print("PHASE 3: FINE-TUNE SPACING MULTIPLIER")
    print("1. Add visual measurement capabilities")
    print("2. Iteratively adjust spacing based on visual results")
    print("3. Create test cases for different replacement scenarios")
    print()

    print("IMMEDIATE ACTION ITEMS:")
    print("□ Check if Q8 replacement code path includes spacing calculation")
    print("□ Measure actual Courier '500' width vs. original '50' width")
    print("□ Add debug output to show calculated vs. applied spacing")
    print("□ Test with different font size scenarios")
    print()

def main():
    analyze_q8_positioning()
    analyze_visual_evidence()
    analyze_other_questions()
    identify_root_causes()
    calculate_fix_requirements()
    specific_q8_analysis()
    proposed_fix_plan()

if __name__ == "__main__":
    main()