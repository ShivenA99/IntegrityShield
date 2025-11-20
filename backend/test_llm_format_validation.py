#!/usr/bin/env python3
"""
Simple format validation tests that check code structure without requiring API calls.
These tests verify that the correct API formats (input_text, input_image, role: user) are used.
"""

import ast
import inspect
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


def check_file_for_patterns(file_path: Path, patterns: dict) -> list:
    """Check a file for specific code patterns."""
    errors = []
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        for pattern_name, (should_exist, should_not_exist) in patterns.items():
            if should_exist:
                # Check if any of the patterns exist (OR logic)
                found = False
                for pattern in should_exist:
                    if pattern in content:
                        found = True
                        break
                if not found:
                    errors.append(f"Missing required pattern (one of: {should_exist}) in {file_path.name}")
            
            if should_not_exist:
                for pattern in should_not_exist:
                    if pattern in content:
                        errors.append(f"Found forbidden pattern '{pattern}' in {file_path.name}")
    except Exception as e:
        errors.append(f"Error reading {file_path.name}: {e}")
    
    return errors


def test_gold_answer_format():
    """Test gold answer generation service format."""
    print("\n=== Testing Gold Answer Service Format ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "pipeline" / "gold_answer_generation_service.py"
    
    patterns = {
        "input_text": (
            ['"type": "input_text"', "'type': 'input_text'"],
            ['"type": "text"', "'type': 'text'"]
        ),
        "input_image": (
            ['"type": "input_image"', "'type': 'input_image'"],
            ['"type": "image_url"', "'type': 'image_url'"]
        ),
    }
    
    errors = check_file_for_patterns(file_path, patterns)
    
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("PASSED: Gold answer service uses correct format (input_text/input_image)")
    return True


def test_answer_scoring_format():
    """Test answer scoring service format."""
    print("\n=== Testing Answer Scoring Service Format ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "reports" / "answer_scoring.py"
    
    patterns = {
        "input_text": (
            ['"type": "input_text"', "'type': 'input_text'"],
            ['"type": "text"', "'type': 'text'"]
        ),
    }
    
    errors = check_file_for_patterns(file_path, patterns)
    
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("PASSED: Answer scoring service uses correct format (input_text)")
    return True


def test_google_gemini_format():
    """Test Google Gemini client format."""
    print("\n=== Testing Google Gemini Client Format ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "reports" / "llm_clients.py"
    
    patterns = {
        "role_user": (
            ['"role": "user"', "'role': 'user'"],
            []
        ),
        "question_data": (
            ['question_data'],
            []
        ),
    }
    
    errors = check_file_for_patterns(file_path, patterns)
    
    # Check specifically in GoogleClient.query_with_file method
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Find GoogleClient class and query_with_file method
        if 'class GoogleClient' in content:
            # Check that role: user is in the payload
            if '"role": "user"' not in content and "'role': 'user'" not in content:
                errors.append("Missing 'role: user' in GoogleClient payload")
            
            # Check that question_data is handled
            if 'question_data' not in content:
                errors.append("Missing question_data parameter handling in GoogleClient")
    except Exception as e:
        errors.append(f"Error checking GoogleClient: {e}")
    
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("PASSED: Google Gemini client uses correct format (role: user, question_data)")
    return True


def test_pdf_orchestrator_format():
    """Test PDF orchestrator format."""
    print("\n=== Testing PDF Orchestrator Format ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "reports" / "pdf_question_orchestrator.py"
    
    patterns = {
        "question_bundle": (
            ['question_bundle'],
            []
        ),
    }
    
    errors = check_file_for_patterns(file_path, patterns)
    
    # Check that _build_batch_prompt returns question_bundle
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        if 'question_bundle' not in content:
            errors.append("Missing question_bundle in PDF orchestrator")
        elif 'return {"prompt": prompt, "question_bundle": question_bundle}' not in content:
            # Check for alternative return formats
            if 'return {"prompt"' not in content or '"question_bundle"' not in content:
                errors.append("_build_batch_prompt does not return question_bundle")
    except Exception as e:
        errors.append(f"Error checking PDF orchestrator: {e}")
    
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("PASSED: PDF orchestrator builds and returns question_bundle")
    return True


def main():
    """Run all format validation tests."""
    print("=" * 60)
    print("LLM API Format Validation Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Gold Answer Format", test_gold_answer_format()))
    results.append(("Answer Scoring Format", test_answer_scoring_format()))
    results.append(("Google Gemini Format", test_google_gemini_format()))
    results.append(("PDF Orchestrator Format", test_pdf_orchestrator_format()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All format validation tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

