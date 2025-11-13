#!/usr/bin/env python3
"""
Comprehensive Ligature Testing Suite
Tests varying word lengths from 5-15 characters
"""

import requests
import subprocess
import time
from pathlib import Path

# Test cases with varying lengths
TEST_CASES = [
    # 5 characters
    {"visual": "hello", "hidden": "world", "length": 5},
    {"visual": "login", "hidden": "admin", "length": 5},
    {"visual": "click", "hidden": "virus", "length": 5},

    # 6 characters
    {"visual": "secure", "hidden": "hacked", "length": 6},
    {"visual": "sample", "hidden": "danger", "length": 6},

    # 7 characters
    {"visual": "welcome", "hidden": "badlink", "length": 7},
    {"visual": "confirm", "hidden": "phished", "length": 7},

    # 8 characters
    {"visual": "download", "hidden": "malware!", "length": 8},
    {"visual": "verified", "hidden": "fakecode", "length": 8},

    # 9 characters
    {"visual": "authentic", "hidden": "deceptive", "length": 9},
    {"visual": "legitimate", "hidden": "falsified", "length": 10},

    # 10 characters
    {"visual": "trustworthy", "hidden": "manipulate", "length": 10},

    # 12 characters
    {"visual": "alohafriends", "hidden": "graciasmucha", "length": 12},

    # 15 characters
    {"visual": "congratulations", "hidden": "youvebeen_pwned", "length": 15},
]

API_URL = "http://127.0.0.1:5001/api/manipulate"
OUTPUT_DIR = Path("/Users/ashishrajshekhar/Desktop/ASU/Fall 2025/real_code_glyph/backend/outputs")

def test_manipulation(visual_word, hidden_word, mode="ligature"):
    """Test a single word pair"""
    print(f"\n{'='*80}")
    print(f"Testing: '{visual_word}' → '{hidden_word}' (length: {len(visual_word)})")
    print(f"{'='*80}")

    # Make API request
    response = requests.post(API_URL, json={
        "mode": mode,
        "visual_word": visual_word,
        "hidden_word": hidden_word
    })

    if not response.ok:
        print(f"❌ API ERROR: {response.status_code}")
        print(response.text)
        return False

    result = response.json()
    if not result.get("success"):
        print(f"❌ FAILED: {result.get('error', 'Unknown error')}")
        return False

    pdf_file = OUTPUT_DIR / result["pdf_file"]

    # Extract text using pdftotext
    try:
        text_output = subprocess.run(
            ["pdftotext", str(pdf_file), "-"],
            capture_output=True,
            text=True
        )

        extracted_text = text_output.stdout

        # Find the deceptive line
        for line in extracted_text.split('\n'):
            if "Deceptive:" in line:
                extracted_word = line.split("Deceptive:")[-1].strip()

                # Verify
                if extracted_word == hidden_word:
                    print(f"✅ TEXT EXTRACTION: Correct ('{extracted_word}')")
                else:
                    print(f"❌ TEXT EXTRACTION: Expected '{hidden_word}', got '{extracted_word}'")
                    return False
                break

        # Visual inspection instruction
        print(f"📄 PDF: {pdf_file.name}")
        print(f"👁️  VISUAL CHECK: Open PDF and verify it displays '{visual_word}'")

        return True

    except Exception as e:
        print(f"❌ EXTRACTION ERROR: {e}")
        return False

def run_all_tests():
    """Run all test cases"""
    print("\n" + "="*80)
    print("COMPREHENSIVE LIGATURE TESTING SUITE")
    print("="*80)

    results = []

    for i, test_case in enumerate(TEST_CASES, 1):
        visual = test_case["visual"]
        hidden = test_case["hidden"]

        success = test_manipulation(visual, hidden)
        results.append({
            "test_num": i,
            "visual": visual,
            "hidden": hidden,
            "length": len(visual),
            "success": success
        })

        time.sleep(1)  # Brief pause between tests

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for r in results if r["success"])
    total = len(results)

    print(f"\nTotal: {total} tests")
    print(f"Passed: {passed} ({passed/total*100:.1f}%)")
    print(f"Failed: {total - passed}")

    # Breakdown by length
    print("\nBreakdown by word length:")
    by_length = {}
    for r in results:
        length = r["length"]
        if length not in by_length:
            by_length[length] = {"passed": 0, "total": 0}
        by_length[length]["total"] += 1
        if r["success"]:
            by_length[length]["passed"] += 1

    for length in sorted(by_length.keys()):
        stats = by_length[length]
        print(f"  {length} chars: {stats['passed']}/{stats['total']} passed")

    # Failed tests detail
    failed = [r for r in results if not r["success"]]
    if failed:
        print("\n⚠️  Failed tests:")
        for r in failed:
            print(f"  - Test #{r['test_num']}: '{r['visual']}' → '{r['hidden']}' ({r['length']} chars)")

    return results

if __name__ == "__main__":
    run_all_tests()
