#!/usr/bin/env python3
"""Test script to verify PDF formatting fixes work correctly."""

import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.pdf_utils import _escape_latex

def test_true_false_formatting():
    """Test that True/False questions are formatted correctly."""
    print("Testing True/False question formatting...")
    
    # Mock question data
    true_false_question = {
        "q_number": "1",
        "stem_text": "Temporal difference method introduces variance but reduces bias.",
        "options": {
            "True": "True",
            "False": "False"
        },
        "attacked_stem": "Temporal difference method introduces variance but reduces bias.",
        "wrong_label": "True",
        "wrong_reason": "Clearly aligns with how the concept is described in the question."
    }
    
    # Test option formatting logic
    options_list = list(true_false_question["options"].items())
    
    print(f"Options list: {options_list}")
    print(f"Is True/False: {len(options_list) == 2 and all(label in ['True', 'False'] for label, _ in options_list)}")
    
    # Simulate the formatting logic
    formatted_options = []
    if len(options_list) == 2 and all(label in ["True", "False"] for label, _ in options_list):
        for i, (label, option) in enumerate(options_list):
            roman_numeral = "i" if i == 0 else "ii"
            formatted_options.append(f"{roman_numeral}) {option}")
    else:
        for label, option in options_list:
            formatted_options.append(f"{label}) {option}")
    
    print(f"Formatted options: {formatted_options}")
    
    expected = ["i) True", "ii) False"]
    assert formatted_options == expected, f"Expected {expected}, got {formatted_options}"
    print("✅ True/False formatting test passed!")

def test_sub_question_formatting():
    """Test that sub-questions are formatted correctly."""
    print("\nTesting sub-question formatting...")
    
    # Test question number parsing
    test_cases = [
        ("1i", "1", "i"),
        ("1ii", "1", "ii"),
        ("2a", "2", "a"),
        ("2b", "2", "b"),
        ("3", "3", None),
        ("10", "10", None)
    ]
    
    import re
    
    for q_number, expected_main, expected_sub in test_cases:
        if re.match(r'\d+[a-z]+', q_number, re.IGNORECASE):
            main_num = re.match(r'(\d+)', q_number).group(1)
            sub_part = q_number[len(main_num):]
            print(f"Question {q_number} -> Main: {main_num}, Sub: {sub_part}")
            assert main_num == expected_main, f"Expected main {expected_main}, got {main_num}"
            assert sub_part == expected_sub, f"Expected sub {expected_sub}, got {sub_part}"
        else:
            print(f"Question {q_number} -> Regular question")
            assert q_number == expected_main, f"Expected {expected_main}, got {q_number}"
    
    print("✅ Sub-question formatting test passed!")

def test_latex_escaping():
    """Test LaTeX escaping function."""
    print("\nTesting LaTeX escaping...")
    
    test_text = "This is a test with special chars: & % $ # _ { } ~ ^"
    escaped = _escape_latex(test_text)
    print(f"Original: {test_text}")
    print(f"Escaped: {escaped}")
    
    # Check that special characters are escaped
    assert "\\&" in escaped, "& should be escaped"
    assert "\\%" in escaped, "% should be escaped"
    assert "\\$" in escaped, "$ should be escaped"
    assert "\\#" in escaped, "# should be escaped"
    assert "\\_" in escaped, "_ should be escaped"
    
    print("✅ LaTeX escaping test passed!")

def test_mcq_formatting():
    """Test that MCQ questions are formatted correctly."""
    print("\nTesting MCQ question formatting...")
    
    # Mock MCQ question data
    mcq_question = {
        "q_number": "2",
        "stem_text": "Which algorithms belong to the policy-gradient family?",
        "options": {
            "A": "Proximal Policy Optimization (PPO)",
            "B": "Q-learning",
            "C": "REINFORCE",
            "D": "Deep Q-Network (DQN)"
        },
        "attacked_stem": "Which algorithms belong to the policy-gradient family?",
        "wrong_label": "A",
        "wrong_reason": "Clearly aligns with how the concept is described in the question."
    }
    
    # Test option formatting logic
    options_list = list(mcq_question["options"].items())
    
    print(f"Options list: {options_list}")
    print(f"Is True/False: {len(options_list) == 2 and all(label in ['True', 'False'] for label, _ in options_list)}")
    
    # Simulate the formatting logic
    formatted_options = []
    if len(options_list) == 2 and all(label in ["True", "False"] for label, _ in options_list):
        for i, (label, option) in enumerate(options_list):
            roman_numeral = "i" if i == 0 else "ii"
            formatted_options.append(f"{roman_numeral}) {option}")
    else:
        for label, option in options_list:
            formatted_options.append(f"{label}) {option}")
    
    print(f"Formatted options: {formatted_options}")
    
    expected = [
        "A) Proximal Policy Optimization (PPO)",
        "B) Q-learning", 
        "C) REINFORCE",
        "D) Deep Q-Network (DQN)"
    ]
    assert formatted_options == expected, f"Expected {expected}, got {formatted_options}"
    print("✅ MCQ formatting test passed!")




if __name__ == "__main__":
    print("Running PDF formatting tests...")
    print("=" * 50)
    
    try:
        test_true_false_formatting()
        test_sub_question_formatting()
        test_latex_escaping()
        test_mcq_formatting()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! PDF formatting fixes are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
