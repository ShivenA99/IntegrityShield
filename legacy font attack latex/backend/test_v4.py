#!/usr/bin/env python3
"""
Comprehensive test suite for V4 manipulator
Tests various word lengths and character patterns
"""

import requests
import json
from pathlib import Path

API_URL = "http://localhost:5001/api"

# Test cases covering various scenarios
TEST_CASES = [
    # Format: (visual_word, hidden_word, description)

    # Length 3-5: Simple cases
    ("cat", "dog", "Simple 3-letter substitution"),
    ("test", "work", "Simple 4-letter substitution"),
    ("hello", "world", "Simple 5-letter, no repetition"),

    # Length 5-7: With repeated characters
    ("hello", "anita", "Repeated 'a' in hidden word"),
    ("hello", "fuffa", "Repeated 'f' in hidden word (3x)"),
    ("simple", "repeat", "Repeated 'e' in both words"),

    # Length 8-10: More complex
    ("computer", "software", "8-letter words"),
    ("algorithm", "procedure", "9-letter words"),
    ("javascript", "typescript", "10-letter words with overlap"),

    # Length 10-12: Long words
    ("extinction", "extraction", "10-letter, some same chars"),
    ("helloworld", "fuffafuffi", "10-letter, repeated 'f' (6x)"),
    ("information", "programming", "11-letter words"),

    # Length 13-15: Very long words
    ("unidirectional", "biidirectional", "14-letter, repeated 'i' (4x)"),
    ("authentication", "authorization", "14-letter words"),
    ("internationalization", "localizationprocess", "20-letter words"),

    # Edge cases
    ("aaa", "bbb", "All same character"),
    ("aba", "cdc", "Palindrome pattern"),
    ("Test", "Work", "Mixed case"),
    ("123", "456", "Numbers only"),
]

def test_manipulation(visual_word, hidden_word, description):
    """Test a single word pair"""
    print(f"\n{'='*80}")
    print(f"Test: {description}")
    print(f"Visual: '{visual_word}' → Hidden: '{hidden_word}'")
    print(f"{'='*80}")

    try:
        response = requests.post(
            f"{API_URL}/manipulate",
            json={
                "mode": "truly_selective_v4",
                "visual_word": visual_word,
                "hidden_word": hidden_word
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✓ SUCCESS")
                print(f"  PDF: {result['pdf_file']}")
                print(f"  Font: {result['font_file']}")

                # Check log file
                log_dir = Path(f"/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/outputs/{result.get('log_dir', '')}")
                if log_dir.exists():
                    log_file = log_dir / 'steps.log'
                    if log_file.exists():
                        with open(log_file) as f:
                            log_content = f.read()
                            # Extract modified hidden word
                            for line in log_content.split('\n'):
                                if 'Modified hidden word:' in line:
                                    print(f"  {line}")
                                    break
                return True
            else:
                print(f"✗ FAILED: {result.get('error', 'Unknown error')}")
                return False
        else:
            error_msg = response.json().get('error', 'Unknown error')
            print(f"✗ FAILED: HTTP {response.status_code} - {error_msg}")
            return False

    except Exception as e:
        print(f"✗ EXCEPTION: {str(e)}")
        return False

def run_all_tests():
    """Run all test cases"""
    print("\n" + "="*80)
    print("V4 MANIPULATOR COMPREHENSIVE TEST SUITE")
    print("="*80)

    results = []
    for visual, hidden, desc in TEST_CASES:
        success = test_manipulation(visual, hidden, desc)
        results.append((desc, success))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\nPassed: {passed}/{total} ({100*passed//total}%)")
    print("\nDetailed Results:")
    for desc, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {desc}")

    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
