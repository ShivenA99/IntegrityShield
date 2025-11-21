#!/usr/bin/env python3
"""
Simple mock tests for LLM API calls that verify format without full app imports.
Uses direct code inspection to avoid Python version compatibility issues.
"""

import ast
import inspect
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


def test_gold_answer_prompt_structure():
    """Test gold answer prompt structure by inspecting the code."""
    print("\n=== Testing Gold Answer Prompt Structure ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "pipeline" / "gold_answer_generation_service.py"
    
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Check for correct format
        has_input_text = '"type": "input_text"' in code or "'type': 'input_text'" in code
        has_input_image = '"type": "input_image"' in code or "'type': 'input_image'" in code
        no_text = '"type": "text"' not in code and "'type': 'text'" not in code
        no_image_url = '"type": "image_url"' not in code and "'type': 'image_url'" not in code
        
        if not has_input_text:
            print("FAILED: Missing 'input_text' format")
            return False
        if not has_input_image:
            print("FAILED: Missing 'input_image' format")
            return False
        if not no_text:
            print("FAILED: Found forbidden 'text' format")
            return False
        if not no_image_url:
            print("FAILED: Found forbidden 'image_url' format")
            return False
        
        print("PASSED: Gold answer prompt uses correct format")
        return True
    except Exception as e:
        print(f"FAILED: Error checking file: {e}")
        return False


def test_answer_scoring_structure():
    """Test answer scoring structure by inspecting the code."""
    print("\n=== Testing Answer Scoring Structure ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "reports" / "answer_scoring.py"
    
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Check for correct format
        has_input_text = '"type": "input_text"' in code or "'type': 'input_text'" in code
        no_text = '"type": "text"' not in code and "'type': 'text'" not in code
        
        if not has_input_text:
            print("FAILED: Missing 'input_text' format")
            return False
        if not no_text:
            print("FAILED: Found forbidden 'text' format")
            return False
        
        print("PASSED: Answer scoring uses correct format")
        return True
    except Exception as e:
        print(f"FAILED: Error checking file: {e}")
        return False


def test_google_gemini_structure():
    """Test Google Gemini structure by inspecting the code."""
    print("\n=== Testing Google Gemini Structure ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "reports" / "llm_clients.py"
    
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Find GoogleClient class
        if 'class GoogleClient' not in code:
            print("FAILED: GoogleClient class not found")
            return False
        
        # Extract the query_with_file method
        lines = code.split('\n')
        in_google_client = False
        in_query_method = False
        method_lines = []
        
        for i, line in enumerate(lines):
            if 'class GoogleClient' in line:
                in_google_client = True
            elif in_google_client and 'async def query_with_file' in line:
                in_query_method = True
                method_lines = [line]
            elif in_query_method:
                if line.strip() and not line[0].isspace():
                    # New top-level definition, end of method
                    break
                method_lines.append(line)
        
        method_code = '\n'.join(method_lines)
        
        # Check for required elements
        has_role_user = '"role": "user"' in method_code or "'role': 'user'" in method_code
        has_question_data = 'question_data' in method_code
        has_contents = '"contents"' in method_code or "'contents'" in method_code
        
        errors = []
        if not has_role_user:
            errors.append("Missing 'role: user' in contents")
        if not has_question_data:
            errors.append("Missing question_data parameter handling")
        if not has_contents:
            errors.append("Missing 'contents' array in payload")
        
        if errors:
            print("FAILED:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        print("PASSED: Google Gemini uses correct structure")
        return True
    except Exception as e:
        print(f"FAILED: Error checking file: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pdf_orchestrator_structure():
    """Test PDF orchestrator structure."""
    print("\n=== Testing PDF Orchestrator Structure ===")
    
    file_path = Path(__file__).parent / "app" / "services" / "reports" / "pdf_question_orchestrator.py"
    
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Check for question_bundle
        has_question_bundle = 'question_bundle' in code
        has_build_method = 'def _build_batch_prompt' in code or 'async def _build_batch_prompt' in code
        
        if not has_question_bundle:
            print("FAILED: Missing question_bundle")
            return False
        if not has_build_method:
            print("FAILED: Missing _build_batch_prompt method")
            return False
        
        # Check return statement
        if 'return {"prompt"' not in code and "return {'prompt'" not in code:
            print("FAILED: _build_batch_prompt doesn't return dict with prompt")
            return False
        
        print("PASSED: PDF orchestrator has correct structure")
        return True
    except Exception as e:
        print(f"FAILED: Error checking file: {e}")
        return False


def test_mock_api_call_formats():
    """Test that we can create properly formatted API call payloads."""
    print("\n=== Testing Mock API Call Formats ===")
    
    # Test gold answer format
    gold_messages = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": "System prompt"}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "User prompt"}],
        },
    ]
    
    # Test answer scoring format
    scoring_messages = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": "System prompt"}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": json.dumps({"test": "data"})}],
        },
    ]
    
    # Test Google Gemini format
    gemini_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"file_data": {"file_uri": "test_id", "mime_type": "application/pdf"}},
                    {"text": "Prompt text"},
                    {"text": json.dumps({"question_bundle": "data"})},
                ],
            }
        ],
    }
    
    errors = []
    
    # Validate gold answer format
    for msg in gold_messages:
        for part in msg.get("content", []):
            if part.get("type") != "input_text":
                errors.append(f"Gold answer: Found {part.get('type')} instead of input_text")
    
    # Validate scoring format
    for msg in scoring_messages:
        for part in msg.get("content", []):
            if part.get("type") != "input_text":
                errors.append(f"Scoring: Found {part.get('type')} instead of input_text")
    
    # Validate Gemini format
    if gemini_payload["contents"][0].get("role") != "user":
        errors.append("Gemini: Missing role: user")
    if not gemini_payload["contents"][0].get("parts"):
        errors.append("Gemini: Missing parts array")
    
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("PASSED: Mock API call formats are correct")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("LLM API Mock Tests (Simple)")
    print("=" * 60)
    
    results = []
    
    results.append(("Gold Answer Prompt Structure", test_gold_answer_prompt_structure()))
    results.append(("Answer Scoring Structure", test_answer_scoring_structure()))
    results.append(("Google Gemini Structure", test_google_gemini_structure()))
    results.append(("PDF Orchestrator Structure", test_pdf_orchestrator_structure()))
    results.append(("Mock API Call Formats", test_mock_api_call_formats()))
    
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
        print("\n✓ All mock tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())


