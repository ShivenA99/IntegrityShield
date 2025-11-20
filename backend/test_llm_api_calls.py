#!/usr/bin/env python3
"""
Validation script to test LLM API call formats with dummy requests.
This ensures all API calls use correct syntax before running the actual pipeline.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from app.config import BaseConfig

# Initialize Flask app for config access
app = Flask(__name__)
app.config.from_object(BaseConfig)

# Set required environment variables if not set
if not app.config.get("OPENAI_API_KEY"):
    print("WARNING: OPENAI_API_KEY not set. Some tests will be skipped.")
if not app.config.get("GOOGLE_AI_KEY"):
    print("WARNING: GOOGLE_AI_KEY not set. Google tests will be skipped.")
if not app.config.get("ANTHROPIC_API_KEY"):
    print("WARNING: ANTHROPIC_API_KEY not set. Anthropic tests will be skipped.")


def test_gold_answer_responses_format():
    """Test that gold answer service uses correct Responses API format."""
    print("\n=== Testing Gold Answer Responses API Format ===")
    
    with app.app_context():
        from app.services.pipeline.gold_answer_generation_service import GoldAnswerGenerationService
        
        service = GoldAnswerGenerationService()
        if not service.is_configured():
            print("SKIP: Gold answer service not configured")
            return False
        
        # Create a dummy question
        question = {
            "question_number": "1",
            "stem_text": "What is 2+2?",
            "question_type": "mcq_single",
            "options": {"A": "3", "B": "4", "C": "5"},
        }
        document = {}
        
        messages = service._build_prompt(question, document)
        
        # Verify format
        errors = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", [])
            for part in content:
                part_type = part.get("type")
                if part_type == "text":
                    errors.append(f"Found 'text' instead of 'input_text' in {role} message")
                elif part_type == "image_url":
                    errors.append(f"Found 'image_url' instead of 'input_image' in {role} message")
                elif part_type not in ("input_text", "input_image"):
                    errors.append(f"Unknown content type: {part_type} in {role} message")
        
        if errors:
            print("FAILED:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        print("PASSED: Gold answer service uses correct Responses API format")
        return True


def test_answer_scoring_responses_format():
    """Test that answer scoring service uses correct Responses API format."""
    print("\n=== Testing Answer Scoring Responses API Format ===")
    
    with app.app_context():
        from app.services.reports.answer_scoring import AnswerScoringService
        
        service = AnswerScoringService()
        if not service.enabled:
            print("SKIP: Answer scoring service not enabled")
            return False
        
        # Check the _score_answers_with_responses method by inspecting source
        import inspect
        source = inspect.getsource(service._score_answers_with_responses)
        
        errors = []
        if '"type": "text"' in source:
            errors.append("Found 'text' instead of 'input_text' in scoring service")
        
        if errors:
            print("FAILED:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        print("PASSED: Answer scoring service uses correct Responses API format")
        return True


def test_gemini_question_bundle_format():
    """Test that Google Gemini client properly formats question bundle."""
    print("\n=== Testing Google Gemini Question Bundle Format ===")
    
    with app.app_context():
        from app.services.reports.llm_clients import GoogleClient
        
        client = GoogleClient(
            api_key=app.config.get("GOOGLE_AI_KEY"),
            model="models/gemini-1.5-pro"
        )
        
        if not client.is_configured():
            print("SKIP: Google client not configured")
            return False
        
        # Check the query_with_file method by inspecting source
        import inspect
        source = inspect.getsource(client.query_with_file)
        
        errors = []
        if '"role": "user"' not in source:
            errors.append("Missing 'role: user' in contents array")
        if "question_data" not in source:
            errors.append("Missing question_data parameter handling")
        
        if errors:
            print("FAILED:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        print("PASSED: Google Gemini client properly formats question bundle")
        return True


def test_pdf_orchestrator_question_bundle():
    """Test that PDF orchestrator builds and passes question bundle."""
    print("\n=== Testing PDF Orchestrator Question Bundle ===")
    
    with app.app_context():
        from app.services.reports.pdf_question_orchestrator import PDFQuestionEvaluator, QuestionPrompt
        
        # Create dummy questions
        questions = [
            QuestionPrompt(
                question_id=1,
                question_number="1",
                question_text="What is 2+2?",
                question_type="mcq_single",
                options=[{"label": "A", "text": "3"}, {"label": "B", "text": "4"}],
                gold_answer="B",
            )
        ]
        
        evaluator = PDFQuestionEvaluator(prompts=["dummy"])
        payload = evaluator._build_batch_prompt("google", questions)
        
        errors = []
        if "question_bundle" not in payload:
            errors.append("Missing 'question_bundle' in payload")
        if "prompt" not in payload:
            errors.append("Missing 'prompt' in payload")
        
        if errors:
            print("FAILED:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        print("PASSED: PDF orchestrator builds question bundle correctly")
        return True


async def test_gold_answer_actual_call():
    """Test actual gold answer API call (if configured)."""
    print("\n=== Testing Gold Answer Actual API Call ===")
    
    with app.app_context():
        from app.services.pipeline.gold_answer_generation_service import GoldAnswerGenerationService
        
        service = GoldAnswerGenerationService()
        if not service.is_configured():
            print("SKIP: Gold answer service not configured")
            return False
        
        question = {
            "question_number": "1",
            "stem_text": "What is 2+2?",
            "question_type": "mcq_single",
            "options": {"A": "3", "B": "4", "C": "5"},
        }
        document = {}
        
        messages = service._build_prompt(question, document)
        
        try:
            result = await service._call_model_async(question, messages)
            if result:
                print(f"PASSED: Gold answer API call successful (got: {result.get('gold_answer')})")
                return True
            else:
                print("FAILED: Gold answer API call returned None")
                return False
        except Exception as exc:
            print(f"FAILED: Gold answer API call raised exception: {exc}")
            return False


async def test_answer_scoring_actual_call():
    """Test actual answer scoring API call (if configured)."""
    print("\n=== Testing Answer Scoring Actual API Call ===")
    
    with app.app_context():
        from app.services.reports.answer_scoring import AnswerScoringService
        
        service = AnswerScoringService()
        if not service.enabled:
            print("SKIP: Answer scoring service not enabled")
            return False
        
        provider_answers = [
            {"provider": "openai", "answer_label": "B", "answer_text": "4"},
            {"provider": "anthropic", "answer_label": "B", "answer_text": "4"},
        ]
        
        try:
            results = service._score_answers_with_responses(
                question_text="What is 2+2?",
                question_type="mcq_single",
                gold_answer="B",
                provider_answers=provider_answers,
                options=[{"label": "A", "text": "3"}, {"label": "B", "text": "4"}],
                detection_context=None,
            )
            if results:
                print(f"PASSED: Answer scoring API call successful (got {len(results)} results)")
                return True
            else:
                print("FAILED: Answer scoring API call returned empty results")
                return False
        except Exception as exc:
            print(f"FAILED: Answer scoring API call raised exception: {exc}")
            return False


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("LLM API Call Format Validation Tests")
    print("=" * 60)
    
    results = []
    
    # Format validation tests (no API calls)
    results.append(("Gold Answer Format", test_gold_answer_responses_format()))
    results.append(("Answer Scoring Format", test_answer_scoring_responses_format()))
    results.append(("Gemini Question Bundle Format", test_gemini_question_bundle_format()))
    results.append(("PDF Orchestrator Bundle", test_pdf_orchestrator_question_bundle()))
    
    # Actual API call tests (if configured)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results.append(("Gold Answer API Call", loop.run_until_complete(test_gold_answer_actual_call())))
        results.append(("Answer Scoring API Call", loop.run_until_complete(test_answer_scoring_actual_call())))
    finally:
        loop.close()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "SKIP/FAIL"
        print(f"{name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed or skipped")
        return 1


if __name__ == "__main__":
    sys.exit(main())

