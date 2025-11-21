#!/usr/bin/env python3
"""Test the validation service fixes."""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Set up Flask app context
from flask import Flask
from app.config import BaseConfig

# Initialize Flask app for config access
app = Flask(__name__)
app.config.from_object(BaseConfig)

# Suppress Flask-Migrate warnings
import logging
logging.getLogger('flask_migrate').setLevel(logging.ERROR)

from app.services.validation.gpt5_validation_service import GPT5ValidationService

async def test_validation_service():
    """Test that validation service works without response_format."""
    with app.app_context():
        service = GPT5ValidationService()
        
        if not service.is_configured():
            print("❌ OpenAI API key not configured. Set OPENAI_API_KEY environment variable.")
            return False
        
        print("✅ Validation service is configured")
        
        # Test with a simple MCQ question
        question_text = "What is the unit of electrical resistance?"
        question_type = "mcq_single"
        gold_answer = "B. Ohm"
        test_answer = "A. Ampere"  # Different answer - should show deviation
        
        options_data = {
            "A": "Ampere",
            "B": "Ohm",
            "C": "Volt",
            "D": "Watt"
        }
        
        print(f"\n📝 Testing validation:")
        print(f"   Question: {question_text}")
        print(f"   Gold Answer: {gold_answer}")
        print(f"   Test Answer: {test_answer}")
        print(f"   Question Type: {question_type}")
        
        try:
            result = service.validate_answer_deviation(
                question_text=question_text,
                question_type=question_type,
                gold_answer=gold_answer,
                test_answer=test_answer,
                options_data=options_data,
                target_option="A",
                target_option_text="Ampere",
                run_id="test-run-123"
            )
            
            print(f"\n✅ Validation completed successfully!")
            print(f"   Is Valid: {result.is_valid}")
            print(f"   Confidence: {result.confidence:.3f}")
            print(f"   Deviation Score: {result.deviation_score:.3f}")
            print(f"   Reasoning: {result.reasoning[:200]}...")
            print(f"   Model Used: {result.model_used}")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Validation failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_validation_api_format():
    """Test that validation service uses correct API format (no response_format, input_text)."""
    print("\n📋 Checking validation service API format...")
    
    import inspect
    from app.services.validation.gpt5_validation_service import GPT5ValidationService
    
    service = GPT5ValidationService()
    source = inspect.getsource(service.validate_answer_deviation)
    
    errors = []
    if 'response_format=' in source:
        errors.append("❌ Found 'response_format' parameter (should be removed)")
    if '"type": "text"' in source:
        errors.append("❌ Found 'type: text' (should be 'input_text')")
    if '"type": "input_text"' not in source:
        errors.append("❌ Missing 'input_text' type in content")
    
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"   {error}")
        return False
    
    print("✅ Validation service uses correct API format:")
    print("   ✓ No 'response_format' parameter")
    print("   ✓ Uses 'input_text' for content type")
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Validation Service Fixes")
    print("=" * 60)
    
    # Test 1: Validation service API format check
    print("\n[Test 1] Validation Service API Format Check")
    print("-" * 60)
    format_ok = test_validation_api_format()
    
    # Test 2: Validation service actual API call
    print("\n[Test 2] Validation Service API Call")
    print("-" * 60)
    validation_ok = await test_validation_service()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"API Format Check: {'✅ PASS' if format_ok else '❌ FAIL'}")
    print(f"API Call Test: {'✅ PASS' if validation_ok else '❌ FAIL'}")
    
    if format_ok and validation_ok:
        print("\n🎉 All tests passed!")
        print("\n✅ Validation service is fixed and working correctly:")
        print("   - No 'response_format' parameter (removed)")
        print("   - Uses 'input_text' for content type")
        print("   - API calls succeed without errors")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

